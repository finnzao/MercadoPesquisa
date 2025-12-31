"""
Scraper específico para Pão de Açúcar - VERSÃO COM API.
https://www.paodeacucar.com

Esta versão usa a API interna do Pão de Açúcar para buscar produtos,
executando as requisições de dentro do contexto do navegador para evitar CORS.
"""

import asyncio
import json
import re
from datetime import datetime
from typing import Optional
from urllib.parse import quote_plus

from playwright.async_api import async_playwright, Page


async def search_pao_acucar_api(
    search_term: str = "arroz 5kg",
    store_id: int = 461,  # Loja padrão (pode variar por CEP)
    page_num: int = 1,
    results_per_page: int = 16,
    headless: bool = True,
    debug: bool = False,
) -> dict:
    """
    Busca produtos no Pão de Açúcar usando a API interna.
    
    A chave para evitar CORS é executar a requisição fetch() de DENTRO
    do contexto do navegador (page.evaluate), não de fora.
    
    Args:
        search_term: Termo de busca
        store_id: ID da loja (varia por CEP/região)
        page_num: Número da página
        results_per_page: Resultados por página
        headless: Se True, roda sem interface gráfica
        debug: Se True, mostra informações de debug
        
    Returns:
        Dicionário com produtos encontrados
    """
    
    print(f"🔍 Buscando: {search_term}")
    print(f"   Store ID: {store_id}, Página: {page_num}")
    
    async with async_playwright() as p:
        # Inicia o navegador
        browser = await p.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ]
        )
        
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="pt-BR",
        )
        
        page = await context.new_page()
        
        try:
            # PASSO 1: Navegar para o site do Pão de Açúcar primeiro
            # Isso é ESSENCIAL para que as requisições à API funcionem sem CORS
            print("\n[1/3] Navegando para o site (estabelecendo contexto)...")
            await page.goto(
                "https://www.paodeacucar.com/",
                wait_until="domcontentloaded",
            )
            await page.wait_for_timeout(2000)
            
            # PASSO 2: Executar a requisição à API de DENTRO do navegador
            # Usando page.evaluate(), a requisição parte do contexto do site,
            # então o servidor aceita (mesmo Origin)
            print("\n[2/3] Executando requisição à API (de dentro do navegador)...")
            
            # Prepara o payload da API
            api_payload = {
                "terms": search_term,
                "page": page_num,
                "sortBy": "relevance",
                "resultsPerPage": results_per_page,
                "allowRedirect": True,
                "storeId": store_id,
                "department": "ecom",
                "customerPlus": True,
                "partner": "linx",
                # userHash pode ser gerado ou omitido em alguns casos
            }
            
            # Executa fetch de dentro do contexto do navegador
            # Esta é a SOLUÇÃO para o problema de CORS!
            api_result = await page.evaluate("""
                async (payload) => {
                    try {
                        const response = await fetch("https://api.vendas.gpa.digital/pa/search/search", {
                            method: "POST",
                            headers: {
                                "Accept": "application/json, text/plain, */*",
                                "Content-Type": "application/json",
                            },
                            body: JSON.stringify(payload),
                        });
                        
                        if (!response.ok) {
                            return {
                                error: true,
                                status: response.status,
                                statusText: response.statusText,
                            };
                        }
                        
                        const data = await response.json();
                        return {
                            error: false,
                            data: data,
                        };
                    } catch (e) {
                        return {
                            error: true,
                            message: e.message,
                        };
                    }
                }
            """, api_payload)
            
            # PASSO 3: Processar resultados
            print("\n[3/3] Processando resultados...")
            
            if api_result.get("error"):
                print(f"❌ Erro na API: {api_result}")
                return {"error": api_result, "products": []}
            
            data = api_result.get("data", {})
            products_raw = data.get("products", [])
            
            print(f"✅ Encontrados {len(products_raw)} produtos!")
            
            # Formata os produtos
            products = []
            for idx, prod in enumerate(products_raw):
                product = {
                    "position": idx + 1,
                    "id": prod.get("id"),
                    "title": prod.get("name", prod.get("title", "")),
                    "brand": prod.get("brand", ""),
                    "price": prod.get("price", 0),
                    "price_formatted": f"R$ {prod.get('price', 0):.2f}".replace(".", ","),
                    "original_price": prod.get("originalPrice"),
                    "unit_price": prod.get("unitPrice"),
                    "unit": prod.get("unit", ""),
                    "image_url": prod.get("image", prod.get("imageUrl", "")),
                    "url": f"https://www.paodeacucar.com{prod.get('url', '')}" if prod.get('url') else None,
                    "available": prod.get("available", True),
                    "quantity": prod.get("quantity", ""),
                }
                products.append(product)
            
            # Metadados da busca
            result = {
                "search_term": search_term,
                "total_products": data.get("totalProducts", len(products)),
                "page": page_num,
                "results_per_page": results_per_page,
                "products": products,
                "raw_response": data if debug else None,
            }
            
            return result
            
        except Exception as e:
            print(f"❌ Erro: {e}")
            import traceback
            traceback.print_exc()
            return {"error": str(e), "products": []}
            
        finally:
            await browser.close()


async def get_store_id_by_cep(cep: str, headless: bool = True) -> Optional[int]:
    """
    Obtém o ID da loja mais próxima baseado no CEP.
    
    Args:
        cep: CEP para buscar loja
        headless: Se True, roda sem interface gráfica
        
    Returns:
        ID da loja ou None se não encontrar
    """
    
    print(f"🏪 Buscando loja para CEP: {cep}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            locale="pt-BR",
        )
        page = await context.new_page()
        
        try:
            # Navega para o site
            await page.goto("https://www.paodeacucar.com/", wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            
            # Busca a loja pelo CEP usando a API
            cep_clean = cep.replace("-", "").replace(".", "")
            
            store_result = await page.evaluate("""
                async (cep) => {
                    try {
                        const response = await fetch(`https://api.vendas.gpa.digital/pa/delivery/stores?zipCode=${cep}`, {
                            method: "GET",
                            headers: {
                                "Accept": "application/json",
                            },
                        });
                        
                        if (!response.ok) {
                            return { error: true, status: response.status };
                        }
                        
                        const data = await response.json();
                        return { error: false, data: data };
                    } catch (e) {
                        return { error: true, message: e.message };
                    }
                }
            """, cep_clean)
            
            if store_result.get("error"):
                print(f"⚠️ Não foi possível obter loja para o CEP")
                return None
            
            stores = store_result.get("data", {}).get("stores", [])
            if stores:
                store_id = stores[0].get("id")
                store_name = stores[0].get("name", "")
                print(f"✅ Loja encontrada: {store_name} (ID: {store_id})")
                return store_id
            
            return None
            
        finally:
            await browser.close()


def display_products(result: dict, limit: int = 10):
    """Exibe os produtos de forma formatada."""
    
    products = result.get("products", [])
    
    print("\n" + "=" * 70)
    print(f"RESULTADOS: {result.get('search_term', '')}")
    print(f"Total: {result.get('total_products', 0)} produtos")
    print("=" * 70)
    
    if not products:
        print("\n⚠️ Nenhum produto encontrado")
        return
    
    for p in products[:limit]:
        print(f"\n[{p['position']}] {p['title'][:60]}...")
        print(f"    Preço: {p['price_formatted']}")
        if p.get('unit_price'):
            print(f"    Preço/unidade: R$ {p['unit_price']:.2f}/{p.get('unit', 'un')}")
        if p.get('url'):
            print(f"    URL: {p['url'][:70]}...")
    
    if len(products) > limit:
        print(f"\n... e mais {len(products) - limit} produtos")
    
    # Estatísticas de preço
    prices = [p['price'] for p in products if p.get('price')]
    if prices:
        print("\n" + "-" * 40)
        print("ESTATÍSTICAS DE PREÇO")
        print("-" * 40)
        print(f"Menor preço: R$ {min(prices):.2f}")
        print(f"Maior preço: R$ {max(prices):.2f}")
        print(f"Preço médio: R$ {sum(prices)/len(prices):.2f}")


async def main():
    """Exemplo de uso."""
    
    print("=" * 70)
    print("SCRAPER PÃO DE AÇÚCAR - VERSÃO API")
    print("=" * 70)
    
    # Exemplo 1: Busca simples
    result = await search_pao_acucar_api(
        search_term="arroz 5kg",
        headless=True,  # Mude para False para ver o navegador
        debug=False,
    )
    
    display_products(result)
    
    # Exemplo 2: Busca com CEP específico (opcional)
    # store_id = await get_store_id_by_cep("01310-100")
    # if store_id:
    #     result = await search_pao_acucar_api(
    #         search_term="leite integral",
    #         store_id=store_id,
    #     )
    #     display_products(result)


if __name__ == "__main__":
    asyncio.run(main())