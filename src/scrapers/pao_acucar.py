"""
Pão de Açúcar Scraper - API HTTP Pura (sem Playwright)
https://www.paodeacucar.com

API utilizada:
- POST https://api.vendas.gpa.digital/pa/search/search

Este scraper usa requisições HTTP diretas ao invés de Playwright,
seguindo o padrão do Carrefour e Atacadão.
"""

import json
from typing import Any, Dict, List, Optional

from config.markets import MARKETS_CONFIG, PAO_ACUCAR_CONFIG
from src.core.models import RawProduct
from src.scrapers.base_api import BaseAPIScraper


class PaoDeAcucarScraper(BaseAPIScraper):
    """
    Scraper para Pão de Açúcar via API REST.
    
    Usa requisições HTTP diretas - sem necessidade de browser.
    
    API Endpoint:
        POST https://api.vendas.gpa.digital/pa/search/search
        
    Payload:
        {
            "terms": "arroz",
            "page": 1,
            "sortBy": "relevance",
            "resultsPerPage": 16,
            "storeId": 461,
            ...
        }
    """
    
    PRODUCTS_PER_PAGE = 16
    API_URL = "https://api.vendas.gpa.digital/pa/search/search"
    DEFAULT_STORE_ID = 461  # Store ID padrão (São Paulo)
    
    def __init__(self, config=None):
        """
        Inicializa o scraper.
        
        Args:
            config: Configuração do mercado (opcional, usa padrão se não fornecido)
        """
        config = config or PAO_ACUCAR_CONFIG
        super().__init__(config)
        self._store_id = self.DEFAULT_STORE_ID
        self._cep: Optional[str] = None
    
    async def search(self, query: str, cep: Optional[str] = None, max_pages: int = 1):
        """
        Executa busca salvando CEP para uso interno.
        """
        self._cep = cep
        
        # Se CEP fornecido, tenta obter store_id correspondente
        if cep:
            await self._resolve_store_id(cep)
        
        return await super().search(query, cep, max_pages)
    
    async def _resolve_store_id(self, cep: str) -> None:
        """
        Obtém store_id baseado no CEP via API.
        """
        from src.core.http_client import get_http_client
        
        try:
            cep_clean = cep.replace("-", "").replace(".", "")
            url = f"https://api.vendas.gpa.digital/pa/delivery/stores?zipCode={cep_clean}"
            
            http = await get_http_client()
            response = await http.get(url, market_id=self.market_id)
            
            data = response.json()
            stores = data.get("stores", [])
            
            if stores:
                store_id = stores[0].get("id")
                if store_id:
                    self._store_id = int(store_id)
                    self.logger.info(
                        "Store ID obtido pelo CEP",
                        store_id=self._store_id,
                        cep=cep,
                    )
        except Exception as e:
            self.logger.debug(f"Erro ao obter store_id pelo CEP: {e}")
    
    def _build_request(self, query: str, page: int) -> Dict[str, Any]:
        """
        Constrói configuração da requisição para a API.
        
        Args:
            query: Termo de busca
            page: Número da página (0-indexed)
            
        Returns:
            Dict com configuração da requisição
        """
        payload = {
            "terms": query,
            "page": page + 1,  # API usa 1-indexed
            "sortBy": "relevance",
            "resultsPerPage": self.PRODUCTS_PER_PAGE,
            "allowRedirect": True,
            "storeId": self._store_id,
            "department": "ecom",
            "customerPlus": True,
            "partner": "linx",
        }
        
        return {
            "url": self.API_URL,
            "method": "POST",
            "json": payload,
            "headers": {
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json",
                "Origin": "https://www.paodeacucar.com",
                "Referer": "https://www.paodeacucar.com/",
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
        Parseia resposta da API.
        
        Args:
            data: Dados JSON da resposta
            query: Termo de busca
            cep: CEP utilizado
            page: Número da página
            
        Returns:
            Tupla (lista de produtos, total disponível)
        """
        if not isinstance(data, dict):
            return [], 0
        
        items = data.get("products", [])
        total = data.get("totalProducts", len(items))
        
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
        Converte item da API para RawProduct.
        
        Args:
            item: Item da resposta da API
            query: Termo de busca
            cep: CEP
            position: Posição no resultado
            
        Returns:
            RawProduct ou None se inválido
        """
        # Extrai título
        title = item.get("name") or item.get("title")
        if not title:
            return None
        
        # Extrai preço
        price = item.get("price")
        if price is None:
            return None
        
        try:
            price_float = float(price)
        except (ValueError, TypeError):
            return None
        
        # URL do produto
        product_url = item.get("url", "")
        if product_url and not product_url.startswith("http"):
            product_url = f"https://www.paodeacucar.com{product_url}"
        elif not product_url:
            product_id = item.get("id")
            if product_id:
                product_url = f"https://www.paodeacucar.com/produto/{product_id}/p"
            else:
                product_url = "https://www.paodeacucar.com"
        
        # Imagem
        image_url = item.get("image") or item.get("imageUrl")
        
        # Preço unitário
        unit_price_raw = None
        unit_price = item.get("unitPrice")
        unit = item.get("unit", "")
        if unit_price:
            try:
                unit_price_raw = f"R$ {float(unit_price):.2f}/{unit}".replace(".", ",")
            except (ValueError, TypeError):
                pass
        
        # Disponibilidade
        is_available = item.get("available", True)
        
        return self._create_product(
            title=title,
            price=price_float,
            url=product_url,
            query=query,
            cep=cep,
            position=position,
            image_url=image_url,
            external_id=str(item.get("id")) if item.get("id") else None,
            unit_price_raw=unit_price_raw,
            extra_data={
                "brand": item.get("brand"),
                "original_price": item.get("originalPrice"),
                "quantity": item.get("quantity"),
                "available": is_available,
            },
        )


async def search_pao_acucar(query: str, cep: Optional[str] = None, max_pages: int = 1):
    """Função de conveniência para busca rápida."""
    scraper = PaoDeAcucarScraper()
    return await scraper.search(query, cep, max_pages)

