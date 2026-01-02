"""
Processador de Lista de Compras.
Coordena a busca de múltiplos itens e encontra os melhores preços.
"""

import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Optional

from config.logging_config import LoggerMixin, get_logger
from config.markets import get_active_markets
from src.core.models import PriceOffer
from src.pipeline import ProcessingPipeline
from src.ranking import RankingStrategy, FuzzyMatcher
from src.scrapers import ScraperManager
from src.shopping_list.models import (
    ShoppingItem,
    ShoppingListResult,
    ItemResult,
)


class ShoppingListProcessor(LoggerMixin):
    """
    Processador de lista de compras.
    
    Busca cada item da lista em todos os mercados disponíveis
    e retorna o melhor preço encontrado para cada um.
    
    Exemplo de uso:
        processor = ShoppingListProcessor()
        
        items = [
            ShoppingItem("arroz 5kg", quantity=2),
            ShoppingItem("feijão 1kg"),
            ShoppingItem("leite integral 1L", quantity=6),
        ]
        
        result = await processor.process(items, cep="01310100")
        
        for item in result.items:
            print(f"{item.item_name}: {item.formatted_price} - {item.market_name}")
    """
    
    def __init__(
        self,
        ranking_strategy: RankingStrategy = RankingStrategy.PRICE_FIRST,
        include_alternatives: bool = True,
        max_alternatives: int = 2,
    ):
        """
        Inicializa o processador.
        
        Args:
            ranking_strategy: Estratégia de ranking para buscas
            include_alternatives: Se deve incluir ofertas alternativas
            max_alternatives: Máximo de alternativas por item
        """
        self.ranking_strategy = ranking_strategy
        self.include_alternatives = include_alternatives
        self.max_alternatives = max_alternatives
        
        # Componentes
        self.scraper_manager = ScraperManager()
        self.pipeline = ProcessingPipeline(
            ranking_strategy=ranking_strategy,
            filter_irrelevant=False,  # Queremos ver todas as ofertas
        )
        self.matcher = FuzzyMatcher()
        
        # Logger é herdado do LoggerMixin via property
    
    async def process(
        self,
        items: list[ShoppingItem],
        cep: Optional[str] = None,
        markets: Optional[list[str]] = None,
        max_pages: int = 1,
    ) -> ShoppingListResult:
        """
        Processa lista de compras e encontra melhores preços.
        
        Args:
            items: Lista de itens para buscar
            cep: CEP para localização (opcional)
            markets: Lista de mercados específicos (None = todos)
            max_pages: Máximo de páginas por busca
            
        Returns:
            ShoppingListResult com todos os resultados
        """
        if not items:
            self.logger.warning("Lista de compras vazia")
            return ShoppingListResult()
        
        # Inicializa resultado
        target_markets = markets or [m.id for m in get_active_markets()]
        
        result = ShoppingListResult(
            cep=cep,
            markets_searched=target_markets,
        )
        
        self.logger.info(
            "Processando lista de compras",
            total_items=len(items),
            cep=cep,
            markets=target_markets,
        )
        
        # Processa cada item
        for item in items:
            self.logger.info(f"Buscando: {item.name}")
            
            try:
                item_result = await self._process_item(
                    item=item,
                    cep=cep,
                    markets=target_markets,
                    max_pages=max_pages,
                )
                
                if item_result.found:
                    result.items.append(item_result)
                else:
                    result.not_found.append(item.name)
                    # Adiciona mesmo assim para manter registro
                    result.items.append(item_result)
                    
            except Exception as e:
                self.logger.error(
                    f"Erro ao processar item: {item.name}",
                    error=str(e),
                )
                result.not_found.append(item.name)
                result.items.append(ItemResult(
                    item_name=item.name,
                    item_quantity=item.quantity,
                    found=False,
                ))
        
        result.mark_finished()
        
        self.logger.info(
            "Lista processada",
            total=len(items),
            found=result.items_found,
            not_found=len(result.not_found),
            total_estimated=str(result.total_estimated),
            duration=f"{result.duration_seconds:.2f}s" if result.duration_seconds else "N/A",
        )
        
        return result
    
    async def process_text(
        self,
        text: str,
        cep: Optional[str] = None,
        markets: Optional[list[str]] = None,
    ) -> ShoppingListResult:
        """
        Processa lista de compras a partir de texto.
        
        Aceita texto com um item por linha, opcionalmente com quantidade.
        
        Formatos aceitos:
            - "arroz 5kg"
            - "2x leite integral 1L"
            - "feijão 1kg (quantidade: 3)"
            - "3 - açúcar 1kg"
        
        Args:
            text: Texto com lista de itens
            cep: CEP para localização
            markets: Lista de mercados
            
        Returns:
            ShoppingListResult
        """
        items = self._parse_text_list(text)
        return await self.process(items, cep=cep, markets=markets)
    
    def _parse_text_list(self, text: str) -> list[ShoppingItem]:
        """
        Faz parsing de texto para lista de itens.
        
        Args:
            text: Texto com um item por linha
            
        Returns:
            Lista de ShoppingItem
        """
        import re
        
        items = []
        lines = text.strip().split("\n")
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            
            # Remove numeração de lista (1. 2. - * etc)
            line = re.sub(r"^[\d\.\-\*\•]+\s*", "", line)
            
            # Tenta extrair quantidade
            quantity = 1
            name = line
            
            # Formato: "2x item" ou "2 x item"
            match = re.match(r"^(\d+)\s*[xX]\s+(.+)$", line)
            if match:
                quantity = int(match.group(1))
                name = match.group(2)
            
            # Formato: "item (quantidade: 3)" ou "item (qty: 3)"
            match = re.search(r"\((?:quantidade|qty|qtd)[:\s]*(\d+)\)", line, re.IGNORECASE)
            if match:
                quantity = int(match.group(1))
                name = re.sub(r"\s*\((?:quantidade|qty|qtd)[:\s]*\d+\)", "", line, flags=re.IGNORECASE)
            
            # Formato: "3 - item" ou "3- item"
            match = re.match(r"^(\d+)\s*-\s*(.+)$", line)
            if match:
                quantity = int(match.group(1))
                name = match.group(2)
            
            name = name.strip()
            if name:
                items.append(ShoppingItem(name=name, quantity=quantity))
        
        return items
    
    async def _process_item(
        self,
        item: ShoppingItem,
        cep: Optional[str],
        markets: list[str],
        max_pages: int,
    ) -> ItemResult:
        """
        Processa um único item da lista.
        
        Args:
            item: Item para buscar
            cep: CEP
            markets: Lista de mercados
            max_pages: Máximo de páginas
            
        Returns:
            ItemResult com melhor oferta
        """
        start_time = datetime.now()
        
        # Busca em todos os mercados
        raw_products, metadata = await self.scraper_manager.search_all(
            query=item.name,
            cep=cep,
            max_pages=max_pages,
            markets=markets,
        )
        
        if not raw_products:
            return ItemResult(
                item_name=item.name,
                item_quantity=item.quantity,
                found=False,
                total_offers_found=0,
                search_time_seconds=(datetime.now() - start_time).total_seconds(),
            )
        
        # Processa pelo pipeline
        offers = self.pipeline.process_batch(
            raw_products,
            apply_ranking=True,
            search_query=item.name,
        )
        
        if not offers:
            return ItemResult(
                item_name=item.name,
                item_quantity=item.quantity,
                found=False,
                total_offers_found=len(raw_products),
                search_time_seconds=(datetime.now() - start_time).total_seconds(),
            )
        
        # Filtra ofertas relevantes
        relevant_offers = [
            o for o in offers
            if self.matcher.is_relevant(item.name, o.title)
        ]
        
        # Se não houver relevantes, usa todas
        search_offers = relevant_offers if relevant_offers else offers
        
        # Encontra a melhor oferta (menor preço normalizado)
        best_offer = self._find_best_offer(search_offers)
        
        if not best_offer:
            return ItemResult(
                item_name=item.name,
                item_quantity=item.quantity,
                found=False,
                total_offers_found=len(offers),
                relevant_offers=len(relevant_offers),
                search_time_seconds=(datetime.now() - start_time).total_seconds(),
            )
        
        # Cria resultado
        result = self._offer_to_item_result(
            offer=best_offer,
            item=item,
            total_offers=len(offers),
            relevant_offers=len(relevant_offers),
        )
        result.search_time_seconds = (datetime.now() - start_time).total_seconds()
        
        # Adiciona alternativas
        if self.include_alternatives:
            alternatives = self._get_alternatives(
                offers=search_offers,
                best_offer=best_offer,
                item=item,
            )
            result.alternatives = alternatives
        
        return result
    
    def _find_best_offer(self, offers: list[PriceOffer]) -> Optional[PriceOffer]:
        """
        Encontra a melhor oferta (menor preço).
        
        Prioriza preço normalizado, depois preço bruto.
        
        Args:
            offers: Lista de ofertas
            
        Returns:
            Melhor oferta ou None
        """
        if not offers:
            return None
        
        # Separa comparáveis e não comparáveis
        comparable = [o for o in offers if o.is_comparable]
        
        if comparable:
            # Ordena por preço normalizado
            return min(comparable, key=lambda o: o.normalized_price or Decimal("inf"))
        
        # Fallback: ordena por preço bruto
        return min(offers, key=lambda o: o.price)
    
    def _get_alternatives(
        self,
        offers: list[PriceOffer],
        best_offer: PriceOffer,
        item: ShoppingItem,
    ) -> list[ItemResult]:
        """
        Obtém ofertas alternativas (de outros mercados).
        
        Args:
            offers: Todas as ofertas
            best_offer: Melhor oferta já selecionada
            item: Item original
            
        Returns:
            Lista de alternativas
        """
        alternatives = []
        seen_markets = {best_offer.market_id}
        
        # Ordena por preço
        if best_offer.is_comparable:
            sorted_offers = sorted(
                [o for o in offers if o.is_comparable],
                key=lambda o: o.normalized_price or Decimal("inf"),
            )
        else:
            sorted_offers = sorted(offers, key=lambda o: o.price)
        
        for offer in sorted_offers:
            if offer.id == best_offer.id:
                continue
            
            # Pula se já temos uma alternativa deste mercado
            if offer.market_id in seen_markets:
                continue
            
            seen_markets.add(offer.market_id)
            
            alt_result = self._offer_to_item_result(
                offer=offer,
                item=item,
                total_offers=0,
                relevant_offers=0,
            )
            alternatives.append(alt_result)
            
            if len(alternatives) >= self.max_alternatives:
                break
        
        return alternatives
    
    def _offer_to_item_result(
        self,
        offer: PriceOffer,
        item: ShoppingItem,
        total_offers: int,
        relevant_offers: int,
    ) -> ItemResult:
        """
        Converte PriceOffer para ItemResult.
        
        Args:
            offer: Oferta encontrada
            item: Item original
            total_offers: Total de ofertas encontradas
            relevant_offers: Total de ofertas relevantes
            
        Returns:
            ItemResult
        """
        return ItemResult(
            item_name=item.name,
            item_quantity=item.quantity,
            found=True,
            product_title=offer.title,
            price=offer.price,
            normalized_price=offer.normalized_price,
            normalized_unit=offer.normalized_unit.value if offer.normalized_unit else None,
            price_display=offer.price_display,
            market_id=offer.market_id,
            market_name=offer.market_name,
            product_url=offer.url,
            image_url=offer.image_url,
            total_offers_found=total_offers,
            relevant_offers=relevant_offers,
        )


async def process_shopping_list(
    items: list[str],
    cep: Optional[str] = None,
    markets: Optional[list[str]] = None,
) -> ShoppingListResult:
    """
    Função de conveniência para processar lista de compras.
    
    Args:
        items: Lista de strings com nomes dos itens
        cep: CEP para localização
        markets: Lista de mercados
        
    Returns:
        ShoppingListResult
    
    Exemplo:
        result = await process_shopping_list([
            "arroz 5kg",
            "feijão 1kg",
            "leite 1L",
        ])
    """
    processor = ShoppingListProcessor()
    shopping_items = [ShoppingItem(name=item) for item in items]
    return await processor.process(shopping_items, cep=cep, markets=markets)


async def process_shopping_list_text(
    text: str,
    cep: Optional[str] = None,
    markets: Optional[list[str]] = None,
) -> ShoppingListResult:
    """
    Função de conveniência para processar lista de texto.
    
    Args:
        text: Texto com lista (um item por linha)
        cep: CEP para localização
        markets: Lista de mercados
        
    Returns:
        ShoppingListResult
    
    Exemplo:
        result = await process_shopping_list_text('''
            arroz 5kg
            2x feijão 1kg
            leite integral 1L (quantidade: 6)
        ''')
    """
    processor = ShoppingListProcessor()
    return await processor.process_text(text, cep=cep, markets=markets)