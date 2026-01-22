"""
Carrefour Scraper - API Remix/VTEX
"""

import json
import brotli  # pip install brotli
import gzip
import zlib
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from config.markets import MARKETS_CONFIG
from src.core.models import RawProduct
from src.scrapers.base_api import BaseAPIScraper


class RemixDataParser:
    """Parser para formato Remix (array flat com referências)."""
    
    def __init__(self, data: list):
        self.data = data
        self._products_idx = self._find_products_index()
    
    def _find_products_index(self) -> Optional[int]:
        for i, item in enumerate(self.data):
            if item == 'products' and i + 1 < len(self.data):
                if isinstance(self.data[i + 1], list):
                    return i + 1
        return None
    
    def get_value(self, idx: int) -> Any:
        if 0 <= idx < len(self.data):
            return self.data[idx]
        return None
    
    def extract_dict(self, obj: dict) -> dict:
        """Extrai campos de dict de referências (_XXXX: valor_idx)."""
        result = {}
        for key, value_idx in obj.items():
            if not key.startswith('_'):
                continue
            try:
                key_num = int(key[1:])
                field_name = self.get_value(key_num)
                if isinstance(field_name, str):
                    result[field_name] = self.get_value(value_idx) if isinstance(value_idx, int) else value_idx
            except (ValueError, TypeError):
                pass
        return result
    
    def get_products(self) -> List[dict]:
        """Retorna lista de produtos parseados."""
        if self._products_idx is None:
            return []
        
        indices = self.get_value(self._products_idx)
        if not isinstance(indices, list):
            return []
        
        products = []
        for idx in indices:
            prod = self._parse_product(idx)
            if prod:
                products.append(prod)
        return products
    
    def _parse_product(self, idx: int) -> Optional[dict]:
        prod_dict = self.get_value(idx)
        if not isinstance(prod_dict, dict):
            return None
        
        product = self.extract_dict(prod_dict)
        if not product.get('productName'):
            return None
        
        # Extrai items (SKUs)
        items_ref = product.get('items')
        if isinstance(items_ref, list) and items_ref:
            item_dict = self.get_value(items_ref[0])
            if isinstance(item_dict, dict):
                item_data = self.extract_dict(item_dict)
                product['_item'] = item_data
                
                # Extrai sellers
                sellers_ref = item_data.get('sellers')
                if isinstance(sellers_ref, list) and sellers_ref:
                    seller_dict = self.get_value(sellers_ref[0])
                    if isinstance(seller_dict, dict):
                        seller_data = self.extract_dict(seller_dict)
                        product['_seller'] = seller_data
                        
                        # Extrai oferta
                        offer_ref = seller_data.get('commertialOffer')
                        if isinstance(offer_ref, dict):
                            product['_offer'] = self.extract_dict(offer_ref)
                
                # Extrai imagem
                images_ref = item_data.get('images')
                if isinstance(images_ref, list) and images_ref:
                    img_dict = self.get_value(images_ref[0])
                    if isinstance(img_dict, dict):
                        product['_image'] = self.extract_dict(img_dict)
        
        return product


def decompress_response(content: bytes, content_encoding: str = None) -> str:
    """
    Descomprime a resposta baseado no encoding ou tenta múltiplos métodos.
    
    Args:
        content: Bytes da resposta
        content_encoding: Header Content-Encoding da resposta
        
    Returns:
        String decodificada
    """
    # Se já é string válida, retorna
    try:
        return content.decode('utf-8')
    except UnicodeDecodeError:
        pass
    
    # Tenta Brotli
    try:
        decompressed = brotli.decompress(content)
        return decompressed.decode('utf-8')
    except Exception:
        pass
    
    # Tenta gzip
    try:
        decompressed = gzip.decompress(content)
        return decompressed.decode('utf-8')
    except Exception:
        pass
    
    # Tenta zlib (deflate)
    try:
        decompressed = zlib.decompress(content)
        return decompressed.decode('utf-8')
    except Exception:
        pass
    
    # Tenta zlib com wbits negativo
    try:
        decompressed = zlib.decompress(content, -zlib.MAX_WBITS)
        return decompressed.decode('utf-8')
    except Exception:
        pass
    
    # Última tentativa: decodificar com errors='replace'
    return content.decode('utf-8', errors='replace')


class CarrefourScraper(BaseAPIScraper):
    """
    Scraper Carrefour via API .data (Remix).
    VERSÃO CORRIGIDA - Trata respostas comprimidas adequadamente.
    """
    
    PRODUCTS_PER_PAGE = 20
    BASE_URL = "https://mercado.carrefour.com.br"
    
    def __init__(self, config=None):
        config = config or MARKETS_CONFIG.get("carrefour")
        super().__init__(config)
    
    def _build_request(self, query: str, page: int) -> Dict[str, Any]:
        encoded = quote(query)
        url = f"{self.BASE_URL}/busca/{encoded}.data"
        
        params = {"_routes": "routes/busca.$term"}
        if page > 0:
            params["page"] = str(page + 1)
        
        return {
            "url": url,
            "method": "GET",
            "params": params,
            "headers": {
                "Accept": "text/x-script, application/json, */*",
                "Accept-Encoding": "gzip, deflate, br",
                "Referer": "https://mercado.carrefour.com.br/",
            },
        }
    
    async def search(self, query: str, cep: Optional[str] = None, max_pages: int = 1):
        """
        Sobrescreve o método search para tratar respostas comprimidas.
        """
        from dataclasses import dataclass, field
        from datetime import datetime
        from src.core.types import CollectionStatus
        from src.scrapers.base_pooled import ScraperResult
        from src.core.http_client import get_http_client
        import asyncio
        import random
        
        result = ScraperResult(
            market_id=self.market_id,
            search_query=query,
            status=CollectionStatus.FAILED,
        )
        
        self.logger.info("Iniciando busca API", market=self.market_id, query=query)
        
        try:
            http = await get_http_client()
            all_products = []
            total_available = None
            
            for page_num in range(max_pages):
                req = self._build_request(query, page_num)
                
                # Executa requisição
                response = await http.get(
                    req["url"],
                    market_id=self.market_id,
                    headers=req.get("headers"),
                    params=req.get("params"),
                )
                
                # CORREÇÃO: Trata resposta que pode estar comprimida
                try:
                    # Primeiro tenta o método normal
                    data = response.json()
                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                    self.logger.debug(
                        "Resposta não é JSON direto, tentando descomprimir",
                        error=str(e)[:100]
                    )
                    
                    # Obtém o content-encoding do header
                    content_encoding = response.headers.get('content-encoding', '')
                    
                    # Tenta descomprimir
                    text_content = decompress_response(response.content, content_encoding)
                    
                    # Agora tenta parsear o JSON
                    try:
                        data = json.loads(text_content)
                    except json.JSONDecodeError as je:
                        self.logger.error(
                            "Falha ao parsear JSON após descompressão",
                            error=str(je)[:200],
                            content_preview=text_content[:200] if text_content else "empty"
                        )
                        result.status = CollectionStatus.FAILED
                        result.error_message = f"JSON inválido: {str(je)[:100]}"
                        break
                
                products, total = self._parse_response(data, query, cep, page_num)
                
                if total_available is None:
                    total_available = total
                
                if not products:
                    if page_num == 0:
                        result.status = CollectionStatus.NO_RESULTS
                    break
                
                all_products.extend(products)
                result.pages_scraped += 1
                
                self.logger.info("Página coletada", page=page_num + 1, products=len(products))
                
                # Verifica se há mais páginas
                if total_available and (page_num + 1) * self.PRODUCTS_PER_PAGE >= total_available:
                    break
                
                # Delay entre páginas
                if page_num < max_pages - 1:
                    await asyncio.sleep(random.uniform(0.3, 0.8))
            
            result.products = all_products
            result.status = CollectionStatus.SUCCESS if all_products else CollectionStatus.NO_RESULTS
            
        except Exception as e:
            result.status = CollectionStatus.FAILED
            result.error_message = str(e)
            self.logger.error("Erro na busca", error=str(e), exc_info=True)
        
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
    
    def _parse_response(self, data: Any, query: str, cep: Optional[str], page: int) -> tuple[List[RawProduct], int]:
        if not isinstance(data, list):
            self.logger.warning("Resposta não é uma lista", type=type(data).__name__)
            return [], 0
        
        parser = RemixDataParser(data)
        products_data = parser.get_products()
        
        # Tenta extrair total
        total = len(products_data)
        for i, item in enumerate(data):
            if item in ('recordsFiltered', 'totalProducts') and i + 1 < len(data):
                val = data[i + 1]
                if isinstance(val, int):
                    total = val
                    break
        
        products = []
        for idx, p in enumerate(products_data):
            product = self._convert_product(p, query, cep, page * self.PRODUCTS_PER_PAGE + idx + 1)
            if product:
                products.append(product)
        
        return products, total
    
    def _convert_product(self, p: dict, query: str, cep: Optional[str], position: int) -> Optional[RawProduct]:
        name = p.get('productName')
        if not name:
            return None
        
        offer = p.get('_offer', {})
        price = offer.get('Price')
        if not price:
            return None
        
        try:
            price_float = float(price)
        except (ValueError, TypeError):
            return None
        
        # URL
        link = p.get('link', '')
        url = f"{self.BASE_URL}{link}" if link else self.BASE_URL
        
        # Imagem
        image = p.get('_image', {}).get('imageUrl')
        
        # Preço unitário
        item = p.get('_item', {})
        spot = offer.get('spotPrice')
        unit = item.get('measurementUnit')
        unit_price = None
        if spot and unit:
            unit_price = f"R$ {float(spot):.2f}/{unit}".replace(".", ",")
        
        return self._create_product(
            title=name,
            price=price_float,
            url=url,
            query=query,
            cep=cep,
            position=position,
            image_url=image,
            external_id=p.get('productReference'),
            unit_price_raw=unit_price,
            extra_data={
                "brand": p.get('brand'),
                "listPrice": offer.get('ListPrice'),
                "availableQty": offer.get('AvailableQuantity'),
            },
        )


async def search_carrefour(query: str, cep: Optional[str] = None, max_pages: int = 1):
    """Função de conveniência."""
    scraper = CarrefourScraper()
    return await scraper.search(query, cep, max_pages)