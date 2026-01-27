# src/services/cache/dynamic_ttl.py
"""
TTL (Time To Live) Dinâmico para Cache.

Calcula TTL baseado em múltiplos fatores:
- Período do dia (madrugada, manhã, tarde, noite)
- Dia da semana (sexta tem mais promoções, domingo menos atualizações)
- Mercado específico (alguns atualizam mais frequentemente)
- Se o produto está em promoção
- Popularidade da busca
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from dataclasses import dataclass


class TimePeriod(Enum):
    """Períodos do dia para cálculo de TTL."""
    OVERNIGHT = "overnight"      # 00:00 - 06:00
    MORNING = "morning"          # 06:00 - 12:00
    AFTERNOON = "afternoon"      # 12:00 - 18:00
    EVENING = "evening"          # 18:00 - 00:00


@dataclass
class TTLConfig:
    """Configurações de TTL."""
    
    # TTL mínimo e máximo em segundos
    min_ttl: int = 60             # 1 minuto
    max_ttl: int = 3600           # 1 hora
    
    # TTL padrão quando não há fatores específicos
    default_ttl: int = 300        # 5 minutos


class DynamicTTLCalculator:
    """
    Calcula TTL dinamicamente baseado em múltiplos fatores.
    
    Fatores considerados:
    1. Período do dia - madrugada permite TTL maior, manhã menor
    2. Dia da semana - sexta/sábado têm mais promoções
    3. Mercado - alguns mercados atualizam mais frequentemente
    4. Promoção - produtos em promoção precisam de TTL menor
    5. Popularidade - buscas populares podem ter TTL ligeiramente maior
    
    Exemplo de uso:
        calculator = DynamicTTLCalculator()
        
        # TTL para busca normal
        ttl = calculator.calculate_ttl(market_id="carrefour")
        
        # TTL para produto promocional
        ttl = calculator.calculate_ttl(
            market_id="atacadao",
            is_promotional=True
        )
        
        # TTL para múltiplos mercados
        ttl = calculator.calculate_ttl_for_search(
            query="arroz",
            market_ids=["carrefour", "atacadao"]
        )
    """
    
    # TTL base por período do dia (em segundos)
    PERIOD_TTL = {
        TimePeriod.OVERNIGHT: 600,     # 10 min - baixa atividade
        TimePeriod.MORNING: 180,       # 3 min - período de atualizações
        TimePeriod.AFTERNOON: 300,     # 5 min - estabilidade média
        TimePeriod.EVENING: 420,       # 7 min - preços geralmente estáveis
    }
    
    # Multiplicadores por dia da semana (0=segunda, 6=domingo)
    # Valores menores = TTL menor = cache atualiza mais frequentemente
    DAY_MULTIPLIERS = {
        0: 0.8,   # Segunda - mais atualizações pós-fim de semana
        1: 1.0,   # Terça - normal
        2: 1.0,   # Quarta - normal
        3: 0.9,   # Quinta - preparação para promoções de sexta
        4: 0.7,   # Sexta - muitas promoções, precisa atualizar mais
        5: 0.8,   # Sábado - promoções ativas
        6: 1.2,   # Domingo - poucas atualizações, pode cachear mais
    }
    
    # Multiplicadores por mercado
    # Mercados que atualizam mais frequentemente têm valores menores
    MARKET_MULTIPLIERS = {
        "atacadao": 0.8,          # Atualiza preços com frequência
        "carrefour": 1.0,         # Padrão
        "pao_acucar": 1.0,        # Padrão
        "gbarbosa": 1.2,          # Atualizações menos frequentes
        "samsclub": 0.9,          # Preços de atacado mudam
        "redemix": 1.1,           # Regional, menos atualizações
        "mercantil": 1.1,         # Regional
        "hiperideal": 1.1,        # Regional
        "extra": 1.0,             # Padrão
        "assai": 0.85,            # Atacado, atualiza frequentemente
    }
    
    def __init__(self, config: Optional[TTLConfig] = None):
        """
        Inicializa o calculador de TTL.
        
        Args:
            config: Configurações customizadas de TTL
        """
        self.config = config or TTLConfig()
    
    @staticmethod
    def get_current_period() -> TimePeriod:
        """
        Determina o período atual do dia.
        
        Returns:
            TimePeriod correspondente ao horário atual
        """
        current_hour = datetime.now().hour
        
        if 0 <= current_hour < 6:
            return TimePeriod.OVERNIGHT
        elif 6 <= current_hour < 12:
            return TimePeriod.MORNING
        elif 12 <= current_hour < 18:
            return TimePeriod.AFTERNOON
        else:
            return TimePeriod.EVENING
    
    def calculate_ttl(
        self,
        market_id: Optional[str] = None,
        is_promotional: bool = False,
        query_popularity: float = 0.0,
        custom_base_ttl: Optional[int] = None,
    ) -> int:
        """
        Calcula TTL dinâmico baseado em múltiplos fatores.
        
        Args:
            market_id: ID do mercado (ex: "carrefour", "atacadao")
            is_promotional: Se o produto está em promoção
            query_popularity: Score de popularidade da busca (0.0 a 1.0)
            custom_base_ttl: TTL base customizado (sobrescreve período do dia)
            
        Returns:
            TTL calculado em segundos
            
        Exemplo:
            # Busca normal no Carrefour às 10h de uma sexta-feira
            ttl = calculator.calculate_ttl(market_id="carrefour")
            # Resultado: ~126 segundos (180s base * 0.7 sexta)
            
            # Produto promocional no Atacadão
            ttl = calculator.calculate_ttl(
                market_id="atacadao",
                is_promotional=True
            )
            # Resultado: TTL bem menor devido à promoção
        """
        # 1. Define TTL base pelo período do dia (ou customizado)
        if custom_base_ttl is not None:
            base_ttl = custom_base_ttl
        else:
            period = self.get_current_period()
            base_ttl = self.PERIOD_TTL[period]
        
        # 2. Aplica multiplicador do dia da semana
        weekday = datetime.now().weekday()
        day_multiplier = self.DAY_MULTIPLIERS.get(weekday, 1.0)
        
        # 3. Aplica multiplicador do mercado
        market_multiplier = 1.0
        if market_id:
            market_multiplier = self.MARKET_MULTIPLIERS.get(market_id, 1.0)
        
        # 4. Aplica multiplicador de promoção
        # Produtos em promoção precisam de cache mais curto (mudam rápido)
        promo_multiplier = 0.5 if is_promotional else 1.0
        
        # 5. Aplica multiplicador de popularidade
        # Buscas populares podem ter TTL ligeiramente maior (mais valor em cachear)
        # Mas limitado para não ficar muito desatualizado
        # popularity de 0.0 = multiplicador 1.0
        # popularity de 1.0 = multiplicador 1.3
        popularity_multiplier = 1.0 + (query_popularity * 0.3)
        
        # Calcula TTL final
        final_ttl = int(
            base_ttl 
            * day_multiplier 
            * market_multiplier 
            * promo_multiplier 
            * popularity_multiplier
        )
        
        # Garante limites mínimo e máximo
        return max(self.config.min_ttl, min(final_ttl, self.config.max_ttl))
    
    def calculate_ttl_for_search(
        self,
        query: str,
        market_ids: Optional[list[str]] = None,
        has_promotional_items: bool = False,
        query_popularity: float = 0.0,
    ) -> int:
        """
        Calcula TTL para uma busca completa (múltiplos mercados).
        
        Usa o menor TTL entre todos os mercados envolvidos para garantir
        que os dados mais voláteis sejam atualizados.
        
        Args:
            query: Termo de busca
            market_ids: Lista de IDs dos mercados pesquisados
            has_promotional_items: Se algum resultado é promocional
            query_popularity: Popularidade da busca
            
        Returns:
            TTL em segundos (menor entre todos os mercados)
        """
        if not market_ids:
            return self.calculate_ttl(
                is_promotional=has_promotional_items,
                query_popularity=query_popularity,
            )
        
        # Calcula TTL para cada mercado e usa o menor
        ttls = [
            self.calculate_ttl(
                market_id=market_id,
                is_promotional=has_promotional_items,
                query_popularity=query_popularity,
            )
            for market_id in market_ids
        ]
        
        return min(ttls)
    
    def get_ttl_info(
        self,
        market_id: Optional[str] = None,
        is_promotional: bool = False,
        query_popularity: float = 0.0,
    ) -> dict:
        """
        Retorna informações detalhadas sobre o cálculo do TTL.
        Útil para debug e logging.
        
        Returns:
            Dicionário com todos os fatores e o TTL final
        """
        period = self.get_current_period()
        weekday = datetime.now().weekday()
        
        base_ttl = self.PERIOD_TTL[period]
        day_multiplier = self.DAY_MULTIPLIERS.get(weekday, 1.0)
        market_multiplier = self.MARKET_MULTIPLIERS.get(market_id, 1.0) if market_id else 1.0
        promo_multiplier = 0.5 if is_promotional else 1.0
        popularity_multiplier = 1.0 + (query_popularity * 0.3)
        
        final_ttl = self.calculate_ttl(
            market_id=market_id,
            is_promotional=is_promotional,
            query_popularity=query_popularity,
        )
        
        weekday_names = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"]
        
        return {
            "period": period.value,
            "weekday": weekday,
            "weekday_name": weekday_names[weekday],
            "base_ttl_seconds": base_ttl,
            "multipliers": {
                "day": day_multiplier,
                "market": market_multiplier,
                "promotional": promo_multiplier,
                "popularity": round(popularity_multiplier, 2),
            },
            "final_ttl_seconds": final_ttl,
            "final_ttl_formatted": f"{final_ttl // 60}m {final_ttl % 60}s",
        }
