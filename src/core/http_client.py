"""
Cliente HTTP Resiliente - Modulo Central
src/core/http_client.py
"""

import asyncio
import random
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import httpx

from config.logging_config import get_logger

logger = get_logger(__name__)


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
]

RETRYABLE_EXCEPTIONS = (
    httpx.ReadError,
    httpx.ConnectError,
    httpx.TimeoutException,
    httpx.RemoteProtocolError,
    ConnectionResetError,
    ConnectionError,
    asyncio.TimeoutError,
)

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504, 520, 521, 522, 523, 524}


@dataclass
class DomainConfig:
    requests_per_second: float = 5.0
    burst_size: int = 10
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    connect_timeout: float = 10.0
    read_timeout: float = 30.0
    min_request_interval: float = 0.5
    max_request_interval: float = 1.5
    failure_threshold: int = 5
    recovery_timeout: float = 60.0


MARKET_CONFIGS: Dict[str, DomainConfig] = {
    "carrefour": DomainConfig(
        requests_per_second=3.0,
        base_delay=1.5,
        min_request_interval=0.8,
        max_request_interval=2.0,
    ),
    "atacadao": DomainConfig(
        requests_per_second=5.0,
        base_delay=1.0,
    ),
    "gbarbosa": DomainConfig(
        requests_per_second=8.0,
        base_delay=0.8,
    ),
    "pao_acucar": DomainConfig(
        requests_per_second=4.0,
        base_delay=1.2,
    ),
    "samsclub": DomainConfig(
        requests_per_second=8.0,
        base_delay=0.8,
    ),
    "redemix": DomainConfig(
        requests_per_second=8.0,
        base_delay=0.8,
    ),
    "mercantil": DomainConfig(
        requests_per_second=8.0,
        base_delay=0.8,
    ),
    "hiperideal": DomainConfig(
        requests_per_second=8.0,
        base_delay=0.8,
    ),
}

DEFAULT_CONFIG = DomainConfig()


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_time: Optional[datetime] = None
    half_open_successes: int = 0
    
    def record_success(self):
        if self.state == CircuitState.HALF_OPEN:
            self.half_open_successes += 1
            if self.half_open_successes >= 2:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.half_open_successes = 0
        else:
            self.failure_count = max(0, self.failure_count - 1)
    
    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            self.half_open_successes = 0
        elif self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
    
    def can_execute(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        
        if self.state == CircuitState.OPEN:
            if self.last_failure_time:
                elapsed = (datetime.now() - self.last_failure_time).total_seconds()
                if elapsed >= self.recovery_timeout:
                    self.state = CircuitState.HALF_OPEN
                    self.half_open_successes = 0
                    return True
            return False
        
        return True


@dataclass
class TokenBucket:
    capacity: float
    refill_rate: float
    tokens: float = field(init=False)
    last_refill: float = field(init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    
    def __post_init__(self):
        self.tokens = self.capacity
        self.last_refill = time.monotonic()
    
    async def acquire(self, tokens: float = 1.0) -> float:
        async with self._lock:
            self._refill()
            
            if self.tokens >= tokens:
                self.tokens -= tokens
                return 0.0
            
            needed = tokens - self.tokens
            wait_time = needed / self.refill_rate
            
            await asyncio.sleep(wait_time)
            self._refill()
            self.tokens -= tokens
            return wait_time
    
    def _refill(self):
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now
    
    def adjust_rate(self, factor: float):
        self.refill_rate = max(0.5, min(self.refill_rate * factor, 20.0))


class ResilientHTTPClient:
    
    def __init__(self):
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._rate_limiters: Dict[str, TokenBucket] = {}
        self._last_request_time: Dict[str, float] = {}
        self._lock = asyncio.Lock()
    
    def _get_config(self, market_id: Optional[str]) -> DomainConfig:
        if market_id and market_id in MARKET_CONFIGS:
            return MARKET_CONFIGS[market_id]
        return DEFAULT_CONFIG
    
    def _get_domain(self, url: str) -> str:
        return urlparse(url).netloc
    
    async def _get_circuit_breaker(self, domain: str, config: DomainConfig) -> CircuitBreaker:
        async with self._lock:
            if domain not in self._circuit_breakers:
                self._circuit_breakers[domain] = CircuitBreaker(
                    failure_threshold=config.failure_threshold,
                    recovery_timeout=config.recovery_timeout,
                )
            return self._circuit_breakers[domain]
    
    async def _get_rate_limiter(self, domain: str, config: DomainConfig) -> TokenBucket:
        async with self._lock:
            if domain not in self._rate_limiters:
                self._rate_limiters[domain] = TokenBucket(
                    capacity=config.burst_size,
                    refill_rate=config.requests_per_second,
                )
            return self._rate_limiters[domain]
    
    def _get_headers(self, extra_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = {
            "Accept": "application/json, text/html, */*",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "User-Agent": random.choice(USER_AGENTS),
            "Connection": "keep-alive",
            "Cache-Control": "no-cache",
        }
        if extra_headers:
            headers.update(extra_headers)
        return headers
    
    def _calculate_backoff(self, attempt: int, base_delay: float, max_delay: float) -> float:
        delay = base_delay * (2 ** attempt)
        jitter = random.uniform(0, base_delay)
        return min(delay + jitter, max_delay)
    
    async def _apply_request_interval(self, domain: str, config: DomainConfig):
        now = time.monotonic()
        last_time = self._last_request_time.get(domain, 0)
        elapsed = now - last_time
        
        min_interval = config.min_request_interval
        max_interval = config.max_request_interval
        required_interval = random.uniform(min_interval, max_interval)
        
        if elapsed < required_interval:
            await asyncio.sleep(required_interval - elapsed)
        
        self._last_request_time[domain] = time.monotonic()
    
    async def request(
        self,
        method: str,
        url: str,
        market_id: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        **kwargs,
    ) -> httpx.Response:
        config = self._get_config(market_id)
        domain = self._get_domain(url)
        
        circuit_breaker = await self._get_circuit_breaker(domain, config)
        rate_limiter = await self._get_rate_limiter(domain, config)
        
        if not circuit_breaker.can_execute():
            raise httpx.ConnectError(f"Circuit breaker OPEN for {domain}")
        
        last_exception = None
        
        for attempt in range(config.max_retries):
            try:
                if attempt > 0:
                    delay = self._calculate_backoff(attempt, config.base_delay, config.max_delay)
                    logger.info(f"Retry {attempt + 1}/{config.max_retries} apos {delay:.2f}s", domain=domain)
                    await asyncio.sleep(delay)
                
                await rate_limiter.acquire()
                await self._apply_request_interval(domain, config)
                
                async with httpx.AsyncClient(
                    headers=self._get_headers(headers),
                    timeout=httpx.Timeout(
                        connect=config.connect_timeout,
                        read=config.read_timeout,
                        write=10.0,
                        pool=10.0,
                    ),
                    follow_redirects=True,
                ) as client:
                    response = await client.request(method, url, **kwargs)
                    
                    if response.status_code in RETRYABLE_STATUS_CODES:
                        circuit_breaker.record_failure()
                        
                        if response.status_code == 429:
                            rate_limiter.adjust_rate(0.5)
                            retry_after = response.headers.get("Retry-After")
                            if retry_after:
                                await asyncio.sleep(min(float(retry_after), config.max_delay))
                        
                        if attempt < config.max_retries - 1:
                            continue
                    
                    response.raise_for_status()
                    circuit_breaker.record_success()
                    rate_limiter.adjust_rate(1.05)
                    return response
                    
            except RETRYABLE_EXCEPTIONS as e:
                last_exception = e
                circuit_breaker.record_failure()
                logger.warning(
                    f"Erro retryable (tentativa {attempt + 1}/{config.max_retries})",
                    error_type=type(e).__name__,
                    domain=domain,
                )
                continue
                
            except httpx.HTTPStatusError as e:
                if e.response.status_code not in RETRYABLE_STATUS_CODES:
                    raise
                last_exception = e
                circuit_breaker.record_failure()
                continue
        
        logger.error(f"Todas as {config.max_retries} tentativas falharam", domain=domain)
        if last_exception:
            raise last_exception
        raise httpx.RequestError(f"Max retries exceeded for {url}")
    
    async def get(self, url: str, **kwargs) -> httpx.Response:
        return await self.request("GET", url, **kwargs)
    
    async def post(self, url: str, **kwargs) -> httpx.Response:
        return await self.request("POST", url, **kwargs)
    
    def get_circuit_breaker_status(self, domain: str) -> Optional[Dict[str, Any]]:
        cb = self._circuit_breakers.get(domain)
        if cb:
            return {
                "state": cb.state.value,
                "failure_count": cb.failure_count,
                "last_failure": cb.last_failure_time.isoformat() if cb.last_failure_time else None,
            }
        return None
    
    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        return {
            domain: {
                "circuit_breaker": self.get_circuit_breaker_status(domain),
                "rate_limiter": {
                    "tokens": self._rate_limiters[domain].tokens if domain in self._rate_limiters else None,
                    "rate": self._rate_limiters[domain].refill_rate if domain in self._rate_limiters else None,
                },
            }
            for domain in set(list(self._circuit_breakers.keys()) + list(self._rate_limiters.keys()))
        }
    
    def reset_circuit_breaker(self, domain: str):
        if domain in self._circuit_breakers:
            cb = self._circuit_breakers[domain]
            cb.state = CircuitState.CLOSED
            cb.failure_count = 0
            cb.half_open_successes = 0
            logger.info(f"Circuit breaker resetado", domain=domain)


http_client = ResilientHTTPClient()


async def get(url: str, **kwargs) -> httpx.Response:
    return await http_client.get(url, **kwargs)


async def post(url: str, **kwargs) -> httpx.Response:
    return await http_client.post(url, **kwargs)