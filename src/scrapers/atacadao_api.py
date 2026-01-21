"""
Atacadão Scraper - API GraphQL VTEX.
Caminho: /src/scrapers/atacadao_api.py
"""

import base64
import json
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

from config.markets import MARKETS_CONFIG
from src.core.models import RawProduct
from src.scrapers.base_api import BaseAPIScraper


# Mapeamento CEP -> seller
CEP_TO_SELLER = {
    "01": "atacadaobr60", "02": "atacadaobr60", "03": "atacadaobr60",
    "04": "atacadaobr60", "05": "atacadaobr60", "06": "atacadaobr60",
    "07": "atacadaobr60", "08": "atacadaobr60", "09": "atacadaobr60",
    "40": "atacadaobr1", "41": "atacadaobr1", "42": "atacadaobr1",
    "20": "atacadaobr30", "21": "atacadaobr30", "22": "atacadaobr30",
    "default": "atacadaobr60",
}


def get_seller(cep: Optional[str]) -> str:
    if cep and len(cep) >= 2:
        return CEP_TO_SELLER.get(cep[:2], CEP_TO_SELLER["default"])
    return CEP_TO_SELLER["default"]


def make_region_id(seller: str) -> str:
    return base64.b64encode(f"SW#{seller}".encode()).decode()


class AtacadaoScraper(BaseAPIScraper):
    """
    Scraper Atacadão via API GraphQL.
    Sessão estável, sem rotação de UA.
    """
    
    PRODUCTS_PER_PAGE = 20
    BASE_URL = "https://www.atacadao.com.br"
    API_ENDPOINT = "/api/graphql"
    
    def __init__(self, config=None):
        super().__init__(config or MARKETS_CONFIG.get("atacadao"))
        self._cep: Optional[str] = None
    
    async def search(self, query: str, cep: Optional[str] = None, max_pages: int = 1):
        self._cep = cep
        return await super().search(query, cep, max_pages)
    
    def _build_request(self, query: str, page: int) -> Dict[str, Any]:
        seller = get_seller(self._cep)
        region_id = make_region_id(seller)
        
        channel = json.dumps({
            "salesChannel": "1",
            "seller": seller,
            "regionId": region_id,
        }, separators=(',', ':'))
        
        variables = {
            "first": self.PRODUCTS_PER_PAGE,
            "after": str(page * self.PRODUCTS_PER_PAGE),
            "sort": "score_desc",
            "term": query,
            "selectedFacets": [
                {"key": "region-id", "value": region_id},
                {"key": "channel", "value": channel},
                {"key": "locale", "value": "pt-BR"},
            ],
        }
        
        params = {
            "operationName": "ProductsQuery",
            "variables": json.dumps(variables, separators=(',', ':')),
        }
        
        return {
            "url": f"{self.BASE_URL}{self.API_ENDPOINT}",
            "method": "GET",
            "params": params,
        }
    
    def _parse_response(self, data: Any, query: str, cep: Optional[str], page: int) -> tuple[List[RawProduct], int]:
        try:
            search_data = data.get("data", {}).get("search", {})
            products_data = search_data.get("products", {})
            edges = products_data.get("edges", [])
            total = products_data.get("pageInfo", {}).get("totalCount", 0)
        except (TypeError, AttributeError):
            return [], 0
        
        products = []
        for idx, edge in enumerate(edges):
            node = edge.get("node", {})
            product = self._convert_product(node, query, cep, page * self.PRODUCTS_PER_PAGE + idx + 1)
            if product:
                products.append(product)
        
        return products, total
    
    def _convert_product(self, node: dict, query: str, cep: Optional[str], position: int) -> Optional[RawProduct]:
        name = node.get("name")
        if not name:
            return None
        
        offers = node.get("offers", {})
        offers_list = offers.get("offers", [])
        
        # Preço unitário e atacado
        price = None
        bulk_price = None
        bulk_min = None
        
        for offer in offers_list:
            p = offer.get("price")
            min_qty = offer.get("minQuantity", 1)
            if min_qty == 1:
                price = p
            elif min_qty > 1 and bulk_price is None:
                bulk_price = p
                bulk_min = min_qty
        
        if price is None:
            price = offers.get("lowPrice") or offers.get("highPrice")
        
        if price is None:
            return None
        
        try:
            price_float = float(price)
        except (ValueError, TypeError):
            return None
        
        # URL
        slug = node.get("slug", "")
        url = f"{self.BASE_URL}/{slug}/p" if slug else self.BASE_URL
        
        # Imagem
        images = node.get("image", [])
        image_url = images[0].get("url") if images else None
        
        # Preço atacado
        unit_price = None
        if bulk_price and bulk_min:
            unit_price = f"R$ {float(bulk_price):.2f} (min {bulk_min} un.)".replace(".", ",")
        
        return self._create_product(
            title=name,
            price=price_float,
            url=url,
            query=query,
            cep=cep,
            position=position,
            image_url=image_url,
            external_id=str(node.get("id")) if node.get("id") else None,
            unit_price_raw=unit_price,
            extra_data={
                "brand": node.get("brand", {}).get("brandName"),
                "sku": node.get("sku"),
                "bulk_price": bulk_price,
                "bulk_min": bulk_min,
            },
        )


async def search_atacadao(query: str, cep: Optional[str] = None, max_pages: int = 1):
    """Função de conveniência."""
    scraper = AtacadaoScraper()
    return await scraper.search(query, cep, max_pages)
