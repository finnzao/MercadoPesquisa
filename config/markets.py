"""
Configurações CORRIGIDAS dos mercados.
URLs e seletores atualizados para dezembro de 2024.

SUBSTITUA o conteúdo de config/markets.py por este arquivo.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ScrapingMethod(str, Enum):
    """Método de scraping a ser utilizado."""
    REQUESTS = "requests"      # requests + BeautifulSoup (sites estáticos)
    PLAYWRIGHT = "playwright"  # Playwright (sites com JavaScript)


class MarketStatus(str, Enum):
    """Status de implementação do scraper."""
    ACTIVE = "active"
    DEVELOPMENT = "development"
    DISABLED = "disabled"
    BLOCKED = "blocked"


@dataclass
class MarketSelectors:
    """Seletores CSS/XPath para extração de dados."""
    
    # Container de produtos
    product_container: str
    
    # Dados do produto
    product_title: str
    product_price: str
    product_price_cents: Optional[str] = None
    product_unit_price: Optional[str] = None
    product_image: Optional[str] = None
    product_link: Optional[str] = None
    product_availability: Optional[str] = None
    
    # Paginação
    next_page: Optional[str] = None
    total_results: Optional[str] = None
    
    # CEP
    cep_input: Optional[str] = None
    cep_submit: Optional[str] = None
    cep_confirm: Optional[str] = None


@dataclass
class MarketConfig:
    """Configuração completa de um mercado."""
    
    # Identificação
    id: str
    name: str
    display_name: str
    
    # URLs
    base_url: str
    search_url: str
    
    # Scraping
    method: ScrapingMethod
    status: MarketStatus
    selectors: MarketSelectors
    
    # Rate limiting
    requests_per_minute: int = 10
    
    # Headers customizados
    custom_headers: dict = field(default_factory=dict)
    
    # Configurações específicas
    requires_cep: bool = False
    has_api: bool = False
    api_url: Optional[str] = None
    
    # Região padrão (Salvador/BA)
    default_region: str = "Salvador - BA"
    default_cep: str = "40000000"
    
    def get_search_url(self, query: str, page: int = 1) -> str:
        """Monta a URL de busca com a query."""
        return self.search_url.format(query=query, page=page)


# =============================================================================
# CONFIGURAÇÕES DOS MERCADOS - CORRIGIDAS DEZEMBRO 2024
# =============================================================================

# -----------------------------------------------------------------------------
# CARREFOUR MERCADO - USA SUBDOMÍNIO SEPARADO
# URL de busca: https://mercado.carrefour.com.br/s?q=TERMO&sort=score_desc&page=0
# -----------------------------------------------------------------------------
CARREFOUR_CONFIG = MarketConfig(
    id="carrefour",
    name="carrefour",
    display_name="Carrefour Mercado",
    base_url="https://mercado.carrefour.com.br",
    search_url="https://mercado.carrefour.com.br/s?q={query}&sort=score_desc&page={page}",
    method=ScrapingMethod.PLAYWRIGHT,
    status=MarketStatus.DEVELOPMENT,
    requests_per_minute=6,  # Mais conservador
    requires_cep=False,
    selectors=MarketSelectors(
        # Seletores VTEX (plataforma usada pelo Carrefour)
        product_container="div[data-testid='product-summary'], article[class*='product'], div[class*='vtex-product-summary']",
        product_title="span[class*='productName'], h3[class*='product'], a[class*='product'] span",
        product_price="span[class*='price'], span[class*='sellingPrice'], div[class*='price'] span",
        product_price_cents="span[class*='cents']",
        product_unit_price="span[class*='unitPrice'], div[class*='unitprice']",
        product_link="a[class*='product'], a[href*='/p']",
        product_image="img[class*='product'], img[src*='vtexassets']",
        product_availability="span[class*='availability'], div[class*='stock']",
        next_page="button[class*='next'], a[class*='next']",
        cep_input="input[placeholder*='CEP'], input[id*='cep']",
        cep_submit="button[class*='cep'], button[type='submit']",
    ),
)

# -----------------------------------------------------------------------------
# ATACADÃO - USA /catalogo PARA LISTAGEM
# URL: https://www.atacadao.com.br/catalogo?q=TERMO
# Nota: O Atacadão tem e-commerce limitado, funciona mais como catálogo
# -----------------------------------------------------------------------------
ATACADAO_CONFIG = MarketConfig(
    id="atacadao",
    name="atacadao",
    display_name="Atacadão",
    base_url="https://www.atacadao.com.br",
    search_url="https://www.atacadao.com.br/catalogo?q={query}&page={page}",
    method=ScrapingMethod.PLAYWRIGHT,
    status=MarketStatus.DEVELOPMENT,
    requests_per_minute=6,
    requires_cep=True,  # Atacadão exige CEP para ver preços
    selectors=MarketSelectors(
        # Seletores baseados em VTEX/Next.js
        product_container="div[class*='product-card'], article[class*='product'], a[class*='product-summary']",
        product_title="h3[class*='product'], span[class*='productName'], p[class*='product-name']",
        product_price="span[class*='price'], p[class*='price'], div[class*='price']",
        product_price_cents="span[class*='decimal'], span[class*='cents']",
        product_unit_price="span[class*='unit'], small[class*='unit']",
        product_link="a[href*='/p/'], a[class*='product-link']",
        product_image="img[class*='product'], img[src*='vtexassets']",
        product_availability="span[class*='stock'], div[class*='availability']",
        next_page="button[class*='next'], a[aria-label*='próx']",
        cep_input="input[placeholder*='CEP'], input[name*='cep']",
        cep_submit="button[class*='cep-button']",
    ),
)

# -----------------------------------------------------------------------------
# PÃO DE AÇÚCAR - GPA
# URL: https://www.paodeacucar.com/busca?q=TERMO
# -----------------------------------------------------------------------------
PAO_ACUCAR_CONFIG = MarketConfig(
    id="pao_acucar",
    name="pao_acucar",
    display_name="Pão de Açúcar",
    base_url="https://www.paodeacucar.com",
    search_url="https://www.paodeacucar.com/busca?q={query}&page={page}",
    method=ScrapingMethod.PLAYWRIGHT,
    status=MarketStatus.DEVELOPMENT,
    requests_per_minute=6,
    requires_cep=False,
    selectors=MarketSelectors(
        # GPA usa React/Next.js
        product_container="div[class*='product-card'], div[data-testid*='product'], article[class*='product']",
        product_title="h3[class*='product'], a[class*='product-name'], span[class*='name']",
        product_price="span[class*='price'], p[class*='price-value']",
        product_price_cents="span[class*='cents']",
        product_unit_price="span[class*='unit-price'], small[class*='price-per']",
        product_link="a[class*='product'], a[href*='/produto/']",
        product_image="img[class*='product'], img[loading='lazy']",
        product_availability="span[class*='stock'], div[class*='availability']",
        next_page="button[class*='next'], button[aria-label*='próxima']",
        cep_input="input[placeholder*='CEP']",
        cep_submit="button[class*='location']",
    ),
)

# -----------------------------------------------------------------------------
# EXTRA - GPA (mesma plataforma do Pão de Açúcar)
# URL: https://www.extra.com.br/busca?q=TERMO
# -----------------------------------------------------------------------------
EXTRA_CONFIG = MarketConfig(
    id="extra",
    name="extra",
    display_name="Extra Mercado",
    base_url="https://www.extra.com.br",
    search_url="https://www.extra.com.br/busca?q={query}&page={page}",
    method=ScrapingMethod.PLAYWRIGHT,
    status=MarketStatus.DEVELOPMENT,
    requests_per_minute=6,
    requires_cep=False,
    selectors=MarketSelectors(
        # Mesma estrutura GPA
        product_container="div[class*='product-card'], div[data-testid*='product'], article[class*='product']",
        product_title="h3[class*='product'], a[class*='product-name'], span[class*='name']",
        product_price="span[class*='price'], p[class*='price-value']",
        product_price_cents="span[class*='cents']",
        product_unit_price="span[class*='unit-price'], small[class*='price-per']",
        product_link="a[class*='product'], a[href*='/produto/']",
        product_image="img[class*='product'], img[loading='lazy']",
        product_availability="span[class*='stock'], div[class*='availability']",
        next_page="button[class*='next'], button[aria-label*='próxima']",
        cep_input="input[placeholder*='CEP']",
        cep_submit="button[class*='location']",
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