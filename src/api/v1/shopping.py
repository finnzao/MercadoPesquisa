"""
Shopping List API endpoints.
Processa listas de compras, texto livre e otimiza estratégias.
"""

import re
import asyncio
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..deps import (
    check_rate_limit,
    validate_cep,
    validate_markets,
    SearchServiceDep,
    SettingsDep,
)
from src.services.search_service import SearchRequest

router = APIRouter()


# ============================================================================
# Schemas
# ============================================================================

class ShoppingItemInput(BaseModel):
    """Item individual da lista de compras."""
    name: str = Field(..., min_length=2, max_length=100, description="Nome do produto")
    quantity: int = Field(default=1, ge=1, le=100, description="Quantidade")
    unit: Optional[str] = Field(default=None, description="Unidade (kg, L, un)")
    notes: Optional[str] = Field(default=None, max_length=200, description="Observações")


class ShoppingListInput(BaseModel):
    """Lista de compras estruturada."""
    items: list[ShoppingItemInput] = Field(..., min_length=1, max_length=50)
    cep: str = Field(..., pattern=r"^\d{8}$", description="CEP sem formatação")
    markets: Optional[list[str]] = Field(default=None, description="Mercados específicos")
    budget: Optional[float] = Field(default=None, ge=0, description="Orçamento máximo")


class ShoppingTextInput(BaseModel):
    """Lista de compras em texto livre."""
    text: str = Field(..., min_length=3, max_length=2000, description="Um item por linha")
    cep: str = Field(..., pattern=r"^\d{8}$")
    markets: Optional[list[str]] = Field(default=None)
    budget: Optional[float] = Field(default=None, ge=0)


class ProductResult(BaseModel):
    """Resultado de busca para um produto."""
    name: str
    brand: Optional[str] = None
    price: float
    unit_price: Optional[float] = None
    unit: Optional[str] = None
    market_id: str
    market_name: str
    url: Optional[str] = None
    available: bool = True


class ShoppingItemResult(BaseModel):
    """Resultado para um item da lista."""
    query: str
    quantity: int
    unit: Optional[str] = None
    best_offer: Optional[ProductResult] = None
    alternatives: list[ProductResult] = []
    total_price: Optional[float] = None
    status: str = "found"  # found, not_found, partial


class MarketSummary(BaseModel):
    """Resumo de compras em um mercado."""
    market_id: str
    market_name: str
    items_found: int
    items_total: int
    subtotal: float
    missing_items: list[str] = []


class OptimizationStrategy(BaseModel):
    """Uma estratégia de otimização."""
    name: str
    description: str
    total: float
    markets_count: int
    items_found: int
    items_total: int
    coverage_percent: float
    details: list[MarketSummary]


class ShoppingListResponse(BaseModel):
    """Resposta da lista de compras processada."""
    items: list[ShoppingItemResult]
    total_items: int
    items_found: int
    best_total: float
    budget: Optional[float] = None
    within_budget: Optional[bool] = None
    savings_from_comparison: float
    metadata: dict = {}


class OptimizeResponse(BaseModel):
    """Resposta da otimização de lista."""
    items: list[ShoppingItemResult]
    strategies: list[OptimizationStrategy]
    recommended: str
    potential_savings: float
    metadata: dict = {}


# ============================================================================
# Helper Functions
# ============================================================================

def parse_shopping_text(text: str) -> list[ShoppingItemInput]:
    """
    Parse texto livre em itens de compras.
    
    Formatos suportados:
    - "arroz 5kg"
    - "2x leite 1L"
    - "3 pacotes de café"
    - "feijão"
    """
    items = []
    lines = [line.strip() for line in text.strip().split("\n") if line.strip()]
    
    for line in lines:
        # Ignorar linhas de comentário
        if line.startswith("#") or line.startswith("//"):
            continue
        
        # Tentar extrair quantidade no início (2x, 3x, etc)
        quantity = 1
        match_qty = re.match(r"^(\d+)\s*[xX]\s*(.+)$", line)
        if match_qty:
            quantity = int(match_qty.group(1))
            line = match_qty.group(2)
        else:
            # Tentar "3 pacotes de" ou "2 "
            match_qty2 = re.match(r"^(\d+)\s+(?:(?:pacotes?|unidades?|latas?|caixas?|garrafas?)\s+(?:de\s+)?)?(.+)$", line, re.IGNORECASE)
            if match_qty2:
                quantity = int(match_qty2.group(1))
                line = match_qty2.group(2)
        
        # Extrair unidade no final (kg, L, ml, g, un)
        unit = None
        match_unit = re.search(r"\s+(\d+(?:[.,]\d+)?)\s*(kg|g|l|ml|un|und|unid)\.?$", line, re.IGNORECASE)
        if match_unit:
            # A unidade faz parte do nome do produto (ex: "leite 1L")
            unit = match_unit.group(2).lower()
            if unit in ("un", "und", "unid"):
                unit = "un"
            elif unit == "l":
                unit = "L"
        
        name = line.strip()
        if name:
            items.append(ShoppingItemInput(
                name=name,
                quantity=min(quantity, 100),  # Limitar quantidade
                unit=unit
            ))
    
    return items[:50]  # Limitar a 50 itens


async def search_item(
    search_service,
    item: ShoppingItemInput,
    cep: str,
    markets: Optional[list[str]],
    settings
) -> ShoppingItemResult:
    """Busca um item e retorna o resultado formatado."""
    try:
        request = SearchRequest(
            query=item.name,
            cep=cep,
            markets=markets or settings.mercados_enabled,
            max_pages=1
        )
        
        response = await search_service.search(request)
        
        if not response.results:
            return ShoppingItemResult(
                query=item.name,
                quantity=item.quantity,
                unit=item.unit,
                status="not_found"
            )
        
        # Melhor oferta
        best = response.results[0]
        best_offer = ProductResult(
            name=best.get("name", item.name),
            brand=best.get("brand"),
            price=best.get("price", 0),
            unit_price=best.get("unit_price"),
            unit=best.get("unit"),
            market_id=best.get("market_id", ""),
            market_name=best.get("market_name", ""),
            url=best.get("url"),
            available=best.get("available", True)
        )
        
        # Alternativas (até 5)
        alternatives = []
        for alt in response.results[1:6]:
            alternatives.append(ProductResult(
                name=alt.get("name", item.name),
                brand=alt.get("brand"),
                price=alt.get("price", 0),
                unit_price=alt.get("unit_price"),
                unit=alt.get("unit"),
                market_id=alt.get("market_id", ""),
                market_name=alt.get("market_name", ""),
                url=alt.get("url"),
                available=alt.get("available", True)
            ))
        
        total_price = best_offer.price * item.quantity
        
        return ShoppingItemResult(
            query=item.name,
            quantity=item.quantity,
            unit=item.unit,
            best_offer=best_offer,
            alternatives=alternatives,
            total_price=total_price,
            status="found"
        )
        
    except Exception as e:
        return ShoppingItemResult(
            query=item.name,
            quantity=item.quantity,
            unit=item.unit,
            status="error"
        )


def calculate_optimization_strategies(
    items: list[ShoppingItemResult]
) -> list[OptimizationStrategy]:
    """
    Calcula diferentes estratégias de compra.
    
    Estratégias:
    1. Melhor preço individual (pode exigir múltiplos mercados)
    2. Tudo em um mercado (cada mercado)
    3. Menor número de mercados com boa cobertura
    """
    strategies = []
    found_items = [i for i in items if i.best_offer is not None]
    total_items = len(items)
    
    if not found_items:
        return strategies
    
    # Estratégia 1: Melhor preço individual
    best_price_total = sum(i.total_price or 0 for i in found_items)
    markets_used = set(i.best_offer.market_id for i in found_items if i.best_offer)
    
    market_details = {}
    for item in found_items:
        if item.best_offer:
            mid = item.best_offer.market_id
            if mid not in market_details:
                market_details[mid] = {
                    "market_id": mid,
                    "market_name": item.best_offer.market_name,
                    "items": [],
                    "subtotal": 0
                }
            market_details[mid]["items"].append(item.query)
            market_details[mid]["subtotal"] += item.total_price or 0
    
    strategies.append(OptimizationStrategy(
        name="best_price",
        description="Melhor preço para cada item (pode exigir múltiplos mercados)",
        total=best_price_total,
        markets_count=len(markets_used),
        items_found=len(found_items),
        items_total=total_items,
        coverage_percent=round(len(found_items) / total_items * 100, 1),
        details=[
            MarketSummary(
                market_id=d["market_id"],
                market_name=d["market_name"],
                items_found=len(d["items"]),
                items_total=total_items,
                subtotal=round(d["subtotal"], 2)
            )
            for d in market_details.values()
        ]
    ))
    
    # Estratégia 2: Tudo em um mercado
    # Agrupa todas as ofertas por mercado
    market_offers: dict[str, dict] = {}
    
    for item in items:
        if item.best_offer:
            # Adicionar melhor oferta
            mid = item.best_offer.market_id
            if mid not in market_offers:
                market_offers[mid] = {
                    "market_id": mid,
                    "market_name": item.best_offer.market_name,
                    "items": {},
                    "subtotal": 0
                }
            market_offers[mid]["items"][item.query] = item.total_price or 0
            market_offers[mid]["subtotal"] += item.total_price or 0
            
            # Adicionar alternativas
            for alt in item.alternatives:
                amid = alt.market_id
                if amid not in market_offers:
                    market_offers[amid] = {
                        "market_id": amid,
                        "market_name": alt.market_name,
                        "items": {},
                        "subtotal": 0
                    }
                if item.query not in market_offers[amid]["items"]:
                    alt_total = alt.price * item.quantity
                    market_offers[amid]["items"][item.query] = alt_total
                    market_offers[amid]["subtotal"] += alt_total
    
    # Criar estratégia para cada mercado com boa cobertura (>50%)
    for mid, data in market_offers.items():
        coverage = len(data["items"]) / total_items
        if coverage >= 0.5:  # Pelo menos 50% dos itens
            missing = [i.query for i in items if i.query not in data["items"]]
            strategies.append(OptimizationStrategy(
                name=f"single_market_{mid}",
                description=f"Tudo no {data['market_name']}",
                total=round(data["subtotal"], 2),
                markets_count=1,
                items_found=len(data["items"]),
                items_total=total_items,
                coverage_percent=round(coverage * 100, 1),
                details=[
                    MarketSummary(
                        market_id=mid,
                        market_name=data["market_name"],
                        items_found=len(data["items"]),
                        items_total=total_items,
                        subtotal=round(data["subtotal"], 2),
                        missing_items=missing[:10]  # Limitar lista
                    )
                ]
            ))
    
    # Ordenar por total (menor primeiro)
    strategies.sort(key=lambda s: (s.total, -s.coverage_percent))
    
    return strategies


# ============================================================================
# Endpoints
# ============================================================================

@router.post(
    "/list",
    response_model=ShoppingListResponse,
    summary="Processar lista de compras",
    description="Processa uma lista de compras estruturada e encontra os melhores preços"
)
async def process_shopping_list(
    data: ShoppingListInput,
    search_service: SearchServiceDep,
    settings: SettingsDep,
    _: None = Depends(check_rate_limit)
):
    """Processa lista de compras estruturada."""
    # Validar mercados
    markets = validate_markets(data.markets, settings) if data.markets else None
    validate_cep(data.cep)
    
    # Buscar todos os itens em paralelo
    tasks = [
        search_item(search_service, item, data.cep, markets, settings)
        for item in data.items
    ]
    results = await asyncio.gather(*tasks)
    
    # Calcular totais
    items_found = sum(1 for r in results if r.status == "found")
    best_total = sum(r.total_price or 0 for r in results)
    
    # Calcular economia comparando com preço mais alto encontrado
    max_total = 0
    for r in results:
        if r.alternatives:
            max_price = max(alt.price for alt in r.alternatives)
            max_total += max_price * r.quantity
        elif r.best_offer:
            max_total += r.best_offer.price * r.quantity
    
    savings = max(0, max_total - best_total)
    
    # Verificar orçamento
    within_budget = None
    if data.budget is not None:
        within_budget = best_total <= data.budget
    
    return ShoppingListResponse(
        items=results,
        total_items=len(data.items),
        items_found=items_found,
        best_total=round(best_total, 2),
        budget=data.budget,
        within_budget=within_budget,
        savings_from_comparison=round(savings, 2),
        metadata={
            "cep": data.cep,
            "markets_searched": markets or settings.mercados_enabled
        }
    )


@router.post(
    "/text",
    response_model=ShoppingListResponse,
    summary="Processar texto livre",
    description="Processa lista de compras em texto livre (um item por linha)"
)
async def process_shopping_text(
    data: ShoppingTextInput,
    search_service: SearchServiceDep,
    settings: SettingsDep,
    _: None = Depends(check_rate_limit)
):
    """Processa lista de compras em texto livre."""
    # Parse do texto
    items = parse_shopping_text(data.text)
    
    if not items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nenhum item válido encontrado no texto"
        )
    
    # Validar mercados
    markets = validate_markets(data.markets, settings) if data.markets else None
    validate_cep(data.cep)
    
    # Buscar todos os itens
    tasks = [
        search_item(search_service, item, data.cep, markets, settings)
        for item in items
    ]
    results = await asyncio.gather(*tasks)
    
    # Calcular totais
    items_found = sum(1 for r in results if r.status == "found")
    best_total = sum(r.total_price or 0 for r in results)
    
    # Economia
    max_total = 0
    for r in results:
        if r.alternatives:
            max_price = max(alt.price for alt in r.alternatives)
            max_total += max_price * r.quantity
        elif r.best_offer:
            max_total += r.best_offer.price * r.quantity
    
    savings = max(0, max_total - best_total)
    
    within_budget = None
    if data.budget is not None:
        within_budget = best_total <= data.budget
    
    return ShoppingListResponse(
        items=results,
        total_items=len(items),
        items_found=items_found,
        best_total=round(best_total, 2),
        budget=data.budget,
        within_budget=within_budget,
        savings_from_comparison=round(savings, 2),
        metadata={
            "cep": data.cep,
            "markets_searched": markets or settings.mercados_enabled,
            "parsed_items": len(items)
        }
    )


@router.post(
    "/optimize",
    response_model=OptimizeResponse,
    summary="Otimizar lista de compras",
    description="Analisa diferentes estratégias de compra para otimizar gastos"
)
async def optimize_shopping_list(
    data: ShoppingListInput,
    search_service: SearchServiceDep,
    settings: SettingsDep,
    _: None = Depends(check_rate_limit)
):
    """
    Otimiza lista de compras comparando estratégias:
    - Melhor preço individual (múltiplos mercados)
    - Tudo em um mercado (por mercado)
    """
    # Validar
    markets = validate_markets(data.markets, settings) if data.markets else None
    validate_cep(data.cep)
    
    # Buscar todos os itens
    tasks = [
        search_item(search_service, item, data.cep, markets, settings)
        for item in data.items
    ]
    results = await asyncio.gather(*tasks)
    
    # Calcular estratégias
    strategies = calculate_optimization_strategies(results)
    
    if not strategies:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nenhum produto encontrado para otimização"
        )
    
    # Determinar melhor estratégia
    # Preferir best_price se economia > 10%, senão single_market com melhor cobertura
    best_price = next((s for s in strategies if s.name == "best_price"), None)
    single_markets = [s for s in strategies if s.name.startswith("single_market_")]
    
    recommended = "best_price"
    potential_savings = 0
    
    if best_price and single_markets:
        best_single = min(single_markets, key=lambda s: s.total)
        
        # Se diferença é pequena (<10%) e single_market tem boa cobertura, recomendar
        if best_single.coverage_percent >= 80:
            diff_percent = (best_single.total - best_price.total) / best_price.total * 100
            if diff_percent < 10:
                recommended = best_single.name
                potential_savings = 0
            else:
                potential_savings = best_single.total - best_price.total
        else:
            potential_savings = best_single.total - best_price.total if best_single else 0
    
    # Calcular economia potencial vs pior estratégia
    if strategies:
        worst_total = max(s.total for s in strategies)
        best_total = min(s.total for s in strategies)
        potential_savings = worst_total - best_total
    
    return OptimizeResponse(
        items=results,
        strategies=strategies[:10],  # Limitar a 10 estratégias
        recommended=recommended,
        potential_savings=round(potential_savings, 2),
        metadata={
            "cep": data.cep,
            "total_items": len(data.items),
            "items_found": sum(1 for r in results if r.status == "found"),
            "strategies_analyzed": len(strategies)
        }
    )


@router.post(
    "/quick",
    summary="Lista rápida",
    description="Versão simplificada para bots - retorna apenas totais"
)
async def quick_shopping_list(
    data: ShoppingTextInput,
    search_service: SearchServiceDep,
    settings: SettingsDep,
    _: None = Depends(check_rate_limit)
):
    """Versão rápida para bots - retorna resumo compacto."""
    items = parse_shopping_text(data.text)
    
    if not items:
        return {
            "success": False,
            "error": "Nenhum item válido"
        }
    
    markets = validate_markets(data.markets, settings) if data.markets else None
    
    tasks = [
        search_item(search_service, item, data.cep, markets, settings)
        for item in items
    ]
    results = await asyncio.gather(*tasks)
    
    found = [r for r in results if r.status == "found"]
    not_found = [r.query for r in results if r.status != "found"]
    
    total = sum(r.total_price or 0 for r in found)
    
    # Agrupar por mercado
    by_market: dict[str, float] = {}
    for r in found:
        if r.best_offer:
            mid = r.best_offer.market_name
            by_market[mid] = by_market.get(mid, 0) + (r.total_price or 0)
    
    return {
        "success": True,
        "total_items": len(items),
        "items_found": len(found),
        "total": round(total, 2),
        "by_market": {k: round(v, 2) for k, v in sorted(by_market.items(), key=lambda x: x[1])},
        "not_found": not_found[:5],
        "within_budget": total <= data.budget if data.budget else None
    }