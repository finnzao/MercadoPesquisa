"""
Normalizador de quantidades.
Extrai quantidade e unidade do título/descrição e converte para unidades base.
"""

import re
from typing import Optional

from config.logging_config import LoggerMixin
from src.core.constants import (
    QUANTITY_PATTERNS,
    UNIT_CONVERSIONS,
    PACK_MULTIPLIER_PATTERN,
    CATEGORY_KEYWORDS,
)
from src.core.models import QuantityInfo, RawProduct
from src.core.types import Unit


class QuantityNormalizer(LoggerMixin):
    """
    Normalizador de quantidades de produtos.
    Extrai e converte quantidades para unidades base (kg, L, un).
    """
    
    def __init__(self):
        """Inicializa o normalizador."""
        self._compiled_patterns = QUANTITY_PATTERNS
    
    def extract_quantity(
        self, 
        text: str,
        raw_product: Optional[RawProduct] = None,
    ) -> Optional[QuantityInfo]:
        """
        Extrai informação de quantidade do texto.
        
        Args:
            text: Texto para extrair quantidade (geralmente título)
            raw_product: Produto bruto para contexto adicional
            
        Returns:
            QuantityInfo se encontrar, None caso contrário
        """
        if not text:
            return None
        
        text_clean = text.lower().strip()
        
        # Tenta extrair pack com volume/peso individual (ex: "12x500ml")
        pack_info = self._extract_pack_quantity(text_clean)
        if pack_info:
            return pack_info
        
        # Tenta cada padrão de quantidade
        for pattern in self._compiled_patterns:
            match = pattern.search(text_clean)
            if match:
                result = self._process_match(match, text, pattern)
                if result:
                    return result
        
        # Tenta inferir se é produto vendido por kg (hortifruti)
        if self._is_likely_hortifruti(text_clean):
            return QuantityInfo(
                value=1.0,
                unit=Unit.KILOGRAM,
                base_value=1.0,
                base_unit=Unit.KILOGRAM,
                multiplier=1,
                raw_text=text,
                extraction_pattern="hortifruti_inference",
            )
        
        self.logger.debug("Quantidade não encontrada", text=text[:100])
        return None
    
    def _process_match(
        self, 
        match: re.Match, 
        original_text: str,
        pattern: re.Pattern,
    ) -> Optional[QuantityInfo]:
        """
        Processa um match de regex e cria QuantityInfo.
        
        Args:
            match: Match do regex
            original_text: Texto original
            pattern: Padrão que fez match
            
        Returns:
            QuantityInfo ou None se inválido
        """
        groups = match.groups()
        
        if len(groups) < 2:
            # Padrão "por kg" - sem valor numérico
            if len(groups) == 1:
                unit_str = groups[0].lower()
                if unit_str in UNIT_CONVERSIONS:
                    base_unit, _ = UNIT_CONVERSIONS[unit_str]
                    return QuantityInfo(
                        value=1.0,
                        unit=Unit(base_unit),
                        base_value=1.0,
                        base_unit=Unit(base_unit),
                        multiplier=1,
                        raw_text=match.group(0),
                        extraction_pattern=pattern.pattern[:50],
                    )
            return None
        
        try:
            # Extrai valor e unidade
            value_str = groups[0].replace(",", ".")
            value = float(value_str)
            unit_str = groups[1].lower()
            
            if value <= 0:
                return None
            
            # Converte unidade
            if unit_str not in UNIT_CONVERSIONS:
                self.logger.debug(
                    "Unidade desconhecida",
                    unit=unit_str,
                    text=original_text[:50],
                )
                return None
            
            base_unit_str, conversion_factor = UNIT_CONVERSIONS[unit_str]
            base_value = value * conversion_factor
            
            # Detecta multiplicador de pack
            multiplier = self._extract_multiplier(original_text)
            
            return QuantityInfo(
                value=value,
                unit=self._str_to_unit(unit_str),
                base_value=base_value,
                base_unit=Unit(base_unit_str),
                multiplier=multiplier,
                raw_text=match.group(0),
                extraction_pattern=pattern.pattern[:50],
            )
            
        except (ValueError, KeyError) as e:
            self.logger.debug(
                "Erro ao processar match",
                error=str(e),
                groups=groups,
            )
            return None
    
    def _extract_pack_quantity(self, text: str) -> Optional[QuantityInfo]:
        """
        Extrai quantidade de packs (ex: "12x500ml").
        
        Args:
            text: Texto limpo (lowercase)
            
        Returns:
            QuantityInfo para packs ou None
        """
        # Padrão: NUMxNUMunidade (12x500ml, 6x1L)
        pack_pattern = re.compile(
            r"(\d+)\s*x\s*(\d+[.,]?\d*)\s*(ml|l|lt|g|gr|kg)\b",
            re.IGNORECASE,
        )
        
        match = pack_pattern.search(text)
        if not match:
            return None
        
        try:
            multiplier = int(match.group(1))
            value = float(match.group(2).replace(",", "."))
            unit_str = match.group(3).lower()
            
            if unit_str not in UNIT_CONVERSIONS:
                return None
            
            base_unit_str, conversion_factor = UNIT_CONVERSIONS[unit_str]
            base_value = value * conversion_factor
            
            return QuantityInfo(
                value=value,
                unit=self._str_to_unit(unit_str),
                base_value=base_value,
                base_unit=Unit(base_unit_str),
                multiplier=multiplier,
                raw_text=match.group(0),
                extraction_pattern="pack_NxM",
            )
            
        except (ValueError, KeyError):
            return None
    
    def _extract_multiplier(self, text: str) -> int:
        """
        Extrai multiplicador de pack do texto.
        
        Args:
            text: Texto do produto
            
        Returns:
            Multiplicador (default 1)
        """
        match = PACK_MULTIPLIER_PATTERN.search(text.lower())
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                pass
        return 1
    
    def _is_likely_hortifruti(self, text: str) -> bool:
        """
        Verifica se o produto parece ser hortifruti vendido por kg.
        
        Args:
            text: Texto limpo (lowercase)
            
        Returns:
            True se parecer hortifruti
        """
        # Verifica keywords de hortifruti
        for keyword in CATEGORY_KEYWORDS.get("hortifruti", []):
            if keyword in text:
                # Confirma se tem indicador de "por kg"
                if any(ind in text for ind in ["por kg", "/kg", "kg", "quilo"]):
                    return True
        return False
    
    def _str_to_unit(self, unit_str: str) -> Unit:
        """
        Converte string de unidade para enum Unit.
        
        Args:
            unit_str: String da unidade
            
        Returns:
            Enum Unit correspondente
        """
        unit_mapping = {
            "kg": Unit.KILOGRAM,
            "quilo": Unit.KILOGRAM,
            "quilos": Unit.KILOGRAM,
            "g": Unit.GRAM,
            "gr": Unit.GRAM,
            "grama": Unit.GRAM,
            "gramas": Unit.GRAM,
            "mg": Unit.MILLIGRAM,
            "l": Unit.LITER,
            "lt": Unit.LITER,
            "litro": Unit.LITER,
            "litros": Unit.LITER,
            "ml": Unit.MILLILITER,
            "mililitro": Unit.MILLILITER,
            "mililitros": Unit.MILLILITER,
            "un": Unit.UNIT,
            "und": Unit.UNIT,
            "unid": Unit.UNIT,
            "unidade": Unit.UNIT,
            "unidades": Unit.UNIT,
            "pack": Unit.PACK,
            "pct": Unit.PACK,
            "pacote": Unit.PACK,
            "dz": Unit.DOZEN,
            "duzia": Unit.DOZEN,
            "dúzia": Unit.DOZEN,
        }
        return unit_mapping.get(unit_str.lower(), Unit.UNKNOWN)
    
    def normalize_to_base(
        self,
        quantity_info: QuantityInfo,
    ) -> tuple[float, Unit]:
        """
        Retorna quantidade total em unidade base.
        
        Args:
            quantity_info: Informação de quantidade
            
        Returns:
            Tupla (valor_total, unidade_base)
        """
        total = quantity_info.total_base_value
        return (total, quantity_info.base_unit)