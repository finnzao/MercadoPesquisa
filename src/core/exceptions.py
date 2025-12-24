"""
Hierarquia de exceções do sistema.
Todas as exceções herdam de PriceCollectorError para facilitar tratamento.
"""

from typing import Any, Optional

class PriceCollectorError(Exception):
    """
    Exceção base do sistema.
    Todas as exceções customizadas herdam desta classe.
    """
    
    def __init__(
        self,
        message: str,
        *,
        details: Optional[dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.cause = cause
    
    def __str__(self) -> str:
        base = self.message
        if self.details:
            base += f" | Details: {self.details}"
        if self.cause:
            base += f" | Caused by: {self.cause}"
        return base
    
    def to_dict(self) -> dict[str, Any]:
        """Serializa exceção para dicionário."""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "details": self.details,
            "cause": str(self.cause) if self.cause else None,
        }


# EXCEÇÕES DE SCRAPING

class ScraperError(PriceCollectorError):
    """Erro genérico de scraping."""
    
    def __init__(
        self,
        message: str,
        *,
        market_id: Optional[str] = None,
        url: Optional[str] = None,
        **kwargs,
    ):
        details = kwargs.pop("details", {})
        if market_id:
            details["market_id"] = market_id
        if url:
            details["url"] = url
        super().__init__(message, details=details, **kwargs)
        self.market_id = market_id
        self.url = url


class NetworkError(ScraperError):
    """Erro de rede (timeout, conexão recusada, etc)."""
    
    def __init__(
        self,
        message: str = "Erro de conexão com o servidor",
        *,
        status_code: Optional[int] = None,
        **kwargs,
    ):
        details = kwargs.pop("details", {})
        if status_code:
            details["status_code"] = status_code
        super().__init__(message, details=details, **kwargs)
        self.status_code = status_code


class RateLimitError(ScraperError):
    """Erro de rate limit excedido."""
    
    def __init__(
        self,
        message: str = "Rate limit excedido",
        *,
        retry_after: Optional[int] = None,
        **kwargs,
    ):
        details = kwargs.pop("details", {})
        if retry_after:
            details["retry_after_seconds"] = retry_after
        super().__init__(message, details=details, **kwargs)
        self.retry_after = retry_after


class BlockedError(ScraperError):
    """Erro quando o scraper é bloqueado (captcha, ban, etc)."""
    
    def __init__(
        self,
        message: str = "Acesso bloqueado pelo site",
        *,
        block_type: Optional[str] = None,
        **kwargs,
    ):
        details = kwargs.pop("details", {})
        if block_type:
            details["block_type"] = block_type
        super().__init__(message, details=details, **kwargs)
        self.block_type = block_type


class HTMLChangedError(ScraperError):
    """Erro quando a estrutura HTML mudou (seletores não encontrados)."""
    
    def __init__(
        self,
        message: str = "Estrutura HTML alterada",
        *,
        selector: Optional[str] = None,
        **kwargs,
    ):
        details = kwargs.pop("details", {})
        if selector:
            details["failed_selector"] = selector
        super().__init__(message, details=details, **kwargs)
        self.selector = selector


# EXCEÇÕES DE PARSING E NORMALIZAÇÃO

class ParsingError(PriceCollectorError):
    """Erro ao fazer parsing de dados extraídos."""
    
    def __init__(
        self,
        message: str,
        *,
        raw_data: Optional[str] = None,
        field: Optional[str] = None,
        **kwargs,
    ):
        details = kwargs.pop("details", {})
        if field:
            details["field"] = field
        if raw_data:
            # Limita tamanho para não poluir logs
            details["raw_data"] = raw_data[:200] if len(raw_data) > 200 else raw_data
        super().__init__(message, details=details, **kwargs)


class NormalizationError(PriceCollectorError):
    """Erro na normalização de quantidade/preço."""
    
    def __init__(
        self,
        message: str,
        *,
        product_title: Optional[str] = None,
        raw_quantity: Optional[str] = None,
        **kwargs,
    ):
        details = kwargs.pop("details", {})
        if product_title:
            details["product_title"] = product_title
        if raw_quantity:
            details["raw_quantity"] = raw_quantity
        super().__init__(message, details=details, **kwargs)


# EXCEÇÕES DE STORAGE

class StorageError(PriceCollectorError):
    """Erro de persistência de dados."""
    
    def __init__(
        self,
        message: str,
        *,
        storage_type: Optional[str] = None,
        path: Optional[str] = None,
        **kwargs,
    ):
        details = kwargs.pop("details", {})
        if storage_type:
            details["storage_type"] = storage_type
        if path:
            details["path"] = path
        super().__init__(message, details=details, **kwargs)


class DatabaseError(StorageError):
    """Erro específico de banco de dados."""
    pass


class FileStorageError(StorageError):
    """Erro específico de armazenamento em arquivo."""
    pass


# EXCEÇÕES DE VALIDAÇÃO

class ValidationError(PriceCollectorError):
    """Erro de validação de dados de entrada."""
    
    def __init__(
        self,
        message: str,
        *,
        field: Optional[str] = None,
        value: Optional[Any] = None,
        **kwargs,
    ):
        details = kwargs.pop("details", {})
        if field:
            details["field"] = field
        if value is not None:
            details["invalid_value"] = str(value)
        super().__init__(message, details=details, **kwargs)