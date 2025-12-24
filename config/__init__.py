"""
Módulo de configuração do sistema.
Exporta as configurações principais para uso em todo o projeto.
"""

from config.settings import Settings, get_settings
from config.markets import MarketConfig, MARKETS_CONFIG
from config.logging_config import setup_logging

__all__ = [
    "Settings",
    "get_settings",
    "MarketConfig",
    "MARKETS_CONFIG",
    "setup_logging",
]