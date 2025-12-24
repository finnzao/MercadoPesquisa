"""
Tipos customizados e enumerações do sistema.
"""

from enum import Enum
from typing import Annotated, Literal

from pydantic import Field, StringConstraints


# ENUMERAÇÕES

class Unit(str, Enum):
    """Unidades de medida suportadas."""
    
    # Massa
    KILOGRAM = "kg"
    GRAM = "g"
    MILLIGRAM = "mg"
    
    # Volume
    LITER = "L"
    MILLILITER = "ml"
    
    # Unidade
    UNIT = "un"
    PACK = "pack"
    DOZEN = "dz"
    
    # Especiais
    UNKNOWN = "unknown"
    
    @classmethod
    def base_units(cls) -> list["Unit"]:
        """Retorna unidades base para normalização."""
        return [cls.KILOGRAM, cls.LITER, cls.UNIT]
    
    @classmethod
    def mass_units(cls) -> list["Unit"]:
        """Retorna unidades de massa."""
        return [cls.KILOGRAM, cls.GRAM, cls.MILLIGRAM]
    
    @classmethod
    def volume_units(cls) -> list["Unit"]:
        """Retorna unidades de volume."""
        return [cls.LITER, cls.MILLILITER]
    
    def get_base_unit(self) -> "Unit":
        """Retorna a unidade base correspondente."""
        if self in self.mass_units():
            return Unit.KILOGRAM
        elif self in self.volume_units():
            return Unit.LITER
        else:
            return Unit.UNIT


class Availability(str, Enum):
    """Status de disponibilidade do produto."""
    
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    LOW_STOCK = "low_stock"
    PRE_ORDER = "pre_order"
    UNKNOWN = "unknown"
    
    @classmethod
    def from_text(cls, text: str | None) -> "Availability":
        """Infere disponibilidade a partir de texto."""
        if not text:
            return cls.UNKNOWN
        
        text_lower = text.lower().strip()
        
        unavailable_keywords = [
            "indisponível", "esgotado", "sem estoque",
            "unavailable", "out of stock", "sold out",
        ]
        low_stock_keywords = [
            "últimas unidades", "poucas unidades",
            "restam poucos", "low stock",
        ]
        available_keywords = [
            "disponível", "em estoque", "adicionar",
            "comprar", "available", "in stock", "add to cart",
        ]
        
        for keyword in unavailable_keywords:
            if keyword in text_lower:
                return cls.UNAVAILABLE
        
        for keyword in low_stock_keywords:
            if keyword in text_lower:
                return cls.LOW_STOCK
        
        for keyword in available_keywords:
            if keyword in text_lower:
                return cls.AVAILABLE
        
        return cls.UNKNOWN


class NormalizationStatus(str, Enum):
    """Status da normalização do produto."""
    
    SUCCESS = "success"           # Normalização completa
    PARTIAL = "partial"           # Normalização parcial (sem quantidade)
    FAILED = "failed"             # Falha na normalização
    NOT_APPLICABLE = "n/a"        # Não aplicável


class CollectionStatus(str, Enum):
    """Status da coleta de um mercado."""
    
    SUCCESS = "success"
    PARTIAL = "partial"           # Alguns produtos coletados
    FAILED = "failed"
    TIMEOUT = "timeout"
    BLOCKED = "blocked"
    NO_RESULTS = "no_results"


# TIPOS ANOTADOS

# CEP brasileiro (8 dígitos)
CEP = Annotated[
    str,
    StringConstraints(
        pattern=r"^\d{8}$",
        strip_whitespace=True,
    ),
]

# IDs de mercados suportados
MarketID = Literal["carrefour", "atacadao", "pao_acucar", "extra"]

# Preço (sempre positivo)
Price = Annotated[float, Field(ge=0)]

# Quantidade (sempre positiva)
Quantity = Annotated[float, Field(gt=0)]

# URL validada
URLString = Annotated[
    str,
    StringConstraints(
        pattern=r"^https?://.*",
        strip_whitespace=True,
    ),
]

# Query de busca
SearchQuery = Annotated[
    str,
    StringConstraints(
        min_length=2,
        max_length=200,
        strip_whitespace=True,
    ),
]