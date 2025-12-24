"""
Testes de integração para o Storage.
"""

from datetime import datetime

import pytest
import pytest_asyncio

from src.storage import StorageManager, SQLiteStorage, CSVStorage, StorageType
from src.core.models import PriceOffer, CollectionMetadata


class TestSQLiteStorage:
    """Testes de integração para SQLiteStorage."""
    
    @pytest_asyncio.fixture
    async def storage(self, temp_data_dir) -> SQLiteStorage:
        """Instância do storage SQLite."""
        return SQLiteStorage(temp_data_dir)
    
    @pytest.mark.asyncio
    async def test_save_and_load_offers(self, storage, price_offer_arroz, price_offer_leite):
        """Testa salvar e carregar ofertas."""
        offers = [price_offer_arroz, price_offer_leite]
        
        # Salva
        path = await storage.save_offers(offers)
        assert path is not None
        
        # Carrega
        loaded = await storage.load_offers()
        assert len(loaded) == 2
    
    @pytest.mark.asyncio
    async def test_load_with_filters(self, storage, price_offers_for_comparison):
        """Testa carregamento com filtros."""
        await storage.save_offers(price_offers_for_comparison)
        
        # Filtra por mercado
        carrefour_offers = await storage.load_offers(market_id="carrefour")
        assert all(o.market_id == "carrefour" for o in carrefour_offers)
        
        # Filtra por query
        arroz_offers = await storage.load_offers(search_query="arroz")
        assert len(arroz_offers) > 0
    
    @pytest.mark.asyncio
    async def test_get_statistics(self, storage, price_offers_for_comparison):
        """Testa obtenção de estatísticas."""
        await storage.save_offers(price_offers_for_comparison)
        
        stats = await storage.get_statistics()
        
        assert stats["total_offers"] > 0
        assert "by_market" in stats


class TestCSVStorage:
    """Testes de integração para CSVStorage."""
    
    @pytest_asyncio.fixture
    async def storage(self, temp_data_dir) -> CSVStorage:
        """Instância do storage CSV."""
        return CSVStorage(temp_data_dir)
    
    @pytest.mark.asyncio
    async def test_save_and_load_offers(self, storage, price_offer_arroz):
        """Testa salvar e carregar ofertas em CSV."""
        offers = [price_offer_arroz]
        
        # Salva
        path = await storage.save_offers(offers)
        assert path.endswith(".csv")
        
        # Carrega
        loaded = await storage.load_offers()
        assert len(loaded) == 1
        assert loaded[0].title == price_offer_arroz.title


class TestStorageManager:
    """Testes de integração para StorageManager."""
    
    @pytest.fixture
    def manager(self, temp_data_dir) -> StorageManager:
        """Instância do storage manager."""
        return StorageManager(base_path=temp_data_dir)
    
    @pytest.mark.asyncio
    async def test_save_to_all_backends(self, manager, price_offers_for_comparison):
        """Testa salvamento em todos os backends."""
        results = await manager.save_to_all(price_offers_for_comparison)
        
        assert StorageType.SQLITE in results
        assert StorageType.CSV in results
        assert StorageType.PARQUET in results
    
    @pytest.mark.asyncio
    async def test_export_sqlite_to_csv(self, manager, price_offers_for_comparison, temp_data_dir):
        """Testa exportação de SQLite para CSV."""
        # Salva no SQLite
        await manager.save_offers(
            price_offers_for_comparison,
            storage_type=StorageType.SQLITE,
        )
        
        # Exporta para CSV
        output_path = temp_data_dir / "export.csv"
        path = await manager.export_to_csv(output_path=output_path)
        
        assert path == str(output_path)