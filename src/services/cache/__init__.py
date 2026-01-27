# src/services/cache/__init__.py
"""
Módulo de Cache com TTL Dinâmico e Rate Limiting.

Componentes principais:
- DynamicTTLCalculator: Calcula TTL baseado em período, dia, mercado, etc.
- CacheService: Serviço principal com cache L1 (memória) e L2 (Redis)
- LRUCache: Implementação de cache LRU em memória
- RedisClient: Cliente Redis singleton
- RateLimiter: Rate limiting com sliding window

Exemplo de uso:
    from src.services.cache import (
        init_cache_service,
        get_cache_service,
        get_rate_limiter,
    )
    
    # No startup da aplicação
    cache = await init_cache_service(redis_url="redis://localhost:6379")
    
    # Em qualquer lugar
    cache = await get_cache_service()
    result = await cache.get("minha_chave")
    
    # Rate limiting
    limiter = await get_rate_limiter()
    result = await limiter.check_user("user123")
    if not result.allowed:
        raise HTTPException(429, "Rate limit excedido")
"""

# TTL Dinâmico
from .dynamic_ttl import (
    DynamicTTLCalculator,
    TTLConfig,
    TimePeriod,
)

# Cache Service
from .cache_service import (
    CacheService,
    CacheEntry,
    CacheStats,
    LRUCache,
    get_cache_service,
    init_cache_service,
)

# Redis Client
from .redis_client import (
    RedisClient,
    get_redis_client,
    close_redis_client,
)

# Rate Limiter
from .rate_limiter import (
    RateLimiter,
    RateLimitConfig,
    RateLimitResult,
    RateLimitType,
    get_rate_limiter,
    reset_rate_limiter,
)

__all__ = [
    # TTL Dinâmico
    "DynamicTTLCalculator",
    "TTLConfig",
    "TimePeriod",
    
    # Cache Service
    "CacheService",
    "CacheEntry",
    "CacheStats",
    "LRUCache",
    "get_cache_service",
    "init_cache_service",
    
    # Redis Client
    "RedisClient",
    "get_redis_client",
    "close_redis_client",
    
    # Rate Limiter
    "RateLimiter",
    "RateLimitConfig",
    "RateLimitResult",
    "RateLimitType",
    "get_rate_limiter",
    "reset_rate_limiter",
]

__version__ = "1.0.0"
