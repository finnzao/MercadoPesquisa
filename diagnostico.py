"""
Script de Diagnóstico para Scrapers de Supermercados
====================================================

Este script testa cada mercado individualmente e gera:
- Screenshots de cada página
- HTML completo das páginas
- Logs detalhados
- Relatório de diagnóstico

Uso:
    python diagnostico.py

Os arquivos serão salvos em: ./diagnostico/
"""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

# Adiciona o diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent))

from playwright.async_api import async_playwright, Page, Browser


# =============================================================================
# CONFIGURAÇÃO
# =============================================================================

# Termo de busca para teste
SEARCH_TERM = "arroz 5kg"

# Diretório para salvar diagnósticos
DIAGNOSTICO_DIR = Path("diagnostico")

# URLs de busca CORRETAS (atualizadas)
MARKETS = {
    "carrefour": {
        "name": "Carrefour Mercado",
        "search_url": f"https://mercado.carrefour.com.br/busca/{quote(SEARCH_TERM)}",
        "home_url": "https://mercado.carrefour.com.br",
    },
    "atacadao": {
        "name": "Atacadão",
        "search_url": f"https://www.atacadao.com.br/s?q={quote(SEARCH_TERM)}&sort=score_desc&page=0",
        "home_url": "https://www.atacadao.com.br",
    },
    "pao_acucar": {
        "name": "Pão de Açúcar",
        "search_url": f"https://www.paodeacucar.com/busca?terms={quote(SEARCH_TERM)}",
        "home_url": "https://www.paodeacucar.com",
    },
    "extra": {
        "name": "Extra",
        "search_url": f"https://www.extra.com.br/busca?terms={quote(SEARCH_TERM)}",
        "home_url": "https://www.extra.com.br",
    },
}

# User Agent realista
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


# =============================================================================
# FUNÇÕES DE DIAGNÓSTICO
# =============================================================================

async def setup_browser():
    """Configura o browser com opções anti-detecção."""
    playwright = await async_playwright().start()
    
    browser = await playwright.chromium.launch(
        headless=False,  # VISÍVEL para debug!
        args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--window-size=1920,1080",
        ],
    )
    
    context = await browser.new_context(
        user_agent=USER_AGENT,
        viewport={"width": 1920, "height": 1080},
        locale="pt-BR",
        timezone_id="America/Sao_Paulo",
        extra_http_headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        },
    )
    
    # Script anti-detecção
    await context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        window.chrome = { runtime: {} };
    """)
    
    return playwright, browser, context


async def diagnose_market(context, market_id: str, market_info: dict, output_dir: Path) -> dict:
    """
    Diagnostica um mercado específico.
    
    Returns:
        dict com resultados do diagnóstico
    """
    result = {
        "market_id": market_id,
        "name": market_info["name"],
        "search_url": market_info["search_url"],
        "status": "unknown",
        "http_status": None,
        "blocked": False,
        "block_reason": None,
        "has_products": False,
        "product_count": 0,
        "errors": [],
        "screenshots": [],
        "html_files": [],
    }
    
    print(f"\n{'='*60}")
    print(f"🔍 Testando: {market_info['name']}")
    print(f"   URL: {market_info['search_url']}")
    print(f"{'='*60}")
    
    page = await context.new_page()
    
    try:
        # 1. Primeiro acessa a home (para pegar cookies)
        print(f"\n📍 Acessando home: {market_info['home_url']}")
        await page.goto(market_info["home_url"], wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        
        # Screenshot da home
        home_screenshot = output_dir / f"{market_id}_01_home.png"
        await page.screenshot(path=str(home_screenshot), full_page=False)
        result["screenshots"].append(str(home_screenshot))
        print(f"   ✅ Screenshot salvo: {home_screenshot.name}")
        
        # 2. Navega para busca
        print(f"\n📍 Acessando busca: {market_info['search_url']}")
        response = await page.goto(
            market_info["search_url"],
            wait_until="domcontentloaded",
            timeout=30000
        )
        
        result["http_status"] = response.status if response else None
        print(f"   HTTP Status: {result['http_status']}")
        
        # Aguarda carregamento
        await page.wait_for_timeout(5000)
        
        # 3. Screenshot da página de busca
        search_screenshot = output_dir / f"{market_id}_02_search.png"
        await page.screenshot(path=str(search_screenshot), full_page=True)
        result["screenshots"].append(str(search_screenshot))
        print(f"   ✅ Screenshot salvo: {search_screenshot.name}")
        
        # 4. Salva HTML completo
        html_content = await page.content()
        html_file = output_dir / f"{market_id}_page.html"
        html_file.write_text(html_content, encoding="utf-8")
        result["html_files"].append(str(html_file))
        print(f"   ✅ HTML salvo: {html_file.name}")
        
        # 5. Verifica bloqueios
        html_lower = html_content.lower()
        
        block_checks = [
            ("captcha", "CAPTCHA detectado"),
            ("robot", "Verificação de robô"),
            ("cloudflare", "Cloudflare proteção"),
            ("blocked", "Acesso bloqueado"),
            ("access denied", "Acesso negado"),
            ("acesso negado", "Acesso negado"),
            ("verificação", "Verificação necessária"),
            ("rate limit", "Rate limit"),
            ("too many requests", "Muitas requisições"),
        ]
        
        for indicator, reason in block_checks:
            if indicator in html_lower:
                # Verifica falso positivo
                if indicator == "robot" and "robô aspirador" in html_lower:
                    continue
                result["blocked"] = True
                result["block_reason"] = reason
                print(f"   ⚠️  BLOQUEIO DETECTADO: {reason}")
                break
        
        # 6. Tenta encontrar produtos
        product_selectors = [
            "div[class*='product']",
            "article[class*='product']",
            "div[data-testid*='product']",
            "a[class*='product']",
            "div[class*='ProductCard']",
            "div[class*='shelf']",
            "div[class*='item']",
            "li[class*='product']",
        ]
        
        for selector in product_selectors:
            try:
                products = await page.query_selector_all(selector)
                if products and len(products) > 0:
                    result["has_products"] = True
                    result["product_count"] = len(products)
                    print(f"   ✅ Produtos encontrados: {len(products)} (seletor: {selector})")
                    break
            except Exception:
                continue
        
        if not result["has_products"]:
            print(f"   ❌ Nenhum produto encontrado com seletores padrão")
        
        # 7. Lista todos os elementos principais da página
        print(f"\n   📋 Analisando estrutura da página...")
        
        # Encontra divs e classes principais
        main_elements = await page.evaluate("""
            () => {
                const elements = document.querySelectorAll('div[class], article, section, main');
                const classes = new Set();
                elements.forEach(el => {
                    if (el.className && typeof el.className === 'string') {
                        el.className.split(' ').forEach(c => {
                            if (c.length > 3 && c.length < 50) {
                                classes.add(c);
                            }
                        });
                    }
                });
                return Array.from(classes).slice(0, 50);
            }
        """)
        
        # Salva classes encontradas
        classes_file = output_dir / f"{market_id}_classes.txt"
        classes_file.write_text("\n".join(main_elements), encoding="utf-8")
        print(f"   ✅ Classes CSS salvas: {classes_file.name}")
        
        # 8. Define status final
        if result["blocked"]:
            result["status"] = "blocked"
        elif result["http_status"] and result["http_status"] >= 400:
            result["status"] = "http_error"
        elif result["has_products"]:
            result["status"] = "success"
        else:
            result["status"] = "no_products"
        
    except Exception as e:
        result["status"] = "error"
        result["errors"].append(str(e))
        print(f"   ❌ ERRO: {e}")
        
        # Tenta salvar screenshot do erro
        try:
            error_screenshot = output_dir / f"{market_id}_error.png"
            await page.screenshot(path=str(error_screenshot))
            result["screenshots"].append(str(error_screenshot))
        except:
            pass
    
    finally:
        await page.close()
    
    return result


async def run_diagnostics():
    """Executa diagnóstico completo."""
    
    print("\n" + "="*70)
    print("🔬 DIAGNÓSTICO DE SCRAPERS DE SUPERMERCADOS")
    print("="*70)
    print(f"Data/Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Termo de busca: '{SEARCH_TERM}'")
    
    # Cria diretório de saída
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = DIAGNOSTICO_DIR / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Diretório de saída: {output_dir}")
    
    # Inicia browser
    print("\n🌐 Iniciando browser (modo VISÍVEL para debug)...")
    playwright, browser, context = await setup_browser()
    
    results = []
    
    try:
        for market_id, market_info in MARKETS.items():
            result = await diagnose_market(context, market_id, market_info, output_dir)
            results.append(result)
            
            # Pausa entre mercados
            await asyncio.sleep(2)
    
    finally:
        await context.close()
        await browser.close()
        await playwright.stop()
    
    # Gera relatório
    report = generate_report(results, output_dir)
    
    # Salva relatório
    report_file = output_dir / "RELATORIO.txt"
    report_file.write_text(report, encoding="utf-8")
    
    print("\n" + report)
    print(f"\n📁 Todos os arquivos salvos em: {output_dir.absolute()}")
    
    return results


def generate_report(results: list, output_dir: Path) -> str:
    """Gera relatório de diagnóstico."""
    
    lines = [
        "="*70,
        "📊 RELATÓRIO DE DIAGNÓSTICO",
        "="*70,
        f"Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Termo testado: '{SEARCH_TERM}'",
        "",
        "-"*70,
        "RESUMO",
        "-"*70,
    ]
    
    status_icons = {
        "success": "✅",
        "blocked": "🚫",
        "http_error": "❌",
        "no_products": "⚠️",
        "error": "💥",
        "unknown": "❓",
    }
    
    for r in results:
        icon = status_icons.get(r["status"], "❓")
        lines.append(f"{icon} {r['name']}: {r['status'].upper()}")
        if r["blocked"]:
            lines.append(f"   Motivo: {r['block_reason']}")
        if r["has_products"]:
            lines.append(f"   Produtos: {r['product_count']}")
        if r["http_status"]:
            lines.append(f"   HTTP: {r['http_status']}")
    
    lines.extend([
        "",
        "-"*70,
        "DETALHES POR MERCADO",
        "-"*70,
    ])
    
    for r in results:
        lines.extend([
            "",
            f"### {r['name']} ({r['market_id']}) ###",
            f"Status: {r['status']}",
            f"URL: {r['search_url']}",
            f"HTTP Status: {r['http_status']}",
            f"Bloqueado: {'Sim - ' + r['block_reason'] if r['blocked'] else 'Não'}",
            f"Produtos encontrados: {r['product_count']}",
            f"Screenshots: {', '.join([Path(s).name for s in r['screenshots']])}",
            f"HTML: {', '.join([Path(s).name for s in r['html_files']])}",
        ])
        
        if r["errors"]:
            lines.append(f"Erros: {'; '.join(r['errors'])}")
    
    lines.extend([
        "",
        "-"*70,
        "PRÓXIMOS PASSOS",
        "-"*70,
        "",
        "1. Abra os screenshots para ver o que aparece na tela",
        "2. Abra os arquivos HTML no browser para analisar a estrutura",
        "3. Use os arquivos *_classes.txt para identificar seletores corretos",
        "",
        "Se todos estão BLOCKED:",
        "- Os sites estão usando proteção anti-bot",
        "- Pode ser necessário usar proxy rotativo",
        "- Ou acessar via API oficial (se disponível)",
        "",
        "-"*70,
    ])
    
    return "\n".join(lines)


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    print("\n⚠️  O browser será aberto em modo VISÍVEL para você ver o que acontece!")
    print("    Não feche o browser manualmente - aguarde o script terminar.\n")
    
    asyncio.run(run_diagnostics())