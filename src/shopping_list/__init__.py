"""
Módulo de Lista de Compras.
Permite processar uma lista de itens e encontrar o melhor preço para cada um.
"""

from src.shopping_list.models import (
    ShoppingItem,
    ShoppingListResult,
    ItemResult,
    MarketSummary,
)
from src.shopping_list.processor import ShoppingListProcessor
from src.shopping_list.formatter import ResultFormatter

__all__ = [
    "ShoppingItem",
    "ShoppingListResult",
    "ItemResult",
    "MarketSummary",
    "ShoppingListProcessor",
    "ResultFormatter",
]