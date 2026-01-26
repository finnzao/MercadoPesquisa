"""
Componentes principais:
- DynamicTTLCalculator: Calcula TTL baseado em período, dia, mercado, etc.
- CacheService: Serviço principal com cache L1 (memória) e L2 (Redis)
- LRUCache: Implementação de cache LRU em memória
"""

from .dynamic_ttl import (
    DynamicTTLCalculator,
    TTLConfig,
    TimePeriod,
)

from .cache_service import (
    CacheService,
    CacheEntry,
    CacheStats,
    LRUCache,
    get_cache_service,
    init_cache_service,
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
]

__version__ = "1.0.0"
