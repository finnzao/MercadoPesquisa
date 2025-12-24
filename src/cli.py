"""
Interface de linha de comando (CLI) do Price Collector.
Usa Typer para uma experiência moderna e rica.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from config.settings import get_settings
from src.collector import PriceCollector
from src.storage import StorageType

# Inicializa CLI
app = typer.Typer(
    name="price-collector",
    help="Sistema de coleta e comparação de preços de supermercados online.",
    add_completion=False,
)

# Console Rico para output formatado
console = Console()


def run_async(coro):
    """Helper para executar corrotinas."""
    return asyncio.get_event_loop().run_until_complete(coro)


@app.command("search")
def search(
    query: str = typer.Argument(..., help="Termo de busca (ex: 'arroz tipo 1 5kg')"),
    cep: Optional[str] = typer.Option(None, "--cep", "-c", help="CEP para localização"),
    market: Optional[str] = typer.Option(None, "--market", "-m", help="Mercado específico"),
    pages: int = typer.Option(1, "--pages", "-p", help="Número de páginas por mercado"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Arquivo de saída (CSV)"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Saída em formato JSON"),
):
    """
    Busca produtos em supermercados.
    
    Exemplos:
        price-collector search "arroz tipo 1 5kg"
        price-collector search "leite integral 1L" --cep 40000000
        price-collector search "banana prata" --market carrefour
        price-collector search "café 500g" --output resultados.csv
    """
    markets = [market] if market else None
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task(f"Buscando '{query}'...", total=None)
        
        collector = PriceCollector()
        result = run_async(
            collector.search(
                query=query,
                cep=cep,
                markets=markets,
                max_pages=pages,
            )
        )
    
    if json_output:
        _output_json(result)
        return
    
    if output:
        _export_to_file(collector, result, output)
        return
    
    _display_results(result)


@app.command("compare")
def compare(
    query: str = typer.Argument(..., help="Termo de busca"),
    cep: Optional[str] = typer.Option(None, "--cep", "-c", help="CEP para localização"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Saída em formato JSON"),
):
    """
    Compara preços entre mercados.
    
    Exemplos:
        price-collector compare "arroz tipo 1 5kg"
        price-collector compare "leite integral 1L" --cep 40000000
    """
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task(f"Comparando preços para '{query}'...", total=None)
        
        collector = PriceCollector()
        comparison = run_async(
            collector.compare_prices(query=query, cep=cep)
        )
    
    if json_output:
        console.print_json(json.dumps(comparison, indent=2, default=str))
        return
    
    _display_comparison(comparison)


@app.command("markets")
def list_markets():
    """
    Lista mercados disponíveis.
    """
    collector = PriceCollector()
    markets = collector.get_available_markets()
    
    table = Table(title="Mercados Disponíveis")
    table.add_column("ID", style="cyan")
    table.add_column("Nome", style="green")
    table.add_column("Status", style="yellow")
    table.add_column("Método", style="blue")
    
    for market in markets:
        table.add_row(
            market["id"],
            market["name"],
            market["status"],
            market["method"],
        )
    
    console.print(table)


@app.command("stats")
def statistics(
    market: Optional[str] = typer.Option(None, "--market", "-m", help="Filtrar por mercado"),
    days: int = typer.Option(30, "--days", "-d", help="Período em dias"),
):
    """
    Exibe estatísticas de coleta.
    """
    collector = PriceCollector()
    stats = run_async(
        collector.get_statistics(market_id=market, days=days)
    )
    
    panel = Panel(
        f"""[bold]Estatísticas dos últimos {days} dias[/bold]
        
Total de ofertas: [cyan]{stats.get('total_offers', 0)}[/cyan]
Ofertas normalizadas: [green]{stats.get('normalized_offers', 0)}[/green]
Queries únicas: [yellow]{stats.get('unique_queries', 0)}[/yellow]
Mercados: [blue]{stats.get('markets_count', 0)}[/blue]
Coletas realizadas: [magenta]{stats.get('total_collections', 0)}[/magenta]
        """,
        title="📊 Estatísticas",
        border_style="blue",
    )
    
    console.print(panel)
    
    # Tabela por mercado
    if stats.get("by_market"):
        table = Table(title="Ofertas por Mercado")
        table.add_column("Mercado", style="cyan")
        table.add_column("Ofertas", justify="right", style="green")
        
        for market_id, count in stats["by_market"].items():
            table.add_row(market_id, str(count))
        
        console.print(table)


@app.command("history")
def price_history(
    query: str = typer.Argument(..., help="Termo de busca"),
    market: Optional[str] = typer.Option(None, "--market", "-m", help="Filtrar por mercado"),
    days: int = typer.Option(30, "--days", "-d", help="Período em dias"),
):
    """
    Mostra histórico de preços de um produto.
    """
    collector = PriceCollector()
    history = run_async(
        collector.get_price_history(query=query, market_id=market, days=days)
    )
    
    if not history:
        console.print(f"[yellow]Nenhum histórico encontrado para '{query}'[/yellow]")
        return
    
    table = Table(title=f"Histórico de Preços: {query}")
    table.add_column("Data", style="cyan")
    table.add_column("Mercado", style="green")
    table.add_column("Preço Médio", justify="right", style="yellow")
    table.add_column("Mín", justify="right", style="blue")
    table.add_column("Máx", justify="right", style="red")
    table.add_column("Amostras", justify="right")
    
    for entry in history:
        table.add_row(
            entry["date"],
            entry["market_id"],
            f"R$ {entry['avg_price']:.2f}",
            f"R$ {entry['min_price']:.2f}",
            f"R$ {entry['max_price']:.2f}",
            str(entry["samples"]),
        )
    
    console.print(table)


@app.command("export")
def export(
    output: Path = typer.Argument(..., help="Arquivo de saída"),
    format: str = typer.Option("csv", "--format", "-f", help="Formato (csv ou parquet)"),
    query: Optional[str] = typer.Option(None, "--query", "-q", help="Filtrar por query"),
    market: Optional[str] = typer.Option(None, "--market", "-m", help="Filtrar por mercado"),
):
    """
    Exporta dados coletados para arquivo.
    
    Exemplos:
        price-collector export resultados.csv
        price-collector export dados.parquet --format parquet
        price-collector export arroz.csv --query "arroz"
    """
    collector = PriceCollector()
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("Exportando dados...", total=None)
        
        path = run_async(
            collector.export_results(
                output_path=output,
                format=format,
                query=query,
                market_id=market,
            )
        )
    
    if path:
        console.print(f"[green]✓ Dados exportados para: {path}[/green]")
    else:
        console.print("[yellow]Nenhum dado para exportar[/yellow]")


@app.command("version")
def version():
    """
    Exibe a versão do sistema.
    """
    from src import __version__
    
    console.print(f"[bold blue]Price Collector[/bold blue] v{__version__}")
    console.print("Sistema de coleta e comparação de preços de supermercados")


# FUNÇÕES DE DISPLAY

def _display_results(result):
    """Exibe resultados de busca formatados."""
    metadata = result.metadata
    offers = result.offers
    
    # Header
    console.print()
    console.print(Panel(
        f"[bold]Busca:[/bold] {metadata.search_query}\n"
        f"[bold]CEP:[/bold] {metadata.cep or 'Não informado'}\n"
        f"[bold]Duração:[/bold] {metadata.duration_seconds:.2f}s" if metadata.duration_seconds else "",
        title="🔍 Resultado da Busca",
        border_style="blue",
    ))
    
    if not offers:
        console.print("[yellow]Nenhum produto encontrado.[/yellow]")
        return
    
    # Tabela de ofertas
    table = Table(title=f"Encontrados {len(offers)} produtos")
    table.add_column("#", style="dim", width=4)
    table.add_column("Mercado", style="cyan", width=15)
    table.add_column("Produto", style="white", width=40, overflow="fold")
    table.add_column("Preço", justify="right", style="green", width=12)
    table.add_column("R$/unid", justify="right", style="yellow", width=14)
    table.add_column("Status", width=8)
    
    for i, offer in enumerate(offers[:20], 1):  # Limita a 20
        status_icon = "✓" if offer.is_comparable else "○"
        status_color = "green" if offer.is_comparable else "yellow"
        
        table.add_row(
            str(i),
            offer.market_name[:15],
            offer.title[:40],
            offer.format_price(),
            offer.format_normalized_price(),
            f"[{status_color}]{status_icon}[/{status_color}]",
        )
    
    console.print(table)
    
    if len(offers) > 20:
        console.print(f"[dim]... e mais {len(offers) - 20} produtos[/dim]")
    
    # Resumo
    comparable = sum(1 for o in offers if o.is_comparable)
    console.print(f"\n[bold]Resumo:[/bold] {len(offers)} produtos, {comparable} comparáveis")


def _display_comparison(comparison):
    """Exibe comparação de preços formatada."""
    console.print()
    
    # Header
    console.print(Panel(
        f"[bold]Produto:[/bold] {comparison['query']}\n"
        f"[bold]CEP:[/bold] {comparison.get('cep') or 'Não informado'}\n"
        f"[bold]Ofertas:[/bold] {comparison['total_offers']} ({comparison['comparable_offers']} comparáveis)",
        title="📊 Comparação de Preços",
        border_style="blue",
    ))
    
    if not comparison.get("best_offer"):
        console.print("[yellow]Nenhuma oferta comparável encontrada.[/yellow]")
        return
    
    # Melhor oferta
    best = comparison["best_offer"]
    console.print(Panel(
        f"[bold green]{best['market']}[/bold green]\n\n"
        f"[bold]{best['title']}[/bold]\n\n"
        f"Preço: [bold green]{best['price_display']}[/bold green]\n"
        f"URL: [link={best['url']}]{best['url'][:50]}...[/link]",
        title="🏆 Melhor Oferta",
        border_style="green",
    ))
    
    # Por mercado
    if comparison.get("by_market"):
        table = Table(title="Comparação por Mercado")
        table.add_column("Mercado", style="cyan")
        table.add_column("Ofertas", justify="right")
        table.add_column("Menor Preço", justify="right", style="green")
        table.add_column("Menor R$/unid", justify="right", style="yellow")
        
        for market_id, data in comparison["by_market"].items():
            min_price = f"R$ {data['min_price']:.2f}" if data['min_price'] else "N/A"
            min_norm = f"R$ {data['min_normalized']:.2f}" if data['min_normalized'] else "N/A"
            
            table.add_row(
                data["market_name"],
                str(data["offers_count"]),
                min_price,
                min_norm,
            )
        
        console.print(table)
    
    # Economias potenciais
    if comparison.get("potential_savings"):
        console.print("\n[bold]💰 Economias Potenciais:[/bold]")
        for saving in comparison["potential_savings"][:3]:
            console.print(
                f"  • Comprando no [green]{saving['best_market']}[/green] "
                f"ao invés do [red]{saving['compared_market']}[/red]: "
                f"[bold green]R$ {saving['absolute']:.2f}/{saving['unit']}[/bold green] "
                f"({saving['percentage']:.1f}% de economia)"
            )


def _output_json(result):
    """Exibe resultado em formato JSON."""
    output = {
        "metadata": result.metadata.model_dump(mode="json"),
        "offers": [o.model_dump(mode="json") for o in result.offers],
    }
    console.print_json(json.dumps(output, indent=2, default=str))


def _export_to_file(collector, result, output_path):
    """Exporta resultado para arquivo."""
    run_async(
        collector.storage.save_offers(
            result.offers,
            result.metadata,
            StorageType.CSV if output_path.suffix == ".csv" else StorageType.PARQUET,
        )
    )
    console.print(f"[green]✓ Resultados salvos em: {output_path}[/green]")


# ENTRY POINT

def main():
    """Entry point principal."""
    app()


if __name__ == "__main__":
    main()
