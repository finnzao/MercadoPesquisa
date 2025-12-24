"""
Calculador de preço normalizado por unidade.
Calcula preço por kg, L ou unidade para comparação justa.
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from config.logging_config import LoggerMixin
from src.core.models import NormalizedProduct, PriceOffer, QuantityInfo
from src.core.types import Availability, NormalizationStatus, Unit


class PriceCalculator(LoggerMixin):
    """
    Calculador de preço normalizado.
    Converte preços para R$/kg, R$/L ou R$/un.
    """
    
    def __init__(self, decimal_places: int = 2):
        """
        Inicializa o calculador.
        
        Args:
            decimal_places: Casas decimais para arredondamento
        """
        self.decimal_places = decimal_places
        self._quantize_exp = Decimal(10) ** -decimal_places
    
    def calculate_normalized_price(
        self,
        price: Decimal,
        quantity_info: Optional[QuantityInfo],
    ) -> Optional[tuple[Decimal, Unit]]:
        """
        Calcula preço normalizado por unidade base.
        
        Args:
            price: Preço do produto
            quantity_info: Informação de quantidade normalizada
            
        Returns:
            Tupla (preço_por_unidade, unidade_base) ou None
        """
        if quantity_info is None:
            return None
        
        total_quantity = quantity_info.total_base_value
        
        if total_quantity <= 0:
            self.logger.warning(
                "Quantidade inválida para cálculo",
                quantity=total_quantity,
            )
            return None
        
        # Calcula preço por unidade base
        normalized_price = price / Decimal(str(total_quantity))
        
        # Arredonda
        normalized_price = normalized_price.quantize(
            self._quantize_exp,
            rounding=ROUND_HALF_UP,
        )
        
        return (normalized_price, quantity_info.base_unit)
    
    def create_price_offer(
        self,
        normalized_product: NormalizedProduct,
    ) -> PriceOffer:
        """
        Cria oferta de preço a partir de produto normalizado.
        
        Args:
            normalized_product: Produto com dados normalizados
            
        Returns:
            PriceOffer com preço normalizado calculado
        """
        # Calcula preço normalizado
        normalized_result = self.calculate_normalized_price(
            normalized_product.price,
            normalized_product.quantity,
        )
        
        # Determina status final
        if normalized_result:
            normalized_price, normalized_unit = normalized_result
            status = NormalizationStatus.SUCCESS
            price_display = self._format_price_display(
                normalized_price,
                normalized_unit,
            )
        else:
            normalized_price = None
            normalized_unit = None
            status = (
                NormalizationStatus.PARTIAL 
                if normalized_product.price > 0 
                else NormalizationStatus.FAILED
            )
            price_display = self._format_price_display(
                normalized_product.price,
                None,
            )
        
        # Extrai quantidade se disponível
        quantity_value = None
        quantity_unit = None
        if normalized_product.quantity:
            quantity_value = normalized_product.quantity.total_base_value
            quantity_unit = normalized_product.quantity.base_unit
        
        return PriceOffer(
            market_id=normalized_product.market_id,
            market_name=normalized_product.market_name,
            title=normalized_product.title,
            url=normalized_product.url,
            image_url=normalized_product.image_url,
            price=normalized_product.price,
            quantity_value=quantity_value,
            quantity_unit=quantity_unit,
            normalized_price=normalized_price,
            normalized_unit=normalized_unit,
            price_display=price_display,
            availability=normalized_product.availability,
            normalization_status=status,
            search_query=normalized_product.search_query,
            cep=normalized_product.cep,
            collected_at=normalized_product.collected_at,
        )
    
    def _format_price_display(
        self,
        price: Decimal,
        unit: Optional[Unit],
    ) -> str:
        """
        Formata preço para exibição.
        
        Args:
            price: Valor do preço
            unit: Unidade (None para preço bruto)
            
        Returns:
            String formatada (ex: "R$ 25,99/kg")
        """
        # Formata valor no padrão brasileiro
        price_str = f"{price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        
        if unit:
            return f"R$ {price_str}/{unit.value}"
        else:
            return f"R$ {price_str}"
    
    def compare_offers(
        self,
        offers: list[PriceOffer],
        ascending: bool = True,
    ) -> list[PriceOffer]:
        """
        Ordena ofertas por preço normalizado.
        
        Args:
            offers: Lista de ofertas
            ascending: Se True, menor preço primeiro
            
        Returns:
            Lista ordenada (comparáveis primeiro, depois não-comparáveis)
        """
        # Separa ofertas comparáveis e não-comparáveis
        comparable = [o for o in offers if o.is_comparable]
        non_comparable = [o for o in offers if not o.is_comparable]
        
        # Ordena comparáveis por preço normalizado
        comparable_sorted = sorted(
            comparable,
            key=lambda o: o.normalized_price or Decimal("inf"),
            reverse=not ascending,
        )
        
        # Não-comparáveis ordenados por preço bruto
        non_comparable_sorted = sorted(
            non_comparable,
            key=lambda o: o.price,
            reverse=not ascending,
        )
        
        return comparable_sorted + non_comparable_sorted
    
    def find_best_offer(
        self,
        offers: list[PriceOffer],
    ) -> Optional[PriceOffer]:
        """
        Encontra a melhor oferta (menor preço normalizado).
        
        Args:
            offers: Lista de ofertas
            
        Returns:
            Melhor oferta ou None se não houver comparáveis
        """
        comparable = [o for o in offers if o.is_comparable]
        if not comparable:
            return None
        
        return min(
            comparable,
            key=lambda o: o.normalized_price or Decimal("inf"),
        )
    
    def calculate_savings(
        self,
        best_offer: PriceOffer,
        other_offer: PriceOffer,
    ) -> Optional[dict]:
        """
        Calcula economia entre duas ofertas.
        
        Args:
            best_offer: Melhor oferta (referência)
            other_offer: Outra oferta para comparar
            
        Returns:
            Dicionário com economia absoluta e percentual
        """
        if not (best_offer.is_comparable and other_offer.is_comparable):
            return None
        
        if best_offer.normalized_unit != other_offer.normalized_unit:
            return None
        
        best_price = best_offer.normalized_price
        other_price = other_offer.normalized_price
        
        if best_price is None or other_price is None:
            return None
        
        absolute_diff = other_price - best_price
        
        if other_price > 0:
            percentage_diff = (absolute_diff / other_price) * 100
        else:
            percentage_diff = Decimal("0")
        
        return {
            "absolute": absolute_diff.quantize(self._quantize_exp),
            "percentage": percentage_diff.quantize(Decimal("0.1")),
            "best_market": best_offer.market_name,
            "compared_market": other_offer.market_name,
            "unit": best_offer.normalized_unit.value if best_offer.normalized_unit else None,
        }