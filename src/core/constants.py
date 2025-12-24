"""
Constantes e padrões regex para extração e normalização.
"""

import re
from typing import Final

# =============================================================================
# CONVERSÕES DE UNIDADES
# =============================================================================

UNIT_CONVERSIONS: Final[dict[str, tuple[str, float]]] = {
    # Massa -> kg
    "kg": ("kg", 1.0),
    "quilo": ("kg", 1.0),
    "quilos": ("kg", 1.0),
    "g": ("kg", 0.001),
    "gr": ("kg", 0.001),
    "grama": ("kg", 0.001),
    "gramas": ("kg", 0.001),
    "mg": ("kg", 0.000001),
    
    # Volume -> L
    "l": ("L", 1.0),
    "lt": ("L", 1.0),
    "litro": ("L", 1.0),
    "litros": ("L", 1.0),
    "ml": ("L", 0.001),
    "mililitro": ("L", 0.001),
    "mililitros": ("L", 0.001),
    
    # Unidades
    "un": ("un", 1.0),
    "und": ("un", 1.0),
    "unid": ("un", 1.0),
    "unidade": ("un", 1.0),
    "unidades": ("un", 1.0),
    
    # Packs
    "pack": ("pack", 1.0),
    "pct": ("pack", 1.0),
    "pacote": ("pack", 1.0),
    "fardo": ("pack", 1.0),
    "caixa": ("pack", 1.0),
    "cx": ("pack", 1.0),
    "lata": ("un", 1.0),
    "garrafa": ("un", 1.0),
    "grf": ("un", 1.0),
    
    # Dúzia
    "dz": ("un", 12.0),
    "duzia": ("un", 12.0),
    "dúzia": ("un", 12.0),
}


# =============================================================================
# PADRÕES REGEX PARA EXTRAÇÃO DE QUANTIDADE
# =============================================================================

# Padrão principal: número + unidade
# Exemplos: "5kg", "500g", "1,5L", "6 unidades", "pack c/ 12"
QUANTITY_PATTERNS: Final[list[re.Pattern]] = [
    # Padrão: 5kg, 500g, 1.5L, 200ml (número colado na unidade)
    re.compile(
        r"(\d+[.,]?\d*)\s*(kg|g|gr|mg|l|lt|ml|un|und|unid|unidades?|pack|pct|dz|dúzia|duzia)\b",
        re.IGNORECASE,
    ),
    
    # Padrão: "c/ 12 unidades", "com 6 latas", "x12"
    re.compile(
        r"(?:c/?|com|x)\s*(\d+)\s*(un|und|unid|unidades?|latas?|garrafas?)\b",
        re.IGNORECASE,
    ),
    
    # Padrão: "pack 12", "caixa 6", "fardo 12"
    re.compile(
        r"(pack|caixa|cx|fardo)\s*(?:c/?|com)?\s*(\d+)",
        re.IGNORECASE,
    ),
    
    # Padrão: "12x500ml", "6x1L" (packs com volume individual)
    re.compile(
        r"(\d+)\s*x\s*(\d+[.,]?\d*)\s*(ml|l|lt|g|gr|kg)\b",
        re.IGNORECASE,
    ),
    
    # Padrão: "1 litro", "2 quilos", "500 gramas"
    re.compile(
        r"(\d+[.,]?\d*)\s*(litros?|quilos?|gramas?|mililitros?)\b",
        re.IGNORECASE,
    ),
    
    # Padrão para hortifruti: "por kg", "kg", "/kg"
    re.compile(
        r"(?:por\s+|/\s*)?(kg|quilo)\b",
        re.IGNORECASE,
    ),
]

# Padrão para extrair multiplicador de pack
# Exemplos: "pack c/ 12", "6 unidades", "caixa 24"
PACK_MULTIPLIER_PATTERN: Final[re.Pattern] = re.compile(
    r"(?:pack|caixa|cx|fardo|c/?|com|x)\s*(\d+)",
    re.IGNORECASE,
)


# =============================================================================
# PADRÕES REGEX PARA EXTRAÇÃO DE PREÇO
# =============================================================================

PRICE_PATTERNS: Final[list[re.Pattern]] = [
    # Padrão brasileiro: R$ 12,99 ou R$12.99
    re.compile(
        r"R\$\s*(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})",
        re.IGNORECASE,
    ),
    
    # Padrão sem R$: 12,99 ou 12.99
    re.compile(
        r"(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})",
    ),
    
    # Padrão inteiro + centavos separados
    re.compile(
        r"(\d+)\s*,?\s*(\d{2})",
    ),
]

# Padrão para preço por unidade (ex: "R$ 25,99/kg", "R$ 3,50/L")
UNIT_PRICE_PATTERN: Final[re.Pattern] = re.compile(
    r"R\$\s*(\d+[.,]\d{2})\s*/\s*(kg|l|lt|un|unid)\b",
    re.IGNORECASE,
)


# =============================================================================
# PALAVRAS-CHAVE DE CATEGORIAS
# =============================================================================

CATEGORY_KEYWORDS: Final[dict[str, list[str]]] = {
    "hortifruti": [
        "banana", "maçã", "laranja", "limão", "tomate", "cebola",
        "batata", "cenoura", "alface", "mamão", "melancia", "uva",
        "manga", "abacaxi", "morango", "pera", "kiwi", "melão",
    ],
    "bebidas": [
        "água", "refrigerante", "suco", "cerveja", "vinho", "leite",
        "café", "chá", "energético", "isotônico", "whisky", "vodka",
    ],
    "grãos": [
        "arroz", "feijão", "lentilha", "grão de bico", "ervilha",
        "milho", "aveia", "quinoa", "chia",
    ],
    "carnes": [
        "carne", "frango", "peixe", "porco", "linguiça", "salsicha",
        "hambúrguer", "bife", "filé", "costela", "picanha", "alcatra",
    ],
    "laticínios": [
        "leite", "queijo", "iogurte", "manteiga", "requeijão",
        "cream cheese", "creme de leite", "leite condensado",
    ],
    "limpeza": [
        "detergente", "sabão", "desinfetante", "água sanitária",
        "amaciante", "alvejante", "limpador", "esponja",
    ],
    "higiene": [
        "sabonete", "shampoo", "condicionador", "pasta de dente",
        "escova", "desodorante", "papel higiênico", "fralda",
    ],
}


# =============================================================================
# HEADERS HTTP PADRÃO
# =============================================================================

DEFAULT_HEADERS: Final[dict[str, str]] = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}


# =============================================================================
# CONFIGURAÇÕES DE RETRY
# =============================================================================

RETRY_STATUS_CODES: Final[set[int]] = {408, 429, 500, 502, 503, 504}

RETRY_EXCEPTIONS: Final[tuple[type[Exception], ...]] = (
    ConnectionError,
    TimeoutError,
)