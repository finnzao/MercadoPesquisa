"""
Scraper específico para Pão de Açúcar - VERSÃO CORRIGIDA.
https://www.paodeacucar.com

Baseado na análise real do HTML em 25/12/2024.

Estrutura identificada:
- Produtos em <div class="CardStyled-sc-20azeh-0">
- 75 cards de produto na busca "arroz 5kg"
- Preço em <p class="PriceValue-sc-20azeh-4">
- Título em <a class="Title-sc-20azeh-10">
- Imagem em <img class="Image-sc-20azeh-2">
- Links: a[href*="/produto/"]
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
    
    Particularidades:
    - Requer CEP para mostrar produtos disponíveis
    - Preços podem variar por região
    - Interface React com classes CSS dinâmicas (styled-components)
    """
    
    def __init__(self, config: Optional[MarketConfig] = None):
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
        
        Args:
            page: Página do Playwright
            search_query: Termo buscado
            cep: CEP configurado
            
        Returns:
            Lista de produtos extraídos
        """
        products = []
        
        # Aguarda carregamento completo dos produtos
        await self._wait_for_products_load(page)
        
        # Faz scroll para garantir carregamento de lazy loading
        await self._scroll_to_load_all(page)
        
        # Busca os containers de produto
        # Estrutura: div.CardStyled-sc-20azeh-0
        product_cards = await page.query_selector_all(
            "div.CardStyled-sc-20azeh-0"
        )
        
        # Fallback: tenta seletores alternativos se não encontrar
        if not product_cards:
            self.logger.debug("Tentando seletores alternativos...")
            product_cards = await page.query_selector_all(
                "div[class*='CardStyled-sc-20azeh']"
            )
        
        if not product_cards:
            # Tenta pelo container do grid MuiGrid
            product_cards = await page.query_selector_all(
                "div.MuiGrid-item div[class*='Card-sc']"
            )
        
        if not product_cards:
            # Última tentativa: cards que contêm preço e link de produto
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
    
    async def _wait_for_products_load(self, page: Page) -> None:
        """Aguarda o carregamento dos produtos na página."""
        try:
            # Aguarda o grid de produtos aparecer
            await page.wait_for_selector(
                "div.MuiGrid-container, div[class*='CardStyled'], div[class*='Card-sc']",
                timeout=15000,
            )
            # Aguarda um pouco mais para JavaScript processar
            await page.wait_for_timeout(2000)
        except Exception as e:
            self.logger.warning(f"Timeout aguardando produtos: {e}")
    
    async def _scroll_to_load_all(self, page: Page) -> None:
        """Faz scroll para carregar produtos lazy-loaded."""
        try:
            for i in range(5):  # Mais scrolls para garantir
                await page.evaluate("window.scrollBy(0, window.innerHeight)")
                await page.wait_for_timeout(800)
            # Volta ao topo
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
        """
        Extrai dados de um único card de produto.
        
        Estrutura do card (baseada no HTML real):
        <div class="Card-sc-yvvqkp-0 bUWsSi CardStyled-sc-20azeh-0 kFyEoJ">
          <a href="/produto/{id}/{slug}">
            <img class="Image-sc-20azeh-2 kenac" src="..." alt="...">
          </a>
          <div class="PriceContainer-sc-20azeh-3">
            <p class="PriceValue-sc-20azeh-4 hHjSYF">R$ 24,99</p>
          </div>
          <div class="DescriptionContainer-sc-20azeh-8">
            <a class="Link-sc-j02w35-0 bEJTOI Title-sc-20azeh-10 gdVmss">
              Arroz Agulhinha Tipo 1 CAMIL Pacote 5kg
            </a>
          </div>
        </div>
        """
        
        # === TÍTULO ===
        title = await self._extract_title(card)
        if not title:
            return None
        
        # === PREÇO ===
        price_raw = await self._extract_price(card)
        if not price_raw:
            return None
        
        # === URL DO PRODUTO ===
        product_url = await self._extract_product_url(card, page)
        
        # === IMAGEM ===
        image_url = await self._extract_image_url(card)
        
        # === DISPONIBILIDADE ===
        is_available = await self._check_availability(card)
        
        return RawProduct(
            market_id=self.market_id,
            title=title,
            price_raw=price_raw,
            unit_price_raw=None,  # Pão de Açúcar não mostra preço por unidade/kg
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
        # Tenta pelo link com classe Title
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
        
        # Fallback: alt da imagem
        try:
            img = await card.query_selector("img")
            if img:
                alt = await img.get_attribute("alt")
                if alt and alt.strip():
                    return alt.strip()
        except Exception:
            pass
        
        # Fallback: texto do link de produto
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
        """
        Extrai o preço do produto.
        Formato esperado: "R$ 24,99"
        """
        # Seletores para o preço
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
        
        # Fallback: busca qualquer elemento com R$
        try:
            all_text = await card.inner_text()
            # Regex para encontrar preço
            match = re.search(r'R\$\s*[\d.,]+', all_text)
            if match:
                return self._clean_price(match.group())
        except Exception:
            pass
        
        return None
    
    async def _extract_product_url(self, card: ElementHandle, page: Page) -> str:
        """Extrai a URL do produto."""
        try:
            # Busca link com href contendo /produto/
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
            # Busca imagem pelo seletor específico
            img = await card.query_selector("img.Image-sc-20azeh-2")
            if not img:
                img = await card.query_selector("img[class*='Image-sc']")
            if not img:
                img = await card.query_selector("img")
            
            if img:
                # Tenta src primeiro
                src = await img.get_attribute("src")
                if src and not src.startswith("data:"):
                    return src
                
                # Tenta data-src (lazy loading)
                data_src = await img.get_attribute("data-src")
                if data_src:
                    return data_src
                
                # Tenta srcset
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
            # Se tem preço, provavelmente está disponível
            price_elem = await card.query_selector("p[class*='PriceValue']")
            if price_elem:
                text = await price_elem.inner_text()
                if text and "R$" in text:
                    return True
            
            # Verifica se tem botão de adicionar
            button = await card.query_selector("button")
            if button:
                is_disabled = await button.get_attribute("disabled")
                if is_disabled is None:
                    return True
        except Exception:
            pass
        
        return True  # Assume disponível se não conseguir verificar
    
    def _clean_price(self, price_text: str) -> str:
        """Limpa e normaliza texto de preço."""
        if not price_text:
            return ""
        
        # Remove espaços extras e quebras de linha
        cleaned = " ".join(price_text.split())
        
        # Garante formato "R$ X,XX"
        match = re.search(r'R\$?\s*([\d.,]+)', cleaned)
        if match:
            value = match.group(1)
            # Normaliza para formato brasileiro
            if "." in value and "," not in value:
                # Ex: "17.35" -> "17,35"
                value = value.replace(".", ",")
            return f"R$ {value}"
        
        return cleaned
    
    async def set_location(
        self,
        page: Page,
        cep: str,
    ) -> bool:
        """
        Configura CEP no Pão de Açúcar.
        
        O site requer CEP para mostrar produtos e preços.
        Geralmente aparece um modal na primeira visita.
        """
        try:
            self.logger.debug("Tentando configurar CEP", cep=cep)
            
            # Navega para página inicial para configurar CEP
            await page.goto(
                self.config.base_url,
                wait_until="domcontentloaded",
            )
            await page.wait_for_timeout(2000)
            
            # Verifica se aparece modal de CEP
            cep_modal = await page.query_selector(
                "div[class*='modal'], div[class*='Modal'], div[role='dialog']"
            )
            
            if cep_modal:
                self.logger.debug("Modal de CEP detectado")
                
                # Busca campo de CEP no modal
                cep_input = await page.query_selector(
                    "input[placeholder*='CEP'], input[type='text'][maxlength='9'], input[name*='cep']"
                )
                
                if cep_input:
                    await cep_input.clear()
                    await cep_input.type(cep, delay=100)
                    await page.wait_for_timeout(500)
                    
                    # Busca botão de confirmar
                    confirm_btn = await page.query_selector(
                        "button:has-text('Confirmar'), button:has-text('Buscar'), button[type='submit']"
                    )
                    if confirm_btn:
                        await confirm_btn.click()
                        await page.wait_for_timeout(2000)
                        
                        self.logger.info("CEP configurado via modal", cep=cep)
                        return True
            
            # Alternativa: tenta via header/botão de localização
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
            # Tenta encontrar elemento com contagem de resultados
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
                        # Extrai números do texto
                        match = re.search(r'\d+', text.replace(".", ""))
                        if match:
                            return int(match.group())
        except Exception:
            pass
        
        return None
    
    def build_search_url(self, query: str, page_num: int = 0) -> str:
        """
        Monta a URL de busca para o Pão de Açúcar.
        
        O site aceita tanto quote_plus (+) quanto quote (%20).
        Usamos quote_plus para compatibilidade.
        """
        encoded_query = quote_plus(query)
        url = f"{self.config.base_url}/busca?terms={encoded_query}"
        if page_num > 0:
            url += f"&page={page_num}"
        return url