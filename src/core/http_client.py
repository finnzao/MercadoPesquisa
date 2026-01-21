"""
Cliente HTTP otimizado para scraping.
Regras: sessão estável, UA fixo, sem Accept-Encoding manual, rate limit conservador.
Caminho: /src/core/http_client.py
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from collections import defaultdict

import httpx

from config.logging_config import LoggerMixin
from config.settings import get_settings


class MarketSession(LoggerMixin):
    """
    Sessão dedicada por mercado.
    1 mercado = 1 client = 1 UA = 1 identidade.
    """
    
    DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    
    def __init__(self, market_id: str, requests_per_minute: int = 10):
        self.market_id = market_id
        self.requests_per_minute = requests_per_minute
        self._client: Optional[httpx.AsyncClient] = None
        self._request_times: list[datetime] = []
        self._lock = asyncio.Lock()
        self._blocked_until: Optional[datetime] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=5.0),
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
                follow_redirects=True,
                headers={
                    "User-Agent": self.DEFAULT_UA,
                    "Accept": "application/json, text/html, */*;q=0.8",
                    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
                    "Connection": "keep-alive",
                },
            )
        return self._client
    
    async def _wait_rate_limit(self) -> None:
        async with self._lock:
            now = datetime.now()
            
            if self._blocked_until and now < self._blocked_until:
                wait = (self._blocked_until - now).total_seconds()
                self.logger.warning("Aguardando cooldown", market=self.market_id, seconds=wait)
                await asyncio.sleep(wait)
                self._blocked_until = None
            
            cutoff = now - timedelta(minutes=1)
            self._request_times = [t for t in self._request_times if t > cutoff]
            
            if len(self._request_times) >= self.requests_per_minute:
                oldest = self._request_times[0]
                wait = (oldest + timedelta(minutes=1) - now).total_seconds()
                if wait > 0:
                    await asyncio.sleep(wait + 0.1)
            
            self._request_times.append(datetime.now())
    
    def _handle_error_status(self, status: int) -> None:
        if status == 429:
            self._blocked_until = datetime.now() + timedelta(seconds=60)
            self.logger.warning("Rate limit 429", market=self.market_id)
        elif status == 403:
            self._blocked_until = datetime.now() + timedelta(seconds=120)
            self.logger.error("Bloqueio 403", market=self.market_id)
    
    def _add_referer(self, url: str, headers: Dict) -> Dict:
        if "Referer" not in headers:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"
            headers["Origin"] = f"{parsed.scheme}://{parsed.netloc}"
        return headers
    
    async def get(self, url: str, **kwargs) -> httpx.Response:
        await self._wait_rate_limit()
        client = await self._get_client()
        headers = self._add_referer(url, kwargs.pop("headers", {}))
        
        response = await client.get(url, headers=headers, **kwargs)
        
        if response.status_code in (403, 429):
            self._handle_error_status(response.status_code)
        
        return response
    
    async def post(self, url: str, **kwargs) -> httpx.Response:
        await self._wait_rate_limit()
        client = await self._get_client()
        headers = self._add_referer(url, kwargs.pop("headers", {}))
        
        if "json" in kwargs:
            headers.setdefault("Content-Type", "application/json")
        
        response = await client.post(url, headers=headers, **kwargs)
        
        if response.status_code in (403, 429):
            self._handle_error_status(response.status_code)
        
        return response
    
    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None


class HTTPClientPool(LoggerMixin):
    """Pool de sessões HTTP por mercado."""
    
    _instance: Optional["HTTPClientPool"] = None
    _lock = asyncio.Lock()
    
    def __init__(self):
        self._sessions: Dict[str, MarketSession] = {}
        self._session_locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
    
    @classmethod
    async def get_instance(cls) -> "HTTPClientPool":
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    def _get_rate_limit(self, market_id: str) -> int:
        from config.markets import MARKETS_CONFIG
        config = MARKETS_CONFIG.get(market_id)
        return config.requests_per_minute if config else 10
    
    async def get_session(self, market_id: str) -> MarketSession:
        async with self._session_locks[market_id]:
            if market_id not in self._sessions:
                rate_limit = self._get_rate_limit(market_id)
                self._sessions[market_id] = MarketSession(market_id, rate_limit)
            return self._sessions[market_id]
    
    async def get(self, url: str, market_id: str, **kwargs) -> httpx.Response:
        session = await self.get_session(market_id)
        return await session.get(url, **kwargs)
    
    async def post(self, url: str, market_id: str, **kwargs) -> httpx.Response:
        session = await self.get_session(market_id)
        return await session.post(url, **kwargs)
    
    async def close_session(self, market_id: str) -> None:
        if market_id in self._sessions:
            await self._sessions[market_id].close()
            del self._sessions[market_id]
    
    async def close_all(self) -> None:
        for session in self._sessions.values():
            await session.close()
        self._sessions.clear()


_pool: Optional[HTTPClientPool] = None


async def get_http_client() -> HTTPClientPool:
    global _pool
    if _pool is None:
        _pool = await HTTPClientPool.get_instance()
    return _pool


class _HTTPClientProxy:
    async def get(self, url: str, market_id: str, **kwargs) -> httpx.Response:
        pool = await get_http_client()
        return await pool.get(url, market_id, **kwargs)
    
    async def post(self, url: str, market_id: str, **kwargs) -> httpx.Response:
        pool = await get_http_client()
        return await pool.post(url, market_id, **kwargs)
    
    async def close(self) -> None:
        pool = await get_http_client()
        await pool.close_all()


http_client = _HTTPClientProxy()
