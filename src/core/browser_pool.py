"""
Browser Pool Manager - Reutiliza instâncias Playwright.
Evita criar/destruir browsers a cada requisição.
"""

import asyncio
from typing import Optional, Dict
from contextlib import asynccontextmanager

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright

from config.logging_config import LoggerMixin
from config.settings import get_settings


class BrowserPool(LoggerMixin):
    """Pool de browsers Playwright com reutilização de contextos."""
    
    _instance: Optional["BrowserPool"] = None
    _lock = asyncio.Lock()
    
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    ]
    
    def __init__(self):
        self.settings = get_settings()
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._contexts: Dict[str, BrowserContext] = {}  # market_id -> context
        self._context_locks: Dict[str, asyncio.Lock] = {}
        self._initialized = False
        self._semaphore = asyncio.Semaphore(3)  # max 3 páginas simultâneas
    
    @classmethod
    async def get_instance(cls) -> "BrowserPool":
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    async def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        
        async with self._lock:
            if self._initialized:
                return
            
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=self.settings.headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                    "--disable-gpu",
                    "--single-process",
                ],
            )
            self._initialized = True
            self.logger.info("BrowserPool inicializado")
    
    async def _get_context(self, market_id: str) -> BrowserContext:
        """Retorna contexto reutilizável para um mercado."""
        await self._ensure_initialized()
        
        if market_id not in self._context_locks:
            self._context_locks[market_id] = asyncio.Lock()
        
        async with self._context_locks[market_id]:
            if market_id not in self._contexts:
                import random
                context = await self._browser.new_context(
                    user_agent=random.choice(self.USER_AGENTS),
                    viewport={"width": 1920, "height": 1080},
                    locale="pt-BR",
                    timezone_id="America/Sao_Paulo",
                    java_script_enabled=True,
                )
                
                # Script anti-detecção
                await context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                    window.chrome = { runtime: {} };
                """)
                
                self._contexts[market_id] = context
                self.logger.debug("Contexto criado", market=market_id)
            
            return self._contexts[market_id]
    
    @asynccontextmanager
    async def get_page(self, market_id: str):
        """
        Context manager para obter página.
        
        Uso:
            async with browser_pool.get_page("carrefour") as page:
                await page.goto(url)
        """
        async with self._semaphore:
            context = await self._get_context(market_id)
            page = await context.new_page()
            page.set_default_timeout(self.settings.playwright_timeout)
            
            try:
                yield page
            finally:
                await page.close()
    
    async def execute_in_page(self, market_id: str, url: str, script: str) -> any:
        """
        Navega para URL e executa script JS.
        Útil para APIs que precisam de contexto de navegador.
        """
        async with self.get_page(market_id) as page:
            await page.goto(url, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            return await page.evaluate(script)
    
    async def close_context(self, market_id: str) -> None:
        """Fecha contexto de um mercado específico."""
        if market_id in self._contexts:
            await self._contexts[market_id].close()
            del self._contexts[market_id]
            self.logger.debug("Contexto fechado", market=market_id)
    
    async def close(self) -> None:
        """Fecha todos os recursos."""
        for context in self._contexts.values():
            await context.close()
        self._contexts.clear()
        
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        
        self._initialized = False
        self.logger.info("BrowserPool fechado")
    
    @property
    def is_initialized(self) -> bool:
        return self._initialized
    
    @property
    def active_contexts(self) -> int:
        return len(self._contexts)


# Instância global
_browser_pool: Optional[BrowserPool] = None


async def get_browser_pool() -> BrowserPool:
    global _browser_pool
    if _browser_pool is None:
        _browser_pool = await BrowserPool.get_instance()
    return _browser_pool


# Alias para uso direto
browser_pool = BrowserPool()
