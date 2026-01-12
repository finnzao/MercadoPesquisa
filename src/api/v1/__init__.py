"""API v1 routers."""

from .router import api_router
from .search import router as search_router
from .markets import router as markets_router
from .shopping import router as shopping_router

__all__ = [
    "api_router",
    "search_router",
    "markets_router",
    "shopping_router",
]
