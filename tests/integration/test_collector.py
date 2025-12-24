"""
Testes de integração para o PriceCollector.
"""

import pytest
import pytest_asyncio

from src.collector import PriceCollector
from src.storage import StorageType


class TestPriceCollector:
    """Testes de integração para PriceCollector."""
    
    @pytest.fixture
    def collector(self, temp_data_dir) -> PriceCollector:
        """Instância do collector com diretório temporário."""
        return PriceCollector(
            storage_type=StorageType.SQLITE,
            data_path=temp_data_dir,
        )
    
    def test_get_available_markets(self, collector):
        """Testa listagem de mercados disponíveis."""
        markets = collector.get_available_markets()
        
        assert len(markets) > 0
        assert all("id" in m for m in markets)
        assert all("name" in m for m in markets)
    
    def test_normalize_cep_valido(self, collector):
        """Testa normalização de CEP válido."""
        # Com hífen
        assert collector._normalize_cep("40000-000") == "40000000"
        
        # Sem hífen
        assert collector._normalize_cep("40000000") == "40000000"
        
        # Com espaços
        assert collector._normalize_cep(" 40000000 ") == "40000000"
    
    def test_normalize_cep_invalido(self, collector):
        """Testa que CEP inválido levanta exceção."""
        with pytest.raises(ValueError):
            collector._normalize_cep("1234")
        
        with pytest.raises(ValueError):
            collector._normalize_cep("123456789")
    
    @pytest.mark.asyncio
    async def test_get_statistics_empty(self, collector):
        """Testa estatísticas com banco vazio."""
        stats = await collector.get_statistics()
        
        assert stats["total_offers"] == 0