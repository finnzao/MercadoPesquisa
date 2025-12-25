"""
Configurações dos mercados com URLs CORRETAS.
Atualizado em 25/12/2024 - Seletores corrigidos baseados em análise real do HTML.

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
    # Novos campos para extração mais precisa
    bulk_price_indicator: Optional[str] = None
    discount_badge: Optional[str] = None


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
    default_region: str = "São Paulo - SP"
    default_cep: str = "02170-901"
    
    def get_search_url(self, query: str, page: int = 0) -> str:
        """Monta a URL de busca com a query."""
        return self.search_url.format(query=query, page=page)


# =============================================================================
# CONFIGURAÇÕES DOS MERCADOS
# =============================================================================

# -----------------------------------------------------------------------------
# ATACADÃO - SELETORES CORRIGIDOS BASEADOS NO HTML REAL
# URL: https://www.atacadao.com.br/s?q=TERMO&sort=score_desc&page=0
# 
# Estrutura identificada no HTML:
# - Container: <li> contendo <article class="relative flex flex-col...">
# - Título: <h3 title="..."> com link <a> interno
# - Preço atacado: div com "A partir de X unid." + preço em <p class="text-lg...">
# - Preço unitário: "ou R$ X / cada"
# - Imagem: <img> dentro de data-product-card-image
# - Link: <a> com href contendo "/p" e data-testid="product-link"
# -----------------------------------------------------------------------------
ATACADAO_CONFIG = MarketConfig(
    id="atacadao",
    name="atacadao",
    display_name="Atacadão",
    base_url="https://www.atacadao.com.br",
    search_url="https://www.atacadao.com.br/s?q={query}&sort=score_desc&page={page}",
    method=ScrapingMethod.PLAYWRIGHT,
    status=MarketStatus.ACTIVE,  # Agora funcional!
    requests_per_minute=6,
    requires_cep=True,
    default_cep="02170-901",  # Vila Maria, São Paulo
    selectors=MarketSelectors(
        # Container: cada item da lista de produtos
        # <li style="order: N;"><article class="relative flex flex-col h-full...">
        product_container="ul.grid > li article.relative",
        
        # Título: <h3 title="Nome do Produto">
        product_title="h3[title]",
        
        # Preço principal (atacado): <p class="text-lg xl:text-xl text-neutral-500 font-bold">
        product_price="section[data-testid='store-product-card-content'] p.text-lg.font-bold",
        
        # Preço centavos já vem junto no preço principal
        product_price_cents=None,
        
        # Preço unitário: texto "ou R$ X / cada"
        product_unit_price="div.flex.items-center.gap-1 p.text-sm.font-bold",
        
        # Imagem do produto
        product_image="div[data-product-card-image] img",
        
        # Link do produto: <a data-testid="product-link" href="...">
        product_link="a[data-testid='product-link']",
        
        # Quantidade mínima para preço atacado
        bulk_price_indicator="div.flex.text-\\[10px\\].text-neutral-500",
        
        # Badge de desconto
        discount_badge="div[data-test='discount-badge']",
        
        # Disponibilidade (botão de adicionar)
        product_availability="button[data-testid='buy-button']",
        
        # Paginação
        next_page="a[href*='page='] button, div.flex.justify-center a:last-child",
        
        # Total de resultados
        total_results="h2[data-testid='total-product-count'] span.font-bold",
        
        # CEP
        cep_input="input[placeholder*='CEP'], button[data-testid='userZipCode']",
        cep_submit="button:has-text('Informar Localização')",
    ),
)

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
    status=MarketStatus.ACTIVE,
    requests_per_minute=6,
    requires_cep=False,
    selectors=MarketSelectors(
        product_container='a[data-testid="search-product-card"]',
        product_title="h2",
        product_price="span.text-blue-royal.font-bold, span[class*='text-blue-royal'][class*='font-bold']",
        product_price_cents=None,
        product_unit_price="p[class*='text-gray-medium']",
        product_link=None,
        product_image="img",
        product_availability=None,
        next_page="button[aria-label*='próx'], button[aria-label*='Next']",
        cep_input="input[placeholder*='CEP']",
        cep_submit="button[type='submit']",
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
    requires_cep=True,
    selectors=MarketSelectors(
        product_container="div[class*='product-card'], div[data-testid*='product'], article[class*='product']",
        product_title="h3[class*='product'], a[class*='product-name'], span[class*='name']",
        product_price="span[class*='price'], p[class*='price-value'], div[class*='price']",
        product_price_cents="span[class*='cents'], span[class*='decimal']",
        product_unit_price="span[class*='unit-price'], small[class*='price-per']",
        product_link="a[class*='product'], a[href*='/produto/'], a[href*='/p/']",
        product_image="img[class*='product'], img[loading='lazy']",
        product_availability="span[class*='stock'], div[class*='availability']",
        next_page="button[class*='next'], button[aria-label*='próxima']",
        cep_input="input[placeholder*='CEP']",
        cep_submit="button[class*='location'], button[class*='cep']",
    ),
)


# REGISTRY DE MERCADOS
MARKETS_CONFIG: dict[str, MarketConfig] = {
    "atacadao": ATACADAO_CONFIG,
    "carrefour": CARREFOUR_CONFIG,
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