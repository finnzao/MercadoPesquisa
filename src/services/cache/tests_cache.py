"""
Testes unitários para o módulo de Cache com TTL Dinâmico.

Execute com: pytest tests_cache.py -v
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

# Importa os módulos a serem testados
from dynamic_ttl import DynamicTTLCalculator, TTLConfig, TimePeriod
from cache_service import CacheService, CacheEntry, LRUCache, CacheStats


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def ttl_calculator():
    """Retorna instância do calculador de TTL."""
    return DynamicTTLCalculator()


@pytest.fixture
def custom_ttl_config():
    """Retorna configuração customizada de TTL."""
    return TTLConfig(min_ttl=30, max_ttl=1800, default_ttl=120)


@pytest.fixture
async def cache_service():
    """Retorna instância do cache service (sem Redis)."""
    service = CacheService(redis_url=None, l1_max_size=100)
    await service.initialize()
    yield service
    await service.close()


@pytest.fixture
async def lru_cache():
    """Retorna instância do LRU cache."""
    return LRUCache(max_size=5)


# =============================================================================
# Testes do DynamicTTLCalculator
# =============================================================================

class TestDynamicTTLCalculator:
    """Testes para o calculador de TTL dinâmico."""
    
    def test_get_current_period_overnight(self, ttl_calculator):
        """Testa detecção do período da madrugada."""
        with patch('dynamic_ttl.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2025, 1, 25, 3, 0, 0)
            period = ttl_calculator.get_current_period()
            assert period == TimePeriod.OVERNIGHT
    
    def test_get_current_period_morning(self, ttl_calculator):
        """Testa detecção do período da manhã."""
        with patch('dynamic_ttl.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2025, 1, 25, 9, 0, 0)
            period = ttl_calculator.get_current_period()
            assert period == TimePeriod.MORNING
    
    def test_get_current_period_afternoon(self, ttl_calculator):
        """Testa detecção do período da tarde."""
        with patch('dynamic_ttl.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2025, 1, 25, 14, 0, 0)
            period = ttl_calculator.get_current_period()
            assert period == TimePeriod.AFTERNOON
    
    def test_get_current_period_evening(self, ttl_calculator):
        """Testa detecção do período da noite."""
        with patch('dynamic_ttl.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2025, 1, 25, 20, 0, 0)
            period = ttl_calculator.get_current_period()
            assert period == TimePeriod.EVENING
    
    def test_calculate_ttl_basic(self, ttl_calculator):
        """Testa cálculo básico de TTL."""
        ttl = ttl_calculator.calculate_ttl()
        assert ttl >= 60   # Mínimo
        assert ttl <= 3600  # Máximo
    
    def test_calculate_ttl_with_market(self, ttl_calculator):
        """Testa cálculo de TTL com mercado específico."""
        ttl_atacadao = ttl_calculator.calculate_ttl(market_id="atacadao")
        ttl_gbarbosa = ttl_calculator.calculate_ttl(market_id="gbarbosa")
        
        # Atacadão tem multiplicador menor (0.8) que GBarbosa (1.2)
        # Então TTL do Atacadão deve ser menor
        assert ttl_atacadao < ttl_gbarbosa
    
    def test_calculate_ttl_promotional(self, ttl_calculator):
        """Testa que produtos promocionais têm TTL menor."""
        ttl_normal = ttl_calculator.calculate_ttl(is_promotional=False)
        ttl_promo = ttl_calculator.calculate_ttl(is_promotional=True)
        
        # Promocional tem multiplicador 0.5
        assert ttl_promo < ttl_normal
        assert ttl_promo == pytest.approx(ttl_normal * 0.5, rel=0.1)
    
    def test_calculate_ttl_popularity(self, ttl_calculator):
        """Testa que popularidade aumenta TTL."""
        ttl_unpopular = ttl_calculator.calculate_ttl(query_popularity=0.0)
        ttl_popular = ttl_calculator.calculate_ttl(query_popularity=1.0)
        
        # Popularidade 1.0 tem multiplicador 1.3
        assert ttl_popular > ttl_unpopular
    
    def test_calculate_ttl_respects_limits(self, ttl_calculator):
        """Testa que TTL respeita limites mínimo e máximo."""
        # Cenário que resultaria em TTL muito baixo
        ttl_low = ttl_calculator.calculate_ttl(
            is_promotional=True,
            market_id="atacadao"
        )
        assert ttl_low >= 60
        
        # Cenário que resultaria em TTL muito alto
        ttl_high = ttl_calculator.calculate_ttl(
            query_popularity=1.0,
            custom_base_ttl=5000
        )
        assert ttl_high <= 3600
    
    def test_calculate_ttl_custom_config(self, custom_ttl_config):
        """Testa com configuração customizada."""
        calculator = DynamicTTLCalculator(config=custom_ttl_config)
        ttl = calculator.calculate_ttl()
        
        assert ttl >= custom_ttl_config.min_ttl
        assert ttl <= custom_ttl_config.max_ttl
    
    def test_calculate_ttl_for_search_multiple_markets(self, ttl_calculator):
        """Testa cálculo para múltiplos mercados."""
        ttl = ttl_calculator.calculate_ttl_for_search(
            query="arroz",
            market_ids=["carrefour", "atacadao", "gbarbosa"]
        )
        
        # Deve usar o menor TTL entre os mercados
        ttl_atacadao = ttl_calculator.calculate_ttl(market_id="atacadao")
        assert ttl <= ttl_atacadao
    
    def test_get_ttl_info(self, ttl_calculator):
        """Testa retorno de informações detalhadas."""
        info = ttl_calculator.get_ttl_info(
            market_id="carrefour",
            is_promotional=True,
            query_popularity=0.5
        )
        
        assert "period" in info
        assert "weekday" in info
        assert "base_ttl_seconds" in info
        assert "multipliers" in info
        assert "final_ttl_seconds" in info
        assert "final_ttl_formatted" in info
        
        assert info["multipliers"]["promotional"] == 0.5


# =============================================================================
# Testes do LRUCache
# =============================================================================

class TestLRUCache:
    """Testes para o cache LRU em memória."""
    
    @pytest.mark.asyncio
    async def test_set_and_get(self, lru_cache):
        """Testa operações básicas de set e get."""
        entry = CacheEntry(
            value={"test": "data"},
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(seconds=60),
            ttl_seconds=60
        )
        
        await lru_cache.set("key1", entry)
        result = await lru_cache.get("key1")
        
        assert result is not None
        assert result.value == {"test": "data"}
    
    @pytest.mark.asyncio
    async def test_get_nonexistent(self, lru_cache):
        """Testa busca de chave inexistente."""
        result = await lru_cache.get("nonexistent")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_expired_entry(self, lru_cache):
        """Testa que entradas expiradas são removidas."""
        entry = CacheEntry(
            value="expired",
            created_at=datetime.now() - timedelta(seconds=120),
            expires_at=datetime.now() - timedelta(seconds=60),  # Já expirou
            ttl_seconds=60
        )
        
        await lru_cache.set("expired_key", entry)
        result = await lru_cache.get("expired_key")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_lru_eviction(self, lru_cache):
        """Testa que LRU remove itens mais antigos."""
        # Cache tem max_size=5
        for i in range(7):
            entry = CacheEntry(
                value=f"value_{i}",
                created_at=datetime.now(),
                expires_at=datetime.now() + timedelta(seconds=60),
                ttl_seconds=60
            )
            await lru_cache.set(f"key_{i}", entry)
        
        # Primeiras duas chaves devem ter sido removidas
        assert await lru_cache.get("key_0") is None
        assert await lru_cache.get("key_1") is None
        
        # Últimas chaves devem existir
        assert await lru_cache.get("key_5") is not None
        assert await lru_cache.get("key_6") is not None
    
    @pytest.mark.asyncio
    async def test_access_moves_to_end(self, lru_cache):
        """Testa que acesso move item para o final."""
        for i in range(5):
            entry = CacheEntry(
                value=f"value_{i}",
                created_at=datetime.now(),
                expires_at=datetime.now() + timedelta(seconds=60),
                ttl_seconds=60
            )
            await lru_cache.set(f"key_{i}", entry)
        
        # Acessa key_0 (mais antiga)
        await lru_cache.get("key_0")
        
        # Adiciona mais um item
        entry = CacheEntry(
            value="new",
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(seconds=60),
            ttl_seconds=60
        )
        await lru_cache.set("key_new", entry)
        
        # key_0 deve existir (foi acessada recentemente)
        assert await lru_cache.get("key_0") is not None
        
        # key_1 deve ter sido removida
        assert await lru_cache.get("key_1") is None
    
    @pytest.mark.asyncio
    async def test_delete(self, lru_cache):
        """Testa remoção de chave."""
        entry = CacheEntry(
            value="to_delete",
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(seconds=60),
            ttl_seconds=60
        )
        
        await lru_cache.set("delete_me", entry)
        assert await lru_cache.get("delete_me") is not None
        
        result = await lru_cache.delete("delete_me")
        assert result is True
        assert await lru_cache.get("delete_me") is None
    
    @pytest.mark.asyncio
    async def test_delete_pattern(self, lru_cache):
        """Testa remoção por padrão."""
        for i in range(3):
            entry = CacheEntry(
                value=f"search_{i}",
                created_at=datetime.now(),
                expires_at=datetime.now() + timedelta(seconds=60),
                ttl_seconds=60
            )
            await lru_cache.set(f"search:arroz:{i}", entry)
        
        entry = CacheEntry(
            value="other",
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(seconds=60),
            ttl_seconds=60
        )
        await lru_cache.set("other:key", entry)
        
        deleted = await lru_cache.delete_pattern("search:*")
        
        assert deleted == 3
        assert await lru_cache.get("search:arroz:0") is None
        assert await lru_cache.get("other:key") is not None
    
    @pytest.mark.asyncio
    async def test_cleanup_expired(self, lru_cache):
        """Testa limpeza de expirados."""
        # Adiciona entrada válida
        valid = CacheEntry(
            value="valid",
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(seconds=60),
            ttl_seconds=60
        )
        await lru_cache.set("valid", valid)
        
        # Adiciona entrada expirada
        expired = CacheEntry(
            value="expired",
            created_at=datetime.now() - timedelta(seconds=120),
            expires_at=datetime.now() - timedelta(seconds=60),
            ttl_seconds=60
        )
        # Força inserção direta para testar limpeza
        lru_cache._cache["expired"] = expired
        
        cleaned = await lru_cache.cleanup_expired()
        
        assert cleaned == 1
        assert lru_cache.size() == 1


# =============================================================================
# Testes do CacheService
# =============================================================================

class TestCacheService:
    """Testes para o serviço de cache completo."""
    
    @pytest.mark.asyncio
    async def test_set_and_get(self, cache_service):
        """Testa operações básicas."""
        await cache_service.set(
            key="test:key",
            value={"data": "test"},
            market_id="carrefour"
        )
        
        result = await cache_service.get("test:key")
        
        assert result is not None
        assert result["data"] == "test"
    
    @pytest.mark.asyncio
    async def test_cache_miss(self, cache_service):
        """Testa cache miss."""
        result = await cache_service.get("nonexistent:key")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_stats_tracking(self, cache_service):
        """Testa rastreamento de estatísticas."""
        # Hit
        await cache_service.set("stats:test", {"value": 1})
        await cache_service.get("stats:test")
        
        # Miss
        await cache_service.get("stats:miss")
        
        stats = cache_service.get_stats()
        
        assert stats["l1"]["hits"] == 1
        assert stats["l1"]["misses"] == 1
        assert stats["total_sets"] == 1
    
    @pytest.mark.asyncio
    async def test_delete(self, cache_service):
        """Testa remoção."""
        await cache_service.set("delete:test", {"value": 1})
        assert await cache_service.get("delete:test") is not None
        
        await cache_service.delete("delete:test")
        assert await cache_service.get("delete:test") is None
    
    @pytest.mark.asyncio
    async def test_delete_pattern(self, cache_service):
        """Testa remoção por padrão."""
        await cache_service.set("pattern:a", {"a": 1})
        await cache_service.set("pattern:b", {"b": 2})
        await cache_service.set("other:c", {"c": 3})
        
        deleted = await cache_service.delete_pattern("pattern:*")
        
        assert deleted == 2
        assert await cache_service.get("pattern:a") is None
        assert await cache_service.get("other:c") is not None
    
    @pytest.mark.asyncio
    async def test_invalidate_market(self, cache_service):
        """Testa invalidação por mercado."""
        await cache_service.set("search:arroz:carrefour:123", {"a": 1})
        await cache_service.set("search:leite:carrefour:456", {"b": 2})
        await cache_service.set("search:arroz:atacadao:789", {"c": 3})
        
        deleted = await cache_service.invalidate_market("carrefour")
        
        assert deleted == 2
        assert await cache_service.get("search:arroz:carrefour:123") is None
        assert await cache_service.get("search:arroz:atacadao:789") is not None
    
    @pytest.mark.asyncio
    async def test_clear(self, cache_service):
        """Testa limpeza total."""
        await cache_service.set("clear:a", {"a": 1})
        await cache_service.set("clear:b", {"b": 2})
        
        await cache_service.clear()
        
        assert await cache_service.get("clear:a") is None
        assert await cache_service.get("clear:b") is None
        
        stats = cache_service.get_stats()
        assert stats["l1"]["hits"] == 0
    
    @pytest.mark.asyncio
    async def test_custom_ttl(self, cache_service):
        """Testa TTL customizado."""
        await cache_service.set(
            key="custom:ttl",
            value={"test": 1},
            custom_ttl=120
        )
        
        result = await cache_service.get("custom:ttl")
        assert result is not None
    
    @pytest.mark.asyncio
    async def test_promotional_reduces_ttl(self, cache_service):
        """Testa que produtos promocionais têm TTL reduzido."""
        calculator = cache_service.get_ttl_calculator()
        
        ttl_normal = calculator.calculate_ttl(is_promotional=False)
        ttl_promo = calculator.calculate_ttl(is_promotional=True)
        
        assert ttl_promo < ttl_normal


# =============================================================================
# Testes de CacheEntry
# =============================================================================

class TestCacheEntry:
    """Testes para a classe CacheEntry."""
    
    def test_is_expired_false(self):
        """Testa entrada não expirada."""
        entry = CacheEntry(
            value="test",
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(seconds=60),
            ttl_seconds=60
        )
        
        assert entry.is_expired() is False
    
    def test_is_expired_true(self):
        """Testa entrada expirada."""
        entry = CacheEntry(
            value="test",
            created_at=datetime.now() - timedelta(seconds=120),
            expires_at=datetime.now() - timedelta(seconds=60),
            ttl_seconds=60
        )
        
        assert entry.is_expired() is True
    
    def test_remaining_ttl(self):
        """Testa cálculo de TTL restante."""
        entry = CacheEntry(
            value="test",
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(seconds=30),
            ttl_seconds=60
        )
        
        remaining = entry.remaining_ttl()
        assert 25 <= remaining <= 30


# =============================================================================
# Testes de CacheStats
# =============================================================================

class TestCacheStats:
    """Testes para estatísticas do cache."""
    
    def test_hit_rate_calculation(self):
        """Testa cálculo de hit rate."""
        stats = CacheStats(l1_hits=80, l1_misses=20)
        
        assert stats.l1_hit_rate == 80.0
    
    def test_hit_rate_zero_division(self):
        """Testa hit rate com zero requisições."""
        stats = CacheStats()
        
        assert stats.l1_hit_rate == 0.0
        assert stats.l2_hit_rate == 0.0
    
    def test_to_dict(self):
        """Testa conversão para dicionário."""
        stats = CacheStats(
            l1_hits=10,
            l1_misses=5,
            total_sets=15
        )
        
        result = stats.to_dict()
        
        assert result["l1"]["hits"] == 10
        assert result["l1"]["misses"] == 5
        assert result["total_sets"] == 15


# =============================================================================
# Executar testes
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
