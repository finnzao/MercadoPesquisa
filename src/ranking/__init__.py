"""
Módulo de ranking: fuzzy matching e priorização de resultados.

Este módulo fornece:
- FuzzyMatcher: Comparação simples de títulos (primeira palavra)
- ResultRanker: Sistema de ranking combinando relevância e preço
- RankingConfig: Configurações de estratégia de ranking

Uso básico:
    from src.ranking import FuzzyMatcher, ResultRanker, RankingStrategy
    
    # Verificar se produto é relevante
    matcher = FuzzyMatcher()
    if matcher.is_relevant("arroz 5kg", "Arroz Tipo 1 5kg"):
        print("Produto relevante!")
    
    # Rankear ofertas por preço
    ranker = ResultRanker()
    ranked = ranker.rank_offers(offers, "arroz 5kg")
    print(f"Melhor oferta: {ranked[0].offer.title}")
"""

from src.ranking.fuzzy_matcher import (
    FuzzyMatcher,
    MatchResult,
    fuzzy_match,
    is_relevant,
)
from src.ranking.result_ranker import (
    ResultRanker,
    RankingConfig,
    RankingStrategy,
    RankedOffer,
    SmartSearchResult,
)

__all__ = [
    # Fuzzy Matcher
    "FuzzyMatcher",
    "MatchResult",
    "fuzzy_match",
    "is_relevant",
    # Result Ranker
    "ResultRanker",
    "RankingConfig",
    "RankingStrategy",
    "RankedOffer",
    "SmartSearchResult",
]