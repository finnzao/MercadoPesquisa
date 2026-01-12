"""
Dependências compartilhadas da API.

Define dependências injetáveis via FastAPI Depends():
- Rate limiting
- Autenticação (futuro)
- Serviços
"""

from typing import Optional, Annotated

from fastapi import Depends, Header, HTTPException, Request, status

from config.settings import get_settings, Settings
from src.services import (
    SearchService,
    CacheService,
    RateLimiter,
    get_search_service,
    get_cache_service,
    get_rate_limiter,
)


# ==================== SETTINGS ====================

def get_settings_dep() -> Settings:
    """Dependência para obter configurações."""
    return get_settings()


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]


# ==================== SERVIÇOS ====================

async def get_search_service_dep() -> SearchService:
    """Dependência para obter SearchService."""
    return await get_search_service()


async def get_cache_service_dep() -> CacheService:
    """Dependência para obter CacheService."""
    return await get_cache_service()


async def get_rate_limiter_dep() -> RateLimiter:
    """Dependência para obter RateLimiter."""
    return await get_rate_limiter()


SearchServiceDep = Annotated[SearchService, Depends(get_search_service_dep)]
CacheServiceDep = Annotated[CacheService, Depends(get_cache_service_dep)]
RateLimiterDep = Annotated[RateLimiter, Depends(get_rate_limiter_dep)]


# ==================== RATE LIMITING ====================

async def check_rate_limit(
    request: Request,
    rate_limiter: RateLimiterDep,
    settings: SettingsDep,
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    x_telegram_user: Optional[str] = Header(None, alias="X-Telegram-User"),
):
    """
    Verifica rate limit para a requisição.
    
    Usa X-User-ID ou X-Telegram-User para identificar usuário.
    Fallback para IP se não informado.
    
    Headers de resposta:
    - X-RateLimit-Limit: Limite de requisições
    - X-RateLimit-Remaining: Requisições restantes
    - X-RateLimit-Reset: Segundos até reset
    
    Raises:
        HTTPException 429 se limite excedido
    """
    if not settings.rate_limit_enabled:
        return
    
    # Determina identificador do usuário
    user_id = x_user_id or x_telegram_user
    
    if user_id:
        identifier = f"user:{user_id}"
        limit = settings.rate_limit_requests_per_minute
    else:
        # Fallback para IP
        client_ip = request.client.host if request.client else "unknown"
        identifier = f"ip:{client_ip}"
        limit = settings.rate_limit_requests_per_minute * 2  # IP tem limite maior
    
    allowed, remaining, ttl = await rate_limiter.is_allowed(identifier, limit)
    
    # Adiciona headers de rate limit na resposta (via state)
    request.state.rate_limit_headers = {
        "X-RateLimit-Limit": str(limit),
        "X-RateLimit-Remaining": str(remaining),
        "X-RateLimit-Reset": str(ttl),
    }
    
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limit_exceeded",
                "message": f"Limite de requisições excedido. Tente novamente em {ttl} segundos.",
                "retry_after": ttl,
            },
            headers={
                "Retry-After": str(ttl),
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(ttl),
            },
        )


RateLimitDep = Depends(check_rate_limit)


# ==================== IDENTIFICAÇÃO DE USUÁRIO ====================

async def get_user_id(
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    x_telegram_user: Optional[str] = Header(None, alias="X-Telegram-User"),
) -> Optional[str]:
    """
    Extrai identificador do usuário dos headers.
    
    Prioridade:
    1. X-User-ID (genérico)
    2. X-Telegram-User (específico do bot)
    """
    return x_user_id or x_telegram_user


UserIdDep = Annotated[Optional[str], Depends(get_user_id)]


# ==================== VALIDADORES ====================

def validate_query(query: str) -> str:
    """
    Valida e normaliza termo de busca.
    
    Args:
        query: Termo de busca
        
    Returns:
        Query normalizada
        
    Raises:
        HTTPException 400 se inválida
    """
    query = query.strip()
    
    if not query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Termo de busca não pode ser vazio",
        )
    
    if len(query) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Termo de busca deve ter pelo menos 2 caracteres",
        )
    
    if len(query) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Termo de busca muito longo (máximo 100 caracteres)",
        )
    
    return query


def validate_cep(cep: Optional[str]) -> Optional[str]:
    """
    Valida e normaliza CEP.
    
    Args:
        cep: CEP em qualquer formato
        
    Returns:
        CEP normalizado (8 dígitos) ou None
        
    Raises:
        HTTPException 400 se inválido
    """
    if not cep:
        return None
    
    # Remove formatação
    cep_clean = "".join(c for c in cep if c.isdigit())
    
    if len(cep_clean) != 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"CEP inválido: {cep}. Deve ter 8 dígitos.",
        )
    
    return cep_clean


def validate_markets(markets: Optional[list[str]], settings: Settings) -> Optional[list[str]]:
    """
    Valida lista de mercados.
    
    Args:
        markets: Lista de IDs de mercados
        settings: Configurações
        
    Returns:
        Lista validada ou None
        
    Raises:
        HTTPException 400 se mercado inválido
    """
    if not markets:
        return None
    
    valid_markets = []
    invalid_markets = []
    
    for market in markets:
        if settings.is_market_enabled(market):
            valid_markets.append(market)
        else:
            invalid_markets.append(market)
    
    if invalid_markets:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_markets",
                "message": f"Mercados inválidos ou desabilitados: {', '.join(invalid_markets)}",
                "valid_markets": settings.mercados_enabled,
            },
        )
    
    return valid_markets if valid_markets else None
