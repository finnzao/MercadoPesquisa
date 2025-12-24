"""
Gerenciador de scrapers.
Orquestra execução paralela e agrega resultados.
"""

import asyncio
from datetime import datetime
from typing import Optional

from config.logging_config import LoggerMixin
from config.markets import MARKETS_CONFIG, MarketConfig, MarketStatus
from src.core.models import CollectionMetadata, RawProduct
from src.core.types import CollectionStatus, MarketID
from src.scrapers.base import BaseScraper, ScraperResult


class ScraperManager(LoggerMixin):
    """
    Gerenciador central de scrapers.
    Coordena execução e coleta de múltiplos mercados.
    """
    
    def __init__(self):
        """Inicializa o gerenciador."""
        from src.scrapers import SCRAPER_REGISTRY
        self._registry = SCRAPER_REGISTRY
        self._scrapers: dict[str, BaseScraper] = {}
    
    def _get_scraper(self, market_id: str) -> BaseScraper:
        """
        Obtém ou cria instância do scraper.
        
        Args:
            market_id: ID do mercado
            
        Returns:
            Instância do scraper
        """
        if market_id not in self._scrapers:
            if market_id not in self._registry:
                raise ValueError(f"Scraper não registrado: {market_id}")
            
            config = MARKETS_CONFIG.get(market_id)
            if not config:
                raise ValueError(f"Configuração não encontrada: {market_id}")
            
            scraper_class = self._registry[market_id]
            self._scrapers[market_id] = scraper_class(config)
        
        return self._scrapers[market_id]
    
    def get_available_markets(self) -> list[str]:
        """Retorna lista de mercados disponíveis."""
        return [
            market_id
            for market_id, config in MARKETS_CONFIG.items()
            if config.status in (MarketStatus.ACTIVE, MarketStatus.DEVELOPMENT)
        ]
    
    async def search_single(
        self,
        market_id: str,
        query: str,
        cep: Optional[str] = None,
        max_pages: int = 1,
    ) -> ScraperResult:
        """
        Busca em um único mercado.
        
        Args:
            market_id: ID do mercado
            query: Termo de busca
            cep: CEP opcional
            max_pages: Máximo de páginas
            
        Returns:
            Resultado da busca
        """
        scraper = self._get_scraper(market_id)
        return await scraper.search(query, cep, max_pages)
    
    async def search_all(
        self,
        query: str,
        cep: Optional[str] = None,
        max_pages: int = 1,
        markets: Optional[list[str]] = None,
    ) -> tuple[list[RawProduct], CollectionMetadata]:
        """
        Busca em todos os mercados em paralelo.
        
        Args:
            query: Termo de busca
            cep: CEP opcional
            max_pages: Máximo de páginas por mercado
            markets: Lista de mercados (None = todos)
            
        Returns:
            Tupla (produtos, metadados)
        """
        # Define mercados a buscar
        if markets:
            target_markets = [m for m in markets if m in self.get_available_markets()]
        else:
            target_markets = self.get_available_markets()
        
        if not target_markets:
            raise ValueError("Nenhum mercado disponível para busca")
        
        self.logger.info(
            "Iniciando busca em múltiplos mercados",
            query=query,
            markets=target_markets,
            cep=cep,
        )
        
        # Cria metadados
        metadata = CollectionMetadata(
            search_query=query,
            cep=cep,
            markets_requested=target_markets,
        )
        
        # Executa buscas em paralelo
        tasks = [
            self.search_single(market_id, query, cep, max_pages)
            for market_id in target_markets
        ]
        
        results: list[ScraperResult] = await asyncio.gather(
            *tasks,
            return_exceptions=True,
        )
        
        # Processa resultados
        all_products = []
        
        for market_id, result in zip(target_markets, results):
            if isinstance(result, Exception):
                self.logger.error(
                    "Erro em mercado",
                    market=market_id,
                    error=str(result),
                )
                metadata.errors_per_market[market_id] = str(result)
                metadata.total_errors += 1
            else:
                metadata.results_per_market[market_id] = result.products_count
                
                if result.status == CollectionStatus.SUCCESS:
                    all_products.extend(result.products)
                elif result.error_message:
                    metadata.errors_per_market[market_id] = result.error_message
        
        metadata.total_products = len(all_products)
        metadata.mark_finished()
        
        self.logger.info(
            "Busca finalizada",
            total_products=len(all_products),
            markets_success=len(metadata.results_per_market),
            markets_error=len(metadata.errors_per_market),
            duration=f"{metadata.duration_seconds:.2f}s" if metadata.duration_seconds else "N/A",
        )
        
        return all_products, metadata
    
    async def health_check(self) -> dict[str, dict]:
        """
        Verifica saúde de todos os scrapers.
        
        Returns:
            Dicionário com status de cada mercado
        """
        results = {}
        
        for market_id in self.get_available_markets():
            try:
                scraper = self._get_scraper(market_id)
                # Tenta uma busca simples
                result = await scraper.search("teste", max_pages=1)
                
                results[market_id] = {
                    "status": "healthy" if result.status == CollectionStatus.SUCCESS else "degraded",
                    "response_time": result.duration_seconds,
                    "last_error": result.error_message,
                }
            except Exception as e:
                results[market_id] = {
                    "status": "unhealthy",
                    "response_time": None,
                    "last_error": str(e),
                }
        
        return results