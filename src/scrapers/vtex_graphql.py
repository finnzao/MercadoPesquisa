"""
Scraper Base VTEX GraphQL usando cliente HTTP resiliente

Usado por: GBarbosa, Sam's Club, Hiperideal, Mercantil, Redemix
"""

import asyncio
import json
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import httpx

from config.logging_config import LoggerMixin
from config.markets import MarketConfig
from src.core.http_client import http_client
from src.core.models import RawProduct
from src.core.types import CollectionStatus
from src.scrapers.base import ScraperResult


VTEX_SEARCH_QUERY = """
query ProductSearch(
    $query: String
    $from: Int
    $to: Int
    $selectedFacets: [SelectedFacetInput]
    $orderBy: String
) {
    productSearch(
        query: $query
        from: $from
        to: $to
        selectedFacets: $selectedFacets
        orderBy: $orderBy
    ) {
        products {
            productId
            productName
            brand
            linkText
            items {
                itemId
                name
                nameComplete
                measurementUnit
                unitMultiplier
                images {
                    imageUrl
                    imageLabel
                }
                sellers {
                    sellerId
                    sellerName
                    commertialOffer {
                        Price
                        ListPrice
                        spotPrice
                        AvailableQuantity
                    }
                }
            }
        }
        recordsFiltered
    }
}
"""


class VTEXGraphQLScraper(LoggerMixin, ABC):
    
    PRODUCTS_PER_PAGE = 20
    
    def __init__(self, config: MarketConfig):
        self.config = config
    
    @property
    def market_id(self) -> str:
        return self.config.id
    
    @property
    @abstractmethod
    def graphql_endpoint(self) -> str:
        pass
    
    def _get_extra_headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
    
    def _build_variables(self, query: str, page: int) -> Dict[str, Any]:
        from_idx = page * self.PRODUCTS_PER_PAGE
        to_idx = from_idx + self.PRODUCTS_PER_PAGE - 1
        
        return {
            "query": query,
            "from": from_idx,
            "to": to_idx,
            "selectedFacets": [{"key": "ft", "value": query}],
            "orderBy": "OrderByScoreDESC",
        }
    
    async def _fetch_products(self, query: str, page: int = 0) -> tuple[List[Dict], int]:
        variables = self._build_variables(query, page)
        
        payload = {
            "query": VTEX_SEARCH_QUERY,
            "variables": variables,
        }
        
        self.logger.debug("Buscando produtos VTEX", query=query, page=page)
        
        try:
            response = await http_client.post(
                self.graphql_endpoint,
                market_id=self.market_id,
                headers=self._get_extra_headers(),
                json=payload,
            )
            
            data = response.json()
            
            if "errors" in data:
                self.logger.error("Erro GraphQL", errors=data["errors"])
                return [], 0
            
            product_search = data.get("data", {}).get("productSearch", {})
            products = product_search.get("products", [])
            total = product_search.get("recordsFiltered", len(products))
            
            self.logger.info("Produtos recebidos VTEX", page=page, count=len(products), total=total)
            return products, total
            
        except httpx.HTTPStatusError as e:
            self.logger.error("Erro HTTP VTEX", status_code=e.response.status_code)
            return [], 0
        except json.JSONDecodeError as e:
            self.logger.error("Erro JSON VTEX", error=str(e))
            return [], 0
        except Exception as e:
            self.logger.error("Erro ao buscar VTEX", error=str(e))
            return [], 0
    
    def _convert_to_raw_product(
        self,
        product_data: Dict,
        search_query: str,
        cep: Optional[str],
        position: int,
    ) -> Optional[RawProduct]:
        try:
            name = product_data.get("productName")
            if not name:
                return None
            
            items = product_data.get("items", [])
            if not items:
                return None
            
            item = items[0]
            sellers = item.get("sellers", [])
            if not sellers:
                return None
            
            seller = sellers[0]
            offer = seller.get("commertialOffer", {})
            
            price = offer.get("Price")
            list_price = offer.get("ListPrice")
            spot_price = offer.get("spotPrice")
            available_qty = offer.get("AvailableQuantity", 0)
            
            price_raw = None
            if price:
                price_raw = f"R$ {float(price):.2f}".replace(".", ",")
            
            unit_price_raw = None
            measurement_unit = item.get("measurementUnit")
            if spot_price and measurement_unit:
                unit_price_raw = f"R$ {float(spot_price):.2f}/{measurement_unit}".replace(".", ",")
            
            link_text = product_data.get("linkText", "")
            product_url = urljoin(self.config.base_url, f"/{link_text}/p")
            
            images = item.get("images", [])
            image_url = images[0].get("imageUrl") if images else None
            
            brand = product_data.get("brand")
            product_id = product_data.get("productId")
            
            availability = "Disponivel" if available_qty > 0 else "Indisponivel"
            
            return RawProduct(
                market_id=self.market_id,
                external_id=str(product_id) if product_id else None,
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
                    "source": "vtex_graphql",
                    "brand": brand,
                    "productId": product_id,
                    "price": price,
                    "listPrice": list_price,
                    "spotPrice": spot_price,
                    "measurementUnit": measurement_unit,
                    "availableQuantity": available_qty,
                },
            )
        except Exception as e:
            self.logger.debug("Erro ao converter produto VTEX", error=str(e))
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
        
        self.logger.info("Iniciando busca VTEX", market=self.market_id, query=query)
        
        try:
            all_products = []
            
            for page_num in range(max_pages):
                products_data, total_count = await self._fetch_products(query, page_num)
                
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
                
                if len(products_data) < self.PRODUCTS_PER_PAGE:
                    break
            
            result.products = all_products
            result.status = CollectionStatus.SUCCESS if all_products else CollectionStatus.NO_RESULTS
            
        except Exception as e:
            result.status = CollectionStatus.FAILED
            result.error_message = str(e)
            self.logger.error("Erro na busca VTEX", error=str(e))
        finally:
            result.mark_finished()
        
        self.logger.info(
            "Busca VTEX finalizada",
            market=self.market_id,
            status=result.status.value,
            products=result.products_count,
        )
        
        return result


class GBarbosaScraper(VTEXGraphQLScraper):
    
    @property
    def graphql_endpoint(self) -> str:
        return "https://www.gbarbosa.com.br/_v/segment/graphql/v1"


class SamsClubScraper(VTEXGraphQLScraper):
    
    @property
    def graphql_endpoint(self) -> str:
        return "https://www.samsclub.com.br/_v/segment/graphql/v1"


class HiperidealScraper(VTEXGraphQLScraper):
    
    @property
    def graphql_endpoint(self) -> str:
        return "https://www.hiperideal.com.br/_v/segment/graphql/v1"


class MercantilScraper(VTEXGraphQLScraper):
    
    @property
    def graphql_endpoint(self) -> str:
        return "https://www.mercantilatacado.com.br/_v/segment/graphql/v1"