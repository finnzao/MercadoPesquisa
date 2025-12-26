"""
Scraper específico para Pão de Açúcar - VERSÃO CORRIGIDA.
https://www.paodeacucar.com

CORREÇÃO: Sobrescreve _build_search_url() para usar quote_plus()
pois o Pão de Açúcar usa query string (?terms=...) que precisa de + para espaços.

Estrutura identificada:
- Produtos em <div class="CardStyled-sc-20azeh-0">
- Preço em <p class="PriceValue-sc-20azeh-4">
- Título em <a class="Title-sc-20azeh-10">
"""

import re
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin, quote_plus

from playwright.async_api import Page, ElementHandle

from config.markets import PAO_ACUCAR_CONFIG, MarketConfig
from src.core.models import RawProduct
from src.scrapers.base import BaseScraper


class PaoDeAcucarScraper(BaseScraper):
    """
    Scraper para Pão de Açúcar.
    Site de supermercado com entrega em domicílio.
    
    CORREÇÃO: Usa quote_plus() para encoding da URL de busca.
    """
    
    def __init__(self, config: Optional[MarketConfig] = None):
        """Inicializa o scraper."""
        super().__init__(config or PAO_ACUCAR_CONFIG)
    
    def _build_search_url(self, query: str, page: int = 0) -> str:
        """
        Constrói a URL de busca para o Pão de Açúcar.
        
        CORREÇÃO: Usa quote_plus() ao invés de quote() porque o Pão de Açúcar
        usa query string (?terms=...) e espera espaços como +.
        
        Exemplo:
            query="arroz 5 kg" -> https://www.paodeacucar.com/busca?terms=arroz+5+kg
        """
        encoded_query = quote_plus(query)
        url = f"{self.config.base_url}/busca?terms={encoded_query}"
        if page > 0:
            url += f"&page={page}"
        return url
    
    async def extract_products(
        self,
        page: Page,
        search_query: str,
        cep: Optional[str] = None,
    ) -> list[RawProduct]:
        """Extrai produtos da página de resultados do Pão de Açúcar."""
        products = []
        
        await self._wait_for_products_load(page)
        await self._scroll_to_load_all(page)
        
        # Tenta fechar modal de CEP se aparecer
        await self._close_cep_modal(page)
        
        product_cards = await page.query_selector_all(
            "div.CardStyled-sc-20azeh-0"
        )
        
        if not product_cards:
            self.logger.debug("Tentando seletores alternativos...")
            product_cards = await page.query_selector_all(
                "div[class*='CardStyled-sc-20azeh']"
            )
        
        if not product_cards:
            product_cards = await page.query_selector_all(
                "div.MuiGrid-item div[class*='Card-sc']"
            )
        
        if not product_cards:
            product_cards = await page.query_selector_all(
                "div:has(p[class*='PriceValue']):has(a[href*='/produto/'])"
            )
        
        self.logger.info(
            "Cards de produto encontrados",
            count=len(product_cards),
        )
        
        for idx, card in enumerate(product_cards):
            try:
                product = await self._extract_single_product(
                    card,
                    page,
                    search_query,
                    cep,
                    idx + 1,
                )
                if product:
                    products.append(product)
                    self.logger.debug(
                        "Produto extraído",
                        title=product.title[:50] if product.title else "N/A",
                        price=product.price_raw,
                    )
            except Exception as e:
                self.logger.debug(
                    "Erro ao extrair produto",
                    index=idx,
                    error=str(e),
                )
                continue
        
        return products
    
    async def _close_cep_modal(self, page: Page) -> None:
        """Tenta fechar o modal de CEP se estiver aberto."""
        try:
            # Tenta fechar clicando no X ou em "Fechar"
            close_selectors = [
                "button[aria-label='close']",
                "button[aria-label='fechar']",
                "button:has-text('Fechar')",
                "button:has-text('X')",
                "div[role='dialog'] button:first-child",
            ]
            
            for selector in close_selectors:
                try:
                    close_btn = await page.query_selector(selector)
                    if close_btn:
                        await close_btn.click()
                        await page.wait_for_timeout(500)
                        self.logger.debug("Modal de CEP fechado")
                        return
                except Exception:
                    continue
            
            # Se não encontrou botão, tenta clicar fora do modal
            await page.click("body", position={"x": 10, "y": 10}, force=True)
            await page.wait_for_timeout(300)
            
        except Exception as e:
            self.logger.debug(f"Erro ao fechar modal de CEP: {e}")
    
    async def _wait_for_products_load(self, page: Page) -> None:
        """Aguarda o carregamento dos produtos na página."""
        try:
            await page.wait_for_selector(
                "div.MuiGrid-container, div[class*='CardStyled'], div[class*='Card-sc']",
                timeout=15000,
            )
            await page.wait_for_timeout(2000)
        except Exception as e:
            self.logger.warning(f"Timeout aguardando produtos: {e}")
    
    async def _scroll_to_load_all(self, page: Page) -> None:
        """Faz scroll para carregar produtos lazy-loaded."""
        try:
            for i in range(5):
                await page.evaluate("window.scrollBy(0, window.innerHeight)")
                await page.wait_for_timeout(800)
            await page.evaluate("window.scrollTo(0, 0)")
            await page.wait_for_timeout(500)
        except Exception as e:
            self.logger.debug(f"Erro no scroll: {e}")
    
    async def _extract_single_product(
        self,
        card: ElementHandle,
        page: Page,
        search_query: str,
        cep: Optional[str],
        index: int,
    ) -> Optional[RawProduct]:
        """Extrai dados de um único card de produto."""
        
        title = await self._extract_title(card)
        if not title:
            return None
        
        price_raw = await self._extract_price(card)
        if not price_raw:
            return None
        
        product_url = await self._extract_product_url(card, page)
        image_url = await self._extract_image_url(card)
        is_available = await self._check_availability(card)
        
        return RawProduct(
            market_id=self.market_id,
            title=title,
            price_raw=price_raw,
            unit_price_raw=None,
            url=product_url,
            image_url=image_url,
            availability_raw="Disponível" if is_available else "Indisponível",
            search_query=search_query,
            cep=cep,
            collected_at=datetime.now(),
            extra_data={
                "position": index,
            },
        )
    
    async def _extract_title(self, card: ElementHandle) -> Optional[str]:
        """Extrai o título do produto."""
        selectors = [
            "a.Title-sc-20azeh-10",
            "a[class*='Title-sc-20azeh']",
            "a[class*='Title-sc']",
        ]
        
        for selector in selectors:
            try:
                elem = await card.query_selector(selector)
                if elem:
                    text = await elem.inner_text()
                    if text and text.strip():
                        return text.strip()
            except Exception:
                continue
        
        try:
            img = await card.query_selector("img")
            if img:
                alt = await img.get_attribute("alt")
                if alt and alt.strip():
                    return alt.strip()
        except Exception:
            pass
        
        try:
            link = await card.query_selector("a[href*='/produto/']")
            if link:
                text = await link.inner_text()
                if text and text.strip():
                    return text.strip()
        except Exception:
            pass
        
        return None
    
    async def _extract_price(self, card: ElementHandle) -> Optional[str]:
        """Extrai o preço do produto."""
        selectors = [
            "p.PriceValue-sc-20azeh-4",
            "p[class*='PriceValue-sc-20azeh']",
            "p[class*='PriceValue-sc']",
            "div[class*='PriceContainer'] p",
        ]
        
        for selector in selectors:
            try:
                elem = await card.query_selector(selector)
                if elem:
                    text = await elem.inner_text()
                    if text and "R$" in text:
                        return self._clean_price(text)
            except Exception:
                continue
        
        try:
            all_text = await card.inner_text()
            match = re.search(r'R\$\s*[\d.,]+', all_text)
            if match:
                return self._clean_price(match.group())
        except Exception:
            pass
        
        return None
    
    async def _extract_product_url(self, card: ElementHandle, page: Page) -> str:
        """Extrai a URL do produto."""
        try:
            link = await card.query_selector("a[href*='/produto/']")
            if link:
                href = await link.get_attribute("href")
                if href:
                    return urljoin(self.config.base_url, href)
        except Exception:
            pass
        
        return page.url
    
    async def _extract_image_url(self, card: ElementHandle) -> Optional[str]:
        """Extrai a URL da imagem do produto."""
        try:
            img = await card.query_selector("img.Image-sc-20azeh-2")
            if not img:
                img = await card.query_selector("img[class*='Image-sc']")
            if not img:
                img = await card.query_selector("img")
            
            if img:
                src = await img.get_attribute("src")
                if src and not src.startswith("data:"):
                    return src
                
                data_src = await img.get_attribute("data-src")
                if data_src:
                    return data_src
                
                srcset = await img.get_attribute("srcset")
                if srcset:
                    urls = re.findall(r'(https?://[^\s]+)', srcset)
                    if urls:
                        return urls[0]
        except Exception:
            pass
        
        return None
    
    async def _check_availability(self, card: ElementHandle) -> bool:
        """Verifica se o produto está disponível."""
        try:
            price_elem = await card.query_selector("p[class*='PriceValue']")
            if price_elem:
                text = await price_elem.inner_text()
                if text and "R$" in text:
                    return True
            
            button = await card.query_selector("button")
            if button:
                is_disabled = await button.get_attribute("disabled")
                if is_disabled is None:
                    return True
        except Exception:
            pass
        
        return True
    
    def _clean_price(self, price_text: str) -> str:
        """Limpa e normaliza texto de preço."""
        if not price_text:
            return ""
        
        cleaned = " ".join(price_text.split())
        
        match = re.search(r'R\$?\s*([\d.,]+)', cleaned)
        if match:
            value = match.group(1)
            if "." in value and "," not in value:
                value = value.replace(".", ",")
            return f"R$ {value}"
        
        return cleaned
    
    async def set_location(
        self,
        page: Page,
        cep: str,
    ) -> bool:
        """Configura CEP no Pão de Açúcar."""
        try:
            self.logger.debug("Tentando configurar CEP", cep=cep)
            
            await page.goto(
                self.config.base_url,
                wait_until="domcontentloaded",
            )
            await page.wait_for_timeout(2000)
            
            cep_modal = await page.query_selector(
                "div[class*='modal'], div[class*='Modal'], div[role='dialog']"
            )
            
            if cep_modal:
                self.logger.debug("Modal de CEP detectado")
                
                cep_input = await page.query_selector(
                    "input[placeholder*='CEP'], input[type='text'][maxlength='9'], input[name*='cep']"
                )
                
                if cep_input:
                    await cep_input.clear()
                    await cep_input.type(cep, delay=100)
                    await page.wait_for_timeout(500)
                    
                    confirm_btn = await page.query_selector(
                        "button:has-text('Confirmar'), button:has-text('Buscar'), button[type='submit']"
                    )
                    if confirm_btn:
                        await confirm_btn.click()
                        await page.wait_for_timeout(2000)
                        
                        self.logger.info("CEP configurado via modal", cep=cep)
                        return True
            
            location_btn = await page.query_selector(
                "button[class*='location'], button[class*='cep'], button[data-testid*='location']"
            )
            
            if location_btn:
                await location_btn.click()
                await page.wait_for_timeout(1000)
                
                cep_input = await page.query_selector("input[placeholder*='CEP'], input[type='text']")
                
                if cep_input:
                    await cep_input.clear()
                    await cep_input.type(cep, delay=100)
                    await page.wait_for_timeout(500)
                    
                    confirm_btn = await page.query_selector(
                        "button:has-text('Confirmar'), button:has-text('Buscar'), button[type='submit']"
                    )
                    if confirm_btn:
                        await confirm_btn.click()
                        await page.wait_for_timeout(2000)
                        
                        self.logger.info("CEP configurado via header", cep=cep)
                        return True
            
            self.logger.warning(
                "Não foi possível configurar CEP, continuando sem",
                cep=cep,
            )
            return False
            
        except Exception as e:
            self.logger.warning(
                "Falha ao configurar CEP",
                cep=cep,
                error=str(e),
            )
            return False
    
    async def get_total_results(self, page: Page) -> Optional[int]:
        """Extrai o número total de resultados da busca."""
        try:
            selectors = [
                "span[class*='total']",
                "p[class*='results']",
                "div[class*='count']",
            ]
            
            for selector in selectors:
                elem = await page.query_selector(selector)
                if elem:
                    text = await elem.inner_text()
                    if text:
                        match = re.search(r'\d+', text.replace(".", ""))
                        if match:
                            return int(match.group())
        except Exception:
            pass
        
        return None