"""VTEX Optimized Base Scraper - REST APIs com fallback"""

import asyncio
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, urlencode

import httpx

from config.markets import MarketConfig
from src.core.models import RawProduct
from src.scrapers.base_api import BaseAPIScraper


class VTEXOptimizedScraper(BaseAPIScraper):
    """Classe base otimizada para scrapers VTEX com REST APIs."""
    
    PRODUCTS_PER_PAGE = 50
    MAX_TOTAL_RESULTS = 2500
    MAX_CONCURRENT_REQUESTS = 3
    CONNECT_TIMEOUT = 10
    READ_TIMEOUT = 30
    MAX_RETRIES = 3
    RETRY_BACKOFF_BASE = 1.5
    
    INTELLIGENT_SEARCH_PATH = "/api/io/_v/api/intelligent-search/product_search"
    LEGACY_SEARCH_PATH = "/api/catalog_system/pub/products/search"
    
    def __init__(self, config: MarketConfig):
        super().__init__(config)
        self._http_client: Optional[httpx.AsyncClient] = None
        self._preferred_api = "intelligent"
    
    @property
    def base_url(self) -> str:
        return self.config.base_url
    
    def _get_optimized_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "pt-BR,pt;q=0.9",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Origin": self.base_url,
            "Referer": f"{self.base_url}/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }
        headers.update(self._get_additional_headers())
        return headers
    
    def _get_additional_headers(self) -> Dict[str, str]:
        return {}
    
    async def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(connect=self.CONNECT_TIMEOUT, read=self.READ_TIMEOUT, write=self.READ_TIMEOUT, pool=self.READ_TIMEOUT),
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
                http2=True,
            )
        return self._http_client
    
    async def _close_http_client(self):
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None
    
    async def _request_with_retry(self, method: str, url: str, headers: Dict[str, str], json_data: Optional[dict] = None, params: Optional[dict] = None) -> httpx.Response:
        client = await self._get_http_client()
        last_error = None
        
        for attempt in range(self.MAX_RETRIES):
            try:
                response = await client.request(method=method, url=url, headers=headers, json=json_data, params=params)
                if response.status_code == 429:
                    await asyncio.sleep(int(response.headers.get("Retry-After", 5)))
                    continue
                if response.status_code in (503, 504):
                    await asyncio.sleep(self.RETRY_BACKOFF_BASE ** attempt)
                    continue
                response.raise_for_status()
                return response
            except httpx.TimeoutException as e:
                last_error = e
                await asyncio.sleep(self.RETRY_BACKOFF_BASE ** attempt)
            except httpx.HTTPStatusError as e:
                if 400 <= e.response.status_code < 500:
                    raise
                last_error = e
                await asyncio.sleep(self.RETRY_BACKOFF_BASE ** attempt)
        raise last_error or Exception("Max retries exceeded")
    
    def _build_intelligent_search_url(self, query: str, page: int, count: int = None) -> str:
        count = count or self.PRODUCTS_PER_PAGE
        facets = f"ft={quote(query)}"
        params = {"query": query, "page": page + 1, "count": count, "sort": "score:desc", "locale": "pt-BR", "hideUnavailableItems": "false"}
        return f"{self.base_url}{self.INTELLIGENT_SEARCH_PATH}/{facets}?{urlencode(params)}"
    
    def _parse_intelligent_search_response(self, data: dict) -> Tuple[List[dict], int]:
        products = data.get("products", [])
        return products, data.get("recordsFiltered", len(products))
    
    def _build_legacy_search_url(self, query: str, page: int, count: int = None) -> str:
        count = count or self.PRODUCTS_PER_PAGE
        from_idx = page * count
        to_idx = min(from_idx + count - 1, self.MAX_TOTAL_RESULTS - 1)
        return f"{self.base_url}{self.LEGACY_SEARCH_PATH}?{urlencode({'ft': query, '_from': from_idx, '_to': to_idx})}"
    
    def _parse_legacy_search_response(self, data: Any, total_from_header: int = 0) -> Tuple[List[dict], int]:
        if not isinstance(data, list):
            return [], 0
        return data, total_from_header or len(data)
    
    def _convert_vtex_product(self, item: dict, query: str, cep: Optional[str], position: int) -> Optional[RawProduct]:
        title = item.get("productName") or item.get("productTitle")
        if not title:
            return None
        
        price, list_price, availability, sku_id, ean, image_url = None, None, "Indisponível", None, None, None
        
        for sku in item.get("items", []):
            if not image_url:
                images = sku.get("images", [])
                if images:
                    image_url = images[0].get("imageUrl")
            
            for seller in sku.get("sellers", []):
                offer = seller.get("commertialOffer", {})
                qty = offer.get("AvailableQuantity", 0)
                offer_price = offer.get("Price")
                
                if offer_price and offer_price > 0:
                    if price is None or qty > 0:
                        price, list_price = offer_price, offer.get("ListPrice")
                        sku_id, ean = sku.get("itemId"), sku.get("ean")
                        if qty > 0:
                            availability = "Disponível"
                            break
            if availability == "Disponível":
                break
        
        if price is None:
            price_range = item.get("priceRange", {})
            selling = price_range.get("sellingPrice", {})
            price = selling.get("lowPrice") or selling.get("highPrice")
            listing = price_range.get("listPrice", {})
            list_price = listing.get("lowPrice") or listing.get("highPrice")
        
        if not price:
            return None
        
        try:
            price_float = float(price)
        except (ValueError, TypeError):
            return None
        
        link = item.get("link", "")
        product_url = f"{self.base_url}{link}" if link and not link.startswith("http") else link or self.base_url
        discount = round(list_price - price, 2) if list_price and list_price > price else None
        
        return self._create_product(
            title=title, price=price_float, url=product_url, query=query, cep=cep, position=position,
            image_url=image_url, external_id=str(item.get("productId")) or sku_id,
            extra_data={"brand": item.get("brand"), "brand_id": item.get("brandId"), "category_id": item.get("categoryId"),
                       "sku_id": sku_id, "ean": ean, "list_price": list_price, "discount": discount, "availability": availability},
        )
    
    def _build_request(self, query: str, page: int) -> Dict[str, Any]:
        url = self._build_intelligent_search_url(query, page) if self._preferred_api == "intelligent" else self._build_legacy_search_url(query, page)
        return {"url": url, "method": "GET", "headers": self._get_optimized_headers()}
    
    def _parse_response(self, data: Any, query: str, cep: Optional[str], page: int) -> Tuple[List[RawProduct], int]:
        if self._preferred_api == "intelligent":
            raw_products, total = self._parse_intelligent_search_response(data)
        else:
            raw_products, total = self._parse_legacy_search_response(data)
        
        products = [p for idx, item in enumerate(raw_products) if (p := self._convert_vtex_product(item, query, cep, page * self.PRODUCTS_PER_PAGE + idx + 1))]
        return products, total
    
    async def search(self, query: str, cep: Optional[str] = None, max_pages: int = 1):
        self._preferred_api = "intelligent"
        try:
            result = await super().search(query, cep, max_pages=1)
            if result.products_count == 0:
                self._preferred_api = "legacy"
                result = await super().search(query, cep, max_pages)
            return result
        except Exception:
            self._preferred_api = "legacy"
            return await super().search(query, cep, max_pages)
        finally:
            await self._close_http_client()