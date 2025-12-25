import asyncio
import sys
from urllib.parse import quote, quote_plus, urlencode
from playwright.async_api import async_playwright


async def diagnosticar_pao_de_acucar():
    """Diagnóstico completo do Pão de Açúcar."""
    
    termo = "arroz 5kg"
    
    print("=" * 70)
    print("DIAGNÓSTICO DO PÃO DE AÇÚCAR")
    print("=" * 70)
    
    # PARTE 1: Entendendo URL Encoding
    print("\n" + "=" * 70)
    print("PARTE 1: URL ENCODING")
    print("=" * 70)
    
    print(f"\nTermo original: '{termo}'")
    print()
    
    # Pão de Açúcar usa: /busca?terms=TERMO
    url_com_plus = f"https://www.paodeacucar.com/busca?terms={quote_plus(termo)}"
    url_com_percent = f"https://www.paodeacucar.com/busca?terms={quote(termo)}"
    
    print(f"URL com quote_plus (+):  {url_com_plus}")
    print(f"URL com quote (%20):     {url_com_percent}")
    
    # PARTE 2: Testando qual URL funciona
    print("\n" + "=" * 70)
    print("PARTE 2: TESTANDO URLs")
    print("=" * 70)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="pt-BR",
        )
        
        # Teste 1: URL com +
        print(f"\n[TESTE 1] URL com '+': ")
        print(f"   {url_com_plus}")
        page1 = await context.new_page()
        try:
            response1 = await page1.goto(url_com_plus, wait_until="domcontentloaded", timeout=30000)
            await page1.wait_for_timeout(5000)
            
            content1 = await page1.content()
            tem_produtos1 = "product" in content1.lower() or "price" in content1.lower()
            tem_erro1 = "não encontrado" in content1.lower() or "nenhum resultado" in content1.lower()
            
            # Tenta contar elementos de produto
            cards1 = await page1.query_selector_all("[class*='product'], [data-testid*='product'], article")
            
            print(f"   Status HTTP: {response1.status}")
            print(f"   Tem indicadores de produto: {tem_produtos1}")
            print(f"   Tem mensagem de erro: {tem_erro1}")
            print(f"   Elementos encontrados: {len(cards1)}")
            
        except Exception as e:
            erro_str = str(e)
            print(f"   ERRO: {erro_str[:200]}")
            if "ERR_TUNNEL_CONNECTION_FAILED" in erro_str or "net::" in erro_str:
                print("\n   ⚠️  ERRO DE CONEXÃO DETECTADO!")
                print("   O domínio paodeacucar.com pode estar bloqueado no seu ambiente.")
                print("   Execute este script localmente na sua máquina.")
        finally:
            await page1.close()
        
        # Teste 2: URL com %20
        print(f"\n[TESTE 2] URL com '%20': ")
        print(f"   {url_com_percent}")
        page2 = await context.new_page()
        page2_ok = False
        try:
            response2 = await page2.goto(url_com_percent, wait_until="domcontentloaded", timeout=30000)
            await page2.wait_for_timeout(5000)
            
            content2 = await page2.content()
            tem_produtos2 = "product" in content2.lower() or "price" in content2.lower()
            tem_erro2 = "não encontrado" in content2.lower() or "nenhum resultado" in content2.lower()
            
            cards2 = await page2.query_selector_all("[class*='product'], [data-testid*='product'], article")
            
            print(f"   Status HTTP: {response2.status}")
            print(f"   Tem indicadores de produto: {tem_produtos2}")
            print(f"   Tem mensagem de erro: {tem_erro2}")
            print(f"   Elementos encontrados: {len(cards2)}")
            page2_ok = True
            
        except Exception as e:
            erro_str = str(e)
            print(f"   ERRO: {erro_str[:200]}")
            if "ERR_TUNNEL_CONNECTION_FAILED" in erro_str or "net::" in erro_str:
                print("\n" + "=" * 70)
                print("⚠️  NÃO FOI POSSÍVEL CONECTAR AO PÃO DE AÇÚCAR")
                print("=" * 70)
                print("""
O domínio paodeacucar.com não está acessível neste ambiente.

Para executar o diagnóstico, rode este script na sua máquina local:

    1. Instale as dependências:
       pip install playwright
       playwright install chromium

    2. Execute o script:
       python diagnosticoPaodeAcucar.py

    3. Envie a saída de volta para análise.
""")
                await page2.close()
                await browser.close()
                return
        
        # Usa a página que funcionou melhor para continuar
        if not page2_ok:
            print("\nNenhuma URL funcionou. Encerrando diagnóstico.")
            await page2.close()
            await browser.close()
            return
            
        page = page2
        

        # PARTE 3: Analisando estrutura HTML

        print("\n" + "=" * 70)
        print("PARTE 3: BUSCANDO DATA-TESTID")
        print("=" * 70)
        
        # Scroll para carregar mais produtos (lazy loading)
        print("\nFazendo scroll para carregar produtos...")
        for i in range(5):
            await page.evaluate("window.scrollBy(0, 800)")
            await page.wait_for_timeout(500)
        
        # Busca todos os data-testid na página
        testids = await page.evaluate("""
            () => {
                const elements = document.querySelectorAll('[data-testid]');
                const testids = {};
                elements.forEach(el => {
                    const id = el.getAttribute('data-testid');
                    testids[id] = (testids[id] || 0) + 1;
                });
                return testids;
            }
        """)
        
        print("\ndata-testid encontrados:")
        for testid, count in sorted(testids.items(), key=lambda x: -x[1])[:25]:
            print(f"   {count:3}x  {testid}")
        

        # PARTE 4: Testando seletores de container

        print("\n" + "=" * 70)
        print("PARTE 4: TESTANDO SELETORES DE CONTAINER")
        print("=" * 70)
        
        seletores_container = [
            # Por data-testid (específicos do Pão de Açúcar / GPA)
            "[data-testid='product-card']",
            "[data-testid='productCard']",
            "[data-testid='product-summary']",
            "[data-testid='search-product-card']",
            "[data-testid='shelf-product']",
            "[data-testid='store-product-card']",
            "[data-testid='product-item']",
            
            # Por classes comuns
            "article[class*='product']",
            "div[class*='product-card']",
            "div[class*='productCard']",
            "div[class*='ProductCard']",
            "div[class*='product-item']",
            "a[class*='product']",
            "li[class*='product']",
            
            # Por estrutura de grid/lista
            "ul[class*='product'] > li",
            "div[class*='shelf'] > div",
            "div[class*='grid'] article",
            "section article",
            
            # Links de produto
            "a[href*='/p/']",
            "a[href*='/produto/']",
            "a[href*='/p?']",
            
            # VTEX (plataforma usada por muitos e-commerces BR)
            "[class*='vtex-product-summary']",
            "[class*='vtex-search-result']",
            "[class*='vtex']",
            
            # Outros padrões
            "[class*='card'][class*='product']",
            "[class*='item'][class*='product']",
        ]
        
        print("\nTestando seletores:")
        melhor_seletor = None
        melhor_count = 0
        
        for seletor in seletores_container:
            try:
                elementos = await page.query_selector_all(seletor)
                count = len(elementos)
                if count > 0:
                    # Verifica se tem preço
                    html = await elementos[0].evaluate("el => el.outerHTML")
                    tem_preco = "R$" in html or "price" in html.lower()
                    
                    status = "✓" if tem_preco else "○"
                    print(f"   {status} '{seletor}' → {count} elementos, tem_preço={tem_preco}")
                    
                    if tem_preco and count > melhor_count and count < 100:
                        melhor_count = count
                        melhor_seletor = seletor
            except Exception as e:
                pass
        
        if melhor_seletor:
            print(f"\n   MELHOR SELETOR: '{melhor_seletor}' com {melhor_count} elementos")
        

        # PARTE 5: Analisando estrutura de um produto

        print("\n" + "=" * 70)
        print("PARTE 5: ESTRUTURA DE UM PRODUTO")
        print("=" * 70)
        
        # Tenta encontrar links de produto
        links_produto = await page.query_selector_all("a[href*='/p']")
        print(f"\nLinks de produto (href contém '/p'): {len(links_produto)}")
        
        if links_produto and len(links_produto) > 0:
            primeiro = links_produto[0]
            
            # Pega o href
            href = await primeiro.get_attribute("href")
            print(f"Primeiro link: {href}")
            
            # Analisa hierarquia
            parent_info = await primeiro.evaluate("""
                el => {
                    const info = [];
                    let current = el;
                    for (let i = 0; i < 10 && current; i++) {
                        const html = current.outerHTML;
                        info.push({
                            tag: current.tagName,
                            classes: current.className ? current.className.substring(0, 100) : '',
                            dataTestId: current.getAttribute('data-testid'),
                            temPreco: html.includes('R$'),
                            tamanhoHtml: html.length,
                        });
                        current = current.parentElement;
                    }
                    return info;
                }
            """)
            
            print("\nHierarquia (do link até os pais):")
            for i, info in enumerate(parent_info):
                indent = "  " * i
                testid = f" [data-testid='{info['dataTestId']}']" if info['dataTestId'] else ""
                preco = " 💰" if info['temPreco'] else ""
                print(f"{indent}<{info['tag']}> class='{info['classes'][:60]}'{testid}{preco}")
        

        # PARTE 6: Buscando elementos com preço

        print("\n" + "=" * 70)
        print("PARTE 6: ELEMENTOS COM PREÇO (R$)")
        print("=" * 70)
        
        # Busca elementos que contém R$
        elementos_preco = await page.evaluate("""
            () => {
                const results = [];
                const walk = document.createTreeWalker(
                    document.body,
                    NodeFilter.SHOW_TEXT,
                    null,
                    false
                );
                
                let node;
                while (node = walk.nextNode()) {
                    if (node.textContent.includes('R$')) {
                        const parent = node.parentElement;
                        if (parent) {
                            results.push({
                                texto: node.textContent.trim().substring(0, 50),
                                tag: parent.tagName,
                                classes: parent.className ? parent.className.substring(0, 80) : '',
                                dataTestId: parent.getAttribute('data-testid'),
                            });
                        }
                    }
                }
                return results.slice(0, 15);
            }
        """)
        
        print("\nElementos que contém 'R$':")
        for el in elementos_preco:
            testid = f" [data-testid='{el['dataTestId']}']" if el['dataTestId'] else ""
            print(f"   <{el['tag']}> class='{el['classes'][:50]}'{testid}")
            print(f"      Texto: {el['texto']}")
        

        # PARTE 7: Extraindo dados de produtos

        print("\n" + "=" * 70)
        print("PARTE 7: TENTANDO EXTRAIR DADOS")
        print("=" * 70)
        
        if melhor_seletor:
            produtos = await page.query_selector_all(melhor_seletor)
            
            if produtos:
                print(f"\nAnalisando até 3 produtos com seletor '{melhor_seletor}':")
                
                for idx, produto in enumerate(produtos[:3]):
                    print(f"\n--- Produto {idx + 1} ---")
                    
                    # HTML do produto
                    html = await produto.evaluate("el => el.outerHTML")
                    print(f"Tamanho HTML: {len(html)} chars")
                    
                    # Tenta extrair título
                    titulo_seletores = [
                        "h2", "h3", "h4", 
                        "span[class*='name']", 
                        "[class*='title']", 
                        "[class*='Name']",
                        "[class*='description']",
                        "a span",
                        "a[title]",
                        "[data-testid*='name']",
                        "[data-testid*='title']",
                    ]
                    for sel in titulo_seletores:
                        try:
                            el = await produto.query_selector(sel)
                            if el:
                                texto = await el.inner_text()
                                if texto and len(texto.strip()) > 5:
                                    print(f"TÍTULO ({sel}): {texto.strip()[:60]}")
                                    break
                        except:
                            pass
                    
                    # Tenta extrair preço
                    preco_seletores = [
                        "span[class*='price']",
                        "div[class*='price']",
                        "[class*='Price']",
                        "[class*='selling']",
                        "[class*='value']",
                        "span[class*='bold']",
                        "[data-testid*='price']",
                    ]
                    for sel in preco_seletores:
                        try:
                            el = await produto.query_selector(sel)
                            if el:
                                texto = await el.inner_text()
                                if texto and ("R$" in texto or any(c.isdigit() for c in texto)):
                                    print(f"PREÇO ({sel}): {texto.strip()}")
                                    break
                        except:
                            pass
                    
                    # Mostra início do HTML
                    print(f"HTML (início): {html[:400]}...")
        

        # PARTE 8: Análise de classes CSS únicas

        print("\n" + "=" * 70)
        print("PARTE 8: CLASSES CSS FREQUENTES")
        print("=" * 70)
        
        classes_info = await page.evaluate("""
            () => {
                const classCount = {};
                document.querySelectorAll('*').forEach(el => {
                    if (el.className && typeof el.className === 'string') {
                        el.className.split(' ').forEach(cls => {
                            if (cls && (cls.includes('product') || cls.includes('Product') || 
                                       cls.includes('card') || cls.includes('Card') ||
                                       cls.includes('price') || cls.includes('Price') ||
                                       cls.includes('shelf') || cls.includes('Shelf') ||
                                       cls.includes('item') || cls.includes('Item'))) {
                                classCount[cls] = (classCount[cls] || 0) + 1;
                            }
                        });
                    }
                });
                return classCount;
            }
        """)
        
        print("\nClasses CSS relevantes encontradas:")
        sorted_classes = sorted(classes_info.items(), key=lambda x: -x[1])[:25]
        for cls, count in sorted_classes:
            print(f"   {count:3}x  .{cls}")
        

        # PARTE 9: Salvando HTML completo

        print("\n" + "=" * 70)
        print("PARTE 9: SALVANDO HTML")
        print("=" * 70)
        
        html_completo = await page.content()
        with open("paodeacucar_debug.html", "w", encoding="utf-8") as f:
            f.write(html_completo)
        print(f"\nHTML salvo em: paodeacucar_debug.html")
        print(f"Tamanho: {len(html_completo):,} caracteres")
        
        await page.screenshot(path="paodeacucar_debug.png", full_page=False)
        print("Screenshot salvo em: paodeacucar_debug.png")
        
        await page.close()
        await browser.close()
  

if __name__ == "__main__":
    asyncio.run(diagnosticar_pao_de_acucar())