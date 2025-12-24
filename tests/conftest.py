"""
Configurações e fixtures compartilhadas para pytest.
"""

import asyncio
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Generator
from uuid import uuid4

import pytest
import pytest_asyncio

from src.core.models import RawProduct, NormalizedProduct, PriceOffer, QuantityInfo
from src.core.types import Unit, Availability, NormalizationStatus
from config.markets import CARREFOUR_CONFIG, MarketConfig


# CONFIGURAÇÃO DO ASYNCIO

@pytest.fixture(scope="session")
def event_loop():
    """Cria event loop para testes assíncronos."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# FIXTURES DE DIRETÓRIOS

@pytest.fixture
def temp_data_dir(tmp_path) -> Path:
    """Cria diretório temporário para dados de teste."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return data_dir


@pytest.fixture
def temp_log_dir(tmp_path) -> Path:
    """Cria diretório temporário para logs de teste."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    return log_dir


# FIXTURES DE PRODUTOS BRUTOS

@pytest.fixture
def raw_product_arroz() -> RawProduct:
    """Produto bruto: Arroz 5kg."""
    return RawProduct(
        market_id="carrefour",
        title="Arroz Tipo 1 Tio João 5kg",
        price_raw="R$ 29,90",
        unit_price_raw="R$ 5,98/kg",
        url="https://www.carrefour.com.br/arroz-tio-joao-5kg",
        image_url="https://www.carrefour.com.br/images/arroz.jpg",
        availability_raw="Disponível",
        search_query="arroz tipo 1 5kg",
        cep="40000000",
        collected_at=datetime.now(),
    )


@pytest.fixture
def raw_product_leite() -> RawProduct:
    """Produto bruto: Leite 1L."""
    return RawProduct(
        market_id="atacadao",
        title="Leite Integral Italac 1L",
        price_raw="6,49",
        url="https://www.atacadao.com.br/leite-italac-1l",
        availability_raw="Em estoque",
        search_query="leite integral 1L",
        collected_at=datetime.now(),
    )


@pytest.fixture
def raw_product_pack_cerveja() -> RawProduct:
    """Produto bruto: Pack de cerveja 12x350ml."""
    return RawProduct(
        market_id="pao_acucar",
        title="Cerveja Skol Pilsen 350ml Pack c/ 12 Latas",
        price_raw="R$ 39,90",
        url="https://www.paodeacucar.com/cerveja-skol-pack-12",
        availability_raw="Disponível",
        search_query="cerveja skol",
        collected_at=datetime.now(),
    )


@pytest.fixture
def raw_product_banana() -> RawProduct:
    """Produto bruto: Banana por kg."""
    return RawProduct(
        market_id="extra",
        title="Banana Prata por kg",
        price_raw="R$ 5,99",
        url="https://www.extra.com.br/banana-prata",
        availability_raw="Disponível",
        search_query="banana prata",
        collected_at=datetime.now(),
    )


@pytest.fixture
def raw_product_sem_quantidade() -> RawProduct:
    """Produto bruto sem quantidade identificável."""
    return RawProduct(
        market_id="carrefour",
        title="Creme de Leite Nestlé",
        price_raw="R$ 4,99",
        url="https://www.carrefour.com.br/creme-leite",
        search_query="creme de leite",
        collected_at=datetime.now(),
    )


@pytest.fixture
def raw_products_batch(
    raw_product_arroz,
    raw_product_leite,
    raw_product_pack_cerveja,
    raw_product_banana,
    raw_product_sem_quantidade,
) -> list[RawProduct]:
    """Lista de produtos brutos para testes em lote."""
    return [
        raw_product_arroz,
        raw_product_leite,
        raw_product_pack_cerveja,
        raw_product_banana,
        raw_product_sem_quantidade,
    ]


# FIXTURES DE QUANTIDADE

@pytest.fixture
def quantity_5kg() -> QuantityInfo:
    """Quantidade: 5kg."""
    return QuantityInfo(
        value=5.0,
        unit=Unit.KILOGRAM,
        base_value=5.0,
        base_unit=Unit.KILOGRAM,
        multiplier=1,
        raw_text="5kg",
        extraction_pattern="standard",
    )


@pytest.fixture
def quantity_500g() -> QuantityInfo:
    """Quantidade: 500g."""
    return QuantityInfo(
        value=500.0,
        unit=Unit.GRAM,
        base_value=0.5,
        base_unit=Unit.KILOGRAM,
        multiplier=1,
        raw_text="500g",
        extraction_pattern="standard",
    )


@pytest.fixture
def quantity_1L() -> QuantityInfo:
    """Quantidade: 1L."""
    return QuantityInfo(
        value=1.0,
        unit=Unit.LITER,
        base_value=1.0,
        base_unit=Unit.LITER,
        multiplier=1,
        raw_text="1L",
        extraction_pattern="standard",
    )


@pytest.fixture
def quantity_pack_12x350ml() -> QuantityInfo:
    """Quantidade: Pack 12x350ml."""
    return QuantityInfo(
        value=350.0,
        unit=Unit.MILLILITER,
        base_value=0.35,
        base_unit=Unit.LITER,
        multiplier=12,
        raw_text="12x350ml",
        extraction_pattern="pack_NxM",
    )


# FIXTURES DE OFERTAS

@pytest.fixture
def price_offer_arroz() -> PriceOffer:
    """Oferta de preço: Arroz normalizado."""
    return PriceOffer(
        market_id="carrefour",
        market_name="Carrefour Mercado",
        title="Arroz Tipo 1 Tio João 5kg",
        url="https://www.carrefour.com.br/arroz-tio-joao-5kg",
        price=Decimal("29.90"),
        quantity_value=5.0,
        quantity_unit=Unit.KILOGRAM,
        normalized_price=Decimal("5.98"),
        normalized_unit=Unit.KILOGRAM,
        price_display="R$ 5,98/kg",
        availability=Availability.AVAILABLE,
        normalization_status=NormalizationStatus.SUCCESS,
        search_query="arroz tipo 1 5kg",
        cep="40000000",
        collected_at=datetime.now(),
    )


@pytest.fixture
def price_offer_leite() -> PriceOffer:
    """Oferta de preço: Leite normalizado."""
    return PriceOffer(
        market_id="atacadao",
        market_name="Atacadão",
        title="Leite Integral Italac 1L",
        url="https://www.atacadao.com.br/leite-italac-1l",
        price=Decimal("6.49"),
        quantity_value=1.0,
        quantity_unit=Unit.LITER,
        normalized_price=Decimal("6.49"),
        normalized_unit=Unit.LITER,
        price_display="R$ 6,49/L",
        availability=Availability.AVAILABLE,
        normalization_status=NormalizationStatus.SUCCESS,
        search_query="leite integral 1L",
        collected_at=datetime.now(),
    )


@pytest.fixture
def price_offers_for_comparison(
    price_offer_arroz,
) -> list[PriceOffer]:
    """Lista de ofertas para comparação."""
    # Cria variações de preço do mesmo produto
    offers = [price_offer_arroz]
    
    # Atacadão - mais barato
    offers.append(PriceOffer(
        market_id="atacadao",
        market_name="Atacadão",
        title="Arroz Tipo 1 Tio João 5kg",
        url="https://www.atacadao.com.br/arroz-5kg",
        price=Decimal("27.50"),
        quantity_value=5.0,
        quantity_unit=Unit.KILOGRAM,
        normalized_price=Decimal("5.50"),
        normalized_unit=Unit.KILOGRAM,
        price_display="R$ 5,50/kg",
        availability=Availability.AVAILABLE,
        normalization_status=NormalizationStatus.SUCCESS,
        search_query="arroz tipo 1 5kg",
        collected_at=datetime.now(),
    ))
    
    # Extra - mais caro
    offers.append(PriceOffer(
        market_id="extra",
        market_name="Extra Mercado",
        title="Arroz Tipo 1 Camil 5kg",
        url="https://www.extra.com.br/arroz-5kg",
        price=Decimal("32.90"),
        quantity_value=5.0,
        quantity_unit=Unit.KILOGRAM,
        normalized_price=Decimal("6.58"),
        normalized_unit=Unit.KILOGRAM,
        price_display="R$ 6,58/kg",
        availability=Availability.AVAILABLE,
        normalization_status=NormalizationStatus.SUCCESS,
        search_query="arroz tipo 1 5kg",
        collected_at=datetime.now(),
    ))
    
    return offers


# FIXTURES DE CONFIGURAÇÃO

@pytest.fixture
def market_config() -> MarketConfig:
    """Configuração de mercado para testes."""
    return CARREFOUR_CONFIG


@pytest.fixture
def settings_override(temp_data_dir, temp_log_dir, monkeypatch):
    """Override de settings para testes."""
    monkeypatch.setenv("DATA_PATH", str(temp_data_dir))
    monkeypatch.setenv("LOG_PATH", str(temp_log_dir))
    monkeypatch.setenv("ENV", "testing")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")