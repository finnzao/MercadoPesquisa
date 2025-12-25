"""
Scraper específico para Atacadão - VERSÃO CORRIGIDA.
https://www.atacadao.com.br

Baseado na análise real do HTML em 25/12/2024.

Estrutura identificada:
- Produtos estão em <ul class="grid grid-cols-2..."> > <li> > <article>
- Cada article tem data-testid="store-product-card-content"
- Preços: atacado (A partir de X unid.) e unitário (ou R$ X / cada)
- Imagem em div[data-product-card-image]
- Link com data-testid="product-link"
"""

import re
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

from playwright.async_api import Page, ElementHandle

from config.markets import ATACADAO_CONFIG, MarketConfig
from src.core.models import RawProduct
from src.scrapers.base import BaseScraper


class AtacadaoScraper(BaseScraper):
    """
    Scraper para Atacadão.
    Site de atacado com preços diferenciados para grandes quantidades.
    
    Particularidades:
    - Preço de atacado (a partir de X unidades)
    - Preço unitário (ou R$ X / cada)
    - Badge de desconto (%)
    - Requer CEP para algumas regiões
    """
    
    def __init__(self, config: Optional[MarketConfig] = None):
        """Inicializa o scraper."""
        super().__init__(config or ATACADAO_CONFIG)
    
    async def extract_products(
        self,
        page: Page,
        search_query: str,
        cep: Optional[str] = None,
    ) -> list[RawProduct]:
        """
        Extrai produtos da página de resultados do Atacadão.
        
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
        # Estrutura: ul.grid > li > article
        product_cards = await page.query_selector_all(
            "ul.grid li article.relative"
        )
        
        # Fallback: tenta seletores alternativos se não encontrar
        if not product_cards:
            self.logger.debug("Tentando seletores alternativos...")
            product_cards = await page.query_selector_all(
                "article:has(section[data-testid='store-product-card-content'])"
            )
        
        if not product_cards:
            product_cards = await page.query_selector_all(
                "li:has(a[data-testid='product-link'])"
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
                "ul.grid, [data-fs-product-listing-results]",
                timeout=15000,
            )
            # Aguarda um pouco mais para JavaScript processar
            await page.wait_for_timeout(2000)
        except Exception as e:
            self.logger.warning(f"Timeout aguardando produtos: {e}")
    
    async def _scroll_to_load_all(self, page: Page) -> None:
        """Faz scroll para carregar produtos lazy-loaded."""
        try:
            for i in range(3):
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
        <article class="relative flex flex-col h-full...">
          <div data-product-card-image>
            <img src="..." alt="">
          </div>
          <section data-testid="store-product-card-content">
            <h3 title="Nome do Produto">
              <a href="/produto/p" data-testid="product-link">Nome</a>
            </h3>
            <div>
              <div>A partir de 6 unid.</div>
              <div>
                <p class="text-lg...font-bold">R$ 17,35</p>
                <div data-test="discount-badge">-3%</div>
              </div>
              <div>
                <p>ou</p>
                <p class="text-sm...font-bold">R$ 17,85</p>
                <p>/ cada</p>
              </div>
            </div>
          </section>
          <button data-testid="buy-button">Adicionar</button>
        </article>
        """
        
        # === TÍTULO ===
        title = await self._extract_title(card)
        if not title:
            return None
        
        # === PREÇO ATACADO (principal) ===
        price_raw = await self._extract_main_price(card)
        if not price_raw:
            return None
        
        # === QUANTIDADE MÍNIMA PARA ATACADO ===
        bulk_quantity = await self._extract_bulk_quantity(card)
        
        # === PREÇO UNITÁRIO ===
        unit_price_raw = await self._extract_unit_price(card)
        
        # === DESCONTO ===
        discount = await self._extract_discount(card)
        
        # === URL DO PRODUTO ===
        product_url = await self._extract_product_url(card, page)
        
        # === IMAGEM ===
        image_url = await self._extract_image_url(card)
        
        # === DISPONIBILIDADE ===
        is_available = await self._check_availability(card)
        
        # Monta informação adicional
        extra_info = []
        if bulk_quantity:
            extra_info.append(bulk_quantity)
        if discount:
            extra_info.append(f"Desconto: {discount}")
        
        return RawProduct(
            market_id=self.market_id,
            title=title,
            price_raw=price_raw,
            unit_price_raw=unit_price_raw,
            url=product_url,
            image_url=image_url,
            availability_raw="Disponível" if is_available else "Indisponível",
            search_query=search_query,
            cep=cep,
            collected_at=datetime.now(),
            extra_data={
                "bulk_quantity": bulk_quantity,
                "discount": discount,
                "position": index,
            } if bulk_quantity or discount else None,
        )
    
    async def _extract_title(self, card: ElementHandle) -> Optional[str]:
        """Extrai o título do produto."""
        # Tenta h3 com atributo title
        title_elem = await card.query_selector("h3[title]")
        if title_elem:
            title = await title_elem.get_attribute("title")
            if title:
                return title.strip()
        
        # Fallback: texto do h3
        h3 = await card.query_selector("h3")
        if h3:
            text = await h3.inner_text()
            if text:
                return text.strip()
        
        # Fallback: link do produto
        link = await card.query_selector("a[data-testid='product-link']")
        if link:
            text = await link.inner_text()
            if text:
                return text.strip()
        
        return None
    
    async def _extract_main_price(self, card: ElementHandle) -> Optional[str]:
        """
        Extrai o preço principal (atacado).
        Formato esperado: "R$ 17,35"
        """
        # Seletor principal: p com classes específicas dentro do section
        selectors = [
            "section p.text-lg.font-bold",
            "section p.xl\\:text-xl.font-bold",
            "p.text-lg.text-neutral-500.font-bold",
            "p[class*='text-lg'][class*='font-bold']",
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
    
    async def _extract_unit_price(self, card: ElementHandle) -> Optional[str]:
        """
        Extrai o preço unitário.
        Formato: "ou R$ 17,85 / cada"
        """
        try:
            # Busca div que contém "ou" e "/ cada"
            content = await card.inner_text()
            
            # Regex para "ou R$ X,XX / cada"
            match = re.search(r'ou\s*R\$\s*([\d.,]+)\s*/\s*cada', content, re.IGNORECASE)
            if match:
                return f"R$ {match.group(1)}"
            
            # Alternativa: busca elemento específico
            elem = await card.query_selector("div.flex.items-center.gap-1 p.text-sm.font-bold")
            if elem:
                text = await elem.inner_text()
                if text and "R$" in text:
                    return self._clean_price(text)
        except Exception:
            pass
        
        return None
    
    async def _extract_bulk_quantity(self, card: ElementHandle) -> Optional[str]:
        """
        Extrai a quantidade mínima para preço de atacado.
        Exemplo: "A partir de 6 unid."
        """
        try:
            content = await card.inner_text()
            match = re.search(r'A partir de\s*(\d+)\s*unid\.?', content, re.IGNORECASE)
            if match:
                return f"A partir de {match.group(1)} unid."
        except Exception:
            pass
        
        return None
    
    async def _extract_discount(self, card: ElementHandle) -> Optional[str]:
        """
        Extrai o percentual de desconto.
        Exemplo: "-3%"
        """
        try:
            # Busca badge de desconto
            badge = await card.query_selector("div[data-test='discount-badge']")
            if badge:
                text = await badge.inner_text()
                if text and "%" in text:
                    return text.strip()
            
            # Alternativa: busca por padrão no texto
            content = await card.inner_text()
            match = re.search(r'-\d+%', content)
            if match:
                return match.group()
        except Exception:
            pass
        
        return None
    
    async def _extract_product_url(self, card: ElementHandle, page: Page) -> str:
        """Extrai a URL do produto."""
        try:
            link = await card.query_selector("a[data-testid='product-link']")
            if link:
                href = await link.get_attribute("href")
                if href:
                    return urljoin(self.config.base_url, href)
            
            # Fallback: qualquer link que contém /p
            link = await card.query_selector("a[href*='/p']")
            if link:
                href = await link.get_attribute("href")
                if href and "/p" in href:
                    return urljoin(self.config.base_url, href)
        except Exception:
            pass
        
        return page.url
    
    async def _extract_image_url(self, card: ElementHandle) -> Optional[str]:
        """Extrai a URL da imagem do produto."""
        try:
            # Busca imagem dentro do container de imagem
            img = await card.query_selector("div[data-product-card-image] img")
            if img:
                src = await img.get_attribute("src")
                if src:
                    return src
            
            # Fallback: qualquer imagem no card
            img = await card.query_selector("img")
            if img:
                # Tenta srcset primeiro (maior qualidade)
                srcset = await img.get_attribute("srcset")
                if srcset:
                    # Pega a maior resolução do srcset
                    urls = re.findall(r'(https?://[^\s]+)', srcset)
                    if urls:
                        return urls[-1]  # Última geralmente é a maior
                
                src = await img.get_attribute("src")
                if src:
                    return src
        except Exception:
            pass
        
        return None
    
    async def _check_availability(self, card: ElementHandle) -> bool:
        """Verifica se o produto está disponível."""
        try:
            button = await card.query_selector("button[data-testid='buy-button']")
            if button:
                is_disabled = await button.get_attribute("disabled")
                return is_disabled is None
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
            if "." in value and "," in value:
                # Ex: "1.234,56" -> mantém
                pass
            elif "." in value and "," not in value:
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
        Configura CEP no Atacadão.
        
        O site mostra um tooltip pedindo CEP que pode ser fechado,
        ou usa a localização atual se já configurada.
        """
        try:
            self.logger.debug("Tentando configurar CEP", cep=cep)
            
            # Navega para página inicial para configurar CEP
            await page.goto(
                self.config.base_url,
                wait_until="domcontentloaded",
            )
            await page.wait_for_timeout(2000)
            
            # Verifica se já tem CEP configurado
            current_cep = await page.query_selector(
                "button[data-testid='userZipCode'] span"
            )
            if current_cep:
                current_text = await current_cep.inner_text()
                if cep.replace("-", "") in current_text.replace("-", ""):
                    self.logger.info("CEP já configurado", cep=cep)
                    return True
            
            # Tenta clicar no botão de CEP para abrir modal
            cep_button = await page.query_selector(
                "button[data-testid='userZipCode'], button:has-text('Informar Localização')"
            )
            
            if cep_button:
                await cep_button.click()
                await page.wait_for_timeout(1000)
                
                # Busca campo de CEP no modal
                cep_input = await page.query_selector(
                    "input[placeholder*='CEP'], input[type='text']"
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
                        
                        self.logger.info("CEP configurado", cep=cep)
                        return True
            
            # Se não conseguiu pelo modal, tenta fechar tooltip e continuar
            close_btn = await page.query_selector(
                "button:has-text('Informar Localização')"
            )
            if close_btn:
                # Clica fora para fechar
                await page.click("body", position={"x": 10, "y": 10})
                await page.wait_for_timeout(500)
            
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
            elem = await page.query_selector(
                "h2[data-testid='total-product-count'] span.font-bold"
            )
            if elem:
                text = await elem.inner_text()
                if text:
                    return int(re.sub(r'\D', '', text))
        except Exception:
            pass
        
        return None