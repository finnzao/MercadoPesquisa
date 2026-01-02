"""
Formatador de Resultados da Lista de Compras.
Gera saídas em diferentes formatos (texto, HTML, JSON, Markdown).
"""

import json
from datetime import datetime
from typing import Optional

from src.shopping_list.models import ShoppingListResult, ItemResult, MarketSummary


class ResultFormatter:
    """
    Formatador de resultados de lista de compras.
    
    Gera saídas em diferentes formatos para exibição ou exportação.
    """
    
    @staticmethod
    def to_text(result: ShoppingListResult, show_alternatives: bool = False) -> str:
        """
        Formata resultado como texto simples.
        
        Args:
            result: Resultado da lista de compras
            show_alternatives: Se deve mostrar alternativas
            
        Returns:
            String formatada
        """
        lines = []
        
        # Cabeçalho
        lines.append("=" * 60)
        lines.append("📋 LISTA DE COMPRAS - MELHORES PREÇOS")
        lines.append("=" * 60)
        lines.append("")
        
        if result.cep:
            lines.append(f"📍 CEP: {result.cep}")
        lines.append(f"🏪 Mercados pesquisados: {', '.join(result.markets_searched)}")
        lines.append(f"📅 Data: {result.started_at.strftime('%d/%m/%Y %H:%M')}")
        lines.append("")
        
        # Itens encontrados
        lines.append("-" * 60)
        lines.append("ITENS ENCONTRADOS")
        lines.append("-" * 60)
        lines.append("")
        
        for item in result.items:
            if item.found:
                lines.append(f"✅ {item.item_name}")
                lines.append(f"   📦 {item.product_title}")
                lines.append(f"   💰 Preço: {item.formatted_price}")
                if item.item_quantity > 1:
                    lines.append(f"   🔢 Quantidade: {item.item_quantity}x = {item.formatted_total}")
                lines.append(f"   🏬 Local: {item.market_name}")
                lines.append(f"   🔗 Link: {item.product_url}")
                if item.image_url:
                    lines.append(f"   🖼️  Imagem: {item.image_url}")
                
                if show_alternatives and item.alternatives:
                    lines.append("   📊 Alternativas:")
                    for alt in item.alternatives:
                        lines.append(f"      - {alt.market_name}: {alt.formatted_price}")
                
                lines.append("")
        
        # Itens não encontrados
        if result.not_found:
            lines.append("-" * 60)
            lines.append("ITENS NÃO ENCONTRADOS")
            lines.append("-" * 60)
            lines.append("")
            for item_name in result.not_found:
                lines.append(f"❌ {item_name}")
            lines.append("")
        
        # Resumo
        lines.append("=" * 60)
        lines.append("RESUMO")
        lines.append("=" * 60)
        lines.append("")
        lines.append(f"📊 Total de itens: {result.total_items}")
        lines.append(f"✅ Encontrados: {result.items_found}")
        lines.append(f"❌ Não encontrados: {len(result.not_found)}")
        lines.append(f"💵 TOTAL ESTIMADO: {result.formatted_total}")
        
        if result.duration_seconds:
            lines.append(f"⏱️  Tempo de busca: {result.duration_seconds:.1f}s")
        
        # Resumo por mercado
        by_market = result.get_by_market()
        if by_market:
            lines.append("")
            lines.append("-" * 60)
            lines.append("ITENS POR MERCADO")
            lines.append("-" * 60)
            for summary in by_market:
                lines.append(f"🏪 {summary.market_name}: {summary.total_items} itens - {summary.formatted_total}")
        
        return "\n".join(lines)
    
    @staticmethod
    def to_markdown(result: ShoppingListResult, show_alternatives: bool = True) -> str:
        """
        Formata resultado como Markdown.
        
        Args:
            result: Resultado da lista de compras
            show_alternatives: Se deve mostrar alternativas
            
        Returns:
            String em Markdown
        """
        lines = []
        
        # Cabeçalho
        lines.append("# 📋 Lista de Compras - Melhores Preços")
        lines.append("")
        
        if result.cep:
            lines.append(f"**CEP:** {result.cep}")
        lines.append(f"**Mercados:** {', '.join(result.markets_searched)}")
        lines.append(f"**Data:** {result.started_at.strftime('%d/%m/%Y %H:%M')}")
        lines.append("")
        
        # Tabela de resultados
        lines.append("## Resultados")
        lines.append("")
        lines.append("| Item | Produto | Preço | Qtd | Total | Mercado | Link |")
        lines.append("|------|---------|-------|-----|-------|---------|------|")
        
        for item in result.items:
            if item.found:
                qty = f"{item.item_quantity}x" if item.item_quantity > 1 else "1"
                link = f"[Ver]({item.product_url})" if item.product_url else "-"
                product_short = item.product_title[:40] + "..." if len(item.product_title or "") > 40 else item.product_title
                
                lines.append(
                    f"| {item.item_name} | {product_short} | {item.formatted_price} | "
                    f"{qty} | {item.formatted_total} | {item.market_name} | {link} |"
                )
        
        # Não encontrados
        for item in result.items:
            if not item.found:
                lines.append(f"| ❌ {item.item_name} | *Não encontrado* | - | - | - | - | - |")
        
        lines.append("")
        
        # Detalhes com imagens
        lines.append("## Detalhes dos Produtos")
        lines.append("")
        
        for item in result.items:
            if item.found:
                lines.append(f"### {item.item_name}")
                lines.append("")
                if item.image_url:
                    lines.append(f"![{item.product_title}]({item.image_url})")
                    lines.append("")
                lines.append(f"- **Produto:** {item.product_title}")
                lines.append(f"- **Preço unitário:** {item.formatted_price}")
                if item.price_display and item.normalized_price:
                    lines.append(f"- **Preço normalizado:** {item.price_display}")
                lines.append(f"- **Quantidade:** {item.item_quantity}")
                lines.append(f"- **Total:** {item.formatted_total}")
                lines.append(f"- **Mercado:** {item.market_name}")
                lines.append(f"- **Link:** {item.product_url}")
                
                if show_alternatives and item.alternatives:
                    lines.append("")
                    lines.append("**Alternativas:**")
                    for alt in item.alternatives:
                        lines.append(f"- {alt.market_name}: {alt.formatted_price} - [Ver]({alt.product_url})")
                
                lines.append("")
        
        # Resumo
        lines.append("## 💰 Resumo")
        lines.append("")
        lines.append(f"- **Total de itens:** {result.total_items}")
        lines.append(f"- **Encontrados:** {result.items_found}")
        lines.append(f"- **Não encontrados:** {len(result.not_found)}")
        lines.append(f"- **💵 TOTAL ESTIMADO:** {result.formatted_total}")
        
        if result.duration_seconds:
            lines.append(f"- **Tempo de busca:** {result.duration_seconds:.1f}s")
        
        # Por mercado
        by_market = result.get_by_market()
        if by_market:
            lines.append("")
            lines.append("### Por Mercado")
            lines.append("")
            for summary in by_market:
                lines.append(f"- **{summary.market_name}:** {summary.total_items} itens - {summary.formatted_total}")
        
        return "\n".join(lines)
    
    @staticmethod
    def to_html(result: ShoppingListResult) -> str:
        """
        Formata resultado como HTML com estilos.
        
        Args:
            result: Resultado da lista de compras
            
        Returns:
            String HTML
        """
        html = f"""
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Lista de Compras - Melhores Preços</title>
    <style>
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: #f5f5f5;
            color: #333;
            line-height: 1.6;
            padding: 20px;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 20px;
            text-align: center;
        }}
        header h1 {{
            font-size: 2em;
            margin-bottom: 10px;
        }}
        .meta {{
            opacity: 0.9;
            font-size: 0.9em;
        }}
        .summary-cards {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }}
        .summary-card {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            text-align: center;
        }}
        .summary-card .value {{
            font-size: 2em;
            font-weight: bold;
            color: #667eea;
        }}
        .summary-card .label {{
            color: #666;
            font-size: 0.9em;
        }}
        .total-card {{
            background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
            color: white;
        }}
        .total-card .value {{
            color: white;
        }}
        .total-card .label {{
            color: rgba(255,255,255,0.9);
        }}
        .items-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }}
        .item-card {{
            background: white;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            overflow: hidden;
        }}
        .item-card.not-found {{
            opacity: 0.6;
        }}
        .item-header {{
            background: #667eea;
            color: white;
            padding: 15px;
            font-weight: bold;
        }}
        .item-header.not-found {{
            background: #e74c3c;
        }}
        .item-image {{
            width: 100%;
            height: 200px;
            object-fit: contain;
            background: #f9f9f9;
            padding: 10px;
        }}
        .item-details {{
            padding: 15px;
        }}
        .item-title {{
            font-size: 1.1em;
            margin-bottom: 10px;
            color: #333;
        }}
        .item-price {{
            font-size: 1.5em;
            font-weight: bold;
            color: #11998e;
            margin-bottom: 5px;
        }}
        .item-meta {{
            color: #666;
            font-size: 0.9em;
            margin-bottom: 10px;
        }}
        .item-market {{
            display: inline-block;
            background: #667eea;
            color: white;
            padding: 5px 10px;
            border-radius: 5px;
            font-size: 0.85em;
            margin-bottom: 10px;
        }}
        .item-link {{
            display: inline-block;
            background: #11998e;
            color: white;
            padding: 10px 20px;
            border-radius: 5px;
            text-decoration: none;
            font-weight: bold;
            width: 100%;
            text-align: center;
        }}
        .item-link:hover {{
            background: #0d7a6e;
        }}
        .alternatives {{
            background: #f9f9f9;
            padding: 15px;
            border-top: 1px solid #eee;
        }}
        .alternatives h4 {{
            font-size: 0.9em;
            color: #666;
            margin-bottom: 10px;
        }}
        .alt-item {{
            display: flex;
            justify-content: space-between;
            padding: 5px 0;
            border-bottom: 1px dashed #ddd;
        }}
        .alt-item:last-child {{
            border-bottom: none;
        }}
        .market-summary {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }}
        .market-summary h3 {{
            margin-bottom: 15px;
            color: #333;
        }}
        .market-row {{
            display: flex;
            justify-content: space-between;
            padding: 10px 0;
            border-bottom: 1px solid #eee;
        }}
        .market-row:last-child {{
            border-bottom: none;
        }}
        footer {{
            text-align: center;
            padding: 20px;
            color: #666;
            font-size: 0.9em;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>📋 Lista de Compras</h1>
            <div class="meta">
                {f'CEP: {result.cep} | ' if result.cep else ''}
                {result.started_at.strftime('%d/%m/%Y %H:%M')}
            </div>
        </header>
        
        <div class="summary-cards">
            <div class="summary-card">
                <div class="value">{result.total_items}</div>
                <div class="label">Total de Itens</div>
            </div>
            <div class="summary-card">
                <div class="value">{result.items_found}</div>
                <div class="label">Encontrados</div>
            </div>
            <div class="summary-card">
                <div class="value">{len(result.not_found)}</div>
                <div class="label">Não Encontrados</div>
            </div>
            <div class="summary-card total-card">
                <div class="value">{result.formatted_total}</div>
                <div class="label">Total Estimado</div>
            </div>
        </div>
        
        <div class="items-grid">
"""
        
        for item in result.items:
            if item.found:
                image_html = f'<img src="{item.image_url}" alt="{item.product_title}" class="item-image">' if item.image_url else ''
                qty_info = f" ({item.item_quantity}x = {item.formatted_total})" if item.item_quantity > 1 else ""
                
                alternatives_html = ""
                if item.alternatives:
                    alternatives_html = '<div class="alternatives"><h4>Alternativas:</h4>'
                    for alt in item.alternatives:
                        alternatives_html += f'''
                        <div class="alt-item">
                            <span>{alt.market_name}</span>
                            <span>{alt.formatted_price}</span>
                        </div>
                        '''
                    alternatives_html += '</div>'
                
                html += f"""
            <div class="item-card">
                <div class="item-header">{item.item_name}</div>
                {image_html}
                <div class="item-details">
                    <div class="item-title">{item.product_title}</div>
                    <div class="item-price">{item.formatted_price}{qty_info}</div>
                    <div class="item-meta">{item.price_display or ''}</div>
                    <div class="item-market">{item.market_name}</div>
                    <a href="{item.product_url}" target="_blank" class="item-link">Ver Produto</a>
                </div>
                {alternatives_html}
            </div>
"""
            else:
                html += f"""
            <div class="item-card not-found">
                <div class="item-header not-found">❌ {item.item_name}</div>
                <div class="item-details">
                    <p>Produto não encontrado nos mercados pesquisados.</p>
                </div>
            </div>
"""
        
        # Resumo por mercado
        by_market = result.get_by_market()
        if by_market:
            html += """
        </div>
        
        <div class="market-summary">
            <h3>📊 Resumo por Mercado</h3>
"""
            for summary in by_market:
                html += f"""
            <div class="market-row">
                <span><strong>{summary.market_name}</strong> ({summary.total_items} itens)</span>
                <span><strong>{summary.formatted_total}</strong></span>
            </div>
"""
            html += """
        </div>
"""
        
        html += f"""
        <footer>
            Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
            {f' | Tempo de busca: {result.duration_seconds:.1f}s' if result.duration_seconds else ''}
        </footer>
    </div>
</body>
</html>
"""
        return html
    
    @staticmethod
    def to_json(result: ShoppingListResult, indent: int = 2) -> str:
        """
        Formata resultado como JSON.
        
        Args:
            result: Resultado da lista de compras
            indent: Indentação do JSON
            
        Returns:
            String JSON
        """
        return json.dumps(result.to_dict(), indent=indent, ensure_ascii=False, default=str)
    
    @staticmethod
    def to_csv(result: ShoppingListResult) -> str:
        """
        Formata resultado como CSV.
        
        Args:
            result: Resultado da lista de compras
            
        Returns:
            String CSV
        """
        lines = []
        
        # Cabeçalho
        headers = [
            "Item",
            "Produto",
            "Preço Unitário",
            "Quantidade",
            "Preço Total",
            "Preço Normalizado",
            "Mercado",
            "URL",
            "Imagem",
            "Encontrado",
        ]
        lines.append(";".join(headers))
        
        # Dados
        for item in result.items:
            row = [
                item.item_name,
                item.product_title or "",
                str(item.price) if item.price else "",
                str(item.item_quantity),
                str(item.total_price) if item.total_price else "",
                item.price_display or "",
                item.market_name or "",
                item.product_url or "",
                item.image_url or "",
                "Sim" if item.found else "Não",
            ]
            lines.append(";".join(row))
        
        return "\n".join(lines)