"""
Endpoints bots (WhatsApp/Telegram).

Características:
- Timeout agressivo (5 segundos)
- Early return com poucos resultados
- Resposta simplificada
- Cache agressivo
"""

import asyncio
from typing import Optional

from fastapi import APIRouter, Query, HTTPException, status
from pydantic import BaseModel, Field

from src.api.deps import (
    SearchServiceDep,
    SettingsDep,
    UserIdDep,
    RateLimitDep,
    validate_query,
    validate_cep,
)
from src.services.search_service import SearchRequest

router = APIRouter()


# SCHEMAS

class FastSearchResponse(BaseModel):
    """Resposta simplificada para bots."""
    found: bool
    query: str
    product: Optional[str] = None
    price: Optional[str] = None
    market: Optional[str] = None
    url: Optional[str] = None
    total_results: int = 0
    cache_hit: bool = False
    duration_ms: int = 0
    message: Optional[str] = None


class MultiItemRequest(BaseModel):
    """Requisição de múltiplos itens."""
    items: list[str] = Field(..., min_length=1, max_length=20)
    cep: Optional[str] = None


class MultiItemResponse(BaseModel):
    """Resposta de múltiplos itens."""
    success: bool
    total_items: int
    items_found: int
    total: str
    items: list[dict]
    duration_ms: int


# ENDPOINTS

@router.get(
    "/fast",
    response_model=FastSearchResponse,
    summary="Busca ultra-rápida",
    description="""
Busca otimizada para bots (WhatsApp/Telegram).

**Características:**
- Timeout de 5 segundos
- Retorna assim que encontrar 3 resultados
- Resposta simplificada
- Cache agressivo

**Ideal para:** Chatbots que precisam de resposta rápida.
    """,
    dependencies=[RateLimitDep],
)
async def fast_search(
    search_service: SearchServiceDep,
    settings: SettingsDep,
    user_id: UserIdDep,
    q: str = Query(..., min_length=2, max_length=100, description="Termo de busca"),
    cep: Optional[str] = Query(None, description="CEP (8 dígitos)"),
):
    """
    Busca ultra-rápida para bots.
    """
    # Valida parâmetros
    query = validate_query(q)
    cep_clean = validate_cep(cep)
    
    # Configuração agressiva para bots
    request = SearchRequest(
        query=query,
        cep=cep_clean,
        user_id=user_id,
        timeout_seconds=5.0,  # Timeout agressivo
        market_timeout_seconds=4.0,
        min_results=3,  # Early return
        enable_early_return=True,
        max_pages=1,
    )
    
    response = await search_service.search(request)
    
    # Resposta simplificada
    if not response.results:
        return FastSearchResponse(
            found=False,
            query=query,
            message="Nenhum resultado encontrado",
            cache_hit=response.cache_hit,
            duration_ms=response.duration_ms,
        )
    
    best = response.best_offer
    return FastSearchResponse(
        found=True,
        query=query,
        product=best["title"],
        price=best["price_formatted"],
        market=best["market_name"],
        url=best["url"],
        total_results=response.total_results,
        cache_hit=response.cache_hit,
        duration_ms=response.duration_ms,
    )


@router.post(
    "/fast/multi",
    response_model=MultiItemResponse,
    summary="Busca múltipla rápida",
    description="""
Busca múltiplos itens em paralelo.

**Características:**
- Processa todos os itens simultaneamente
- Timeout de 5 segundos por item
- Retorna total estimado

**Ideal para:** Processar lista de compras rapidamente.
    """,
    dependencies=[RateLimitDep],
)
async def fast_multi_search(
    body: MultiItemRequest,
    search_service: SearchServiceDep,
    settings: SettingsDep,
    user_id: UserIdDep,
):
    """
    Busca múltipla otimizada - processa todos os itens em paralelo.
    """
    from datetime import datetime
    
    start_time = datetime.now()
    
    # Valida CEP
    cep_clean = validate_cep(body.cep) if body.cep else None
    
    # Valida e limpa itens
    clean_items = []
    for item in body.items:
        try:
            clean_item = validate_query(item)
            clean_items.append(clean_item)
        except HTTPException:
            continue
    
    if not clean_items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nenhum item válido na lista",
        )
    
    # Cria todas as tasks em paralelo
    tasks = [
        search_service.search(SearchRequest(
            query=item,
            cep=cep_clean,
            user_id=user_id,
            timeout_seconds=5.0,
            market_timeout_seconds=4.0,
            min_results=1,
            enable_early_return=True,
            max_pages=1,
        ))
        for item in clean_items
    ]
    
    # Executa em paralelo
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Processa resultados
    items_result = []
    total = 0.0
    items_found = 0
    
    for item, result in zip(clean_items, results):
        if isinstance(result, Exception):
            items_result.append({
                "query": item,
                "found": False,
                "error": str(result),
            })
            continue
        
        if result.best_offer:
            price = result.best_offer["price"]
            total += price
            items_found += 1
            items_result.append({
                "query": item,
                "found": True,
                "product": result.best_offer["title"],
                "price": result.best_offer["price_formatted"],
                "market": result.best_offer["market_name"],
                "url": result.best_offer["url"],
            })
        else:
            items_result.append({
                "query": item,
                "found": False,
            })
    
    duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
    
    # Formata total
    total_formatted = f"R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    
    return MultiItemResponse(
        success=True,
        total_items=len(clean_items),
        items_found=items_found,
        total=total_formatted,
        items=items_result,
        duration_ms=duration_ms,
    )


@router.get(
    "/fast/health",
    summary="Health check do serviço rápido",
)
async def fast_health(search_service: SearchServiceDep):
    """Verifica saúde do serviço de busca rápida."""
    cache_stats = search_service.get_cache_stats()
    cb_status = search_service.get_circuit_breakers_status()
    
    healthy_markets = sum(
        1 for cb in cb_status.values()
        if cb["state"] == "closed"
    )
    
    return {
        "status": "healthy",
        "cache": cache_stats,
        "markets": {
            "total": len(cb_status),
            "healthy": healthy_markets,
            "degraded": len(cb_status) - healthy_markets,
        },
    }