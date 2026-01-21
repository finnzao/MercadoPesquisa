"""
Base Scraper Refatorado - Usa pools compartilhados.
Substitui: src/scrapers/base.py
"""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any
from urllib.parse import quote
import random

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from config.logging_config import LoggerMixin
from config.markets import MarketConfig, MarketSelectors
from config.settings import get_settings
from src.core.browser_pool import get_browser_pool
from src.core.http_client import get_http_client
from src.core.models import RawProduct
from src.core.types import CollectionStatus


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
        self.finished_at = datetime.now()
    
    @property
    def duration_seconds(self) -> Optional[float]:
        if self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None
    
    @property
    def products_count(self) -> int:
        return len(self.products)


class BaseScraper(ABC, LoggerMixin):
    """
    Base para scrapers - usa pools compartilhados.
    Não cria browser/cliente próprio.
    """
    
    BLOCK_INDICATORS = ["captcha", "recaptcha", "access denied", "blocked"]
    
    def __init__(self, config: MarketConfig):
        self.config = config
        self.settings = get_settings()
    
    @property
    def market_id(self) -> str:
        return self.config.id
    
    @property
    def selectors(self) -> MarketSelectors:
        return self.config.selectors
    
    @abstractmethod
    async def extract_products(self, page: Page, search_query: str, cep: Optional[str] = None) -> list[RawProduct]:
        """Extrai produtos da página."""
        pass
    
    @abstractmethod
    async def set_location(self, page: Page, cep: str) -> bool:
        """Configura CEP/localização."""
        pass
    
    def _build_search_url(self, query: str, page: int = 0) -> str:
        """Constrói URL de busca. Pode ser sobrescrito."""
        return self.config.get_search_url(quote(query), page)
    
    async def search(self, query: str, cep: Optional[str] = None, max_pages: int = 1) -> ScraperResult:
        """Executa busca usando browser pool."""
        result = ScraperResult(
            market_id=self.market_id,
            search_query=query,
            status=CollectionStatus.FAILED,
        )
        
        self.logger.info("Iniciando busca", market=self.market_id, query=query)
        
        try:
            browser_pool = await get_browser_pool()
            
            async with browser_pool.get_page(self.market_id) as page:
                # Configura CEP se fornecido
                if cep:
                    await self._safe_set_location(page, cep)
                
                all_products = []
                
                for page_num in range(1, max_pages + 1):
                    search_url = self._build_search_url(query, page_num - 1)
                    
                    products = await self._scrape_page(page, search_url, query, cep)
                    
                    if products:
                        all_products.extend(products)
                        result.pages_scraped += 1
                        self.logger.info("Página coletada", page=page_num, products=len(products))
                    else:
                        break
                    
                    if not await self._has_next_page(page):
                        break
                    
                    await asyncio.sleep(random.uniform(1.5, 3))
                
                result.products = all_products
                result.status = CollectionStatus.SUCCESS if all_products else CollectionStatus.NO_RESULTS
                
        except PlaywrightTimeout as e:
            result.status = CollectionStatus.TIMEOUT
            result.error_message = str(e)
            self.logger.error("Timeout", error=str(e))
            
        except Exception as e:
            result.status = CollectionStatus.FAILED
            result.error_message = str(e)
            self.logger.error("Erro na coleta", error=str(e), exc_info=True)
        
        finally:
            result.mark_finished()
        
        self.logger.info(
            "Busca finalizada",
            market=self.market_id,
            status=result.status.value,
            products=result.products_count,
            duration=f"{result.duration_seconds:.2f}s" if result.duration_seconds else "N/A",
        )
        
        return result
    
    async def _scrape_page(self, page: Page, url: str, search_query: str, cep: Optional[str]) -> list[RawProduct]:
        """Coleta produtos de uma página."""
        response = await page.goto(url, wait_until="domcontentloaded", timeout=self.settings.playwright_timeout)
        await page.wait_for_timeout(2000)
        
        if response and response.status >= 400:
            raise Exception(f"HTTP {response.status}")
        
        await self._check_for_blocks(page)
        await self._wait_for_products(page)
        
        return await self.extract_products(page, search_query, cep)
    
    async def _safe_set_location(self, page: Page, cep: str) -> bool:
        try:
            return await self.set_location(page, cep)
        except Exception as e:
            self.logger.warning("Erro ao configurar CEP", error=str(e))
            return False
    
    async def _wait_for_products(self, page: Page) -> None:
        """Aguarda produtos carregarem."""
        selectors = self.selectors.product_container.split(", ")
        for selector in selectors:
            try:
                await page.wait_for_selector(selector.strip(), timeout=10000)
                return
            except PlaywrightTimeout:
                continue
    
    async def _has_next_page(self, page: Page) -> bool:
        if not self.selectors.next_page:
            return False
        try:
            btn = await page.query_selector(self.selectors.next_page)
            if btn:
                return await btn.get_attribute("disabled") is None
        except Exception:
            pass
        return False
    
    async def _check_for_blocks(self, page: Page) -> None:
        """Verifica bloqueio."""
        content = (await page.content()).lower()
        
        # Se tem indicadores de produtos, não é bloqueio
        if any(ind in content for ind in ["adicionar", "carrinho", "r$ ", "comprar"]):
            return
        
        for indicator in self.BLOCK_INDICATORS:
            if indicator in content:
                from src.core.exceptions import BlockedError
                raise BlockedError(f"Bloqueio detectado: {indicator}", market_id=self.market_id)
    
    # Helpers de extração
    async def _safe_get_text(self, element: Any, selector: str, default: str = "") -> str:
        for sel in selector.split(", "):
            try:
                child = await element.query_selector(sel.strip())
                if child:
                    text = await child.inner_text()
                    if text and text.strip():
                        return text.strip()
            except Exception:
                continue
        return default
    
    async def _safe_get_attribute(self, element: Any, selector: str, attr: str, default: str = "") -> str:
        for sel in selector.split(", "):
            try:
                child = await element.query_selector(sel.strip())
                if child:
                    value = await child.get_attribute(attr)
                    if value and value.strip():
                        return value.strip()
            except Exception:
                continue
        return default
