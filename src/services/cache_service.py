# src/services/cache_service.py
"""
Serviço de Cache usando Redis + Cache em Memória (L1).
Gerencia cache de resultados de busca e rate limiting.

- Cache L1 em memória (LRU) para respostas frequentes
- Cache L2 no Redis para persistência
- Reduz latência de ~5ms (Redis) para ~0.1ms (memória)
"""

import asyncio
import hashlib
import json
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Optional

import redis.asyncio as redis

from config.logging_config import LoggerMixin
from config.settings import get_settings


# CACHE L1 - MEMÓRIA (LRU)

@dataclass
class CacheEntry:
    """Entrada de cache com TTL."""
    data: Any
    expires_at: float
    hits: int = 0


class LRUMemoryCache:
    """
    Cache LRU em memória com TTL.
    
    - Acesso em ~0.1ms
    - Evita ida ao Redis para queries frequentes
    - Limite de tamanho para não estourar memória
    """
    
    def __init__(self, max_size: int = 1000, default_ttl: int = 60):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0
    
    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None
            
            entry = self._cache[key]
            
            # Verifica expiração
            if time.time() > entry.expires_at:
                del self._cache[key]
                self._misses += 1
                return None
            
            # Move para o final (LRU)
            self._cache.move_to_end(key)
            entry.hits += 1
            self._hits += 1
            return entry.data
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None):
        async with self._lock:
            ttl = ttl or self.default_ttl
            expires_at = time.time() + ttl
            
            # Remove mais antigo se cheio
            while len(self._cache) >= self.max_size:
                self._cache.popitem(last=False)
            
            self._cache[key] = CacheEntry(data=value, expires_at=expires_at)
    
    async def delete(self, key: str):
        async with self._lock:
            self._cache.pop(key, None)
    
    async def clear(self):
        async with self._lock:
            self._cache.clear()
    
    def stats(self) -> dict:
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate_percent": round(hit_rate, 2),
        }


# REDIS CLIENT (L2)

class RedisClient(LoggerMixin):
    """
    Cliente Redis singleton para cache e rate limiting.
    """
    
    _instance: Optional["RedisClient"] = None
    _lock = asyncio.Lock()
    
    def __init__(self):
        self.settings = get_settings()
        self._redis: Optional[redis.Redis] = None
        self._connected = False
    
    @classmethod
    async def get_instance(cls) -> "RedisClient":
        """Retorna instância singleton do cliente."""
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
                    await cls._instance.connect()
        return cls._instance
    
    async def connect(self) -> bool:
        """Estabelece conexão com Redis."""
        if self._connected:
            return True
        
        try:
            self._redis = redis.from_url(
                self.settings.redis_url,
                password=self.settings.redis_password,
                encoding="utf-8",
                decode_responses=True,
            )
            
            # Testa conexão
            await self._redis.ping()
            self._connected = True
            self.logger.info("Redis conectado", url=self.settings.redis_url)
            return True
            
        except Exception as e:
            self.logger.warning(
                "Redis não disponível, usando apenas cache L1",
                error=str(e),
            )
            self._connected = False
            return False
    
    async def disconnect(self) -> None:
        """Fecha conexão com Redis."""
        if self._redis:
            await self._redis.close()
            self._connected = False
            self.logger.info("Redis desconectado")
    
    @property
    def is_connected(self) -> bool:
        """Verifica se está conectado."""
        return self._connected
    
    async def get(self, key: str) -> Optional[str]:
        """Obtém valor do cache."""
        if not self._connected:
            return None
        
        try:
            full_key = f"{self.settings.cache_prefix}{key}"
            return await self._redis.get(full_key)
        except Exception as e:
            self.logger.debug("Erro ao ler cache Redis", key=key, error=str(e))
            return None
    
    async def set(
        self,
        key: str,
        value: str,
        ttl: Optional[int] = None,
    ) -> bool:
        """Define valor no cache."""
        if not self._connected:
            return False
        
        try:
            full_key = f"{self.settings.cache_prefix}{key}"
            ttl = ttl or self.settings.cache_ttl_seconds
            await self._redis.setex(full_key, ttl, value)
            return True
        except Exception as e:
            self.logger.debug("Erro ao escrever cache Redis", key=key, error=str(e))
            return False
    
    async def delete(self, key: str) -> bool:
        """Remove valor do cache."""
        if not self._connected:
            return False
        
        try:
            full_key = f"{self.settings.cache_prefix}{key}"
            await self._redis.delete(full_key)
            return True
        except Exception as e:
            self.logger.debug("Erro ao deletar cache Redis", key=key, error=str(e))
            return False
    
    async def exists(self, key: str) -> bool:
        """Verifica se chave existe."""
        if not self._connected:
            return False
        
        try:
            full_key = f"{self.settings.cache_prefix}{key}"
            return await self._redis.exists(full_key) > 0
        except Exception:
            return False
    
    async def incr(self, key: str, ttl: Optional[int] = None) -> int:
        """Incrementa contador (para rate limiting)."""
        if not self._connected:
            return 0
        
        try:
            full_key = f"{self.settings.cache_prefix}{key}"
            count = await self._redis.incr(full_key)
            
            # Define TTL apenas na primeira vez
            if count == 1 and ttl:
                await self._redis.expire(full_key, ttl)
            
            return count
        except Exception:
            return 0
    
    async def get_ttl(self, key: str) -> int:
        """Retorna TTL restante de uma chave."""
        if not self._connected:
            return -1
        
        try:
            full_key = f"{self.settings.cache_prefix}{key}"
            return await self._redis.ttl(full_key)
        except Exception:
            return -1


# CACHE SERVICE (L1 + L2)

class CacheService(LoggerMixin):
    """
    Serviço de cache de alto nível para resultados de busca.
    
    ARQUITETURA MULTI-LAYER:
    - L1 (Memória): Cache LRU com TTL curto (60s)
    - L2 (Redis): Cache persistente com TTL maior (300s)
    
    FLUXO DE LEITURA:
    1. Tenta L1 (memória) - ~0.1ms
    2. Se miss, tenta L2 (Redis) - ~1-5ms
    3. Se encontrar em L2, popula L1
    
    FLUXO DE ESCRITA:
    1. Escreve em L1 (memória)
    2. Escreve em L2 (Redis) em background
    """
    
    # Configurações de TTL
    L1_TTL_SECONDS = 60    # 1 minuto em memória
    L2_TTL_SECONDS = 300   # 5 minutos no Redis
    L1_MAX_SIZE = 1000     # Máximo de entradas em memória
    
    def __init__(self):
        self.settings = get_settings()
        self._redis_client: Optional[RedisClient] = None
        self._l1_cache = LRUMemoryCache(
            max_size=self.L1_MAX_SIZE,
            default_ttl=self.L1_TTL_SECONDS,
        )
    
    async def _get_redis(self) -> RedisClient:
        """Obtém cliente Redis."""
        if self._redis_client is None:
            self._redis_client = await RedisClient.get_instance()
        return self._redis_client
    
    def _generate_cache_key(
        self,
        query: str,
        cep: Optional[str] = None,
        markets: Optional[list[str]] = None,
    ) -> str:
        """
        Gera chave de cache única baseada nos parâmetros.
        """
        # Normaliza parâmetros
        query_normalized = query.lower().strip()
        cep_normalized = cep or "all"
        markets_normalized = ",".join(sorted(markets)) if markets else "all"
        
        # Cria string para hash
        cache_string = f"search:{query_normalized}:{cep_normalized}:{markets_normalized}"
        
        # Gera hash MD5 (curto para economizar memória)
        return hashlib.md5(cache_string.encode()).hexdigest()[:16]
    
    async def get_search_result(
        self,
        query: str,
        cep: Optional[str] = None,
        markets: Optional[list[str]] = None,
    ) -> Optional[dict]:
        """
        Obtém resultado de busca do cache (L1 -> L2).
        """
        if not self.settings.cache_enabled:
            return None
        
        cache_key = self._generate_cache_key(query, cep, markets)
        
        # 1. Tenta L1 (memória)
        result = await self._l1_cache.get(cache_key)
        if result is not None:
            self.logger.debug("Cache L1 hit", query=query, key=cache_key[:8])
            return result
        
        # 2. Tenta L2 (Redis)
        redis_client = await self._get_redis()
        if not redis_client.is_connected:
            return None
        
        cached = await redis_client.get(f"search:{cache_key}")
        if cached:
            try:
                result = json.loads(cached)
                # Popula L1 para próximas consultas
                await self._l1_cache.set(cache_key, result, self.L1_TTL_SECONDS)
                self.logger.debug("Cache L2 hit -> L1", query=query, key=cache_key[:8])
                return result
            except json.JSONDecodeError:
                await redis_client.delete(f"search:{cache_key}")
        
        return None
    
    async def set_search_result(
        self,
        query: str,
        result: dict,
        cep: Optional[str] = None,
        markets: Optional[list[str]] = None,
        ttl: Optional[int] = None,
    ) -> bool:
        """
        Armazena resultado de busca no cache (L1 + L2).
        """
        if not self.settings.cache_enabled:
            return False
        
        cache_key = self._generate_cache_key(query, cep, markets)
        l2_ttl = ttl or self.L2_TTL_SECONDS
        
        # 1. Salva em L1 (memória) - TTL menor
        await self._l1_cache.set(
            cache_key,
            result,
            min(self.L1_TTL_SECONDS, l2_ttl),
        )
        
        # 2. Salva em L2 (Redis)
        redis_client = await self._get_redis()
        if not redis_client.is_connected:
            return True  # L1 funcionou
        
        try:
            cached_data = json.dumps(result, default=str)
            success = await redis_client.set(
                f"search:{cache_key}",
                cached_data,
                ttl=l2_ttl,
            )
            
            if success:
                self.logger.debug(
                    "Cache set L1+L2",
                    query=query,
                    key=cache_key[:8],
                    l2_ttl=l2_ttl,
                )
            
            return success
            
        except Exception as e:
            self.logger.warning("Erro ao cachear em L2", error=str(e))
            return True  # L1 funcionou
    
    async def invalidate_search(
        self,
        query: str,
        cep: Optional[str] = None,
        markets: Optional[list[str]] = None,
    ) -> bool:
        """Invalida cache de uma busca específica."""
        cache_key = self._generate_cache_key(query, cep, markets)
        
        # Invalida L1
        await self._l1_cache.delete(cache_key)
        
        # Invalida L2
        redis_client = await self._get_redis()
        if redis_client.is_connected:
            await redis_client.delete(f"search:{cache_key}")
        
        return True
    
    async def invalidate_market(self, market_id: str) -> int:
        """Invalida todos os caches de um mercado."""
        self.logger.info("Invalidação de mercado solicitada", market=market_id)
        # Limpa L1 completamente (simplificado)
        await self._l1_cache.clear()
        return 0
    
    def get_stats(self) -> dict:
        """Retorna estatísticas do cache."""
        return {
            "l1": self._l1_cache.stats(),
            "l2_connected": self._redis_client.is_connected if self._redis_client else False,
        }


# RATE LIMITER

class RateLimiter(LoggerMixin):
    """
    Rate limiter usando Redis.
    Implementa sliding window com contador.
    """
    
    def __init__(self):
        self.settings = get_settings()
        self._client: Optional[RedisClient] = None
    
    async def _get_client(self) -> RedisClient:
        """Obtém cliente Redis."""
        if self._client is None:
            self._client = await RedisClient.get_instance()
        return self._client
    
    async def is_allowed(
        self,
        identifier: str,
        limit: Optional[int] = None,
        window_seconds: int = 60,
    ) -> tuple[bool, int, int]:
        """
        Verifica se requisição é permitida.
        
        Returns:
            Tupla (permitido, requisições_restantes, ttl_reset)
        """
        if not self.settings.rate_limit_enabled:
            return True, -1, 0
        
        client = await self._get_client()
        if not client.is_connected:
            # Se Redis não disponível, permite (fail-open)
            return True, -1, 0
        
        limit = limit or self.settings.rate_limit_requests_per_minute
        key = f"ratelimit:{identifier}"
        
        # Incrementa contador
        current = await client.incr(key, ttl=window_seconds)
        remaining = max(0, limit - current)
        ttl = await client.get_ttl(key)
        
        allowed = current <= limit
        
        if not allowed:
            self.logger.warning(
                "Rate limit excedido",
                identifier=identifier,
                current=current,
                limit=limit,
            )
        
        return allowed, remaining, ttl
    
    async def check_user(self, user_id: str) -> tuple[bool, int, int]:
        """Verifica rate limit para um usuário."""
        return await self.is_allowed(
            f"user:{user_id}",
            self.settings.rate_limit_requests_per_minute,
        )
    
    async def check_market(self, market_id: str) -> tuple[bool, int, int]:
        """Verifica rate limit para um mercado."""
        limit = self.settings.get_rate_limit(market_id)
        return await self.is_allowed(
            f"market:{market_id}",
            limit,
        )
    
    async def check_ip(self, ip: str) -> tuple[bool, int, int]:
        """Verifica rate limit para um IP."""
        return await self.is_allowed(
            f"ip:{ip}",
            self.settings.rate_limit_requests_per_minute * 2,
        )

# INSTÂNCIAS GLOBAIS

_cache_service: Optional[CacheService] = None
_rate_limiter: Optional[RateLimiter] = None


async def get_cache_service() -> CacheService:
    """Retorna instância do serviço de cache."""
    global _cache_service
    if _cache_service is None:
        _cache_service = CacheService()
    return _cache_service


async def get_rate_limiter() -> RateLimiter:
    """Retorna instância do rate limiter."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter