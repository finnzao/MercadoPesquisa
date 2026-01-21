"""
Core module - HTTP client e Browser pool.
Caminho: /src/core/__init__.py
"""

from src.core.http_client import http_client, get_http_client, HTTPClientPool
from src.core.browser_pool import browser_pool, get_browser_pool, BrowserPool

__all__ = [
    "http_client",
    "get_http_client", 
    "HTTPClientPool",
    "browser_pool",
    "get_browser_pool",
    "BrowserPool",
]
