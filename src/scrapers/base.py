"""
Base Scraper Corrigido - Versão 2
=================================

Correções aplicadas:
1. Melhor detecção de falsos positivos (cloudflare em footer, robot em produtos)
2. Suporte a CEP obrigatório
3. Extração de produtos funcional
4. Melhor tratamento de erros

SUBSTITUA o arquivo src/scrapers/base.py por este.
"""

import asyncio
import random
import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional
from urllib.parse import quote_plus

from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeout,
)
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

# Importações do projeto (ajuste conforme sua estrutura)
try:
    from src.core.exceptions import BlockedError, NetworkError, ScrapingError
    from src.core.models import RawProduct
    from config.markets import MarketConfig
except ImportError:
    # Fallback para execução standalone
    class BlockedError(Exception):
        pass
    class NetworkError(Exception):
        pass
    class ScrapingError(Exception):
        pass
    class RawProduct:
        pass
    class MarketConfig:
        pass


class BaseScraper(ABC):
    """Scraper base com melhorias anti-detecção."""
    
    # User agents reais e atualizados
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    ]
    
    # Palavras que indicam bloqueio REAL (não falsos positivos)
    BLOCK_INDICATORS = {
        "captcha": ["captcha", "recaptcha", "hcaptcha"],
        "cloudflare": ["checking your browser", "please wait", "ddos protection"],
        "access_denied": ["access denied", "acesso negado", "403 forbidden"],
        "rate_limit": ["rate limit", "too many requests", "muitas requisições"],
    }
    
    # Contextos que indicam FALSO POSITIVO
    FALSE_POSITIVE_CONTEXTS = [
        "robô aspirador",
        "robô de limpeza", 
        "robot vacuum",
        "cloudflare.com",  # Link para cloudflare, não bloqueio
        "powered by cloudflare",  # Footer
        "© cloudflare",
    ]
    
    def __init__(self, config: MarketConfig):
        self.config = config
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        
    async def __aenter__(self):
        await self._setup_browser()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._cleanup()
        
    async def _setup_browser(self):
        """Configura o browser com opções anti-detecção."""
        self._playwright = await async_playwright().start()
        
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-infobars",
                "--window-size=1920,1080",
                "--disable-extensions",
            ],
        )
        
        # Contexto com configurações realistas
        self._context = await self._browser.new_context(
            user_agent=random.choice(self.USER_AGENTS),
            viewport={"width": 1920, "height": 1080},
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            geolocation={"latitude": -23.5505, "longitude": -46.6333},  # São Paulo
            permissions=["geolocation"],
            extra_http_headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Cache-Control": "max-age=0",
            },
        )
        
        # Script anti-detecção
        await self._context.add_init_script("""
            // Esconde webdriver
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined,
            });
            
            // Esconde automação do Chrome
            window.chrome = {
                runtime: {},
            };
            
            // Plugins falsos
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
            });
            
            // Languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['pt-BR', 'pt', 'en-US', 'en'],
            });
            
            // Permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
        """)
        
    async def _cleanup(self):
        """Limpa recursos do browser."""
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
            
    def _is_blocked(self, html_content: str) -> tuple[bool, Optional[str]]:
        """
        Verifica se a página indica bloqueio.
        
        Returns:
            tuple: (is_blocked, block_type)
        """
        if not html_content:
            return False, None
            
        html_lower = html_content.lower()
        
        # Primeiro, verifica se é falso positivo
        for fp_context in self.FALSE_POSITIVE_CONTEXTS:
            if fp_context in html_lower:
                # Se encontrou contexto de falso positivo, ignora
                return False, None
        
        # Verifica indicadores de bloqueio real
        for block_type, indicators in self.BLOCK_INDICATORS.items():
            for indicator in indicators:
                if indicator in html_lower:
                    # Verifica contexto para evitar falsos positivos
                    if not self._is_false_positive(html_lower, indicator):
                        return True, block_type
                        
        return False, None
    
    def _is_false_positive(self, html_lower: str, indicator: str) -> bool:
        """Verifica se o indicador é um falso positivo."""
        
        # Se "robot" aparece em contexto de produto
        if indicator == "robot":
            robot_contexts = ["robô", "robot vacuum", "aspirador", "limpeza"]
            for ctx in robot_contexts:
                if ctx in html_lower:
                    return True
                    
        # Se "cloudflare" aparece apenas no footer
        if indicator in ["cloudflare", "checking your browser"]:
            # Verifica se há produtos na página (indica que não está bloqueado)
            product_indicators = ["preço", "price", "adicionar", "carrinho", "comprar"]
            for prod_ind in product_indicators:
                if prod_ind in html_lower:
                    return True
                    
        return False
    
    async def _set_cep(self, page: Page, cep: str) -> bool:
        """
        Define o CEP no site, se necessário.
        
        Returns:
            bool: True se conseguiu definir o CEP
        """
        if not cep or not self.config.requires_cep:
            return True
            
        try:
            # Seletores comuns para input de CEP
            cep_selectors = [
                self.config.selectors.cep_input,
                "input[placeholder*='CEP']",
                "input[name*='cep']",
                "input[id*='cep']",
                "input[class*='cep']",
            ]
            
            for selector in cep_selectors:
                if not selector:
                    continue
                try:
                    cep_input = await page.wait_for_selector(selector, timeout=5000)
                    if cep_input:
                        await cep_input.fill(cep)
                        
                        # Tenta clicar no botão de confirmar
                        submit_selectors = [
                            self.config.selectors.cep_submit,
                            "button[class*='cep']",
                            "button[type='submit']",
                        ]
                        
                        for submit_sel in submit_selectors:
                            if not submit_sel:
                                continue
                            try:
                                submit_btn = await page.query_selector(submit_sel)
                                if submit_btn:
                                    await submit_btn.click()
                                    await page.wait_for_timeout(2000)
                                    return True
                            except:
                                continue
                                
                        # Se não achou botão, tenta Enter
                        await cep_input.press("Enter")
                        await page.wait_for_timeout(2000)
                        return True
                        
                except PlaywrightTimeout:
                    continue
                    
        except Exception as e:
            print(f"Erro ao definir CEP: {e}")
            
        return False
    
    async def search(
        self,
        query: str,
        cep: Optional[str] = None,
        max_pages: int = 1,
    ) -> list[dict]:
        """
        Executa busca no mercado.
        
        Args:
            query: Termo de busca
            cep: CEP para localização
            max_pages: Número máximo de páginas
            
        Returns:
            Lista de produtos encontrados
        """
        all_products = []
        
        async with self:
            page = await self._context.new_page()
            
            try:
                # Primeiro acessa a home para pegar cookies
                print(f"[{self.config.name}] Acessando home...")
                await page.goto(
                    self.config.base_url,
                    wait_until="domcontentloaded",
                    timeout=30000
                )
                await page.wait_for_timeout(2000)
                
                # Define CEP se necessário
                if cep and self.config.requires_cep:
                    print(f"[{self.config.name}] Definindo CEP: {cep}")
                    await self._set_cep(page, cep)
                
                # Navega para cada página de resultados
                for page_num in range(max_pages):
                    url = self._build_search_url(query, page_num)
                    print(f"[{self.config.name}] Buscando: {url}")
                    
                    products = await self._scrape_page(page, url, query, cep)
                    
                    if not products:
                        print(f"[{self.config.name}] Nenhum produto encontrado na página {page_num + 1}")
                        break
                        
                    all_products.extend(products)
                    print(f"[{self.config.name}] Encontrados {len(products)} produtos na página {page_num + 1}")
                    
                    # Delay entre páginas
                    if page_num < max_pages - 1:
                        await asyncio.sleep(random.uniform(2, 4))
                        
            except Exception as e:
                print(f"[{self.config.name}] Erro: {e}")
                raise
            finally:
                await page.close()
                
        return all_products
    
    def _build_search_url(self, query: str, page: int = 0) -> str:
        """Constrói a URL de busca."""
        # Codifica a query
        encoded_query = quote_plus(query)
        
        # Substitui placeholders na URL
        url = self.config.search_url.format(
            query=encoded_query,
            page=page
        )
        
        return url
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((NetworkError, PlaywrightTimeout)),
    )
    async def _scrape_page(
        self,
        page: Page,
        url: str,
        search_query: str,
        cep: Optional[str],
    ) -> list[dict]:
        """Faz scraping de uma página de resultados."""
        
        # Navega para a URL
        response = await page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=30000
        )
        
        # Verifica status HTTP
        if response and response.status >= 400:
            raise NetworkError(
                f"Status {response.status}",
                details={
                    "status_code": response.status,
                    "market_id": self.config.id,
                    "url": url,
                }
            )
        
        # Aguarda carregamento do JavaScript
        await page.wait_for_timeout(3000)
        
        # Obtém HTML
        html_content = await page.content()
        
        # Verifica bloqueio (com melhor detecção)
        is_blocked, block_type = self._is_blocked(html_content)
        if is_blocked:
            raise BlockedError(
                f"Detectado possível bloqueio: {block_type}",
                details={
                    "block_type": block_type,
                    "market_id": self.config.id,
                }
            )
        
        # Aguarda produtos carregarem
        await self._wait_for_products(page)
        
        # Extrai produtos
        products = await self.extract_products(page, search_query, cep)
        
        return products
    
    async def _wait_for_products(self, page: Page, timeout: int = 10000):
        """Aguarda os produtos carregarem na página."""
        selectors = self.config.selectors.product_container.split(", ")
        
        for selector in selectors:
            try:
                await page.wait_for_selector(
                    selector.strip(),
                    timeout=timeout,
                    state="attached"
                )
                return
            except PlaywrightTimeout:
                continue
                
        # Se nenhum seletor funcionou, não é erro - pode ser página sem resultados
        print(f"[{self.config.name}] Aviso: Nenhum produto encontrado com seletores padrão")
    
    @abstractmethod
    async def extract_products(
        self,
        page: Page,
        search_query: str,
        cep: Optional[str],
    ) -> list[dict]:
        """
        Extrai produtos da página. Deve ser implementado por cada scraper.
        """
        pass


class GenericScraper(BaseScraper):
    """Scraper genérico que funciona com a maioria dos sites."""
    
    async def extract_products(
        self,
        page: Page,
        search_query: str,
        cep: Optional[str],
    ) -> list[dict]:
        """Extrai produtos usando seletores genéricos."""
        
        products = []
        selectors = self.config.selectors
        
        # Tenta cada seletor de container
        container_selectors = selectors.product_container.split(", ")
        
        for container_sel in container_selectors:
            try:
                elements = await page.query_selector_all(container_sel.strip())
                
                if not elements:
                    continue
                    
                for element in elements:
                    try:
                        product = await self._extract_single_product(element, selectors)
                        if product and product.get("name"):
                            product["market_id"] = self.config.id
                            product["search_query"] = search_query
                            product["cep"] = cep
                            product["collected_at"] = datetime.now().isoformat()
                            products.append(product)
                    except Exception as e:
                        continue
                        
                if products:
                    break
                    
            except Exception as e:
                continue
                
        return products
    
    async def _extract_single_product(self, element, selectors) -> Optional[dict]:
        """Extrai dados de um único produto."""
        
        product = {}
        
        # Nome
        try:
            title_sels = selectors.product_title.split(", ")
            for title_sel in title_sels:
                title_elem = await element.query_selector(title_sel.strip())
                if title_elem:
                    product["name"] = await title_elem.inner_text()
                    product["name"] = product["name"].strip()
                    break
        except:
            pass
            
        # Preço
        try:
            price_sels = selectors.product_price.split(", ")
            for price_sel in price_sels:
                price_elem = await element.query_selector(price_sel.strip())
                if price_elem:
                    price_text = await price_elem.inner_text()
                    product["price"] = self._parse_price(price_text)
                    break
        except:
            pass
            
        # Link
        try:
            if selectors.product_link:
                link_sels = selectors.product_link.split(", ")
                for link_sel in link_sels:
                    link_elem = await element.query_selector(link_sel.strip())
                    if link_elem:
                        href = await link_elem.get_attribute("href")
                        if href:
                            if href.startswith("/"):
                                href = self.config.base_url + href
                            product["url"] = href
                            break
        except:
            pass
            
        # Imagem
        try:
            if selectors.product_image:
                img_sels = selectors.product_image.split(", ")
                for img_sel in img_sels:
                    img_elem = await element.query_selector(img_sel.strip())
                    if img_elem:
                        src = await img_elem.get_attribute("src")
                        if not src:
                            src = await img_elem.get_attribute("data-src")
                        if src:
                            product["image_url"] = src
                            break
        except:
            pass
            
        return product if product.get("name") else None
    
    def _parse_price(self, price_text: str) -> Optional[float]:
        """Converte texto de preço para float."""
        if not price_text:
            return None
            
        try:
            # Remove caracteres não numéricos exceto vírgula e ponto
            price_text = re.sub(r'[^\d,.]', '', price_text)
            
            # Trata formato brasileiro (1.234,56) e americano (1,234.56)
            if ',' in price_text and '.' in price_text:
                if price_text.rfind(',') > price_text.rfind('.'):
                    # Formato brasileiro: 1.234,56
                    price_text = price_text.replace('.', '').replace(',', '.')
                else:
                    # Formato americano: 1,234.56
                    price_text = price_text.replace(',', '')
            elif ',' in price_text:
                # Apenas vírgula: assume brasileiro
                price_text = price_text.replace(',', '.')
                
            return float(price_text)
        except (ValueError, TypeError):
            return None