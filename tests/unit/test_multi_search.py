"""
Testes unitários para o módulo de busca múltipla (multi_search).
Testa a lógica de cálculo de totais por mercado e otimização.
"""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from src.api.v1.multi_search import (
    format_price,
    build_item_result,
    calculate_market_totals,
    find_best_market,
    ItemOffer,
    ItemResult,
    MarketTotal,
)


class TestFormatPrice:
    """Testes para formatação de preço."""
    
    def test_format_price_simple(self):
        """Testa formatação simples."""
        result = format_price(29.90)
        assert result == "R$ 29,90"
    
    def test_format_price_with_thousands(self):
        """Testa formatação com milhares."""
        result = format_price(1234.56)
        assert result == "R$ 1.234,56"
    
    def test_format_price_cents_only(self):
        """Testa formatação de centavos."""
        result = format_price(0.99)
        assert result == "R$ 0,99"
    
    def test_format_price_integer(self):
        """Testa formatação de valor inteiro."""
        result = format_price(10.00)
        assert result == "R$ 10,00"
    
    def test_format_price_large_value(self):
        """Testa formatação de valor grande."""
        result = format_price(12345678.90)
        assert result == "R$ 12.345.678,90"


class TestBuildItemResult:
    """Testes para construção de resultado de item."""
    
    def test_build_item_result_not_found(self):
        """Testa resultado quando não há ofertas."""
        result = build_item_result("arroz", [])
        
        assert result.query == "arroz"
        assert result.status == "not_found"
        assert result.best_offer is None
        assert result.offers_count == 0
    
    def test_build_item_result_found(self):
        """Testa resultado com ofertas."""
        offers = [
            {
                "title": "Arroz 5kg",
                "price": 29.90,
                "price_formatted": "R$ 29,90",
                "market_id": "carrefour",
                "market_name": "Carrefour",
                "url": "https://example.com/arroz",
            }
        ]
        
        result = build_item_result("arroz", offers)
        
        assert result.query == "arroz"
        assert result.status == "found"
        assert result.best_offer is not None
        assert result.best_offer.price == 29.90
        assert result.offers_count == 1
    
    def test_build_item_result_with_alternatives(self):
        """Testa resultado com alternativas."""
        offers = [
            {"title": "Arroz 5kg", "price": 29.90, "market_id": "carrefour", "market_name": "Carrefour", "url": "url1"},
            {"title": "Arroz 5kg", "price": 31.90, "market_id": "atacadao", "market_name": "Atacadão", "url": "url2"},
            {"title": "Arroz 5kg", "price": 32.90, "market_id": "extra", "market_name": "Extra", "url": "url3"},
        ]
        
        result = build_item_result("arroz", offers)
        
        assert result.best_offer.price == 29.90
        assert len(result.alternatives) == 2
        assert result.alternatives[0].price == 31.90
    
    def test_build_item_result_limits_alternatives_to_5(self):
        """Testa que alternativas são limitadas a 5."""
        offers = [
            {"title": f"Arroz {i}", "price": 29.90 + i, "market_id": f"market_{i}", "market_name": f"Market {i}", "url": f"url{i}"}
            for i in range(10)
        ]
        
        result = build_item_result("arroz", offers)
        
        assert len(result.alternatives) == 5  # Máximo de 5 alternativas


class TestCalculateMarketTotals:
    """Testes para cálculo de totais por mercado."""
    
    def test_calculate_market_totals_single_item(self):
        """Testa cálculo com um único item."""
        queries = ["arroz"]
        offers = {
            "arroz": [
                {"market_id": "carrefour", "market_name": "Carrefour", "price": 29.90},
                {"market_id": "atacadao", "market_name": "Atacadão", "price": 27.50},
            ]
        }
        
        totals = calculate_market_totals(queries, offers)
        
        assert "carrefour" in totals
        assert "atacadao" in totals
        assert totals["carrefour"].total == 29.90
        assert totals["atacadao"].total == 27.50
    
    def test_calculate_market_totals_multiple_items(self):
        """Testa cálculo com múltiplos itens."""
        queries = ["arroz", "feijão"]
        offers = {
            "arroz": [
                {"market_id": "carrefour", "market_name": "Carrefour", "price": 29.90},
            ],
            "feijão": [
                {"market_id": "carrefour", "market_name": "Carrefour", "price": 8.90},
            ],
        }
        
        totals = calculate_market_totals(queries, offers)
        
        assert totals["carrefour"].total == pytest.approx(38.80, rel=0.01)
        assert totals["carrefour"].items_found == 2
    
    def test_calculate_market_totals_missing_items(self):
        """Testa cálculo com itens faltando."""
        queries = ["arroz", "feijão", "leite"]
        offers = {
            "arroz": [
                {"market_id": "carrefour", "market_name": "Carrefour", "price": 29.90},
            ],
            "feijão": [
                {"market_id": "carrefour", "market_name": "Carrefour", "price": 8.90},
            ],
            "leite": []  # Não encontrado
        }
        
        totals = calculate_market_totals(queries, offers)
        
        assert totals["carrefour"].items_found == 2
        assert "leite" in totals["carrefour"].items_missing
    
    def test_calculate_market_totals_coverage(self):
        """Testa cálculo de cobertura."""
        queries = ["item1", "item2", "item3", "item4"]
        offers = {
            "item1": [{"market_id": "m1", "market_name": "M1", "price": 10}],
            "item2": [{"market_id": "m1", "market_name": "M1", "price": 10}],
            "item3": [],
            "item4": [],
        }
        
        totals = calculate_market_totals(queries, offers)
        
        # 2 de 4 = 50%
        assert totals["m1"].coverage_percent == 50.0


class TestFindBestMarket:
    """Testes para encontrar o melhor mercado."""
    
    def test_find_best_market_by_price(self):
        """Testa que encontra mercado com menor total."""
        market_totals = {
            "carrefour": MarketTotal(
                market_id="carrefour",
                market_name="Carrefour",
                total=100.0,
                total_formatted="R$ 100,00",
                items_found=3,
                coverage_percent=100.0,
            ),
            "atacadao": MarketTotal(
                market_id="atacadao",
                market_name="Atacadão",
                total=90.0,
                total_formatted="R$ 90,00",
                items_found=3,
                coverage_percent=100.0,
            ),
        }
        
        best = find_best_market(market_totals)
        
        assert best.market_id == "atacadao"
    
    def test_find_best_market_considers_coverage(self):
        """Testa que considera cobertura mínima."""
        market_totals = {
            "carrefour": MarketTotal(
                market_id="carrefour",
                market_name="Carrefour",
                total=100.0,
                total_formatted="R$ 100,00",
                items_found=3,
                coverage_percent=100.0,  # 100% cobertura
            ),
            "atacadao": MarketTotal(
                market_id="atacadao",
                market_name="Atacadão",
                total=50.0,  # Mais barato
                total_formatted="R$ 50,00",
                items_found=1,
                coverage_percent=33.0,  # Baixa cobertura
            ),
        }
        
        # Com cobertura mínima de 50%, Atacadão não qualifica
        best = find_best_market(market_totals, min_coverage=50.0)
        
        assert best.market_id == "carrefour"
    
    def test_find_best_market_empty(self):
        """Testa com dicionário vazio."""
        best = find_best_market({})
        
        assert best is None
    
    def test_find_best_market_prioritizes_coverage_then_price(self):
        """Testa priorização: cobertura > preço."""
        market_totals = {
            "m1": MarketTotal(
                market_id="m1", market_name="M1",
                total=90.0, total_formatted="R$ 90,00",
                items_found=3, coverage_percent=75.0,
            ),
            "m2": MarketTotal(
                market_id="m2", market_name="M2",
                total=100.0, total_formatted="R$ 100,00",
                items_found=4, coverage_percent=100.0,
            ),
        }
        
        best = find_best_market(market_totals)
        
        # M2 tem cobertura maior, então deve ser escolhido
        # mesmo que M1 seja mais barato
        assert best.market_id == "m2"


class TestItemOffer:
    """Testes para ItemOffer."""
    
    def test_item_offer_creation(self):
        """Testa criação de ItemOffer."""
        offer = ItemOffer(
            title="Arroz 5kg",
            price=29.90,
            price_formatted="R$ 29,90",
            market_id="carrefour",
            market_name="Carrefour",
            url="https://example.com/arroz",
        )
        
        assert offer.title == "Arroz 5kg"
        assert offer.price == 29.90
        assert offer.is_comparable is True
    
    def test_item_offer_with_normalized_price(self):
        """Testa ItemOffer com preço normalizado."""
        offer = ItemOffer(
            title="Arroz 5kg",
            price=29.90,
            price_formatted="R$ 29,90",
            normalized_price=5.98,
            normalized_price_formatted="R$ 5,98/kg",
            market_id="carrefour",
            market_name="Carrefour",
            url="https://example.com/arroz",
        )
        
        assert offer.normalized_price == 5.98


class TestItemResult:
    """Testes para ItemResult."""
    
    def test_item_result_not_found(self):
        """Testa ItemResult não encontrado."""
        result = ItemResult(
            query="arroz",
            status="not_found",
        )
        
        assert result.status == "not_found"
        assert result.best_offer is None
        assert result.offers_count == 0
    
    def test_item_result_found(self):
        """Testa ItemResult encontrado."""
        offer = ItemOffer(
            title="Arroz 5kg",
            price=29.90,
            price_formatted="R$ 29,90",
            market_id="carrefour",
            market_name="Carrefour",
            url="https://example.com/arroz",
        )
        
        result = ItemResult(
            query="arroz",
            status="found",
            best_offer=offer,
            offers_count=5,
        )
        
        assert result.status == "found"
        assert result.best_offer.price == 29.90


class TestMarketTotal:
    """Testes para MarketTotal."""
    
    def test_market_total_creation(self):
        """Testa criação de MarketTotal."""
        total = MarketTotal(
            market_id="carrefour",
            market_name="Carrefour",
            total=100.0,
            total_formatted="R$ 100,00",
            items_found=3,
            items_missing=["leite"],
            items=[],
            coverage_percent=75.0,
        )
        
        assert total.market_id == "carrefour"
        assert total.total == 100.0
        assert total.items_found == 3
        assert "leite" in total.items_missing
        assert total.coverage_percent == 75.0
