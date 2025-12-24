"""
Modelos de dados Pydantic para o sistema.
Define estruturas para produtos brutos, normalizados e ofertas.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

from src.core.types import (
    Availability,
    CEP,
    MarketID,
    NormalizationStatus,
    Unit,
)


class RawProduct(BaseModel):
    """
    Produto bruto extraído do scraper.
    Contém dados exatamente como vieram do site.
    """
    
    # Identificação
    market_id: MarketID
    external_id: Optional[str] = None
    
    # Dados extraídos
    title: str = Field(..., min_length=1, max_length=500)
    price_raw: str = Field(..., description="Preço como string original")
    unit_price_raw: Optional[str] = None
    
    # Metadados
    url: str
    image_url: Optional[str] = None
    availability_raw: Optional[str] = None
    description: Optional[str] = None
    
    # Contexto de coleta
    search_query: str
    cep: Optional[str] = None
    collected_at: datetime = Field(default_factory=datetime.now)
    
    # Dados adicionais do site
    extra_data: dict[str, Any] = Field(default_factory=dict)
    
    @field_validator("title")
    @classmethod
    def clean_title(cls, v: str) -> str:
        """Remove espaços extras do título."""
        return " ".join(v.split())
    
    @field_validator("price_raw")
    @classmethod
    def validate_price_raw(cls, v: str) -> str:
        """Valida que o preço contém dígitos."""
        if not any(c.isdigit() for c in v):
            raise ValueError("Preço deve conter ao menos um dígito")
        return v.strip()


class QuantityInfo(BaseModel):
    """Informação de quantidade extraída e normalizada."""
    
    # Valores extraídos
    value: float = Field(..., gt=0)
    unit: Unit
    
    # Valores normalizados para unidade base
    base_value: float = Field(..., gt=0)
    base_unit: Unit
    
    # Multiplicador (para packs)
    multiplier: int = Field(default=1, ge=1)
    
    # Rastreabilidade
    raw_text: str = Field(..., description="Texto original de onde foi extraído")
    extraction_pattern: Optional[str] = None
    
    @computed_field
    @property
    def total_base_value(self) -> float:
        """Valor total considerando multiplicador."""
        return self.base_value * self.multiplier


class NormalizedProduct(BaseModel):
    """
    Produto com dados normalizados e validados.
    Pronto para cálculo de preço por unidade.
    """
    
    # ID único
    id: UUID = Field(default_factory=uuid4)
    
    # Dados do produto
    market_id: MarketID
    market_name: str
    title: str
    
    # Preço
    price: Decimal = Field(..., ge=0, decimal_places=2)
    
    # Quantidade (pode ser None se não extraída)
    quantity: Optional[QuantityInfo] = None
    
    # Status
    normalization_status: NormalizationStatus
    availability: Availability = Availability.UNKNOWN
    
    # URLs
    url: str
    image_url: Optional[str] = None
    
    # Contexto
    search_query: str
    cep: Optional[str] = None
    collected_at: datetime
    
    # Produto bruto original
    raw_product: Optional[RawProduct] = Field(default=None, exclude=True)
    
    @model_validator(mode="after")
    def validate_normalization_status(self):
        """Valida consistência do status de normalização."""
        if self.quantity is None and self.normalization_status == NormalizationStatus.SUCCESS:
            self.normalization_status = NormalizationStatus.PARTIAL
        return self
    
    @computed_field
    @property
    def has_quantity(self) -> bool:
        """Indica se a quantidade foi extraída."""
        return self.quantity is not None


class PriceOffer(BaseModel):
    """
    Oferta final com preço normalizado por unidade.
    Estrutura principal para comparação de preços.
    """
    
    # ID único
    id: UUID = Field(default_factory=uuid4)
    
    # Identificação do mercado
    market_id: MarketID
    market_name: str
    
    # Dados do produto
    title: str
    url: str
    image_url: Optional[str] = None
    
    # Preço original
    price: Decimal = Field(..., ge=0, decimal_places=2)
    
    # Quantidade
    quantity_value: Optional[float] = Field(default=None, gt=0)
    quantity_unit: Optional[Unit] = None
    
    # Preço normalizado
    normalized_price: Optional[Decimal] = Field(default=None, ge=0, decimal_places=2)
    normalized_unit: Optional[Unit] = None
    price_display: str = Field(..., description="Ex: R$ 25,99/kg")
    
    # Status
    availability: Availability
    normalization_status: NormalizationStatus
    
    # Metadados de coleta
    search_query: str
    cep: Optional[str] = None
    collected_at: datetime
    
    class Config:
        json_encoders = {
            Decimal: lambda v: float(v),
            UUID: lambda v: str(v),
            datetime: lambda v: v.isoformat(),
        }
    
    @computed_field
    @property
    def is_comparable(self) -> bool:
        """Indica se o produto pode ser comparado (tem preço normalizado)."""
        return (
            self.normalized_price is not None 
            and self.normalization_status == NormalizationStatus.SUCCESS
        )
    
    def format_price(self) -> str:
        """Formata preço para exibição."""
        return f"R$ {self.price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    
    def format_normalized_price(self) -> str:
        """Formata preço normalizado para exibição."""
        if self.normalized_price is None or self.normalized_unit is None:
            return "N/A"
        price_str = f"R$ {self.normalized_price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{price_str}/{self.normalized_unit.value}"


class CollectionMetadata(BaseModel):
    """Metadados de uma sessão de coleta."""
    
    # Identificação
    collection_id: UUID = Field(default_factory=uuid4)
    
    # Parâmetros da busca
    search_query: str
    cep: Optional[str] = None
    markets_requested: list[MarketID]
    
    # Timestamps
    started_at: datetime = Field(default_factory=datetime.now)
    finished_at: Optional[datetime] = None
    
    # Resultados por mercado
    results_per_market: dict[MarketID, int] = Field(default_factory=dict)
    errors_per_market: dict[MarketID, str] = Field(default_factory=dict)
    
    # Totais
    total_products: int = 0
    total_normalized: int = 0
    total_errors: int = 0
    
    @computed_field
    @property
    def duration_seconds(self) -> Optional[float]:
        """Duração da coleta em segundos."""
        if self.finished_at is None:
            return None
        return (self.finished_at - self.started_at).total_seconds()
    
    def mark_finished(self):
        """Marca a coleta como finalizada."""
        self.finished_at = datetime.now()


class SearchResult(BaseModel):
    """Resultado completo de uma busca."""
    
    # Metadados
    metadata: CollectionMetadata
    
    # Ofertas
    offers: list[PriceOffer] = Field(default_factory=list)
    
    @computed_field
    @property
    def total_offers(self) -> int:
        """Total de ofertas encontradas."""
        return len(self.offers)
    
    @computed_field
    @property
    def comparable_offers(self) -> int:
        """Total de ofertas comparáveis (com preço normalizado)."""
        return sum(1 for o in self.offers if o.is_comparable)
    
    def get_best_offer(self) -> Optional[PriceOffer]:
        """Retorna a melhor oferta (menor preço normalizado)."""
        comparable = [o for o in self.offers if o.is_comparable]
        if not comparable:
            return None
        return min(comparable, key=lambda o: o.normalized_price or Decimal("inf"))
    
    def get_offers_by_market(self, market_id: MarketID) -> list[PriceOffer]:
        """Retorna ofertas de um mercado específico."""
        return [o for o in self.offers if o.market_id == market_id]
    
    def sort_by_price(self, ascending: bool = True) -> list[PriceOffer]:
        """Retorna ofertas ordenadas por preço normalizado."""
        comparable = [o for o in self.offers if o.is_comparable]
        non_comparable = [o for o in self.offers if not o.is_comparable]
        
        sorted_comparable = sorted(
            comparable,
            key=lambda o: o.normalized_price or Decimal("inf"),
            reverse=not ascending,
        )
        
        return sorted_comparable + non_comparable
"""
Modelos de dados Pydantic para o sistema.
Define estruturas para produtos brutos, normalizados e ofertas.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

from src.core.types import (
    Availability,
    CEP,
    MarketID,
    NormalizationStatus,
    Unit,
)


class RawProduct(BaseModel):
    """
    Produto bruto extraído do scraper.
    Contém dados exatamente como vieram do site.
    """
    
    # Identificação
    market_id: MarketID
    external_id: Optional[str] = None
    
    # Dados extraídos
    title: str = Field(..., min_length=1, max_length=500)
    price_raw: str = Field(..., description="Preço como string original")
    unit_price_raw: Optional[str] = None
    
    # Metadados
    url: str
    image_url: Optional[str] = None
    availability_raw: Optional[str] = None
    description: Optional[str] = None
    
    # Contexto de coleta
    search_query: str
    cep: Optional[str] = None
    collected_at: datetime = Field(default_factory=datetime.now)
    
    # Dados adicionais do site
    extra_data: dict[str, Any] = Field(default_factory=dict)
    
    @field_validator("title")
    @classmethod
    def clean_title(cls, v: str) -> str:
        """Remove espaços extras do título."""
        return " ".join(v.split())
    
    @field_validator("price_raw")
    @classmethod
    def validate_price_raw(cls, v: str) -> str:
        """Valida que o preço contém dígitos."""
        if not any(c.isdigit() for c in v):
            raise ValueError("Preço deve conter ao menos um dígito")
        return v.strip()


class QuantityInfo(BaseModel):
    """Informação de quantidade extraída e normalizada."""
    
    # Valores extraídos
    value: float = Field(..., gt=0)
    unit: Unit
    
    # Valores normalizados para unidade base
    base_value: float = Field(..., gt=0)
    base_unit: Unit
    
    # Multiplicador (para packs)
    multiplier: int = Field(default=1, ge=1)
    
    # Rastreabilidade
    raw_text: str = Field(..., description="Texto original de onde foi extraído")
    extraction_pattern: Optional[str] = None
    
    @computed_field
    @property
    def total_base_value(self) -> float:
        """Valor total considerando multiplicador."""
        return self.base_value * self.multiplier


class NormalizedProduct(BaseModel):
    """
    Produto com dados normalizados e validados.
    Pronto para cálculo de preço por unidade.
    """
    
    # ID único
    id: UUID = Field(default_factory=uuid4)
    
    # Dados do produto
    market_id: MarketID
    market_name: str
    title: str
    
    # Preço
    price: Decimal = Field(..., ge=0, decimal_places=2)
    
    # Quantidade (pode ser None se não extraída)
    quantity: Optional[QuantityInfo] = None
    
    # Status
    normalization_status: NormalizationStatus
    availability: Availability = Availability.UNKNOWN
    
    # URLs
    url: str
    image_url: Optional[str] = None
    
    # Contexto
    search_query: str
    cep: Optional[str] = None
    collected_at: datetime
    
    # Produto bruto original
    raw_product: Optional[RawProduct] = Field(default=None, exclude=True)
    
    @model_validator(mode="after")
    def validate_normalization_status(self):
        """Valida consistência do status de normalização."""
        if self.quantity is None and self.normalization_status == NormalizationStatus.SUCCESS:
            self.normalization_status = NormalizationStatus.PARTIAL
        return self
    
    @computed_field
    @property
    def has_quantity(self) -> bool:
        """Indica se a quantidade foi extraída."""
        return self.quantity is not None


class PriceOffer(BaseModel):
    """
    Oferta final com preço normalizado por unidade.
    Estrutura principal para comparação de preços.
    """
    
    # ID único
    id: UUID = Field(default_factory=uuid4)
    
    # Identificação do mercado
    market_id: MarketID
    market_name: str
    
    # Dados do produto
    title: str
    url: str
    image_url: Optional[str] = None
    
    # Preço original
    price: Decimal = Field(..., ge=0, decimal_places=2)
    
    # Quantidade
    quantity_value: Optional[float] = Field(default=None, gt=0)
    quantity_unit: Optional[Unit] = None
    
    # Preço normalizado
    normalized_price: Optional[Decimal] = Field(default=None, ge=0, decimal_places=2)
    normalized_unit: Optional[Unit] = None
    price_display: str = Field(..., description="Ex: R$ 25,99/kg")
    
    # Status
    availability: Availability
    normalization_status: NormalizationStatus
    
    # Metadados de coleta
    search_query: str
    cep: Optional[str] = None
    collected_at: datetime
    
    class Config:
        json_encoders = {
            Decimal: lambda v: float(v),
            UUID: lambda v: str(v),
            datetime: lambda v: v.isoformat(),
        }
    
    @computed_field
    @property
    def is_comparable(self) -> bool:
        """Indica se o produto pode ser comparado (tem preço normalizado)."""
        return (
            self.normalized_price is not None 
            and self.normalization_status == NormalizationStatus.SUCCESS
        )
    
    def format_price(self) -> str:
        """Formata preço para exibição."""
        return f"R$ {self.price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    
    def format_normalized_price(self) -> str:
        """Formata preço normalizado para exibição."""
        if self.normalized_price is None or self.normalized_unit is None:
            return "N/A"
        price_str = f"R$ {self.normalized_price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{price_str}/{self.normalized_unit.value}"


class CollectionMetadata(BaseModel):
    """Metadados de uma sessão de coleta."""
    
    # Identificação
    collection_id: UUID = Field(default_factory=uuid4)
    
    # Parâmetros da busca
    search_query: str
    cep: Optional[str] = None
    markets_requested: list[MarketID]
    
    # Timestamps
    started_at: datetime = Field(default_factory=datetime.now)
    finished_at: Optional[datetime] = None
    
    # Resultados por mercado
    results_per_market: dict[MarketID, int] = Field(default_factory=dict)
    errors_per_market: dict[MarketID, str] = Field(default_factory=dict)
    
    # Totais
    total_products: int = 0
    total_normalized: int = 0
    total_errors: int = 0
    
    @computed_field
    @property
    def duration_seconds(self) -> Optional[float]:
        """Duração da coleta em segundos."""
        if self.finished_at is None:
            return None
        return (self.finished_at - self.started_at).total_seconds()
    
    def mark_finished(self):
        """Marca a coleta como finalizada."""
        self.finished_at = datetime.now()


class SearchResult(BaseModel):
    """Resultado completo de uma busca."""
    
    # Metadados
    metadata: CollectionMetadata
    
    # Ofertas
    offers: list[PriceOffer] = Field(default_factory=list)
    
    @computed_field
    @property
    def total_offers(self) -> int:
        """Total de ofertas encontradas."""
        return len(self.offers)
    
    @computed_field
    @property
    def comparable_offers(self) -> int:
        """Total de ofertas comparáveis (com preço normalizado)."""
        return sum(1 for o in self.offers if o.is_comparable)
    
    def get_best_offer(self) -> Optional[PriceOffer]:
        """Retorna a melhor oferta (menor preço normalizado)."""
        comparable = [o for o in self.offers if o.is_comparable]
        if not comparable:
            return None
        return min(comparable, key=lambda o: o.normalized_price or Decimal("inf"))
    
    def get_offers_by_market(self, market_id: MarketID) -> list[PriceOffer]:
        """Retorna ofertas de um mercado específico."""
        return [o for o in self.offers if o.market_id == market_id]
    
    def sort_by_price(self, ascending: bool = True) -> list[PriceOffer]:
        """Retorna ofertas ordenadas por preço normalizado."""
        comparable = [o for o in self.offers if o.is_comparable]
        non_comparable = [o for o in self.offers if not o.is_comparable]
        
        sorted_comparable = sorted(
            comparable,
            key=lambda o: o.normalized_price or Decimal("inf"),
            reverse=not ascending,
        )
        
        return sorted_comparable + non_comparable

