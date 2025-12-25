#!/usr/bin/env python3
"""
Script de teste para o scraper corrigido do Atacadão.
Testa a extração de produtos com os novos seletores.

Uso:
    python test_atacadao_scraper.py [termo_busca]
    
Exemplo:
    python test_atacadao_scraper.py "arroz 5kg"
"""

import asyncio
import sys
import re
from datetime import datetime
from urllib.parse import quote_plus
from dataclasses import dataclass, field
from typing import Optional
from playwright.async_api import async_playwright, Page


# =============================================================================
# CONFIGURAÇÃO (inline para facilitar testes)
# =============================================================================

@dataclass
class RawProduct:
    """Produto coletado antes de processamento."""
    market_id: str
    title: str
    price_raw: str
    search_query: str
    collected_at: datetime
    unit_price_raw: Optional[str] = None
    url: Optional[str] = None
    image_url: Optional[str] = None
    availability_raw: Optional[str] = None
    cep: Optional[str] = None
    extra_data: Optional[dict] = None


ATACADAO_BASE_URL = "https://www.atacadao.com.br"


# =============================================================================
# FUNÇÕES DE EXTRAÇÃO (do novo scraper)
# =============================================================================

def clean_price(price_text: str) -> str:
    """Limpa e normaliza texto de preço."""
    if not price_text:
        return ""
    cleaned = " ".join(price_text.split())
    match = re.search(r'R\$?\s*([\d.,]+)', cleaned)
    if match:
        value = match.group(1)
        if "." in value and "," not in value:
            value = value.replace(".", ",")
        return f"R$ {value}"
    return cleaned


async def extract_products(page: Page, search_query: str) -> list[RawProduct]:
    """Extrai produtos da página usando os novos seletores."""
    products = []
    
    # Aguarda carregamento
    try:
        await page.wait_for_selector("ul.grid, [data-fs-product-listing-results]", timeout=15000)
        await page.wait_for_timeout(2000)
    except Exception as e:
        print(f"⚠️ Timeout aguardando produtos: {e}")
    
    # Scroll para carregar lazy loading
    for _ in range(3):
        await page.evaluate("window.scrollBy(0, window.innerHeight)")
        await page.wait_for_timeout(800)
    await page.evaluate("window.scrollTo(0, 0)")
    await page.wait_for_timeout(500)
    
    # Busca cards de produto
    product_cards = await page.query_selector_all("ul.grid li article.relative")
    
    if not product_cards:
        product_cards = await page.query_selector_all(
            "article:has(section[data-testid='store-product-card-content'])"
        )
    
    if not product_cards:
        product_cards = await page.query_selector_all("li:has(a[data-testid='product-link'])")
    
    print(f"\n📦 Cards encontrados: {len(product_cards)}")
    
    for idx, card in enumerate(product_cards):
        try:
            # TÍTULO
            title = None
            title_elem = await card.query_selector("h3[title]")
            if title_elem:
                title = await title_elem.get_attribute("title")
            if not title:
                h3 = await card.query_selector("h3")
                if h3:
                    title = await h3.inner_text()
            if not title:
                continue
            title = title.strip()
            
            # PREÇO PRINCIPAL
            price_raw = None
            for selector in ["section p.text-lg.font-bold", "p[class*='text-lg'][class*='font-bold']"]:
                elem = await card.query_selector(selector)
                if elem:
                    text = await elem.inner_text()
                    if text and "R$" in text:
                        price_raw = clean_price(text)
                        break
            
            if not price_raw:
                all_text = await card.inner_text()
                match = re.search(r'R\$\s*[\d.,]+', all_text)
                if match:
                    price_raw = clean_price(match.group())
            
            if not price_raw:
                continue
            
            # PREÇO UNITÁRIO
            unit_price_raw = None
            try:
                content = await card.inner_text()
                match = re.search(r'ou\s*R\$\s*([\d.,]+)\s*/\s*cada', content, re.IGNORECASE)
                if match:
                    unit_price_raw = f"R$ {match.group(1)}"
            except:
                pass
            
            # QUANTIDADE MÍNIMA
            bulk_quantity = None
            try:
                content = await card.inner_text()
                match = re.search(r'A partir de\s*(\d+)\s*unid\.?', content, re.IGNORECASE)
                if match:
                    bulk_quantity = f"A partir de {match.group(1)} unid."
            except:
                pass
            
            # DESCONTO
            discount = None
            try:
                badge = await card.query_selector("div[data-test='discount-badge']")
                if badge:
                    discount = await badge.inner_text()
            except:
                pass
            
            # URL
            product_url = ATACADAO_BASE_URL
            link = await card.query_selector("a[data-testid='product-link']")
            if link:
                href = await link.get_attribute("href")
                if href:
                    product_url = f"{ATACADAO_BASE_URL}{href}" if href.startswith("/") else href
            
            # IMAGEM
            image_url = None
            img = await card.query_selector("div[data-product-card-image] img, img")
            if img:
                srcset = await img.get_attribute("srcset")
                if srcset:
                    urls = re.findall(r'(https?://[^\s]+)', srcset)
                    if urls:
                        image_url = urls[-1]
                if not image_url:
                    image_url = await img.get_attribute("src")
            
            product = RawProduct(
                market_id="atacadao",
                title=title,
                price_raw=price_raw,
                unit_price_raw=unit_price_raw,
                url=product_url,
                image_url=image_url,
                availability_raw="Disponível",
                search_query=search_query,
                collected_at=datetime.now(),
                extra_data={
                    "bulk_quantity": bulk_quantity,
                    "discount": discount,
                    "position": idx + 1,
                },
            )
            products.append(product)
            
        except Exception as e:
            print(f"⚠️ Erro no card {idx}: {e}")
            continue
    
    return products


# =============================================================================
# FUNÇÃO PRINCIPAL DE TESTE
# =============================================================================

async def test_scraper(search_term: str = "arroz 5kg"):
    """Executa teste completo do scraper."""
    
    print("=" * 70)
    print("🧪 TESTE DO SCRAPER CORRIGIDO DO ATACADÃO")
    print("=" * 70)
    print(f"📝 Termo de busca: '{search_term}'")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,  # Mude para True em produção
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ]
        )
        
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            locale="pt-BR",
        )
        
        # Script para esconder automação
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)
        
        page = await context.new_page()
        
        try:
            # Monta URL de busca
            url = f"{ATACADAO_BASE_URL}/s?q={quote_plus(search_term)}&sort=score_desc&page=0"
            print(f"🔗 URL: {url}")
            print("-" * 70)
            
            # Navega
            print("⏳ Navegando...")
            response = await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            print(f"📡 Status HTTP: {response.status}")
            
            # Extrai produtos
            print("🔍 Extraindo produtos...")
            products = await extract_products(page, search_term)
            
            # Exibe resultados
            print("\n" + "=" * 70)
            print(f"✅ PRODUTOS EXTRAÍDOS: {len(products)}")
            print("=" * 70)
            
            for i, p in enumerate(products[:10], 1):  # Mostra até 10 produtos
                print(f"\n📦 Produto {i}:")
                print(f"   📌 Título: {p.title[:60]}...")
                print(f"   💰 Preço Atacado: {p.price_raw}")
                if p.unit_price_raw:
                    print(f"   💵 Preço Unitário: {p.unit_price_raw}")
                if p.extra_data:
                    if p.extra_data.get("bulk_quantity"):
                        print(f"   📊 Qtd. Mínima: {p.extra_data['bulk_quantity']}")
                    if p.extra_data.get("discount"):
                        print(f"   🏷️ Desconto: {p.extra_data['discount']}")
                print(f"   🔗 URL: {p.url[:70]}...")
            
            if len(products) > 10:
                print(f"\n... e mais {len(products) - 10} produtos")
            
            # Estatísticas
            print("\n" + "=" * 70)
            print("📊 ESTATÍSTICAS")
            print("=" * 70)
            
            with_unit_price = sum(1 for p in products if p.unit_price_raw)
            with_discount = sum(1 for p in products if p.extra_data and p.extra_data.get("discount"))
            with_bulk = sum(1 for p in products if p.extra_data and p.extra_data.get("bulk_quantity"))
            
            print(f"   Total de produtos: {len(products)}")
            print(f"   Com preço unitário: {with_unit_price} ({100*with_unit_price/max(1,len(products)):.0f}%)")
            print(f"   Com desconto: {with_discount} ({100*with_discount/max(1,len(products)):.0f}%)")
            print(f"   Com qtd. mínima: {with_bulk} ({100*with_bulk/max(1,len(products)):.0f}%)")
            
            return products
            
        except Exception as e:
            print(f"\n❌ ERRO: {e}")
            import traceback
            traceback.print_exc()
            return []
            
        finally:
            await browser.close()


# =============================================================================
# EXECUÇÃO
# =============================================================================

if __name__ == "__main__":
    search_term = sys.argv[1] if len(sys.argv) > 1 else "arroz 5kg"
    
    products = asyncio.run(test_scraper(search_term))
    
    print("\n" + "=" * 70)
    if products:
        print(f"✅ SUCESSO! {len(products)} produtos extraídos.")
    else:
        print("❌ Nenhum produto extraído. Verifique os seletores.")
    print("=" * 70)