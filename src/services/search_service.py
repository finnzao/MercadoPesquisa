# src/services/search_service.py
"""
Serviço de Busca - Orquestrador Principal.

- Cache multi-layer (L1 memória + L2 Redis)
- Early return quando atingir resultados mínimos
- Streaming de resultados (não espera todos os mercados)
- Timeout por mercado + timeout global
- Priorização de mercados mais rápidos
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Tuple, List
from uuid import uuid4

from config.settings import get_settings
from config.logging_config import LoggerMixin

from src.core.models import PriceOffer
from src.pipeline import ProcessingPipeline
from src.ranking import ResultRanker
from src.scrapers import ScraperManager

# Importa do novo módulo de cache
from src.services.cache import (
    CacheService,
    RateLimiter,
    get_cache_service,
    get_rate_limiter,
)


class CircuitState(str, Enum):
    """Estados do circuit breaker."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    """Circuit breaker para um mercado específico."""
    market_id: str
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None
    
    failure_threshold: int = 3
    recovery_timeout_seconds: int = 60
    half_open_max_calls: int = 1
    
    def record_success(self) -> None:
        self.success_count += 1
        self.last_success_time = datetime.now()
        
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
            self.failure_count = 0
    
    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
    
    def can_execute(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        
        if self.state == CircuitState.OPEN:
            if self.last_failure_time:
                elapsed = (datetime.now() - self.last_failure_time).total_seconds()
                if elapsed >= self.recovery_timeout_seconds:
                    self.state = CircuitState.HALF_OPEN
                    return True
            return False
        
        return True
    
    def to_dict(self) -> dict:
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
    
    # Configurações de performance
    timeout_seconds: float = 10.0  # Timeout global
    market_timeout_seconds: float = 8.0  # Timeout por mercado
    min_results: int = 5  # Early return se atingir
    enable_early_return: bool = True
    
    def __post_init__(self):
        self.query = self.query.strip()
        if self.cep:
            self.cep = self.cep.replace("-", "").replace(".", "")


@dataclass
class SearchResponse:
    """Resposta de busca."""
    request_id: str
    query: str
    status: str
    
    total_results: int = 0
    results: list[dict] = field(default_factory=list)
    
    markets_searched: list[str] = field(default_factory=list)
    markets_failed: list[str] = field(default_factory=list)
    markets_pending: list[str] = field(default_factory=list)
    cache_hit: bool = False
    duration_ms: int = 0
    
    best_offer: Optional[dict] = None
    errors: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
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
                "markets_pending": self.markets_pending,
                "cache_hit": self.cache_hit,
                "duration_ms": self.duration_ms,
            },
            "errors": self.errors if self.errors else None,
        }


class SearchService(LoggerMixin):
    """
    Serviço principal de busca otimizado.
    
    OTIMIZAÇÕES:
    1. Cache multi-layer (L1 memória + L2 Redis)
    2. Early return quando atingir min_results
    3. Streaming de resultados (processa conforme completam)
    4. Timeout por mercado + timeout global
    5. Priorização de mercados mais rápidos
    """
    
    def __init__(self):
        self.settings = get_settings()
        
        # Componentes
        self.scraper_manager = ScraperManager()
        self.pipeline = ProcessingPipeline()
        self.ranker = ResultRanker()
        
        # Cache e rate limiting (lazy init)
        self._cache: Optional[CacheService] = None
        self._rate_limiter: Optional[RateLimiter] = None
        
        # Circuit breakers por mercado
        self._circuit_breakers: dict[str, CircuitBreaker] = {}
        self._init_circuit_breakers()
        
        # Estatísticas de latência por mercado (para priorização)
        self._market_latencies: dict[str, float] = {}
    
    def _init_circuit_breakers(self) -> None:
        for market_id in self.settings.mercados_enabled:
            self._circuit_breakers[market_id] = CircuitBreaker(
                market_id=market_id,
                failure_threshold=self.settings.circuit_breaker_failure_threshold,
                recovery_timeout_seconds=self.settings.circuit_breaker_recovery_timeout_seconds,
                half_open_max_calls=self.settings.circuit_breaker_half_open_max_calls,
            )
    
    async def _get_cache(self) -> CacheService:
        if self._cache is None:
            self._cache = await get_cache_service()
        return self._cache
    
    async def _get_rate_limiter(self) -> RateLimiter:
        if self._rate_limiter is None:
            self._rate_limiter = await get_rate_limiter()
        return self._rate_limiter
    
    async def search(self, request: SearchRequest) -> SearchResponse:
        """
        Executa busca otimizada com early return e streaming.
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
                result = await rate_limiter.check_user(request.user_id)
                
                if not result.allowed:
                    response.status = "error"
                    response.errors.append(
                        f"Rate limit excedido. Tente novamente em {result.reset_in_seconds}s."
                    )
                    return response
            
            # 2. Verifica cache (L1 -> L2)
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
                    duration_ms=response.duration_ms,
                )
                return response
            
            # 3. Determina mercados para buscar (priorizados por latência)
            target_markets = self._get_prioritized_markets(request.markets)
            
            if not target_markets:
                response.status = "error"
                response.errors.append("Nenhum mercado disponível para busca.")
                return response
            
            # 4. Executa busca com streaming e early return
            all_offers, completed_markets, failed_markets, pending_markets = await self._streaming_search(
                request=request,
                target_markets=target_markets,
            )
            
            response.markets_searched = completed_markets
            response.markets_failed = failed_markets
            response.markets_pending = pending_markets
            
            if failed_markets or pending_markets:
                response.status = "partial" if completed_markets else "error"
            
            # 5. Processa e rankeia resultados
            if all_offers:
                processed_results = self._process_results(
                    offers=all_offers,
                    query=request.query,
                )
                
                response.total_results = len(processed_results)
                response.results = processed_results
                
                if processed_results:
                    response.best_offer = processed_results[0]
            
            # 6. Cacheia resultados (se teve sucesso)
            if response.status in ("success", "partial") and response.results:
                # Detecta se há itens promocionais
                has_promo = any(
                    r.get("is_promotional", False) 
                    for r in response.results
                )
                
                # Calcula popularidade simplificada
                query_popularity = min(response.total_results / 100, 1.0)
                
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
                    is_promotional=has_promo,
                    query_popularity=query_popularity,
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
            cache_hit=response.cache_hit,
        )
        
        return response
    
    def _get_prioritized_markets(self, requested_markets: Optional[list[str]]) -> list[str]:
        """
        Determina mercados para buscar, ordenados por latência histórica.
        Mercados mais rápidos primeiro = early return mais eficiente.
        """
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
        
        # Ordena por latência (mais rápidos primeiro)
        return sorted(
            available,
            key=lambda m: self._market_latencies.get(m, 999),
        )
    
    async def _streaming_search(
        self,
        request: SearchRequest,
        target_markets: list[str],
    ) -> Tuple[List[PriceOffer], List[str], List[str], List[str]]:
        """
        Busca com streaming e early return.
        
        Processa resultados conforme os mercados completam,
        e retorna assim que atingir min_results.
        """
        all_offers: List[PriceOffer] = []
        completed_markets: List[str] = []
        failed_markets: List[str] = []
        pending_markets: List[str] = list(target_markets)
        
        try:
            async with asyncio.timeout(request.timeout_seconds):
                # Cria tasks para todos os mercados
                tasks = {
                    asyncio.create_task(
                        self._search_market_with_timeout(
                            market_id=market_id,
                            query=request.query,
                            cep=request.cep,
                            max_pages=request.max_pages,
                            timeout=request.market_timeout_seconds,
                        )
                    ): market_id
                    for market_id in target_markets
                }
                
                # Processa conforme completam (streaming)
                for coro in asyncio.as_completed(tasks.keys()):
                    try:
                        market_id, offers, latency, success = await coro
                        
                        # Remove da lista de pendentes
                        if market_id in pending_markets:
                            pending_markets.remove(market_id)
                        
                        # Atualiza circuit breaker
                        cb = self._circuit_breakers.get(market_id)
                        
                        if success and offers:
                            all_offers.extend(offers)
                            completed_markets.append(market_id)
                            if cb:
                                cb.record_success()
                            # Atualiza latência para priorização futura
                            self._market_latencies[market_id] = latency
                        elif success:
                            completed_markets.append(market_id)
                            if cb:
                                cb.record_success()
                        else:
                            failed_markets.append(market_id)
                            if cb:
                                cb.record_failure()
                        
                        # Early return se já tem resultados suficientes
                        if (
                            request.enable_early_return
                            and len(all_offers) >= request.min_results
                        ):
                            self.logger.info(
                                "Early return ativado",
                                results=len(all_offers),
                                completed=len(completed_markets),
                                pending=len(pending_markets),
                            )
                            # Cancela tasks pendentes
                            for task in tasks.keys():
                                if not task.done():
                                    task.cancel()
                            break
                            
                    except asyncio.CancelledError:
                        continue
                    except Exception as e:
                        self.logger.debug(f"Erro em mercado: {e}")
                        continue
                        
        except asyncio.TimeoutError:
            self.logger.warning(
                "Timeout global",
                completed=len(completed_markets),
                pending=len(pending_markets),
            )
            # Move pendentes para failed
            failed_markets.extend(pending_markets)
            pending_markets = []
        
        return all_offers, completed_markets, failed_markets, pending_markets
    
    async def _search_market_with_timeout(
        self,
        market_id: str,
        query: str,
        cep: Optional[str],
        max_pages: int,
        timeout: float = 8.0,
    ) -> Tuple[str, List[PriceOffer], float, bool]:
        """
        Busca em mercado com timeout individual.
        
        Returns:
            Tupla (market_id, offers, latency_seconds, success)
        """
        start = datetime.now()
        
        try:
            async with asyncio.timeout(timeout):
                result = await self.scraper_manager.search_single(
                    market_id=market_id,
                    query=query,
                    cep=cep,
                    max_pages=max_pages,
                )
                
                latency = (datetime.now() - start).total_seconds()
                
                if result.products:
                    offers = self.pipeline.process_batch(
                        result.products,
                        apply_ranking=False,
                        search_query=query,
                    )
                    return market_id, offers, latency, True
                
                return market_id, [], latency, True
                    
        except asyncio.TimeoutError:
            self.logger.debug(f"Timeout em {market_id}")
            latency = (datetime.now() - start).total_seconds()
            return market_id, [], latency, False
        except Exception as e:
            self.logger.debug(f"Erro em {market_id}: {e}")
            latency = (datetime.now() - start).total_seconds()
            return market_id, [], latency, False
    
    def _process_results(
        self,
        offers: list[PriceOffer],
        query: str,
    ) -> list[dict]:
        """Processa e rankeia ofertas."""
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
                "is_promotional": getattr(offer, 'is_promotional', False),
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
    
    async def get_cache_stats(self) -> dict:
        """Retorna estatísticas do cache."""
        try:
            cache = await self._get_cache()
            return cache.get_stats()
        except RuntimeError:
            return {"error": "Cache não inicializado"}
    
    async def get_rate_limiter_stats(self) -> dict:
        """Retorna estatísticas do rate limiter."""
        try:
            rate_limiter = await self._get_rate_limiter()
            return await rate_limiter.get_stats()
        except Exception as e:
            return {"error": str(e)}


# Instância global para uso simplificado
_search_service: Optional[SearchService] = None


async def get_search_service() -> SearchService:
    """Retorna instância do serviço de busca."""
    global _search_service
    if _search_service is None:
        _search_service = SearchService()
    return _search_service


async def reset_search_service() -> None:
    """Reseta a instância global do serviço de busca."""
    global _search_service
    _search_service = None
