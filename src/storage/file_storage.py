"""
Storage em arquivos (CSV e Parquet).
Ideal para exportação e análise com pandas.
"""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

from src.core.models import PriceOffer, SearchResult, CollectionMetadata
from src.core.types import Availability, NormalizationStatus, Unit
from src.storage.base import BaseStorage, StorageType


class CSVStorage(BaseStorage):
    """
    Storage usando arquivos CSV.
    Fácil de visualizar e importar em outras ferramentas.
    """
    
    def __init__(self, base_path: Path):
        """Inicializa o storage CSV."""
        super().__init__(base_path)
        self.offers_dir = self.base_path / "csv" / "offers"
        self.offers_dir.mkdir(parents=True, exist_ok=True)
    
    @property
    def storage_type(self) -> StorageType:
        return StorageType.CSV
    
    async def save_offers(
        self,
        offers: list[PriceOffer],
        metadata: Optional[CollectionMetadata] = None,
    ) -> str:
        """
        Salva ofertas em arquivo CSV.
        
        Args:
            offers: Lista de ofertas
            metadata: Metadados da coleta
            
        Returns:
            Path do arquivo salvo
        """
        if not offers:
            self.logger.warning("Nenhuma oferta para salvar")
            return ""
        
        # Converte para DataFrame
        df = self._offers_to_dataframe(offers)
        
        # Gera nome do arquivo
        filename = self._generate_filename("offers", "csv")
        filepath = self.offers_dir / filename
        
        # Salva CSV
        df.to_csv(filepath, index=False, encoding="utf-8-sig")
        
        # Salva metadados se fornecidos
        if metadata:
            meta_filename = filename.replace("offers_", "metadata_").replace(".csv", ".json")
            meta_filepath = self.offers_dir / meta_filename
            
            import json
            with open(meta_filepath, "w", encoding="utf-8") as f:
                json.dump(metadata.model_dump(mode="json"), f, indent=2, default=str)
        
        self.logger.info(
            "Ofertas salvas em CSV",
            count=len(offers),
            filepath=str(filepath),
        )
        
        return str(filepath)
    
    async def load_offers(
        self,
        search_query: Optional[str] = None,
        market_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> list[PriceOffer]:
        """
        Carrega ofertas de arquivos CSV.
        """
        all_offers = []
        
        # Lista todos os CSVs
        csv_files = sorted(
            self.offers_dir.glob("offers_*.csv"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        
        for csv_file in csv_files:
            try:
                df = pd.read_csv(csv_file, encoding="utf-8-sig")
                
                # Aplica filtros
                if search_query:
                    df = df[df["search_query"].str.contains(search_query, case=False, na=False)]
                
                if market_id:
                    df = df[df["market_id"] == market_id]
                
                if start_date:
                    df["collected_at"] = pd.to_datetime(df["collected_at"])
                    df = df[df["collected_at"] >= start_date]
                
                if end_date:
                    df["collected_at"] = pd.to_datetime(df["collected_at"])
                    df = df[df["collected_at"] <= end_date]
                
                # Converte para ofertas
                offers = self._dataframe_to_offers(df)
                all_offers.extend(offers)
                
                # Verifica limite
                if limit and len(all_offers) >= limit:
                    all_offers = all_offers[:limit]
                    break
                    
            except Exception as e:
                self.logger.warning(
                    "Erro ao ler CSV",
                    filepath=str(csv_file),
                    error=str(e),
                )
                continue
        
        return all_offers
    
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
        """Retorna estatísticas básicas."""
        cutoff_date = datetime.now() - timedelta(days=days)
        offers = await self.load_offers(
            market_id=market_id,
            start_date=cutoff_date,
        )
        
        return {
            "total_offers": len(offers),
            "normalized_offers": sum(1 for o in offers if o.is_comparable),
            "markets": list(set(o.market_id for o in offers)),
        }
    
    def _offers_to_dataframe(self, offers: list[PriceOffer]) -> pd.DataFrame:
        """Converte lista de ofertas para DataFrame."""
        records = []
        
        for offer in offers:
            records.append({
                "id": str(offer.id),
                "market_id": offer.market_id,
                "market_name": offer.market_name,
                "title": offer.title,
                "url": offer.url,
                "image_url": offer.image_url,
                "price": float(offer.price),
                "quantity_value": offer.quantity_value,
                "quantity_unit": offer.quantity_unit.value if offer.quantity_unit else None,
                "normalized_price": float(offer.normalized_price) if offer.normalized_price else None,
                "normalized_unit": offer.normalized_unit.value if offer.normalized_unit else None,
                "price_display": offer.price_display,
                "availability": offer.availability.value,
                "normalization_status": offer.normalization_status.value,
                "search_query": offer.search_query,
                "cep": offer.cep,
                "collected_at": offer.collected_at.isoformat(),
            })
        
        return pd.DataFrame(records)
    
    def _dataframe_to_offers(self, df: pd.DataFrame) -> list[PriceOffer]:
        """Converte DataFrame para lista de ofertas."""
        from decimal import Decimal
        from uuid import UUID
        
        offers = []
        
        for _, row in df.iterrows():
            try:
                offer = PriceOffer(
                    id=UUID(row["id"]) if pd.notna(row.get("id")) else None,
                    market_id=row["market_id"],
                    market_name=row["market_name"],
                    title=row["title"],
                    url=row["url"],
                    image_url=row.get("image_url") if pd.notna(row.get("image_url")) else None,
                    price=Decimal(str(row["price"])),
                    quantity_value=row.get("quantity_value") if pd.notna(row.get("quantity_value")) else None,
                    quantity_unit=Unit(row["quantity_unit"]) if pd.notna(row.get("quantity_unit")) else None,
                    normalized_price=Decimal(str(row["normalized_price"])) if pd.notna(row.get("normalized_price")) else None,
                    normalized_unit=Unit(row["normalized_unit"]) if pd.notna(row.get("normalized_unit")) else None,
                    price_display=row["price_display"],
                    availability=Availability(row["availability"]),
                    normalization_status=NormalizationStatus(row["normalization_status"]),
                    search_query=row["search_query"],
                    cep=row.get("cep") if pd.notna(row.get("cep")) else None,
                    collected_at=datetime.fromisoformat(str(row["collected_at"])),
                )
                offers.append(offer)
            except Exception as e:
                self.logger.debug(
                    "Erro ao converter row",
                    error=str(e),
                )
                continue
        
        return offers


class ParquetStorage(BaseStorage):
    """
    Storage usando arquivos Parquet.
    Compressão eficiente e ideal para grandes volumes de dados.
    """
    
    def __init__(self, base_path: Path):
        """Inicializa o storage Parquet."""
        super().__init__(base_path)
        self.offers_dir = self.base_path / "parquet" / "offers"
        self.offers_dir.mkdir(parents=True, exist_ok=True)
    
    @property
    def storage_type(self) -> StorageType:
        return StorageType.PARQUET
    
    async def save_offers(
        self,
        offers: list[PriceOffer],
        metadata: Optional[CollectionMetadata] = None,
    ) -> str:
        """
        Salva ofertas em arquivo Parquet.
        
        Args:
            offers: Lista de ofertas
            metadata: Metadados da coleta
            
        Returns:
            Path do arquivo salvo
        """
        if not offers:
            self.logger.warning("Nenhuma oferta para salvar")
            return ""
        
        # Converte para DataFrame
        df = self._offers_to_dataframe(offers)
        
        # Gera nome do arquivo
        filename = self._generate_filename("offers", "parquet")
        filepath = self.offers_dir / filename
        
        # Salva Parquet com compressão
        df.to_parquet(
            filepath,
            engine="pyarrow",
            compression="snappy",
            index=False,
        )
        
        # Salva metadados
        if metadata:
            meta_filename = filename.replace("offers_", "metadata_").replace(".parquet", ".json")
            meta_filepath = self.offers_dir / meta_filename
            
            import json
            with open(meta_filepath, "w", encoding="utf-8") as f:
                json.dump(metadata.model_dump(mode="json"), f, indent=2, default=str)
        
        self.logger.info(
            "Ofertas salvas em Parquet",
            count=len(offers),
            filepath=str(filepath),
        )
        
        return str(filepath)
    
    async def load_offers(
        self,
        search_query: Optional[str] = None,
        market_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> list[PriceOffer]:
        """
        Carrega ofertas de arquivos Parquet.
        """
        all_offers = []
        
        # Lista todos os Parquets
        parquet_files = sorted(
            self.offers_dir.glob("offers_*.parquet"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        
        for parquet_file in parquet_files:
            try:
                df = pd.read_parquet(parquet_file)
                
                # Aplica filtros
                if search_query:
                    df = df[df["search_query"].str.contains(search_query, case=False, na=False)]
                
                if market_id:
                    df = df[df["market_id"] == market_id]
                
                if start_date:
                    df["collected_at"] = pd.to_datetime(df["collected_at"])
                    df = df[df["collected_at"] >= start_date]
                
                if end_date:
                    df["collected_at"] = pd.to_datetime(df["collected_at"])
                    df = df[df["collected_at"] <= end_date]
                
                # Converte para ofertas
                offers = self._dataframe_to_offers(df)
                all_offers.extend(offers)
                
                if limit and len(all_offers) >= limit:
                    all_offers = all_offers[:limit]
                    break
                    
            except Exception as e:
                self.logger.warning(
                    "Erro ao ler Parquet",
                    filepath=str(parquet_file),
                    error=str(e),
                )
                continue
        
        return all_offers
    
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
        """Retorna estatísticas básicas."""
        cutoff_date = datetime.now() - timedelta(days=days)
        offers = await self.load_offers(
            market_id=market_id,
            start_date=cutoff_date,
        )
        
        return {
            "total_offers": len(offers),
            "normalized_offers": sum(1 for o in offers if o.is_comparable),
            "markets": list(set(o.market_id for o in offers)),
        }
    
    def _offers_to_dataframe(self, offers: list[PriceOffer]) -> pd.DataFrame:
        """Converte lista de ofertas para DataFrame."""
        records = []
        
        for offer in offers:
            records.append({
                "id": str(offer.id),
                "market_id": offer.market_id,
                "market_name": offer.market_name,
                "title": offer.title,
                "url": offer.url,
                "image_url": offer.image_url,
                "price": float(offer.price),
                "quantity_value": offer.quantity_value,
                "quantity_unit": offer.quantity_unit.value if offer.quantity_unit else None,
                "normalized_price": float(offer.normalized_price) if offer.normalized_price else None,
                "normalized_unit": offer.normalized_unit.value if offer.normalized_unit else None,
                "price_display": offer.price_display,
                "availability": offer.availability.value,
                "normalization_status": offer.normalization_status.value,
                "search_query": offer.search_query,
                "cep": offer.cep,
                "collected_at": offer.collected_at,
            })
        
        return pd.DataFrame(records)
    
    def _dataframe_to_offers(self, df: pd.DataFrame) -> list[PriceOffer]:
        """Converte DataFrame para lista de ofertas."""
        from decimal import Decimal
        from uuid import UUID
        
        offers = []
        
        for _, row in df.iterrows():
            try:
                offer = PriceOffer(
                    id=UUID(row["id"]) if pd.notna(row.get("id")) else None,
                    market_id=row["market_id"],
                    market_name=row["market_name"],
                    title=row["title"],
                    url=row["url"],
                    image_url=row.get("image_url") if pd.notna(row.get("image_url")) else None,
                    price=Decimal(str(row["price"])),
                    quantity_value=row.get("quantity_value") if pd.notna(row.get("quantity_value")) else None,
                    quantity_unit=Unit(row["quantity_unit"]) if pd.notna(row.get("quantity_unit")) else None,
                    normalized_price=Decimal(str(row["normalized_price"])) if pd.notna(row.get("normalized_price")) else None,
                    normalized_unit=Unit(row["normalized_unit"]) if pd.notna(row.get("normalized_unit")) else None,
                    price_display=row["price_display"],
                    availability=Availability(row["availability"]),
                    normalization_status=NormalizationStatus(row["normalization_status"]),
                    search_query=row["search_query"],
                    cep=row.get("cep") if pd.notna(row.get("cep")) else None,
                    collected_at=pd.to_datetime(row["collected_at"]).to_pydatetime(),
                )
                offers.append(offer)
            except Exception as e:
                self.logger.debug(
                    "Erro ao converter row",
                    error=str(e),
                )
                continue
        
        return offers