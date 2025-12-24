"""
Configurações dos mercados com URLs CORRETAS.
Atualizado em 24/12/2024 com URLs reais testadas.

SUBSTITUA o conteúdo de config/markets.py por este arquivo.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ScrapingMethod(str, Enum):
    """Método de scraping a ser utilizado."""
    REQUESTS = "requests"
    PLAYWRIGHT = "playwright"


class MarketStatus(str, Enum):
    """Status de implementação do scraper."""
    ACTIVE = "active"
    DEVELOPMENT = "development"
    DISABLED = "disabled"
    BLOCKED = "blocked"


@dataclass
class MarketSelectors:
    """Seletores CSS/XPath para extração de dados."""
    
    product_container: str
    product_title: str
    product_price: str
    product_price_cents: Optional[str] = None
    product_unit_price: Optional[str] = None
    product_image: Optional[str] = None
    product_link: Optional[str] = None
    product_availability: Optional[str] = None
    next_page: Optional[str] = None
    total_results: Optional[str] = None
    cep_input: Optional[str] = None
    cep_submit: Optional[str] = None
    cep_confirm: Optional[str] = None


@dataclass
class MarketConfig:
    """Configuração completa de um mercado."""
    
    id: str
    name: str
    display_name: str
    base_url: str
    search_url: str
    method: ScrapingMethod
    status: MarketStatus
    selectors: MarketSelectors
    requests_per_minute: int = 10
    custom_headers: dict = field(default_factory=dict)
    requires_cep: bool = False
    has_api: bool = False
    api_url: Optional[str] = None
    default_region: str = "Salvador - BA"
    default_cep: str = "40000000"
    
    def get_search_url(self, query: str, page: int = 0) -> str:
        """Monta a URL de busca com a query."""
        return self.search_url.format(query=query, page=page)


# =============================================================================
# CONFIGURAÇÕES DOS MERCADOS - URLs CORRETAS 24/12/2024
# =============================================================================

# -----------------------------------------------------------------------------
# CARREFOUR MERCADO
# URL real: https://mercado.carrefour.com.br/busca/TERMO
# Exemplo: https://mercado.carrefour.com.br/busca/leite%20em%20p%C3%B3
# -----------------------------------------------------------------------------
CARREFOUR_CONFIG = MarketConfig(
    id="carrefour",
    name="carrefour",
    display_name="Carrefour Mercado",
    base_url="https://mercado.carrefour.com.br",
    # URL CORRETA - usa /busca/TERMO (não query string)
    search_url="https://mercado.carrefour.com.br/busca/{query}",
    method=ScrapingMethod.PLAYWRIGHT,
    status=MarketStatus.DEVELOPMENT,
    requests_per_minute=6,
    requires_cep=False,
    selectors=MarketSelectors(
        product_container="div[data-testid='product-summary'], article[class*='product'], div[class*='vtex-product-summary'], div[class*='product-card']",
        product_title="span[class*='productName'], h3[class*='product'], a[class*='product'] span, span[class*='name']",
        product_price="span[class*='price'], span[class*='sellingPrice'], div[class*='price'] span",
        product_price_cents="span[class*='cents'], span[class*='decimal']",
        product_unit_price="span[class*='unitPrice'], div[class*='unitprice'], span[class*='perUnit']",
        product_link="a[class*='product'], a[href*='/p'], a[href*='/produto']",
        product_image="img[class*='product'], img[src*='vtexassets'], img[src*='carrefour']",
        product_availability="span[class*='availability'], div[class*='stock']",
        next_page="button[class*='next'], a[class*='next'], button[aria-label*='próx']",
        cep_input="input[placeholder*='CEP'], input[id*='cep']",
        cep_submit="button[class*='cep'], button[type='submit']",
    ),
)

# -----------------------------------------------------------------------------
# ATACADÃO
# URL real: https://www.atacadao.com.br/s?q=TERMO&sort=score_desc&page=0
# Exemplo: https://www.atacadao.com.br/s?q=leite+em+p%C3%B3&sort=score_desc&page=0
# -----------------------------------------------------------------------------
ATACADAO_CONFIG = MarketConfig(
    id="atacadao",
    name="atacadao",
    display_name="Atacadão",
    base_url="https://www.atacadao.com.br",
    # URL CORRETA - usa /s?q=TERMO&sort=score_desc&page=N
    search_url="https://www.atacadao.com.br/s?q={query}&sort=score_desc&page={page}",
    method=ScrapingMethod.PLAYWRIGHT,
    status=MarketStatus.DEVELOPMENT,
    requests_per_minute=6,
    requires_cep=True,
    selectors=MarketSelectors(
        product_container="div[class*='product-card'], article[class*='product'], a[class*='product-summary'], div[class*='productCard']",
        product_title="h3[class*='product'], span[class*='productName'], p[class*='product-name'], h2[class*='name']",
        product_price="span[class*='price'], p[class*='price'], div[class*='price'], span[class*='sellingPrice']",
        product_price_cents="span[class*='decimal'], span[class*='cents']",
        product_unit_price="span[class*='unit'], small[class*='unit'], span[class*='perUnit']",
        product_link="a[href*='/p/'], a[class*='product-link'], a[href*='/produto']",
        product_image="img[class*='product'], img[src*='vtexassets'], img[src*='atacadao']",
        product_availability="span[class*='stock'], div[class*='availability']",
        next_page="button[class*='next'], a[aria-label*='próx'], button[aria-label*='Next']",
        cep_input="input[placeholder*='CEP'], input[name*='cep']",
        cep_submit="button[class*='cep-button'], button[class*='location']",
    ),
)

# -----------------------------------------------------------------------------
# PÃO DE AÇÚCAR
# URL real: https://www.paodeacucar.com/busca?terms=TERMO
# Exemplo: https://www.paodeacucar.com/busca?terms=leite%20em%20p%C3%B3
# -----------------------------------------------------------------------------
PAO_ACUCAR_CONFIG = MarketConfig(
    id="pao_acucar",
    name="pao_acucar",
    display_name="Pão de Açúcar",
    base_url="https://www.paodeacucar.com",
    # URL CORRETA - usa /busca?terms=TERMO (não q=)
    search_url="https://www.paodeacucar.com/busca?terms={query}",
    method=ScrapingMethod.PLAYWRIGHT,
    status=MarketStatus.DEVELOPMENT,
    requests_per_minute=6,
    requires_cep=False,
    selectors=MarketSelectors(
        product_container="div[class*='product-card'], div[data-testid*='product'], article[class*='product'], div[class*='ProductCard']",
        product_title="h3[class*='product'], a[class*='product-name'], span[class*='name'], p[class*='title']",
        product_price="span[class*='price'], p[class*='price-value'], div[class*='price'], span[class*='value']",
        product_price_cents="span[class*='cents'], span[class*='decimal']",
        product_unit_price="span[class*='unit-price'], small[class*='price-per'], span[class*='perUnit']",
        product_link="a[class*='product'], a[href*='/produto/'], a[href*='/p/']",
        product_image="img[class*='product'], img[loading='lazy'], img[src*='paodeacucar']",
        product_availability="span[class*='stock'], div[class*='availability']",
        next_page="button[class*='next'], button[aria-label*='próxima'], a[class*='pagination-next']",
        cep_input="input[placeholder*='CEP']",
        cep_submit="button[class*='location'], button[class*='cep']",
    ),
)

# -----------------------------------------------------------------------------
# EXTRA - Mesmo formato do Pão de Açúcar (mesma empresa GPA)
# URL provável: https://www.extra.com.br/busca?terms=TERMO
# -----------------------------------------------------------------------------
EXTRA_CONFIG = MarketConfig(
    id="extra",
    name="extra",
    display_name="Extra Mercado",
    base_url="https://www.extra.com.br",
    # Usando mesmo formato do Pão de Açúcar (GPA)
    search_url="https://www.extra.com.br/busca?terms={query}",
    method=ScrapingMethod.PLAYWRIGHT,
    status=MarketStatus.DEVELOPMENT,
    requests_per_minute=6,
    requires_cep=False,
    selectors=MarketSelectors(
        product_container="div[class*='product-card'], div[data-testid*='product'], article[class*='product'], div[class*='ProductCard']",
        product_title="h3[class*='product'], a[class*='product-name'], span[class*='name'], p[class*='title']",
        product_price="span[class*='price'], p[class*='price-value'], div[class*='price'], span[class*='value']",
        product_price_cents="span[class*='cents'], span[class*='decimal']",
        product_unit_price="span[class*='unit-price'], small[class*='price-per'], span[class*='perUnit']",
        product_link="a[class*='product'], a[href*='/produto/'], a[href*='/p/']",
        product_image="img[class*='product'], img[loading='lazy'], img[src*='extra']",
        product_availability="span[class*='stock'], div[class*='availability']",
        next_page="button[class*='next'], button[aria-label*='próxima'], a[class*='pagination-next']",
        cep_input="input[placeholder*='CEP']",
        cep_submit="button[class*='location'], button[class*='cep']",
    ),
)


# Dicionário com todas as configurações
MARKETS_CONFIG: dict[str, MarketConfig] = {
    "carrefour": CARREFOUR_CONFIG,
    "atacadao": ATACADAO_CONFIG,
    "pao_acucar": PAO_ACUCAR_CONFIG,
    "extra": EXTRA_CONFIG,
}


def get_market_config(market_id: str) -> MarketConfig:
    """Retorna a configuração de um mercado específico."""
    if market_id not in MARKETS_CONFIG:
        raise ValueError(f"Mercado '{market_id}' não configurado. "
                        f"Disponíveis: {list(MARKETS_CONFIG.keys())}")
    return MARKETS_CONFIG[market_id]


def get_active_markets() -> list[MarketConfig]:
    """Retorna lista de mercados ativos para scraping."""
    return [
        config for config in MARKETS_CONFIG.values()
        if config.status in (MarketStatus.ACTIVE, MarketStatus.DEVELOPMENT)
    ]