"""
Testes unitários para o Normalizer de quantidades.
"""

import pytest

from src.pipeline.normalizer import QuantityNormalizer
from src.core.types import Unit


class TestQuantityNormalizer:
    """Testes para QuantityNormalizer."""
    
    @pytest.fixture
    def normalizer(self) -> QuantityNormalizer:
        """Instância do normalizer."""
        return QuantityNormalizer()
    
    # TESTES: MASSA
    
    class TestMassExtraction:
        """Testes para extração de massa."""
        
        def test_quilograma_5kg(self, normalizer):
            """Testa extração de 5kg."""
            result = normalizer.extract_quantity("Arroz Tipo 1 5kg")
            
            assert result is not None
            assert result.value == 5.0
            assert result.unit == Unit.KILOGRAM
            assert result.base_value == 5.0
            assert result.base_unit == Unit.KILOGRAM
        
        def test_quilograma_1_5kg(self, normalizer):
            """Testa extração de 1,5kg."""
            result = normalizer.extract_quantity("Açúcar Refinado 1,5kg")
            
            assert result is not None
            assert result.value == 1.5
            assert result.unit == Unit.KILOGRAM
            assert result.base_value == 1.5
        
        def test_grama_500g(self, normalizer):
            """Testa extração de 500g e conversão para kg."""
            result = normalizer.extract_quantity("Café Pilão 500g")
            
            assert result is not None
            assert result.value == 500.0
            assert result.unit == Unit.GRAM
            assert result.base_value == 0.5
            assert result.base_unit == Unit.KILOGRAM
        
        def test_grama_250gr(self, normalizer):
            """Testa extração de 250gr."""
            result = normalizer.extract_quantity("Manteiga 250gr")
            
            assert result is not None
            assert result.value == 250.0
            assert result.base_value == 0.25
        
        def test_quilo_escrito(self, normalizer):
            """Testa 1 quilo escrito por extenso."""
            result = normalizer.extract_quantity("Feijão Carioca 1 quilo")
            
            assert result is not None
            assert result.value == 1.0
            assert result.base_unit == Unit.KILOGRAM
        
        def test_gramas_escrito(self, normalizer):
            """Testa gramas escrito por extenso."""
            result = normalizer.extract_quantity("Queijo 200 gramas")
            
            assert result is not None
            assert result.value == 200.0
            assert result.base_value == 0.2
    
    # TESTES: VOLUME
    
    class TestVolumeExtraction:
        """Testes para extração de volume."""
        
        def test_litro_1L(self, normalizer):
            """Testa extração de 1L."""
            result = normalizer.extract_quantity("Leite Integral 1L")
            
            assert result is not None
            assert result.value == 1.0
            assert result.unit == Unit.LITER
            assert result.base_value == 1.0
            assert result.base_unit == Unit.LITER
        
        def test_litro_2_litros(self, normalizer):
            """Testa extração de 2 litros."""
            result = normalizer.extract_quantity("Refrigerante 2 litros")
            
            assert result is not None
            assert result.value == 2.0
            assert result.base_unit == Unit.LITER
        
        def test_mililitro_500ml(self, normalizer):
            """Testa extração de 500ml e conversão para L."""
            result = normalizer.extract_quantity("Suco de Laranja 500ml")
            
            assert result is not None
            assert result.value == 500.0
            assert result.unit == Unit.MILLILITER
            assert result.base_value == 0.5
            assert result.base_unit == Unit.LITER
        
        def test_mililitro_200ml(self, normalizer):
            """Testa extração de 200ml."""
            result = normalizer.extract_quantity("Creme de Leite 200ml")
            
            assert result is not None
            assert result.value == 200.0
            assert result.base_value == 0.2
    
    # TESTES: PACKS
    
    class TestPackExtraction:
        """Testes para extração de packs."""
        
        def test_pack_12x350ml(self, normalizer):
            """Testa extração de pack 12x350ml."""
            result = normalizer.extract_quantity("Cerveja 350ml Pack c/ 12 Latas")
            
            assert result is not None
            # Deve extrair o 350ml com multiplicador 12
            # Total: 12 * 0.35L = 4.2L
        
        def test_pack_6x500ml(self, normalizer):
            """Testa extração de 6x500ml."""
            result = normalizer.extract_quantity("Água Mineral 6x500ml")
            
            assert result is not None
            assert result.multiplier == 6
            assert result.value == 500.0
            assert result.base_value == 0.5
            # Total: 6 * 0.5L = 3.0L
            assert result.total_base_value == 3.0
        
        def test_caixa_24_unidades(self, normalizer):
            """Testa extração de caixa com 24."""
            result = normalizer.extract_quantity("Leite caixa com 24 unidades 1L")
            
            assert result is not None
            # Deve ter multiplicador 24
    
    # TESTES: HORTIFRUTI
    
    class TestHortifrutiExtraction:
        """Testes para extração de hortifruti."""
        
        def test_por_kg(self, normalizer):
            """Testa 'por kg'."""
            result = normalizer.extract_quantity("Banana Prata por kg")
            
            assert result is not None
            assert result.value == 1.0
            assert result.base_unit == Unit.KILOGRAM
        
        def test_barra_kg(self, normalizer):
            """Testa '/kg'."""
            result = normalizer.extract_quantity("Tomate Italiano /kg")
            
            assert result is not None
            assert result.base_unit == Unit.KILOGRAM
        
        def test_kg_implicito(self, normalizer):
            """Testa 'kg' implícito."""
            result = normalizer.extract_quantity("Maçã Fuji kg")
            
            assert result is not None
            assert result.base_unit == Unit.KILOGRAM
    
    # TESTES: CASOS SEM QUANTIDADE
    
    class TestNoQuantity:
        """Testes para casos sem quantidade identificável."""
        
        def test_sem_quantidade(self, normalizer):
            """Testa produto sem quantidade."""
            result = normalizer.extract_quantity("Creme de Leite Nestlé")
            
            assert result is None
        
        def test_produto_generico(self, normalizer):
            """Testa produto genérico."""
            result = normalizer.extract_quantity("Esponja de Aço Bombril")
            
            assert result is None
        
        def test_string_vazia(self, normalizer):
            """Testa string vazia."""
            result = normalizer.extract_quantity("")
            
            assert result is None
        
        def test_none(self, normalizer):
            """Testa None."""
            result = normalizer.extract_quantity(None)
            
            assert result is None