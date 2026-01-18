"""
Endpoint de busca múltipla de produtos.

Permite buscar múltiplos itens e opcionalmente otimizar
para encontrar o melhor mercado único (single_market).

Endpoints:
- POST /search/multi - Busca múltiplos itens
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from src.api.deps import (
    SearchServiceDep,
    SettingsDep,
    UserIdDep,
    RateLimitDep,
    validate_query,
    validate_cep,
    validate_markets,
)
from src.services.search_service import SearchRequest

router = APIRouter()


# ==================== SCHEMAS ====================

class MultiSearchRequest(BaseModel):
    """
    Requisição de busca múltipla.
    
    Exemplo simples:
    {
        "items": ["arroz 5kg", "feijão 1kg"]
    }
    
    Exemplo com otimização:
    {
        "items": ["arroz 5kg", "feijão 1kg", "óleo 900ml"],
        "cep": "01310100",
        "markets": ["carrefour", "atacadao"],
        "single_market": true
    }
    """
    items: list[str] = Field(
        ...,
        min_length=1,
        max_length=20,
        description="Lista de itens para buscar (1-20 itens)"
    )
    cep: Optional[str] = Field(
        None,
        description="CEP para localização (8 dígitos)"
    )
    markets: Optional[list[str]] = Field(
        None,
        description="Mercados específicos (null = todos)"
    )
    single_market: bool = Field(
        False,
        description="Se true, encontra o melhor mercado único para toda a lista"
    )
    

class ItemOffer(BaseModel):
    """Oferta de um item específico."""
    title: str
    price: float
    price_formatted: str
    normalized_price: Optional[float] = None
    normalized_price_formatted: Optional[str] = None
    market_id: str
    market_name: str
    url: str
    image_url: Optional[str] = None
    is_comparable: bool = True


class ItemResult(BaseModel):
    """Resultado de busca para um item."""
    query: str
    status: str  # "found", "not_found", "error"
    best_offer: Optional[ItemOffer] = None
    alternatives: list[ItemOffer] = []
    offers_count: int = 0


class MarketTotal(BaseModel):
    """Total de um mercado para todos os itens."""
    market_id: str
    market_name: str
    total: float
    total_formatted: str
    items_found: int
    items_missing: list[str] = []
    items: list[dict] = []  # Detalhes de cada item neste mercado
    coverage_percent: float


class MultiSearchResponse(BaseModel):
    """
    Resposta da busca múltipla.
    
    Quando single_market=false:
        - Retorna o melhor preço de cada item (pode ser mercados diferentes)
        
    Quando single_market=true:
        - Retorna qual mercado tem o menor total para TODA a lista
    """
    request_id: str
    mode: str  # "best_per_item" ou "single_market"
    
    # Resultados por item (sempre presente)
    items_results: list[ItemResult]
    
    # Resumo geral
    summary: dict
    
    # Presente apenas quando single_market=true
    winner: Optional[MarketTotal] = None
    comparison: Optional[list[MarketTotal]] = None
    savings: Optional[dict] = None
    
    # Metadados
    metadata: dict


# ==================== HELPERS ====================

def format_price(value: float) -> str:
    """Formata preço para exibição brasileira."""
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


async def search_single_item(
    search_service,
    query: str,
    cep: Optional[str],
    markets: Optional[list[str]],
) -> tuple[str, list[dict]]:
    """
    Busca um único item e retorna todos os resultados.
    
    Returns:
        Tupla (query, lista de ofertas como dicts)
    """
    try:
        request = SearchRequest(
            query=query.strip(),
            cep=cep,
            markets=markets,
            max_pages=1,
        )
        
        response = await search_service.search(request)
        return query, response.results
        
    except Exception as e:
        return query, []


def build_item_result(query: str, offers: list[dict]) -> ItemResult:
    """Constrói resultado de um item a partir das ofertas."""
    if not offers:
        return ItemResult(
            query=query,
            status="not_found",
            offers_count=0,
        )
    
    # Melhor oferta (primeiro resultado - já vem ordenado)
    best = offers[0]
    best_offer = ItemOffer(
        title=best.get("title", query),
        price=best.get("price", 0),
        price_formatted=best.get("price_formatted", format_price(best.get("price", 0))),
        normalized_price=best.get("normalized_price"),
        normalized_price_formatted=best.get("normalized_price_formatted"),
        market_id=best.get("market_id", ""),
        market_name=best.get("market_name", ""),
        url=best.get("url", ""),
        image_url=best.get("image_url"),
        is_comparable=best.get("is_comparable", False),
    )
    
    # Alternativas (próximos resultados)
    alternatives = []
    for alt in offers[1:6]:  # Até 5 alternativas
        alternatives.append(ItemOffer(
            title=alt.get("title", query),
            price=alt.get("price", 0),
            price_formatted=alt.get("price_formatted", format_price(alt.get("price", 0))),
            normalized_price=alt.get("normalized_price"),
            normalized_price_formatted=alt.get("normalized_price_formatted"),
            market_id=alt.get("market_id", ""),
            market_name=alt.get("market_name", ""),
            url=alt.get("url", ""),
            image_url=alt.get("image_url"),
            is_comparable=alt.get("is_comparable", False),
        ))
    
    return ItemResult(
        query=query,
        status="found",
        best_offer=best_offer,
        alternatives=alternatives,
        offers_count=len(offers),
    )


def calculate_market_totals(
    items_queries: list[str],
    all_offers: dict[str, list[dict]],
) -> dict[str, MarketTotal]:
    """
    Calcula o total de cada mercado considerando todos os itens.
    
    Args:
        items_queries: Lista de queries (itens)
        all_offers: Dict de query -> lista de ofertas
        
    Returns:
        Dict de market_id -> MarketTotal
    """
    # Agrupa ofertas por mercado
    # market_id -> { item_query -> melhor oferta do item neste mercado }
    market_items: dict[str, dict[str, dict]] = {}
    market_names: dict[str, str] = {}
    
    for query, offers in all_offers.items():
        for offer in offers:
            market_id = offer.get("market_id")
            if not market_id:
                continue
                
            market_names[market_id] = offer.get("market_name", market_id)
            
            if market_id not in market_items:
                market_items[market_id] = {}
            
            # Guarda a melhor oferta deste item neste mercado
            # (primeira encontrada, já vem ordenada por relevância/preço)
            if query not in market_items[market_id]:
                market_items[market_id][query] = offer
    
    # Calcula totais por mercado
    totals: dict[str, MarketTotal] = {}
    total_items = len(items_queries)
    
    for market_id, items_dict in market_items.items():
        items_found = []
        items_missing = []
        total = 0.0
        items_detail = []
        
        for query in items_queries:
            if query in items_dict:
                offer = items_dict[query]
                price = offer.get("price", 0)
                total += price
                items_found.append(query)
                items_detail.append({
                    "query": query,
                    "title": offer.get("title", query),
                    "price": price,
                    "price_formatted": format_price(price),
                })
            else:
                items_missing.append(query)
        
        coverage = (len(items_found) / total_items * 100) if total_items > 0 else 0
        
        totals[market_id] = MarketTotal(
            market_id=market_id,
            market_name=market_names.get(market_id, market_id),
            total=round(total, 2),
            total_formatted=format_price(total),
            items_found=len(items_found),
            items_missing=items_missing,
            items=items_detail,
            coverage_percent=round(coverage, 1),
        )
    
    return totals


def find_best_market(
    market_totals: dict[str, MarketTotal],
    min_coverage: float = 50.0,
) -> Optional[MarketTotal]:
    """
    Encontra o melhor mercado (menor total com cobertura mínima).
    
    Args:
        market_totals: Totais por mercado
        min_coverage: Cobertura mínima exigida (%)
        
    Returns:
        Melhor mercado ou None se nenhum atender
    """
    # Filtra mercados com cobertura mínima
    eligible = [
        mt for mt in market_totals.values()
        if mt.coverage_percent >= min_coverage
    ]
    
    if not eligible:
        # Se nenhum tem cobertura mínima, pega o com maior cobertura
        eligible = list(market_totals.values())
    
    if not eligible:
        return None
    
    # Ordena por: cobertura (desc), total (asc)
    eligible.sort(key=lambda x: (-x.coverage_percent, x.total))
    
    return eligible[0]


# ==================== ENDPOINT ====================

@router.post(
    "/multi",
    response_model=MultiSearchResponse,
    summary="Busca múltiplos itens",
    description="""
Busca múltiplos itens de uma vez, com opção de otimização.

## Modos de Operação

### `single_market=false` (padrão)
Retorna o **melhor preço de cada item**, mesmo que sejam de mercados diferentes.

**Exemplo:** Para "arroz, feijão, óleo":
- Arroz: R$ 24,99 (Atacadão) ← mais barato
- Feijão: R$ 7,99 (Carrefour) ← mais barato  
- Óleo: R$ 8,49 (GBarbosa) ← mais barato

⚠️ Total: R$ 41,47, mas precisa ir em 3 lugares!

### `single_market=true`
Encontra qual **mercado único** tem o menor valor **total** da lista.

**Exemplo:** Para "arroz, feijão, óleo":
- Carrefour: R$ 43,00 (todos os 3 itens)
- Atacadão: R$ 41,00 (todos os 3 itens) ✅ VENCEDOR
- GBarbosa: R$ 44,00 (todos os 3 itens)

✅ Vai em 1 lugar só!

## Uso via WhatsApp (sugestão de parsing)

| Mensagem | Parâmetros |
|----------|------------|
| "arroz 5kg" | items=["arroz 5kg"] |
| "arroz, feijão, óleo" | items=["arroz", "feijão", "óleo"] |
| "arroz, feijão /total" | items=[...], single_market=true |
| "arroz, feijão @carrefour" | items=[...], markets=["carrefour"] |
    """,
    dependencies=[RateLimitDep],
)
async def multi_search(
    body: MultiSearchRequest,
    search_service: SearchServiceDep,
    settings: SettingsDep,
    user_id: UserIdDep,
):
    """
    Busca múltiplos itens com opção de otimização por mercado único.
    """
    start_time = datetime.now()
    request_id = str(uuid4())[:8]
    
    # Validações
    if not body.items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Lista de itens não pode ser vazia",
        )
    
    # Valida e limpa itens
    clean_items = []
    for item in body.items:
        try:
            clean_item = validate_query(item)
            clean_items.append(clean_item)
        except HTTPException:
            continue  # Ignora itens inválidos
    
    if not clean_items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nenhum item válido na lista",
        )
    
    # Valida CEP e mercados
    cep_clean = validate_cep(body.cep) if body.cep else None
    markets_list = validate_markets(body.markets, settings) if body.markets else None
    
    # Busca todos os itens em paralelo
    tasks = [
        search_single_item(search_service, item, cep_clean, markets_list)
        for item in clean_items
    ]
    
    results = await asyncio.gather(*tasks)
    
    # Organiza resultados
    all_offers: dict[str, list[dict]] = {}
    items_results: list[ItemResult] = []
    
    for query, offers in results:
        all_offers[query] = offers
        items_results.append(build_item_result(query, offers))
    
    # Calcula estatísticas básicas
    items_found = sum(1 for r in items_results if r.status == "found")
    
    # Calcula o total do modo "best_per_item"
    best_per_item_total = sum(
        r.best_offer.price for r in items_results 
        if r.best_offer is not None
    )
    
    # Mercados únicos usados no modo best_per_item
    markets_used = list(set(
        r.best_offer.market_id for r in items_results 
        if r.best_offer is not None
    ))
    
    duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
    
    # Modo: best_per_item (padrão)
    if not body.single_market:
        return MultiSearchResponse(
            request_id=request_id,
            mode="best_per_item",
            items_results=items_results,
            summary={
                "total_items": len(clean_items),
                "items_found": items_found,
                "items_not_found": len(clean_items) - items_found,
                "estimated_total": round(best_per_item_total, 2),
                "estimated_total_formatted": format_price(best_per_item_total),
                "markets_involved": markets_used,
                "markets_count": len(markets_used),
            },
            winner=None,
            comparison=None,
            savings=None,
            metadata={
                "cep": cep_clean,
                "markets_filter": markets_list,
                "single_market": False,
                "duration_ms": duration_ms,
            },
        )
    
    # Modo: single_market
    market_totals = calculate_market_totals(clean_items, all_offers)
    
    if not market_totals:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nenhum mercado encontrado com os itens solicitados",
        )
    
    # Encontra o vencedor
    winner = find_best_market(market_totals, min_coverage=50.0)
    
    # Ordena comparação por total
    comparison = sorted(
        market_totals.values(),
        key=lambda x: (x.total if x.items_found > 0 else float('inf')),
    )
    
    # Calcula economia
    savings = {}
    if winner and len(comparison) > 1:
        worst = max(comparison, key=lambda x: x.total if x.items_found > 0 else 0)
        savings["vs_worst"] = round(worst.total - winner.total, 2)
        savings["vs_worst_formatted"] = format_price(worst.total - winner.total)
        savings["vs_worst_market"] = worst.market_name
        
        # Comparação com best_per_item
        diff_vs_best_per_item = winner.total - best_per_item_total
        savings["vs_best_per_item"] = round(diff_vs_best_per_item, 2)
        savings["vs_best_per_item_formatted"] = format_price(abs(diff_vs_best_per_item))
        savings["best_per_item_cheaper"] = diff_vs_best_per_item > 0
        
        if diff_vs_best_per_item > 0:
            savings["note"] = f"Comprando item a item economiza {format_price(diff_vs_best_per_item)}, mas precisa ir em {len(markets_used)} mercados"
        else:
            savings["note"] = f"Comprar tudo no {winner.market_name} é mais barato que item a item!"
    
    return MultiSearchResponse(
        request_id=request_id,
        mode="single_market",
        items_results=items_results,
        summary={
            "total_items": len(clean_items),
            "items_found": items_found,
            "items_not_found": len(clean_items) - items_found,
            "best_per_item_total": round(best_per_item_total, 2),
            "best_per_item_total_formatted": format_price(best_per_item_total),
            "single_market_total": winner.total if winner else None,
            "single_market_total_formatted": winner.total_formatted if winner else None,
            "winner_market": winner.market_name if winner else None,
            "markets_analyzed": len(market_totals),
        },
        winner=winner,
        comparison=comparison[:10],  # Top 10 mercados
        savings=savings,
        metadata={
            "cep": cep_clean,
            "markets_filter": markets_list,
            "single_market": True,
            "duration_ms": duration_ms,
        },
    )


@router.post(
    "/multi/quick",
    summary="Busca múltipla rápida (para bots)",
    description="Versão simplificada para integração com bots WhatsApp/Telegram",
    dependencies=[RateLimitDep],
)
async def multi_search_quick(
    body: MultiSearchRequest,
    search_service: SearchServiceDep,
    settings: SettingsDep,
    user_id: UserIdDep,
):
    """
    Versão compacta para bots - retorna resposta simplificada.
    """
    # Usa o endpoint principal
    try:
        full_response = await multi_search(body, search_service, settings, user_id)
    except HTTPException as e:
        return {
            "success": False,
            "error": e.detail,
        }
    
    # Simplifica resposta
    if body.single_market:
        winner = full_response.winner
        return {
            "success": True,
            "mode": "single_market",
            "total_items": full_response.summary["total_items"],
            "items_found": full_response.summary["items_found"],
            "winner": {
                "market": winner.market_name if winner else None,
                "total": winner.total_formatted if winner else None,
                "items_found": winner.items_found if winner else 0,
                "missing": winner.items_missing if winner else [],
            } if winner else None,
            "comparison_summary": [
                {"market": m.market_name, "total": m.total_formatted}
                for m in (full_response.comparison or [])[:5]
            ],
            "tip": full_response.savings.get("note") if full_response.savings else None,
        }
    else:
        return {
            "success": True,
            "mode": "best_per_item",
            "total_items": full_response.summary["total_items"],
            "items_found": full_response.summary["items_found"],
            "total": full_response.summary["estimated_total_formatted"],
            "markets_count": full_response.summary["markets_count"],
            "items": [
                {
                    "query": r.query,
                    "found": r.status == "found",
                    "price": r.best_offer.price_formatted if r.best_offer else None,
                    "market": r.best_offer.market_name if r.best_offer else None,
                }
                for r in full_response.items_results
            ],
        }