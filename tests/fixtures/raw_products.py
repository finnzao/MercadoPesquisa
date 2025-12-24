"""
Fixtures de produtos brutos para testes.
Contém diversos casos de teste para normalização.
"""

from datetime import datetime
from src.core.models import RawProduct


# CASOS DE TESTE: MASSA (kg, g)

MASS_PRODUCTS = [
    # Formato: 5kg
    RawProduct(
        market_id="carrefour",
        title="Arroz Tipo 1 Tio João 5kg",
        price_raw="R$ 29,90",
        url="https://example.com/1",
        search_query="arroz",
        collected_at=datetime.now(),
    ),
    # Formato: 500g
    RawProduct(
        market_id="carrefour",
        title="Café Pilão Torrado 500g",
        price_raw="R$ 15,99",
        url="https://example.com/2",
        search_query="café",
        collected_at=datetime.now(),
    ),
    # Formato: 1 quilo
    RawProduct(
        market_id="atacadao",
        title="Feijão Carioca 1 quilo",
        price_raw="R$ 8,49",
        url="https://example.com/3",
        search_query="feijão",
        collected_at=datetime.now(),
    ),
    # Formato: 250 gramas
    RawProduct(
        market_id="pao_acucar",
        title="Manteiga Aviação 250 gramas",
        price_raw="R$ 12,90",
        url="https://example.com/4",
        search_query="manteiga",
        collected_at=datetime.now(),
    ),
]


# CASOS DE TESTE: VOLUME (L, ml)

VOLUME_PRODUCTS = [
    # Formato: 1L
    RawProduct(
        market_id="carrefour",
        title="Leite Integral Italac 1L",
        price_raw="R$ 6,49",
        url="https://example.com/5",
        search_query="leite",
        collected_at=datetime.now(),
    ),
    # Formato: 500ml
    RawProduct(
        market_id="atacadao",
        title="Suco de Laranja Del Valle 500ml",
        price_raw="R$ 4,99",
        url="https://example.com/6",
        search_query="suco",
        collected_at=datetime.now(),
    ),
    # Formato: 2 litros
    RawProduct(
        market_id="extra",
        title="Refrigerante Coca-Cola 2 litros",
        price_raw="R$ 10,99",
        url="https://example.com/7",
        search_query="refrigerante",
        collected_at=datetime.now(),
    ),
    # Formato: 200 mililitros
    RawProduct(
        market_id="pao_acucar",
        title="Creme de Leite Nestlé 200 mililitros",
        price_raw="R$ 4,29",
        url="https://example.com/8",
        search_query="creme de leite",
        collected_at=datetime.now(),
    ),
]


# CASOS DE TESTE: PACKS

PACK_PRODUCTS = [
    # Formato: 12x350ml
    RawProduct(
        market_id="carrefour",
        title="Cerveja Skol Pilsen 350ml Pack c/ 12 Latas",
        price_raw="R$ 39,90",
        url="https://example.com/9",
        search_query="cerveja",
        collected_at=datetime.now(),
    ),
    # Formato: pack 6 unidades
    RawProduct(
        market_id="atacadao",
        title="Água Mineral Crystal pack 6 unidades 500ml",
        price_raw="R$ 8,99",
        url="https://example.com/10",
        search_query="água",
        collected_at=datetime.now(),
    ),
    # Formato: caixa com 24
    RawProduct(
        market_id="atacadao",
        title="Leite UHT Integral caixa com 24 unidades 1L",
        price_raw="R$ 115,90",
        url="https://example.com/11",
        search_query="leite",
        collected_at=datetime.now(),
    ),
    # Formato: fardo 12
    RawProduct(
        market_id="atacadao",
        title="Papel Higiênico Neve fardo 12 rolos",
        price_raw="R$ 19,90",
        url="https://example.com/12",
        search_query="papel higiênico",
        collected_at=datetime.now(),
    ),
]


# CASOS DE TESTE: HORTIFRUTI

HORTIFRUTI_PRODUCTS = [
    # Por kg
    RawProduct(
        market_id="carrefour",
        title="Banana Prata por kg",
        price_raw="R$ 5,99",
        url="https://example.com/13",
        search_query="banana",
        collected_at=datetime.now(),
    ),
    # /kg
    RawProduct(
        market_id="pao_acucar",
        title="Tomate Italiano /kg",
        price_raw="R$ 8,99",
        url="https://example.com/14",
        search_query="tomate",
        collected_at=datetime.now(),
    ),
    # kg implícito
    RawProduct(
        market_id="extra",
        title="Maçã Fuji kg",
        price_raw="R$ 12,90",
        url="https://example.com/15",
        search_query="maçã",
        collected_at=datetime.now(),
    ),
]


# CASOS DE TESTE: SEM QUANTIDADE

NO_QUANTITY_PRODUCTS = [
    # Sem indicação de quantidade
    RawProduct(
        market_id="carrefour",
        title="Creme de Leite Nestlé",
        price_raw="R$ 4,99",
        url="https://example.com/16",
        search_query="creme de leite",
        collected_at=datetime.now(),
    ),
    # Produto genérico
    RawProduct(
        market_id="atacadao",
        title="Esponja de Aço Bombril",
        price_raw="R$ 3,49",
        url="https://example.com/17",
        search_query="esponja",
        collected_at=datetime.now(),
    ),
]


# CASOS DE TESTE: PREÇOS DIVERSOS

PRICE_FORMAT_PRODUCTS = [
    # R$ 12,99
    RawProduct(
        market_id="carrefour",
        title="Produto Teste 1kg",
        price_raw="R$ 12,99",
        url="https://example.com/18",
        search_query="teste",
        collected_at=datetime.now(),
    ),
    # R$12.99
    RawProduct(
        market_id="carrefour",
        title="Produto Teste 1kg",
        price_raw="R$12.99",
        url="https://example.com/19",
        search_query="teste",
        collected_at=datetime.now(),
    ),
    # 12,99
    RawProduct(
        market_id="carrefour",
        title="Produto Teste 1kg",
        price_raw="12,99",
        url="https://example.com/20",
        search_query="teste",
        collected_at=datetime.now(),
    ),
    # 1.234,56 (com milhar)
    RawProduct(
        market_id="carrefour",
        title="Produto Teste 1kg",
        price_raw="R$ 1.234,56",
        url="https://example.com/21",
        search_query="teste",
        collected_at=datetime.now(),
    ),
]