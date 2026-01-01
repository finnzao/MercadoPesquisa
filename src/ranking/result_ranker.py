"""
Result Ranker: Sistema de ranking que combina relevância (fuzzy) e preço.

Prioriza produtos que:
1. São relevantes (primeira palavra igual à busca)
2. Têm o menor preço normalizado (R$/kg, R$/L)

Estratégias disponíveis:
- PRICE_FIRST: Prioriza menor preço entre os relevantes
- RELEVANCE_FIRST: Prioriza maior score de relevância
- BALANCED: Equilíbrio entre preço e relevância
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Optional, TYPE_CHECKING

from src.ranking.fuzzy_matcher import FuzzyMatcher, MatchResult

if TYPE_CHECKING:
    from src.core.models import PriceOffer


class RankingStrategy(str, Enum):
    """Estratégias de ranking disponíveis."""
    
    PRICE_FIRST = "price_first"
    RELEVANCE_FIRST = "relevance_first"
    BALANCED = "balanced"


@dataclass
class RankingConfig:
    """Configuração do sistema de ranking."""
    
    strategy: RankingStrategy = RankingStrategy.PRICE_FIRST
    relevance_weight: float = 0.4
    price_weight: float = 0.6
    filter_irrelevant: bool = True
    
    def __post_init__(self):
        """Ajusta pesos baseado na estratégia."""
        if self.strategy == RankingStrategy.PRICE_FIRST:
            self.relevance_weight = 0.2
            self.price_weight = 0.8
        elif self.strategy == RankingStrategy.RELEVANCE_FIRST:
            self.relevance_weight = 0.8
            self.price_weight = 0.2


@dataclass
class RankedOffer:
    """Oferta com informações de ranking."""
    
    offer: "PriceOffer"
    match_result: MatchResult
    relevance_score: float = 0.0
    price_score: float = 0.0
    final_score: float = 0.0
    rank: int = 0
    is_relevant: bool = False
    is_best_price: bool = False
    
    @property
    def price_for_comparison(self) -> Optional[Decimal]:
        """Retorna preço para comparação (normalizado se disponível)."""
        if self.offer.normalized_price is not None:
            return self.offer.normalized_price
        return self.offer.price
    
    def to_dict(self) -> dict:
        """Converte para dicionário."""
        return {
            "rank": self.rank,
            "title": self.offer.title,
            "market": self.offer.market_name,
            "market_id": self.offer.market_id,
            "price": float(self.offer.price),
            "normalized_price": float(self.offer.normalized_price) if self.offer.normalized_price else None,
            "price_display": self.offer.price_display,
            "relevance_score": round(self.relevance_score, 2),
            "price_score": round(self.price_score, 2),
            "final_score": round(self.final_score, 2),
            "is_relevant": self.is_relevant,
            "is_best_price": self.is_best_price,
            "quantity_match": self.match_result.quantity_match,
            "url": self.offer.url,
        }


@dataclass
class SmartSearchResult:
    """Resultado de busca inteligente com ranking."""
    
    query: str
    ranked_offers: list[RankedOffer]
    total_found: int
    total_relevant: int
    
    @property
    def best_offer(self) -> Optional[RankedOffer]:
        """Melhor oferta (primeiro no ranking)."""
        return self.ranked_offers[0] if self.ranked_offers else None
    
    @property
    def best_price_offer(self) -> Optional[RankedOffer]:
        """Oferta com melhor preço entre relevantes."""
        for ro in self.ranked_offers:
            if ro.is_best_price:
                return ro
        return self.best_offer
    
    @property
    def has_results(self) -> bool:
        """Indica se há resultados."""
        return len(self.ranked_offers) > 0
    
    def get_by_market(self, market_id: str) -> list[RankedOffer]:
        """Retorna ofertas de um mercado específico."""
        return [ro for ro in self.ranked_offers if ro.offer.market_id == market_id]
    
    def get_top(self, n: int = 5) -> list[RankedOffer]:
        """Retorna top N ofertas."""
        return self.ranked_offers[:n]
    
    def to_dict(self) -> dict:
        """Converte para dicionário."""
        return {
            "query": self.query,
            "total_found": self.total_found,
            "total_relevant": self.total_relevant,
            "best_offer": self.best_offer.to_dict() if self.best_offer else None,
            "offers": [ro.to_dict() for ro in self.ranked_offers],
        }


class ResultRanker:
    """
    Sistema de ranking de resultados.
    
    Combina relevância (fuzzy matching) com preço para criar
    um ranking que prioriza produtos relevantes E baratos.
    
    Uso:
        ranker = ResultRanker()
        ranked = ranker.rank_offers(offers, "arroz 5kg")
        
        for ro in ranked[:5]:
            print(f"{ro.rank}. {ro.offer.title} - {ro.offer.price_display}")
    """
    
    def __init__(
        self,
        config: Optional[RankingConfig] = None,
        matcher: Optional[FuzzyMatcher] = None,
    ):
        """
        Inicializa o ranker.
        
        Args:
            config: Configuração de ranking
            matcher: Matcher fuzzy (ou cria um novo)
        """
        self.config = config or RankingConfig()
        self.matcher = matcher or FuzzyMatcher()
    
    def rank_offers(
        self,
        offers: list["PriceOffer"],
        search_query: str,
    ) -> list[RankedOffer]:
        """
        Rankeia ofertas baseado em relevância e preço.
        
        Args:
            offers: Lista de ofertas para rankear
            search_query: Query de busca original
            
        Returns:
            Lista de RankedOffer ordenada (melhor primeiro)
        """
        if not offers:
            return []
        
        # Etapa 1: Calcular relevância para cada oferta
        ranked_offers = []
        for offer in offers:
            match_result = self.matcher.match(search_query, offer.title)
            
            ranked_offer = RankedOffer(
                offer=offer,
                match_result=match_result,
                relevance_score=match_result.score,
                is_relevant=match_result.is_relevant,
            )
            ranked_offers.append(ranked_offer)
        
        # Etapa 2: Filtrar não relevantes (se configurado)
        if self.config.filter_irrelevant:
            relevant = [ro for ro in ranked_offers if ro.is_relevant]
            
            # Se nenhum relevante, retorna top 5 por relevância
            if not relevant:
                ranked_offers.sort(key=lambda x: x.relevance_score, reverse=True)
                relevant = ranked_offers[:5]
            
            ranked_offers = relevant
        
        # Etapa 3: Calcular scores de preço
        self._calculate_price_scores(ranked_offers)
        
        # Etapa 4: Calcular score final
        self._calculate_final_scores(ranked_offers)
        
        # Etapa 5: Ordenar por score final
        ranked_offers.sort(key=lambda x: x.final_score, reverse=True)
        
        # Etapa 6: Atribuir ranks e flags
        self._assign_ranks_and_flags(ranked_offers)
        
        return ranked_offers
    
    def create_smart_result(
        self,
        offers: list["PriceOffer"],
        search_query: str,
        total_found: int,
    ) -> SmartSearchResult:
        """
        Cria resultado de busca inteligente.
        
        Args:
            offers: Lista de ofertas
            search_query: Query de busca
            total_found: Total de produtos encontrados (antes do filtro)
            
        Returns:
            SmartSearchResult
        """
        ranked = self.rank_offers(offers, search_query)
        total_relevant = sum(1 for ro in ranked if ro.is_relevant)
        
        return SmartSearchResult(
            query=search_query,
            ranked_offers=ranked,
            total_found=total_found,
            total_relevant=total_relevant,
        )
    
    def get_best_offer(
        self,
        offers: list["PriceOffer"],
        search_query: str,
    ) -> Optional[RankedOffer]:
        """Retorna a melhor oferta."""
        ranked = self.rank_offers(offers, search_query)
        return ranked[0] if ranked else None
    
    def _calculate_price_scores(self, ranked_offers: list[RankedOffer]) -> None:
        """
        Calcula scores de preço.
        Score = 1 - (preço / preço_máximo)
        Maior score = preço mais baixo
        """
        if not ranked_offers:
            return
        
        # Coleta preços válidos
        prices = []
        for ro in ranked_offers:
            price = ro.price_for_comparison
            if price is not None and price > 0:
                prices.append(float(price))
        
        if not prices:
            return
        
        min_price = min(prices)
        max_price = max(prices)
        price_range = max_price - min_price
        
        for ro in ranked_offers:
            price = ro.price_for_comparison
            
            if price is None or price <= 0:
                ro.price_score = 0.0
                continue
            
            if price_range == 0:
                # Todos os preços iguais
                ro.price_score = 1.0
            else:
                # Normaliza: 0 = mais caro, 1 = mais barato
                ro.price_score = 1.0 - ((float(price) - min_price) / price_range)
    
    def _calculate_final_scores(self, ranked_offers: list[RankedOffer]) -> None:
        """Calcula score final combinando relevância e preço."""
        for ro in ranked_offers:
            if self.config.strategy == RankingStrategy.PRICE_FIRST:
                # Preço é prioridade, mas só entre relevantes
                if ro.is_relevant:
                    ro.final_score = ro.price_score
                else:
                    ro.final_score = ro.price_score * 0.5
                    
            elif self.config.strategy == RankingStrategy.RELEVANCE_FIRST:
                # Relevância é prioridade
                ro.final_score = (
                    self.config.relevance_weight * ro.relevance_score +
                    self.config.price_weight * ro.price_score
                )
                
            else:  # BALANCED
                ro.final_score = (
                    self.config.relevance_weight * ro.relevance_score +
                    self.config.price_weight * ro.price_score
                )
    
    def _assign_ranks_and_flags(self, ranked_offers: list[RankedOffer]) -> None:
        """Atribui posições e flags especiais."""
        if not ranked_offers:
            return
        
        # Atribui ranks
        for idx, ro in enumerate(ranked_offers, 1):
            ro.rank = idx
        
        # Flag: melhor preço entre relevantes
        relevant = [ro for ro in ranked_offers if ro.is_relevant]
        if relevant:
            best_price = min(relevant, key=lambda x: x.price_for_comparison or Decimal("inf"))
            best_price.is_best_price = True