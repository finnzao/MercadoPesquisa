#!/usr/bin/env python3
"""
Script de teste para o scraper do Pão de Açúcar.
Testa a extração de produtos usando Playwright.

Uso:
    python test_paodeacucar_scraper.py
    python test_paodeacucar_scraper.py "feijão 1kg"
    python test_paodeacucar_scraper.py "arroz 5kg" --cep 01310-100
    python test_paodeacucar_scraper.py --debug
"""

import asyncio
import argparse
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

# Adiciona diretório do projeto ao path
sys.path.insert(0, str(Path(__file__).parent))


async def test_scraper(
    search_term: str = "arroz 5kg",
    cep: str = "01310-100",
    headless: bool = False,
    debug: bool = True,
):
    """
    Testa o scraper do Pão de Açúcar.
    
    Args:
        search_term: Termo de busca
        cep: CEP para configurar localização
        headless: Se True, roda sem interface gráfica
        debug: Se True, salva screenshots e HTML
    """
    from playwright.async_api import async_playwright
    import re
    
    print("=" * 70)
    print("TESTE DO SCRAPER PÃO DE AÇÚCAR")
    print("=" * 70)
    print(f"\nTermo de busca: {search_term}")
    print(f"CEP: {cep}")
    print(f"Headless: {headless}")
    print(f"Debug: {debug}")
    
    # Monta URL de busca
    encoded_query = quote_plus(search_term)
    search_url = f"https://www.paodeacucar.com/busca?terms={encoded_query}"
    print(f"\nURL: {search_url}")
    
    async with async_playwright() as p:
        print("\n[1/6] Iniciando navegador...")
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
            # Navega para a página de busca
            print("\n[2/6] Navegando para página de busca...")
            await page.goto(search_url, wait_until="domcontentloaded")
            
            # Fecha modal de CEP se aparecer
            print("\n[3/6] Verificando modal de CEP...")
            await page.wait_for_timeout(3000)
            
            # Tenta fechar modal se existir
            try:
                close_btn = await page.query_selector("button[aria-label*='fechar'], button[class*='close']")
                if close_btn:
                    await close_btn.click()
                    print("   Modal de CEP fechado")
                    await page.wait_for_timeout(1000)
            except:
                pass
            
            # Faz scroll para carregar lazy loading
            print("\n[4/6] Fazendo scroll para carregar produtos...")
            for i in range(5):
                await page.evaluate("window.scrollBy(0, window.innerHeight)")
                await page.wait_for_timeout(800)
            await page.evaluate("window.scrollTo(0, 0)")
            await page.wait_for_timeout(1000)
            
            # Extrai produtos
            print("\n[5/6] Extraindo produtos...")
            
            # Lista de seletores para tentar
            selectors = [
                ("div.CardStyled-sc-20azeh-0", "Seletor principal"),
                ("div[class*='CardStyled-sc-20azeh']", "Seletor flexível"),
                ("div.MuiGrid-item div[class*='Card-sc']", "Via MuiGrid"),
                ("div:has(p[class*='PriceValue']):has(a[href*='/produto/'])", "Via preço+link"),
            ]
            
            product_cards = []
            for selector, desc in selectors:
                product_cards = await page.query_selector_all(selector)
                if product_cards:
                    print(f"   ✓ {desc}: {len(product_cards)} cards encontrados")
                    break
                print(f"   ○ {desc}: 0 cards")
            
            if not product_cards:
                print("\n⚠️ Nenhum produto encontrado com seletores padrão")
                print("   Salvando debug para análise...")
                
                if debug:
                    await page.screenshot(path="paodeacucar_test_debug.png", full_page=True)
                    html = await page.content()
                    with open("paodeacucar_test_debug.html", "w", encoding="utf-8") as f:
                        f.write(html)
                    print("   Salvos: paodeacucar_test_debug.png e paodeacucar_test_debug.html")
                
                await browser.close()
                return
            
            # Extrai dados de cada produto
            print(f"\n[6/6] Processando {len(product_cards)} produtos...")
            products = []
            
            for idx, card in enumerate(product_cards[:20]):  # Limita a 20 para teste
                try:
                    # Título
                    title = None
                    for sel in ["a.Title-sc-20azeh-10", "a[class*='Title-sc']", "img"]:
                        elem = await card.query_selector(sel)
                        if elem:
                            if sel == "img":
                                title = await elem.get_attribute("alt")
                            else:
                                title = await elem.inner_text()
                            if title and title.strip():
                                title = title.strip()
                                break
                    
                    # Preço
                    price = None
                    for sel in ["p.PriceValue-sc-20azeh-4", "p[class*='PriceValue']"]:
                        elem = await card.query_selector(sel)
                        if elem:
                            price = await elem.inner_text()
                            if price and "R$" in price:
                                price = price.strip()
                                break
                    
                    # URL
                    url = None
                    link = await card.query_selector("a[href*='/produto/']")
                    if link:
                        href = await link.get_attribute("href")
                        if href:
                            url = f"https://www.paodeacucar.com{href}" if href.startswith("/") else href
                    
                    # Imagem
                    image_url = None
                    img = await card.query_selector("img")
                    if img:
                        image_url = await img.get_attribute("src")
                    
                    if title and price:
                        products.append({
                            "position": idx + 1,
                            "title": title,
                            "price": price,
                            "url": url,
                            "image_url": image_url[:50] + "..." if image_url and len(image_url) > 50 else image_url,
                        })
                
                except Exception as e:
                    if debug:
                        print(f"   Erro no produto {idx + 1}: {e}")
                    continue
            
            # Exibe resultados
            print("\n" + "=" * 70)
            print("RESULTADOS")
            print("=" * 70)
            
            if products:
                print(f"\n✅ {len(products)} produtos extraídos com sucesso!\n")
                
                for p in products[:10]:  # Mostra primeiros 10
                    print(f"[{p['position']}] {p['title'][:60]}...")
                    print(f"    Preço: {p['price']}")
                    if p['url']:
                        print(f"    URL: {p['url'][:80]}...")
                    print()
                
                if len(products) > 10:
                    print(f"... e mais {len(products) - 10} produtos")
                
                # Estatísticas de preço
                prices = []
                for p in products:
                    match = re.search(r'R\$\s*([\d.,]+)', p['price'])
                    if match:
                        value = match.group(1).replace(".", "").replace(",", ".")
                        try:
                            prices.append(float(value))
                        except:
                            pass
                
                if prices:
                    print("\n" + "-" * 40)
                    print("ESTATÍSTICAS DE PREÇO")
                    print("-" * 40)
                    print(f"Menor preço: R$ {min(prices):.2f}")
                    print(f"Maior preço: R$ {max(prices):.2f}")
                    print(f"Preço médio: R$ {sum(prices)/len(prices):.2f}")
            else:
                print("\n⚠️ Nenhum produto foi extraído com sucesso")
                print("   Os cards foram encontrados mas os dados não puderam ser extraídos")
            
            # Salva debug se solicitado
            if debug:
                await page.screenshot(path="paodeacucar_test_result.png", full_page=True)
                print(f"\nScreenshot salvo: paodeacucar_test_result.png")
        
        except Exception as e:
            print(f"\n❌ Erro durante o teste: {e}")
            import traceback
            traceback.print_exc()
            
            if debug:
                await page.screenshot(path="paodeacucar_test_error.png")
                html = await page.content()
                with open("paodeacucar_test_error.html", "w", encoding="utf-8") as f:
                    f.write(html)
                print("\nDebug salvo: paodeacucar_test_error.png e .html")
        
        finally:
            await browser.close()
    
    print("\n" + "=" * 70)
    print("TESTE CONCLUÍDO")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="Testa o scraper do Pão de Açúcar"
    )
    parser.add_argument(
        "termo",
        nargs="?",
        default="arroz 5kg",
        help="Termo de busca (padrão: 'arroz 5kg')"
    )
    parser.add_argument(
        "--cep",
        default="01310-100",
        help="CEP para configurar localização (padrão: 01310-100 - Av. Paulista)"
    )
    parser.add_argument(
        "--visible",
        action="store_true",
        help="Mostra o navegador (não headless)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Salva screenshots e HTML para debug"
    )
    
    args = parser.parse_args()
    
    asyncio.run(test_scraper(
        search_term=args.termo,
        cep=args.cep,
        headless=not args.visible,
        debug=args.debug,
    ))


if __name__ == "__main__":
    main()