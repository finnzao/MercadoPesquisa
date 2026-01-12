"""
Módulo de serviços - Camada de orquestração.

Contém a lógica de negócio que coordena:
- Cache
- Rate limiting
- Circuit breakers
- Fan-out para scrapers
- Processamento de resultados
"""

from src.services.cache_service import (
    CacheService,
    RateLimiter,
    RedisClient,
    get_cache_service,
    get_rate_limiter,
)
from src.services.search_service import (
    SearchService,
    SearchRequest,
    SearchResponse,
    CircuitBreaker,
    CircuitState,
    get_search_service,
)

__all__ = [
    # Cache
    "CacheService",
    "RateLimiter",
    "RedisClient",
    "get_cache_service",
    "get_rate_limiter",
    # Search
    "SearchService",
    "SearchRequest",
    "SearchResponse",
    "CircuitBreaker",
    "CircuitState",
    "get_search_service",
]
