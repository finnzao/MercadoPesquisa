"""
Scraper específico para Carrefour Mercado.
https://www.carrefour.com.br
"""

from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

from playwright.async_api import Page

from config.markets import CARREFOUR_CONFIG
from src.core.models import RawProduct
from src.scrapers.base import BaseScraper


class CarrefourScraper(BaseScraper):
    """
    Scraper para Carrefour Mercado.
    Usa Playwright devido ao carregamento dinâmico via JavaScript.
    """
    
    def __init__(self, config=None):
        """Inicializa o scraper."""
        super().__init__(config or CARREFOUR_CONFIG)
    
    async def extract_products(
        self,
        page: Page,
        search_query: str,
        cep: Optional[str] = None,
    ) -> list[RawProduct]:
        """
        Extrai produtos da página de resultados do Carrefour.
        
        Args:
            page: Página do Playwright
            search_query: Termo buscado
            cep: CEP configurado
            
        Returns:
            Lista de produtos extraídos
        """
        products = []
        
        # Encontra todos os cards de produto
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
    
    async def _extract_single_product(
        self,
        card,
        page: Page,
        search_query: str,
        cep: Optional[str],
    ) -> Optional[RawProduct]:
        """
        Extrai dados de um único card de produto.
        
        Args:
            card: Elemento do card
            page: Página do Playwright
            search_query: Termo buscado
            cep: CEP configurado
            
        Returns:
            RawProduct ou None se falhar
        """
        # Título (obrigatório)
        title = await self._safe_get_text(
            card,
            self.selectors.product_title,
        )
        if not title:
            return None
        
        # Preço (obrigatório)
        price_int = await self._safe_get_text(
            card,
            self.selectors.product_price,
        )
        price_cents = await self._safe_get_text(
            card,
            self.selectors.product_price_cents,
        )
        
        if not price_int:
            return None
        
        # Monta preço completo
        price_raw = price_int
        if price_cents:
            price_raw = f"{price_int},{price_cents}"
        
        # Preço por unidade (opcional - alguns sites já fornecem)
        unit_price_raw = await self._safe_get_text(
            card,
            self.selectors.product_unit_price,
        )
        
        # URL do produto
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
        Configura CEP no Carrefour.
        
        Args:
            page: Página do Playwright
            cep: CEP a configurar
            
        Returns:
            True se sucesso
        """
        try:
            # Navega para home primeiro
            await page.goto(
                self.config.base_url,
                wait_until="domcontentloaded",
            )
            
            # Procura campo de CEP
            cep_input = await page.query_selector(self.selectors.cep_input)
            if not cep_input:
                self.logger.debug("Campo de CEP não encontrado")
                return False
            
            # Limpa e preenche CEP
            await cep_input.clear()
            await cep_input.type(cep, delay=100)
            
            # Clica no botão de confirmar
            if self.selectors.cep_submit:
                submit_btn = await page.query_selector(self.selectors.cep_submit)
                if submit_btn:
                    await submit_btn.click()
                    # Aguarda confirmação
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