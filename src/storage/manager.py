"""
Gerenciador de storage.
Unifica acesso a diferentes backends de persistência.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

from config.logging_config import LoggerMixin
from config.settings import get_settings
from src.core.models import PriceOffer, SearchResult, CollectionMetadata
from src.storage.base import BaseStorage, StorageType
from src.storage.sqlite_storage import SQLiteStorage
from src.storage.file_storage import CSVStorage, ParquetStorage


class StorageManager(LoggerMixin):
    """
    Gerenciador unificado de storage.
    Permite usar múltiplos backends simultaneamente.
    """
    
    def __init__(
        self,
        base_path: Optional[Path] = None,
        default_type: StorageType = StorageType.SQLITE,
    ):
        """
        Inicializa o gerenciador.
        
        Args:
            base_path: Diretório base para dados
            default_type: Tipo de storage padrão
        """
        settings = get_settings()
        self.base_path = base_path or settings.data_path
        self.default_type = default_type
        
        # Inicializa backends
        self._backends: dict[StorageType, BaseStorage] = {}
        self._init_backends()
    
    def _init_backends(self) -> None:
        """Inicializa todos os backends disponíveis."""
        self._backends[StorageType.SQLITE] = SQLiteStorage(self.base_path)
        self._backends[StorageType.CSV] = CSVStorage(self.base_path)
        self._backends[StorageType.PARQUET] = ParquetStorage(self.base_path)
        
        self.logger.debug(
            "Storage backends inicializados",
            backends=list(self._backends.keys()),
        )
    
    def get_backend(self, storage_type: Optional[StorageType] = None) -> BaseStorage:
        """
        Retorna backend específico.
        
        Args:
            storage_type: Tipo de storage (None = padrão)
            
        Returns:
            Instância do backend
        """
        st = storage_type or self.default_type
        return self._backends[st]
    
    async def save_offers(
        self,
        offers: list[PriceOffer],
        metadata: Optional[CollectionMetadata] = None,
        storage_type: Optional[StorageType] = None,
    ) -> str:
        """
        Salva ofertas no backend especificado.
        
        Args:
            offers: Lista de ofertas
            metadata: Metadados da coleta
            storage_type: Tipo de storage
            
        Returns:
            Identificador/path do arquivo salvo
        """
        backend = self.get_backend(storage_type)
        return await backend.save_offers(offers, metadata)
    
    async def save_to_all(
        self,
        offers: list[PriceOffer],
        metadata: Optional[CollectionMetadata] = None,
    ) -> dict[StorageType, str]:
        """
        Salva ofertas em todos os backends.
        
        Args:
            offers: Lista de ofertas
            metadata: Metadados da coleta
            
        Returns:
            Dicionário com paths por backend
        """
        results = {}
        
        for storage_type, backend in self._backends.items():
            try:
                path = await backend.save_offers(offers, metadata)
                results[storage_type] = path
            except Exception as e:
                self.logger.error(
                    "Erro ao salvar em backend",
                    backend=storage_type.value,
                    error=str(e),
                )
                results[storage_type] = f"ERROR: {e}"
        
        return results
    
    async def load_offers(
        self,
        search_query: Optional[str] = None,
        market_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: Optional[int] = None,
        storage_type: Optional[StorageType] = None,
    ) -> list[PriceOffer]:
        """
        Carrega ofertas do backend especificado.
        """
        backend = self.get_backend(storage_type)
        return await backend.load_offers(
            search_query=search_query,
            market_id=market_id,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )
    
    async def save_search_result(
        self,
        result: SearchResult,
        storage_type: Optional[StorageType] = None,
    ) -> str:
        """
        Salva resultado completo de busca.
        """
        backend = self.get_backend(storage_type)
        return await backend.save_search_result(result)
    
    async def get_statistics(
        self,
        market_id: Optional[str] = None,
        days: int = 30,
        storage_type: Optional[StorageType] = None,
    ) -> dict:
        """
        Retorna estatísticas de coleta.
        """
        backend = self.get_backend(storage_type)
        return await backend.get_statistics(market_id=market_id, days=days)
    
    async def export_to_csv(
        self,
        search_query: Optional[str] = None,
        market_id: Optional[str] = None,
        output_path: Optional[Path] = None,
    ) -> str:
        """
        Exporta dados do SQLite para CSV.
        
        Args:
            search_query: Filtrar por query
            market_id: Filtrar por mercado
            output_path: Caminho de saída
            
        Returns:
            Path do arquivo exportado
        """
        # Carrega do SQLite
        offers = await self.load_offers(
            search_query=search_query,
            market_id=market_id,
            storage_type=StorageType.SQLITE,
        )
        
        if not offers:
            self.logger.warning("Nenhuma oferta para exportar")
            return ""
        
        # Salva em CSV
        csv_backend = self.get_backend(StorageType.CSV)
        
        if output_path:
            # Usa caminho especificado
            import pandas as pd
            df = csv_backend._offers_to_dataframe(offers)
            df.to_csv(output_path, index=False, encoding="utf-8-sig")
            return str(output_path)
        
        return await csv_backend.save_offers(offers)
    
    async def export_to_parquet(
        self,
        search_query: Optional[str] = None,
        market_id: Optional[str] = None,
        output_path: Optional[Path] = None,
    ) -> str:
        """
        Exporta dados do SQLite para Parquet.
        
        Args:
            search_query: Filtrar por query
            market_id: Filtrar por mercado
            output_path: Caminho de saída
            
        Returns:
            Path do arquivo exportado
        """
        # Carrega do SQLite
        offers = await self.load_offers(
            search_query=search_query,
            market_id=market_id,
            storage_type=StorageType.SQLITE,
        )
        
        if not offers:
            self.logger.warning("Nenhuma oferta para exportar")
            return ""
        
        # Salva em Parquet
        parquet_backend = self.get_backend(StorageType.PARQUET)
        
        if output_path:
            import pandas as pd
            df = parquet_backend._offers_to_dataframe(offers)
            df.to_parquet(output_path, engine="pyarrow", compression="snappy", index=False)
            return str(output_path)
        
        return await parquet_backend.save_offers(offers)
