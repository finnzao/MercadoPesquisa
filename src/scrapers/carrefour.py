"""
API de dados do Carrefour (Remix/VTEX)
"""

import asyncio
import json
import re
from datetime import datetime
from typing import Optional, Any
from urllib.parse import quote, urlencode

import httpx

from config.logging_config import LoggerMixin
from config.markets import MarketConfig, MarketStatus, ScrapingMethod, MarketSelectors
from src.core.models import RawProduct
from src.core.types import CollectionStatus
from src.scrapers.base import ScraperResult

# CONFIGURAÇÃO DO CARREFOUR
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
    requests_per_minute=20,
    requires_cep=False,
    supports_pagination=True,
    max_pages=5,
)

# PARSER DE DADOS REMIX
class RemixDataParser:
    """
    Parser para o formato de dados serializado do Remix/React Router.
    
    O Carrefour usa uma estrutura "flat" onde:
    - O array contém valores intercalados com referências
    - Dicionários usam chaves como '_XXXX' onde XXXX é o índice do NOME do campo
    - O valor está no índice especificado como valor da chave
    
    Exemplo:
        data[2934] = "productId"      # Nome do campo
        data[2935] = "4739577"        # Valor do campo
        
        dict = {"_2934": 2935}        # Chave _2934 -> nome em data[2934], valor em data[2935]
    """
    
    def __init__(self, data: list):
        self.data = data
        self._products_list_key = None
        self._find_products_key()
    
    def _find_products_key(self):
        """
        Encontra o índice onde está a lista de produtos.
        Procura pela string 'products' seguida de uma lista.
        """
        for i, item in enumerate(self.data):
            if item == 'products':
                if i + 1 < len(self.data):
                    next_item = self.data[i + 1]
                    if isinstance(next_item, list):
                        self._products_list_key = i + 1
                        return
    
    def get_value(self, index: int) -> Any:
        """Obtém valor pelo índice, tratando referências negativas."""
        if index < 0 or index >= len(self.data):
            return None
        return self.data[index]
    
    def extract_dict(self, obj: dict) -> dict:
        """
        Extrai os campos de um dict de referências.
        
        Para cada chave "_XXXX": valor_idx:
        - Nome do campo está em data[XXXX]
        - Valor está em data[valor_idx]
        
        Returns:
            Dict com {nome_campo: valor}
        """
        result = {}
        
        for key, value_idx in obj.items():
            if not key.startswith('_'):
                continue
            
            try:
                key_num = int(key[1:])  # Remove '_' e converte para int
                
                # Nome do campo está no próprio key_num
                field_name = self.get_value(key_num)
                
                if not isinstance(field_name, str):
                    continue
                
                # Valor está no índice especificado
                if isinstance(value_idx, int):
                    value = self.get_value(value_idx)
                else:
                    value = value_idx
                
                result[field_name] = value
                
            except (ValueError, TypeError):
                pass
        
        return result
    
    def get_products_indices(self) -> list[int]:
        """Retorna os índices dos produtos."""
        if self._products_list_key is None:
            return []
        
        products_list = self.get_value(self._products_list_key)
        if isinstance(products_list, list):
            return products_list
        return []
    
    def parse_product(self, prod_idx: int) -> Optional[dict]:
        """
        Parseia um produto completo pelo seu índice.
        
        Returns:
            Dict com dados do produto ou None se inválido
        """
        prod_dict = self.get_value(prod_idx)
        if not isinstance(prod_dict, dict):
            return None
        
        # Extrair campos do produto
        product = self.extract_dict(prod_dict)
        
        if not product.get('productName'):
            return None
        
        # Processar items (contém sellers, preços, imagens)
        items_ref = product.get('items')
        if isinstance(items_ref, list) and len(items_ref) > 0:
            item_idx = items_ref[0]
            item_dict = self.get_value(item_idx)
            
            if isinstance(item_dict, dict):
                item_data = self.extract_dict(item_dict)
                product['_item'] = item_data
                
                # Extrair sellers
                sellers_ref = item_data.get('sellers')
                if isinstance(sellers_ref, list) and len(sellers_ref) > 0:
                    seller_idx = sellers_ref[0]
                    seller_dict = self.get_value(seller_idx)
                    
                    if isinstance(seller_dict, dict):
                        seller_data = self.extract_dict(seller_dict)
                        product['_seller'] = seller_data
                        
                        # Extrair oferta comercial (preços)
                        offer_ref = seller_data.get('commertialOffer')
                        if isinstance(offer_ref, dict):
                            offer_data = self.extract_dict(offer_ref)
                            product['_offer'] = offer_data
                
                # Extrair imagens
                images_ref = item_data.get('images')
                if isinstance(images_ref, list) and len(images_ref) > 0:
                    img_idx = images_ref[0]
                    img_dict = self.get_value(img_idx)
                    
                    if isinstance(img_dict, dict):
                        img_data = self.extract_dict(img_dict)
                        product['_image'] = img_data
        
        return product

# SCRAPER CARREFOUR API
class CarrefourScraper(LoggerMixin):
    """
    Scraper para Mercado Carrefour usando API de dados Remix.
    
    Vantagens sobre a versão Playwright:
    - Muito mais rápido (sem renderização de página)
    - Mais confiável (não depende de seletores CSS)
    - Menos recursos (não precisa de browser)
    
    Uso:
        scraper = CarrefourScraper()
        result = await scraper.search("arroz 5kg")
        
        for product in result.products:
            print(f"{product.title}: {product.price_raw}")
    """
    
    # Headers padrão para requisições
    DEFAULT_HEADERS = {
        "Accept": "text/x-script",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://mercado.carrefour.com.br/",
        "Origin": "https://mercado.carrefour.com.br",
    }
    
    PRODUCTS_PER_PAGE = 20
    
    def __init__(self, config: Optional[MarketConfig] = None):
        """
        Inicializa o scraper.
        
        Args:
            config: Configuração do mercado (opcional)
        """
        self.config = config or CARREFOUR_CONFIG
        self._client: Optional[httpx.AsyncClient] = None
    
    @property
    def market_id(self) -> str:
        """ID do mercado."""
        return self.config.id
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Retorna cliente HTTP (lazy initialization)."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers=self.DEFAULT_HEADERS,
                timeout=30.0,
                follow_redirects=True,
            )
        return self._client
    
    async def _close_client(self) -> None:
        """Fecha o cliente HTTP."""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    def _build_url(self, query: str, page: int = 0) -> str:
        """
        Constrói a URL de busca.
        
        Args:
            query: Termo de busca
            page: Número da página (0-indexed)
            
        Returns:
            URL completa
        """
        # Encode do termo de busca
        encoded_query = quote(query)
        
        # Parâmetros da URL - IMPORTANTE: precisa incluir routes/busca.$term
        params = {
            "_routes": "layout/default,routes/busca,routes/busca.$term"
        }
        
        # Se página > 0, adiciona parâmetros de paginação
        if page > 0:
            params["page"] = str(page)
        
        base_url = f"{self.config.base_url}/busca/{encoded_query}.data"
        return f"{base_url}?{urlencode(params)}"
    
    async def _fetch_products(
        self,
        query: str,
        page: int = 0,
    ) -> tuple[list[dict], int]:
        """
        Busca produtos na API.
        
        Args:
            query: Termo de busca
            page: Número da página (0-indexed)
            
        Returns:
            Tupla (lista de produtos dict, total de produtos)
        """
        client = await self._get_client()
        
        url = self._build_url(query, page)
        
        self.logger.debug(
            "Buscando produtos via API",
            query=query,
            page=page,
            url=url[:150],
        )
        
        try:
            response = await client.get(url)
            response.raise_for_status()
            
            # Parse do JSON
            data = response.json()
            
            if not isinstance(data, list):
                self.logger.warning("Resposta não é uma lista", type=type(data))
                return [], 0
            
            # Usar o parser customizado
            parser = RemixDataParser(data)
            
            products_indices = parser.get_products_indices()
            products = []
            
            for prod_idx in products_indices:
                product = parser.parse_product(prod_idx)
                if product:
                    products.append(product)
            
            # Tentar encontrar o total (pode estar em diferentes lugares)
            total_count = len(products)  # Default
            for i, item in enumerate(data):
                if item == 'recordsFiltered' or item == 'totalProducts':
                    if i + 1 < len(data):
                        total_val = data[i + 1]
                        if isinstance(total_val, int):
                            total_count = total_val
                            break
            
            self.logger.info(
                "Produtos recebidos da API",
                page=page,
                count=len(products),
                total=total_count,
            )
            
            return products, total_count
            
        except httpx.HTTPStatusError as e:
            self.logger.error(
                "Erro HTTP na API",
                status_code=e.response.status_code,
                error=str(e),
            )
            return [], 0
            
        except json.JSONDecodeError as e:
            self.logger.error(
                "Erro ao decodificar JSON",
                error=str(e),
            )
            return [], 0
            
        except Exception as e:
            self.logger.error(
                "Erro ao buscar produtos",
                error=str(e),
                exc_info=True,
            )
            return [], 0
    
    def _convert_to_raw_product(
        self,
        product_data: dict,
        search_query: str,
        cep: Optional[str],
        position: int,
    ) -> Optional[RawProduct]:
        """
        Converte dados da API para RawProduct.
        
        Args:
            product_data: Dados do produto parseados
            search_query: Termo de busca original
            cep: CEP usado na busca
            position: Posição no resultado
            
        Returns:
            RawProduct ou None se dados inválidos
        """
        try:
            name = product_data.get('productName')
            if not name:
                return None
            
            # Preços vêm da oferta comercial
            offer = product_data.get('_offer', {})
            price = offer.get('Price')
            list_price = offer.get('ListPrice')
            spot_price = offer.get('spotPrice')  # Preço por unidade de medida
            
            price_raw = None
            if price:
                price_raw = f"R$ {float(price):.2f}".replace(".", ",")
            
            # Preço por unidade (para produtos vendidos por kg, etc)
            unit_price_raw = None
            item_data = product_data.get('_item', {})
            measurement_unit = item_data.get('measurementUnit')
            if spot_price and measurement_unit:
                unit_price_raw = f"R$ {float(spot_price):.2f}/{measurement_unit}".replace(".", ",")
            
            # URL do produto
            link = product_data.get('link', '')
            product_url = f"{self.config.base_url}{link}" if link else self.config.base_url
            
            # Imagem
            image_data = product_data.get('_image', {})
            image_url = image_data.get('imageUrl')
            
            # SKU
            sku = product_data.get('productReference')
            
            # Marca
            brand = product_data.get('brand')
            
            # Disponibilidade
            available_qty = offer.get('AvailableQuantity', 0)
            availability = "Disponível" if available_qty > 0 else "Indisponível"
            
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
                    "discount": round(float(list_price) - float(price), 2) if price and list_price and float(list_price) > float(price) else None,
                },
            )
            
        except Exception as e:
            self.logger.debug(
                "Erro ao converter produto",
                error=str(e),
                product_name=product_data.get('productName'),
            )
            return None
    
    async def search(
        self,
        query: str,
        cep: Optional[str] = None,
        max_pages: int = 1,
    ) -> ScraperResult:
        """
        Executa busca no Mercado Carrefour usando a API de dados.
        
        Args:
            query: Termo de busca (ex: "arroz 5kg")
            cep: CEP (não usado atualmente, reservado para futuro)
            max_pages: Número máximo de páginas
            
        Returns:
            ScraperResult com produtos encontrados
        """
        result = ScraperResult(
            market_id=self.market_id,
            search_query=query,
            status=CollectionStatus.FAILED,
        )
        
        self.logger.info(
            "Iniciando busca via API",
            market=self.market_id,
            query=query,
            max_pages=max_pages,
        )
        
        try:
            all_products = []
            total_available = None
            
            for page_num in range(max_pages):
                # Busca produtos
                products_data, total_count = await self._fetch_products(
                    query=query,
                    page=page_num,
                )
                
                if total_available is None:
                    total_available = total_count
                
                if not products_data:
                    if page_num == 0:
                        result.status = CollectionStatus.NO_RESULTS
                    break
                
                # Converte para RawProduct
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
                    "Página processada",
                    page=page_num + 1,
                    products_page=len(products_data),
                    products_total=len(all_products),
                )
                
                # Verifica se há mais páginas
                if len(products_data) < self.PRODUCTS_PER_PAGE:
                    break
                
                # Delay entre páginas
                if page_num < max_pages - 1:
                    await asyncio.sleep(0.5)
            
            result.products = all_products
            result.status = (
                CollectionStatus.SUCCESS if all_products
                else CollectionStatus.NO_RESULTS
            )
            
        except Exception as e:
            result.status = CollectionStatus.FAILED
            result.error_message = str(e)
            self.logger.error(
                "Erro na busca",
                error=str(e),
                exc_info=True,
            )
            
        finally:
            await self._close_client()
            result.mark_finished()
        
        self.logger.info(
            "Busca finalizada",
            market=self.market_id,
            status=result.status.value,
            products=result.products_count,
            duration=f"{result.duration_seconds:.2f}s" if result.duration_seconds else "N/A",
        )
        
        return result
    
    # =========================================================================
    # MÉTODOS DE COMPATIBILIDADE COM BaseScraper
    # =========================================================================
    
    async def set_location(self, page, cep: str) -> bool:
        """
        Compatibilidade com interface BaseScraper.
        O Carrefour não usa CEP na API de busca atualmente.
        """
        return True
    
    async def extract_products(
        self,
        page,
        search_query: str,
        cep: Optional[str] = None,
    ) -> list[RawProduct]:
        """
        Compatibilidade com interface BaseScraper.
        Na versão API, use search() diretamente.
        """
        result = await self.search(search_query, cep=cep, max_pages=1)
        return result.products

# FUNÇÕES DE CONVENIÊNCIA
async def search_carrefour(
    query: str,
    cep: Optional[str] = None,
    max_pages: int = 1,
) -> ScraperResult:
    """
    Função de conveniência para busca rápida no Mercado Carrefour.
    
    Args:
        query: Termo de busca
        cep: CEP (reservado para futuro)
        max_pages: Máximo de páginas
        
    Returns:
        ScraperResult
        
    Exemplo:
        result = await search_carrefour("banana prata")
        for product in result.products:
            print(f"{product.title}: {product.price_raw}")
    """
    scraper = CarrefourScraper()
    return await scraper.search(query, cep=cep, max_pages=max_pages)

# TESTE LOCAL
if __name__ == "__main__":
    async def test():
        print("=" * 80)
        print("TESTE DO SCRAPER CARREFOUR (API v2)")
        print("=" * 80)
        
        scraper = CarrefourScraper()
        
        # Teste: Busca simples
        print("\n[TESTE] Busca: 'banana prata'")
        result = await scraper.search("banana prata", max_pages=1)
        
        print(f"Status: {result.status.value}")
        print(f"Produtos: {result.products_count}")
        print(f"Duração: {result.duration_seconds:.2f}s" if result.duration_seconds else "N/A")
        
        if result.products:
            print("\nProdutos encontrados:")
            for p in result.products[:5]:
                print(f"  - {p.title}")
                print(f"    Preço: {p.price_raw}")
                if p.unit_price_raw:
                    print(f"    Preço/unidade: {p.unit_price_raw}")
                print(f"    Marca: {p.extra_data.get('brand', 'N/A')}")
                if p.extra_data.get('discount'):
                    print(f"    Desconto: R$ {p.extra_data['discount']:.2f}")
                print()
    
    asyncio.run(test())