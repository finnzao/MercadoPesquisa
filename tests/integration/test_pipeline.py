"""
Testes de integração para o Pipeline de processamento.
"""

import pytest

from src.pipeline import ProcessingPipeline
from src.core.models import RawProduct
from src.core.types import NormalizationStatus


class TestProcessingPipeline:
    """Testes de integração para ProcessingPipeline."""
    
    @pytest.fixture
    def pipeline(self) -> ProcessingPipeline:
        """Instância do pipeline."""
        return ProcessingPipeline()
    
    def test_process_raw_product_completo(self, pipeline, raw_product_arroz):
        """Testa processamento completo de produto."""
        offer = pipeline.process_raw_product(raw_product_arroz)
        
        assert offer is not None
        assert offer.market_id == "carrefour"
        assert offer.title == "Arroz Tipo 1 Tio João 5kg"
        assert offer.price > 0
        assert offer.normalized_price is not None
        assert offer.normalization_status == NormalizationStatus.SUCCESS
    
    def test_process_raw_product_sem_quantidade(self, pipeline, raw_product_sem_quantidade):
        """Testa processamento de produto sem quantidade."""
        offer = pipeline.process_raw_product(raw_product_sem_quantidade)
        
        assert offer is not None
        assert offer.price > 0
        assert offer.normalized_price is None
        assert offer.normalization_status == NormalizationStatus.PARTIAL
    
    def test_process_batch(self, pipeline, raw_products_batch):
        """Testa processamento em lote."""
        offers = pipeline.process_batch(raw_products_batch)
        
        assert len(offers) > 0
        assert len(offers) <= len(raw_products_batch)
        
        # Verifica que há tanto ofertas completas quanto parciais
        statuses = [o.normalization_status for o in offers]
        assert NormalizationStatus.SUCCESS in statuses or NormalizationStatus.PARTIAL in statuses
    
    def test_get_statistics(self, pipeline, raw_products_batch):
        """Testa estatísticas do processamento."""
        offers = pipeline.process_batch(raw_products_batch)
        stats = pipeline.get_statistics(offers)
        
        assert stats["total"] == len(offers)
        assert "comparable" in stats
        assert "by_market" in stats
        assert "by_status" in stats