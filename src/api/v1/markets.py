"""
Endpoints de informações sobre mercados.

Endpoints:
- GET /markets - Lista mercados disponíveis
- GET /markets/{id} - Detalhes de um mercado
- GET /markets/status - Status dos circuit breakers
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from config.settings import get_settings
from config.markets import MARKETS_CONFIG
from config.markets import MarketStatus
from src.api.deps import SearchServiceDep, SettingsDep

router = APIRouter()


# ==================== SCHEMAS ====================

class MarketInfo(BaseModel):
    """Informações de um mercado."""
    id: str
    name: str
    status: str
    enabled: bool
    requires_cep: bool
    rate_limit: int


class MarketStatusInfo(BaseModel):
    """Status do circuit breaker de um mercado."""
    market_id: str
    state: str
    failure_count: int
    success_count: int
    last_failure: Optional[str]
    last_success: Optional[str]


# ==================== ENDPOINTS ====================

@router.get(
    "",
    summary="Lista mercados",
    description="""
Lista todos os mercados suportados pelo sistema.

Retorna:
- ID do mercado
- Nome de exibição
- Status (active, development, disabled)
- Se está habilitado nas configurações
- Se requer CEP
    """,
)
async def list_markets(settings: SettingsDep) -> list[MarketInfo]:
    """Lista todos os mercados disponíveis."""
    markets = []
    
    for market_id, config in MARKETS_CONFIG.items():
        markets.append(MarketInfo(
            id=market_id,
            name=config.display_name,
            status=config.status.value,
            enabled=settings.is_market_enabled(market_id),
            requires_cep=config.requires_cep,
            rate_limit=settings.get_rate_limit(market_id),
        ))
    
    # Ordena por nome
    markets.sort(key=lambda m: m.name)
    
    return markets


@router.get(
    "/enabled",
    summary="Lista mercados habilitados",
    description="Retorna apenas os mercados que estão habilitados para busca.",
)
async def list_enabled_markets(settings: SettingsDep) -> list[MarketInfo]:
    """Lista apenas mercados habilitados."""
    markets = []
    
    for market_id in settings.mercados_enabled:
        config = MARKETS_CONFIG.get(market_id)
        if config and config.status == MarketStatus.ACTIVE:
            markets.append(MarketInfo(
                id=market_id,
                name=config.display_name,
                status=config.status.value,
                enabled=True,
                requires_cep=config.requires_cep,
                rate_limit=settings.get_rate_limit(market_id),
            ))
    
    markets.sort(key=lambda m: m.name)
    return markets


@router.get(
    "/status",
    summary="Status dos mercados",
    description="""
Retorna o status dos circuit breakers de cada mercado.

Estados possíveis:
- `closed`: Normal - aceita requisições
- `open`: Bloqueado - muitas falhas recentes
- `half_open`: Testando recuperação

Use este endpoint para monitorar a saúde dos scrapers.
    """,
)
async def get_markets_status(
    search_service: SearchServiceDep,
) -> dict[str, MarketStatusInfo]:
    """Retorna status dos circuit breakers."""
    status_dict = search_service.get_circuit_breakers_status()
    
    return {
        market_id: MarketStatusInfo(**data)
        for market_id, data in status_dict.items()
    }


@router.get(
    "/{market_id}",
    summary="Detalhes do mercado",
    description="Retorna informações detalhadas de um mercado específico.",
)
async def get_market(
    market_id: str,
    settings: SettingsDep,
    search_service: SearchServiceDep,
):
    """Retorna detalhes de um mercado."""
    config = MARKETS_CONFIG.get(market_id)
    
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Mercado não encontrado: {market_id}",
        )
    
    # Status do circuit breaker
    cb_status = search_service.get_circuit_breakers_status().get(market_id, {})
    
    return {
        "id": market_id,
        "name": config.display_name,
        "base_url": config.base_url,
        "status": config.status.value,
        "enabled": settings.is_market_enabled(market_id),
        "requires_cep": config.requires_cep,
        "supports_pagination": config.supports_pagination,
        "max_pages": config.max_pages,
        "rate_limit": settings.get_rate_limit(market_id),
        "circuit_breaker": cb_status,
    }


@router.post(
    "/{market_id}/reset",
    summary="Reseta circuit breaker",
    description="""
Reseta o circuit breaker de um mercado.

Use quando um mercado foi corrigido e você quer forçar
uma nova tentativa antes do tempo de recovery.

**Atenção:** Use com cuidado em produção.
    """,
)
async def reset_market_circuit_breaker(
    market_id: str,
    search_service: SearchServiceDep,
    settings: SettingsDep,
):
    """Reseta circuit breaker de um mercado."""
    if not settings.is_market_enabled(market_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Mercado não encontrado ou desabilitado: {market_id}",
        )
    
    success = search_service.reset_circuit_breaker(market_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao resetar circuit breaker",
        )
    
    return {
        "status": "success",
        "message": f"Circuit breaker do mercado {market_id} resetado",
        "market_id": market_id,
    }
