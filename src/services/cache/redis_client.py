# src/services/cache/redis_client.py
"""
Cliente Redis singleton para cache e rate limiting.

Gerencia conexão com Redis de forma centralizada,
com reconexão automática e fallback gracioso.
"""

import asyncio
from typing import Optional

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

import structlog

logger = structlog.get_logger()


class RedisClient:
    """
    Cliente Redis singleton para cache e rate limiting.
    
    Features:
    - Singleton pattern para reutilização de conexão
    - Reconexão automática em caso de falha
    - Fallback gracioso quando Redis não disponível
    - Métodos utilitários para operações comuns
    """
    
    _instance: Optional["RedisClient"] = None
    _lock = asyncio.Lock()
    
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        redis_password: Optional[str] = None,
        cache_prefix: str = "preco:",
        default_ttl: int = 300,
    ):
        """
        Inicializa o cliente Redis.
        
        Args:
            redis_url: URL de conexão do Redis
            redis_password: Senha do Redis (opcional)
            cache_prefix: Prefixo para todas as chaves
            default_ttl: TTL padrão em segundos
        """
        self.redis_url = redis_url
        self.redis_password = redis_password
        self.cache_prefix = cache_prefix
        self.default_ttl = default_ttl
        
        self._redis: Optional[redis.Redis] = None
        self._connected = False
    
    @classmethod
    async def get_instance(
        cls,
        redis_url: str = "redis://localhost:6379",
        redis_password: Optional[str] = None,
        cache_prefix: str = "preco:",
        default_ttl: int = 300,
    ) -> "RedisClient":
        """
        Retorna instância singleton do cliente.
        
        Args:
            redis_url: URL de conexão do Redis
            redis_password: Senha do Redis
            cache_prefix: Prefixo para chaves
            default_ttl: TTL padrão
            
        Returns:
            Instância única do RedisClient
        """
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(
                        redis_url=redis_url,
                        redis_password=redis_password,
                        cache_prefix=cache_prefix,
                        default_ttl=default_ttl,
                    )
                    await cls._instance.connect()
        return cls._instance
    
    @classmethod
    async def reset_instance(cls) -> None:
        """Reseta a instância singleton (útil para testes)."""
        if cls._instance is not None:
            await cls._instance.disconnect()
            cls._instance = None
    
    async def connect(self) -> bool:
        """
        Estabelece conexão com Redis.
        
        Returns:
            True se conectou com sucesso, False caso contrário
        """
        if self._connected:
            return True
        
        if not REDIS_AVAILABLE:
            logger.warning(
                "redis_library_not_available",
                message="Biblioteca redis não instalada. Instale com: pip install redis"
            )
            return False
        
        try:
            self._redis = redis.from_url(
                self.redis_url,
                password=self.redis_password,
                encoding="utf-8",
                decode_responses=True,
            )
            
            # Testa conexão
            await self._redis.ping()
            self._connected = True
            
            logger.info(
                "redis_connected",
                url=self._mask_url(self.redis_url),
            )
            return True
            
        except Exception as e:
            logger.warning(
                "redis_connection_failed",
                error=str(e),
                message="Redis não disponível, operações de cache serão ignoradas",
            )
            self._connected = False
            return False
    
    async def disconnect(self) -> None:
        """Fecha conexão com Redis."""
        if self._redis:
            try:
                await self._redis.close()
            except Exception as e:
                logger.debug("redis_disconnect_error", error=str(e))
            finally:
                self._connected = False
                self._redis = None
                logger.info("redis_disconnected")
    
    async def reconnect(self) -> bool:
        """Tenta reconectar ao Redis."""
        await self.disconnect()
        return await self.connect()
    
    @property
    def is_connected(self) -> bool:
        """Verifica se está conectado."""
        return self._connected
    
    def _get_full_key(self, key: str) -> str:
        """Adiciona prefixo à chave."""
        return f"{self.cache_prefix}{key}"
    
    def _mask_url(self, url: str) -> str:
        """Mascara senha na URL para logs."""
        if "@" in url:
            parts = url.split("@")
            return f"***@{parts[-1]}"
        return url
    
    # =========================================================================
    # Operações básicas
    # =========================================================================
    
    async def get(self, key: str) -> Optional[str]:
        """
        Obtém valor do cache.
        
        Args:
            key: Chave (sem prefixo)
            
        Returns:
            Valor armazenado ou None
        """
        if not self._connected or not self._redis:
            return None
        
        try:
            full_key = self._get_full_key(key)
            return await self._redis.get(full_key)
        except Exception as e:
            logger.debug("redis_get_error", key=key, error=str(e))
            return None
    
    async def set(
        self,
        key: str,
        value: str,
        ttl: Optional[int] = None,
    ) -> bool:
        """
        Define valor no cache.
        
        Args:
            key: Chave (sem prefixo)
            value: Valor a armazenar
            ttl: TTL em segundos (usa default se não informado)
            
        Returns:
            True se armazenou com sucesso
        """
        if not self._connected or not self._redis:
            return False
        
        try:
            full_key = self._get_full_key(key)
            ttl = ttl or self.default_ttl
            await self._redis.setex(full_key, ttl, value)
            return True
        except Exception as e:
            logger.debug("redis_set_error", key=key, error=str(e))
            return False
    
    async def delete(self, key: str) -> bool:
        """
        Remove valor do cache.
        
        Args:
            key: Chave (sem prefixo)
            
        Returns:
            True se removeu com sucesso
        """
        if not self._connected or not self._redis:
            return False
        
        try:
            full_key = self._get_full_key(key)
            result = await self._redis.delete(full_key)
            return result > 0
        except Exception as e:
            logger.debug("redis_delete_error", key=key, error=str(e))
            return False
    
    async def exists(self, key: str) -> bool:
        """
        Verifica se chave existe.
        
        Args:
            key: Chave (sem prefixo)
            
        Returns:
            True se existe
        """
        if not self._connected or not self._redis:
            return False
        
        try:
            full_key = self._get_full_key(key)
            return await self._redis.exists(full_key) > 0
        except Exception:
            return False
    
    async def get_ttl(self, key: str) -> int:
        """
        Retorna TTL restante de uma chave.
        
        Args:
            key: Chave (sem prefixo)
            
        Returns:
            TTL em segundos, -1 se não existe, -2 se sem TTL
        """
        if not self._connected or not self._redis:
            return -1
        
        try:
            full_key = self._get_full_key(key)
            return await self._redis.ttl(full_key)
        except Exception:
            return -1
    
    # =========================================================================
    # Operações para rate limiting
    # =========================================================================
    
    async def incr(self, key: str, ttl: Optional[int] = None) -> int:
        """
        Incrementa contador (para rate limiting).
        
        Args:
            key: Chave do contador (sem prefixo)
            ttl: TTL em segundos para a janela
            
        Returns:
            Valor atual do contador, 0 se falhou
        """
        if not self._connected or not self._redis:
            return 0
        
        try:
            full_key = self._get_full_key(key)
            count = await self._redis.incr(full_key)
            
            # Define TTL apenas na primeira vez (count == 1)
            if count == 1 and ttl:
                await self._redis.expire(full_key, ttl)
            
            return count
        except Exception as e:
            logger.debug("redis_incr_error", key=key, error=str(e))
            return 0
    
    async def decr(self, key: str) -> int:
        """
        Decrementa contador.
        
        Args:
            key: Chave do contador (sem prefixo)
            
        Returns:
            Valor atual do contador
        """
        if not self._connected or not self._redis:
            return 0
        
        try:
            full_key = self._get_full_key(key)
            return await self._redis.decr(full_key)
        except Exception:
            return 0
    
    # =========================================================================
    # Operações em lote
    # =========================================================================
    
    async def mget(self, keys: list[str]) -> list[Optional[str]]:
        """
        Obtém múltiplos valores.
        
        Args:
            keys: Lista de chaves (sem prefixo)
            
        Returns:
            Lista de valores (None para chaves não encontradas)
        """
        if not self._connected or not self._redis or not keys:
            return [None] * len(keys)
        
        try:
            full_keys = [self._get_full_key(k) for k in keys]
            return await self._redis.mget(full_keys)
        except Exception as e:
            logger.debug("redis_mget_error", error=str(e))
            return [None] * len(keys)
    
    async def delete_pattern(self, pattern: str) -> int:
        """
        Remove todas as chaves que correspondem ao padrão.
        
        Args:
            pattern: Padrão com wildcard * (ex: "search:*")
            
        Returns:
            Número de chaves removidas
        """
        if not self._connected or not self._redis:
            return 0
        
        try:
            full_pattern = self._get_full_key(pattern)
            deleted = 0
            cursor = 0
            
            while True:
                cursor, keys = await self._redis.scan(
                    cursor=cursor,
                    match=full_pattern,
                    count=100,
                )
                
                if keys:
                    await self._redis.delete(*keys)
                    deleted += len(keys)
                
                if cursor == 0:
                    break
            
            return deleted
        except Exception as e:
            logger.debug("redis_delete_pattern_error", pattern=pattern, error=str(e))
            return 0
    
    async def flush_db(self) -> bool:
        """
        Limpa todo o banco Redis atual.
        
        ⚠️ CUIDADO: Remove TODOS os dados!
        
        Returns:
            True se limpou com sucesso
        """
        if not self._connected or not self._redis:
            return False
        
        try:
            await self._redis.flushdb()
            logger.warning("redis_flushed", message="Todos os dados foram removidos")
            return True
        except Exception as e:
            logger.error("redis_flush_error", error=str(e))
            return False
    
    # =========================================================================
    # Health check
    # =========================================================================
    
    async def health_check(self) -> dict:
        """
        Verifica saúde da conexão Redis.
        
        Returns:
            Dicionário com status da conexão
        """
        result = {
            "connected": self._connected,
            "url": self._mask_url(self.redis_url),
            "prefix": self.cache_prefix,
        }
        
        if self._connected and self._redis:
            try:
                start = asyncio.get_event_loop().time()
                await self._redis.ping()
                latency = (asyncio.get_event_loop().time() - start) * 1000
                
                info = await self._redis.info("memory")
                
                result.update({
                    "status": "healthy",
                    "latency_ms": round(latency, 2),
                    "used_memory": info.get("used_memory_human", "unknown"),
                })
            except Exception as e:
                result.update({
                    "status": "unhealthy",
                    "error": str(e),
                })
        else:
            result["status"] = "disconnected"
        
        return result


# =========================================================================
# Funções de conveniência
# =========================================================================

_redis_client: Optional[RedisClient] = None


async def get_redis_client(
    redis_url: str = "redis://localhost:6379",
    redis_password: Optional[str] = None,
    cache_prefix: str = "preco:",
) -> RedisClient:
    """
    Retorna instância global do cliente Redis.
    
    Args:
        redis_url: URL de conexão
        redis_password: Senha
        cache_prefix: Prefixo das chaves
        
    Returns:
        Instância do RedisClient
    """
    global _redis_client
    
    if _redis_client is None:
        _redis_client = await RedisClient.get_instance(
            redis_url=redis_url,
            redis_password=redis_password,
            cache_prefix=cache_prefix,
        )
    
    return _redis_client


async def close_redis_client() -> None:
    """Fecha a conexão global do Redis."""
    global _redis_client
    
    if _redis_client is not None:
        await _redis_client.disconnect()
        _redis_client = None
