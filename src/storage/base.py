"""
Classe base abstrata para storage.
Define interface comum para todos os backends de persistência.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from config.logging_config import LoggerMixin
from src.core.models import PriceOffer, SearchResult, CollectionMetadata


class StorageType(str, Enum):
    """Tipos de storage disponíveis."""
    SQLITE = "sqlite"
    CSV = "csv"
    PARQUET = "parquet"


class BaseStorage(ABC, LoggerMixin):
    """
    Classe base abstrata para backends de storage.
    Define interface para persistência de ofertas e resultados.
    """
    
    def __init__(self, base_path: Path):
        """
        Inicializa o storage.
        
        Args:
            base_path: Diretório base para armazenamento
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
    
    @property
    @abstractmethod
    def storage_type(self) -> StorageType:
        """Retorna o tipo de storage."""
        pass
    
    @abstractmethod
    async def save_offers(
        self,
        offers: list[PriceOffer],
        metadata: Optional[CollectionMetadata] = None,
    ) -> str:
        """
        Salva lista de ofertas.
        
        Args:
            offers: Lista de ofertas para salvar
            metadata: Metadados da coleta (opcional)
            
        Returns:
            Identificador/path do arquivo salvo
        """
        pass
    
    @abstractmethod
    async def load_offers(
        self,
        search_query: Optional[str] = None,
        market_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> list[PriceOffer]:
        """
        Carrega ofertas com filtros opcionais.
        
        Args:
            search_query: Filtrar por termo de busca
            market_id: Filtrar por mercado
            start_date: Data inicial
            end_date: Data final
            limit: Limite de resultados
            
        Returns:
            Lista de ofertas
        """
        pass
    
    @abstractmethod
    async def save_search_result(
        self,
        result: SearchResult,
    ) -> str:
        """
        Salva resultado completo de busca.
        
        Args:
            result: Resultado da busca
            
        Returns:
            Identificador/path do arquivo salvo
        """
        pass
    
    @abstractmethod
    async def get_statistics(
        self,
        market_id: Optional[str] = None,
        days: int = 30,
    ) -> dict:
        """
        Retorna estatísticas de coleta.
        
        Args:
            market_id: Filtrar por mercado
            days: Período em dias
            
        Returns:
            Dicionário com estatísticas
        """
        pass
    
    def _generate_filename(
        self,
        prefix: str,
        extension: str,
        timestamp: Optional[datetime] = None,
    ) -> str:
        """
        Gera nome de arquivo com timestamp.
        
        Args:
            prefix: Prefixo do arquivo
            extension: Extensão do arquivo
            timestamp: Timestamp (default: agora)
            
        Returns:
            Nome do arquivo
        """
        ts = timestamp or datetime.now()
        ts_str = ts.strftime("%Y%m%d_%H%M%S")
        return f"{prefix}_{ts_str}.{extension}"