"""
Pipeline de processamento completo.
Orquestra parser, normalizer e calculator para processar produtos.
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


class ProcessingPipeline(LoggerMixin):
    """
    Pipeline de processamento de produtos.
    Fluxo: RawProduct -> NormalizedProduct -> PriceOffer
    """
    
    def __init__(self):
        """Inicializa o pipeline com seus componentes."""
        self.parser = ProductParser()
        self.normalizer = QuantityNormalizer()
        self.calculator = PriceCalculator()
    
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
    ) -> list[PriceOffer]:
        """
        Processa lote de produtos brutos.
        
        Args:
            raw_products: Lista de produtos brutos
            
        Returns:
            Lista de ofertas processadas (exclui falhas)
        """
        self.logger.info(
            "Processando lote de produtos",
            total=len(raw_products),
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
        
        return offers
    
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
    ) -> dict:
        """
        Calcula estatísticas de um conjunto de ofertas.
        
        Args:
            offers: Lista de ofertas processadas
            
        Returns:
            Dicionário com estatísticas
        """
        if not offers:
            return {
                "total": 0,
                "comparable": 0,
                "partial": 0,
                "failed": 0,
                "by_market": {},
                "by_status": {},
            }
        
        comparable = [o for o in offers if o.is_comparable]
        
        # Agrupa por mercado
        by_market = {}
        for offer in offers:
            market = offer.market_id
            if market not in by_market:
                by_market[market] = {"total": 0, "comparable": 0}
            by_market[market]["total"] += 1
            if offer.is_comparable:
                by_market[market]["comparable"] += 1
        
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
            "by_market": by_market,
            "by_status": by_status,
            "price_stats": price_stats,
        }
