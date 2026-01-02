"""
CLI do Price Collector usando Typer e Rich.
"""

import asyncio
import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from config.settings import get_settings
from src.collector import PriceCollector
from src.ranking import RankingStrategy
from src.storage import StorageType

app = typer.Typer(
    name="price-collector",
    help="Sistema de coleta e comparacao de precos de supermercados online.",
    add_completion=False,
)

console = Console()


def run_async(coro):
    """Executa corrotinas de forma sincrona."""
    return asyncio.get_event_loop().run_until_complete(coro)


def parse_ranking_strategy(strategy: str) -> RankingStrategy:
    """Converte string para RankingStrategy."""
    strategy_map = {
        "price": RankingStrategy.PRICE_FIRST,
        "relevance": RankingStrategy.RELEVANCE_FIRST,
        "balanced": RankingStrategy.BALANCED,
    }
    return strategy_map.get(strategy.lower(), RankingStrategy.PRICE_FIRST)


@app.command("search")
def search(
    query: str = typer.Argument(..., help="Termo de busca (ex: 'arroz tipo 1 5kg')"),
    cep: Optional[str] = typer.Option(None, "--cep", "-c", help="CEP para localizacao"),
    market: Optional[str] = typer.Option(None, "--market", "-m", help="Mercado especifico"),
    pages: int = typer.Option(1, "--pages", "-p", help="Numero de paginas por mercado"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Arquivo de saida (CSV)"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Saida em formato JSON"),
    ranking: str = typer.Option("price", "--ranking", "-r", help="Estrategia: price, relevance, balanced"),
    no_filter: bool = typer.Option(False, "--no-filter", help="Nao filtrar produtos irrelevantes"),
    show_relevance: bool = typer.Option(False, "--show-relevance", "-s", help="Mostrar indicador de relevancia"),
):
    """
    Busca produtos em supermercados com ranking inteligente.
    
    Exemplos:
        price-collector search "arroz tipo 1 5kg"
        price-collector search "leite integral 1L" --cep 40000000
        price-collector search "banana prata" --market carrefour
    """
    markets = [market] if market else None
    strategy = parse_ranking_strategy(ranking)
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task(f"Buscando '{query}'...", total=None)
        
        collector = PriceCollector(
            ranking_strategy=strategy,
            filter_irrelevant=not no_filter,
        )
        result = run_async(
            collector.search(
                query=query,
                cep=cep,
                markets=markets,
                max_pages=pages,
                apply_ranking=True,
            )
        )
    
    if json_output:
        _output_json(result, query, collector)
        return
    
    if output:
        _export_to_file(collector, result, output)
        return
    
    _display_results(result, query, collector, show_relevance)


@app.command("smart-search")
def smart_search(
    query: str = typer.Argument(..., help="Termo de busca"),
    cep: Optional[str] = typer.Option(None, "--cep", "-c", help="CEP para localizacao"),
    market: Optional[str] = typer.Option(None, "--market", "-m", help="Mercado especifico"),
    top: int = typer.Option(10, "--top", "-t", help="Numero de resultados a exibir"),
):
    """
    Busca inteligente com detalhes de ranking.
    
    Exemplos:
        price-collector smart-search "arroz 5kg"
        price-collector smart-search "leite" --top 5
    """
    markets = [market] if market else None
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task(f"Buscando '{query}' com ranking inteligente...", total=None)
        
        collector = PriceCollector()
        smart_result = run_async(
            collector.smart_search(query=query, cep=cep, markets=markets)
        )
    
    _display_smart_results(smart_result, top)


@app.command("compare")
def compare(
    query: str = typer.Argument(..., help="Termo de busca"),
    cep: Optional[str] = typer.Option(None, "--cep", "-c", help="CEP para localizacao"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Saida em formato JSON"),
    ranking: str = typer.Option("price", "--ranking", "-r", help="Estrategia: price, relevance, balanced"),
):
    """
    Compara precos entre mercados com ranking.
    
    Exemplos:
        price-collector compare "arroz tipo 1 5kg"
        price-collector compare "leite integral 1L" --cep 40000000
    """
    strategy = parse_ranking_strategy(ranking)
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task(f"Comparando precos para '{query}'...", total=None)
        
        collector = PriceCollector(ranking_strategy=strategy)
        comparison = run_async(collector.compare_prices(query=query, cep=cep))
    
    if json_output:
        console.print_json(json.dumps(comparison, indent=2, default=str))
        return
    
    _display_comparison(comparison)


@app.command("markets")
def list_markets():
    """Lista mercados disponiveis."""
    collector = PriceCollector()
    markets = collector.get_available_markets()
    
    table = Table(title="Mercados Disponiveis")
    table.add_column("ID", style="cyan")
    table.add_column("Nome", style="green")
    table.add_column("Status", style="yellow")
    table.add_column("Metodo", style="blue")
    
    for market in markets:
        table.add_row(market["id"], market["name"], market["status"], market["method"])
    
    console.print(table)


@app.command("stats")
def statistics(
    market: Optional[str] = typer.Option(None, "--market", "-m", help="Filtrar por mercado"),
    days: int = typer.Option(30, "--days", "-d", help="Periodo em dias"),
):
    """Exibe estatisticas de coleta."""
    collector = PriceCollector()
    stats = run_async(collector.get_statistics(market_id=market, days=days))
    
    console.print()
    console.print(f"[bold]Estatisticas dos ultimos {days} dias[/bold]")
    console.print()
    console.print(f"  Total de ofertas:      [cyan]{stats.get('total_offers', 0)}[/cyan]")
    console.print(f"  Ofertas normalizadas:  [green]{stats.get('normalized_offers', 0)}[/green]")
    console.print(f"  Queries unicas:        [yellow]{stats.get('unique_queries', 0)}[/yellow]")
    console.print(f"  Mercados:              [blue]{stats.get('markets_count', 0)}[/blue]")
    console.print(f"  Coletas realizadas:    [magenta]{stats.get('total_collections', 0)}[/magenta]")
    console.print()
    
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
    days: int = typer.Option(30, "--days", "-d", help="Periodo em dias"),
):
    """Mostra historico de precos de um produto."""
    collector = PriceCollector()
    history = run_async(collector.get_price_history(query=query, market_id=market, days=days))
    
    if not history:
        console.print(f"[yellow]Nenhum historico encontrado para '{query}'[/yellow]")
        return
    
    table = Table(title=f"Historico de Precos: {query}")
    table.add_column("Data", style="cyan")
    table.add_column("Mercado", style="green")
    table.add_column("Preco Medio", justify="right", style="yellow")
    table.add_column("Min", justify="right", style="blue")
    table.add_column("Max", justify="right", style="red")
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
    output: Path = typer.Argument(..., help="Arquivo de saida"),
    format: str = typer.Option("csv", "--format", "-f", help="Formato (csv ou parquet)"),
    query: Optional[str] = typer.Option(None, "--query", "-q", help="Filtrar por query"),
    market: Optional[str] = typer.Option(None, "--market", "-m", help="Filtrar por mercado"),
):
    """
    Exporta dados coletados para arquivo.
    
    Exemplos:
        price-collector export resultados.csv
        price-collector export dados.parquet --format parquet
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
            collector.export_results(output_path=output, format=format, query=query, market_id=market)
        )
    
    if path:
        console.print(f"[green]Dados exportados para: {path}[/green]")
    else:
        console.print("[yellow]Nenhum dado para exportar[/yellow]")


@app.command("version")
def version():
    """Exibe a versao do sistema."""
    from src import __version__
    
    console.print(f"[bold blue]Price Collector[/bold blue] v{__version__}")
    console.print("Sistema de coleta e comparacao de precos de supermercados")


def _display_results(result, query, collector, show_relevance=False):
    """Exibe resultados de busca formatados."""
    metadata = result.metadata
    offers = result.offers
    
    console.print()
    console.print("[bold]Resultado da Busca[/bold]")
    console.print(f"  Busca:    {metadata.search_query}")
    console.print(f"  CEP:      {metadata.cep or 'Nao informado'}")
    console.print(f"  Ranking:  {collector.ranking_strategy.value}")
    if metadata.duration_seconds:
        console.print(f"  Duracao:  {metadata.duration_seconds:.2f}s")
    console.print()
    
    if not offers:
        console.print("[yellow]Nenhum produto encontrado.[/yellow]")
        return
    
    table = Table(title=f"Encontrados {len(offers)} produtos")
    table.add_column("#", style="dim", width=4)
    table.add_column("Mercado", style="cyan", width=15)
    table.add_column("Produto", style="white", width=40, overflow="fold")
    table.add_column("Preco", justify="right", style="green", width=12)
    table.add_column("R$/unid", justify="right", style="yellow", width=14)
    
    if show_relevance:
        table.add_column("Rel", width=5)
    
    table.add_column("OK", width=4)
    
    for i, offer in enumerate(offers[:20], 1):
        status_icon = "S" if offer.is_comparable else "-"
        status_color = "green" if offer.is_comparable else "yellow"
        
        is_relevant = collector.pipeline.matcher.is_relevant(query, offer.title)
        relevance_icon = "S" if is_relevant else "N"
        relevance_color = "green" if is_relevant else "red"
        
        row = [
            str(i),
            offer.market_name[:15],
            offer.title[:40],
            offer.format_price(),
            offer.format_normalized_price(),
        ]
        
        if show_relevance:
            row.append(f"[{relevance_color}]{relevance_icon}[/{relevance_color}]")
        
        row.append(f"[{status_color}]{status_icon}[/{status_color}]")
        
        table.add_row(*row)
    
    console.print(table)
    
    if len(offers) > 20:
        console.print(f"[dim]... e mais {len(offers) - 20} produtos[/dim]")
    
    comparable = sum(1 for o in offers if o.is_comparable)
    relevant = sum(1 for o in offers if collector.pipeline.matcher.is_relevant(query, o.title))
    
    console.print()
    console.print(f"[bold]Resumo:[/bold] {len(offers)} produtos | {comparable} comparaveis | {relevant} relevantes")


def _display_smart_results(smart_result, top=10):
    """Exibe resultados de busca inteligente com scores."""
    console.print()
    console.print("[bold]Busca Inteligente[/bold]")
    console.print(f"  Busca:           {smart_result.query}")
    console.print(f"  Total encontrado: {smart_result.total_found}")
    console.print(f"  Total relevante:  {smart_result.total_relevant}")
    console.print()
    
    if not smart_result.has_results:
        console.print("[yellow]Nenhum produto encontrado.[/yellow]")
        return
    
    if smart_result.best_offer:
        best = smart_result.best_offer
        console.print("[bold]Melhor Oferta[/bold]")
        console.print(f"  Mercado:          [green]{best.offer.market_name}[/green]")
        console.print(f"  Produto:          {best.offer.title}")
        console.print(f"  Preco:            [green]{best.offer.price_display}[/green]")
        console.print(f"  Score Relevancia: [cyan]{best.relevance_score:.2f}[/cyan]")
        console.print(f"  Score Preco:      [yellow]{best.price_score:.2f}[/yellow]")
        console.print(f"  Score Final:      [magenta]{best.final_score:.2f}[/magenta]")
        console.print()
    
    table = Table(title=f"Top {min(top, len(smart_result.ranked_offers))} Resultados")
    table.add_column("#", style="dim", width=4)
    table.add_column("Mercado", style="cyan", width=12)
    table.add_column("Produto", style="white", width=35, overflow="fold")
    table.add_column("Preco", justify="right", style="green", width=14)
    table.add_column("Rel", justify="right", style="cyan", width=6)
    table.add_column("Preco", justify="right", style="yellow", width=6)
    table.add_column("Final", justify="right", style="magenta", width=6)
    table.add_column("Info", width=8)
    
    for ro in smart_result.get_top(top):
        flags = []
        if ro.is_relevant:
            flags.append("REL")
        if ro.is_best_price:
            flags.append("$")
        
        table.add_row(
            str(ro.rank),
            ro.offer.market_name[:12],
            ro.offer.title[:35],
            ro.offer.price_display,
            f"{ro.relevance_score:.2f}",
            f"{ro.price_score:.2f}",
            f"{ro.final_score:.2f}",
            " ".join(flags) if flags else "-",
        )
    
    console.print(table)


def _display_comparison(comparison):
    """Exibe comparacao de precos formatada."""
    console.print()
    console.print("[bold]Comparacao de Precos[/bold]")
    console.print(f"  Produto:  {comparison['query']}")
    console.print(f"  CEP:      {comparison.get('cep') or 'Nao informado'}")
    console.print(f"  Ranking:  {comparison.get('ranking_strategy', 'price_first')}")
    console.print(f"  Ofertas:  {comparison['total_offers']} ({comparison['comparable_offers']} comparaveis, {comparison.get('relevant_offers', 0)} relevantes)")
    console.print()
    
    if not comparison.get("best_offer"):
        console.print("[yellow]Nenhuma oferta comparavel encontrada.[/yellow]")
        return
    
    best = comparison["best_offer"]
    relevance_text = "Relevante" if best.get("is_relevant") else "Nao relevante"
    relevance_color = "green" if best.get("is_relevant") else "yellow"
    
    console.print("[bold]Melhor Oferta[/bold]")
    console.print(f"  Mercado:    [green]{best['market']}[/green]")
    console.print(f"  Produto:    {best['title']}")
    console.print(f"  Preco:      [green]{best['price_display']}[/green]")
    console.print(f"  Relevancia: [{relevance_color}]{relevance_text}[/{relevance_color}]")
    console.print(f"  URL:        {best['url'][:60]}...")
    console.print()
    
    if comparison.get("by_market"):
        table = Table(title="Comparacao por Mercado")
        table.add_column("Mercado", style="cyan")
        table.add_column("Ofertas", justify="right")
        table.add_column("Relevantes", justify="right", style="green")
        table.add_column("Menor Preco", justify="right", style="green")
        table.add_column("Menor R$/unid", justify="right", style="yellow")
        
        for market_id, data in comparison["by_market"].items():
            min_price = f"R$ {data['min_price']:.2f}" if data['min_price'] else "N/A"
            min_norm = f"R$ {data['min_normalized']:.2f}" if data['min_normalized'] else "N/A"
            
            table.add_row(
                data["market_name"],
                str(data["offers_count"]),
                str(data.get("relevant_count", 0)),
                min_price,
                min_norm,
            )
        
        console.print(table)
    
    if comparison.get("potential_savings"):
        console.print()
        console.print("[bold]Economias Potenciais[/bold]")
        for saving in comparison["potential_savings"][:3]:
            console.print(
                f"  Comprando no [green]{saving['best_market']}[/green] "
                f"ao inves do [red]{saving['compared_market']}[/red]: "
                f"[green]R$ {saving['absolute']:.2f}/{saving['unit']}[/green] "
                f"({saving['percentage']:.1f}%)"
            )


def _output_json(result, query, collector):
    """Exibe resultado em formato JSON."""
    offers_with_relevance = []
    for o in result.offers:
        offer_dict = o.model_dump(mode="json")
        offer_dict["is_relevant"] = collector.pipeline.matcher.is_relevant(query, o.title)
        offers_with_relevance.append(offer_dict)
    
    output = {
        "metadata": result.metadata.model_dump(mode="json"),
        "ranking_strategy": collector.ranking_strategy.value,
        "offers": offers_with_relevance,
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
    console.print(f"[green]Resultados salvos em: {output_path}[/green]")


def main():
    """Entry point principal."""
    app()


if __name__ == "__main__":
    main()