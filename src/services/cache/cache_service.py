# src/services/cache/cache_service.py
"""
Serviço de Cache com TTL Dinâmico.

Implementa cache em duas camadas (L1 em memória, L2 em Redis) com TTL
calculado dinamicamente baseado em múltiplos fatores.
"""

import asyncio
import json
import hashlib
from datetime import datetime, timedelta
from typing import Any, Optional, List
from dataclasses import dataclass
from collections import OrderedDict

import structlog

from .dynamic_ttl import DynamicTTLCalculator, TTLConfig
from .redis_client import RedisClient, get_redis_client

logger = structlog.get_logger()


@dataclass
class CacheEntry:
    """Entrada individual do cache."""
    value: Any
    created_at: datetime
    expires_at: datetime
    ttl_seconds: int
    market_id: Optional[str] = None
    is_promotional: bool = False
    hit_count: int = 0
    
    def is_expired(self) -> bool:
        """Verifica se a entrada expirou."""
        return datetime.now() >= self.expires_at
    
    def remaining_ttl(self) -> int:
        """Retorna TTL restante em segundos."""
        remaining = (self.expires_at - datetime.now()).total_seconds()
        return max(0, int(remaining))


@dataclass
class CacheStats:
    """Estatísticas do cache."""
    l1_hits: int = 0
    l1_misses: int = 0
    l2_hits: int = 0
    l2_misses: int = 0
    total_sets: int = 0
    total_deletes: int = 0
    evictions: int = 0
    
    @property
    def l1_hit_rate(self) -> float:
        total = self.l1_hits + self.l1_misses
        return (self.l1_hits / total * 100) if total > 0 else 0.0
    
    @property
    def l2_hit_rate(self) -> float:
        total = self.l2_hits + self.l2_misses
        return (self.l2_hits / total * 100) if total > 0 else 0.0
    
    def to_dict(self) -> dict:
        return {
            "l1": {
                "hits": self.l1_hits,
                "misses": self.l1_misses,
                "hit_rate": f"{self.l1_hit_rate:.1f}%"
            },
            "l2": {
                "hits": self.l2_hits,
                "misses": self.l2_misses,
                "hit_rate": f"{self.l2_hit_rate:.1f}%"
            },
            "total_sets": self.total_sets,
            "total_deletes": self.total_deletes,
            "evictions": self.evictions
        }


class LRUCache:
    """
    Cache LRU (Least Recently Used) em memória.
    
    Implementa ordenação por acesso recente, removendo automaticamente
    os itens menos acessados quando atinge o limite.
    """
    
    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = asyncio.Lock()
    
    async def get(self, key: str) -> Optional[CacheEntry]:
        """
        Busca entrada no cache.
        Move para o final (mais recente) se encontrar.
        """
        async with self._lock:
            if key not in self._cache:
                return None
            
            entry = self._cache[key]
            
            # Verifica expiração
            if entry.is_expired():
                del self._cache[key]
                return None
            
            # Move para o final (mais recente)
            self._cache.move_to_end(key)
            entry.hit_count += 1
            
            return entry
    
    async def set(self, key: str, entry: CacheEntry) -> bool:
        """
        Adiciona ou atualiza entrada no cache.
        Remove entradas antigas se necessário.
        """
        async with self._lock:
            # Se já existe, atualiza
            if key in self._cache:
                self._cache[key] = entry
                self._cache.move_to_end(key)
                return True
            
            # Verifica limite e remove mais antigos se necessário
            evicted = 0
            while len(self._cache) >= self.max_size:
                self._cache.popitem(last=False)  # Remove o primeiro (mais antigo)
                evicted += 1
            
            self._cache[key] = entry
            return evicted > 0  # Retorna True se houve eviction
    
    async def delete(self, key: str) -> bool:
        """Remove entrada do cache."""
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
    
    async def delete_pattern(self, pattern: str) -> int:
        """
        Remove todas as entradas que correspondem ao padrão.
        Suporta * como wildcard.
        
        Exemplo: "search:arroz:*" remove todas as buscas de arroz
        """
        async with self._lock:
            import fnmatch
            keys_to_delete = [
                k for k in self._cache.keys() 
                if fnmatch.fnmatch(k, pattern)
            ]
            
            for key in keys_to_delete:
                del self._cache[key]
            
            return len(keys_to_delete)
    
    async def clear(self):
        """Limpa todo o cache."""
        async with self._lock:
            self._cache.clear()
    
    async def cleanup_expired(self) -> int:
        """Remove todas as entradas expiradas."""
        async with self._lock:
            expired_keys = [
                k for k, v in self._cache.items() 
                if v.is_expired()
            ]
            
            for key in expired_keys:
                del self._cache[key]
            
            return len(expired_keys)
    
    def size(self) -> int:
        """Retorna número de entradas no cache."""
        return len(self._cache)
    
    def keys(self) -> List[str]:
        """Retorna lista de chaves."""
        return list(self._cache.keys())


class CacheService:
    """
    Serviço de cache com duas camadas e TTL dinâmico.
    
    Camadas:
    - L1 (memória): Cache LRU local, ultra-rápido (~0.1ms)
    - L2 (Redis): Cache distribuído, compartilhado entre instâncias (~1-5ms)
    
    O TTL é calculado dinamicamente baseado em:
    - Período do dia
    - Dia da semana
    - Mercado específico
    - Se há itens promocionais
    - Popularidade da busca
    """
    
    def __init__(
        self,
        redis_url: Optional[str] = None,
        redis_password: Optional[str] = None,
        l1_max_size: int = 1000,
        l1_default_ttl: int = 60,
        l2_default_ttl: int = 300,
        ttl_config: Optional[TTLConfig] = None,
        cache_prefix: str = "preco:",
    ):
        """
        Inicializa o serviço de cache.
        
        Args:
            redis_url: URL de conexão do Redis (None = apenas L1)
            redis_password: Senha do Redis
            l1_max_size: Tamanho máximo do cache L1
            l1_default_ttl: TTL padrão do L1 em segundos
            l2_default_ttl: TTL padrão do L2 em segundos
            ttl_config: Configurações customizadas de TTL dinâmico
            cache_prefix: Prefixo para chaves no Redis
        """
        self.redis_url = redis_url
        self.redis_password = redis_password
        self.l1_default_ttl = l1_default_ttl
        self.l2_default_ttl = l2_default_ttl
        self.cache_prefix = cache_prefix
        
        # Cache L1 (memória)
        self._l1 = LRUCache(max_size=l1_max_size)
        
        # Cache L2 (Redis)
        self._redis: Optional[RedisClient] = None
        
        # Calculador de TTL dinâmico
        self._ttl_calculator = DynamicTTLCalculator(config=ttl_config)
        
        # Estatísticas
        self._stats = CacheStats()
        
        # Task de limpeza em background
        self._cleanup_task: Optional[asyncio.Task] = None
    
    async def initialize(self):
        """Inicializa conexões e tasks em background."""
        # Tenta conectar ao Redis
        if self.redis_url:
            try:
                self._redis = await get_redis_client(
                    redis_url=self.redis_url,
                    redis_password=self.redis_password,
                    cache_prefix=self.cache_prefix,
                )
                logger.info(
                    "cache_service_redis_connected",
                    url=self.redis_url,
                )
            except Exception as e:
                logger.warning(
                    "cache_service_redis_failed",
                    error=str(e),
                    message="Usando apenas cache L1",
                )
                self._redis = None
        
        # Inicia task de limpeza periódica
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
        
        logger.info(
            "cache_service_initialized",
            l1_max_size=self._l1.max_size,
            l2_available=self._redis is not None and self._redis.is_connected,
        )
    
    async def close(self):
        """Fecha conexões e para tasks."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        # Nota: não fechamos o redis_client aqui pois é compartilhado
        logger.info("cache_service_closed")
    
    def _generate_cache_key(
        self,
        query: str,
        cep: Optional[str] = None,
        market_ids: Optional[List[str]] = None,
    ) -> str:
        """
        Gera chave única para cache baseada nos parâmetros de busca.
        
        Formato: search:{hash}
        Onde hash é gerado a partir de query + cep + markets ordenados
        """
        parts = [query.lower().strip()]
        
        if cep:
            parts.append(cep)
        
        if market_ids:
            parts.append(":".join(sorted(market_ids)))
        
        key_content = "|".join(parts)
        key_hash = hashlib.md5(key_content.encode()).hexdigest()[:12]
        
        return f"search:{key_hash}"
    
    async def get(self, key: str) -> Optional[Any]:
        """
        Busca valor no cache.
        
        Fluxo:
        1. Verifica L1 (memória)
        2. Se não encontrar, verifica L2 (Redis)
        3. Se encontrar em L2, popula L1
        
        Args:
            key: Chave do cache
            
        Returns:
            Valor armazenado ou None se não encontrar
        """
        # 1. Tenta L1
        entry = await self._l1.get(key)
        if entry:
            self._stats.l1_hits += 1
            logger.debug("cache_l1_hit", key=key, ttl_remaining=entry.remaining_ttl())
            return entry.value
        
        self._stats.l1_misses += 1
        
        # 2. Tenta L2 (Redis)
        if self._redis and self._redis.is_connected:
            try:
                data = await self._redis.get(key)
                if data:
                    self._stats.l2_hits += 1
                    value = json.loads(data)
                    
                    # Popula L1 com TTL menor
                    l1_ttl = min(self.l1_default_ttl, 60)
                    await self._set_l1(key, value, l1_ttl)
                    
                    logger.debug("cache_l2_hit", key=key)
                    return value
                
                self._stats.l2_misses += 1
            except Exception as e:
                logger.error("cache_l2_get_error", key=key, error=str(e))
                self._stats.l2_misses += 1
        
        logger.debug("cache_miss", key=key)
        return None
    
    async def set(
        self,
        key: str,
        value: Any,
        market_id: Optional[str] = None,
        market_ids: Optional[List[str]] = None,
        is_promotional: bool = False,
        query_popularity: float = 0.0,
        custom_ttl: Optional[int] = None,
    ) -> bool:
        """
        Armazena valor no cache com TTL dinâmico.
        
        Args:
            key: Chave do cache
            value: Valor a armazenar
            market_id: ID de um mercado específico
            market_ids: Lista de IDs de mercados (usa o menor TTL)
            is_promotional: Se contém itens promocionais
            query_popularity: Popularidade da busca (0.0 a 1.0)
            custom_ttl: TTL customizado (sobrescreve cálculo dinâmico)
            
        Returns:
            True se armazenou com sucesso
        """
        # Calcula TTL dinâmico
        if custom_ttl is not None:
            ttl = custom_ttl
        elif market_ids:
            ttl = self._ttl_calculator.calculate_ttl_for_search(
                query="",
                market_ids=market_ids,
                has_promotional_items=is_promotional,
                query_popularity=query_popularity,
            )
        else:
            ttl = self._ttl_calculator.calculate_ttl(
                market_id=market_id,
                is_promotional=is_promotional,
                query_popularity=query_popularity,
            )
        
        # Log do TTL calculado
        ttl_info = self._ttl_calculator.get_ttl_info(
            market_id=market_id or (market_ids[0] if market_ids else None),
            is_promotional=is_promotional,
            query_popularity=query_popularity,
        )
        
        logger.debug(
            "cache_ttl_calculated",
            key=key,
            ttl_seconds=ttl,
            ttl_info=ttl_info,
        )
        
        self._stats.total_sets += 1
        
        # Armazena em L1
        l1_ttl = min(ttl, self.l1_default_ttl * 2)  # L1 tem TTL limitado
        evicted = await self._set_l1(
            key=key,
            value=value,
            ttl=l1_ttl,
            market_id=market_id,
            is_promotional=is_promotional,
        )
        
        if evicted:
            self._stats.evictions += 1
        
        # Armazena em L2 (Redis)
        if self._redis and self._redis.is_connected:
            try:
                serialized = json.dumps(value, default=str)
                await self._redis.set(key, serialized, ttl=ttl)
                logger.debug("cache_l2_set", key=key, ttl=ttl)
            except Exception as e:
                logger.error("cache_l2_set_error", key=key, error=str(e))
        
        return True
    
    async def _set_l1(
        self,
        key: str,
        value: Any,
        ttl: int,
        market_id: Optional[str] = None,
        is_promotional: bool = False,
    ) -> bool:
        """Armazena valor no cache L1."""
        now = datetime.now()
        entry = CacheEntry(
            value=value,
            created_at=now,
            expires_at=now + timedelta(seconds=ttl),
            ttl_seconds=ttl,
            market_id=market_id,
            is_promotional=is_promotional,
        )
        return await self._l1.set(key, entry)
    
    async def delete(self, key: str) -> bool:
        """
        Remove valor do cache (ambas camadas).
        
        Args:
            key: Chave do cache
            
        Returns:
            True se removeu de pelo menos uma camada
        """
        self._stats.total_deletes += 1
        
        l1_deleted = await self._l1.delete(key)
        l2_deleted = False
        
        if self._redis and self._redis.is_connected:
            try:
                l2_deleted = await self._redis.delete(key)
            except Exception as e:
                logger.error("cache_l2_delete_error", key=key, error=str(e))
        
        logger.debug("cache_deleted", key=key, l1=l1_deleted, l2=l2_deleted)
        return l1_deleted or l2_deleted
    
    async def delete_pattern(self, pattern: str) -> int:
        """
        Remove todas as chaves que correspondem ao padrão.
        
        Args:
            pattern: Padrão com wildcard * (ex: "search:arroz:*")
            
        Returns:
            Número de chaves removidas
        """
        deleted = 0
        
        # Remove de L1
        deleted += await self._l1.delete_pattern(pattern)
        
        # Remove de L2
        if self._redis and self._redis.is_connected:
            try:
                deleted += await self._redis.delete_pattern(pattern)
            except Exception as e:
                logger.error("cache_pattern_delete_error", pattern=pattern, error=str(e))
        
        logger.info("cache_pattern_deleted", pattern=pattern, count=deleted)
        return deleted
    
    async def invalidate_market(self, market_id: str) -> int:
        """
        Invalida todo o cache de um mercado específico.
        Útil quando detectamos que o mercado atualizou preços.
        
        Args:
            market_id: ID do mercado
            
        Returns:
            Número de entradas invalidadas
        """
        pattern = f"*:{market_id}:*"
        deleted = await self.delete_pattern(pattern)
        
        logger.info("market_cache_invalidated", market_id=market_id, count=deleted)
        return deleted
    
    async def clear(self):
        """Limpa todo o cache (ambas camadas)."""
        await self._l1.clear()
        
        if self._redis and self._redis.is_connected:
            try:
                await self._redis.flush_db()
            except Exception as e:
                logger.error("cache_clear_error", error=str(e))
        
        # Reseta estatísticas
        self._stats = CacheStats()
        
        logger.info("cache_cleared")
    
    async def _periodic_cleanup(self):
        """Task que limpa entradas expiradas periodicamente."""
        while True:
            try:
                await asyncio.sleep(60)  # A cada 1 minuto
                
                expired_count = await self._l1.cleanup_expired()
                if expired_count > 0:
                    logger.debug("cache_cleanup", expired_removed=expired_count)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("cache_cleanup_error", error=str(e))
    
    def get_stats(self) -> dict:
        """Retorna estatísticas do cache."""
        return {
            **self._stats.to_dict(),
            "l1_size": self._l1.size(),
            "l1_max_size": self._l1.max_size,
            "l2_available": self._redis is not None and self._redis.is_connected,
        }
    
    def get_ttl_calculator(self) -> DynamicTTLCalculator:
        """Retorna o calculador de TTL para uso externo."""
        return self._ttl_calculator
    

    # Métodos de conveniência para buscas

    
    async def get_search_result(
        self,
        query: str,
        cep: Optional[str] = None,
        markets: Optional[List[str]] = None,
    ) -> Optional[dict]:
        """
        Obtém resultado de busca do cache.
        
        Args:
            query: Termo de busca
            cep: CEP do usuário
            markets: Lista de mercados
            
        Returns:
            Resultado cacheado ou None
        """
        key = self._generate_cache_key(query, cep, markets)
        return await self.get(key)
    
    async def set_search_result(
        self,
        query: str,
        result: dict,
        cep: Optional[str] = None,
        markets: Optional[List[str]] = None,
        is_promotional: bool = False,
        query_popularity: float = 0.0,
    ) -> bool:
        """
        Armazena resultado de busca no cache.
        
        Args:
            query: Termo de busca
            result: Resultado a armazenar
            cep: CEP do usuário
            markets: Lista de mercados
            is_promotional: Se há itens promocionais
            query_popularity: Popularidade da busca
            
        Returns:
            True se armazenou com sucesso
        """
        key = self._generate_cache_key(query, cep, markets)
        return await self.set(
            key=key,
            value=result,
            market_ids=markets,
            is_promotional=is_promotional,
            query_popularity=query_popularity,
        )


# Singleton para uso global

_cache_service: Optional[CacheService] = None


async def get_cache_service() -> CacheService:
    """Retorna instância global do cache service."""
    global _cache_service
    
    if _cache_service is None:
        raise RuntimeError(
            "CacheService não inicializado. Chame init_cache_service primeiro."
        )
    
    return _cache_service


async def init_cache_service(
    redis_url: Optional[str] = None,
    redis_password: Optional[str] = None,
    **kwargs,
) -> CacheService:
    """
    Inicializa o cache service global.
    
    Args:
        redis_url: URL do Redis
        redis_password: Senha do Redis
        **kwargs: Argumentos adicionais para CacheService
        
    Returns:
        Instância do CacheService
    """
    global _cache_service
    
    _cache_service = CacheService(
        redis_url=redis_url,
        redis_password=redis_password,
        **kwargs,
    )
    await _cache_service.initialize()
    
    return _cache_service


async def close_cache_service() -> None:
    """Fecha o cache service global."""
    global _cache_service
    
    if _cache_service is not None:
        await _cache_service.close()
        _cache_service = None
