"""
Modelos de dados para Lista de Compras.
Define estruturas para itens, resultados e resumos.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4


@dataclass
class ShoppingItem:
    """
    Item da lista de compras.
    
    Attributes:
        name: Nome/descrição do item (ex: "arroz 5kg", "leite integral 1L")
        quantity: Quantidade desejada (default: 1)
        notes: Observações opcionais
    """
    name: str
    quantity: int = 1
    notes: Optional[str] = None
    
    def __post_init__(self):
        self.name = self.name.strip()
        if self.quantity < 1:
            self.quantity = 1


@dataclass
class ItemResult:
    """
    Resultado da busca para um item da lista.
    
    Contém informações do produto mais barato encontrado.
    """
    # Item original
    item_name: str
    item_quantity: int
    
    # Melhor oferta encontrada
    found: bool = False
    product_title: Optional[str] = None
    price: Optional[Decimal] = None
    normalized_price: Optional[Decimal] = None
    normalized_unit: Optional[str] = None
    price_display: Optional[str] = None
    
    # Localização
    market_id: Optional[str] = None
    market_name: Optional[str] = None
    
    # Links
    product_url: Optional[str] = None
    image_url: Optional[str] = None
    
    # Metadados
    total_offers_found: int = 0
    relevant_offers: int = 0
    search_time_seconds: Optional[float] = None
    
    # Alternativas (outras ofertas boas)
    alternatives: list["ItemResult"] = field(default_factory=list)
    
    @property
    def total_price(self) -> Optional[Decimal]:
        """Preço total considerando quantidade."""
        if self.price is None:
            return None
        return self.price * self.item_quantity
    
    @property
    def formatted_price(self) -> str:
        """Preço formatado no padrão brasileiro."""
        if self.price is None:
            return "N/A"
        price_str = f"{self.price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {price_str}"
    
    @property
    def formatted_total(self) -> str:
        """Preço total formatado."""
        total = self.total_price
        if total is None:
            return "N/A"
        price_str = f"{total:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {price_str}"
    
    def to_dict(self) -> dict:
        """Converte para dicionário."""
        return {
            "item_name": self.item_name,
            "item_quantity": self.item_quantity,
            "found": self.found,
            "product_title": self.product_title,
            "price": float(self.price) if self.price else None,
            "total_price": float(self.total_price) if self.total_price else None,
            "normalized_price": float(self.normalized_price) if self.normalized_price else None,
            "normalized_unit": self.normalized_unit,
            "price_display": self.price_display,
            "market_id": self.market_id,
            "market_name": self.market_name,
            "product_url": self.product_url,
            "image_url": self.image_url,
            "total_offers_found": self.total_offers_found,
            "relevant_offers": self.relevant_offers,
            "alternatives": [alt.to_dict() for alt in self.alternatives] if self.alternatives else [],
        }


@dataclass
class MarketSummary:
    """
    Resumo de compras por mercado.
    
    Agrupa itens que devem ser comprados no mesmo mercado.
    """
    market_id: str
    market_name: str
    items: list[ItemResult] = field(default_factory=list)
    
    @property
    def total_items(self) -> int:
        """Total de itens neste mercado."""
        return len(self.items)
    
    @property
    def total_price(self) -> Decimal:
        """Soma dos preços totais dos itens."""
        total = Decimal("0.00")
        for item in self.items:
            if item.total_price:
                total += item.total_price
        return total
    
    @property
    def formatted_total(self) -> str:
        """Total formatado."""
        price_str = f"{self.total_price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {price_str}"
    
    def to_dict(self) -> dict:
        """Converte para dicionário."""
        return {
            "market_id": self.market_id,
            "market_name": self.market_name,
            "total_items": self.total_items,
            "total_price": float(self.total_price),
            "formatted_total": self.formatted_total,
            "items": [item.to_dict() for item in self.items],
        }


@dataclass
class ShoppingListResult:
    """
    Resultado completo do processamento da lista de compras.
    """
    # Identificação
    id: UUID = field(default_factory=uuid4)
    
    # Timestamps
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: Optional[datetime] = None
    
    # Parâmetros
    cep: Optional[str] = None
    markets_searched: list[str] = field(default_factory=list)
    
    # Resultados por item
    items: list[ItemResult] = field(default_factory=list)
    
    # Itens não encontrados
    not_found: list[str] = field(default_factory=list)
    
    def mark_finished(self):
        """Marca como finalizado."""
        self.finished_at = datetime.now()
    
    @property
    def duration_seconds(self) -> Optional[float]:
        """Duração em segundos."""
        if self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None
    
    @property
    def total_items(self) -> int:
        """Total de itens na lista."""
        return len(self.items) + len(self.not_found)
    
    @property
    def items_found(self) -> int:
        """Total de itens encontrados."""
        return sum(1 for item in self.items if item.found)
    
    @property
    def total_estimated(self) -> Decimal:
        """Valor total estimado da compra."""
        total = Decimal("0.00")
        for item in self.items:
            if item.total_price:
                total += item.total_price
        return total
    
    @property
    def formatted_total(self) -> str:
        """Total formatado."""
        price_str = f"{self.total_estimated:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {price_str}"
    
    def get_by_market(self) -> list[MarketSummary]:
        """
        Agrupa resultados por mercado.
        
        Returns:
            Lista de MarketSummary ordenada por total (menor primeiro)
        """
        market_items: dict[str, MarketSummary] = {}
        
        for item in self.items:
            if item.found and item.market_id:
                if item.market_id not in market_items:
                    market_items[item.market_id] = MarketSummary(
                        market_id=item.market_id,
                        market_name=item.market_name or item.market_id,
                    )
                market_items[item.market_id].items.append(item)
        
        # Ordena por total (menor primeiro)
        summaries = list(market_items.values())
        summaries.sort(key=lambda m: m.total_price)
        
        return summaries
    
    def get_best_market_for_all(self) -> Optional[MarketSummary]:
        """
        Encontra o mercado onde a compra completa seria mais barata.
        
        TODO: Itens que não foram
        
        Returns:
            MarketSummary do melhor mercado ou None
        """
        summaries = self.get_by_market()
        return summaries[0] if summaries else None
    
    def to_dict(self) -> dict:
        """Converte para dicionário."""
        return {
            "id": str(self.id),
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "duration_seconds": self.duration_seconds,
            "cep": self.cep,
            "markets_searched": self.markets_searched,
            "total_items": self.total_items,
            "items_found": self.items_found,
            "total_estimated": float(self.total_estimated),
            "formatted_total": self.formatted_total,
            "items": [item.to_dict() for item in self.items],
            "not_found": self.not_found,
            "by_market": [m.to_dict() for m in self.get_by_market()],
        }