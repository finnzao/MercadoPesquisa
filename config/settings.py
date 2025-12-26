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
    
    # Ambiente
    env: Literal["development", "production", "testing"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    
    # Rate Limiting (requisições por minuto)
    rate_limit_default: int = Field(default=10, ge=1, le=60)
    rate_limit_carrefour: int = Field(default=8, ge=1, le=60)
    rate_limit_atacadao: int = Field(default=10, ge=1, le=60)
    rate_limit_pao_acucar: int = Field(default=8, ge=1, le=60)
    rate_limit_extra: int = Field(default=8, ge=1, le=60)
    
    # Timeouts
    request_timeout: int = Field(default=30, ge=5, le=120)
    playwright_timeout: int = Field(default=60000, ge=10000, le=180000)
    
    # Retries
    max_retries: int = Field(default=3, ge=1, le=10)
    retry_delay: int = Field(default=5, ge=1, le=30)
    
    # Paths
    base_path: Path = Field(default_factory=lambda: Path(__file__).parent.parent)
    data_path: Path = Field(default=Path("./data"))
    log_path: Path = Field(default=Path("./logs"))
    
    # User Agent
    user_agent: str = Field(
        default=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    )
    
    # Playwright
    headless: bool = True
    slow_mo: int = Field(default=0, ge=0, le=1000)
    
    @field_validator("data_path", "log_path", mode="after")
    @classmethod
    def ensure_path_exists(cls, v: Path) -> Path:
        """Garante que os diretórios existam."""
        v.mkdir(parents=True, exist_ok=True)
        return v
    
    def get_rate_limit(self, market_id: str) -> int:
        """Retorna o rate limit específico para um mercado."""
        rate_limits = {
            "carrefour": self.rate_limit_carrefour,
            "atacadao": self.rate_limit_atacadao,
            "pao_acucar": self.rate_limit_pao_acucar,
            "extra": self.rate_limit_extra,
        }
        return rate_limits.get(market_id, self.rate_limit_default)


@lru_cache
def get_settings() -> Settings:
    """
    Retorna instância singleton das configurações.
    Usa cache para evitar recarregar .env múltiplas vezes.
    """
    return Settings()