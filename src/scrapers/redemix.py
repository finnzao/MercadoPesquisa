"""
Scraper específico para Rede Mix - VTEX Legacy (Portal)
https://www.redemix.com.br

Este scraper usa o endpoint /buscapagina do VTEX Legacy que retorna HTML
com os produtos renderizados. Diferente do Sam's Club e GBarbosa que usam
VTEX IO com GraphQL.

Endpoint principal:
  GET https://www.redemix.com.br/buscapagina?ft={query}&PS={pageSize}&PageNumber={page}

"""

import asyncio
import html
import random
import re
from datetime import datetime
from typing import Optional
from urllib.parse import urlencode, quote_plus

from playwright.async_api import async_playwright, Page, Browser, BrowserContext, Playwright

from config.logging_config import LoggerMixin
from config.markets import MarketConfig, MarketStatus, ScrapingMethod, MarketSelectors
from src.core.models import RawProduct
from src.core.types import CollectionStatus
from src.scrapers.base import ScraperResult


# CONFIGURAÇÃO DO REDE MIX
REDEMIX_SELECTORS = MarketSelectors(
    product_container="div.product.product--shelf",
    product_title="h3.product__name a",
    product_price="span.price__best, button.buy-button[data-best-price]",
    product_price_cents="",
    product_unit_price="span.price__unit",
    product_image="div.product__media img",
    product_link="a.product__link",
    product_availability="button.buy-button",
    next_page="",
    total_results="",
    cep_input="input[placeholder*='CEP']",
    cep_submit="button:has-text('Confirmar')",
)

REDEMIX_CONFIG = MarketConfig(
    id="redemix",
    display_name="Rede Mix",
    base_url="https://www.redemix.com.br",
    search_url_template="{base_url}/{query}",
    status=MarketStatus.ACTIVE,
    method=ScrapingMethod.API,  # Usa buscapagina endpoint
    selectors=REDEMIX_SELECTORS,
    requests_per_minute=10,
    requires_cep=False,
    supports_pagination=True,
    max_pages=5,
)


class RedeMixScraper(LoggerMixin):
    """
    Scraper para Rede Mix usando VTEX Legacy (Portal).

    Diferente do VTEX IO (usado por Sam's Club e GBarbosa), o VTEX Legacy
    usa o endpoint /buscapagina que retorna HTML renderizado com os produtos.

    Fluxo:
    1. Navegar para a página de busca (estabelece cookies/sessão)
    2. Fazer requisições ao endpoint /buscapagina
    3. Fazer parse do HTML para extrair dados dos produtos

    Uso:
        scraper = RedeMixScraper()
        result = await scraper.search("arroz 5kg")
        
        for product in result.products:
            print(f"{product.title}: {product.price_raw}")
    """

    # Configurações do endpoint buscapagina
    SEARCH_ENDPOINT = "/buscapagina"
    PRODUCTS_PER_PAGE = 18  # PS padrão do Rede Mix

    def __init__(self, config: Optional[MarketConfig] = None):
        """Inicializa o scraper."""
        self.config = config or REDEMIX_CONFIG

        # Estado do Playwright
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    @property
    def market_id(self) -> str:
        """ID do mercado."""
        return self.config.id

    async def search(
        self,
        query: str,
        cep: Optional[str] = None,
        max_pages: int = 1,
    ) -> ScraperResult:
        """
        Executa busca no Rede Mix usando endpoint buscapagina.

        Args:
            query: Termo de busca (ex: "arroz 5kg")
            cep: CEP opcional para localização
            max_pages: Número máximo de páginas

        Returns:
            ScraperResult com produtos encontrados
        """
        result = ScraperResult(
            market_id=self.market_id,
            search_query=query,
            status=CollectionStatus.FAILED,
        )

        self.logger.info(
            "Iniciando busca",
            market=self.market_id,
            query=query,
            cep=cep,
        )

        try:
            # PASSO 1: Inicia browser
            await self._init_browser()
            page = await self._context.new_page()

            # PASSO 2: Navega para o site principal (estabelece contexto/cookies)
            search_url = f"{self.config.base_url}/{quote_plus(query)}"
            self.logger.debug("Navegando para URL de busca", url=search_url)

            await page.goto(
                search_url,
                wait_until="domcontentloaded",
            )
            await page.wait_for_timeout(2000)

            # Configura CEP se fornecido
            if cep:
                await self._try_set_cep(page, cep)

            # PASSO 3: Coleta produtos via buscapagina
            all_products = []

            for page_num in range(1, max_pages + 1):
                self.logger.info(
                    "Buscando página",
                    query=query,
                    page=page_num,
                )

                # Chama o endpoint buscapagina
                html_content = await self._fetch_buscapagina(page, query, page_num)

                if html_content:
                    # Faz parse do HTML
                    products = self._parse_html_response(
                        html_content, query, cep, page_num
                    )

                    if products:
                        all_products.extend(products)
                        result.pages_scraped += 1
                        self.logger.info(
                            "Página coletada",
                            page=page_num,
                            products=len(products),
                        )

                        # Se retornou menos que o esperado, é a última página
                        if len(products) < self.PRODUCTS_PER_PAGE:
                            self.logger.debug("Última página detectada")
                            break
                    else:
                        # Sem produtos nesta página
                        self.logger.debug("Nenhum produto na página", page=page_num)
                        break
                else:
                    self.logger.warning("Falha ao obter página", page=page_num)
                    break

                # Delay entre páginas
                if page_num < max_pages:
                    await asyncio.sleep(random.uniform(1, 2))

            # Se buscapagina falhou, tenta fallback HTML da página principal
            if not all_products:
                self.logger.info("Tentando fallback: extração do HTML da página")
                all_products = await self._extract_from_page_html(page, query, cep)
                if all_products:
                    result.pages_scraped = 1

            result.products = all_products
            result.status = (
                CollectionStatus.SUCCESS if all_products
                else CollectionStatus.NO_RESULTS
            )

        except Exception as e:
            result.status = CollectionStatus.FAILED
            result.error_message = str(e)
            self.logger.error("Erro na coleta", error=str(e), exc_info=True)

        finally:
            await self._close_browser()
            result.mark_finished()

        self.logger.info(
            "Busca finalizada",
            market=self.market_id,
            status=result.status.value,
            products=result.products_count,
            duration=f"{result.duration_seconds:.2f}s" if result.duration_seconds else "N/A",
        )

        return result

    async def _init_browser(self) -> None:
        """
        Inicializa browser com configurações anti-detecção.
        """
        if self._browser is not None:
            return

        self._playwright = await async_playwright().start()

        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ]
        )

        self._context = await self._browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            extra_http_headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            }
        )

        # Script anti-detecção
        await self._context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined,
            });
            
            window.chrome = { runtime: {} };
            
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
            });
        """)

    async def _close_browser(self) -> None:
        """Fecha browser e libera recursos."""
        if self._context:
            await self._context.close()
            self._context = None

        if self._browser:
            await self._browser.close()
            self._browser = None

        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    def _build_buscapagina_url(
        self,
        query: str,
        page_number: int,
    ) -> str:
        """
        Constrói a URL do endpoint buscapagina.

        Parâmetros observados no HAR:
        - ft: termo de busca (fulltext)
        - O: ordenação (OrderByTopSaleDESC, OrderByPriceDESC, etc)
        - PS: page size (produtos por página)
        - PageNumber: número da página (1-indexed)
        """
        params = {
            "ft": query,
            "O": "OrderByTopSaleDESC",
            "PS": self.PRODUCTS_PER_PAGE,
            "PageNumber": page_number,
        }

        return f"{self.config.base_url}{self.SEARCH_ENDPOINT}?{urlencode(params)}"

    async def _fetch_buscapagina(
        self,
        page: Page,
        query: str,
        page_number: int,
    ) -> Optional[str]:
        """
        Faz requisição ao endpoint buscapagina de dentro do navegador.

        Retorna o HTML da prateleira de produtos.
        """
        url = self._build_buscapagina_url(query, page_number)

        try:
            result = await page.evaluate("""
                async (url) => {
                    try {
                        const response = await fetch(url, {
                            method: "GET",
                            headers: {
                                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                            },
                            credentials: "include",
                        });
                        
                        if (!response.ok) {
                            return {
                                error: true,
                                status: response.status,
                            };
                        }
                        
                        const html = await response.text();
                        return { html: html };
                    } catch (e) {
                        return {
                            error: true,
                            message: e.message,
                        };
                    }
                }
            """, url)

            if result and result.get("error"):
                self.logger.warning(
                    "Erro na requisição buscapagina",
                    error=result.get("message"),
                    status=result.get("status"),
                )
                return None

            return result.get("html")

        except Exception as e:
            self.logger.error(
                "Exceção ao chamar buscapagina",
                error=str(e),
            )
            return None

    def _parse_html_response(
        self,
        html_content: str,
        search_query: str,
        cep: Optional[str],
        page_number: int,
    ) -> list[RawProduct]:
        """
        Faz parse do HTML retornado pelo buscapagina.

        Estrutura HTML do Rede Mix:
        - div.product.product--shelf: container do produto
        - data-product-id: ID do produto
        - h3.product__name a: nome e link
        - button.buy-button[data-best-price]: preço
        - div.product__media img: imagem
        """
        products = []

        if not html_content:
            return products

        # Extrai todos os dados usando regex
        # Produto ID
        product_ids = re.findall(
            r'data-product-id=["\'](\d+)["\']',
            html_content
        )

        # Remove duplicatas mantendo ordem
        seen_ids = set()
        unique_ids = []
        for pid in product_ids:
            if pid not in seen_ids:
                seen_ids.add(pid)
                unique_ids.append(pid)

        # Para cada ID único, extrai os dados
        for idx, product_id in enumerate(unique_ids):
            try:
                product = self._extract_product_from_html(
                    html_content,
                    product_id,
                    search_query,
                    cep,
                    position=(page_number - 1) * self.PRODUCTS_PER_PAGE + idx + 1,
                )
                if product:
                    products.append(product)
            except Exception as e:
                self.logger.debug(
                    "Erro ao extrair produto",
                    product_id=product_id,
                    error=str(e),
                )
                continue

        return products

    def _extract_product_from_html(
        self,
        html_content: str,
        product_id: str,
        search_query: str,
        cep: Optional[str],
        position: int,
    ) -> Optional[RawProduct]:
        """
        Extrai dados de um produto específico do HTML.
        """
        # Padrão para encontrar o bloco do produto
        # O HTML tem classe como: product product--shelf product-actions 5452
        product_pattern = rf'<div class="product product--shelf[^"]*\s+{product_id}">(.*?)<div class="product product--shelf'
        
        match = re.search(product_pattern, html_content, re.DOTALL)
        if not match:
            # Tenta padrão alternativo (último produto da lista)
            product_pattern = rf'<div class="product product--shelf[^"]*\s+{product_id}">(.*?)(?:</li>|$)'
            match = re.search(product_pattern, html_content, re.DOTALL)

        if not match:
            # Fallback: extrai dados diretamente usando o ID
            return self._extract_product_by_id(
                html_content, product_id, search_query, cep, position
            )

        block = match.group(1)

        # Nome do produto
        name_match = re.search(
            r'class="product__link"[^>]*title="([^"]+)"',
            block
        )
        title = name_match.group(1) if name_match else None

        if not title:
            return None

        # Decodifica entidades HTML
        title = html.unescape(title)

        # Preço
        price_match = re.search(
            r'data-best-price="([^"]+)"',
            block
        )
        price_raw = price_match.group(1) if price_match else None

        if not price_raw:
            # Tenta alternativa
            price_match = re.search(
                r'class="price__best"[^>]*>([^<]+)</span>',
                block
            )
            price_raw = price_match.group(1).strip() if price_match else None

        if not price_raw:
            return None

        # URL do produto
        url_match = re.search(
            r'href="(https://www\.redemix\.com\.br/[^"]+/p)"',
            block
        )
        product_url = url_match.group(1) if url_match else self.config.base_url

        # Imagem
        img_match = re.search(
            r'<img src="([^"]+redemix\.vteximg[^"]+)"',
            block
        )
        image_url = img_match.group(1) if img_match else None

        # Preço de lista (se houver)
        list_price_match = re.search(
            r'data-list-price="([^"]+)"',
            block
        )
        list_price_raw = list_price_match.group(1) if list_price_match else None

        return RawProduct(
            market_id=self.market_id,
            external_id=product_id,
            title=title.strip(),
            price_raw=price_raw.strip(),
            unit_price_raw=None,
            url=product_url,
            image_url=image_url,
            availability_raw="Disponível",  # Se está na lista, está disponível
            search_query=search_query,
            cep=cep,
            collected_at=datetime.now(),
            extra_data={
                "position": position,
                "source": "buscapagina",
                "list_price_raw": list_price_raw,
            },
        )

    def _extract_product_by_id(
        self,
        html_content: str,
        product_id: str,
        search_query: str,
        cep: Optional[str],
        position: int,
    ) -> Optional[RawProduct]:
        """
        Extrai dados de um produto usando buscas específicas pelo ID.
        Fallback quando o padrão de bloco não funciona.
        """
        # Nome - procura pelo link com o ID no data-product-id mais próximo
        name_pattern = rf'data-product-id="{product_id}"[^>]*>.*?title="([^"]+)"'
        name_match = re.search(name_pattern, html_content, re.DOTALL)
        
        if not name_match:
            # Tenta encontrar o nome em qualquer lugar associado ao ID
            name_pattern = rf'data-product-id="{product_id}".*?class="product__link"[^>]*title="([^"]+)"'
            name_match = re.search(name_pattern, html_content, re.DOTALL)

        title = html.unescape(name_match.group(1)) if name_match else None

        if not title:
            return None

        # Preço - procura pelo botão de compra com o ID
        price_pattern = rf'<button[^>]*class="buy-button {product_id}"[^>]*data-best-price="([^"]+)"'
        price_match = re.search(price_pattern, html_content)
        price_raw = price_match.group(1) if price_match else None

        if not price_raw:
            return None

        # URL
        url_pattern = rf'href="(https://www\.redemix\.com\.br/[^"]+/p)"[^>]*>.*?{re.escape(title[:20])}'
        url_match = re.search(url_pattern, html_content, re.DOTALL | re.IGNORECASE)
        product_url = url_match.group(1) if url_match else self.config.base_url

        # Imagem
        img_pattern = r'<img src="([^"]+redemix\.vteximg[^"]+)"'
        img_matches = re.findall(img_pattern, html_content)
        image_url = img_matches[position - 1] if position <= len(img_matches) else (img_matches[0] if img_matches else None)

        return RawProduct(
            market_id=self.market_id,
            external_id=product_id,
            title=title.strip(),
            price_raw=price_raw.strip(),
            unit_price_raw=None,
            url=product_url,
            image_url=image_url,
            availability_raw="Disponível",
            search_query=search_query,
            cep=cep,
            collected_at=datetime.now(),
            extra_data={
                "position": position,
                "source": "buscapagina_fallback",
            },
        )

    async def _extract_from_page_html(
        self,
        page: Page,
        query: str,
        cep: Optional[str],
    ) -> list[RawProduct]:
        """
        Fallback: extrai produtos diretamente do HTML da página de busca.
        Usado quando o endpoint buscapagina falha.
        """
        products = []

        try:
            # Espera os produtos carregarem
            await page.wait_for_selector(
                "div.product, div[class*='product'], li[class*='product']",
                timeout=10000,
            )

            # Obtém o HTML da página
            html_content = await page.content()

            # Usa o mesmo parser do buscapagina
            products = self._parse_html_response(html_content, query, cep, 1)

            if not products:
                # Tenta extração via seletores Playwright
                products = await self._extract_via_selectors(page, query, cep)

        except Exception as e:
            self.logger.warning(f"Falha no fallback HTML: {e}")

        return products

    async def _extract_via_selectors(
        self,
        page: Page,
        query: str,
        cep: Optional[str],
    ) -> list[RawProduct]:
        """
        Extração via seletores Playwright como último recurso.
        """
        products = []

        try:
            cards = await page.query_selector_all(
                "div.product.product--shelf, li.produto, div[class*='productCard']"
            )

            self.logger.debug(f"Encontrados {len(cards)} cards via seletores")

            for idx, card in enumerate(cards[:30]):
                try:
                    # Título
                    title_el = await card.query_selector(
                        "h3.product__name a, a.product__link, h2, h3"
                    )
                    title = await title_el.get_attribute("title") if title_el else None
                    if not title:
                        title = await title_el.inner_text() if title_el else None

                    if not title:
                        continue

                    # Preço
                    price_el = await card.query_selector(
                        "button.buy-button, span.price__best, [class*='price']"
                    )
                    price_text = None
                    if price_el:
                        price_text = await price_el.get_attribute("data-best-price")
                        if not price_text:
                            price_text = await price_el.inner_text()

                    if not price_text or "R$" not in price_text:
                        continue

                    # URL
                    link_el = await card.query_selector("a[href*='/p']")
                    href = await link_el.get_attribute("href") if link_el else None
                    product_url = href or page.url

                    # Imagem
                    img_el = await card.query_selector("img")
                    img_src = await img_el.get_attribute("src") if img_el else None

                    # ID
                    product_id = await card.query_selector("[data-product-id]")
                    ext_id = await product_id.get_attribute("data-product-id") if product_id else None

                    products.append(RawProduct(
                        market_id=self.market_id,
                        external_id=ext_id,
                        title=html.unescape(title.strip()),
                        price_raw=price_text.strip(),
                        url=product_url,
                        image_url=img_src,
                        availability_raw="Disponível",
                        search_query=query,
                        cep=cep,
                        collected_at=datetime.now(),
                        extra_data={"source": "selector_fallback", "position": idx + 1},
                    ))

                except Exception as e:
                    self.logger.debug(f"Erro ao extrair card {idx}: {e}")
                    continue

        except Exception as e:
            self.logger.warning(f"Falha na extração via seletores: {e}")

        return products

    async def _try_set_cep(self, page: Page, cep: str) -> bool:
        """
        Tenta configurar CEP no site.
        """
        try:
            cep_clean = cep.replace("-", "").replace(".", "")

            # Procura modal ou campo de CEP
            cep_input = await page.query_selector(
                "input[placeholder*='CEP'], input[name*='cep'], "
                "input[id*='cep'], input[type='text'][maxlength='9']"
            )

            if cep_input:
                await cep_input.clear()
                await cep_input.type(cep_clean, delay=100)
                await page.wait_for_timeout(500)

                # Procura botão de confirmar
                confirm_btn = await page.query_selector(
                    "button:has-text('OK'), button:has-text('Confirmar'), "
                    "button[type='submit']"
                )

                if confirm_btn:
                    await confirm_btn.click()
                    await page.wait_for_timeout(2000)
                    self.logger.info("CEP configurado", cep=cep)
                    return True

            self.logger.debug("Campo de CEP não encontrado")
            return False

        except Exception as e:
            self.logger.debug(f"Erro ao configurar CEP: {e}")
            return False

    # Métodos de compatibilidade com interface BaseScraper

    async def set_location(self, page: Page, cep: str) -> bool:
        """Compatibilidade com interface BaseScraper."""
        return await self._try_set_cep(page, cep)

    async def extract_products(
        self,
        page: Page,
        search_query: str,
        cep: Optional[str] = None,
    ) -> list[RawProduct]:
        """Compatibilidade com interface BaseScraper."""
        html_content = await self._fetch_buscapagina(page, search_query, 1)
        if html_content:
            return self._parse_html_response(html_content, search_query, cep, 1)
        return await self._extract_from_page_html(page, search_query, cep)


# FUNÇÕES DE CONVENIÊNCIA

async def search_redemix(
    query: str,
    cep: Optional[str] = None,
    max_pages: int = 1,
) -> ScraperResult:
    """
    Função de conveniência para busca rápida no Rede Mix.

    Args:
        query: Termo de busca
        cep: CEP para região (opcional)
        max_pages: Máximo de páginas

    Returns:
        ScraperResult

    Exemplo:
        result = await search_redemix("arroz 5kg")
        for product in result.products:
            print(f"{product.title}: {product.price_raw}")
    """
    scraper = RedeMixScraper()
    return await scraper.search(query, cep=cep, max_pages=max_pages)


# TESTE LOCAL
if __name__ == "__main__":
    async def test():
        print("=" * 80)
        print("TESTE DO SCRAPER REDE MIX (VTEX Legacy - buscapagina)")
        print("=" * 80)

        scraper = RedeMixScraper()

        # Teste 1: Busca simples
        print("\n[TESTE 1] Busca: 'arroz 5kg'")
        result = await scraper.search("arroz 5kg", max_pages=1)

        print(f"Status: {result.status.value}")
        print(f"Produtos: {result.products_count}")
        print(f"Duração: {result.duration_seconds:.2f}s" if result.duration_seconds else "N/A")

        if result.products:
            print("\nPrimeiros 5 produtos:")
            for p in result.products[:5]:
                print(f"  - {p.title}")
                print(f"    Preço: {p.price_raw}")
                print(f"    ID: {p.external_id}")
                print(f"    URL: {p.url[:60]}...")
                print()

        # Teste 2: Outra busca
        print("\n[TESTE 2] Busca: 'leite'")
        result2 = await scraper.search("leite", max_pages=1)

        print(f"Status: {result2.status.value}")
        print(f"Produtos: {result2.products_count}")

        if result2.products:
            print(f"Primeiro produto: {result2.products[0].title}")

    asyncio.run(test())