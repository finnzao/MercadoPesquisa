"""
Router principal da API v1.

Agrupa todos os routers de endpoints.
"""

from fastapi import APIRouter

from src.api.v1.search import router as search_router
from src.api.v1.search_fast import router as search_fast_router
from src.api.v1.multi_search import router as multi_search_router
from src.api.v1.markets import router as markets_router
from src.api.v1.shopping import router as shopping_router

api_router = APIRouter()

# Endpoints de busca simples
api_router.include_router(
    search_router,
    prefix="/search",
    tags=["Busca"],
)

# Endpoints de busca rápida
api_router.include_router(
    search_fast_router,
    prefix="/search",
    tags=["Busca Rápida"],
)

# Endpoints de busca múltipla
api_router.include_router(
    multi_search_router,
    prefix="/search",
    tags=["Busca Múltipla"],
)

# Endpoints de mercados
api_router.include_router(
    markets_router,
    prefix="/markets",
    tags=["Mercados"],
)

# Endpoints de lista de compras
api_router.include_router(
    shopping_router,
    prefix="/shopping",
    tags=["Lista de Compras"],
)
