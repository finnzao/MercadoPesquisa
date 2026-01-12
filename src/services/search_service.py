"""
Serviço de Busca - Orquestrador Principal.

Este serviço coordena:
- Cache Redis
- Rate limiting
- Circuit breaker
- Fan-out paralelo para mercados
- Normalização de preços
- Ranking de resultados

É a camada entre a API e os scrapers/pipeline.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, Any
from uuid import uuid4

from config.settings import get_settings
from config.logging_config import LoggerMixin, get_logger
from config.markets import get_active_markets, MARKETS_CONFIG

from src.core.models import PriceOffer, SearchResult, CollectionMetadata
from src.pipeline import ProcessingPipeline
from src.ranking import OfferRanker
from src.scrapers import ScraperManager
from src.services.cache_service import CacheService, RateLimiter, get_cache_service, get_rate_limiter


class CircuitState(str, Enum):
    """Estados do circuit breaker."""
    CLOSED = "closed"      # Normal - permite requisições
    OPEN = "open"          # Falhas demais - bloqueia requisições
    HALF_OPEN = "half_open"  # Testando recuperação


@dataclass
class CircuitBreaker:
    """
    Circuit breaker para um mercado específico.
    
    Previne requisições para mercados com falhas recorrentes.
    """
    market_id: str
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None
    
    # Configurações
    failure_threshold: int = 3
    recovery_timeout_seconds: int = 60
    half_open_max_calls: int = 1
    
    def record_success(self) -> None:
        """Registra sucesso."""
        self.success_count += 1
        self.last_success_time = datetime.now()
        
        if self.state == CircuitState.HALF_OPEN:
            # Recuperou - fecha o circuito
            self.state = CircuitState.CLOSED
            self.failure_count = 0
    
    def record_failure(self) -> None:
        """Registra falha."""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
    
    def can_execute(self) -> bool:
        """Verifica se pode executar requisição."""
        if self.state == CircuitState.CLOSED:
            return True
        
        if self.state == CircuitState.OPEN:
            # Verifica se passou o tempo de recovery
            if self.last_failure_time:
                elapsed = (datetime.now() - self.last_failure_time).total_seconds()
                if elapsed >= self.recovery_timeout_seconds:
                    self.state = CircuitState.HALF_OPEN
                    return True
            return False
        
        # HALF_OPEN - permite uma chamada de teste
        return True
    
    def to_dict(self) -> dict:
        """Converte para dicionário."""
        return {
            "market_id": self.market_id,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure": self.last_failure_time.isoformat() if self.last_failure_time else None,
            "last_success": self.last_success_time.isoformat() if self.last_success_time else None,
        }


@dataclass
class SearchRequest:
    """Requisição de busca."""
    query: str
    cep: Optional[str] = None
    markets: Optional[list[str]] = None
    max_pages: int = 1
    user_id: Optional[str] = None
    request_id: str = field(default_factory=lambda: str(uuid4())[:8])
    
    def __post_init__(self):
        self.query = self.query.strip()
        if self.cep:
            self.cep = self.cep.replace("-", "").replace(".", "")


@dataclass
class SearchResponse:
    """Resposta de busca."""
    request_id: str
    query: str
    status: str  # "success", "partial", "error", "cached"
    
    # Resultados
    total_results: int = 0
    results: list[dict] = field(default_factory=list)
    
    # Metadados
    markets_searched: list[str] = field(default_factory=list)
    markets_failed: list[str] = field(default_factory=list)
    cache_hit: bool = False
    duration_ms: int = 0
    
    # Melhor oferta
    best_offer: Optional[dict] = None
    
    # Erros
    errors: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        """Converte para dicionário."""
        return {
            "request_id": self.request_id,
            "query": self.query,
            "status": self.status,
            "total_results": self.total_results,
            "results": self.results,
            "best_offer": self.best_offer,
            "metadata": {
                "markets_searched": self.markets_searched,
                "markets_failed": self.markets_failed,
                "cache_hit": self.cache_hit,
                "duration_ms": self.duration_ms,
            },
            "errors": self.errors if self.errors else None,
        }


class SearchService(LoggerMixin):
    """
    Serviço principal de busca.
    
    Orquestra todo o fluxo de busca:
    1. Verifica cache
    2. Verifica rate limits
    3. Verifica circuit breakers
    4. Executa fan-out paralelo
    5. Processa resultados
    6. Aplica ranking
    7. Cacheia resultados
    
    Uso:
        service = SearchService()
        response = await service.search(SearchRequest(query="arroz 5kg"))
    """
    
    def __init__(self):
        self.settings = get_settings()
        
        # Componentes
        self.scraper_manager = ScraperManager()
        self.pipeline = ProcessingPipeline()
        self.ranker = OfferRanker()
        
        # Cache e rate limiting (lazy init)
        self._cache: Optional[CacheService] = None
        self._rate_limiter: Optional[RateLimiter] = None
        
        # Circuit breakers por mercado
        self._circuit_breakers: dict[str, CircuitBreaker] = {}
        self._init_circuit_breakers()
    
    def _init_circuit_breakers(self) -> None:
        """Inicializa circuit breakers para cada mercado."""
        for market_id in self.settings.mercados_enabled:
            self._circuit_breakers[market_id] = CircuitBreaker(
                market_id=market_id,
                failure_threshold=self.settings.circuit_breaker_failure_threshold,
                recovery_timeout_seconds=self.settings.circuit_breaker_recovery_timeout_seconds,
                half_open_max_calls=self.settings.circuit_breaker_half_open_max_calls,
            )
    
    async def _get_cache(self) -> CacheService:
        """Obtém serviço de cache."""
        if self._cache is None:
            self._cache = await get_cache_service()
        return self._cache
    
    async def _get_rate_limiter(self) -> RateLimiter:
        """Obtém rate limiter."""
        if self._rate_limiter is None:
            self._rate_limiter = await get_rate_limiter()
        return self._rate_limiter
    
    async def search(self, request: SearchRequest) -> SearchResponse:
        """
        Executa busca completa.
        
        Args:
            request: Requisição de busca
            
        Returns:
            SearchResponse com resultados
        """
        start_time = datetime.now()
        
        self.logger.info(
            "Iniciando busca",
            request_id=request.request_id,
            query=request.query,
            cep=request.cep,
            user_id=request.user_id,
        )
        
        response = SearchResponse(
            request_id=request.request_id,
            query=request.query,
            status="success",
        )
        
        try:
            # 1. Verifica rate limit do usuário
            if request.user_id:
                rate_limiter = await self._get_rate_limiter()
                allowed, remaining, ttl = await rate_limiter.check_user(request.user_id)
                
                if not allowed:
                    response.status = "error"
                    response.errors.append(f"Rate limit excedido. Tente novamente em {ttl}s.")
                    return response
            
            # 2. Verifica cache
            cache = await self._get_cache()
            cached_result = await cache.get_search_result(
                query=request.query,
                cep=request.cep,
                markets=request.markets,
            )
            
            if cached_result:
                response.status = "cached"
                response.cache_hit = True
                response.total_results = cached_result.get("total_results", 0)
                response.results = cached_result.get("results", [])
                response.best_offer = cached_result.get("best_offer")
                response.markets_searched = cached_result.get("markets_searched", [])
                response.duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                
                self.logger.info(
                    "Cache hit",
                    request_id=request.request_id,
                    results=response.total_results,
                )
                return response
            
            # 3. Determina mercados para buscar
            target_markets = self._get_target_markets(request.markets)
            
            if not target_markets:
                response.status = "error"
                response.errors.append("Nenhum mercado disponível para busca.")
                return response
            
            # 4. Executa fan-out paralelo com timeout global
            try:
                async with asyncio.timeout(self.settings.collector_global_timeout_seconds):
                    offers, markets_success, markets_failed = await self._fan_out_search(
                        query=request.query,
                        cep=request.cep,
                        markets=target_markets,
                        max_pages=request.max_pages,
                    )
            except asyncio.TimeoutError:
                self.logger.warning(
                    "Timeout global na busca",
                    request_id=request.request_id,
                )
                offers = []
                markets_success = []
                markets_failed = target_markets
            
            response.markets_searched = markets_success
            response.markets_failed = markets_failed
            
            if markets_failed:
                response.status = "partial" if markets_success else "error"
            
            # 5. Processa e rankeia resultados
            if offers:
                processed_results = self._process_results(
                    offers=offers,
                    query=request.query,
                )
                
                response.total_results = len(processed_results)
                response.results = processed_results
                
                # Encontra melhor oferta
                if processed_results:
                    response.best_offer = processed_results[0]
            
            # 6. Cacheia resultados (se teve sucesso)
            if response.status in ("success", "partial") and response.results:
                await cache.set_search_result(
                    query=request.query,
                    cep=request.cep,
                    markets=request.markets,
                    result={
                        "total_results": response.total_results,
                        "results": response.results,
                        "best_offer": response.best_offer,
                        "markets_searched": response.markets_searched,
                    },
                )
            
        except Exception as e:
            self.logger.error(
                "Erro na busca",
                request_id=request.request_id,
                error=str(e),
                exc_info=True,
            )
            response.status = "error"
            response.errors.append(str(e))
        
        response.duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
        
        self.logger.info(
            "Busca finalizada",
            request_id=request.request_id,
            status=response.status,
            results=response.total_results,
            duration_ms=response.duration_ms,
        )
        
        return response
    
    def _get_target_markets(self, requested_markets: Optional[list[str]]) -> list[str]:
        """
        Determina mercados para buscar, considerando:
        - Mercados solicitados
        - Mercados habilitados
        - Estado dos circuit breakers
        """
        # Se especificou mercados, usa apenas esses
        if requested_markets:
            candidates = [
                m for m in requested_markets
                if m in self.settings.mercados_enabled
            ]
        else:
            candidates = self.settings.mercados_enabled.copy()
        
        # Filtra por circuit breaker
        available = []
        for market_id in candidates:
            cb = self._circuit_breakers.get(market_id)
            if cb and cb.can_execute():
                available.append(market_id)
            else:
                self.logger.debug(
                    "Mercado bloqueado pelo circuit breaker",
                    market=market_id,
                    state=cb.state.value if cb else "unknown",
                )
        
        return available
    
    async def _fan_out_search(
        self,
        query: str,
        cep: Optional[str],
        markets: list[str],
        max_pages: int,
    ) -> tuple[list[PriceOffer], list[str], list[str]]:
        """
        Executa busca em paralelo em múltiplos mercados.
        
        Args:
            query: Termo de busca
            cep: CEP
            markets: Lista de mercados
            max_pages: Máximo de páginas
            
        Returns:
            Tupla (ofertas, mercados_sucesso, mercados_falha)
        """
        all_offers: list[PriceOffer] = []
        markets_success: list[str] = []
        markets_failed: list[str] = []
        
        # Cria tasks para cada mercado
        tasks = []
        for market_id in markets:
            task = self._search_single_market(
                market_id=market_id,
                query=query,
                cep=cep,
                max_pages=max_pages,
            )
            tasks.append((market_id, task))
        
        # Executa em paralelo com semáforo para limitar concorrência
        semaphore = asyncio.Semaphore(self.settings.collector_concurrent_limit)
        
        async def bounded_task(market_id: str, task):
            async with semaphore:
                return market_id, await task
        
        results = await asyncio.gather(
            *[bounded_task(m, t) for m, t in tasks],
            return_exceptions=True,
        )
        
        # Processa resultados
        for result in results:
            if isinstance(result, Exception):
                self.logger.error("Erro em task de mercado", error=str(result))
                continue
            
            market_id, (offers, success) = result
            
            cb = self._circuit_breakers.get(market_id)
            
            if success and offers:
                all_offers.extend(offers)
                markets_success.append(market_id)
                if cb:
                    cb.record_success()
            else:
                markets_failed.append(market_id)
                if cb:
                    cb.record_failure()
        
        return all_offers, markets_success, markets_failed
    
    async def _search_single_market(
        self,
        market_id: str,
        query: str,
        cep: Optional[str],
        max_pages: int,
    ) -> tuple[list[PriceOffer], bool]:
        """
        Busca em um único mercado com timeout individual.
        
        Returns:
            Tupla (ofertas, sucesso)
        """
        try:
            async with asyncio.timeout(self.settings.collector_timeout_seconds):
                result = await self.scraper_manager.search_single(
                    market_id=market_id,
                    query=query,
                    cep=cep,
                    max_pages=max_pages,
                )
                
                if result.products:
                    # Processa pelo pipeline
                    offers = self.pipeline.process_batch(
                        result.products,
                        apply_ranking=False,  # Ranking será aplicado depois
                        search_query=query,
                    )
                    return offers, True
                
                return [], True  # Sucesso mas sem resultados
                
        except asyncio.TimeoutError:
            self.logger.warning(
                "Timeout em mercado",
                market=market_id,
                timeout=self.settings.collector_timeout_seconds,
            )
            return [], False
            
        except Exception as e:
            self.logger.error(
                "Erro ao buscar em mercado",
                market=market_id,
                error=str(e),
            )
            return [], False
    
    def _process_results(
        self,
        offers: list[PriceOffer],
        query: str,
    ) -> list[dict]:
        """
        Processa e rankeia ofertas.
        
        Args:
            offers: Lista de ofertas brutas
            query: Query original
            
        Returns:
            Lista de dicts ordenados por relevância/preço
        """
        if not offers:
            return []
        
        # Aplica ranking
        ranked = self.pipeline.get_ranked_offers(offers, query)
        
        # Converte para dicts
        results = []
        for ro in ranked:
            offer = ro.offer
            results.append({
                "rank": ro.rank,
                "title": offer.title,
                "price": float(offer.price),
                "price_formatted": offer.format_price(),
                "normalized_price": float(offer.normalized_price) if offer.normalized_price else None,
                "normalized_price_formatted": offer.format_normalized_price(),
                "market_id": offer.market_id,
                "market_name": offer.market_name,
                "url": offer.url,
                "image_url": offer.image_url,
                "is_relevant": ro.is_relevant,
                "is_comparable": offer.is_comparable,
                "relevance_score": round(ro.relevance_score, 2),
                "price_score": round(ro.price_score, 2),
                "final_score": round(ro.final_score, 2),
            })
        
        return results
    
    def get_circuit_breakers_status(self) -> dict[str, dict]:
        """Retorna status de todos os circuit breakers."""
        return {
            market_id: cb.to_dict()
            for market_id, cb in self._circuit_breakers.items()
        }
    
    def reset_circuit_breaker(self, market_id: str) -> bool:
        """Reseta circuit breaker de um mercado."""
        cb = self._circuit_breakers.get(market_id)
        if cb:
            cb.state = CircuitState.CLOSED
            cb.failure_count = 0
            self.logger.info("Circuit breaker resetado", market=market_id)
            return True
        return False


# Instância global para uso simplificado
_search_service: Optional[SearchService] = None


async def get_search_service() -> SearchService:
    """Retorna instância do serviço de busca."""
    global _search_service
    if _search_service is None:
        _search_service = SearchService()
    return _search_service
