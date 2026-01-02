#!/usr/bin/env python
"""
Exemplo de uso do módulo de Lista de Compras.

Este script demonstra como usar o ShoppingListProcessor para:
1. Processar uma lista de compras
2. Encontrar os melhores preços para cada item
3. Gerar relatórios em diferentes formatos
"""

import asyncio
from pathlib import Path

from src.shopping_list import (
    ShoppingItem,
    ShoppingListProcessor,
    ResultFormatter,
)
from src.shopping_list.processor import process_shopping_list, process_shopping_list_text


async def exemplo_basico():
    """Exemplo básico: processar lista de strings."""
    print("=" * 60)
    print("EXEMPLO 1: Lista básica de strings")
    print("=" * 60)
    
    # Lista simples de itens
    items = [
        "arroz 5kg",
        "feijão 1kg",
        "leite integral 1L",
        "açúcar 1kg",
    ]
    
    # Processa a lista
    result = await process_shopping_list(items)
    
    # Exibe resultado em texto
    print(ResultFormatter.to_text(result))
    print()


async def exemplo_com_quantidade():
    """Exemplo com quantidades personalizadas."""
    print("=" * 60)
    print("EXEMPLO 2: Lista com quantidades")
    print("=" * 60)
    
    # Lista com quantidades
    items = [
        ShoppingItem("arroz 5kg", quantity=2),
        ShoppingItem("feijão 1kg", quantity=3),
        ShoppingItem("leite integral 1L", quantity=12),
        ShoppingItem("café 500g", quantity=2),
    ]
    
    # Cria processador
    processor = ShoppingListProcessor(include_alternatives=True)
    
    # Processa com CEP específico
    result = await processor.process(
        items=items,
        cep="01310100",  # CEP de São Paulo
    )
    
    # Exibe resultado
    print(ResultFormatter.to_text(result, show_alternatives=True))
    print()


async def exemplo_texto():
    """Exemplo processando texto com lista."""
    print("=" * 60)
    print("EXEMPLO 3: Processar texto com lista")
    print("=" * 60)
    
    # Texto com lista de compras (como se fosse um arquivo)
    texto_lista = """
    # Minha lista de compras
    arroz 5kg
    2x feijão 1kg
    leite integral 1L (quantidade: 6)
    açúcar 1kg
    óleo de soja 900ml
    macarrão 500g
    """
    
    result = await process_shopping_list_text(texto_lista)
    
    # Exibe em markdown
    print(ResultFormatter.to_markdown(result))
    print()


async def exemplo_exportar():
    """Exemplo exportando para diferentes formatos."""
    print("=" * 60)
    print("EXEMPLO 4: Exportar para diferentes formatos")
    print("=" * 60)
    
    items = [
        ShoppingItem("arroz 5kg"),
        ShoppingItem("feijão 1kg"),
        ShoppingItem("leite 1L", quantity=6),
    ]
    
    processor = ShoppingListProcessor()
    result = await processor.process(items)
    
    # Cria diretório de saída
    output_dir = Path("./output")
    output_dir.mkdir(exist_ok=True)
    
    # Exporta em diferentes formatos
    
    # JSON
    json_content = ResultFormatter.to_json(result)
    (output_dir / "lista_compras.json").write_text(json_content, encoding="utf-8")
    print(f"✓ Salvo: {output_dir / 'lista_compras.json'}")
    
    # HTML
    html_content = ResultFormatter.to_html(result)
    (output_dir / "lista_compras.html").write_text(html_content, encoding="utf-8")
    print(f"✓ Salvo: {output_dir / 'lista_compras.html'}")
    
    # Markdown
    md_content = ResultFormatter.to_markdown(result)
    (output_dir / "lista_compras.md").write_text(md_content, encoding="utf-8")
    print(f"✓ Salvo: {output_dir / 'lista_compras.md'}")
    
    # CSV
    csv_content = ResultFormatter.to_csv(result)
    (output_dir / "lista_compras.csv").write_text(csv_content, encoding="utf-8")
    print(f"✓ Salvo: {output_dir / 'lista_compras.csv'}")
    
    print()


async def exemplo_analise_mercados():
    """Exemplo analisando resultados por mercado."""
    print("=" * 60)
    print("EXEMPLO 5: Análise por mercado")
    print("=" * 60)
    
    items = [
        ShoppingItem("arroz 5kg"),
        ShoppingItem("feijão 1kg"),
        ShoppingItem("leite 1L"),
        ShoppingItem("óleo 900ml"),
        ShoppingItem("açúcar 1kg"),
    ]
    
    processor = ShoppingListProcessor()
    result = await processor.process(items)
    
    print(f"\nTotal estimado: {result.formatted_total}")
    print(f"Itens encontrados: {result.items_found} / {result.total_items}")
    
    # Análise por mercado
    print("\n📊 Compras por Mercado:")
    print("-" * 40)
    
    for summary in result.get_by_market():
        print(f"\n🏪 {summary.market_name}")
        print(f"   Itens: {summary.total_items}")
        print(f"   Total: {summary.formatted_total}")
        print("   Produtos:")
        for item in summary.items:
            print(f"     - {item.item_name}: {item.formatted_price}")
    
    print()


async def main():
    """Executa todos os exemplos."""
    print("\n" + "=" * 60)
    print("   EXEMPLOS DE USO - LISTA DE COMPRAS")
    print("=" * 60 + "\n")
    
    # Escolha quais exemplos executar
    # (comente os que não quiser testar)
    
    await exemplo_basico()
    # await exemplo_com_quantidade()
    # await exemplo_texto()
    # await exemplo_exportar()
    # await exemplo_analise_mercados()


if __name__ == "__main__":
    asyncio.run(main())