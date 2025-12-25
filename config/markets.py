"""
Configurações dos mercados com URLs CORRETAS.
Atualizado em 24/12/2024.

NOTA: Extra foi removido pois o e-commerce foi descontinuado.
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


# CONFIGURAÇÕES DOS MERCADOS

# -----------------------------------------------------------------------------
# CARREFOUR MERCADO
# URL: https://mercado.carrefour.com.br/busca/TERMO
# IMPORTANTE: Usar quote() (não quote_plus) para encoding - espaço vira %20
# -----------------------------------------------------------------------------
CARREFOUR_CONFIG = MarketConfig(
    id="carrefour",
    name="carrefour",
    display_name="Carrefour Mercado",
    base_url="https://mercado.carrefour.com.br",
    search_url="https://mercado.carrefour.com.br/busca/{query}",
    method=ScrapingMethod.PLAYWRIGHT,
    status=MarketStatus.ACTIVE,  # Funcionando!
    requests_per_minute=6,
    requires_cep=False,
    selectors=MarketSelectors(
        # Container: é um <a> com data-testid
        product_container='a[data-testid="search-product-card"]',
        # Título: h2 dentro do card
        product_title="h2",
        # Preço: span com classes específicas
        product_price="span.text-blue-royal.font-bold, span[class*='text-blue-royal'][class*='font-bold']",
        product_price_cents=None,  # Preço já vem completo
        product_unit_price="p[class*='text-gray-medium']",
        # Link: o próprio card é um <a>
        product_link=None,  # Não precisa, card já é <a>
        # Imagem
        product_image="img",
        product_availability=None,
        next_page="button[aria-label*='próx'], button[aria-label*='Next']",
        cep_input="input[placeholder*='CEP']",
        cep_submit="button[type='submit']",
    ),
)

# -----------------------------------------------------------------------------
# ATACADÃO
# URL: https://www.atacadao.com.br/s?q=TERMO&sort=score_desc&page=0
# -----------------------------------------------------------------------------
ATACADAO_CONFIG = MarketConfig(
    id="atacadao",
    name="atacadao",
    display_name="Atacadão",
    base_url="https://www.atacadao.com.br",
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
# URL: https://www.paodeacucar.com/busca?terms=TERMO
# NOTA: Requer CEP para mostrar produtos
# -----------------------------------------------------------------------------
PAO_ACUCAR_CONFIG = MarketConfig(
    id="pao_acucar",
    name="pao_acucar",
    display_name="Pão de Açúcar",
    base_url="https://www.paodeacucar.com",
    search_url="https://www.paodeacucar.com/busca?terms={query}",
    method=ScrapingMethod.PLAYWRIGHT,
    status=MarketStatus.DEVELOPMENT,
    requests_per_minute=6,
    requires_cep=True,  # Sem CEP mostra "Nenhum resultado"
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


# REGISTRY DE MERCADOS

MARKETS_CONFIG: dict[str, MarketConfig] = {
    "carrefour": CARREFOUR_CONFIG,
    "atacadao": ATACADAO_CONFIG,
    "pao_acucar": PAO_ACUCAR_CONFIG,
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