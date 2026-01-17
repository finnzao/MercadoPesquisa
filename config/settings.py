"""
Configurações globais do sistema usando Pydantic Settings.
Carrega variáveis de ambiente e define valores padrão.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações principais do sistema."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    
    # ==================== AMBIENTE ====================
    env: Literal["development", "production", "testing"] = "development"
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    
    # ==================== API ====================
    api_title: str = "Price Tracker API"
    api_version: str = "1.0.0"
    api_prefix: str = "/api/v1"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    
    # ==================== MERCADOS ====================
    mercados_enabled: list[str] = [
        "carrefour", 
        "atacadao", 
        "pao_acucar", 
        "gbarbosa", 
        "samsclub", 
        "redemix", 
        "mercantil", 
        "hiperideal"
    ]
    
    # ==================== REDIS/CACHE ====================
    redis_url: str = "redis://localhost:6379/0"
    redis_password: str | None = None
    cache_enabled: bool = True
    cache_prefix: str = "price_tracker:"
    cache_ttl_seconds: int = 300
    
    # ==================== RATE LIMITING API ====================
    rate_limit_enabled: bool = True
    rate_limit_requests_per_minute: int = 60
    
    # ==================== CIRCUIT BREAKER ====================
    circuit_breaker_failure_threshold: int = 3
    circuit_breaker_recovery_timeout_seconds: int = 60
    circuit_breaker_half_open_max_calls: int = 1
    
    # ==================== COLLECTOR ====================
    collector_timeout_seconds: int = 30
    collector_global_timeout_seconds: int = 120
    collector_concurrent_limit: int = 5
    
    # ==================== RATE LIMITING SCRAPERS ====================
    rate_limit_default: int = Field(default=10, ge=1, le=60)
    rate_limit_carrefour: int = Field(default=8, ge=1, le=60)
    rate_limit_atacadao: int = Field(default=10, ge=1, le=60)
    rate_limit_pao_acucar: int = Field(default=8, ge=1, le=60)
    rate_limit_gbarbosa: int = Field(default=10, ge=1, le=60)
    rate_limit_samsclub: int = Field(default=10, ge=1, le=60)
    rate_limit_redemix: int = Field(default=10, ge=1, le=60)
    rate_limit_mercantil: int = Field(default=10, ge=1, le=60)
    rate_limit_hiperideal: int = Field(default=10, ge=1, le=60)
    rate_limit_extra: int = Field(default=8, ge=1, le=60)
    
    # ==================== TIMEOUTS ====================
    request_timeout: int = Field(default=30, ge=5, le=120)
    playwright_timeout: int = Field(default=60000, ge=10000, le=180000)
    
    # ==================== RETRIES ====================
    max_retries: int = Field(default=3, ge=1, le=10)
    retry_delay: int = Field(default=5, ge=1, le=30)
    
    # ==================== PATHS ====================
    base_path: Path = Field(default_factory=lambda: Path(__file__).parent.parent)
    data_path: Path = Field(default=Path("./data"))
    log_path: Path = Field(default=Path("./logs"))
    
    # ==================== USER AGENT ====================
    user_agent: str = Field(
        default=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    )
    
    # ==================== PLAYWRIGHT ====================
    headless: bool = True
    slow_mo: int = Field(default=0, ge=0, le=1000)
    
    # ==================== VALIDATORS ====================
    @field_validator("data_path", "log_path", mode="after")
    @classmethod
    def ensure_path_exists(cls, v: Path) -> Path:
        """Garante que os diretórios existam."""
        v.mkdir(parents=True, exist_ok=True)
        return v
    
    # ==================== METHODS ====================
    def get_rate_limit(self, market_id: str) -> int:
        """Retorna o rate limit específico para um mercado."""
        rate_limits = {
            "carrefour": self.rate_limit_carrefour,
            "atacadao": self.rate_limit_atacadao,
            "pao_acucar": self.rate_limit_pao_acucar,
            "gbarbosa": self.rate_limit_gbarbosa,
            "samsclub": self.rate_limit_samsclub,
            "redemix": self.rate_limit_redemix,
            "mercantil": self.rate_limit_mercantil,
            "hiperideal": self.rate_limit_hiperideal,
            "extra": self.rate_limit_extra,
        }
        return rate_limits.get(market_id, self.rate_limit_default)
    
    def is_market_enabled(self, market_id: str) -> bool:
        """Verifica se um mercado está habilitado."""
        return market_id in self.mercados_enabled


@lru_cache
def get_settings() -> Settings:
    """
    Retorna instância singleton das configurações.
    Usa cache para evitar recarregar .env múltiplas vezes.
    """
    return Settings()