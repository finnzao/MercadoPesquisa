"""
Parser de dados brutos extraídos dos scrapers.
Converte strings de preço, quantidade e disponibilidade em tipos estruturados.
"""

import re
from decimal import Decimal, InvalidOperation
from typing import Optional

from config.logging_config import LoggerMixin
from src.core.constants import PRICE_PATTERNS, UNIT_PRICE_PATTERN
from src.core.exceptions import ParsingError
from src.core.models import RawProduct
from src.core.types import Availability


class ProductParser(LoggerMixin):
    """
    Parser de produtos brutos.
    Extrai e converte dados de strings para tipos apropriados.
    """
    
    def parse_price(self, price_raw: str) -> Decimal:
        """
        Converte string de preço para Decimal.
        
        Args:
            price_raw: String com preço (ex: "R$ 12,99", "12.99")
            
        Returns:
            Preço como Decimal
            
        Raises:
            ParsingError: Se não conseguir extrair preço válido
        """
        if not price_raw:
            raise ParsingError("Preço vazio", field="price")
        
        # Limpa a string
        cleaned = price_raw.strip()
        
        # Tenta cada padrão de preço
        for pattern in PRICE_PATTERNS:
            match = pattern.search(cleaned)
            if match:
                try:
                    # Extrai os grupos
                    groups = match.groups()
                    
                    if len(groups) == 1:
                        # Preço completo em um grupo
                        price_str = groups[0]
                    elif len(groups) == 2:
                        # Inteiro + centavos separados
                        price_str = f"{groups[0]}.{groups[1]}"
                    else:
                        continue
                    
                    # Normaliza formato: 1.234,56 -> 1234.56
                    price_str = self._normalize_price_format(price_str)
                    
                    return Decimal(price_str)
                    
                except (InvalidOperation, ValueError) as e:
                    self.logger.debug(
                        "Falha ao converter preço",
                        pattern=pattern.pattern,
                        price_str=price_str,
                        error=str(e),
                    )
                    continue
        
        raise ParsingError(
            f"Não foi possível extrair preço de: {price_raw}",
            field="price",
            raw_data=price_raw,
        )
    
    def _normalize_price_format(self, price_str: str) -> str:
        """
        Normaliza formato de preço brasileiro para padrão decimal.
        
        Exemplos:
            "1.234,56" -> "1234.56"
            "12,99" -> "12.99"
            "1234.56" -> "1234.56" (já no formato correto)
        """
        # Remove espaços
        price_str = price_str.strip()
        
        # Detecta formato brasileiro (vírgula como decimal)
        if "," in price_str:
            # Remove pontos de milhar e troca vírgula por ponto
            price_str = price_str.replace(".", "").replace(",", ".")
        
        return price_str
    
    def parse_unit_price(
        self, 
        unit_price_raw: Optional[str],
    ) -> Optional[tuple[Decimal, str]]:
        """
        Extrai preço por unidade já fornecido pelo site.
        
        Args:
            unit_price_raw: String como "R$ 25,99/kg"
            
        Returns:
            Tupla (preço, unidade) ou None se não encontrar
        """
        if not unit_price_raw:
            return None
        
        match = UNIT_PRICE_PATTERN.search(unit_price_raw)
        if match:
            try:
                price_str = self._normalize_price_format(match.group(1))
                unit = match.group(2).lower()
                return (Decimal(price_str), unit)
            except (InvalidOperation, ValueError):
                return None
        
        return None
    
    def parse_availability(
        self, 
        availability_raw: Optional[str],
    ) -> Availability:
        """
        Converte texto de disponibilidade para enum.
        
        Args:
            availability_raw: Texto indicando disponibilidade
            
        Returns:
            Enum de disponibilidade
        """
        return Availability.from_text(availability_raw)
    
    def parse_raw_product(self, raw: RawProduct) -> dict:
        """
        Faz parsing completo de um produto bruto.
        
        Args:
            raw: Produto bruto do scraper
            
        Returns:
            Dicionário com dados parseados
        """
        self.logger.debug("Parsing produto", title=raw.title[:50])
        
        # Parse preço (obrigatório)
        try:
            price = self.parse_price(raw.price_raw)
        except ParsingError:
            self.logger.warning(
                "Falha ao parsear preço",
                title=raw.title,
                price_raw=raw.price_raw,
            )
            raise
        
        # Parse preço unitário (opcional, pode vir do site)
        site_unit_price = self.parse_unit_price(raw.unit_price_raw)
        
        # Parse disponibilidade
        availability = self.parse_availability(raw.availability_raw)
        
        return {
            "price": price,
            "site_unit_price": site_unit_price,
            "availability": availability,
        }