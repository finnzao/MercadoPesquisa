"""
Módulo de scrapers: coleta de dados dos mercados.
Arquitetura em plugins - cada mercado tem seu scraper.
"""

from src.scrapers.base import BaseScraper, ScraperResult
from src.scrapers.manager import ScraperManager
from src.scrapers.rate_limiter import RateLimiter
from src.scrapers.carrefour import CarrefourScraper
from src.scrapers.atacadao import AtacadaoScraper
from src.scrapers.pao_acucar import PaoDeAcucarScraper
from src.scrapers.extra import ExtraScraper

# Registry de scrapers disponíveis
SCRAPER_REGISTRY: dict[str, type[BaseScraper]] = {
    "carrefour": CarrefourScraper,
    "atacadao": AtacadaoScraper,
    "pao_acucar": PaoDeAcucarScraper,
    "extra": ExtraScraper,
}

__all__ = [
    "BaseScraper",
    "ScraperResult",
    "ScraperManager",
    "RateLimiter",
    "CarrefourScraper",
    "AtacadaoScraper",
    "PaoDeAcucarScraper",
    "ExtraScraper",
    "SCRAPER_REGISTRY",
]