"""
Scraper específico para Pão de Açúcar.
https://www.paodeacucar.com
"""

from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

from playwright.async_api import Page

from config.markets import PAO_ACUCAR_CONFIG
from src.core.models import RawProduct
from src.scrapers.base import BaseScraper


class PaoDeAcucarScraper(BaseScraper):
    """
    Scraper para Pão de Açúcar.
    Parte do grupo GPA, compartilha estrutura com Extra.
    """
    
    def __init__(self, config=None):
        """Inicializa o scraper."""
        super().__init__(config or PAO_ACUCAR_CONFIG)
    
    async def extract_products(
        self,
        page: Page,
        search_query: str,
        cep: Optional[str] = None,
    ) -> list[RawProduct]:
        """
        Extrai produtos da página de resultados do Pão de Açúcar.
        """
        products = []
        
        # Sites do GPA costumam ter carregamento lazy
        await self._scroll_to_load_products(page)
        
        product_cards = await page.query_selector_all(
            self.selectors.product_container
        )
        
        self.logger.debug(
            "Cards encontrados",
            count=len(product_cards),
        )
        
        for card in product_cards:
            try:
                product = await self._extract_single_product(
                    card,
                    page,
                    search_query,
                    cep,
                )
                if product:
                    products.append(product)
            except Exception as e:
                self.logger.debug(
                    "Erro ao extrair produto",
                    error=str(e),
                )
                continue
        
        return products
    
    async def _scroll_to_load_products(self, page: Page) -> None:
        """
        Faz scroll para carregar produtos lazy-loaded.
        """
        for _ in range(3):
            await page.evaluate("window.scrollBy(0, window.innerHeight)")
            await page.wait_for_timeout(500)
    
    async def _extract_single_product(
        self,
        card,
        page: Page,
        search_query: str,
        cep: Optional[str],
    ) -> Optional[RawProduct]:
        """
        Extrai dados de um único card de produto.
        """
        # Título
        title = await self._safe_get_text(
            card,
            self.selectors.product_title,
        )
        if not title:
            return None
        
        # Preço
        price_value = await self._safe_get_text(
            card,
            self.selectors.product_price,
        )
        price_cents = await self._safe_get_text(
            card,
            self.selectors.product_price_cents,
        )
        
        if not price_value:
            return None
        
        # Monta preço
        price_raw = f"{price_value},{price_cents}" if price_cents else price_value
        
        # Preço por unidade
        unit_price_raw = await self._safe_get_text(
            card,
            self.selectors.product_unit_price,
        )
        
        # URL
        product_link = await self._safe_get_attribute(
            card,
            self.selectors.product_link,
            "href",
        )
        product_url = urljoin(self.config.base_url, product_link) if product_link else page.url
        
        # Imagem
        image_url = await self._safe_get_attribute(
            card,
            self.selectors.product_image,
            "src",
        )
        
        # Disponibilidade
        availability_raw = await self._safe_get_text(
            card,
            self.selectors.product_availability,
        )
        
        return RawProduct(
            market_id=self.market_id,
            title=title,
            price_raw=price_raw,
            unit_price_raw=unit_price_raw if unit_price_raw else None,
            url=product_url,
            image_url=image_url if image_url else None,
            availability_raw=availability_raw if availability_raw else None,
            search_query=search_query,
            cep=cep,
            collected_at=datetime.now(),
        )
    
    async def set_location(
        self,
        page: Page,
        cep: str,
    ) -> bool:
        """
        Configura CEP no Pão de Açúcar.
        """
        try:
            await page.goto(
                self.config.base_url,
                wait_until="domcontentloaded",
            )
            
            # Sites GPA geralmente têm modal de CEP
            cep_input = await page.query_selector(self.selectors.cep_input)
            if not cep_input:
                # Tenta abrir modal
                await page.click("text=Informe seu CEP", timeout=3000)
                await page.wait_for_timeout(1000)
                cep_input = await page.query_selector(self.selectors.cep_input)
            
            if not cep_input:
                return False
            
            await cep_input.clear()
            await cep_input.type(cep, delay=100)
            
            if self.selectors.cep_submit:
                submit_btn = await page.query_selector(self.selectors.cep_submit)
                if submit_btn:
                    await submit_btn.click()
                    await page.wait_for_timeout(2000)
            
            self.logger.info("CEP configurado", cep=cep)
            return True
            
        except Exception as e:
            self.logger.warning(
                "Falha ao configurar CEP",
                cep=cep,
                error=str(e),
            )
            return False