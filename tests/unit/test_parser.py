"""
Testes unitários para o Parser de produtos.
"""

from decimal import Decimal

import pytest

from src.pipeline.parser import ProductParser
from src.core.exceptions import ParsingError
from src.core.types import Availability


class TestProductParser:
    """Testes para ProductParser."""
    
    @pytest.fixture
    def parser(self) -> ProductParser:
        """Instância do parser."""
        return ProductParser()
    
    # TESTES: parse_price
    
    class TestParsePrice:
        """Testes para parsing de preço."""
        
        def test_preco_formato_brasileiro_completo(self, parser):
            """Testa R$ 12,99."""
            result = parser.parse_price("R$ 12,99")
            assert result == Decimal("12.99")
        
        def test_preco_formato_brasileiro_sem_espaco(self, parser):
            """Testa R$12,99."""
            result = parser.parse_price("R$12,99")
            assert result == Decimal("12.99")
        
        def test_preco_apenas_numero_virgula(self, parser):
            """Testa 12,99."""
            result = parser.parse_price("12,99")
            assert result == Decimal("12.99")
        
        def test_preco_formato_ponto(self, parser):
            """Testa 12.99."""
            result = parser.parse_price("12.99")
            assert result == Decimal("12.99")
        
        def test_preco_com_milhar(self, parser):
            """Testa R$ 1.234,56."""
            result = parser.parse_price("R$ 1.234,56")
            assert result == Decimal("1234.56")
        
        def test_preco_inteiro(self, parser):
            """Testa R$ 10,00."""
            result = parser.parse_price("R$ 10,00")
            assert result == Decimal("10.00")
        
        def test_preco_centavos(self, parser):
            """Testa R$ 0,99."""
            result = parser.parse_price("R$ 0,99")
            assert result == Decimal("0.99")
        
        def test_preco_com_texto_extra(self, parser):
            """Testa preço com texto adicional."""
            result = parser.parse_price("Por apenas R$ 29,90 à vista")
            assert result == Decimal("29.90")
        
        def test_preco_vazio_raises(self, parser):
            """Testa que string vazia levanta exceção."""
            with pytest.raises(ParsingError):
                parser.parse_price("")
        
        def test_preco_sem_digitos_raises(self, parser):
            """Testa que string sem dígitos levanta exceção."""
            with pytest.raises(ParsingError):
                parser.parse_price("sem preço")
    
    # TESTES: parse_unit_price
    
    class TestParseUnitPrice:
        """Testes para parsing de preço unitário."""
        
        def test_preco_por_kg(self, parser):
            """Testa R$ 5,98/kg."""
            result = parser.parse_unit_price("R$ 5,98/kg")
            assert result == (Decimal("5.98"), "kg")
        
        def test_preco_por_litro(self, parser):
            """Testa R$ 6,49/L."""
            result = parser.parse_unit_price("R$ 6,49/L")
            assert result == (Decimal("6.49"), "l")
        
        def test_preco_por_unidade(self, parser):
            """Testa R$ 2,99/un."""
            result = parser.parse_unit_price("R$ 2,99/un")
            assert result == (Decimal("2.99"), "un")
        
        def test_preco_unitario_none(self, parser):
            """Testa retorno None para entrada None."""
            result = parser.parse_unit_price(None)
            assert result is None
        
        def test_preco_unitario_invalido(self, parser):
            """Testa retorno None para formato inválido."""
            result = parser.parse_unit_price("preço normal")
            assert result is None
    
    # TESTES: parse_availability
    
    class TestParseAvailability:
        """Testes para parsing de disponibilidade."""
        
        def test_disponivel(self, parser):
            """Testa texto indicando disponível."""
            assert parser.parse_availability("Disponível") == Availability.AVAILABLE
            assert parser.parse_availability("Em estoque") == Availability.AVAILABLE
            assert parser.parse_availability("Adicionar ao carrinho") == Availability.AVAILABLE
        
        def test_indisponivel(self, parser):
            """Testa texto indicando indisponível."""
            assert parser.parse_availability("Indisponível") == Availability.UNAVAILABLE
            assert parser.parse_availability("Esgotado") == Availability.UNAVAILABLE
            assert parser.parse_availability("Sem estoque") == Availability.UNAVAILABLE
        
        def test_poucas_unidades(self, parser):
            """Testa texto indicando poucas unidades."""
            assert parser.parse_availability("Últimas unidades") == Availability.LOW_STOCK
            assert parser.parse_availability("Restam poucos") == Availability.LOW_STOCK
        
        def test_desconhecido(self, parser):
            """Testa texto não reconhecido."""
            assert parser.parse_availability("Texto qualquer") == Availability.UNKNOWN
            assert parser.parse_availability(None) == Availability.UNKNOWN
            assert parser.parse_availability("") == Availability.UNKNOWN