"""
Pipeline de processamento completo.
Orquestra parser, normalizer, calculator e ranker para processar produtos.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from config.logging_config import LoggerMixin
from config.markets import get_market_config
from src.core.exceptions import ParsingError, NormalizationError
from src.core.models import (
    RawProduct,
    NormalizedProduct,
    PriceOffer,
    QuantityInfo,
)
from src.core.types import NormalizationStatus, Availability

from src.pipeline.parser import ProductParser
from src.pipeline.normalizer import QuantityNormalizer
from src.pipeline.price_calculator import PriceCalculator
from src.ranking import FuzzyMatcher, ResultRanker, RankingConfig, RankingStrategy, RankedOffer


class ProcessingPipeline(LoggerMixin):
    """
    Pipeline de processamento de produtos.
    Fluxo: RawProduct -> NormalizedProduct -> PriceOffer -> RankedOffer
    """
    
    def __init__(
        self,
        ranking_strategy: RankingStrategy = RankingStrategy.PRICE_FIRST,
        filter_irrelevant: bool = True,
    ):
        """
        Inicializa o pipeline com seus componentes.
        
        Args:
            ranking_strategy: Estratégia de ranking (PRICE_FIRST, RELEVANCE_FIRST, BALANCED)
            filter_irrelevant: Se True, filtra produtos não relevantes
        """
        self.parser = ProductParser()
        self.normalizer = QuantityNormalizer()
        self.calculator = PriceCalculator()
        self.matcher = FuzzyMatcher()
        
        # Configura o ranker
        self.ranking_config = RankingConfig(
            strategy=ranking_strategy,
            filter_irrelevant=filter_irrelevant,
        )
        self.ranker = ResultRanker(
            config=self.ranking_config,
            matcher=self.matcher,
        )
    
    def process_raw_product(
        self,
        raw_product: RawProduct,
    ) -> Optional[PriceOffer]:
        """
        Processa um produto bruto e retorna oferta de preço.
        
        Args:
            raw_product: Produto bruto do scraper
            
        Returns:
            PriceOffer ou None se falhar criticamente
        """
        self.logger.debug(
            "Processando produto",
            market=raw_product.market_id,
            title=raw_product.title[:50],
        )
        
        try:
            # Etapa 1: Parse dos dados brutos
            parsed_data = self._parse_product(raw_product)
            if parsed_data is None:
                return None
            
            # Etapa 2: Normalização de quantidade
            quantity_info = self._normalize_quantity(raw_product)
            
            # Etapa 3: Criar produto normalizado
            normalized_product = self._create_normalized_product(
                raw_product,
                parsed_data,
                quantity_info,
            )
            
            # Etapa 4: Calcular preço normalizado e criar oferta
            price_offer = self.calculator.create_price_offer(normalized_product)
            
            self.logger.debug(
                "Produto processado com sucesso",
                title=price_offer.title[:50],
                price=str(price_offer.price),
                normalized_price=str(price_offer.normalized_price) if price_offer.normalized_price else "N/A",
                status=price_offer.normalization_status.value,
            )
            
            return price_offer
            
        except Exception as e:
            self.logger.error(
                "Erro ao processar produto",
                error=str(e),
                market=raw_product.market_id,
                title=raw_product.title[:50],
            )
            return None
    
    def process_batch(
        self,
        raw_products: list[RawProduct],
        apply_ranking: bool = False,
        search_query: Optional[str] = None,
    ) -> list[PriceOffer]:
        """
        Processa lote de produtos brutos.
        
        Args:
            raw_products: Lista de produtos brutos
            apply_ranking: Se True, aplica ranking fuzzy aos resultados
            search_query: Query de busca para ranking (obrigatório se apply_ranking=True)
            
        Returns:
            Lista de ofertas processadas (exclui falhas)
        """
        self.logger.info(
            "Processando lote de produtos",
            total=len(raw_products),
            apply_ranking=apply_ranking,
        )
        
        offers = []
        success_count = 0
        error_count = 0
        
        for raw_product in raw_products:
            offer = self.process_raw_product(raw_product)
            if offer:
                offers.append(offer)
                success_count += 1
            else:
                error_count += 1
        
        self.logger.info(
            "Lote processado",
            total=len(raw_products),
            success=success_count,
            errors=error_count,
        )
        
        # Aplica ranking se solicitado
        if apply_ranking and search_query and offers:
            offers = self.apply_ranking(offers, search_query)
        
        return offers
    
    def apply_ranking(
        self,
        offers: list[PriceOffer],
        search_query: str,
    ) -> list[PriceOffer]:
        """
        Aplica ranking fuzzy às ofertas e retorna ordenadas.
        
        Args:
            offers: Lista de ofertas processadas
            search_query: Query de busca original
            
        Returns:
            Lista de ofertas ordenadas por relevância e preço
        """
        if not offers or not search_query:
            return offers
        
        self.logger.info(
            "Aplicando ranking fuzzy",
            total_offers=len(offers),
            query=search_query,
            strategy=self.ranking_config.strategy.value,
        )
        
        # Rankeia as ofertas
        ranked_offers = self.ranker.rank_offers(offers, search_query)
        
        # Extrai apenas as ofertas (sem metadados de ranking)
        sorted_offers = [ro.offer for ro in ranked_offers]
        
        relevant_count = sum(1 for ro in ranked_offers if ro.is_relevant)
        
        self.logger.info(
            "Ranking aplicado",
            total=len(sorted_offers),
            relevant=relevant_count,
            filtered_out=len(offers) - len(sorted_offers),
        )
        
        return sorted_offers
    
    def get_ranked_offers(
        self,
        offers: list[PriceOffer],
        search_query: str,
    ) -> list[RankedOffer]:
        """
        Retorna ofertas com metadados completos de ranking.
        
        Args:
            offers: Lista de ofertas processadas
            search_query: Query de busca original
            
        Returns:
            Lista de RankedOffer com scores e metadados
        """
        if not offers or not search_query:
            return []
        
        return self.ranker.rank_offers(offers, search_query)
    
    def filter_relevant_only(
        self,
        offers: list[PriceOffer],
        search_query: str,
    ) -> list[PriceOffer]:
        """
        Filtra apenas ofertas relevantes (primeira palavra igual).
        
        Args:
            offers: Lista de ofertas
            search_query: Query de busca
            
        Returns:
            Lista filtrada de ofertas relevantes
        """
        if not offers or not search_query:
            return offers
        
        relevant = []
        for offer in offers:
            if self.matcher.is_relevant(search_query, offer.title):
                relevant.append(offer)
        
        self.logger.debug(
            "Ofertas filtradas por relevância",
            total=len(offers),
            relevant=len(relevant),
        )
        
        return relevant
    
    def _parse_product(
        self,
        raw_product: RawProduct,
    ) -> Optional[dict]:
        """
        Faz parsing do produto bruto.
        
        Args:
            raw_product: Produto bruto
            
        Returns:
            Dados parseados ou None se falhar
        """
        try:
            return self.parser.parse_raw_product(raw_product)
        except ParsingError as e:
            self.logger.warning(
                "Falha no parsing",
                error=str(e),
                title=raw_product.title[:50],
            )
            return None
    
    def _normalize_quantity(
        self,
        raw_product: RawProduct,
    ) -> Optional[QuantityInfo]:
        """
        Extrai e normaliza quantidade do produto.
        
        Args:
            raw_product: Produto bruto
            
        Returns:
            QuantityInfo ou None se não encontrar
        """
        # Tenta extrair do título
        quantity_info = self.normalizer.extract_quantity(
            raw_product.title,
            raw_product,
        )
        
        # Se não encontrou no título, tenta na descrição
        if quantity_info is None and raw_product.description:
            quantity_info = self.normalizer.extract_quantity(
                raw_product.description,
                raw_product,
            )
        
        return quantity_info
    
    def _create_normalized_product(
        self,
        raw_product: RawProduct,
        parsed_data: dict,
        quantity_info: Optional[QuantityInfo],
    ) -> NormalizedProduct:
        """
        Cria produto normalizado a partir dos dados processados.
        
        Args:
            raw_product: Produto bruto original
            parsed_data: Dados parseados
            quantity_info: Informação de quantidade normalizada
            
        Returns:
            NormalizedProduct
        """
        # Obtém nome do mercado
        try:
            market_config = get_market_config(raw_product.market_id)
            market_name = market_config.display_name
        except ValueError:
            market_name = raw_product.market_id.capitalize()
        
        # Determina status de normalização
        if quantity_info is not None:
            status = NormalizationStatus.SUCCESS
        else:
            status = NormalizationStatus.PARTIAL
        
        return NormalizedProduct(
            market_id=raw_product.market_id,
            market_name=market_name,
            title=raw_product.title,
            price=parsed_data["price"],
            quantity=quantity_info,
            normalization_status=status,
            availability=parsed_data["availability"],
            url=raw_product.url,
            image_url=raw_product.image_url,
            search_query=raw_product.search_query,
            cep=raw_product.cep,
            collected_at=raw_product.collected_at,
            raw_product=raw_product,
        )
    
    def get_statistics(
        self,
        offers: list[PriceOffer],
        search_query: Optional[str] = None,
    ) -> dict:
        """
        Calcula estatísticas de um conjunto de ofertas.
        
        Args:
            offers: Lista de ofertas processadas
            search_query: Query para calcular relevância
            
        Returns:
            Dicionário com estatísticas
        """
        if not offers:
            return {
                "total": 0,
                "comparable": 0,
                "partial": 0,
                "failed": 0,
                "relevant": 0,
                "by_market": {},
                "by_status": {},
            }
        
        comparable = [o for o in offers if o.is_comparable]
        
        # Calcula relevância se query fornecida
        relevant_count = 0
        if search_query:
            for offer in offers:
                if self.matcher.is_relevant(search_query, offer.title):
                    relevant_count += 1
        
        # Agrupa por mercado
        by_market = {}
        for offer in offers:
            market = offer.market_id
            if market not in by_market:
                by_market[market] = {"total": 0, "comparable": 0, "relevant": 0}
            by_market[market]["total"] += 1
            if offer.is_comparable:
                by_market[market]["comparable"] += 1
            if search_query and self.matcher.is_relevant(search_query, offer.title):
                by_market[market]["relevant"] += 1
        
        # Agrupa por status
        by_status = {}
        for offer in offers:
            status = offer.normalization_status.value
            by_status[status] = by_status.get(status, 0) + 1
        
        # Estatísticas de preço
        price_stats = {}
        if comparable:
            prices = [o.normalized_price for o in comparable if o.normalized_price]
            if prices:
                price_stats = {
                    "min": min(prices),
                    "max": max(prices),
                    "avg": sum(prices) / len(prices),
                }
        
        return {
            "total": len(offers),
            "comparable": len(comparable),
            "partial": sum(1 for o in offers if o.normalization_status == NormalizationStatus.PARTIAL),
            "failed": sum(1 for o in offers if o.normalization_status == NormalizationStatus.FAILED),
            "relevant": relevant_count,
            "by_market": by_market,
            "by_status": by_status,
            "price_stats": price_stats,
        }