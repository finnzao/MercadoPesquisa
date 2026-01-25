# src/core/http_client.py
"""
Cliente HTTP resiliente com pool de conexões por mercado.
Gerencia sessões, rate limiting e retry automático.
"""

import asyncio
from typing import Dict, Optional
from urllib.parse import urlparse

import httpx

from config.logging_config import LoggerMixin
from config.settings import get_settings


class MarketSession(LoggerMixin):
    """Sessão HTTP dedicada para um mercado específico."""
    
    # User agent padrão
    DEFAULT_UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    
    # Configurações otimizadas
    CONNECT_TIMEOUT = 5.0
    READ_TIMEOUT = 15.0
    POOL_TIMEOUT = 10.0
    MAX_CONNECTIONS = 20
    MAX_KEEPALIVE = 10
    
    def __init__(self, market_id: str, requests_per_minute: int = 10):
        self.market_id = market_id
        self.requests_per_minute = requests_per_minute
        self._client: Optional[httpx.AsyncClient] = None
        self._last_request: float = 0
        self._lock = asyncio.Lock()
        # Semáforo para limitar concorrência por mercado
        self._semaphore = asyncio.Semaphore(min(requests_per_minute, 10))
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Obtém ou cria cliente HTTP com configurações otimizadas."""
        if self._client is None or self._client.is_closed:
            settings = get_settings()
            self._client = httpx.AsyncClient(
                http2=True,  # HTTP/2 para multiplexing
                timeout=httpx.Timeout(
                    connect=self.CONNECT_TIMEOUT,
                    read=self.READ_TIMEOUT,
                    write=self.READ_TIMEOUT,
                    pool=self.POOL_TIMEOUT,
                ),
                limits=httpx.Limits(
                    max_connections=self.MAX_CONNECTIONS,
                    max_keepalive_connections=self.MAX_KEEPALIVE,
                    keepalive_expiry=30.0,
                ),
                follow_redirects=True,
                headers={
                    "User-Agent": self.DEFAULT_UA,
                    "Accept": "application/json, text/plain, */*",
                    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Connection": "keep-alive",
                },
            )
        return self._client
    
    async def _wait_rate_limit(self):
        """Aguarda rate limit se necessário."""
        async with self._lock:
            now = asyncio.get_event_loop().time()
            min_interval = 60.0 / self.requests_per_minute
            elapsed = now - self._last_request
            
            if elapsed < min_interval:
                wait_time = min_interval - elapsed
                self.logger.debug(
                    "Rate limit - aguardando",
                    market=self.market_id,
                    wait=f"{wait_time:.2f}s",
                )
                await asyncio.sleep(wait_time)
            
            self._last_request = asyncio.get_event_loop().time()
    
    async def _handle_response(self, response: httpx.Response) -> httpx.Response:
        """Processa resposta e loga erros."""
        if response.status_code == 403:
            self.logger.error("Bloqueio 403", market=self.market_id)
        return response
    
    def _add_referer(self, url: str, headers: Optional[Dict]) -> Dict:
        """Adiciona Referer ao header se não existir."""
        if headers is None:
            headers = {}
        
        if "Referer" not in headers:
            parsed = urlparse(url)
            headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"
        
        return headers
    
    async def get(self, url: str, **kwargs) -> httpx.Response:
        """Executa requisição GET com controle de concorrência."""
        async with self._semaphore:
            await self._wait_rate_limit()
            client = await self._get_client()
            
            headers = self._add_referer(url, kwargs.pop("headers", None))
            
            response = await client.get(url, headers=headers, **kwargs)
            return await self._handle_response(response)
    
    async def post(self, url: str, **kwargs) -> httpx.Response:
        """Executa requisição POST com controle de concorrência."""
        async with self._semaphore:
            await self._wait_rate_limit()
            client = await self._get_client()
            
            headers = self._add_referer(url, kwargs.pop("headers", None))
            
            response = await client.post(url, headers=headers, **kwargs)
            return await self._handle_response(response)
    
    async def close(self):
        """Fecha a sessão."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None


class HTTPClientPool(LoggerMixin):
    """
    Pool de clientes HTTP por mercado.
    
    OTIMIZAÇÕES:
    - HTTP/2 com multiplexing
    - Connection pooling por mercado
    - Semáforos para controle de concorrência
    - Keep-alive agressivo
    """
    
    _instance: Optional["HTTPClientPool"] = None
    
    def __init__(self):
        self._sessions: Dict[str, MarketSession] = {}
        self._lock = asyncio.Lock()
        self._settings = get_settings()
    
    @classmethod
    async def get_instance(cls) -> "HTTPClientPool":
        """Obtém instância singleton."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    async def get_session(self, market_id: str) -> MarketSession:
        """Obtém ou cria sessão para um mercado."""
        async with self._lock:
            if market_id not in self._sessions:
                rate_limit = self._settings.get_rate_limit(market_id)
                self._sessions[market_id] = MarketSession(
                    market_id=market_id,
                    requests_per_minute=rate_limit,
                )
                self.logger.debug(
                    "Sessão criada",
                    market=market_id,
                    rate_limit=rate_limit,
                )
            return self._sessions[market_id]
    
    async def get(self, url: str, market_id: str, **kwargs) -> httpx.Response:
        """Executa GET usando sessão do mercado."""
        session = await self.get_session(market_id)
        return await session.get(url, **kwargs)
    
    async def post(self, url: str, market_id: str, **kwargs) -> httpx.Response:
        """Executa POST usando sessão do mercado."""
        session = await self.get_session(market_id)
        return await session.post(url, **kwargs)
    
    async def close_all(self):
        """Fecha todas as sessões."""
        async with self._lock:
            for session in self._sessions.values():
                await session.close()
            self._sessions.clear()
            self.logger.info("Todas as sessões fechadas")


# Instância global para acesso rápido
_http_pool: Optional[HTTPClientPool] = None


async def get_http_client() -> HTTPClientPool:
    """Obtém instância do pool de clientes HTTP."""
    global _http_pool
    if _http_pool is None:
        _http_pool = await HTTPClientPool.get_instance()
    return _http_pool


# Alias para compatibilidade
http_client = None


async def init_http_client():
    global http_client
    http_client = await get_http_client()
    return http_client