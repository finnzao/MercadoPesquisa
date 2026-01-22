"""Rede Mix Scraper - VTEX REST API"""

from typing import Dict, Optional

from config.markets import MarketConfig, MarketStatus, ScrapingMethod, MarketSelectors
from src.scrapers.vtex_graphql import VTEXOptimizedScraper


REDEMIX_SELECTORS = MarketSelectors(
    product_container="", product_title="", product_price="", product_price_cents="",
    product_unit_price="", product_image="", product_link="", product_availability="",
    next_page="", total_results="", cep_input="", cep_submit="",
)

REDEMIX_CONFIG = MarketConfig(
    id="redemix", display_name="Rede Mix", base_url="https://www.redemix.com.br",
    search_url_template="{base_url}/busca?ft={query}", status=MarketStatus.ACTIVE,
    method=ScrapingMethod.API, selectors=REDEMIX_SELECTORS, requests_per_minute=20,
    requires_cep=False, supports_pagination=True, max_pages=5,
)


class RedeMixScraper(VTEXOptimizedScraper):
    """Scraper para Rede Mix via VTEX REST API."""
    
    def __init__(self, config: Optional[MarketConfig] = None):
        super().__init__(config or REDEMIX_CONFIG)
    
    def _get_additional_headers(self) -> Dict[str, str]:
        return {}


RedeMix = RedeMixScraper


async def search_redemix(query: str, cep: Optional[str] = None, max_pages: int = 1):
    scraper = RedeMixScraper()
    return await scraper.search(query, cep, max_pages)