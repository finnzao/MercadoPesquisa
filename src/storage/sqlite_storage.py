"""
Storage SQLite para persistência estruturada.
Ideal para consultas complexas e histórico de preços.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from uuid import UUID

import aiosqlite

from src.core.models import PriceOffer, SearchResult, CollectionMetadata
from src.core.types import Availability, NormalizationStatus, Unit
from src.storage.base import BaseStorage, StorageType


class SQLiteStorage(BaseStorage):
    """
    Storage usando SQLite.
    Suporta queries complexas e é ideal para análise histórica.
    """
    
    def __init__(self, base_path: Path, db_name: str = "price_collector.db"):
        """
        Inicializa o storage SQLite.
        
        Args:
            base_path: Diretório base
            db_name: Nome do arquivo do banco
        """
        super().__init__(base_path)
        self.db_path = self.base_path / db_name
        self._initialized = False
    
    @property
    def storage_type(self) -> StorageType:
        return StorageType.SQLITE
    
    async def _ensure_initialized(self) -> None:
        """Garante que as tabelas existem."""
        if self._initialized:
            return
        
        async with aiosqlite.connect(self.db_path) as db:
            # Tabela de ofertas
            await db.execute("""
                CREATE TABLE IF NOT EXISTS offers (
                    id TEXT PRIMARY KEY,
                    market_id TEXT NOT NULL,
                    market_name TEXT NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    image_url TEXT,
                    price REAL NOT NULL,
                    quantity_value REAL,
                    quantity_unit TEXT,
                    normalized_price REAL,
                    normalized_unit TEXT,
                    price_display TEXT NOT NULL,
                    availability TEXT NOT NULL,
                    normalization_status TEXT NOT NULL,
                    search_query TEXT NOT NULL,
                    cep TEXT,
                    collected_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Tabela de metadados de coleta
            await db.execute("""
                CREATE TABLE IF NOT EXISTS collections (
                    id TEXT PRIMARY KEY,
                    search_query TEXT NOT NULL,
                    cep TEXT,
                    markets_requested TEXT NOT NULL,
                    started_at TIMESTAMP NOT NULL,
                    finished_at TIMESTAMP,
                    total_products INTEGER DEFAULT 0,
                    total_normalized INTEGER DEFAULT 0,
                    total_errors INTEGER DEFAULT 0,
                    results_json TEXT,
                    errors_json TEXT
                )
            """)
            
            # Índices para queries frequentes
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_offers_market 
                ON offers(market_id)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_offers_query 
                ON offers(search_query)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_offers_collected 
                ON offers(collected_at)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_offers_market_query 
                ON offers(market_id, search_query)
            """)
            
            await db.commit()
        
        self._initialized = True
        self.logger.debug("SQLite inicializado", db_path=str(self.db_path))
    
    async def save_offers(
        self,
        offers: list[PriceOffer],
        metadata: Optional[CollectionMetadata] = None,
    ) -> str:
        """
        Salva ofertas no SQLite.
        
        Args:
            offers: Lista de ofertas
            metadata: Metadados da coleta
            
        Returns:
            Path do banco de dados
        """
        await self._ensure_initialized()
        
        async with aiosqlite.connect(self.db_path) as db:
            # Salva metadados se fornecidos
            if metadata:
                await db.execute("""
                    INSERT OR REPLACE INTO collections 
                    (id, search_query, cep, markets_requested, started_at, 
                     finished_at, total_products, total_normalized, total_errors,
                     results_json, errors_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    str(metadata.collection_id),
                    metadata.search_query,
                    metadata.cep,
                    json.dumps(metadata.markets_requested),
                    metadata.started_at.isoformat(),
                    metadata.finished_at.isoformat() if metadata.finished_at else None,
                    metadata.total_products,
                    metadata.total_normalized,
                    metadata.total_errors,
                    json.dumps(metadata.results_per_market),
                    json.dumps(metadata.errors_per_market),
                ))
            
            # Salva ofertas
            for offer in offers:
                await db.execute("""
                    INSERT OR REPLACE INTO offers
                    (id, market_id, market_name, title, url, image_url, price,
                     quantity_value, quantity_unit, normalized_price, normalized_unit,
                     price_display, availability, normalization_status, search_query,
                     cep, collected_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    str(offer.id),
                    offer.market_id,
                    offer.market_name,
                    offer.title,
                    offer.url,
                    offer.image_url,
                    float(offer.price),
                    offer.quantity_value,
                    offer.quantity_unit.value if offer.quantity_unit else None,
                    float(offer.normalized_price) if offer.normalized_price else None,
                    offer.normalized_unit.value if offer.normalized_unit else None,
                    offer.price_display,
                    offer.availability.value,
                    offer.normalization_status.value,
                    offer.search_query,
                    offer.cep,
                    offer.collected_at.isoformat(),
                ))
            
            await db.commit()
        
        self.logger.info(
            "Ofertas salvas no SQLite",
            count=len(offers),
            db_path=str(self.db_path),
        )
        
        return str(self.db_path)
    
    async def load_offers(
        self,
        search_query: Optional[str] = None,
        market_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> list[PriceOffer]:
        """
        Carrega ofertas do SQLite com filtros.
        """
        await self._ensure_initialized()
        
        # Monta query dinamicamente
        query = "SELECT * FROM offers WHERE 1=1"
        params = []
        
        if search_query:
            query += " AND search_query LIKE ?"
            params.append(f"%{search_query}%")
        
        if market_id:
            query += " AND market_id = ?"
            params.append(market_id)
        
        if start_date:
            query += " AND collected_at >= ?"
            params.append(start_date.isoformat())
        
        if end_date:
            query += " AND collected_at <= ?"
            params.append(end_date.isoformat())
        
        query += " ORDER BY collected_at DESC"
        
        if limit:
            query += " LIMIT ?"
            params.append(limit)
        
        offers = []
        
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, params) as cursor:
                async for row in cursor:
                    offer = self._row_to_offer(dict(row))
                    offers.append(offer)
        
        self.logger.debug(
            "Ofertas carregadas",
            count=len(offers),
            filters={
                "query": search_query,
                "market": market_id,
            },
        )
        
        return offers
    
    def _row_to_offer(self, row: dict) -> PriceOffer:
        """Converte row do SQLite para PriceOffer."""
        from decimal import Decimal
        
        return PriceOffer(
            id=UUID(row["id"]),
            market_id=row["market_id"],
            market_name=row["market_name"],
            title=row["title"],
            url=row["url"],
            image_url=row["image_url"],
            price=Decimal(str(row["price"])),
            quantity_value=row["quantity_value"],
            quantity_unit=Unit(row["quantity_unit"]) if row["quantity_unit"] else None,
            normalized_price=Decimal(str(row["normalized_price"])) if row["normalized_price"] else None,
            normalized_unit=Unit(row["normalized_unit"]) if row["normalized_unit"] else None,
            price_display=row["price_display"],
            availability=Availability(row["availability"]),
            normalization_status=NormalizationStatus(row["normalization_status"]),
            search_query=row["search_query"],
            cep=row["cep"],
            collected_at=datetime.fromisoformat(row["collected_at"]),
        )
    
    async def save_search_result(
        self,
        result: SearchResult,
    ) -> str:
        """Salva resultado completo de busca."""
        return await self.save_offers(result.offers, result.metadata)
    
    async def get_statistics(
        self,
        market_id: Optional[str] = None,
        days: int = 30,
    ) -> dict:
        """
        Retorna estatísticas de coleta.
        """
        await self._ensure_initialized()
        
        cutoff_date = datetime.now() - timedelta(days=days)
        
        async with aiosqlite.connect(self.db_path) as db:
            # Total de ofertas
            query = """
                SELECT 
                    COUNT(*) as total,
                    COUNT(CASE WHEN normalized_price IS NOT NULL THEN 1 END) as normalized,
                    COUNT(DISTINCT search_query) as unique_queries,
                    COUNT(DISTINCT market_id) as markets
                FROM offers
                WHERE collected_at >= ?
            """
            params = [cutoff_date.isoformat()]
            
            if market_id:
                query = query.replace("WHERE", "WHERE market_id = ? AND")
                params.insert(0, market_id)
            
            async with db.execute(query, params) as cursor:
                row = await cursor.fetchone()
                stats = {
                    "total_offers": row[0],
                    "normalized_offers": row[1],
                    "unique_queries": row[2],
                    "markets_count": row[3],
                }
            
            # Ofertas por mercado
            query = """
                SELECT market_id, COUNT(*) as count
                FROM offers
                WHERE collected_at >= ?
                GROUP BY market_id
            """
            
            async with db.execute(query, [cutoff_date.isoformat()]) as cursor:
                stats["by_market"] = {
                    row[0]: row[1] async for row in cursor
                }
            
            # Coletas recentes
            query = """
                SELECT COUNT(*) as collections
                FROM collections
                WHERE started_at >= ?
            """
            
            async with db.execute(query, [cutoff_date.isoformat()]) as cursor:
                row = await cursor.fetchone()
                stats["total_collections"] = row[0]
        
        return stats
    
    async def get_price_history(
        self,
        search_query: str,
        market_id: Optional[str] = None,
        days: int = 30,
    ) -> list[dict]:
        """
        Retorna histórico de preços para um produto.
        
        Args:
            search_query: Termo de busca
            market_id: Filtrar por mercado
            days: Período em dias
            
        Returns:
            Lista com histórico de preços
        """
        await self._ensure_initialized()
        
        cutoff_date = datetime.now() - timedelta(days=days)
        
        query = """
            SELECT 
                DATE(collected_at) as date,
                market_id,
                AVG(normalized_price) as avg_price,
                MIN(normalized_price) as min_price,
                MAX(normalized_price) as max_price,
                COUNT(*) as samples
            FROM offers
            WHERE search_query LIKE ?
              AND collected_at >= ?
              AND normalized_price IS NOT NULL
        """
        params = [f"%{search_query}%", cutoff_date.isoformat()]
        
        if market_id:
            query += " AND market_id = ?"
            params.append(market_id)
        
        query += " GROUP BY DATE(collected_at), market_id ORDER BY date"
        
        history = []
        
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(query, params) as cursor:
                async for row in cursor:
                    history.append({
                        "date": row[0],
                        "market_id": row[1],
                        "avg_price": row[2],
                        "min_price": row[3],
                        "max_price": row[4],
                        "samples": row[5],
                    })
        
        return history