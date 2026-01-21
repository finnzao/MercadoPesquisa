"""
Scraper específico para Pão de Açúcar - VERSÃO API INDEPENDENTE.
https://www.paodeacucar.com

API utilizada:
- POST https://api.vendas.gpa.digital/pa/search/search
"""

import asyncio
import random
import re
from datetime import datetime
from typing import Optional
from urllib.parse import quote_plus

from playwright.async_api import async_playwright, Page, Browser, BrowserContext, Playwright

from config.logging_config import LoggerMixin
from config.markets import PAO_ACUCAR_CONFIG, MarketConfig
from src.core.models import RawProduct
from src.core.types import CollectionStatus
from src.scrapers.base import ScraperResult


class PaoDeAcucarScraper(LoggerMixin):
    """
    Scraper para Pão de Açúcar usando API interna.

    Esta versão é INDEPENDENTE do BaseScraper e gerencia seu próprio
    browser com as configurações exatas do script de teste que funciona.

    A requisição à API é feita de DENTRO do contexto do navegador
    (page.evaluate) para evitar CORS.
    """

    # Configurações da API
    API_URL = "https://api.vendas.gpa.digital/pa/search/search"
    DEFAULT_STORE_ID = 461  # Store ID padrão (São Paulo)
    PRODUCTS_PER_PAGE = 16

    def __init__(self, config: Optional[MarketConfig] = None):
        """
        Inicializa o scraper.
        
        Args:
            config: Configuração do mercado (opcional, usa padrão se não fornecido)
        """
        self.config = config or PAO_ACUCAR_CONFIG
        self._store_id = self.DEFAULT_STORE_ID

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
        Executa busca no Pão de Açúcar usando a API.

        Fluxo (exatamente igual ao script de teste):
        1. Inicia browser com configurações anti-detecção
        2. Navega para a HOME do site (estabelece contexto)
        3. Faz requisição POST à API de dentro do navegador
        4. Processa resposta JSON

        Args:
            query: Termo de busca
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
            # PASSO 1: Inicia browser (configurações do script de teste)
            await self._init_browser()
            page = await self._context.new_page()

            # PASSO 2: Navega para a HOME do site primeiro
            # Isso é ESSENCIAL para que as requisições à API funcionem sem CORS
            self.logger.debug(
                "Navegando para o site (estabelecendo contexto)...")
            await page.goto(
                "https://www.paodeacucar.com/",
                wait_until="domcontentloaded",
            )
            await page.wait_for_timeout(2000)

            # Configura CEP se fornecido
            if cep:
                await self._try_set_cep(page, cep)

            # PASSO 3: Coleta produtos via API
            all_products = []

            for page_num in range(1, max_pages + 1):
                self.logger.info(
                    "Buscando via API",
                    query=query,
                    store_id=self._store_id,
                    page=page_num,
                )

                # Chama a API de DENTRO do navegador
                api_data = await self._fetch_api(page, query, page_num)

                if api_data and not api_data.get("error"):
                    # Processa produtos da API
                    products = self._parse_api_response(api_data, query, cep)

                    if products:
                        all_products.extend(products)
                        result.pages_scraped += 1
                        self.logger.info(
                            "Página coletada via API",
                            page=page_num,
                            products=len(products),
                        )
                    else:
                        break

                    # Verifica se há mais páginas
                    total_products = api_data.get("totalProducts", 0)
                    if page_num * self.PRODUCTS_PER_PAGE >= total_products:
                        break

                    # Delay entre páginas
                    if page_num < max_pages:
                        await asyncio.sleep(random.uniform(1, 2))
                else:
                    # API falhou
                    error_msg = api_data.get(
                        "message") if api_data else "No response"
                    self.logger.warning(
                        "API falhou",
                        error=error_msg,
                    )
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

    async def _init_browser(self) -> None:
        """
        Inicializa browser com configurações EXATAS do script de teste.
        """
        if self._browser is not None:
            return

        self._playwright = await async_playwright().start()

        # Configurações EXATAS do script de teste
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ]
        )

        # Contexto com configurações EXATAS do script de teste
        self._context = await self._browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="pt-BR",
        )

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

    async def _fetch_api(
        self,
        page: Page,
        query: str,
        page_num: int = 1,
    ) -> Optional[dict]:
        """
        Faz requisição POST à API de DENTRO do contexto do navegador.

        IMPORTANTE: Usar page.evaluate() é a SOLUÇÃO para o problema de CORS!
        A requisição parte do contexto do site, então o servidor aceita.

        Código JavaScript EXATO do script de teste.
        """
        # Payload EXATO do script de teste
        api_payload = {
            "terms": query,
            "page": page_num,
            "sortBy": "relevance",
            "resultsPerPage": self.PRODUCTS_PER_PAGE,
            "allowRedirect": True,
            "storeId": self._store_id,
            "department": "ecom",
            "customerPlus": True,
            "partner": "linx",
        }

        try:
            # JavaScript EXATO do script de teste
            result = await page.evaluate("""
                async (payload) => {
                    try {
                        const response = await fetch("https://api.vendas.gpa.digital/pa/search/search", {
                            method: "POST",
                            headers: {
                                "Accept": "application/json, text/plain, */*",
                                "Content-Type": "application/json",
                            },
                            body: JSON.stringify(payload),
                        });
                        
                        if (!response.ok) {
                            return {
                                error: true,
                                status: response.status,
                                statusText: response.statusText,
                            };
                        }
                        
                        const data = await response.json();
                        return {
                            error: false,
                            data: data,
                        };
                    } catch (e) {
                        return {
                            error: true,
                            message: e.message,
                        };
                    }
                }
            """, api_payload)

            if result.get("error"):
                self.logger.warning(
                    "Erro na requisição API",
                    error=result.get("message") or result.get(
                        "statusText") or str(result),
                )
                return result

            return result.get("data")

        except Exception as e:
            self.logger.error(
                "Exceção ao chamar API",
                error=str(e),
            )
            return {"error": True, "message": str(e)}

    def _parse_api_response(
        self,
        api_data: dict,
        search_query: str,
        cep: Optional[str],
    ) -> list[RawProduct]:
        """
        Processa a resposta da API e converte para RawProduct.

        Estrutura da resposta (do script de teste):
        {
            "products": [...],
            "totalProducts": 75,
            ...
        }
        """
        products = []

        items = api_data.get("products", [])

        if not items:
            self.logger.debug("Nenhum produto encontrado na resposta da API")
            return products

        for idx, item in enumerate(items):
            try:
                product = self._parse_api_product(
                    item, search_query, cep, idx + 1)
                if product:
                    products.append(product)
            except Exception as e:
                self.logger.debug(
                    "Erro ao processar produto da API",
                    index=idx,
                    error=str(e),
                )
                continue

        return products

    def _parse_api_product(
        self,
        item: dict,
        search_query: str,
        cep: Optional[str],
        position: int,
    ) -> Optional[RawProduct]:
        """
        Converte um item da API para RawProduct.

        Campos da API (do script de teste):
        - name / title: nome do produto
        - price: preço
        - originalPrice: preço original (sem desconto)
        - unitPrice: preço por unidade
        - unit: unidade (kg, L, etc)
        - image / imageUrl: URL da imagem
        - url: URL do produto
        - available: disponibilidade
        - id: ID do produto
        - brand: marca
        """
        # Extrai título
        title = item.get("name") or item.get("title") or ""
        if not title:
            return None

        # Extrai preço
        price = item.get("price")
        if price is None:
            return None

        try:
            price_float = float(price)
        except (ValueError, TypeError):
            return None

        # Formata preço no padrão brasileiro
        price_raw = f"R$ {price_float:.2f}".replace(".", ",")

        # Extrai preço unitário se disponível
        unit_price_raw = None
        unit_price = item.get("unitPrice")
        unit = item.get("unit", "")
        if unit_price:
            try:
                unit_price_raw = f"R$ {float(unit_price):.2f}/{unit}".replace(".", ",")
            except (ValueError, TypeError):
                pass

        # Extrai URL do produto
        product_url = item.get("url", "")
        if product_url:
            if not product_url.startswith("http"):
                product_url = f"https://www.paodeacucar.com{product_url}"
        else:
            product_id = item.get("id")
            if product_id:
                product_url = f"https://www.paodeacucar.com/produto/{product_id}/p"
            else:
                product_url = "https://www.paodeacucar.com"

        # Extrai URL da imagem
        image_url = item.get("image") or item.get("imageUrl")

        # Verifica disponibilidade
        is_available = item.get("available", True)

        # Extrai ID externo
        external_id = str(item.get("id", "")) if item.get("id") else None

        return RawProduct(
            market_id=self.market_id,
            external_id=external_id,
            title=title.strip(),
            price_raw=price_raw,
            unit_price_raw=unit_price_raw,
            url=product_url,
            image_url=image_url,
            availability_raw="Disponível" if is_available else "Indisponível",
            search_query=search_query,
            cep=cep,
            collected_at=datetime.now(),
            extra_data={
                "position": position,
                "source": "api",
                "brand": item.get("brand"),
                "original_price": item.get("originalPrice"),
                "quantity": item.get("quantity"),
            },
        )

    async def _try_set_cep(self, page: Page, cep: str) -> bool:
        """
        Tenta configurar CEP e obter store_id correspondente.
        """
        try:
            cep_clean = cep.replace("-", "").replace(".", "")

            # Tenta obter store_id pelo CEP usando a API
            store_result = await page.evaluate("""
                async (cep) => {
                    try {
                        const response = await fetch(`https://api.vendas.gpa.digital/pa/delivery/stores?zipCode=${cep}`, {
                            method: "GET",
                            headers: {
                                "Accept": "application/json",
                            },
                        });
                        
                        if (!response.ok) {
                            return { error: true, status: response.status };
                        }
                        
                        const data = await response.json();
                        return { error: false, data: data };
                    } catch (e) {
                        return { error: true, message: e.message };
                    }
                }
            """, cep_clean)

            if store_result.get("error"):
                self.logger.debug("Não foi possível obter store_id pelo CEP")
                return False

            stores = store_result.get("data", {}).get("stores", [])
            if stores:
                store_id = stores[0].get("id")
                store_name = stores[0].get("name", "")
                if store_id:
                    self._store_id = int(store_id)
                    self.logger.info(
                        "Store ID obtido pelo CEP",
                        store_id=self._store_id,
                        store_name=store_name,
                        cep=cep,
                    )
                    return True

            return False

        except Exception as e:
            self.logger.debug(f"Erro ao configurar CEP: {e}")
            return False

    # Métodos para compatibilidade com a interface esperada

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
        api_data = await self._fetch_api(page, search_query, page_num=1)
        if api_data and not api_data.get("error"):
            return self._parse_api_response(api_data, search_query, cep)
        return []


async def search_pao_acucar(query: str, cep: Optional[str] = None, max_pages: int = 1):
    """Função de conveniência."""
    scraper = PaoDeAcucarScraper()
    return await scraper.search(query, cep, max_pages)