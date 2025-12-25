"""
Classe base para scrapers de mercados.
Com configurações melhoradas para evitar detecção de bot e
detecção de bloqueio corrigida para evitar falsos positivos.

SUBSTITUA o conteúdo de src/scrapers/base.py por este arquivo.
"""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from urllib.parse import quote
import random
import re

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

from config.logging_config import LoggerMixin
from config.markets import MarketConfig, MarketSelectors
from config.settings import get_settings
from src.core.exceptions import (
    ScraperError,
    NetworkError,
    BlockedError,
    HTMLChangedError,
    RateLimitError,
)
from src.core.models import RawProduct
from src.core.types import CollectionStatus
from src.scrapers.rate_limiter import get_rate_limiter


# =============================================================================
# RESULTADO DO SCRAPER
# =============================================================================

@dataclass
class ScraperResult:
    """Resultado de uma execução de scraper."""
    
    market_id: str
    search_query: str
    status: CollectionStatus
    products: list[RawProduct] = field(default_factory=list)
    error_message: Optional[str] = None
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: Optional[datetime] = None
    pages_scraped: int = 0
    
    def mark_finished(self):
        """Marca como finalizado."""
        self.finished_at = datetime.now()
    
    @property
    def duration_seconds(self) -> Optional[float]:
        """Duração em segundos."""
        if self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None
    
    @property
    def products_count(self) -> int:
        """Quantidade de produtos coletados."""
        return len(self.products)


# =============================================================================
# CLASSE BASE DO SCRAPER
# =============================================================================

class BaseScraper(ABC, LoggerMixin):
    """
    Classe base abstrata para todos os scrapers de mercados.
    Implementa funcionalidades comuns e define interface.
    """
    
    # User agents reais para rotação
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    ]
    
    # Indicadores de bloqueio REAL (não falsos positivos)
    BLOCK_INDICATORS = {
        "captcha": ["captcha", "recaptcha", "hcaptcha", "verificação de segurança"],
        "cloudflare_challenge": ["checking your browser", "please wait", "ddos protection by"],
        "access_denied": ["access denied", "acesso negado", "403 forbidden", "bloqueado"],
        "rate_limit": ["rate limit", "too many requests", "muitas requisições"],
        "bot_detection": ["você é um robô", "are you a robot", "bot detected"],
    }
    
    # Contextos que indicam FALSO POSITIVO (não é bloqueio)
    FALSE_POSITIVE_CONTEXTS = [
        # Produtos com "robô" no nome
        "robô aspirador", "robô de limpeza", "robo aspirador", "robot vacuum",
        "aspirador robô", "robô mop", "robô híbrido",
        # Menções normais do Cloudflare (não bloqueio)
        "cloudflare.com", "powered by cloudflare", "© cloudflare",
        "cdn.cloudflare", "cdnjs.cloudflare",
        # Outros falsos positivos
        "robot de cocina", "robot de cozinha",
    ]
    
    def __init__(self, config: MarketConfig):
        """
        Inicializa o scraper.
        
        Args:
            config: Configuração do mercado
        """
        self.config = config
        self.settings = get_settings()
        self.rate_limiter = get_rate_limiter()
        
        # Configura rate limiter para este mercado
        self.rate_limiter.configure(
            self.config.id,
            self.config.requests_per_minute,
        )
        
        # Estado do Playwright
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
    
    @property
    def market_id(self) -> str:
        """ID do mercado."""
        return self.config.id
    
    @property
    def selectors(self) -> MarketSelectors:
        """Seletores CSS do mercado."""
        return self.config.selectors
    
    # MÉTODOS ABSTRATOS (devem ser implementados por cada scraper)
    
    @abstractmethod
    async def extract_products(
        self,
        page: Page,
        search_query: str,
        cep: Optional[str] = None,
    ) -> list[RawProduct]:
        """
        Extrai produtos da página de resultados.
        """
        pass
    
    @abstractmethod
    async def set_location(
        self,
        page: Page,
        cep: str,
    ) -> bool:
        """
        Configura CEP/localização no site.
        """
        pass
    
    # MÉTODOS COMUNS
    
    async def search(
        self,
        query: str,
        cep: Optional[str] = None,
        max_pages: int = 1,
    ) -> ScraperResult:
        """
        Executa busca no mercado.
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
            page = await self._create_page()
            
            # Configura CEP se fornecido
            if cep:
                cep_success = await self._safe_set_location(page, cep)
                if not cep_success:
                    self.logger.warning(
                        "Não foi possível configurar CEP, continuando sem",
                        cep=cep,
                    )
            
            # Coleta produtos de cada página
            all_products = []
            for page_num in range(1, max_pages + 1):
                # Rate limiting
                await self.rate_limiter.acquire(self.market_id)
                
                # Navega para página de busca
                search_url = self.config.get_search_url(
                    quote(query),
                    page_num - 1,  # Muitos sites usam page=0 como primeiro
                )
                
                products = await self._scrape_page(
                    page,
                    search_url,
                    query,
                    cep,
                )
                
                if products:
                    all_products.extend(products)
                    result.pages_scraped += 1
                    self.logger.info(
                        "Página coletada",
                        page=page_num,
                        products=len(products),
                    )
                else:
                    # Sem mais produtos, para
                    break
                
                # Verifica se há próxima página
                if not await self._has_next_page(page):
                    break
                
                # Delay aleatório entre páginas (parecer mais humano)
                await asyncio.sleep(random.uniform(2, 4))
            
            result.products = all_products
            result.status = (
                CollectionStatus.SUCCESS if all_products
                else CollectionStatus.NO_RESULTS
            )
            
        except BlockedError as e:
            result.status = CollectionStatus.BLOCKED
            result.error_message = str(e)
            self.logger.error("Bloqueado pelo site", error=str(e))
            
        except PlaywrightTimeout as e:
            result.status = CollectionStatus.TIMEOUT
            result.error_message = str(e)
            self.logger.error("Timeout na coleta", error=str(e))
            
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
    ) -> list[RawProduct]:
        """
        Coleta produtos de uma página específica.
        """
        self.logger.debug("Navegando para URL", url=url)
        
        # Navega com timeout generoso
        response = await page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=self.settings.playwright_timeout,
        )
        
        # Aguarda um pouco para JavaScript carregar
        await page.wait_for_timeout(3000)
        
        # Verifica resposta
        if response and response.status >= 400:
            if response.status == 429:
                raise RateLimitError(
                    market_id=self.market_id,
                    url=url,
                )
            raise NetworkError(
                f"Status {response.status}",
                market_id=self.market_id,
                url=url,
                status_code=response.status,
            )
        
        # Verifica bloqueio (com detecção melhorada)
        await self._check_for_blocks(page)
        
        # Aguarda carregamento dos produtos
        await self._wait_for_products(page)
        
        # Extrai produtos
        return await self.extract_products(page, search_query, cep)
    
    async def _safe_set_location(
        self,
        page: Page,
        cep: str,
    ) -> bool:
        """Tenta configurar localização com tratamento de erro."""
        try:
            return await self.set_location(page, cep)
        except Exception as e:
            self.logger.warning(
                "Erro ao configurar CEP",
                cep=cep,
                error=str(e),
            )
            return False
    
    async def _wait_for_products(self, page: Page) -> None:
        """Aguarda carregamento dos produtos na página."""
        # Tenta múltiplos seletores
        selectors = self.selectors.product_container.split(", ")
        
        for selector in selectors:
            try:
                await page.wait_for_selector(
                    selector.strip(),
                    timeout=10000,  # 10 segundos por seletor
                )
                self.logger.debug("Produtos encontrados", selector=selector)
                return
            except PlaywrightTimeout:
                continue
        
        self.logger.debug("Timeout aguardando produtos - tentando continuar")
    
    async def _has_next_page(self, page: Page) -> bool:
        """Verifica se existe próxima página."""
        if not self.selectors.next_page:
            return False
        
        try:
            next_btn = await page.query_selector(self.selectors.next_page)
            if next_btn:
                is_disabled = await next_btn.get_attribute("disabled")
                return is_disabled is None
        except Exception:
            pass
        
        return False
    
    async def _check_for_blocks(self, page: Page) -> None:
        """
        Verifica se a página indica bloqueio.
        Versão melhorada com detecção de falsos positivos.
        """
        content = await page.content()
        content_lower = content.lower()
        
        # Primeiro, verifica se há produtos na página (indica que NÃO é bloqueio)
        if self._has_product_indicators(content_lower):
            self.logger.debug("Página contém indicadores de produtos - não é bloqueio")
            return
        
        # Verifica cada categoria de bloqueio
        for block_type, indicators in self.BLOCK_INDICATORS.items():
            for indicator in indicators:
                if indicator in content_lower:
                    # Verifica se não é falso positivo
                    if not self._is_false_positive(content_lower, indicator):
                        self.logger.warning(
                            "Possível bloqueio detectado",
                            type=block_type,
                            indicator=indicator,
                        )
                        raise BlockedError(
                            f"Detectado bloqueio: {block_type}",
                            market_id=self.market_id,
                            block_type=block_type,
                        )
    
    def _is_false_positive(self, content: str, indicator: str) -> bool:
        """
        Verifica se a detecção é um falso positivo.
        
        Args:
            content: Conteúdo da página (lowercase)
            indicator: Indicador que foi encontrado
            
        Returns:
            True se for falso positivo (não é bloqueio real)
        """
        # Verifica contextos conhecidos de falso positivo
        for context in self.FALSE_POSITIVE_CONTEXTS:
            if context in content:
                self.logger.debug(
                    "Falso positivo detectado",
                    indicator=indicator,
                    context=context,
                )
                return True
        
        # Se "robot" aparece, verifica se é produto
        if "robot" in indicator or "robô" in indicator:
            # Padrões de produtos com robô
            robot_product_patterns = [
                r"robô.*\d+.*ml",  # Robô com capacidade
                r"robô.*\d+.*w",   # Robô com potência
                r"r\$.*robô",      # Preço antes de robô
                r"robô.*r\$",      # Robô antes de preço
                r"aspirador.*robô",
                r"robô.*aspirador",
            ]
            for pattern in robot_product_patterns:
                if re.search(pattern, content):
                    return True
        
        # Se "cloudflare" aparece, verifica se é apenas menção no footer/scripts
        if "cloudflare" in indicator:
            # Cloudflare challenge tem frases específicas
            challenge_phrases = [
                "checking your browser",
                "please wait",
                "enable javascript",
                "ray id",
            ]
            # Se nenhuma frase de challenge, é falso positivo
            if not any(phrase in content for phrase in challenge_phrases):
                return True
        
        return False
    
    def _has_product_indicators(self, content: str) -> bool:
        """
        Verifica se a página contém indicadores de produtos.
        Se houver produtos, definitivamente não é uma página de bloqueio.
        
        Args:
            content: Conteúdo da página (lowercase)
            
        Returns:
            True se a página parece ter produtos
        """
        # Indicadores de que a página tem produtos
        product_indicators = [
            "adicionar ao carrinho",
            "add to cart",
            "comprar",
            "r$ ",  # Preço
            "preço",
            "price",
            "produto",
            "product",
            "/kg",
            "/un",
            "/l",
        ]
        
        # Conta quantos indicadores foram encontrados
        found_count = sum(1 for ind in product_indicators if ind in content)
        
        # Se encontrou 3 ou mais indicadores, provavelmente tem produtos
        return found_count >= 3
    
    # GERENCIAMENTO DO BROWSER - CONFIGURAÇÃO ANTI-DETECÇÃO
    
    async def _init_browser(self) -> None:
        """Inicializa o Playwright e browser com configurações anti-detecção."""
        if self._browser is not None:
            return
        
        self._playwright = await async_playwright().start()
        
        # Usa Chromium com configurações anti-detecção
        self._browser = await self._playwright.chromium.launch(
            headless=self.settings.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-infobars",
                "--window-size=1920,1080",
                "--start-maximized",
            ],
        )
        
        # Contexto com configurações que parecem um browser real
        self._context = await self._browser.new_context(
            user_agent=random.choice(self.USER_AGENTS),
            viewport={"width": 1920, "height": 1080},
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            geolocation={"latitude": -12.9714, "longitude": -38.5014},  # Salvador
            permissions=["geolocation"],
            java_script_enabled=True,
            accept_downloads=False,
            extra_http_headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
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
        
        # Adiciona script para esconder automação
        await self._context.add_init_script("""
            // Esconde webdriver
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined,
            });
            
            // Esconde automação do Chrome
            window.chrome = {
                runtime: {},
            };
            
            // Esconde permissões
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
            
            // Plugins falsos
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
            });
            
            // Languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['pt-BR', 'pt', 'en-US', 'en'],
            });
        """)
    
    async def _create_page(self) -> Page:
        """Cria nova página no contexto."""
        if self._context is None:
            await self._init_browser()
        
        page = await self._context.new_page()
        
        # Configura timeout padrão
        page.set_default_timeout(self.settings.playwright_timeout)
        
        return page
    
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
    
    # HELPERS DE EXTRAÇÃO
    
    async def _safe_get_text(
        self,
        element: Any,
        selector: str,
        default: str = "",
    ) -> str:
        """Extrai texto de elemento de forma segura."""
        # Tenta múltiplos seletores separados por vírgula
        selectors = selector.split(", ")
        
        for sel in selectors:
            try:
                child = await element.query_selector(sel.strip())
                if child:
                    text = await child.inner_text()
                    if text and text.strip():
                        return text.strip()
            except Exception:
                continue
        
        return default
    
    async def _safe_get_attribute(
        self,
        element: Any,
        selector: str,
        attribute: str,
        default: str = "",
    ) -> str:
        """Extrai atributo de elemento de forma segura."""
        selectors = selector.split(", ")
        
        for sel in selectors:
            try:
                child = await element.query_selector(sel.strip())
                if child:
                    value = await child.get_attribute(attribute)
                    if value and value.strip():
                        return value.strip()
            except Exception:
                continue
        
        return default