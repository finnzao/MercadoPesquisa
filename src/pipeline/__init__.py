"""
Módulo de pipeline: parsing, normalização, cálculo de preços e ranking.
"""

from src.pipeline.parser import ProductParser
from src.pipeline.normalizer import QuantityNormalizer
from src.pipeline.price_calculator import PriceCalculator
from src.pipeline.pipeline import ProcessingPipeline

__all__ = [
    "ProductParser",
    "QuantityNormalizer",
    "PriceCalculator",
    "ProcessingPipeline",
]