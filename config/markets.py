"""
Configuração dos mercados suportados.
Define URLs, seletores CSS e parâmetros de cada mercado.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from urllib.parse import quote_plus


class MarketStatus(str, Enum):
    """Status de um mercado."""
    ACTIVE = "active"
    DEVELOPMENT = "development"
    DISABLED = "disabled"
    DEPRECATED = "deprecated"


class ScrapingMethod(str, Enum):
    """Método de scraping utilizado."""
    PLAYWRIGHT = "playwright"
    REQUESTS = "requests"
    API = "api"


@dataclass
class MarketSelectors:
    """Seletores CSS para extração de dados."""
    
    # Container de produto
    product_container: str = ""
    
    # Dados do produto
    product_title: str = ""
    product_price: str = ""
    product_price_cents: str = ""
    product_unit_price: str = ""
    product_image: str = ""
    product_link: str = ""
    product_availability: str = ""
    
    # Navegação
    next_page: str = ""
    total_results: str = ""
    
    # CEP/Localização
    cep_input: str = ""
    cep_submit: str = ""


@dataclass
class MarketConfig:
    """Configuração completa de um mercado."""
    
    id: str
    display_name: str
    base_url: str
    search_url_template: str
    
    status: MarketStatus = MarketStatus.ACTIVE
    method: ScrapingMethod = ScrapingMethod.PLAYWRIGHT
    
    # Seletores CSS
    selectors: MarketSelectors = field(default_factory=MarketSelectors)
    
    # Rate limiting
    requests_per_minute: int = 10
    
    # Parâmetros adicionais
    requires_cep: bool = False
    supports_pagination: bool = True
    max_pages: int = 5
    
    def get_search_url(self, query: str, page: int = 0) -> str:
        """
        Monta URL de busca.
        
        Args:
            query: Termo de busca (já codificado)
            page: Número da página (0-indexed)
            
        Returns:
            URL completa de busca
        """
        url = self.search_url_template.format(
            base_url=self.base_url,
            query=query,
            page=page,
        )
        return url


# =============================================================================
# CONFIGURAÇÃO DO CARREFOUR
# =============================================================================

CARREFOUR_SELECTORS = MarketSelectors(
    product_container='a[data-testid="search-product-card"]',
    product_title="h2",
    product_price="span.text-blue-royal.font-bold, span[class*='text-blue-royal'][class*='font-bold']",
    product_price_cents="",
    product_unit_price="p[class*='text-gray-medium']",
    product_image="img",
    product_link="",  # O próprio container é o link
    product_availability="",
    next_page="button[aria-label='Próxima página']",
    total_results="span[class*='total']",
    cep_input="input[placeholder*='CEP']",
    cep_submit="button[type='submit']",
)

CARREFOUR_CONFIG = MarketConfig(
    id="carrefour",
    display_name="Carrefour",
    base_url="https://mercado.carrefour.com.br",
    search_url_template="{base_url}/busca/{query}?page={page}",
    status=MarketStatus.ACTIVE,
    method=ScrapingMethod.PLAYWRIGHT,
    selectors=CARREFOUR_SELECTORS,
    requests_per_minute=10,
    requires_cep=False,
    supports_pagination=True,
    max_pages=5,
)


# =============================================================================
# CONFIGURAÇÃO DO ATACADÃO
# =============================================================================

ATACADAO_SELECTORS = MarketSelectors(
    product_container="ul.grid li article.relative",
    product_title="h3[title], h3, a[data-testid='product-link']",
    product_price="section p.text-lg.font-bold, p[class*='text-lg'][class*='font-bold']",
    product_price_cents="",
    product_unit_price="",
    product_image="div[data-product-card-image] img, img",
    product_link="a[data-testid='product-link'], a[href*='/p']",
    product_availability="button[data-testid='buy-button']",
    next_page="button[aria-label='Próxima página']",
    total_results="h2[data-testid='total-product-count'] span.font-bold",
    cep_input="input[placeholder*='CEP']",
    cep_submit="button:has-text('Confirmar')",
)

ATACADAO_CONFIG = MarketConfig(
    id="atacadao",
    display_name="Atacadão",
    base_url="https://www.atacadao.com.br",
    search_url_template="{base_url}/pesquisa?q={query}&page={page}",
    status=MarketStatus.ACTIVE,
    method=ScrapingMethod.PLAYWRIGHT,
    selectors=ATACADAO_SELECTORS,
    requests_per_minute=10,
    requires_cep=False,
    supports_pagination=True,
    max_pages=5,
)


# =============================================================================
# CONFIGURAÇÃO DO PÃO DE AÇÚCAR
# =============================================================================

PAO_ACUCAR_SELECTORS = MarketSelectors(
    product_container="div.CardStyled-sc-20azeh-0, div[class*='CardStyled-sc-20azeh']",
    product_title="a.Title-sc-20azeh-10, a[class*='Title-sc-20azeh'], a[class*='Title-sc']",
    product_price="p.PriceValue-sc-20azeh-4, p[class*='PriceValue-sc-20azeh'], p[class*='PriceValue-sc']",
    product_price_cents="",
    product_unit_price="",
    product_image="img.Image-sc-20azeh-2, img[class*='Image-sc'], img",
    product_link="a[href*='/produto/']",
    product_availability="",
    next_page="button[aria-label='Próxima página']",
    total_results="span[class*='total']",
    cep_input="input[placeholder*='CEP']",
    cep_submit="button:has-text('Confirmar')",
)

PAO_ACUCAR_CONFIG = MarketConfig(
    id="pao_acucar",
    display_name="Pão de Açúcar",
    base_url="https://www.paodeacucar.com",
    # IMPORTANTE: O Pão de Açúcar usa /busca?terms=TERMO
    # O scraper sobrescreve get_search_url para usar quote_plus corretamente
    search_url_template="{base_url}/busca?terms={query}",
    status=MarketStatus.ACTIVE,
    method=ScrapingMethod.PLAYWRIGHT,
    selectors=PAO_ACUCAR_SELECTORS,
    requests_per_minute=10,
    requires_cep=True,
    supports_pagination=True,
    max_pages=5,
)


# =============================================================================
# CONFIGURAÇÃO DO EXTRA (DESCONTINUADO)
# =============================================================================

EXTRA_SELECTORS = MarketSelectors(
    product_container="div[class*='product-card']",
    product_title="h2, h3",
    product_price="span[class*='price']",
    product_price_cents="",
    product_unit_price="",
    product_image="img",
    product_link="a",
    product_availability="",
    next_page="",
    total_results="",
    cep_input="input[placeholder*='CEP']",
    cep_submit="button[type='submit']",
)

EXTRA_CONFIG = MarketConfig(
    id="extra",
    display_name="Extra",
    base_url="https://www.extra.com.br",
    search_url_template="{base_url}/busca/{query}",
    status=MarketStatus.DEPRECATED,  # E-commerce Extra foi descontinuado
    method=ScrapingMethod.PLAYWRIGHT,
    selectors=EXTRA_SELECTORS,
    requests_per_minute=10,
    requires_cep=False,
    supports_pagination=False,
    max_pages=1,
)


# =============================================================================
# REGISTRO DE MERCADOS
# =============================================================================

MARKETS_CONFIG: dict[str, MarketConfig] = {
    "carrefour": CARREFOUR_CONFIG,
    "atacadao": ATACADAO_CONFIG,
    "pao_acucar": PAO_ACUCAR_CONFIG,
    "extra": EXTRA_CONFIG,
}


def get_market_config(market_id: str) -> MarketConfig:
    """
    Retorna configuração de um mercado.
    
    Args:
        market_id: ID do mercado
        
    Returns:
        Configuração do mercado
        
    Raises:
        ValueError: Se mercado não encontrado
    """
    if market_id not in MARKETS_CONFIG:
        raise ValueError(f"Mercado não encontrado: {market_id}")
    return MARKETS_CONFIG[market_id]


def get_active_markets() -> list[MarketConfig]:
    """
    Retorna lista de mercados ativos.
    
    Returns:
        Lista de configurações de mercados ativos
    """
    return [
        config for config in MARKETS_CONFIG.values()
        if config.status in (MarketStatus.ACTIVE, MarketStatus.DEVELOPMENT)
    ]