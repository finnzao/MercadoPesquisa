"""
Scraper específico para Atacadão - VERSÃO API GraphQL.
https://www.atacadao.com.br

Este scraper usa a API GraphQL do Atacadão (VTEX) para buscar produtos,
eliminando a necessidade de automação end-to-end com Playwright.

Endpoint principal:
  GET https://www.atacadao.com.br/api/graphql?operationName=ProductsQuery&variables={...}

O CEP/região é controlado pelo parâmetro regionId nos selectedFacets.
"""

import asyncio
import base64
import json
import re
from datetime import datetime
from typing import Optional
from urllib.parse import urlencode, quote

import httpx

from config.logging_config import LoggerMixin
from config.markets import MarketConfig, MarketStatus, ScrapingMethod, MarketSelectors
from src.core.models import RawProduct
from src.core.types import CollectionStatus
from src.scrapers.base import ScraperResult


# CONFIGURAÇÃO DO ATACADÃO

ATACADAO_SELECTORS = MarketSelectors(
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

ATACADAO_CONFIG = MarketConfig(
    id="atacadao",
    display_name="Atacadão",
    base_url="https://www.atacadao.com.br",
    search_url_template="{base_url}/api/graphql",
    status=MarketStatus.ACTIVE,
    method=ScrapingMethod.API,
    selectors=ATACADAO_SELECTORS,
    requests_per_minute=20,
    requires_cep=False,
    supports_pagination=True,
    max_pages=5,
)


# MAPEAMENTO DE SELLERS POR REGIÃO

# Mapeamento de CEPs para sellers (lojas) conhecidos
# Formato: prefixo do CEP -> seller_id
# O seller_id é usado para gerar o regionId
CEP_TO_SELLER = {
    # São Paulo Capital
    "01": "atacadaobr60",  # Vila Maria / Centro
    "02": "atacadaobr60",
    "03": "atacadaobr60",
    "04": "atacadaobr60",
    "05": "atacadaobr60",
    # Grande São Paulo
    "06": "atacadaobr60",
    "07": "atacadaobr60",
    "08": "atacadaobr60",
    "09": "atacadaobr60",
    # Salvador / Bahia
    "40": "atacadaobr1",
    "41": "atacadaobr1",
    "42": "atacadaobr1",
    # Rio de Janeiro
    "20": "atacadaobr30",
    "21": "atacadaobr30",
    "22": "atacadaobr30",
    "23": "atacadaobr30",
    # Default
    "default": "atacadaobr60",
}


def get_seller_for_cep(cep: Optional[str]) -> str:
    """
    Retorna o seller_id apropriado para um CEP.
    
    Args:
        cep: CEP (com ou sem formatação)
        
    Returns:
        seller_id da loja mais próxima
    """
    if not cep:
        return CEP_TO_SELLER["default"]
    
    # Limpa o CEP
    cep_clean = re.sub(r'\D', '', cep)
    
    if len(cep_clean) >= 2:
        prefix = cep_clean[:2]
        if prefix in CEP_TO_SELLER:
            return CEP_TO_SELLER[prefix]
    
    return CEP_TO_SELLER["default"]


def generate_region_id(seller_id: str) -> str:
    """
    Gera o regionId em base64 a partir do seller_id.
    
    Formato: "SW#{seller_id}" codificado em base64
    
    Args:
        seller_id: ID do seller (ex: "atacadaobr60")
        
    Returns:
        regionId codificado (ex: "U1cjYXRhY2FkYW9icjYw")
    """
    raw = f"SW#{seller_id}"
    return base64.b64encode(raw.encode()).decode()


# SCRAPER ATACADÃO API

class AtacadaoScraper(LoggerMixin):
    """
    Scraper para Atacadão usando API GraphQL.
    
    Vantagens sobre a versão Playwright:
    - Muito mais rápido (sem renderização de página)
    - Mais confiável (não depende de seletores CSS)
    - Menos recursos (não precisa de browser)
    - Suporte nativo a CEP via regionId
    
    Uso:
        scraper = AtacadaoScraper()
        result = await scraper.search("arroz 5kg", cep="01310100")
        
        for product in result.products:
            print(f"{product.title}: {product.price_raw}")
    """
    
    # Configurações da API
    API_ENDPOINT = "https://www.atacadao.com.br/api/graphql"
    PRODUCTS_PER_PAGE = 20
    
    # Headers padrão para requisições
    DEFAULT_HEADERS = {
        "Accept": "application/json",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.atacadao.com.br/",
        "Origin": "https://www.atacadao.com.br",
    }
    
    def __init__(self, config: Optional[MarketConfig] = None):
        """
        Inicializa o scraper.
        
        Args:
            config: Configuração do mercado (opcional)
        """
        self.config = config or ATACADAO_CONFIG
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
    
    def _build_variables(
        self,
        query: str,
        page: int = 0,
        per_page: int = 20,
        sort: str = "score_desc",
        cep: Optional[str] = None,
    ) -> dict:
        """
        Constrói as variáveis para a query GraphQL.
        
        Args:
            query: Termo de busca
            page: Número da página (0-indexed)
            per_page: Produtos por página
            sort: Ordenação (score_desc, price_asc, price_desc)
            cep: CEP para determinar região
            
        Returns:
            Dicionário de variáveis
        """
        # Determina o seller baseado no CEP
        seller_id = get_seller_for_cep(cep)
        region_id = generate_region_id(seller_id)
        
        # Constrói o channel object
        channel = json.dumps({
            "salesChannel": "1",
            "seller": seller_id,
            "regionId": region_id,
        }, separators=(',', ':'))
        
        return {
            "first": per_page,
            "after": str(page * per_page),
            "sort": sort,
            "term": query,
            "selectedFacets": [
                {
                    "key": "region-id",
                    "value": region_id,
                },
                {
                    "key": "channel",
                    "value": channel,
                },
                {
                    "key": "locale",
                    "value": "pt-BR",
                },
            ],
        }
    
    def _build_url(self, variables: dict) -> str:
        """
        Constrói a URL completa com os parâmetros.
        
        Args:
            variables: Variáveis da query
            
        Returns:
            URL completa
        """
        params = {
            "operationName": "ProductsQuery",
            "variables": json.dumps(variables, separators=(',', ':')),
        }
        return f"{self.API_ENDPOINT}?{urlencode(params)}"
    
    async def _fetch_products(
        self,
        query: str,
        page: int = 0,
        cep: Optional[str] = None,
    ) -> tuple[list[dict], int]:
        """
        Busca produtos na API.
        
        Args:
            query: Termo de busca
            page: Número da página (0-indexed)
            cep: CEP para região
            
        Returns:
            Tupla (lista de produtos raw, total de produtos)
        """
        client = await self._get_client()
        
        variables = self._build_variables(query, page, self.PRODUCTS_PER_PAGE, cep=cep)
        url = self._build_url(variables)
        
        self.logger.debug(
            "Buscando produtos via API",
            query=query,
            page=page,
            url=url[:150],
        )
        
        try:
            response = await client.get(url)
            response.raise_for_status()
            
            data = response.json()
            
            # Extrai produtos da resposta
            search_data = data.get("data", {}).get("search", {})
            products_data = search_data.get("products", {})
            
            edges = products_data.get("edges", [])
            total_count = products_data.get("pageInfo", {}).get("totalCount", 0)
            
            products = [edge.get("node", {}) for edge in edges if edge.get("node")]
            
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
            
        except Exception as e:
            self.logger.error(
                "Erro ao buscar produtos",
                error=str(e),
                exc_info=True,
            )
            return [], 0
    
    def _parse_product(
        self,
        product_data: dict,
        search_query: str,
        cep: Optional[str],
        position: int,
    ) -> Optional[RawProduct]:
        """
        Converte dados da API para RawProduct.
        
        Args:
            product_data: Dados do produto da API
            search_query: Termo de busca original
            cep: CEP usado na busca
            position: Posição no resultado
            
        Returns:
            RawProduct ou None se dados inválidos
        """
        try:
            # Campos obrigatórios
            product_id = product_data.get("id")
            name = product_data.get("name")
            
            if not name:
                return None
            
            # Preços
            offers = product_data.get("offers", {})
            offers_list = offers.get("offers", [])
            
            # Pega o primeiro preço (unitário) e o preço de atacado se existir
            price = None
            bulk_price = None
            bulk_min_qty = None
            
            for offer in offers_list:
                offer_price = offer.get("price")
                min_qty = offer.get("minQuantity", 1)
                
                if min_qty == 1:
                    price = offer_price
                elif min_qty > 1 and bulk_price is None:
                    bulk_price = offer_price
                    bulk_min_qty = min_qty
            
            # Se não encontrou preço unitário, usa o lowPrice
            if price is None:
                price = offers.get("lowPrice") or offers.get("highPrice")
            
            if price is None:
                return None
            
            # Formata preço no padrão brasileiro
            price_raw = f"R$ {price:.2f}".replace(".", ",")
            
            # Preço de atacado como unit_price_raw
            unit_price_raw = None
            if bulk_price and bulk_min_qty:
                unit_price_raw = f"R$ {bulk_price:.2f} (a partir de {bulk_min_qty} un.)".replace(".", ",")
            
            # URL do produto
            slug = product_data.get("slug", "")
            product_url = f"{self.config.base_url}/{slug}/p" if slug else self.config.base_url
            
            # Imagem
            images = product_data.get("image", [])
            image_url = images[0].get("url") if images else None
            
            # Marca
            brand = product_data.get("brand", {})
            brand_name = brand.get("brandName") or brand.get("name")
            
            # SKU
            sku = product_data.get("sku")
            
            # Disponibilidade - se tem preço, está disponível
            availability = "Disponível" if price else "Indisponível"
            
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
                    "source": "api",
                    "brand": brand_name,
                    "sku": sku,
                    "low_price": offers.get("lowPrice"),
                    "high_price": offers.get("highPrice"),
                    "bulk_price": bulk_price,
                    "bulk_min_qty": bulk_min_qty,
                    "unit_per_box": offers_list[0].get("unitPerBox") if offers_list else None,
                },
            )
            
        except Exception as e:
            self.logger.debug(
                "Erro ao parsear produto",
                error=str(e),
                product_id=product_data.get("id"),
            )
            return None
    
    async def search(
        self,
        query: str,
        cep: Optional[str] = None,
        max_pages: int = 1,
    ) -> ScraperResult:
        """
        Executa busca no Atacadão usando a API GraphQL.
        
        Args:
            query: Termo de busca (ex: "arroz 5kg")
            cep: CEP para determinar região/loja (opcional)
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
            cep=cep,
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
                    cep=cep,
                )
                
                if total_available is None:
                    total_available = total_count
                
                if not products_data:
                    # Sem mais produtos
                    if page_num == 0:
                        result.status = CollectionStatus.NO_RESULTS
                    break
                
                # Converte para RawProduct
                for idx, product_data in enumerate(products_data):
                    position = page_num * self.PRODUCTS_PER_PAGE + idx + 1
                    product = self._parse_product(
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
                if (page_num + 1) * self.PRODUCTS_PER_PAGE >= total_available:
                    break
                
                # Pequeno delay entre páginas
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
        Na versão API, o CEP é passado diretamente para search().
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

async def search_atacadao(
    query: str,
    cep: Optional[str] = None,
    max_pages: int = 1,
) -> ScraperResult:
    """
    Função de conveniência para busca rápida no Atacadão.
    
    Args:
        query: Termo de busca
        cep: CEP para região (opcional)
        max_pages: Máximo de páginas
        
    Returns:
        ScraperResult
        
    Exemplo:
        result = await search_atacadao("arroz 5kg", cep="01310100")
        for product in result.products:
            print(f"{product.title}: {product.price_raw}")
    """
    scraper = AtacadaoScraper()
    return await scraper.search(query, cep=cep, max_pages=max_pages)


# TESTE LOCAL

if __name__ == "__main__":
    async def test():
        print("=" * 80)
        print("TESTE DO SCRAPER ATACADÃO (API)")
        print("=" * 80)
        
        scraper = AtacadaoScraper()
        
        # Teste 1: Busca simples
        print("\n[TESTE 1] Busca: 'arroz 5kg'")
        result = await scraper.search("arroz 5kg", max_pages=1)
        
        print(f"Status: {result.status.value}")
        print(f"Produtos: {result.products_count}")
        print(f"Duração: {result.duration_seconds:.2f}s")
        
        if result.products:
            print("\nPrimeiros 3 produtos:")
            for p in result.products[:3]:
                print(f"  - {p.title}")
                print(f"    Preço: {p.price_raw}")
                print(f"    URL: {p.url[:60]}...")
                if p.extra_data.get("bulk_price"):
                    print(f"    Atacado: R$ {p.extra_data['bulk_price']:.2f} (min {p.extra_data['bulk_min_qty']} un.)")
                print()
        
        # Teste 2: Busca com CEP
        print("\n[TESTE 2] Busca: 'leite' com CEP 40000000 (Salvador)")
        result2 = await scraper.search("leite", cep="40000000", max_pages=1)
        
        print(f"Status: {result2.status.value}")
        print(f"Produtos: {result2.products_count}")
        
        if result2.products:
            print(f"Primeiro produto: {result2.products[0].title}")
    
    asyncio.run(test())