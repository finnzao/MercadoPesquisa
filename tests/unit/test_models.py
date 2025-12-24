"""
Testes unitários para os modelos de dados.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

from src.core.models import (
    RawProduct,
    NormalizedProduct,
    PriceOffer,
    QuantityInfo,
    SearchResult,
    CollectionMetadata,
)
from src.core.types import Unit, Availability, NormalizationStatus


class TestRawProduct:
    """Testes para RawProduct."""
    
    def test_criacao_valida(self):
        """Testa criação com dados válidos."""
        product = RawProduct(
            market_id="carrefour",
            title="Arroz 5kg",
            price_raw="R$ 29,90",
            url="https://example.com/arroz",
            search_query="arroz",
            collected_at=datetime.now(),
        )
        
        assert product.market_id == "carrefour"
        assert product.title == "Arroz 5kg"
    
    def test_titulo_limpo(self):
        """Testa que título é limpo de espaços extras."""
        product = RawProduct(
            market_id="carrefour",
            title="  Arroz   5kg  ",
            price_raw="R$ 29,90",
            url="https://example.com/arroz",
            search_query="arroz",
            collected_at=datetime.now(),
        )
        
        assert product.title == "Arroz 5kg"
    
    def test_preco_sem_digitos_invalido(self):
        """Testa que preço sem dígitos é inválido."""
        with pytest.raises(ValidationError):
            RawProduct(
                market_id="carrefour",
                title="Arroz 5kg",
                price_raw="sem preço",
                url="https://example.com/arroz",
                search_query="arroz",
                collected_at=datetime.now(),
            )


class TestQuantityInfo:
    """Testes para QuantityInfo."""
    
    def test_total_base_value(self):
        """Testa cálculo de total_base_value."""
        qty = QuantityInfo(
            value=350.0,
            unit=Unit.MILLILITER,
            base_value=0.35,
            base_unit=Unit.LITER,
            multiplier=12,
            raw_text="12x350ml",
        )
        
        assert qty.total_base_value == 4.2  # 0.35 * 12
    
    def test_sem_multiplicador(self):
        """Testa que multiplicador padrão é 1."""
        qty = QuantityInfo(
            value=5.0,
            unit=Unit.KILOGRAM,
            base_value=5.0,
            base_unit=Unit.KILOGRAM,
            raw_text="5kg",
        )
        
        assert qty.multiplier == 1
        assert qty.total_base_value == 5.0


class TestPriceOffer:
    """Testes para PriceOffer."""
    
    def test_is_comparable(self, price_offer_arroz):
        """Testa propriedade is_comparable."""
        assert price_offer_arroz.is_comparable is True
    
    def test_is_not_comparable_sem_preco_normalizado(self):
        """Testa que oferta sem preço normalizado não é comparável."""
        offer = PriceOffer(
            market_id="carrefour",
            market_name="Carrefour",
            title="Produto Teste",
            url="https://example.com",
            price=Decimal("10.00"),
            price_display="R$ 10,00",
            availability=Availability.AVAILABLE,
            normalization_status=NormalizationStatus.PARTIAL,
            search_query="teste",
            collected_at=datetime.now(),
        )
        
        assert offer.is_comparable is False
    
    def test_format_price(self, price_offer_arroz):
        """Testa formatação de preço."""
        formatted = price_offer_arroz.format_price()
        
        assert "29,90" in formatted
        assert "R$" in formatted
    
    def test_format_normalized_price(self, price_offer_arroz):
        """Testa formatação de preço normalizado."""
        formatted = price_offer_arroz.format_normalized_price()
        
        assert "5,98" in formatted
        assert "/kg" in formatted


class TestSearchResult:
    """Testes para SearchResult."""
    
    def test_total_offers(self, price_offers_for_comparison):
        """Testa contagem de ofertas."""
        metadata = CollectionMetadata(
            search_query="arroz",
            markets_requested=["carrefour", "atacadao", "extra"],
        )
        
        result = SearchResult(
            metadata=metadata,
            offers=price_offers_for_comparison,
        )
        
        assert result.total_offers == 3
    
    def test_comparable_offers(self, price_offers_for_comparison):
        """Testa contagem de ofertas comparáveis."""
        metadata = CollectionMetadata(
            search_query="arroz",
            markets_requested=["carrefour", "atacadao", "extra"],
        )
        
        result = SearchResult(
            metadata=metadata,
            offers=price_offers_for_comparison,
        )
        
        assert result.comparable_offers == 3
    
    def test_get_best_offer(self, price_offers_for_comparison):
        """Testa obtenção da melhor oferta."""
        metadata = CollectionMetadata(
            search_query="arroz",
            markets_requested=["carrefour", "atacadao", "extra"],
        )
        
        result = SearchResult(
            metadata=metadata,
            offers=price_offers_for_comparison,
        )
        
        best = result.get_best_offer()
        
        assert best is not None
        assert best.market_id == "atacadao"