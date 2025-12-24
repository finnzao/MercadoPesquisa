"""
PriceCollector: Orquestrador principal do sistema.
Coordena scrapers, pipeline e storage para coleta completa.
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional

from config.logging_config import LoggerMixin, setup_logging, get_logger
from config.markets import MARKETS_CONFIG, get_active_markets
from config.settings import get_settings
from src.core.models import (
    PriceOffer,
    SearchResult,
    CollectionMetadata,
    RawProduct,
)
from src.core.types import CollectionStatus, MarketID
from src.pipeline import ProcessingPipeline
from src.scrapers import ScraperManager
from src.storage import StorageManager, StorageType


class PriceCollector(LoggerMixin):
    """
    Orquestrador principal do sistema de coleta de preços.
    
    Responsabilidades:
    - Coordenar busca em múltiplos mercados
    - Processar produtos através do pipeline
    - Persistir resultados
    - Gerar relatórios e comparações
    """
    
    def __init__(
        self,
        storage_type: StorageType = StorageType.SQLITE,
        data_path: Optional[Path] = None,
    ):
        """
        Inicializa o coletor.
        
        Args:
            storage_type: Tipo de storage padrão
            data_path: Diretório para dados (None = config)
        """
        self.settings = get_settings()
        
        # Inicializa componentes
        self.scraper_manager = ScraperManager()
        self.pipeline = ProcessingPipeline()
        self.storage = StorageManager(
            base_path=data_path or self.settings.data_path,
            default_type=storage_type,
        )
        
        # Configura logging
        setup_logging(
            level=self.settings.log_level,
            log_path=self.settings.log_path,
        )
        
        self.logger.info(
            "PriceCollector inicializado",
            storage_type=storage_type.value,
            data_path=str(data_path or self.settings.data_path),
        )
    
    async def search(
        self,
        query: str,
        cep: Optional[str] = None,
        markets: Optional[list[str]] = None,
        max_pages: int = 1,
        save_results: bool = True,
    ) -> SearchResult:
        """
        Executa busca completa em mercados.
        
        Args:
            query: Termo de busca (ex: "arroz tipo 1 5kg")
            cep: CEP opcional para localização
            markets: Lista de mercados (None = todos ativos)
            max_pages: Máximo de páginas por mercado
            save_results: Se deve salvar resultados
            
        Returns:
            SearchResult com ofertas processadas
        """
        self.logger.info(
            "Iniciando busca",
            query=query,
            cep=cep,
            markets=markets,
        )
        
        # Valida CEP se fornecido
        if cep:
            cep = self._normalize_cep(cep)
        
        # Define mercados alvo
        target_markets = markets or [m.id for m in get_active_markets()]
        
        # Cria metadados
        metadata = CollectionMetadata(
            search_query=query,
            cep=cep,
            markets_requested=target_markets,
        )
        
        try:
            # Etapa 1: Coleta de dados brutos
            raw_products, scraper_metadata = await self.scraper_manager.search_all(
                query=query,
                cep=cep,
                max_pages=max_pages,
                markets=target_markets,
            )
            
            # Atualiza metadados
            metadata.results_per_market = scraper_metadata.results_per_market
            metadata.errors_per_market = scraper_metadata.errors_per_market
            
            self.logger.info(
                "Coleta concluída",
                raw_products=len(raw_products),
            )
            
            # Etapa 2: Processamento pelo pipeline
            offers = self.pipeline.process_batch(raw_products)
            
            self.logger.info(
                "Processamento concluído",
                total_offers=len(offers),
                comparable=sum(1 for o in offers if o.is_comparable),
            )
            
            # Atualiza metadados finais
            metadata.total_products = len(offers)
            metadata.total_normalized = sum(1 for o in offers if o.is_comparable)
            metadata.total_errors = len(metadata.errors_per_market)
            metadata.mark_finished()
            
            # Cria resultado
            result = SearchResult(
                metadata=metadata,
                offers=offers,
            )
            
            # Etapa 3: Persistência (se habilitada)
            if save_results and offers:
                await self._save_results(result)
            
            return result
            
        except Exception as e:
            self.logger.error(
                "Erro na busca",
                error=str(e),
                exc_info=True,
            )
            metadata.mark_finished()
            return SearchResult(metadata=metadata, offers=[])
    
    async def search_single_market(
        self,
        query: str,
        market_id: str,
        cep: Optional[str] = None,
        max_pages: int = 1,
    ) -> list[PriceOffer]:
        """
        Busca em um único mercado.
        
        Args:
            query: Termo de busca
            market_id: ID do mercado
            cep: CEP opcional
            max_pages: Máximo de páginas
            
        Returns:
            Lista de ofertas processadas
        """
        result = await self.search(
            query=query,
            cep=cep,
            markets=[market_id],
            max_pages=max_pages,
            save_results=False,
        )
        return result.offers
    
    async def compare_prices(
        self,
        query: str,
        cep: Optional[str] = None,
    ) -> dict:
        """
        Compara preços entre mercados.
        
        Args:
            query: Termo de busca
            cep: CEP opcional
            
        Returns:
            Dicionário com comparação detalhada
        """
        result = await self.search(query=query, cep=cep)
        
        if not result.offers:
            return {
                "query": query,
                "total_offers": 0,
                "comparison": [],
                "best_offer": None,
                "savings": None,
            }
        
        # Ordena por preço normalizado
        sorted_offers = self.pipeline.calculator.compare_offers(result.offers)
        
        # Melhor oferta
        best = self.pipeline.calculator.find_best_offer(result.offers)
        
        # Calcula economia
        savings = []
        if best:
            for offer in sorted_offers[1:]:  # Pula a melhor
                if offer.is_comparable:
                    saving = self.pipeline.calculator.calculate_savings(best, offer)
                    if saving:
                        savings.append(saving)
        
        # Agrupa por mercado
        by_market = {}
        for offer in result.offers:
            if offer.market_id not in by_market:
                by_market[offer.market_id] = {
                    "market_name": offer.market_name,
                    "offers_count": 0,
                    "min_price": None,
                    "min_normalized": None,
                }
            
            market_data = by_market[offer.market_id]
            market_data["offers_count"] += 1
            
            if offer.price:
                if market_data["min_price"] is None or offer.price < market_data["min_price"]:
                    market_data["min_price"] = float(offer.price)
            
            if offer.normalized_price:
                if market_data["min_normalized"] is None or offer.normalized_price < market_data["min_normalized"]:
                    market_data["min_normalized"] = float(offer.normalized_price)
        
        return {
            "query": query,
            "cep": cep,
            "collected_at": result.metadata.started_at.isoformat(),
            "total_offers": len(result.offers),
            "comparable_offers": result.comparable_offers,
            "by_market": by_market,
            "best_offer": {
                "market": best.market_name,
                "title": best.title,
                "price": float(best.price),
                "normalized_price": float(best.normalized_price) if best.normalized_price else None,
                "price_display": best.price_display,
                "url": best.url,
            } if best else None,
            "potential_savings": savings[:5],  # Top 5 economias
            "all_offers": [
                {
                    "market": o.market_name,
                    "title": o.title,
                    "price": float(o.price),
                    "normalized_price": float(o.normalized_price) if o.normalized_price else None,
                    "price_display": o.price_display,
                    "is_comparable": o.is_comparable,
                }
                for o in sorted_offers
            ],
        }
    
    async def get_price_history(
        self,
        query: str,
        market_id: Optional[str] = None,
        days: int = 30,
    ) -> list[dict]:
        """
        Obtém histórico de preços.
        
        Args:
            query: Termo de busca
            market_id: Filtrar por mercado
            days: Período em dias
            
        Returns:
            Lista com histórico de preços
        """
        sqlite_storage = self.storage.get_backend(StorageType.SQLITE)
        return await sqlite_storage.get_price_history(
            search_query=query,
            market_id=market_id,
            days=days,
        )
    
    async def export_results(
        self,
        output_path: Path,
        format: str = "csv",
        query: Optional[str] = None,
        market_id: Optional[str] = None,
    ) -> str:
        """
        Exporta resultados para arquivo.
        
        Args:
            output_path: Caminho de saída
            format: Formato (csv ou parquet)
            query: Filtrar por query
            market_id: Filtrar por mercado
            
        Returns:
            Path do arquivo exportado
        """
        if format.lower() == "csv":
            return await self.storage.export_to_csv(
                search_query=query,
                market_id=market_id,
                output_path=output_path,
            )
        elif format.lower() == "parquet":
            return await self.storage.export_to_parquet(
                search_query=query,
                market_id=market_id,
                output_path=output_path,
            )
        else:
            raise ValueError(f"Formato não suportado: {format}")
    
    async def get_statistics(
        self,
        market_id: Optional[str] = None,
        days: int = 30,
    ) -> dict:
        """
        Obtém estatísticas de coleta.
        
        Args:
            market_id: Filtrar por mercado
            days: Período em dias
            
        Returns:
            Dicionário com estatísticas
        """
        return await self.storage.get_statistics(
            market_id=market_id,
            days=days,
        )
    
    def get_available_markets(self) -> list[dict]:
        """
        Lista mercados disponíveis.
        
        Returns:
            Lista com informações dos mercados
        """
        markets = []
        for market in get_active_markets():
            markets.append({
                "id": market.id,
                "name": market.display_name,
                "status": market.status.value,
                "method": market.method.value,
            })
        return markets
    
    async def _save_results(self, result: SearchResult) -> None:
        """Salva resultados no storage."""
        try:
            # Salva no storage padrão
            path = await self.storage.save_search_result(result)
            self.logger.info("Resultados salvos", path=path)
            
        except Exception as e:
            self.logger.error(
                "Erro ao salvar resultados",
                error=str(e),
            )
    
    def _normalize_cep(self, cep: str) -> str:
        """
        Normaliza CEP removendo caracteres não numéricos.
        
        Args:
            cep: CEP em qualquer formato
            
        Returns:
            CEP com apenas números (8 dígitos)
        """
        # Remove caracteres não numéricos
        cep_clean = "".join(c for c in cep if c.isdigit())
        
        if len(cep_clean) != 8:
            raise ValueError(f"CEP inválido: {cep}. Deve ter 8 dígitos.")
        
        return cep_clean


# Função de conveniência para uso rápido
async def quick_search(
    query: str,
    cep: Optional[str] = None,
    markets: Optional[list[str]] = None,
) -> SearchResult:
    """
    Função de conveniência para busca rápida.
    
    Args:
        query: Termo de busca
        cep: CEP opcional
        markets: Lista de mercados
        
    Returns:
        SearchResult com ofertas
    """
    collector = PriceCollector()
    return await collector.search(query=query, cep=cep, markets=markets)


async def quick_compare(
    query: str,
    cep: Optional[str] = None,
) -> dict:
    """
    Função de conveniência para comparação rápida.
    
    Args:
        query: Termo de busca
        cep: CEP opcional
        
    Returns:
        Dicionário com comparação
    """
    collector = PriceCollector()
    return await collector.compare_prices(query=query, cep=cep)