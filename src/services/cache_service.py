"""
Serviço de Cache usando Redis.
Gerencia cache de resultados de busca e rate limiting.
"""

import asyncio
import hashlib
import json
from datetime import datetime
from typing import Any, Optional, TypeVar, Generic
from dataclasses import dataclass

import redis.asyncio as redis
from pydantic import BaseModel

from config.settings import get_settings
from config.logging_config import LoggerMixin

T = TypeVar("T")


@dataclass
class CacheEntry:
    """Entrada do cache com metadados."""
    data: Any
    created_at: datetime
    ttl_seconds: int
    hits: int = 0


class RedisClient(LoggerMixin):
    """
    Cliente Redis singleton para cache e rate limiting.
    
    Uso:
        client = await RedisClient.get_instance()
        await client.set("key", "value", ttl=300)
        value = await client.get("key")
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
                "Redis não disponível, cache desabilitado",
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
            self.logger.debug("Erro ao ler cache", key=key, error=str(e))
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
            self.logger.debug("Erro ao escrever cache", key=key, error=str(e))
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
            self.logger.debug("Erro ao deletar cache", key=key, error=str(e))
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


class CacheService(LoggerMixin):
    """
    Serviço de cache de alto nível para resultados de busca.
    
    Gera chaves de cache baseadas nos parâmetros de busca
    e gerencia serialização/deserialização.
    """
    
    def __init__(self):
        self.settings = get_settings()
        self._client: Optional[RedisClient] = None
    
    async def _get_client(self) -> RedisClient:
        """Obtém cliente Redis."""
        if self._client is None:
            self._client = await RedisClient.get_instance()
        return self._client
    
    def _generate_cache_key(
        self,
        query: str,
        cep: Optional[str] = None,
        markets: Optional[list[str]] = None,
    ) -> str:
        """
        Gera chave de cache única baseada nos parâmetros.
        
        Args:
            query: Termo de busca
            cep: CEP (opcional)
            markets: Lista de mercados (opcional)
            
        Returns:
            Hash MD5 dos parâmetros
        """
        # Normaliza parâmetros
        query_normalized = query.lower().strip()
        cep_normalized = cep or "all"
        markets_normalized = ",".join(sorted(markets)) if markets else "all"
        
        # Cria string para hash
        cache_string = f"search:{query_normalized}:{cep_normalized}:{markets_normalized}"
        
        # Gera hash MD5
        return hashlib.md5(cache_string.encode()).hexdigest()
    
    async def get_search_result(
        self,
        query: str,
        cep: Optional[str] = None,
        markets: Optional[list[str]] = None,
    ) -> Optional[dict]:
        """
        Obtém resultado de busca do cache.
        
        Args:
            query: Termo de busca
            cep: CEP
            markets: Lista de mercados
            
        Returns:
            Resultado cacheado ou None
        """
        if not self.settings.cache_enabled:
            return None
        
        client = await self._get_client()
        if not client.is_connected:
            return None
        
        cache_key = self._generate_cache_key(query, cep, markets)
        
        cached = await client.get(f"search:{cache_key}")
        if cached:
            try:
                result = json.loads(cached)
                self.logger.debug(
                    "Cache hit",
                    query=query,
                    key=cache_key[:8],
                )
                return result
            except json.JSONDecodeError:
                await client.delete(f"search:{cache_key}")
        
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
        Armazena resultado de busca no cache.
        
        Args:
            query: Termo de busca
            result: Resultado a cachear
            cep: CEP
            markets: Lista de mercados
            ttl: TTL customizado
            
        Returns:
            True se cacheou com sucesso
        """
        if not self.settings.cache_enabled:
            return False
        
        client = await self._get_client()
        if not client.is_connected:
            return False
        
        cache_key = self._generate_cache_key(query, cep, markets)
        
        try:
            cached_data = json.dumps(result, default=str)
            success = await client.set(
                f"search:{cache_key}",
                cached_data,
                ttl=ttl or self.settings.cache_ttl_seconds,
            )
            
            if success:
                self.logger.debug(
                    "Cache set",
                    query=query,
                    key=cache_key[:8],
                    ttl=ttl or self.settings.cache_ttl_seconds,
                )
            
            return success
            
        except Exception as e:
            self.logger.warning("Erro ao cachear resultado", error=str(e))
            return False
    
    async def invalidate_search(
        self,
        query: str,
        cep: Optional[str] = None,
        markets: Optional[list[str]] = None,
    ) -> bool:
        """Invalida cache de uma busca específica."""
        client = await self._get_client()
        if not client.is_connected:
            return False
        
        cache_key = self._generate_cache_key(query, cep, markets)
        return await client.delete(f"search:{cache_key}")
    
    async def invalidate_market(self, market_id: str) -> int:
        """
        Invalida todos os caches de um mercado.
        
        Nota: Requer SCAN para encontrar chaves relacionadas.
        Em produção, considere usar tags ou estrutura diferente.
        """
        # Implementação simplificada - em produção usar SCAN
        self.logger.info("Invalidação de mercado solicitada", market=market_id)
        return 0


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
        
        Args:
            identifier: ID único (user_id, ip, etc)
            limit: Limite de requisições
            window_seconds: Janela de tempo em segundos
            
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
            self.settings.rate_limit_requests_per_minute * 2,  # IP tem limite maior
        )


# Instâncias globais para uso simplificado
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
