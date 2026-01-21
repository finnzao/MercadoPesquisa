"""
Scraper do Carrefour usando cliente HTTP resiliente
src/scrapers/carrefour.py
"""

import asyncio
import json
from datetime import datetime
from typing import Any, Optional
from urllib.parse import quote, urlencode

import httpx

from config.logging_config import LoggerMixin
from config.markets import MarketConfig, MarketStatus, ScrapingMethod, MarketSelectors
from src.core.http_client import http_client
from src.core.models import RawProduct
from src.core.types import CollectionStatus
from src.scrapers.base import ScraperResult


CARREFOUR_SELECTORS = MarketSelectors(
    product_container="",
    product_title="",
    product_price="",
    product_price_cents="",
    product_unit_price="",
    product_image="",
    product_link="",
    product_availability="",
    next_page="",
    total_results="",
    cep_input="",
    cep_submit="",
)

CARREFOUR_CONFIG = MarketConfig(
    id="carrefour",
    display_name="Mercado Carrefour",
    base_url="https://mercado.carrefour.com.br",
    search_url_template="{base_url}/busca/{query}.data",
    status=MarketStatus.ACTIVE,
    method=ScrapingMethod.API,
    selectors=CARREFOUR_SELECTORS,
    requests_per_minute=10,
    requires_cep=False,
    supports_pagination=True,
    max_pages=5,
)


class RemixDataParser:
    
    def __init__(self, data: list):
        self.data = data
        self._products_list_key = None
        self._find_products_key()
    
    def _find_products_key(self):
        for i, item in enumerate(self.data):
            if item == 'products':
                if i + 1 < len(self.data):
                    next_item = self.data[i + 1]
                    if isinstance(next_item, list):
                        self._products_list_key = i + 1
                        return
    
    def get_value(self, index: int) -> Any:
        if index < 0 or index >= len(self.data):
            return None
        return self.data[index]
    
    def extract_dict(self, obj: dict) -> dict:
        result = {}
        for key, value_idx in obj.items():
            if not key.startswith('_'):
                continue
            try:
                key_num = int(key[1:])
                field_name = self.get_value(key_num)
                if not isinstance(field_name, str):
                    continue
                if isinstance(value_idx, int):
                    value = self.get_value(value_idx)
                else:
                    value = value_idx
                result[field_name] = value
            except (ValueError, TypeError):
                pass
        return result
    
    def get_products_indices(self) -> list[int]:
        if self._products_list_key is None:
            return []
        products_list = self.get_value(self._products_list_key)
        if isinstance(products_list, list):
            return products_list
        return []
    
    def parse_product(self, prod_idx: int) -> Optional[dict]:
        prod_dict = self.get_value(prod_idx)
        if not isinstance(prod_dict, dict):
            return None
        
        product = self.extract_dict(prod_dict)
        if not product.get('productName'):
            return None
        
        items_ref = product.get('items')
        if isinstance(items_ref, list) and len(items_ref) > 0:
            item_idx = items_ref[0]
            item_dict = self.get_value(item_idx)
            
            if isinstance(item_dict, dict):
                item_data = self.extract_dict(item_dict)
                product['_item'] = item_data
                
                sellers_ref = item_data.get('sellers')
                if isinstance(sellers_ref, list) and len(sellers_ref) > 0:
                    seller_idx = sellers_ref[0]
                    seller_dict = self.get_value(seller_idx)
                    
                    if isinstance(seller_dict, dict):
                        seller_data = self.extract_dict(seller_dict)
                        product['_seller'] = seller_data
                        
                        offer_ref = seller_data.get('commertialOffer')
                        if isinstance(offer_ref, dict):
                            offer_data = self.extract_dict(offer_ref)
                            product['_offer'] = offer_data
                
                images_ref = item_data.get('images')
                if isinstance(images_ref, list) and len(images_ref) > 0:
                    img_idx = images_ref[0]
                    img_dict = self.get_value(img_idx)
                    
                    if isinstance(img_dict, dict):
                        img_data = self.extract_dict(img_dict)
                        product['_image'] = img_data
        
        return product


class CarrefourScraper(LoggerMixin):
    
    PRODUCTS_PER_PAGE = 20
    
    def __init__(self, config: Optional[MarketConfig] = None):
        self.config = config or CARREFOUR_CONFIG
    
    @property
    def market_id(self) -> str:
        return self.config.id
    
    def _build_url(self, query: str, page: int = 0) -> str:
        encoded_query = quote(query)
        params = {"_routes": "layout/default,routes/busca,routes/busca.$term"}
        if page > 0:
            params["page"] = str(page)
        base_url = f"{self.config.base_url}/busca/{encoded_query}.data"
        return f"{base_url}?{urlencode(params)}"
    
    def _get_extra_headers(self) -> dict:
        return {
            "Accept": "text/x-script, application/json, */*",
            "Referer": "https://mercado.carrefour.com.br/",
            "Origin": "https://mercado.carrefour.com.br",
        }
    
    async def _fetch_products(self, query: str, page: int = 0) -> tuple[list[dict], int]:
        url = self._build_url(query, page)
        
        self.logger.debug("Buscando produtos", query=query, page=page)
        
        try:
            response = await http_client.get(
                url,
                market_id=self.market_id,
                headers=self._get_extra_headers(),
            )
            
            data = response.json()
            
            if not isinstance(data, list):
                self.logger.warning("Resposta nao e lista", type=type(data).__name__)
                return [], 0
            
            parser = RemixDataParser(data)
            products_indices = parser.get_products_indices()
            products = []
            
            for prod_idx in products_indices:
                product = parser.parse_product(prod_idx)
                if product:
                    products.append(product)
            
            total_count = len(products)
            for i, item in enumerate(data):
                if item in ('recordsFiltered', 'totalProducts'):
                    if i + 1 < len(data):
                        total_val = data[i + 1]
                        if isinstance(total_val, int):
                            total_count = total_val
                            break
            
            self.logger.info("Produtos recebidos", page=page, count=len(products), total=total_count)
            return products, total_count
            
        except httpx.HTTPStatusError as e:
            self.logger.error("Erro HTTP", status_code=e.response.status_code)
            return [], 0
        except json.JSONDecodeError as e:
            self.logger.error("Erro JSON", error=str(e))
            return [], 0
        except Exception as e:
            self.logger.error("Erro ao buscar", error=str(e))
            return [], 0
    
    def _convert_to_raw_product(
        self,
        product_data: dict,
        search_query: str,
        cep: Optional[str],
        position: int,
    ) -> Optional[RawProduct]:
        try:
            name = product_data.get('productName')
            if not name:
                return None
            
            offer = product_data.get('_offer', {})
            price = offer.get('Price')
            list_price = offer.get('ListPrice')
            spot_price = offer.get('spotPrice')
            
            price_raw = None
            if price:
                price_raw = f"R$ {float(price):.2f}".replace(".", ",")
            
            unit_price_raw = None
            item_data = product_data.get('_item', {})
            measurement_unit = item_data.get('measurementUnit')
            if spot_price and measurement_unit:
                unit_price_raw = f"R$ {float(spot_price):.2f}/{measurement_unit}".replace(".", ",")
            
            link = product_data.get('link', '')
            product_url = f"{self.config.base_url}{link}" if link else self.config.base_url
            
            image_data = product_data.get('_image', {})
            image_url = image_data.get('imageUrl')
            
            sku = product_data.get('productReference')
            brand = product_data.get('brand')
            
            available_qty = offer.get('AvailableQuantity', 0)
            availability = "Disponivel" if available_qty > 0 else "Indisponivel"
            
            return RawProduct(
                market_id=self.market_id,
                external_id=str(sku) if sku else None,
                title=name.strip(),
                price_raw=price_raw,
                unit_price_raw=unit_price_raw,
                url=product_url,
                image_url=image_url,
                availability_raw=availability,
                search_query=search_query,
                cep=cep,
                collected_at=datetime.now(),
                extra_data={
                    "position": position,
                    "source": "api",
                    "brand": brand,
                    "sku": sku,
                    "productId": product_data.get('productId'),
                    "price": price,
                    "listPrice": list_price,
                    "spotPrice": spot_price,
                    "measurementUnit": measurement_unit,
                    "availableQuantity": available_qty,
                },
            )
        except Exception as e:
            self.logger.debug("Erro ao converter produto", error=str(e))
            return None
    
    async def search(
        self,
        query: str,
        cep: Optional[str] = None,
        max_pages: int = 1,
    ) -> ScraperResult:
        result = ScraperResult(
            market_id=self.market_id,
            search_query=query,
            status=CollectionStatus.FAILED,
        )
        
        self.logger.info("Iniciando busca", market=self.market_id, query=query, max_pages=max_pages)
        
        try:
            all_products = []
            
            for page_num in range(max_pages):
                products_data, total_count = await self._fetch_products(query=query, page=page_num)
                
                if not products_data:
                    if page_num == 0:
                        result.status = CollectionStatus.NO_RESULTS
                    break
                
                for idx, product_data in enumerate(products_data):
                    position = page_num * self.PRODUCTS_PER_PAGE + idx + 1
                    product = self._convert_to_raw_product(
                        product_data=product_data,
                        search_query=query,
                        cep=cep,
                        position=position,
                    )
                    if product:
                        all_products.append(product)
                
                result.pages_scraped += 1
                
                self.logger.info(
                    "Pagina processada",
                    page=page_num + 1,
                    products_page=len(products_data),
                    products_total=len(all_products),
                )
                
                if len(products_data) < self.PRODUCTS_PER_PAGE:
                    break
            
            result.products = all_products
            result.status = CollectionStatus.SUCCESS if all_products else CollectionStatus.NO_RESULTS
            
        except Exception as e:
            result.status = CollectionStatus.FAILED
            result.error_message = str(e)
            self.logger.error("Erro na busca", error=str(e))
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
    
    async def set_location(self, page, cep: str) -> bool:
        return True
    
    async def extract_products(
        self,
        page,
        search_query: str,
        cep: Optional[str] = None,
    ) -> list[RawProduct]:
        result = await self.search(search_query, cep=cep, max_pages=1)
        return result.products


async def search_carrefour(
    query: str,
    cep: Optional[str] = None,
    max_pages: int = 1,
) -> ScraperResult:
    scraper = CarrefourScraper()
    return await scraper.search(query, cep=cep, max_pages=max_pages)