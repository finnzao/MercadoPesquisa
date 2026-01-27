# src/services/cache/rate_limiter.py
"""
Rate Limiter usando Redis.

Implementa sliding window com contador para limitar
requisições por usuário, IP ou mercado.
"""

import asyncio
from dataclasses import dataclass
from typing import Optional, Tuple
from enum import Enum

import structlog

from .redis_client import RedisClient, get_redis_client

logger = structlog.get_logger()


class RateLimitType(str, Enum):
    """Tipos de rate limit."""
    USER = "user"
    IP = "ip"
    MARKET = "market"
    API_KEY = "api_key"
    GLOBAL = "global"


@dataclass
class RateLimitConfig:
    """Configuração de rate limit."""
    
    # Limites padrão por minuto
    requests_per_minute: int = 60
    
    # Limites específicos
    user_requests_per_minute: int = 60
    ip_requests_per_minute: int = 120
    api_key_requests_per_minute: int = 1000
    
    # Limites por mercado (para proteger os scrapers)
    market_requests_per_minute: dict = None
    
    # Janela de tempo em segundos
    window_seconds: int = 60
    
    # Se deve usar rate limiting
    enabled: bool = True
    
    def __post_init__(self):
        if self.market_requests_per_minute is None:
            # Limites padrão por mercado
            self.market_requests_per_minute = {
                "atacadao": 30,
                "carrefour": 30,
                "pao_acucar": 30,
                "gbarbosa": 20,
                "samsclub": 25,
                "redemix": 20,
                "mercantil": 20,
                "hiperideal": 20,
            }
    
    def get_market_limit(self, market_id: str) -> int:
        """Retorna limite para um mercado específico."""
        return self.market_requests_per_minute.get(
            market_id,
            20  # Limite padrão conservador
        )


@dataclass
class RateLimitResult:
    """Resultado de verificação de rate limit."""
    allowed: bool
    current_count: int
    limit: int
    remaining: int
    reset_in_seconds: int
    limit_type: RateLimitType
    identifier: str
    
    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "current_count": self.current_count,
            "limit": self.limit,
            "remaining": self.remaining,
            "reset_in_seconds": self.reset_in_seconds,
            "limit_type": self.limit_type.value,
        }
    
    def to_headers(self) -> dict:
        """Retorna headers HTTP para rate limiting."""
        return {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(self.remaining),
            "X-RateLimit-Reset": str(self.reset_in_seconds),
        }


class RateLimiter:
    """
    Rate limiter usando Redis com sliding window.
    
    Features:
    - Suporte a múltiplos tipos de limite (usuário, IP, mercado)
    - Configuração flexível de limites
    - Fallback gracioso quando Redis não disponível
    - Headers HTTP para resposta
    
    Exemplo de uso:
        limiter = RateLimiter()
        result = await limiter.check_user("user123")
        
        if not result.allowed:
            raise HTTPException(429, "Rate limit excedido")
    """
    
    def __init__(
        self,
        config: Optional[RateLimitConfig] = None,
        redis_client: Optional[RedisClient] = None,
    ):
        """
        Inicializa o rate limiter.
        
        Args:
            config: Configuração de limites
            redis_client: Cliente Redis (usa global se não informado)
        """
        self.config = config or RateLimitConfig()
        self._redis_client = redis_client
    
    async def _get_redis(self) -> RedisClient:
        """Obtém cliente Redis."""
        if self._redis_client is None:
            self._redis_client = await get_redis_client()
        return self._redis_client
    
    def _get_key(self, limit_type: RateLimitType, identifier: str) -> str:
        """Gera chave do rate limit."""
        return f"ratelimit:{limit_type.value}:{identifier}"
    
    async def is_allowed(
        self,
        identifier: str,
        limit_type: RateLimitType,
        limit: Optional[int] = None,
        window_seconds: Optional[int] = None,
    ) -> RateLimitResult:
        """
        Verifica se requisição é permitida.
        
        Args:
            identifier: Identificador único (user_id, IP, market_id)
            limit_type: Tipo de rate limit
            limit: Limite de requisições (usa config se não informado)
            window_seconds: Janela de tempo
            
        Returns:
            RateLimitResult com informações do limite
        """
        # Se rate limiting desabilitado, permite tudo
        if not self.config.enabled:
            return RateLimitResult(
                allowed=True,
                current_count=0,
                limit=-1,
                remaining=-1,
                reset_in_seconds=0,
                limit_type=limit_type,
                identifier=identifier,
            )
        
        # Define limite baseado no tipo
        if limit is None:
            if limit_type == RateLimitType.USER:
                limit = self.config.user_requests_per_minute
            elif limit_type == RateLimitType.IP:
                limit = self.config.ip_requests_per_minute
            elif limit_type == RateLimitType.API_KEY:
                limit = self.config.api_key_requests_per_minute
            elif limit_type == RateLimitType.MARKET:
                limit = self.config.get_market_limit(identifier)
            else:
                limit = self.config.requests_per_minute
        
        window = window_seconds or self.config.window_seconds
        
        # Tenta usar Redis
        redis_client = await self._get_redis()
        
        if not redis_client.is_connected:
            # Fallback: permite (fail-open)
            logger.debug(
                "rate_limit_redis_unavailable",
                identifier=identifier,
                message="Redis não disponível, permitindo requisição",
            )
            return RateLimitResult(
                allowed=True,
                current_count=0,
                limit=limit,
                remaining=limit,
                reset_in_seconds=0,
                limit_type=limit_type,
                identifier=identifier,
            )
        
        key = self._get_key(limit_type, identifier)
        
        # Incrementa contador
        current = await redis_client.incr(key, ttl=window)
        ttl = await redis_client.get_ttl(key)
        
        remaining = max(0, limit - current)
        allowed = current <= limit
        
        if not allowed:
            logger.warning(
                "rate_limit_exceeded",
                limit_type=limit_type.value,
                identifier=identifier,
                current=current,
                limit=limit,
                reset_in=ttl,
            )
        
        return RateLimitResult(
            allowed=allowed,
            current_count=current,
            limit=limit,
            remaining=remaining,
            reset_in_seconds=max(0, ttl),
            limit_type=limit_type,
            identifier=identifier,
        )
    
    # =========================================================================
    # Métodos de conveniência
    # =========================================================================
    
    async def check_user(
        self,
        user_id: str,
        limit: Optional[int] = None,
    ) -> RateLimitResult:
        """
        Verifica rate limit para um usuário.
        
        Args:
            user_id: ID do usuário
            limit: Limite customizado (opcional)
            
        Returns:
            RateLimitResult
        """
        return await self.is_allowed(
            identifier=user_id,
            limit_type=RateLimitType.USER,
            limit=limit,
        )
    
    async def check_ip(
        self,
        ip: str,
        limit: Optional[int] = None,
    ) -> RateLimitResult:
        """
        Verifica rate limit para um IP.
        
        Args:
            ip: Endereço IP
            limit: Limite customizado (opcional)
            
        Returns:
            RateLimitResult
        """
        return await self.is_allowed(
            identifier=ip,
            limit_type=RateLimitType.IP,
            limit=limit,
        )
    
    async def check_market(
        self,
        market_id: str,
        limit: Optional[int] = None,
    ) -> RateLimitResult:
        """
        Verifica rate limit para um mercado.
        
        Usado para proteger os scrapers de fazer
        muitas requisições em um mercado específico.
        
        Args:
            market_id: ID do mercado
            limit: Limite customizado (opcional)
            
        Returns:
            RateLimitResult
        """
        return await self.is_allowed(
            identifier=market_id,
            limit_type=RateLimitType.MARKET,
            limit=limit,
        )
    
    async def check_api_key(
        self,
        api_key: str,
        limit: Optional[int] = None,
    ) -> RateLimitResult:
        """
        Verifica rate limit para uma API key.
        
        Args:
            api_key: Chave da API
            limit: Limite customizado (opcional)
            
        Returns:
            RateLimitResult
        """
        return await self.is_allowed(
            identifier=api_key,
            limit_type=RateLimitType.API_KEY,
            limit=limit,
        )
    
    async def check_multiple(
        self,
        checks: list[Tuple[str, RateLimitType, Optional[int]]],
    ) -> Tuple[bool, list[RateLimitResult]]:
        """
        Verifica múltiplos rate limits de uma vez.
        
        Útil quando precisa verificar usuário E IP ao mesmo tempo.
        
        Args:
            checks: Lista de tuplas (identifier, limit_type, limit)
            
        Returns:
            Tupla (all_allowed, results)
        """
        results = []
        all_allowed = True
        
        for identifier, limit_type, limit in checks:
            result = await self.is_allowed(
                identifier=identifier,
                limit_type=limit_type,
                limit=limit,
            )
            results.append(result)
            
            if not result.allowed:
                all_allowed = False
        
        return all_allowed, results
    
    # =========================================================================
    # Administração
    # =========================================================================
    
    async def reset(
        self,
        identifier: str,
        limit_type: RateLimitType,
    ) -> bool:
        """
        Reseta o contador de rate limit.
        
        Args:
            identifier: Identificador
            limit_type: Tipo de limite
            
        Returns:
            True se resetou com sucesso
        """
        redis_client = await self._get_redis()
        
        if not redis_client.is_connected:
            return False
        
        key = self._get_key(limit_type, identifier)
        success = await redis_client.delete(key)
        
        if success:
            logger.info(
                "rate_limit_reset",
                limit_type=limit_type.value,
                identifier=identifier,
            )
        
        return success
    
    async def get_current_usage(
        self,
        identifier: str,
        limit_type: RateLimitType,
    ) -> Optional[int]:
        """
        Retorna uso atual sem incrementar.
        
        Args:
            identifier: Identificador
            limit_type: Tipo de limite
            
        Returns:
            Contagem atual ou None se não existe
        """
        redis_client = await self._get_redis()
        
        if not redis_client.is_connected:
            return None
        
        key = self._get_key(limit_type, identifier)
        value = await redis_client.get(key)
        
        return int(value) if value else 0
    
    async def get_stats(self) -> dict:
        """
        Retorna estatísticas do rate limiter.
        
        Returns:
            Dicionário com configuração e status
        """
        redis_client = await self._get_redis()
        
        return {
            "enabled": self.config.enabled,
            "redis_connected": redis_client.is_connected if redis_client else False,
            "limits": {
                "user_per_minute": self.config.user_requests_per_minute,
                "ip_per_minute": self.config.ip_requests_per_minute,
                "api_key_per_minute": self.config.api_key_requests_per_minute,
                "markets": self.config.market_requests_per_minute,
            },
            "window_seconds": self.config.window_seconds,
        }


# =========================================================================
# Instância global
# =========================================================================

_rate_limiter: Optional[RateLimiter] = None


async def get_rate_limiter(
    config: Optional[RateLimitConfig] = None,
) -> RateLimiter:
    """
    Retorna instância global do rate limiter.
    
    Args:
        config: Configuração (usa padrão se não informado)
        
    Returns:
        Instância do RateLimiter
    """
    global _rate_limiter
    
    if _rate_limiter is None:
        _rate_limiter = RateLimiter(config=config)
    
    return _rate_limiter


async def reset_rate_limiter() -> None:
    """Reseta a instância global do rate limiter."""
    global _rate_limiter
    _rate_limiter = None
