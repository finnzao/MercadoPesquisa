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
from src.scrapers.gbarbosa import GBarbosaScraper
from src.scrapers.samsclub import SamsClubScraper
from src.scrapers.redemix import RedeMix
from src.scrapers.mercantil import MercantilAtacadoScraper
from src.scrapers.hiperideal import HiperidealScraper

# Scrapers disponíveis
SCRAPER_REGISTRY: dict[str, type] = {
    "carrefour": CarrefourScraper,
    "atacadao": AtacadaoScraper,
    "pao_acucar": PaoDeAcucarScraper,
    "gbarbosa": GBarbosaScraper,
    "samsclub": SamsClubScraper,
    "redemix": RedeMix,
    "mercantil": MercantilAtacadoScraper,
    "hiperideal": HiperidealScraper,
}

__all__ = [
    "BaseScraper",
    "ScraperResult",
    "ScraperManager",
    "RateLimiter",
    "CarrefourScraper",
    "AtacadaoScraper",
    "PaoDeAcucarScraper",
    "GBarbosaScraper",
    "SamsClubScraper",
    "RedeMix",
    "MercantilAtacadoScraper",
    "HiperidealScraper",
    "SCRAPER_REGISTRY",
]
