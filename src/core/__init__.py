"""
Módulo core: modelos de dados, exceções, tipos e constantes.
"""

from src.core.models import (
    RawProduct,
    NormalizedProduct,
    PriceOffer,
    SearchResult,
    CollectionMetadata,
)
from src.core.exceptions import (
    PriceCollectorError,
    ScraperError,
    ParsingError,
    NormalizationError,
    StorageError,
    RateLimitError,
    BlockedError,
    NetworkError,
)
from src.core.types import (
    Unit,
    Availability,
    MarketID,
    CEP,
)
from src.core.constants import (
    UNIT_CONVERSIONS,
    QUANTITY_PATTERNS,
    PRICE_PATTERNS,
)

__all__ = [
    # Models
    "RawProduct",
    "NormalizedProduct",
    "PriceOffer",
    "SearchResult",
    "CollectionMetadata",
    # Exceptions
    "PriceCollectorError",
    "ScraperError",
    "ParsingError",
    "NormalizationError",
    "StorageError",
    "RateLimitError",
    "BlockedError",
    "NetworkError",
    # Types
    "Unit",
    "Availability",
    "MarketID",
    "CEP",
    # Constants
    "UNIT_CONVERSIONS",
    "QUANTITY_PATTERNS",
    "PRICE_PATTERNS",
]