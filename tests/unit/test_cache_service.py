"""
Testes unitários para o serviço de cache.
"""

import asyncio
import time

import pytest
import pytest_asyncio

from src.services.cache_service import (
    LRUMemoryCache,
    CacheEntry,
    CacheService,
    RedisClient,
)


class TestLRUMemoryCache:
    """Testes para LRUMemoryCache."""
    
    @pytest_asyncio.fixture
    async def cache(self):
        """Instância do cache."""
        return LRUMemoryCache(max_size=5, default_ttl=60)
    
    @pytest.mark.asyncio
    async def test_set_and_get(self, cache):
        """Testa operações básicas de set e get."""
        await cache.set("key1", "value1")
        result = await cache.get("key1")
        
        assert result == "value1"
    
    @pytest.mark.asyncio
    async def test_get_nonexistent(self, cache):
        """Testa busca de chave inexistente."""
        result = await cache.get("nonexistent")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_expired_entry_returns_none(self, cache):
        """Testa que entradas expiradas retornam None."""
        # Cria um cache com TTL muito curto
        cache_short_ttl = LRUMemoryCache(max_size=5, default_ttl=1)
        
        await cache_short_ttl.set("key1", "value1", ttl=1)
        
        # Espera expirar
        await asyncio.sleep(1.5)
        
        result = await cache_short_ttl.get("key1")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_lru_eviction(self, cache):
        """Testa que LRU remove itens mais antigos."""
        # Cache tem max_size=5
        for i in range(7):
            await cache.set(f"key_{i}", f"value_{i}")
        
        # Primeiras duas chaves devem ter sido removidas
        assert await cache.get("key_0") is None
        assert await cache.get("key_1") is None
        
        # Últimas chaves devem existir
        assert await cache.get("key_5") is not None
        assert await cache.get("key_6") is not None
    
    @pytest.mark.asyncio
    async def test_access_moves_to_end(self, cache):
        """Testa que acesso move item para o final."""
        for i in range(5):
            await cache.set(f"key_{i}", f"value_{i}")
        
        # Acessa key_0 (mais antiga)
        await cache.get("key_0")
        
        # Adiciona mais um item
        await cache.set("key_new", "new_value")
        
        # key_0 deve existir (foi acessada recentemente)
        assert await cache.get("key_0") is not None
        
        # key_1 deve ter sido removida
        assert await cache.get("key_1") is None
    
    @pytest.mark.asyncio
    async def test_delete(self, cache):
        """Testa remoção de chave."""
        await cache.set("delete_me", "value")
        assert await cache.get("delete_me") is not None
        
        await cache.delete("delete_me")
        assert await cache.get("delete_me") is None
    
    @pytest.mark.asyncio
    async def test_clear(self, cache):
        """Testa limpeza do cache."""
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        
        await cache.clear()
        
        assert await cache.get("key1") is None
        assert await cache.get("key2") is None
    
    @pytest.mark.asyncio
    async def test_stats(self, cache):
        """Testa estatísticas do cache."""
        await cache.set("key1", "value1")
        await cache.get("key1")  # hit
        await cache.get("key2")  # miss
        
        stats = cache.stats()
        
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["size"] == 1


class TestCacheService:
    """Testes para CacheService."""
    
    @pytest_asyncio.fixture
    async def service(self):
        """Instância do serviço de cache."""
        return CacheService()
    
    @pytest.mark.asyncio
    async def test_generate_cache_key(self, service):
        """Testa geração de chave de cache."""
        key1 = service._generate_cache_key("arroz", "40000000", ["carrefour"])
        key2 = service._generate_cache_key("arroz", "40000000", ["carrefour"])
        key3 = service._generate_cache_key("feijão", "40000000", ["carrefour"])
        
        # Mesmos parâmetros devem gerar mesma chave
        assert key1 == key2
        
        # Parâmetros diferentes devem gerar chaves diferentes
        assert key1 != key3
    
    @pytest.mark.asyncio
    async def test_get_stats(self, service):
        """Testa obtenção de estatísticas."""
        stats = service.get_stats()
        
        assert "l1" in stats
        assert "l2_connected" in stats