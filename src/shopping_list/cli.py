"""
Interface de linha de comando (CLI) para Lista de Compras.
Permite processar lista de compras de forma interativa ou via arquivo.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table
from rich.markdown import Markdown

from src.shopping_list.models import ShoppingItem, ShoppingListResult
from src.shopping_list.processor import ShoppingListProcessor
from src.shopping_list.formatter import ResultFormatter

# Inicializa CLI
app = typer.Typer(
    name="shopping-list",
    help="Processador de Lista de Compras - Encontra os melhores preços.",
    add_completion=False,
)

# Console Rico para output formatado
console = Console()


def run_async(coro):
    """Helper para executar corrotinas."""
    return asyncio.get_event_loop().run_until_complete(coro)


@app.command("process")
def process_list(
    items: list[str] = typer.Argument(..., help="Itens da lista (ex: 'arroz 5kg' 'feijão 1kg')"),
    cep: Optional[str] = typer.Option(None, "--cep", "-c", help="CEP para localização"),
    market: Optional[str] = typer.Option(None, "--market", "-m", help="Mercado específico"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Arquivo de saída"),
    format: str = typer.Option("text", "--format", "-f", help="Formato: text, json, html, markdown, csv"),
    show_alternatives: bool = typer.Option(False, "--alternatives", "-a", help="Mostrar alternativas"),
):
    """
    Processa lista de compras e encontra os melhores preços.
    
    Exemplos:
        shopping-list process "arroz 5kg" "feijão 1kg" "leite 1L"
        shopping-list process "arroz 5kg" "leite 1L" --cep 01310100
        shopping-list process "cerveja" --market carrefour
        shopping-list process "arroz" "feijão" --format html --output lista.html
    """
    markets = [market] if market else None
    shopping_items = [ShoppingItem(name=item) for item in items]
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task(
            f"Processando {len(items)} itens...",
            total=len(items),
        )
        
        processor = ShoppingListProcessor(include_alternatives=show_alternatives)
        result = run_async(
            processor.process(
                items=shopping_items,
                cep=cep,
                markets=markets,
            )
        )
        progress.update(task, completed=len(items))
    
    # Formata saída
    _output_result(result, format, output, show_alternatives)


@app.command("from-file")
def process_from_file(
    file: Path = typer.Argument(..., help="Arquivo com lista de compras (um item por linha)"),
    cep: Optional[str] = typer.Option(None, "--cep", "-c", help="CEP para localização"),
    market: Optional[str] = typer.Option(None, "--market", "-m", help="Mercado específico"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Arquivo de saída"),
    format: str = typer.Option("text", "--format", "-f", help="Formato: text, json, html, markdown, csv"),
):
    """
    Processa lista de compras a partir de arquivo.
    
    O arquivo deve conter um item por linha. Formatos aceitos:
    - arroz 5kg
    - 2x leite integral 1L
    - feijão 1kg (quantidade: 3)
    
    Exemplos:
        shopping-list from-file minha_lista.txt
        shopping-list from-file lista.txt --cep 01310100 --output resultado.html --format html
    """
    if not file.exists():
        console.print(f"[red]Arquivo não encontrado: {file}[/red]")
        raise typer.Exit(1)
    
    text = file.read_text(encoding="utf-8")
    markets = [market] if market else None
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("Processando lista de compras...", total=None)
        
        processor = ShoppingListProcessor()
        result = run_async(
            processor.process_text(
                text=text,
                cep=cep,
                markets=markets,
            )
        )
    
    _output_result(result, format, output, show_alternatives=True)


@app.command("interactive")
def interactive_mode(
    cep: Optional[str] = typer.Option(None, "--cep", "-c", help="CEP para localização"),
):
    """
    Modo interativo para criar lista de compras.
    
    Digite os itens um por um e pressione Enter duas vezes para processar.
    
    Exemplos:
        shopping-list interactive
        shopping-list interactive --cep 01310100
    """
    console.print(Panel(
        "[bold]Modo Interativo - Lista de Compras[/bold]\n\n"
        "Digite os itens da sua lista (um por linha).\n"
        "Formatos aceitos:\n"
        "  • arroz 5kg\n"
        "  • 2x leite integral 1L\n"
        "  • feijão 1kg\n\n"
        "Pressione [bold]Enter duas vezes[/bold] para processar.",
        title="📋 Lista de Compras",
        border_style="blue",
    ))
    
    items = []
    console.print("\n[cyan]Digite os itens:[/cyan]")
    
    while True:
        try:
            line = input(f"  {len(items) + 1}. ")
            if line.strip():
                items.append(line.strip())
            else:
                if items:
                    break
                console.print("[yellow]Lista vazia. Digite pelo menos um item.[/yellow]")
        except EOFError:
            break
    
    if not items:
        console.print("[yellow]Nenhum item informado.[/yellow]")
        raise typer.Exit(0)
    
    console.print(f"\n[green]✓ {len(items)} itens na lista[/green]\n")
    
    # Processa
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("Buscando melhores preços...", total=None)
        
        processor = ShoppingListProcessor(include_alternatives=True)
        shopping_items = [ShoppingItem(name=item) for item in items]
        result = run_async(
            processor.process(
                items=shopping_items,
                cep=cep,
            )
        )
    
    _display_rich_result(result)


@app.command("quick")
def quick_search(
    item: str = typer.Argument(..., help="Item para buscar (ex: 'arroz 5kg')"),
    cep: Optional[str] = typer.Option(None, "--cep", "-c", help="CEP para localização"),
    quantity: int = typer.Option(1, "--qty", "-q", help="Quantidade"),
):
    """
    Busca rápida de um único item.
    
    Exemplos:
        shopping-list quick "arroz 5kg"
        shopping-list quick "leite integral 1L" --qty 6
        shopping-list quick "cerveja" --cep 01310100
    """
    shopping_item = ShoppingItem(name=item, quantity=quantity)
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task(f"Buscando '{item}'...", total=None)
        
        processor = ShoppingListProcessor(include_alternatives=True, max_alternatives=3)
        result = run_async(
            processor.process(
                items=[shopping_item],
                cep=cep,
            )
        )
    
    if result.items and result.items[0].found:
        item_result = result.items[0]
        
        console.print()
        console.print(Panel(
            f"[bold green]{item_result.product_title}[/bold green]\n\n"
            f"💰 Preço: [bold]{item_result.formatted_price}[/bold]\n"
            f"📦 Quantidade: {item_result.item_quantity}x = [bold]{item_result.formatted_total}[/bold]\n"
            f"📊 Preço normalizado: {item_result.price_display or 'N/A'}\n"
            f"🏬 Mercado: [cyan]{item_result.market_name}[/cyan]\n"
            f"🔗 Link: {item_result.product_url}",
            title=f"🏆 Melhor Preço: {item}",
            border_style="green",
        ))
        
        if item_result.image_url:
            console.print(f"\n[dim]🖼️  Imagem: {item_result.image_url}[/dim]")
        
        if item_result.alternatives:
            console.print("\n[bold]Alternativas:[/bold]")
            table = Table(show_header=True)
            table.add_column("Mercado", style="cyan")
            table.add_column("Preço", justify="right", style="green")
            table.add_column("Link")
            
            for alt in item_result.alternatives:
                table.add_row(
                    alt.market_name,
                    alt.formatted_price,
                    alt.product_url[:50] + "..." if len(alt.product_url or "") > 50 else alt.product_url or "-",
                )
            
            console.print(table)
    else:
        console.print(f"\n[red]❌ Produto não encontrado: {item}[/red]")


def _output_result(
    result: ShoppingListResult,
    format: str,
    output: Optional[Path],
    show_alternatives: bool,
):
    """Formata e exibe/salva resultado."""
    format = format.lower()
    
    if format == "json":
        content = ResultFormatter.to_json(result)
    elif format == "html":
        content = ResultFormatter.to_html(result)
    elif format == "markdown" or format == "md":
        content = ResultFormatter.to_markdown(result, show_alternatives)
    elif format == "csv":
        content = ResultFormatter.to_csv(result)
    else:  # text
        content = ResultFormatter.to_text(result, show_alternatives)
    
    if output:
        output.write_text(content, encoding="utf-8")
        console.print(f"[green]✓ Resultado salvo em: {output}[/green]")
    else:
        if format == "markdown" or format == "md":
            console.print(Markdown(content))
        elif format == "json":
            console.print_json(content)
        else:
            console.print(content)


def _display_rich_result(result: ShoppingListResult):
    """Exibe resultado formatado com Rich."""
    console.print()
    
    # Resumo
    console.print(Panel(
        f"[bold]Itens encontrados:[/bold] {result.items_found} / {result.total_items}\n"
        f"[bold]Não encontrados:[/bold] {len(result.not_found)}\n"
        f"[bold green]💰 TOTAL ESTIMADO: {result.formatted_total}[/bold green]",
        title="📊 Resumo",
        border_style="blue",
    ))
    
    # Tabela de resultados
    table = Table(title="🛒 Lista de Compras - Melhores Preços")
    table.add_column("#", style="dim", width=3)
    table.add_column("Item", style="white", width=20)
    table.add_column("Produto", style="cyan", width=35, overflow="fold")
    table.add_column("Preço", justify="right", style="green", width=12)
    table.add_column("Qtd", justify="center", width=5)
    table.add_column("Total", justify="right", style="bold green", width=12)
    table.add_column("Mercado", style="yellow", width=15)
    
    for idx, item in enumerate(result.items, 1):
        if item.found:
            product_short = item.product_title[:35] if item.product_title else "-"
            table.add_row(
                str(idx),
                item.item_name[:20],
                product_short,
                item.formatted_price,
                str(item.item_quantity),
                item.formatted_total,
                item.market_name or "-",
            )
        else:
            table.add_row(
                str(idx),
                item.item_name[:20],
                "[red]Não encontrado[/red]",
                "-",
                str(item.item_quantity),
                "-",
                "-",
            )
    
    console.print(table)
    
    # Links
    console.print("\n[bold]🔗 Links dos Produtos:[/bold]")
    for item in result.items:
        if item.found:
            console.print(f"  • {item.item_name}: [link={item.product_url}]{item.product_url}[/link]")
            if item.image_url:
                console.print(f"    [dim]🖼️  {item.image_url}[/dim]")
    
    # Por mercado
    by_market = result.get_by_market()
    if by_market and len(by_market) > 1:
        console.print("\n[bold]🏪 Por Mercado:[/bold]")
        for summary in by_market:
            console.print(f"  • {summary.market_name}: {summary.total_items} itens - {summary.formatted_total}")
    
    if result.duration_seconds:
        console.print(f"\n[dim]⏱️  Tempo de busca: {result.duration_seconds:.1f}s[/dim]")


def main():
    """Entry point principal."""
    app()


if __name__ == "__main__":
    main()