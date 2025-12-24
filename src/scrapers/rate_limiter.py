"""
Rate limiter para controle de requisições por domínio.
Evita sobrecarga nos servidores e bloqueios.
"""

import asyncio
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

from config.logging_config import LoggerMixin


class RateLimiter(LoggerMixin):
    """
    Rate limiter baseado em token bucket por domínio.
    Controla requisições por minuto para cada mercado.
    """
    
    def __init__(self):
        """Inicializa o rate limiter."""
        # Timestamps das últimas requisições por domínio
        self._requests: dict[str, list[datetime]] = defaultdict(list)
        # Configuração de limite por domínio
        self._limits: dict[str, int] = {}
        # Lock para thread safety
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
    
    def configure(self, domain: str, requests_per_minute: int) -> None:
        """
        Configura limite para um domínio.
        
        Args:
            domain: Identificador do domínio/mercado
            requests_per_minute: Máximo de requisições por minuto
        """
        self._limits[domain] = requests_per_minute
        self.logger.debug(
            "Rate limit configurado",
            domain=domain,
            limit=requests_per_minute,
        )
    
    async def acquire(self, domain: str) -> None:
        """
        Aguarda até ter permissão para fazer requisição.
        
        Args:
            domain: Identificador do domínio/mercado
        """
        async with self._locks[domain]:
            limit = self._limits.get(domain, 10)  # Default: 10 req/min
            now = datetime.now()
            window_start = now - timedelta(minutes=1)
            
            # Remove requisições fora da janela de 1 minuto
            self._requests[domain] = [
                ts for ts in self._requests[domain]
                if ts > window_start
            ]
            
            # Se atingiu o limite, aguarda
            if len(self._requests[domain]) >= limit:
                oldest = self._requests[domain][0]
                wait_time = (oldest + timedelta(minutes=1) - now).total_seconds()
                
                if wait_time > 0:
                    self.logger.debug(
                        "Rate limit atingido, aguardando",
                        domain=domain,
                        wait_seconds=round(wait_time, 2),
                    )
                    await asyncio.sleep(wait_time)
            
            # Registra a requisição
            self._requests[domain].append(datetime.now())
    
    def get_current_usage(self, domain: str) -> dict:
        """
        Retorna uso atual do rate limit.
        
        Args:
            domain: Identificador do domínio
            
        Returns:
            Dicionário com estatísticas de uso
        """
        now = datetime.now()
        window_start = now - timedelta(minutes=1)
        
        recent_requests = [
            ts for ts in self._requests.get(domain, [])
            if ts > window_start
        ]
        
        limit = self._limits.get(domain, 10)
        
        return {
            "domain": domain,
            "current": len(recent_requests),
            "limit": limit,
            "available": max(0, limit - len(recent_requests)),
            "usage_percent": round(len(recent_requests) / limit * 100, 1),
        }
    
    def reset(self, domain: Optional[str] = None) -> None:
        """
        Reseta contadores do rate limiter.
        
        Args:
            domain: Domínio específico ou None para todos
        """
        if domain:
            self._requests[domain] = []
        else:
            self._requests.clear()


# Instância global do rate limiter
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Retorna instância singleton do rate limiter."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter