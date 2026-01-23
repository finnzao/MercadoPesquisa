"""
Hiperideal Scraper - VTEX REST API Otimizado
https://www.hiperideal.com.br

Refatorado para usar VTEXOptimizedScraper com:
- REST API com fallback automático (Intelligent Search → Legacy Search)
- 50 produtos por página (máximo VTEX)
- Connection pooling via httpx.AsyncClient (HTTP/2)
- Compressão gzip (~70% redução de payload)
- Retry com backoff exponencial (429, 503, 504)
"""

from typing import Dict, Optional

from config.markets import MarketConfig, MarketStatus, ScrapingMethod, MarketSelectors
from src.scrapers.vtex_graphql import VTEXOptimizedScraper


# Configuração do Hiperideal
HIPERIDEAL_SELECTORS = MarketSelectors(
    product_container="",
    product_title="",
    product_price="",
    product_price_cents="",
    product_unit_price="",
    product_image="",
    product_link="",
    product_availability="",
    next_page="",
    total_results="",
    cep_input="",
    cep_submit="",
)

HIPERIDEAL_CONFIG = MarketConfig(
    id="hiperideal",
    display_name="Hiperideal",
    base_url="https://www.hiperideal.com.br",
    search_url_template="{base_url}/busca?ft={query}",
    status=MarketStatus.ACTIVE,
    method=ScrapingMethod.API,
    selectors=HIPERIDEAL_SELECTORS,
    requests_per_minute=20,
    requires_cep=False,
    supports_pagination=True,
    max_pages=5,
)


class HiperidealScraper(VTEXOptimizedScraper):
    """
    Scraper para Hiperideal via VTEX REST API.
    
    Herda toda a lógica de VTEXOptimizedScraper:
    - Intelligent Search com fallback para Legacy Search
    - 50 produtos por página
    - Retry automático com backoff exponencial
    - Parsing de produtos VTEX padrão
    """
    
    def __init__(self, config: Optional[MarketConfig] = None):
        """
        Inicializa o scraper.
        
        Args:
            config: Configuração do mercado (opcional, usa HIPERIDEAL_CONFIG)
        """
        super().__init__(config or HIPERIDEAL_CONFIG)
    
    def _get_additional_headers(self) -> Dict[str, str]:
        """
        Headers adicionais específicos do Hiperideal.
        
        Returns:
            Dict com headers extras (vazio = usa padrão da classe base)
        """
        return {}


async def search_hiperideal(query: str, cep: Optional[str] = None, max_pages: int = 1):
    """
    Função de conveniência para busca rápida.
    
    Args:
        query: Termo de busca
        cep: CEP para localização (opcional)
        max_pages: Máximo de páginas a buscar
        
    Returns:
        ScraperResult com produtos encontrados
    """
    scraper = HiperidealScraper()
    return await scraper.search(query, cep, max_pages)