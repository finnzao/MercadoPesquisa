"""
Scraper específico para Hiperideal - API VTEX IO GraphQL
https://www.hiperideal.com.br

Este scraper usa a API GraphQL do Hiperideal (plataforma VTEX IO).
Usa o mesmo padrão do Sam's Club, GBarbosa e Mercantil Atacado:
- Persisted queries com variáveis codificadas em Base64
- Mesmo SHA256 hash da query productSearchV3

Endpoint principal:
  GET https://www.hiperideal.com.br/_v/segment/graphql/v1?operationName=productSearchV3&...

Diferenças específicas do Hiperideal:
- hideUnavailableItems: false (mostra produtos indisponíveis)
- Paginação com 20 produtos por página (to: 19)
"""

import asyncio
import base64
import json
import random
import re
from datetime import datetime
from typing import Optional
from urllib.parse import urlencode, quote

from playwright.async_api import async_playwright, Page, Browser, BrowserContext, Playwright

from config.logging_config import LoggerMixin
from config.markets import MarketConfig, MarketStatus, ScrapingMethod, MarketSelectors
from src.core.models import RawProduct
from src.core.types import CollectionStatus
from src.scrapers.base import ScraperResult


# CONFIGURAÇÃO DO HIPERIDEAL
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
    cep_input="input[placeholder*='CEP']",
    cep_submit="button:has-text('Confirmar')",
)

HIPERIDEAL_CONFIG = MarketConfig(
    id="hiperideal",
    display_name="Hiperideal",
    base_url="https://www.hiperideal.com.br",
    search_url_template="{base_url}/{query}?_q={query}&map=ft",
    status=MarketStatus.ACTIVE,
    method=ScrapingMethod.API,
    selectors=HIPERIDEAL_SELECTORS,
    requests_per_minute=10,
    requires_cep=False,
    supports_pagination=True,
    max_pages=5,
)


class HiperidealScraper(LoggerMixin):
    """
    Scraper para Hiperideal usando API GraphQL VTEX IO.

    Usa o mesmo padrão do Sam's Club, GBarbosa e Mercantil:
    - Endpoint: /_v/segment/graphql/v1
    - Operation: productSearchV3
    - Persisted queries com variáveis em Base64

    Diferenças do Hiperideal:
    - hideUnavailableItems: false
    - 20 produtos por página

    Uso:
        scraper = HiperidealScraper()
        result = await scraper.search("arroz")
        
        for product in result.products:
            print(f"{product.title}: {product.price_raw}")
    """

    # Configurações da API (mesmo hash dos outros VTEX IO)
    GRAPHQL_ENDPOINT = "/_v/segment/graphql/v1"
    OPERATION_NAME = "productSearchV3"
    SHA256_HASH = "31d3fa494df1fc41efef6d16dd96a96e6911b8aed7a037868699a1f3f4d365de"
    SENDER = "vtex.store-resources@0.x"
    PROVIDER = "vtex.search-graphql@0.x"

    PRODUCTS_PER_PAGE = 20  # Hiperideal usa 20 por página

    def __init__(self, config: Optional[MarketConfig] = None):
        """Inicializa o scraper."""
        self.config = config or HIPERIDEAL_CONFIG

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
        Executa busca no Hiperideal usando a API GraphQL.

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
            await self._init_browser()
            page = await self._context.new_page()

            # Navega para a URL de busca (estabelece contexto)
            search_url = self._build_search_page_url(query)
            self.logger.debug("Navegando para URL de busca", url=search_url)

            await page.goto(
                search_url,
                wait_until="domcontentloaded",
            )
            await page.wait_for_timeout(3000)

            if cep:
                await self._try_set_cep(page, cep)

            # Coleta produtos via API GraphQL
            all_products = []
            total_available = None

            for page_num in range(1, max_pages + 1):
                from_idx = (page_num - 1) * self.PRODUCTS_PER_PAGE
                to_idx = from_idx + self.PRODUCTS_PER_PAGE - 1

                self.logger.info(
                    "Buscando via GraphQL",
                    query=query,
                    page=page_num,
                    from_idx=from_idx,
                    to_idx=to_idx,
                )

                api_data = await self._fetch_graphql(page, query, from_idx, to_idx)

                if api_data and not api_data.get("error"):
                    products = self._parse_graphql_response(api_data, query, cep)

                    if products:
                        all_products.extend(products)
                        result.pages_scraped += 1
                        self.logger.info(
                            "Página coletada via GraphQL",
                            page=page_num,
                            products=len(products),
                        )
                    else:
                        break

                    if total_available is None:
                        total_available = api_data.get("data", {}).get(
                            "productSearch", {}
                        ).get("recordsFiltered", 0)

                    if to_idx + 1 >= total_available:
                        self.logger.debug(
                            "Última página alcançada",
                            total_available=total_available,
                        )
                        break

                    if page_num < max_pages:
                        await asyncio.sleep(random.uniform(1, 2))
                else:
                    error_msg = str(api_data) if api_data else "No response"
                    self.logger.warning(
                        "GraphQL falhou, tentando fallback HTML",
                        error=error_msg[:200],
                    )

                    html_products = await self._extract_from_html(page, query, cep)
                    if html_products:
                        all_products.extend(html_products)
                        result.pages_scraped = 1
                    break

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

    def _build_search_page_url(self, query: str) -> str:
        """Constrói a URL da página de busca."""
        query_clean = re.sub(r'[^\w\s]', '', query).strip()
        query_slug = query_clean.lower().replace(' ', '%20')
        query_param = quote(query_clean)

        return f"{self.config.base_url}/{query_slug}?_q={query_param}&map=ft"

    async def _init_browser(self) -> None:
        """Inicializa browser com configurações anti-detecção."""
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

    def _build_graphql_variables(
        self,
        query: str,
        from_idx: int,
        to_idx: int,
    ) -> dict:
        """
        Constrói as variáveis para a query GraphQL.

        Nota: Hiperideal usa hideUnavailableItems: false
        """
        query_clean = query.strip()

        return {
            "hideUnavailableItems": False,  # Diferente: mostra indisponíveis
            "skusFilter": "ALL",
            "simulationBehavior": "default",
            "installmentCriteria": "MAX_WITHOUT_INTEREST",
            "productOriginVtex": False,
            "map": "ft",
            "query": query_clean,
            "orderBy": "OrderByScoreDESC",
            "from": from_idx,
            "to": to_idx,
            "selectedFacets": [
                {"key": "ft", "value": query_clean}
            ],
            "fullText": query_clean,
            "facetsBehavior": "Static",
            "categoryTreeBehavior": "default",
            "withFacets": False,
        }

    def _build_graphql_url(
        self,
        query: str,
        from_idx: int,
        to_idx: int,
    ) -> str:
        """Constrói a URL completa para a requisição GraphQL."""
        variables = self._build_graphql_variables(query, from_idx, to_idx)
        variables_json = json.dumps(variables, separators=(",", ":"))
        variables_b64 = base64.b64encode(variables_json.encode()).decode()

        extensions = {
            "persistedQuery": {
                "version": 1,
                "sha256Hash": self.SHA256_HASH,
                "sender": self.SENDER,
                "provider": self.PROVIDER,
            },
            "variables": variables_b64,
        }

        params = {
            "workspace": "master",
            "maxAge": "short",
            "appsEtag": "remove",
            "domain": "store",
            "locale": "pt-BR",
            "operationName": self.OPERATION_NAME,
            "variables": "{}",
            "extensions": json.dumps(extensions, separators=(",", ":")),
        }

        url = f"{self.config.base_url}{self.GRAPHQL_ENDPOINT}?{urlencode(params)}"
        return url

    async def _fetch_graphql(
        self,
        page: Page,
        query: str,
        from_idx: int,
        to_idx: int,
    ) -> Optional[dict]:
        """Faz requisição GET ao endpoint GraphQL de dentro do navegador."""
        url = self._build_graphql_url(query, from_idx, to_idx)

        try:
            result = await page.evaluate("""
                async (url) => {
                    try {
                        const response = await fetch(url, {
                            method: "GET",
                            headers: {
                                "Accept": "application/json",
                                "Content-Type": "application/json",
                            },
                            credentials: "include",
                        });
                        
                        if (!response.ok) {
                            return {
                                error: true,
                                status: response.status,
                                statusText: response.statusText || "",
                            };
                        }
                        
                        const data = await response.json();
                        return data;
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
                    "Erro na requisição GraphQL",
                    error=result.get("message") or result.get("statusText"),
                    status=result.get("status"),
                )

            return result

        except Exception as e:
            self.logger.error("Exceção ao chamar GraphQL", error=str(e))
            return {"error": True, "message": str(e)}

    async def _extract_from_html(
        self,
        page: Page,
        query: str,
        cep: Optional[str],
    ) -> list[RawProduct]:
        """Fallback: extrai produtos diretamente do HTML da página."""
        products = []

        try:
            await page.wait_for_selector(
                "[class*='product'], [class*='shelf'], [data-testid*='product']",
                timeout=10000,
            )

            selectors = [
                "article[class*='product']",
                "div[class*='productCard']",
                "div[class*='vtex-product-summary']",
                "section[class*='product']",
                "a[href*='/p']",
            ]

            cards = []
            for selector in selectors:
                cards = await page.query_selector_all(selector)
                if len(cards) > 3:
                    break

            self.logger.debug(f"Encontrados {len(cards)} cards no HTML")

            for idx, card in enumerate(cards[:20]):
                try:
                    title_el = await card.query_selector(
                        "h1, h2, h3, [class*='productName'], [class*='name']"
                    )
                    title = await title_el.inner_text() if title_el else None

                    if not title:
                        continue

                    price_el = await card.query_selector(
                        "[class*='price'], [class*='Price'], span[class*='selling']"
                    )
                    price_text = await price_el.inner_text() if price_el else None

                    if not price_text or "R$" not in price_text:
                        continue

                    link_el = await card.query_selector("a[href*='/p']")
                    href = await link_el.get_attribute("href") if link_el else None
                    product_url = f"{self.config.base_url}{href}" if href and href.startswith(
                        "/") else (href or page.url)

                    img_el = await card.query_selector("img")
                    img_src = await img_el.get_attribute("src") if img_el else None

                    products.append(RawProduct(
                        market_id=self.market_id,
                        title=title.strip(),
                        price_raw=price_text.strip(),
                        url=product_url,
                        image_url=img_src,
                        availability_raw="Disponível",
                        search_query=query,
                        cep=cep,
                        collected_at=datetime.now(),
                        extra_data={"source": "html_fallback", "position": idx + 1},
                    ))

                except Exception as e:
                    self.logger.debug(f"Erro ao extrair card {idx}: {e}")
                    continue

        except Exception as e:
            self.logger.warning(f"Falha no fallback HTML: {e}")

        return products

    def _parse_graphql_response(
        self,
        api_data: dict,
        search_query: str,
        cep: Optional[str],
    ) -> list[RawProduct]:
        """Processa a resposta da API GraphQL."""
        products = []

        try:
            product_search = api_data.get("data", {}).get("productSearch", {})
            items = product_search.get("products", [])
        except (TypeError, AttributeError):
            self.logger.debug("Estrutura de resposta inválida")
            return products

        if not items:
            self.logger.debug("Nenhum produto encontrado na resposta")
            return products

        for idx, item in enumerate(items):
            try:
                product = self._parse_product(item, search_query, cep, idx + 1)
                if product:
                    products.append(product)
            except Exception as e:
                self.logger.debug(
                    "Erro ao processar produto",
                    index=idx,
                    error=str(e),
                )
                continue

        return products

    def _parse_product(
        self,
        item: dict,
        search_query: str,
        cep: Optional[str],
        position: int,
    ) -> Optional[RawProduct]:
        """Converte um item da API GraphQL para RawProduct."""
        title = item.get("productName") or ""
        if not title:
            return None

        # Extrai preço
        price = None
        availability = "Indisponível"

        skus = item.get("items", [])
        for sku in skus:
            sellers = sku.get("sellers", [])
            for seller in sellers:
                offer = seller.get("commertialOffer", {})
                qty = offer.get("AvailableQuantity", 0)

                if qty > 0:
                    price = offer.get("Price")
                    availability = "Disponível"
                    break

            if price is not None:
                break

        # Fallback: priceRange
        if price is None:
            price_range = item.get("priceRange", {})
            selling_price = price_range.get("sellingPrice", {})
            price = selling_price.get("lowPrice")

        if price is None:
            return None

        # Formata preço
        try:
            price_float = float(price)
        except (ValueError, TypeError):
            return None

        price_raw = f"R$ {price_float:.2f}".replace(".", ",")

        # URL
        link = item.get("link", "")
        if link:
            if not link.startswith("http"):
                product_url = f"{self.config.base_url}{link}"
            else:
                product_url = link
        else:
            product_url = self.config.base_url

        # Imagem
        image_url = None
        if skus:
            images = skus[0].get("images", [])
            if images:
                image_url = images[0].get("imageUrl")

        # ID externo
        external_id = item.get("productId")

        # Marca
        brand = item.get("brand")

        # Preço de lista
        list_price = None
        price_range = item.get("priceRange", {})
        list_price_range = price_range.get("listPrice", {})
        list_price = list_price_range.get("lowPrice")

        # Desconto
        discount = None
        if list_price and price and list_price > price:
            discount = round(list_price - price, 2)

        return RawProduct(
            market_id=self.market_id,
            external_id=str(external_id) if external_id else None,
            title=title.strip(),
            price_raw=price_raw,
            unit_price_raw=None,
            url=product_url,
            image_url=image_url,
            availability_raw=availability,
            search_query=search_query,
            cep=cep,
            collected_at=datetime.now(),
            extra_data={
                "position": position,
                "source": "graphql",
                "brand": brand,
                "product_reference": item.get("productReference"),
                "category_id": item.get("categoryId"),
                "list_price": list_price,
                "discount": discount,
            },
        )

    async def _try_set_cep(self, page: Page, cep: str) -> bool:
        """Tenta configurar CEP no site."""
        try:
            cep_clean = cep.replace("-", "").replace(".", "")

            location_btn = await page.query_selector(
                "button[class*='location'], button[class*='cep'], "
                "[data-testid*='location'], [data-testid*='cep']"
            )

            if location_btn:
                await location_btn.click()
                await page.wait_for_timeout(1000)

            cep_input = await page.query_selector(
                "input[placeholder*='CEP'], input[name*='cep'], "
                "input[id*='cep'], input[type='text'][maxlength='9']"
            )

            if cep_input:
                await cep_input.clear()
                await cep_input.type(cep_clean, delay=100)
                await page.wait_for_timeout(500)

                confirm_btn = await page.query_selector(
                    "button:has-text('Confirmar'), button:has-text('OK'), "
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

    # Métodos de compatibilidade

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
        api_data = await self._fetch_graphql(page, search_query, 0, 19)
        if api_data and not api_data.get("error"):
            return self._parse_graphql_response(api_data, search_query, cep)
        return await self._extract_from_html(page, search_query, cep)


# FUNÇÕES DE CONVENIÊNCIA

async def search_hiperideal(
    query: str,
    cep: Optional[str] = None,
    max_pages: int = 1,
) -> ScraperResult:
    """
    Função de conveniência para busca rápida no Hiperideal.

    Args:
        query: Termo de busca
        cep: CEP para região (opcional)
        max_pages: Máximo de páginas

    Returns:
        ScraperResult

    Exemplo:
        result = await search_hiperideal("arroz 5kg")
        for product in result.products:
            print(f"{product.title}: {product.price_raw}")
    """
    scraper = HiperidealScraper()
    return await scraper.search(query, cep=cep, max_pages=max_pages)

