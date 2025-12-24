"""
Configurações dos Mercados - Versão Corrigida
==============================================

Atualizado em 24/12/2024 baseado no diagnóstico real.

Mudanças:
- Extra REMOVIDO (site descontinuou e-commerce de supermercado)
- Pão de Açúcar requer CEP para mostrar produtos
- URLs corrigidas
- Seletores atualizados baseados no HTML real

SUBSTITUA config/markets.py por este arquivo.
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
    requests_per_minute: int = 6
    custom_headers: dict = field(default_factory=dict)
    requires_cep: bool = False
    has_api: bool = False
    api_url: Optional[str] = None
    default_region: str = "São Paulo - SP"
    default_cep: str = "01310100"  # Av. Paulista
    
    def get_search_url(self, query: str, page: int = 0) -> str:
        """Monta a URL de busca com a query."""
        return self.search_url.format(query=query, page=page)


# =============================================================================
# CARREFOUR MERCADO
# URL testada: https://mercado.carrefour.com.br/busca/arroz%205kg
# Status: FUNCIONANDO (HTTP 200, produtos encontrados)
# =============================================================================
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
        # Baseado nas classes encontradas no diagnóstico
        product_container="div[class*='product'], article[class*='product'], a[class*='product'], div[data-testid*='product']",
        product_title="span[class*='productName'], h3[class*='product'], span[class*='name'], a[class*='product'] span",
        product_price="span[class*='price'], span[class*='sellingPrice'], div[class*='price'] span, p[class*='price']",
        product_price_cents="span[class*='cents'], span[class*='decimal']",
        product_unit_price="span[class*='unitPrice'], span[class*='perUnit']",
        product_link="a[href*='/p'], a[href*='/produto'], a[class*='product']",
        product_image="img[class*='product'], img[src*='vtex'], img[src*='carrefour']",
        next_page="button[class*='next'], a[aria-label*='próx']",
        cep_input="input[placeholder*='CEP'], input[id*='cep']",
        cep_submit="button[class*='cep'], button[type='submit']",
    ),
)


# =============================================================================
# ATACADÃO
# URL testada: https://www.atacadao.com.br/s?q=arroz%205kg&sort=score_desc&page=0
# Status: FUNCIONANDO (HTTP 200, 20 produtos encontrados)
# =============================================================================
ATACADAO_CONFIG = MarketConfig(
    id="atacadao",
    name="atacadao",
    display_name="Atacadão",
    base_url="https://www.atacadao.com.br",
    search_url="https://www.atacadao.com.br/s?q={query}&sort=score_desc&page={page}",
    method=ScrapingMethod.PLAYWRIGHT,
    status=MarketStatus.ACTIVE,
    requests_per_minute=6,
    requires_cep=True,  # Melhor definir CEP para preços corretos
    selectors=MarketSelectors(
        # Baseado nas classes: SearchInput_searchInput__pH9vT, etc
        product_container="div[class*='product'], article[class*='product'], a[class*='product'], div[class*='ProductCard']",
        product_title="h3[class*='product'], span[class*='productName'], p[class*='name'], h2[class*='name']",
        product_price="span[class*='price'], p[class*='price'], div[class*='price']",
        product_price_cents="span[class*='decimal'], span[class*='cents']",
        product_unit_price="span[class*='unit'], small[class*='unit']",
        product_link="a[href*='/p/'], a[href*='/produto']",
        product_image="img[class*='product'], img[src*='atacadao'], img[loading='lazy']",
        next_page="button[class*='next'], a[aria-label*='Next']",
        cep_input="input[placeholder*='CEP'], input[name*='cep']",
        cep_submit="button[class*='cep'], button[class*='location']",
    ),
)


# =============================================================================
# PÃO DE AÇÚCAR
# URL testada: https://www.paodeacucar.com/busca?terms=arroz%205kg
# Status: REQUER CEP - Sem CEP mostra "Nenhum resultado encontrado"
# Seletores baseados no HTML real do diagnóstico
# =============================================================================
PAO_ACUCAR_CONFIG = MarketConfig(
    id="pao_acucar",
    name="pao_acucar",
    display_name="Pão de Açúcar",
    base_url="https://www.paodeacucar.com",
    search_url="https://www.paodeacucar.com/busca?terms={query}",
    method=ScrapingMethod.PLAYWRIGHT,
    status=MarketStatus.DEVELOPMENT,
    requests_per_minute=6,
    requires_cep=True,  # OBRIGATÓRIO para mostrar produtos
    selectors=MarketSelectors(
        # Classes encontradas: BoxStyled-sc-iohoom-0, Item-sc-xxx, etc
        # O site usa styled-components, então classes são dinâmicas
        product_container="div[class*='ProductCard'], div[class*='product-card'], article[class*='product'], a[class*='product']",
        product_title="span[class*='name'], h3[class*='product'], p[class*='title'], a[class*='product-name']",
        product_price="span[class*='price'], p[class*='price'], div[class*='price'] span",
        product_price_cents="span[class*='cents'], span[class*='decimal']",
        product_unit_price="span[class*='unit-price'], small[class*='price-per']",
        product_link="a[href*='/produto/'], a[href*='/p/'], a[class*='product']",
        product_image="img[class*='product'], img[loading='lazy'], img[src*='gpa.digital']",
        next_page="button[aria-label*='próxima'], a[class*='pagination-next']",
        cep_input="input[placeholder*='CEP'], input[id*='cep']",
        cep_submit="button[class*='location'], button[class*='cep']",
    ),
)


# =============================================================================
# EXTRA - DESCONTINUADO
# O site Extra.com.br não oferece mais e-commerce de supermercado
# Redireciona para Casas Bahia. NÃO INCLUIR.
# =============================================================================
# EXTRA_CONFIG foi removido


# =============================================================================
# Dicionário de mercados ativos
# =============================================================================
MARKETS_CONFIG: dict[str, MarketConfig] = {
    "carrefour": CARREFOUR_CONFIG,
    "atacadao": ATACADAO_CONFIG,
    "pao_acucar": PAO_ACUCAR_CONFIG,
    # "extra" foi removido - site descontinuado
}


def get_market_config(market_id: str) -> MarketConfig:
    """Retorna a configuração de um mercado específico."""
    if market_id not in MARKETS_CONFIG:
        raise ValueError(
            f"Mercado '{market_id}' não configurado. "
            f"Disponíveis: {list(MARKETS_CONFIG.keys())}"
        )
    return MARKETS_CONFIG[market_id]


def get_active_markets() -> list[MarketConfig]:
    """Retorna lista de mercados ativos para scraping."""
    return [
        config for config in MARKETS_CONFIG.values()
        if config.status in (MarketStatus.ACTIVE, MarketStatus.DEVELOPMENT)
    ]


def get_markets_requiring_cep() -> list[str]:
    """Retorna lista de IDs de mercados que requerem CEP."""
    return [
        config.id for config in MARKETS_CONFIG.values()
        if config.requires_cep
    ]