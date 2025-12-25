"""
Módulo de scrapers: coleta de dados dos mercados.
Arquitetura em plugins - cada mercado tem seu scraper.

NOTA: ExtraScraper foi removido pois o e-commerce Extra foi descontinuado.
"""

from src.scrapers.base import BaseScraper, ScraperResult
from src.scrapers.manager import ScraperManager
from src.scrapers.rate_limiter import RateLimiter
from src.scrapers.carrefour import CarrefourScraper
from src.scrapers.atacadao import AtacadaoScraper
from src.scrapers.pao_acucar import PaoDeAcucarScraper

# Registry de scrapers disponíveis (Extra removido - descontinuado)
SCRAPER_REGISTRY: dict[str, type[BaseScraper]] = {
    "carrefour": CarrefourScraper,
    "atacadao": AtacadaoScraper,
    "pao_acucar": PaoDeAcucarScraper,
}

__all__ = [
    "BaseScraper",
    "ScraperResult",
    "ScraperManager",
    "RateLimiter",
    "CarrefourScraper",
    "AtacadaoScraper",
    "PaoDeAcucarScraper",
    "SCRAPER_REGISTRY",
]