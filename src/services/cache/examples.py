"""
Exemplo de integração do Cache com TTL Dinâmico na API.

Este arquivo mostra como integrar o novo sistema de cache na sua aplicação.
"""

# =============================================================================
# 1. INTEGRAÇÃO NO main.py DA API
# =============================================================================

"""
# No arquivo src/api/main.py, adicione:

from contextlib import asynccontextmanager
from fastapi import FastAPI
from config.settings import settings

# Importa o novo cache service
from src.services.cache_service import init_cache_service, get_cache_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    cache = await init_cache_service(
        redis_url=settings.redis_url,
        l1_max_size=1000,
        l1_default_ttl=60,
        l2_default_ttl=300
    )
    
    yield
    
    # Shutdown
    await cache.close()


app = FastAPI(lifespan=lifespan)
"""


# =============================================================================
# 2. USO NO SEARCH SERVICE
# =============================================================================

"""
# No arquivo src/services/search_service.py, modifique:

from src.services.cache_service import get_cache_service


class SearchService:
    
    async def search(
        self,
        query: str,
        cep: str = None,
        markets: list[str] = None,
        **kwargs
    ):
        cache = await get_cache_service()
        
        # Gera chave do cache
        cache_key = cache._generate_cache_key(query, cep, markets)
        
        # Tenta buscar no cache
        cached_result = await cache.get(cache_key)
        if cached_result:
            return cached_result
        
        # Executa busca nos scrapers
        results = await self._execute_search(query, cep, markets, **kwargs)
        
        # Verifica se há itens promocionais
        has_promo = any(r.get("is_promotional") for r in results.get("results", []))
        
        # Armazena no cache com TTL dinâmico
        await cache.set(
            key=cache_key,
            value=results,
            market_ids=markets or self._get_all_market_ids(),
            is_promotional=has_promo,
            query_popularity=await self._get_query_popularity(query)
        )
        
        return results
"""


# =============================================================================
# 3. EXEMPLO COMPLETO DE USO
# =============================================================================

import asyncio
import sys
import os

# Adiciona o diretório atual ao path para imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dynamic_ttl import DynamicTTLCalculator, TTLConfig
from cache_service import CacheService, init_cache_service


async def exemplo_ttl_calculator():
    """Demonstra o uso do calculador de TTL dinâmico."""
    
    print("=" * 60)
    print("EXEMPLO: Calculador de TTL Dinâmico")
    print("=" * 60)
    
    calculator = DynamicTTLCalculator()
    
    # Cenário 1: Busca normal no Carrefour
    print("\n1. Busca normal no Carrefour:")
    ttl_info = calculator.get_ttl_info(market_id="carrefour")
    print(f"   Período: {ttl_info['period']}")
    print(f"   Dia: {ttl_info['weekday_name']}")
    print(f"   TTL base: {ttl_info['base_ttl_seconds']}s")
    print(f"   Multiplicadores: {ttl_info['multipliers']}")
    print(f"   TTL final: {ttl_info['final_ttl_formatted']}")
    
    # Cenário 2: Produto promocional no Atacadão
    print("\n2. Produto promocional no Atacadão:")
    ttl_info = calculator.get_ttl_info(
        market_id="atacadao",
        is_promotional=True
    )
    print(f"   TTL final: {ttl_info['final_ttl_formatted']}")
    print(f"   (Multiplicador promocional: {ttl_info['multipliers']['promotional']})")
    
    # Cenário 3: Busca muito popular
    print("\n3. Busca popular (arroz 5kg):")
    ttl_info = calculator.get_ttl_info(
        market_id="carrefour",
        query_popularity=0.9
    )
    print(f"   TTL final: {ttl_info['final_ttl_formatted']}")
    print(f"   (Multiplicador popularidade: {ttl_info['multipliers']['popularity']})")
    
    # Cenário 4: Múltiplos mercados
    print("\n4. Busca em múltiplos mercados:")
    ttl = calculator.calculate_ttl_for_search(
        query="leite",
        market_ids=["carrefour", "atacadao", "gbarbosa"]
    )
    print(f"   TTL usado (menor entre os mercados): {ttl}s ({ttl // 60}m {ttl % 60}s)")


async def exemplo_cache_service():
    """Demonstra o uso do CacheService."""
    
    print("\n" + "=" * 60)
    print("EXEMPLO: Cache Service com TTL Dinâmico")
    print("=" * 60)
    
    # Inicializa sem Redis (apenas L1)
    cache = CacheService(
        redis_url=None,  # Sem Redis para este exemplo
        l1_max_size=100
    )
    await cache.initialize()
    
    try:
        # Simula resultado de busca
        search_result = {
            "query": "arroz 5kg",
            "total_results": 25,
            "best_offer": {
                "title": "Arroz Tipo 1 Tio João 5kg",
                "price": 24.99,
                "market": "atacadao"
            },
            "results": [
                {"title": "Arroz 1", "price": 24.99},
                {"title": "Arroz 2", "price": 25.99},
                {"title": "Arroz 3", "price": 26.49},
            ]
        }
        
        # 1. Armazena no cache
        print("\n1. Armazenando busca no cache...")
        key = "search:arroz-5kg:default"
        await cache.set(
            key=key,
            value=search_result,
            market_id="atacadao",
            is_promotional=False,
            query_popularity=0.7
        )
        print(f"   Chave: {key}")
        
        # 2. Busca no cache
        print("\n2. Buscando no cache...")
        result = await cache.get(key)
        if result:
            print(f"   Cache HIT!")
            print(f"   Query: {result['query']}")
            print(f"   Total resultados: {result['total_results']}")
        
        # 3. Estatísticas
        print("\n3. Estatísticas do cache:")
        stats = cache.get_stats()
        print(f"   L1 hits: {stats['l1']['hits']}")
        print(f"   L1 misses: {stats['l1']['misses']}")
        print(f"   L1 size: {stats['l1_size']}/{stats['l1_max_size']}")
        
        # 4. Cache miss
        print("\n4. Buscando chave inexistente...")
        result = await cache.get("search:inexistente")
        if result is None:
            print("   Cache MISS (esperado)")
        
        # 5. Estatísticas atualizadas
        print("\n5. Estatísticas atualizadas:")
        stats = cache.get_stats()
        print(f"   L1 hits: {stats['l1']['hits']}")
        print(f"   L1 misses: {stats['l1']['misses']}")
        print(f"   Hit rate: {stats['l1']['hit_rate']}")
        
        # 6. Invalidação por padrão
        print("\n6. Invalidando cache por padrão...")
        deleted = await cache.delete_pattern("search:*")
        print(f"   Chaves removidas: {deleted}")
        
    finally:
        await cache.close()


async def exemplo_integracao_api():
    """
    Exemplo de como ficaria a integração completa na API.
    Este é um pseudo-código para referência.
    """
    
    print("\n" + "=" * 60)
    print("EXEMPLO: Integração na API (pseudo-código)")
    print("=" * 60)
    
    print("""
    # src/api/routes/search.py
    
    from fastapi import APIRouter, Query
    from src.services.cache_service import get_cache_service
    
    router = APIRouter()
    
    @router.get("/search")
    async def search(
        q: str = Query(..., description="Termo de busca"),
        cep: str = Query(None, description="CEP para mercados regionais"),
        markets: str = Query(None, description="Mercados separados por vírgula")
    ):
        cache = await get_cache_service()
        
        # Parse markets
        market_list = markets.split(",") if markets else None
        
        # Gera chave
        cache_key = f"search:{q}:{cep or 'default'}:{markets or 'all'}"
        
        # Tenta cache
        cached = await cache.get(cache_key)
        if cached:
            return {"source": "cache", **cached}
        
        # Executa busca
        results = await execute_search(q, cep, market_list)
        
        # Detecta promoções
        has_promo = any(r.get("promotional") for r in results["offers"])
        
        # Calcula popularidade (simplificado)
        popularity = min(results["total"] / 100, 1.0)
        
        # Armazena com TTL dinâmico
        await cache.set(
            key=cache_key,
            value=results,
            market_ids=market_list,
            is_promotional=has_promo,
            query_popularity=popularity
        )
        
        return {"source": "fresh", **results}
    """)


async def main():
    """Executa todos os exemplos."""
    await exemplo_ttl_calculator()
    await exemplo_cache_service()
    await exemplo_integracao_api()
    
    print("\n" + "=" * 60)
    print("Exemplos concluídos!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
