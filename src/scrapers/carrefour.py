"""
Scraper específico para Carrefour Mercado.
https://mercado.carrefour.com.br

ATUALIZADO: 24/12/2024 - Seletores corrigidos baseados no HTML real.
"""

from datetime import datetime
from typing import Optional
from urllib.parse import urljoin, quote

from playwright.async_api import Page

from config.markets import CARREFOUR_CONFIG
from src.core.models import RawProduct
from src.scrapers.base import BaseScraper


class CarrefourScraper(BaseScraper):
    """
    Scraper para Carrefour Mercado.
    
    Estrutura do site (24/12/2024):
    - Container: <a data-testid="search-product-card" href="/produto/p">
    - Título: <h2 class="text-sm...">Nome do Produto</h2>
    - Preço: <span class="text-blue-royal font-bold...">R$ 19,79</span>
    - Imagem: <img src="..." alt="...">
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
        
        # Scroll para carregar lazy loading
        await self._scroll_to_load(page)
        
        # Seletor principal: cards de produto
        # O Carrefour usa <a data-testid="search-product-card"> como container
        product_cards = await page.query_selector_all(
            'a[data-testid="search-product-card"]'
        )
        
        self.logger.info(
            "Cards encontrados",
            count=len(product_cards),
            market="carrefour",
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
    
    async def _scroll_to_load(self, page: Page) -> None:
        """Scroll para carregar produtos lazy-loaded."""
        for _ in range(5):
            await page.evaluate("window.scrollBy(0, 600)")
            await page.wait_for_timeout(300)
    
    async def _extract_single_product(
        self,
        card,
        page: Page,
        search_query: str,
        cep: Optional[str],
    ) -> Optional[RawProduct]:
        """
        Extrai dados de um único card de produto.
        
        Estrutura do card:
        <a data-testid="search-product-card" href="/produto-nome/p">
            <div>
                <img src="..." alt="Nome do Produto">
            </div>
            <div>
                <h2>Nome do Produto</h2>
                <span class="text-blue-royal font-bold">R$ 19,79</span>
            </div>
        </a>
        """
        # =====================================================================
        # TÍTULO
        # =====================================================================
        # Tenta h2 primeiro (é o seletor principal)
        title = None
        
        # Método 1: h2 dentro do card
        h2 = await card.query_selector("h2")
        if h2:
            title = await h2.inner_text()
        
        # Método 2: alt da imagem (fallback)
        if not title:
            img = await card.query_selector("img")
            if img:
                title = await img.get_attribute("alt")
        
        if not title or not title.strip():
            return None
        
        title = title.strip()
        
        # =====================================================================
        # PREÇO
        # =====================================================================
        price_raw = None
        
        # Método 1: span com classes específicas do Carrefour
        price_selectors = [
            "span.text-blue-royal.font-bold",
            "span[class*='text-blue-royal'][class*='font-bold']",
            "span[class*='text-lg']",
        ]
        
        for selector in price_selectors:
            try:
                price_el = await card.query_selector(selector)
                if price_el:
                    text = await price_el.inner_text()
                    if text and "R$" in text:
                        price_raw = text.strip()
                        break
            except:
                continue
        
        # Método 2: busca qualquer span com R$
        if not price_raw:
            spans = await card.query_selector_all("span")
            for span in spans:
                try:
                    text = await span.inner_text()
                    if text and "R$" in text and any(c.isdigit() for c in text):
                        price_raw = text.strip()
                        break
                except:
                    continue
        
        if not price_raw:
            return None
        
        # =====================================================================
        # URL DO PRODUTO
        # =====================================================================
        # O próprio card é um <a>, então pegamos o href dele
        product_href = await card.get_attribute("href")
        
        if product_href:
            # Se começa com /, é relativo
            if product_href.startswith("/"):
                product_url = urljoin(self.config.base_url, product_href)
            else:
                product_url = product_href
        else:
            product_url = page.url
        
        # =====================================================================
        # IMAGEM
        # =====================================================================
        image_url = None
        img = await card.query_selector("img")
        if img:
            image_url = await img.get_attribute("src")
        
        # =====================================================================
        # PREÇO POR UNIDADE (opcional)
        # =====================================================================
        unit_price_raw = None
        # Carrefour às vezes mostra preço por kg/L em um elemento separado
        unit_selectors = [
            "p[class*='text-gray-medium']",
            "span[class*='text-xs']",
        ]
        
        for selector in unit_selectors:
            try:
                unit_el = await card.query_selector(selector)
                if unit_el:
                    text = await unit_el.inner_text()
                    if text and ("/" in text or "por" in text.lower()):
                        unit_price_raw = text.strip()
                        break
            except:
                continue
        
        # =====================================================================
        # CRIAR PRODUTO
        # =====================================================================
        return RawProduct(
            market_id=self.market_id,
            title=title,
            price_raw=price_raw,
            unit_price_raw=unit_price_raw,
            url=product_url,
            image_url=image_url,
            availability_raw="Disponível",  # Se aparece na busca, está disponível
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
            await page.wait_for_timeout(2000)
            
            # Procura campo de CEP (vários seletores possíveis)
            cep_selectors = [
                "input[placeholder*='CEP']",
                "input[placeholder*='cep']",
                "input[id*='cep']",
                "input[name*='cep']",
                "input[data-testid*='cep']",
            ]
            
            cep_input = None
            for selector in cep_selectors:
                cep_input = await page.query_selector(selector)
                if cep_input:
                    break
            
            if not cep_input:
                self.logger.debug("Campo de CEP não encontrado")
                return False
            
            # Limpa e preenche CEP
            await cep_input.clear()
            await cep_input.type(cep, delay=100)
            
            # Tenta confirmar
            confirm_selectors = [
                "button[type='submit']",
                "button[class*='cep']",
                "button:has-text('Confirmar')",
                "button:has-text('OK')",
            ]
            
            for selector in confirm_selectors:
                try:
                    btn = await page.query_selector(selector)
                    if btn:
                        await btn.click()
                        await page.wait_for_timeout(2000)
                        break
                except:
                    continue
            
            self.logger.info("CEP configurado", cep=cep)
            return True
            
        except Exception as e:
            self.logger.warning(
                "Falha ao configurar CEP",
                cep=cep,
                error=str(e),
            )
            return False