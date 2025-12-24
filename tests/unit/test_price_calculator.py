"""
Testes unitários para o Price Calculator.
"""

from decimal import Decimal

import pytest

from src.pipeline.price_calculator import PriceCalculator
from src.core.models import QuantityInfo, PriceOffer
from src.core.types import Unit, NormalizationStatus, Availability


class TestPriceCalculator:
    """Testes para PriceCalculator."""
    
    @pytest.fixture
    def calculator(self) -> PriceCalculator:
        """Instância do calculator."""
        return PriceCalculator()
    
    # TESTES: calculate_normalized_price
    
    class TestCalculateNormalizedPrice:
        """Testes para cálculo de preço normalizado."""
        
        def test_preco_por_kg_simples(self, calculator, quantity_5kg):
            """Testa cálculo simples: R$ 29,90 / 5kg = R$ 5,98/kg."""
            result = calculator.calculate_normalized_price(
                Decimal("29.90"),
                quantity_5kg,
            )
            
            assert result is not None
            price, unit = result
            assert price == Decimal("5.98")
            assert unit == Unit.KILOGRAM
        
        def test_preco_por_litro(self, calculator, quantity_1L):
            """Testa cálculo: R$ 6,49 / 1L = R$ 6,49/L."""
            result = calculator.calculate_normalized_price(
                Decimal("6.49"),
                quantity_1L,
            )
            
            assert result is not None
            price, unit = result
            assert price == Decimal("6.49")
            assert unit == Unit.LITER
        
        def test_preco_com_gramas(self, calculator, quantity_500g):
            """Testa conversão: R$ 15,00 / 500g = R$ 30,00/kg."""
            result = calculator.calculate_normalized_price(
                Decimal("15.00"),
                quantity_500g,
            )
            
            assert result is not None
            price, unit = result
            assert price == Decimal("30.00")
            assert unit == Unit.KILOGRAM
        
        def test_preco_com_pack(self, calculator, quantity_pack_12x350ml):
            """Testa pack: R$ 39,90 / (12 x 350ml) = R$ 9,50/L."""
            result = calculator.calculate_normalized_price(
                Decimal("39.90"),
                quantity_pack_12x350ml,
            )
            
            assert result is not None
            price, unit = result
            # 12 * 0.35L = 4.2L
            # 39.90 / 4.2 = 9.50
            assert price == Decimal("9.50")
            assert unit == Unit.LITER
        
        def test_quantidade_none(self, calculator):
            """Testa retorno None quando quantidade é None."""
            result = calculator.calculate_normalized_price(
                Decimal("10.00"),
                None,
            )
            
            assert result is None
    
    # TESTES: compare_offers
    
    class TestCompareOffers:
        """Testes para comparação de ofertas."""
        
        def test_ordenacao_ascendente(self, calculator, price_offers_for_comparison):
            """Testa ordenação por preço crescente."""
            sorted_offers = calculator.compare_offers(
                price_offers_for_comparison,
                ascending=True,
            )
            
            # Primeiro deve ser o mais barato (Atacadão - R$ 5,50/kg)
            assert sorted_offers[0].market_id == "atacadao"
            assert sorted_offers[0].normalized_price == Decimal("5.50")
            
            # Último comparável deve ser o mais caro
            comparable = [o for o in sorted_offers if o.is_comparable]
            assert comparable[-1].market_id == "extra"
        
        def test_ordenacao_descendente(self, calculator, price_offers_for_comparison):
            """Testa ordenação por preço decrescente."""
            sorted_offers = calculator.compare_offers(
                price_offers_for_comparison,
                ascending=False,
            )
            
            # Primeiro deve ser o mais caro
            assert sorted_offers[0].market_id == "extra"
    
    # TESTES: find_best_offer
    
    class TestFindBestOffer:
        """Testes para encontrar melhor oferta."""
        
        def test_encontra_melhor(self, calculator, price_offers_for_comparison):
            """Testa que encontra a oferta mais barata."""
            best = calculator.find_best_offer(price_offers_for_comparison)
            
            assert best is not None
            assert best.market_id == "atacadao"
            assert best.normalized_price == Decimal("5.50")
        
        def test_lista_vazia(self, calculator):
            """Testa retorno None para lista vazia."""
            best = calculator.find_best_offer([])
            
            assert best is None
    
    # TESTES: calculate_savings
    
    class TestCalculateSavings:
        """Testes para cálculo de economia."""
        
        def test_calcula_economia(self, calculator, price_offers_for_comparison):
            """Testa cálculo de economia entre ofertas."""
            best = price_offers_for_comparison[1]  # Atacadão - R$ 5,50/kg
            other = price_offers_for_comparison[2]  # Extra - R$ 6,58/kg
            
            savings = calculator.calculate_savings(best, other)
            
            assert savings is not None
            # Economia: 6,58 - 5,50 = R$ 1,08/kg
            assert savings["absolute"] == Decimal("1.08")
            assert savings["best_market"] == "Atacadão"
            assert savings["compared_market"] == "Extra Mercado"