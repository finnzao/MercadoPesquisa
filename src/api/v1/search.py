"""
Endpoints de busca de produtos.

Endpoints principais:
- GET /search - Busca simples
- POST /search - Busca com opções avançadas
- GET /search/compare - Comparação de preços
"""

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
    validate_markets,
)
from src.services import SearchRequest

router = APIRouter()


# SCHEMAS

class SearchQueryParams(BaseModel):
    """Parâmetros de busca via query string."""
    q: str = Field(..., min_length=2, max_length=100, description="Termo de busca")
    cep: Optional[str] = Field(None, description="CEP para localização (8 dígitos)")
    markets: Optional[str] = Field(None, description="Mercados separados por vírgula")
    limit: int = Field(20, ge=1, le=100, description="Limite de resultados")


class SearchBody(BaseModel):
    """Corpo da requisição de busca avançada."""
    query: str = Field(..., min_length=2, max_length=100, description="Termo de busca")
    cep: Optional[str] = Field(None, description="CEP para localização")
    markets: Optional[list[str]] = Field(None, description="Lista de mercados")
    max_pages: int = Field(1, ge=1, le=5, description="Máximo de páginas por mercado")
    include_unavailable: bool = Field(False, description="Incluir produtos indisponíveis")


class SearchResult(BaseModel):
    """Resultado de busca."""
    request_id: str
    query: str
    status: str
    total_results: int
    results: list[dict]
    best_offer: Optional[dict]
    metadata: dict
    errors: Optional[list[str]]


class CompareResult(BaseModel):
    """Resultado de comparação de preços."""
    query: str
    total_offers: int
    comparable_offers: int
    best_offer: Optional[dict]
    by_market: dict
    potential_savings: list[dict]


# ENDPOINTS

@router.get(
    "",
    response_model=SearchResult,
    summary="Busca produtos",
    description="""
Busca produtos em múltiplos supermercados.

**Parâmetros:**
- `q`: Termo de busca (obrigatório)
- `cep`: CEP para localização (opcional)
- `markets`: Mercados específicos separados por vírgula (opcional)
- `limit`: Limite de resultados (default: 20)

**Exemplo:**
```
GET /api/v1/search?q=arroz%205kg&cep=01310100
```

**Resposta:**
Retorna lista de produtos ordenados por relevância e preço,
incluindo o melhor preço encontrado.
    """,
    dependencies=[RateLimitDep],
)
async def search_products(
    search_service: SearchServiceDep,
    settings: SettingsDep,
    user_id: UserIdDep,
    q: str = Query(..., min_length=2, max_length=100, description="Termo de busca"),
    cep: Optional[str] = Query(None, description="CEP (8 dígitos)"),
    markets: Optional[str] = Query(None, description="Mercados (separados por vírgula)"),
    limit: int = Query(20, ge=1, le=100, description="Limite de resultados"),
):
    """
    Busca produtos em supermercados.
    
    Retorna produtos ordenados por relevância e preço normalizado.
    """
    # Valida parâmetros
    query = validate_query(q)
    cep_clean = validate_cep(cep)
    
    # Parse de mercados
    markets_list = None
    if markets:
        markets_list = [m.strip() for m in markets.split(",") if m.strip()]
        markets_list = validate_markets(markets_list, settings)
    
    # Executa busca
    request = SearchRequest(
        query=query,
        cep=cep_clean,
        markets=markets_list,
        user_id=user_id,
    )
    
    response = await search_service.search(request)
    
    # Aplica limite
    if response.results and len(response.results) > limit:
        response.results = response.results[:limit]
        response.total_results = limit
    
    return SearchResult(
        request_id=response.request_id,
        query=response.query,
        status=response.status,
        total_results=response.total_results,
        results=response.results,
        best_offer=response.best_offer,
        metadata={
            "markets_searched": response.markets_searched,
            "markets_failed": response.markets_failed,
            "cache_hit": response.cache_hit,
            "duration_ms": response.duration_ms,
        },
        errors=response.errors if response.errors else None,
    )


@router.post(
    "",
    response_model=SearchResult,
    summary="Busca avançada",
    description="""
Busca avançada com mais opções de configuração.

**Corpo da requisição:**
```json
{
    "query": "arroz 5kg",
    "cep": "01310100",
    "markets": ["carrefour", "atacadao"],
    "max_pages": 2,
    "include_unavailable": false
}
```

Use este endpoint quando precisar de:
- Múltiplas páginas de resultados
- Controle fino sobre mercados
- Incluir produtos indisponíveis
    """,
    dependencies=[RateLimitDep],
)
async def search_products_advanced(
    body: SearchBody,
    search_service: SearchServiceDep,
    settings: SettingsDep,
    user_id: UserIdDep,
):
    """
    Busca avançada com mais opções.
    """
    # Valida parâmetros
    query = validate_query(body.query)
    cep_clean = validate_cep(body.cep)
    markets_list = validate_markets(body.markets, settings)
    
    # Executa busca
    request = SearchRequest(
        query=query,
        cep=cep_clean,
        markets=markets_list,
        max_pages=body.max_pages,
        user_id=user_id,
    )
    
    response = await search_service.search(request)
    
    return SearchResult(
        request_id=response.request_id,
        query=response.query,
        status=response.status,
        total_results=response.total_results,
        results=response.results,
        best_offer=response.best_offer,
        metadata={
            "markets_searched": response.markets_searched,
            "markets_failed": response.markets_failed,
            "cache_hit": response.cache_hit,
            "duration_ms": response.duration_ms,
        },
        errors=response.errors if response.errors else None,
    )


@router.get(
    "/compare",
    response_model=CompareResult,
    summary="Compara preços",
    description="""
Compara preços de um produto entre mercados.

Retorna:
- Melhor oferta geral
- Menor preço por mercado
- Economia potencial

**Exemplo:**
```
GET /api/v1/search/compare?q=leite%20integral%201L
```
    """,
    dependencies=[RateLimitDep],
)
async def compare_prices(
    search_service: SearchServiceDep,
    settings: SettingsDep,
    user_id: UserIdDep,
    q: str = Query(..., min_length=2, max_length=100, description="Termo de busca"),
    cep: Optional[str] = Query(None, description="CEP (8 dígitos)"),
):
    """
    Compara preços entre mercados.
    """
    # Valida parâmetros
    query = validate_query(q)
    cep_clean = validate_cep(cep)
    
    # Executa busca
    request = SearchRequest(
        query=query,
        cep=cep_clean,
        user_id=user_id,
    )
    
    response = await search_service.search(request)
    
    if response.status == "error" and not response.results:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "no_results",
                "message": f"Nenhum resultado encontrado para: {query}",
            },
        )
    
    # Agrupa por mercado
    by_market = {}
    for result in response.results:
        market_id = result["market_id"]
        if market_id not in by_market:
            by_market[market_id] = {
                "market_name": result["market_name"],
                "offers_count": 0,
                "min_price": None,
                "min_normalized_price": None,
                "best_offer": None,
            }
        
        by_market[market_id]["offers_count"] += 1
        
        # Atualiza menor preço
        price = result.get("price")
        if price and (by_market[market_id]["min_price"] is None or price < by_market[market_id]["min_price"]):
            by_market[market_id]["min_price"] = price
            by_market[market_id]["best_offer"] = result
        
        normalized = result.get("normalized_price")
        if normalized and (by_market[market_id]["min_normalized_price"] is None or normalized < by_market[market_id]["min_normalized_price"]):
            by_market[market_id]["min_normalized_price"] = normalized
    
    # Calcula economia potencial
    savings = []
    if response.best_offer:
        best_price = response.best_offer.get("normalized_price") or response.best_offer.get("price")
        best_market = response.best_offer.get("market_name")
        
        for market_id, data in by_market.items():
            if data["market_name"] == best_market:
                continue
            
            other_price = data.get("min_normalized_price") or data.get("min_price")
            if other_price and best_price and other_price > best_price:
                diff = other_price - best_price
                pct = (diff / other_price) * 100
                savings.append({
                    "best_market": best_market,
                    "compared_market": data["market_name"],
                    "savings_absolute": round(diff, 2),
                    "savings_percentage": round(pct, 1),
                })
    
    # Ordena por economia
    savings.sort(key=lambda x: x["savings_absolute"], reverse=True)
    
    return CompareResult(
        query=query,
        total_offers=response.total_results,
        comparable_offers=sum(1 for r in response.results if r.get("is_comparable")),
        best_offer=response.best_offer,
        by_market=by_market,
        potential_savings=savings[:5],  # Top 5
    )


@router.get(
    "/quick",
    summary="Busca rápida",
    description="""
Busca rápida que retorna apenas o melhor preço.

Ideal para bots e integrações que precisam apenas do resultado principal.

**Exemplo:**
```
GET /api/v1/search/quick?q=banana%20prata
```
    """,
    dependencies=[RateLimitDep],
)
async def quick_search(
    search_service: SearchServiceDep,
    settings: SettingsDep,
    user_id: UserIdDep,
    q: str = Query(..., min_length=2, max_length=100, description="Termo de busca"),
    cep: Optional[str] = Query(None, description="CEP"),
):
    """
    Busca rápida - retorna apenas o melhor resultado.
    """
    query = validate_query(q)
    cep_clean = validate_cep(cep)
    
    request = SearchRequest(
        query=query,
        cep=cep_clean,
        user_id=user_id,
    )
    
    response = await search_service.search(request)
    
    if not response.best_offer:
        return {
            "found": False,
            "query": query,
            "message": "Nenhum resultado encontrado",
        }
    
    return {
        "found": True,
        "query": query,
        "product": response.best_offer["title"],
        "price": response.best_offer["price_formatted"],
        "normalized_price": response.best_offer.get("normalized_price_formatted"),
        "market": response.best_offer["market_name"],
        "url": response.best_offer["url"],
        "total_results": response.total_results,
        "cache_hit": response.cache_hit,
    }
