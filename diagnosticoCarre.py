"""
Teste do scraper do Carrefour após correções.
Execute: python teste_carrefour.py
"""

import asyncio
from urllib.parse import quote
from playwright.async_api import async_playwright
from datetime import datetime


async def testar_carrefour():
    """Testa a extração de produtos do Carrefour."""
    
    termo = "arroz 5kg"
    url = f"https://mercado.carrefour.com.br/busca/{quote(termo)}"
    
    print("=" * 70)
    print("TESTE DO SCRAPER CARREFOUR")
    print("=" * 70)
    print(f"Termo: {termo}")
    print(f"URL: {url}")
    print()
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="pt-BR",
        )
        
        page = await context.new_page()
        
        print("Navegando...")
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        
        # Scroll para carregar
        print("Carregando produtos (scroll)...")
        for _ in range(5):
            await page.evaluate("window.scrollBy(0, 600)")
            await page.wait_for_timeout(300)
        
        # Busca cards
        cards = await page.query_selector_all('a[data-testid="search-product-card"]')
        print(f"\nCards encontrados: {len(cards)}")
        print("-" * 70)
        
        produtos_extraidos = []
        
        for i, card in enumerate(cards[:10]):  # Limita a 10 para teste
            try:
                # Título
                h2 = await card.query_selector("h2")
                titulo = await h2.inner_text() if h2 else None
                
                if not titulo:
                    img = await card.query_selector("img")
                    titulo = await img.get_attribute("alt") if img else "N/A"
                
                # Preço
                preco = None
                price_el = await card.query_selector("span.text-blue-royal.font-bold")
                if price_el:
                    preco = await price_el.inner_text()
                else:
                    # Fallback: busca span com R$
                    spans = await card.query_selector_all("span")
                    for span in spans:
                        text = await span.inner_text()
                        if "R$" in text:
                            preco = text
                            break
                
                # Link
                href = await card.get_attribute("href")
                if href and href.startswith("/"):
                    href = f"https://mercado.carrefour.com.br{href}"
                
                # Imagem
                img = await card.query_selector("img")
                img_src = await img.get_attribute("src") if img else None
                
                produto = {
                    "titulo": titulo.strip() if titulo else "N/A",
                    "preco": preco.strip() if preco else "N/A",
                    "url": href[:60] + "..." if href and len(href) > 60 else href,
                    "imagem": "✓" if img_src else "✗",
                }
                
                produtos_extraidos.append(produto)
                
                print(f"\n[Produto {i+1}]")
                print(f"  Título: {produto['titulo'][:50]}...")
                print(f"  Preço:  {produto['preco']}")
                print(f"  URL:    {produto['url']}")
                print(f"  Imagem: {produto['imagem']}")
                
            except Exception as e:
                print(f"\n[Produto {i+1}] ERRO: {e}")
        
        await browser.close()
    
    # Resumo
    print("\n" + "=" * 70)
    print("RESUMO")
    print("=" * 70)
    
    total = len(produtos_extraidos)
    com_preco = sum(1 for p in produtos_extraidos if p['preco'] != 'N/A')
    com_titulo = sum(1 for p in produtos_extraidos if p['titulo'] != 'N/A')
    
    print(f"Total de produtos extraídos: {total}")
    print(f"Com preço válido: {com_preco}")
    print(f"Com título válido: {com_titulo}")
    
    if total > 0 and com_preco == total:
        print("\n✓ SUCESSO! Todos os produtos têm preço.")
    elif com_preco > 0:
        print(f"\n⚠ PARCIAL: {com_preco}/{total} produtos com preço.")
    else:
        print("\n✗ FALHA: Nenhum produto com preço extraído.")
    
    # Lista alguns preços para validação
    print("\nPreços encontrados:")
    for p in produtos_extraidos[:5]:
        print(f"  • {p['preco']} - {p['titulo'][:40]}...")


if __name__ == "__main__":
    asyncio.run(testar_carrefour())