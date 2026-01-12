"""
Router principal da API v1.

Agrupa todos os routers de endpoints.
"""

from fastapi import APIRouter

from src.api.v1.search import router as search_router
from src.api.v1.markets import router as markets_router
from src.api.v1.shopping import router as shopping_router

api_router = APIRouter()

# Endpoints de busca
api_router.include_router(
    search_router,
    prefix="/search",
    tags=["Busca"],
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
