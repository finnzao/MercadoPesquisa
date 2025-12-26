#!/usr/bin/env python3
"""
Script de diagnóstico para verificar se as correções foram aplicadas.

Execute este script no diretório do seu projeto:
    python diagnostico_correcao.py
"""

import sys
import inspect
from pathlib import Path

# Adiciona o diretório atual ao path
sys.path.insert(0, str(Path(__file__).parent))

def main():
    print("=" * 70)
    print("DIAGNÓSTICO DAS CORREÇÕES DOS SCRAPERS")
    print("=" * 70)
    
    erros = []
    
    # =========================================================================
    # 1. Verifica BaseScraper
    # =========================================================================
    print("\n[1/4] Verificando BaseScraper...")
    
    try:
        from src.scrapers.base import BaseScraper
        
        # Verifica se tem o método _build_search_url
        if hasattr(BaseScraper, '_build_search_url'):
            print("   ✅ BaseScraper tem método _build_search_url")
            
            # Verifica o código fonte
            source = inspect.getsource(BaseScraper._build_search_url)
            if "def _build_search_url" in source:
                print("   ✅ Método _build_search_url está definido")
            else:
                print("   ❌ Método _build_search_url não encontrado no código")
                erros.append("BaseScraper._build_search_url não definido corretamente")
        else:
            print("   ❌ BaseScraper NÃO tem método _build_search_url")
            print("      -> O arquivo base.py NÃO foi atualizado!")
            erros.append("BaseScraper não tem _build_search_url - arquivo não atualizado")
        
        # Verifica se search() usa _build_search_url
        search_source = inspect.getsource(BaseScraper.search)
        if "_build_search_url" in search_source:
            print("   ✅ BaseScraper.search() chama _build_search_url")
        elif "config.get_search_url" in search_source:
            print("   ❌ BaseScraper.search() ainda usa config.get_search_url (ANTIGO)")
            print("      -> O arquivo base.py NÃO foi atualizado!")
            erros.append("BaseScraper.search() não chama _build_search_url")
        
    except Exception as e:
        print(f"   ❌ Erro ao importar BaseScraper: {e}")
        erros.append(f"Erro ao importar BaseScraper: {e}")
    
    # =========================================================================
    # 2. Verifica PaoDeAcucarScraper
    # =========================================================================
    print("\n[2/4] Verificando PaoDeAcucarScraper...")
    
    try:
        from src.scrapers.pao_acucar import PaoDeAcucarScraper
        
        # Verifica se sobrescreve _build_search_url
        if '_build_search_url' in PaoDeAcucarScraper.__dict__:
            print("   ✅ PaoDeAcucarScraper sobrescreve _build_search_url")
            
            # Verifica se usa quote_plus
            source = inspect.getsource(PaoDeAcucarScraper._build_search_url)
            if "quote_plus" in source:
                print("   ✅ Usa quote_plus() corretamente")
            else:
                print("   ❌ NÃO usa quote_plus()")
                erros.append("PaoDeAcucarScraper._build_search_url não usa quote_plus")
        else:
            print("   ❌ PaoDeAcucarScraper NÃO sobrescreve _build_search_url")
            print("      -> O arquivo pao_acucar.py NÃO foi atualizado!")
            erros.append("PaoDeAcucarScraper não sobrescreve _build_search_url")
        
        # Testa a URL gerada
        scraper = PaoDeAcucarScraper()
        if hasattr(scraper, '_build_search_url'):
            url = scraper._build_search_url("arroz 5 kg", 0)
            print(f"   URL gerada: {url}")
            
            if "arroz+5+kg" in url:
                print("   ✅ URL usa + para espaços (CORRETO)")
            elif "arroz%205%20kg" in url:
                print("   ❌ URL usa %20 para espaços (INCORRETO)")
                erros.append("PaoDeAcucarScraper gera URL com %20 ao invés de +")
        
    except Exception as e:
        print(f"   ❌ Erro ao importar PaoDeAcucarScraper: {e}")
        erros.append(f"Erro ao importar PaoDeAcucarScraper: {e}")
    
    # =========================================================================
    # 3. Verifica AtacadaoScraper
    # =========================================================================
    print("\n[3/4] Verificando AtacadaoScraper...")
    
    try:
        from src.scrapers.atacadao import AtacadaoScraper
        
        if '_build_search_url' in AtacadaoScraper.__dict__:
            print("   ✅ AtacadaoScraper sobrescreve _build_search_url")
            
            source = inspect.getsource(AtacadaoScraper._build_search_url)
            if "quote_plus" in source:
                print("   ✅ Usa quote_plus() corretamente")
            else:
                print("   ❌ NÃO usa quote_plus()")
                erros.append("AtacadaoScraper._build_search_url não usa quote_plus")
        else:
            print("   ❌ AtacadaoScraper NÃO sobrescreve _build_search_url")
            print("      -> O arquivo atacadao.py NÃO foi atualizado!")
            erros.append("AtacadaoScraper não sobrescreve _build_search_url")
        
        # Testa a URL gerada
        scraper = AtacadaoScraper()
        if hasattr(scraper, '_build_search_url'):
            url = scraper._build_search_url("arroz 5 kg", 0)
            print(f"   URL gerada: {url}")
            
            if "arroz+5+kg" in url:
                print("   ✅ URL usa + para espaços (CORRETO)")
            elif "arroz%205%20kg" in url:
                print("   ❌ URL usa %20 para espaços (INCORRETO)")
                erros.append("AtacadaoScraper gera URL com %20 ao invés de +")
        
    except Exception as e:
        print(f"   ❌ Erro ao importar AtacadaoScraper: {e}")
        erros.append(f"Erro ao importar AtacadaoScraper: {e}")
    
    # =========================================================================
    # 4. Verifica CarrefourScraper
    # =========================================================================
    print("\n[4/4] Verificando CarrefourScraper...")
    
    try:
        from src.scrapers.carrefour import CarrefourScraper
        
        scraper = CarrefourScraper()
        if hasattr(scraper, '_build_search_url'):
            url = scraper._build_search_url("arroz 5 kg", 0)
            print(f"   URL gerada: {url}")
            
            if "/busca/arroz" in url:
                print("   ✅ URL de path (correto para Carrefour)")
            else:
                print("   ⚠️  Formato de URL diferente do esperado")
        else:
            print("   ⚠️  Usando método padrão do BaseScraper")
        
    except Exception as e:
        print(f"   ❌ Erro ao importar CarrefourScraper: {e}")
        erros.append(f"Erro ao importar CarrefourScraper: {e}")
    
    # =========================================================================
    # RESUMO
    # =========================================================================
    print("\n" + "=" * 70)
    print("RESUMO")
    print("=" * 70)
    
    if erros:
        print(f"\n❌ Encontrados {len(erros)} problemas:\n")
        for i, erro in enumerate(erros, 1):
            print(f"   {i}. {erro}")
        
        print("\n" + "-" * 70)
        print("SOLUÇÃO:")
        print("-" * 70)
        print("""
Os arquivos corrigidos NÃO foram aplicados corretamente.

Execute os seguintes comandos para aplicar as correções:

    cp base_corrigido.py src/scrapers/base.py
    cp atacadao_corrigido.py src/scrapers/atacadao.py
    cp pao_acucar_corrigido.py src/scrapers/pao_acucar.py
    cp carrefour_corrigido.py src/scrapers/carrefour.py

Depois execute este diagnóstico novamente.
""")
    else:
        print("\n✅ Todas as correções foram aplicadas corretamente!")
        print("\nO comando CLI deve funcionar agora:")
        print("    price-collector search \"arroz 5 kg\" --output resultados.csv")


if __name__ == "__main__":
    main()