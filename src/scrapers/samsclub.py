"""
Sam's Club Scraper - API GraphQL HTTP Pura (sem Playwright)
https://www.samsclub.com.br

API utilizada:
- GET https://www.samsclub.com.br/_v/segment/graphql/v1?operationName=productSearchV3&...

Este scraper usa requisições HTTP diretas ao endpoint GraphQL VTEX,
seguindo o padrão do Carrefour, Atacadão e GBarbosa.

A VTEX usa "persisted queries" onde as variáveis são codificadas em Base64
dentro do campo extensions.variables.
"""

import base64
import json
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

from config.markets import MarketConfig, MarketStatus, ScrapingMethod, MarketSelectors
from src.core.models import RawProduct
from src.scrapers.base_api import BaseAPIScraper


# Configuração do Sam's Club
SAMSCLUB_SELECTORS = MarketSelectors(
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

SAMSCLUB_CONFIG = MarketConfig(
    id="samsclub",
    display_name="Sam's Club",
    base_url="https://www.samsclub.com.br",
    search_url_template="{base_url}/{query}?_q={query}&map=ft",
    status=MarketStatus.ACTIVE,
    method=ScrapingMethod.API,
    selectors=SAMSCLUB_SELECTORS,
    requests_per_minute=10,
    requires_cep=False,
    supports_pagination=True,
    max_pages=5,
)


class SamsClubScraper(BaseAPIScraper):
    """
    Scraper para Sam's Club via API GraphQL VTEX.
    
    Usa requisições HTTP diretas - sem necessidade de browser.
    
    API Endpoint:
        GET https://www.samsclub.com.br/_v/segment/graphql/v1
        
    A VTEX usa persisted queries com variáveis em Base64.
    
    Diferenças do Sam's Club:
    - skusFilter: "ALL" (mostra todos os SKUs)
    - 24 produtos por página
    """
    
    PRODUCTS_PER_PAGE = 24
    BASE_URL = "https://www.samsclub.com.br"
    GRAPHQL_ENDPOINT = "/_v/segment/graphql/v1"
    
    # Hash da query persistida (comum para lojas VTEX)
    SHA256_HASH = "31d3fa494df1fc41efef6d16dd96a96e6911b8aed7a037868699a1f3f4d365de"
    SENDER = "vtex.store-resources@0.x"
    PROVIDER = "vtex.search-graphql@0.x"
    
    def __init__(self, config=None):
        """
        Inicializa o scraper.
        
        Args:
            config: Configuração do mercado (opcional)
        """
        config = config or SAMSCLUB_CONFIG
        super().__init__(config)
    
    def _build_graphql_variables(self, query: str, from_idx: int, to_idx: int) -> dict:
        """
        Constrói as variáveis para a query GraphQL.
        
        Args:
            query: Termo de busca
            from_idx: Índice inicial
            to_idx: Índice final
            
        Returns:
            Dict com variáveis da query
        """
        query_clean = query.strip()
        
        return {
            "hideUnavailableItems": True,
            "skusFilter": "ALL",  # Sam's Club usa ALL
            "simulationBehavior": "default",
            "installmentCriteria": "MAX_WITHOUT_INTEREST",
            "productOriginVtex": False,
            "map": "ft",
            "query": query_clean,
            "orderBy": "OrderByScoreDESC",
            "from": from_idx,
            "to": to_idx,
            "selectedFacets": [
                {"key": "ft", "value": query_clean}
            ],
            "fullText": query_clean,
            "facetsBehavior": "Static",
            "categoryTreeBehavior": "default",
            "withFacets": False,
        }
    
    def _build_request(self, query: str, page: int) -> Dict[str, Any]:
        """
        Constrói configuração da requisição para a API GraphQL.
        
        Args:
            query: Termo de busca
            page: Número da página (0-indexed)
            
        Returns:
            Dict com configuração da requisição
        """
        from_idx = page * self.PRODUCTS_PER_PAGE
        to_idx = from_idx + self.PRODUCTS_PER_PAGE - 1
        
        # Constrói variáveis e codifica em Base64
        variables = self._build_graphql_variables(query, from_idx, to_idx)
        variables_json = json.dumps(variables, separators=(",", ":"))
        variables_b64 = base64.b64encode(variables_json.encode()).decode()
        
        # Constrói extensions com persisted query
        extensions = {
            "persistedQuery": {
                "version": 1,
                "sha256Hash": self.SHA256_HASH,
                "sender": self.SENDER,
                "provider": self.PROVIDER,
            },
            "variables": variables_b64,
        }
        
        # Parâmetros da query string
        params = {
            "workspace": "master",
            "maxAge": "short",
            "appsEtag": "remove",
            "domain": "store",
            "locale": "pt-BR",
            "operationName": "productSearchV3",
            "variables": "{}",
            "extensions": json.dumps(extensions, separators=(",", ":")),
        }
        
        url = f"{self.BASE_URL}{self.GRAPHQL_ENDPOINT}?{urlencode(params)}"
        
        return {
            "url": url,
            "method": "GET",
            "headers": {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Origin": self.BASE_URL,
                "Referer": f"{self.BASE_URL}/",
            },
        }
    
    def _parse_response(
        self, 
        data: Any, 
        query: str, 
        cep: Optional[str], 
        page: int
    ) -> tuple[List[RawProduct], int]:
        """
        Parseia resposta da API GraphQL.
        
        Args:
            data: Dados JSON da resposta
            query: Termo de busca
            cep: CEP utilizado
            page: Número da página
            
        Returns:
            Tupla (lista de produtos, total disponível)
        """
        try:
            product_search = data.get("data", {}).get("productSearch", {})
            items = product_search.get("products", [])
            total = product_search.get("recordsFiltered", len(items))
        except (TypeError, AttributeError):
            self.logger.debug("Estrutura de resposta inválida")
            return [], 0
        
        products = []
        for idx, item in enumerate(items):
            product = self._convert_product(
                item, 
                query, 
                cep, 
                page * self.PRODUCTS_PER_PAGE + idx + 1
            )
            if product:
                products.append(product)
        
        return products, total
    
    def _convert_product(
        self, 
        item: dict, 
        query: str, 
        cep: Optional[str], 
        position: int
    ) -> Optional[RawProduct]:
        """
        Converte item da API GraphQL para RawProduct.
        
        Estrutura VTEX:
        - productName: nome do produto
        - priceRange.sellingPrice.lowPrice: preço de venda
        - priceRange.listPrice.lowPrice: preço original
        - items[0].sellers[0].commertialOffer.Price: preço do seller
        - items[0].images[0].imageUrl: URL da imagem
        - link: URL do produto
        - brand: marca
        """
        title = item.get("productName")
        if not title:
            return None
        
        # Extrai preço do primeiro SKU/Seller disponível
        price = None
        availability = "Indisponível"
        
        skus = item.get("items", [])
        for sku in skus:
            sellers = sku.get("sellers", [])
            for seller in sellers:
                offer = seller.get("commertialOffer", {})
                qty = offer.get("AvailableQuantity", 0)
                
                if qty > 0:
                    price = offer.get("Price")
                    availability = "Disponível"
                    break
            
            if price is not None:
                break
        
        # Fallback: priceRange
        if price is None:
            price_range = item.get("priceRange", {})
            selling_price = price_range.get("sellingPrice", {})
            price = selling_price.get("lowPrice")
        
        if price is None:
            return None
        
        try:
            price_float = float(price)
        except (ValueError, TypeError):
            return None
        
        # URL do produto
        link = item.get("link", "")
        if link:
            product_url = f"{self.BASE_URL}{link}" if not link.startswith("http") else link
        else:
            product_url = self.BASE_URL
        
        # Imagem
        image_url = None
        if skus:
            images = skus[0].get("images", [])
            if images:
                image_url = images[0].get("imageUrl")
        
        # Preço original (listPrice) e desconto
        list_price = None
        discount = None
        price_range = item.get("priceRange", {})
        list_price_range = price_range.get("listPrice", {})
        list_price = list_price_range.get("lowPrice")
        
        if list_price and price and list_price > price:
            discount = round(list_price - price, 2)
        
        return self._create_product(
            title=title,
            price=price_float,
            url=product_url,
            query=query,
            cep=cep,
            position=position,
            image_url=image_url,
            external_id=str(item.get("productId")) if item.get("productId") else None,
            unit_price_raw=None,
            extra_data={
                "brand": item.get("brand"),
                "product_reference": item.get("productReference"),
                "category_id": item.get("categoryId"),
                "list_price": list_price,
                "discount": discount,
                "availability": availability,
            },
        )


async def search_samsclub(query: str, cep: Optional[str] = None, max_pages: int = 1):
    """Função de conveniência para busca rápida."""
    scraper = SamsClubScraper()
    return await scraper.search(query, cep, max_pages)
