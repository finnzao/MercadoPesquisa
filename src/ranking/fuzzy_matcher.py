"""
Fuzzy Matcher Simplificado para comparação de títulos de produtos.

Regra principal: A primeira palavra da busca DEVE ser igual à primeira
palavra do título do produto para ser considerado relevante.

Exemplo:
    - Busca: "Arroz 5kg" 
    - Título: "Arroz Tipo 1 Tio João 5kg" ✓ (primeira palavra = "arroz")
    - Título: "Feijão Carioca 1kg" ✗ (primeira palavra ≠ "arroz")
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional


@dataclass
class MatchResult:
    """Resultado de uma comparação fuzzy."""
    
    # Flags principais
    first_word_match: bool = False    # Primeira palavra é igual?
    quantity_match: bool = False       # Quantidade combina?
    
    # Score final (0.0 a 1.0)
    score: float = 0.0
    
    # Informações extras
    query_first_word: str = ""
    title_first_word: str = ""
    query_quantity: Optional[str] = None
    title_quantity: Optional[str] = None
    
    @property
    def is_relevant(self) -> bool:
        """Produto é relevante se primeira palavra combina."""
        return self.first_word_match
    
    @property
    def is_exact_match(self) -> bool:
        """Match exato: primeira palavra + quantidade."""
        return self.first_word_match and self.quantity_match


class FuzzyMatcher:
    """
    Matcher simplificado para comparar queries com títulos de produtos.
    
    Regras:
    1. OBRIGATÓRIO: Primeira palavra da busca = primeira palavra do título
    2. BONUS: Se quantidade especificada na busca combina com título
    
    Score:
    - 0.0: Primeira palavra não combina (irrelevante)
    - 0.6: Primeira palavra combina
    - 0.8: Primeira palavra + quantidade parcial
    - 1.0: Primeira palavra + quantidade exata
    """
    
    def __init__(self):
        """Inicializa o matcher."""
        pass
    
    def match(self, query: str, title: str) -> MatchResult:
        """
        Compara query de busca com título do produto.
        
        Args:
            query: Termo de busca (ex: "Arroz 5kg")
            title: Título do produto (ex: "Arroz Tipo 1 Tio João 5kg")
            
        Returns:
            MatchResult com resultado da comparação
        """
        if not query or not title:
            return MatchResult()
        
        # Normaliza e extrai primeira palavra
        query_first = self._get_first_word(query)
        title_first = self._get_first_word(title)
        
        if not query_first or not title_first:
            return MatchResult()
        
        # Verifica match da primeira palavra
        first_word_match = query_first == title_first
        
        # Extrai quantidades
        query_qty = self._extract_quantity(query)
        title_qty = self._extract_quantity(title)
        
        # Verifica match de quantidade
        quantity_match = self._compare_quantities(query_qty, title_qty)
        
        # Calcula score
        if not first_word_match:
            score = 0.0
        elif query_qty is None:
            # Sem quantidade na busca = aceita qualquer uma
            score = 0.8
        elif quantity_match:
            score = 1.0
        else:
            # Primeira palavra ok, mas quantidade diferente
            score = 0.5
        
        return MatchResult(
            first_word_match=first_word_match,
            quantity_match=quantity_match,
            score=score,
            query_first_word=query_first,
            title_first_word=title_first,
            query_quantity=query_qty,
            title_quantity=title_qty,
        )
    
    def is_relevant(self, query: str, title: str) -> bool:
        """
        Verifica rapidamente se o produto é relevante.
        
        Args:
            query: Termo de busca
            title: Título do produto
            
        Returns:
            True se primeira palavra combina
        """
        query_first = self._get_first_word(query)
        title_first = self._get_first_word(title)
        return query_first == title_first and bool(query_first)
    
    def filter_relevant(
        self, 
        query: str, 
        titles: list[str]
    ) -> list[tuple[int, str]]:
        """
        Filtra apenas títulos relevantes.
        
        Args:
            query: Termo de busca
            titles: Lista de títulos
            
        Returns:
            Lista de tuplas (índice, título) dos relevantes
        """
        query_first = self._get_first_word(query)
        if not query_first:
            return []
        
        relevant = []
        for idx, title in enumerate(titles):
            title_first = self._get_first_word(title)
            if title_first == query_first:
                relevant.append((idx, title))
        
        return relevant
    
    def rank_by_relevance(
        self, 
        query: str, 
        titles: list[str]
    ) -> list[tuple[int, MatchResult]]:
        """
        Rankeia títulos por relevância.
        
        Args:
            query: Termo de busca
            titles: Lista de títulos
            
        Returns:
            Lista de tuplas (índice, MatchResult) ordenada por score
        """
        results = []
        
        for idx, title in enumerate(titles):
            match = self.match(query, title)
            if match.is_relevant:
                results.append((idx, match))
        
        # Ordena por score decrescente
        results.sort(key=lambda x: x[1].score, reverse=True)
        return results
    
    def _get_first_word(self, text: str) -> str:
        """
        Extrai e normaliza a primeira palavra do texto.
        
        Args:
            text: Texto para extrair primeira palavra
            
        Returns:
            Primeira palavra normalizada (lowercase, sem acentos)
        """
        if not text:
            return ""
        
        # Normaliza: remove acentos, lowercase
        normalized = self._normalize(text)
        
        # Pega primeira palavra (split por espaço)
        words = normalized.split()
        return words[0] if words else ""
    
    def _normalize(self, text: str) -> str:
        """
        Normaliza texto: remove acentos, lowercase, limpa espaços.
        
        Args:
            text: Texto para normalizar
            
        Returns:
            Texto normalizado
        """
        # Remove acentos
        text = unicodedata.normalize("NFKD", text)
        text = "".join(c for c in text if not unicodedata.combining(c))
        
        # Lowercase
        text = text.lower().strip()
        
        return text
    
    def _extract_quantity(self, text: str) -> Optional[str]:
        """
        Extrai quantidade do texto (ex: "5kg", "1L", "500ml").
        
        Args:
            text: Texto para extrair quantidade
            
        Returns:
            String da quantidade normalizada ou None
        """
        if not text:
            return None
        
        text_lower = text.lower()
        
        # Padrão: número + unidade
        # Ex: 5kg, 500g, 1L, 500ml, 12x350ml
        patterns = [
            # Pack: 12x350ml, 6x1L
            r"(\d+)\s*x\s*(\d+[.,]?\d*)\s*(kg|g|l|ml)\b",
            # Simples: 5kg, 500g, 1L, 500ml
            r"(\d+[.,]?\d*)\s*(kg|g|l|ml)\b",
        ]
        
        # Tenta pack primeiro
        pack_match = re.search(patterns[0], text_lower)
        if pack_match:
            mult = pack_match.group(1)
            val = pack_match.group(2).replace(",", ".")
            unit = pack_match.group(3)
            # Normaliza para unidade base
            total, base_unit = self._normalize_quantity(
                float(mult) * float(val), unit
            )
            return f"{total:.2f}{base_unit}"
        
        # Tenta simples
        simple_match = re.search(patterns[1], text_lower)
        if simple_match:
            val = simple_match.group(1).replace(",", ".")
            unit = simple_match.group(2)
            total, base_unit = self._normalize_quantity(float(val), unit)
            return f"{total:.2f}{base_unit}"
        
        return None
    
    def _normalize_quantity(
        self, 
        value: float, 
        unit: str
    ) -> tuple[float, str]:
        """
        Normaliza quantidade para unidade base (kg ou L).
        
        Args:
            value: Valor numérico
            unit: Unidade (g, kg, ml, l)
            
        Returns:
            Tupla (valor_normalizado, unidade_base)
        """
        unit = unit.lower()
        
        if unit == "g":
            return (value / 1000, "kg")
        elif unit == "kg":
            return (value, "kg")
        elif unit == "ml":
            return (value / 1000, "l")
        elif unit == "l":
            return (value, "l")
        
        return (value, unit)
    
    def _compare_quantities(
        self, 
        qty1: Optional[str], 
        qty2: Optional[str]
    ) -> bool:
        """
        Compara duas quantidades.
        
        Args:
            qty1: Primeira quantidade
            qty2: Segunda quantidade
            
        Returns:
            True se são iguais ou qty1 é None (aceita qualquer)
        """
        if qty1 is None:
            return True  # Sem quantidade na busca = aceita qualquer
        if qty2 is None:
            return False  # Quantidade na busca mas não no título
        
        return qty1 == qty2


def fuzzy_match(query: str, title: str) -> MatchResult:
    """
    Função de conveniência para match rápido.
    
    Args:
        query: Termo de busca
        title: Título do produto
        
    Returns:
        MatchResult
    """
    return FuzzyMatcher().match(query, title)


def is_relevant(query: str, title: str) -> bool:
    """
    Verifica rapidamente se produto é relevante.
    
    Args:
        query: Termo de busca
        title: Título do produto
        
    Returns:
        True se primeira palavra combina
    """
    return FuzzyMatcher().is_relevant(query, title)