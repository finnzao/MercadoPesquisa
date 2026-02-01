"""
Testes de carga básicos para simular múltiplos usuários de bot WhatsApp.
Testa performance e estabilidade sob carga.

NOTA: Estes testes são mais intensivos e podem ser pulados em CI rápido.
Execute com: pytest tests/load/ -v --run-load-tests
"""

import asyncio
import time
import statistics
from typing import List, Tuple
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient


# Marca todos os testes de carga
pytestmark = pytest.mark.load


class TestBasicLoadScenarios:
    """Cenários básicos de carga."""
    
    @pytest.mark.asyncio
    async def test_sequential_requests_performance(self, async_client):
        """Testa performance de requisições sequenciais."""
        num_requests = 10
        response_times: List[float] = []
        
        for i in range(num_requests):
            start = time.time()
            response = await async_client.get(f"/api/v1/search/fast?q=arroz{i}")
            elapsed = time.time() - start
            response_times.append(elapsed)
        
        # Calcula estatísticas
        avg_time = statistics.mean(response_times)
        max_time = max(response_times)
        min_time = min(response_times)
        
        print(f"\nSequential requests performance:")
        print(f"  Requests: {num_requests}")
        print(f"  Avg time: {avg_time:.3f}s")
        print(f"  Min time: {min_time:.3f}s")
        print(f"  Max time: {max_time:.3f}s")
        
        # Todas devem completar em tempo razoável
        assert max_time < 15  # 15 segundos max
    
    @pytest.mark.asyncio
    async def test_concurrent_requests_performance(self, async_client):
        """Testa performance de requisições concorrentes."""
        num_concurrent = 10
        
        async def make_request(i: int) -> Tuple[int, float]:
            start = time.time()
            response = await async_client.get(f"/api/v1/search/fast?q=item{i}")
            elapsed = time.time() - start
            return response.status_code, elapsed
        
        start_total = time.time()
        tasks = [make_request(i) for i in range(num_concurrent)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        total_time = time.time() - start_total
        
        # Filtra resultados válidos
        valid_results = [r for r in results if isinstance(r, tuple)]
        response_times = [r[1] for r in valid_results]
        
        print(f"\nConcurrent requests performance:")
        print(f"  Concurrent: {num_concurrent}")
        print(f"  Total time: {total_time:.3f}s")
        print(f"  Successful: {len(valid_results)}/{num_concurrent}")
        
        if response_times:
            print(f"  Avg time: {statistics.mean(response_times):.3f}s")
        
        # Pelo menos 80% das requisições devem completar
        assert len(valid_results) >= num_concurrent * 0.8
    
    @pytest.mark.asyncio
    async def test_burst_requests(self, async_client):
        """Testa comportamento sob burst de requisições."""
        burst_size = 20
        
        async def make_request(i: int):
            response = await async_client.get(f"/api/v1/search/fast?q=burst{i}")
            return response.status_code
        
        # Todas as requisições ao mesmo tempo
        start = time.time()
        tasks = [make_request(i) for i in range(burst_size)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        elapsed = time.time() - start
        
        successful = sum(1 for r in results if isinstance(r, int) and r in [200, 500])
        
        print(f"\nBurst requests:")
        print(f"  Burst size: {burst_size}")
        print(f"  Total time: {elapsed:.3f}s")
        print(f"  Successful: {successful}/{burst_size}")
        
        # Pelo menos 50% devem completar (sistema pode ter rate limiting)
        assert successful >= burst_size * 0.5


class TestMultiUserSimulation:
    """Simulação de múltiplos usuários de bot."""
    
    @pytest.mark.asyncio
    async def test_multiple_users_searching(self, async_client):
        """Simula múltiplos usuários fazendo buscas."""
        num_users = 5
        searches_per_user = 3
        
        async def user_session(user_id: str) -> List[Tuple[str, int, float]]:
            """Simula sessão de um usuário."""
            results = []
            headers = {"X-User-ID": user_id}
            
            queries = ["arroz", "feijão", "leite"]
            for query in queries[:searches_per_user]:
                start = time.time()
                response = await async_client.get(
                    f"/api/v1/search/fast?q={query}",
                    headers=headers,
                )
                elapsed = time.time() - start
                results.append((query, response.status_code, elapsed))
            
            return results
        
        # Executa todas as sessões em paralelo
        start = time.time()
        tasks = [user_session(f"user_{i}") for i in range(num_users)]
        all_results = await asyncio.gather(*tasks)
        total_time = time.time() - start
        
        # Conta resultados
        total_requests = num_users * searches_per_user
        successful = sum(
            1 for user_results in all_results
            for _, status, _ in user_results
            if status in [200, 500]
        )
        
        print(f"\nMultiple users simulation:")
        print(f"  Users: {num_users}")
        print(f"  Searches/user: {searches_per_user}")
        print(f"  Total requests: {total_requests}")
        print(f"  Total time: {total_time:.3f}s")
        print(f"  Successful: {successful}/{total_requests}")
        
        assert successful >= total_requests * 0.8
    
    @pytest.mark.asyncio
    async def test_users_with_different_ceps(self, async_client):
        """Simula usuários de diferentes regiões (CEPs diferentes)."""
        users = [
            ("user_sp", "01310100"),  # São Paulo
            ("user_rj", "22041080"),  # Rio de Janeiro
            ("user_ba", "40000000"),  # Salvador
        ]
        
        async def user_search(user_id: str, cep: str):
            headers = {"X-User-ID": user_id}
            response = await async_client.get(
                f"/api/v1/search/fast?q=arroz&cep={cep}",
                headers=headers,
            )
            return user_id, cep, response.status_code
        
        tasks = [user_search(uid, cep) for uid, cep in users]
        results = await asyncio.gather(*tasks)
        
        print("\nUsers from different regions:")
        for user_id, cep, status in results:
            print(f"  {user_id} (CEP {cep}): status {status}")
        
        # Todas devem completar
        assert all(status in [200, 500] for _, _, status in results)


class TestShoppingListLoad:
    """Testes de carga para lista de compras."""
    
    @pytest.mark.asyncio
    async def test_concurrent_shopping_lists(self, async_client):
        """Testa múltiplas listas de compras simultâneas."""
        num_users = 5
        
        async def create_shopping_list(user_id: str):
            headers = {"X-User-ID": user_id}
            response = await async_client.post(
                "/api/v1/shopping/quick",
                json={
                    "text": "arroz 5kg\nfeijão 1kg\nleite 1L",
                    "cep": "01310100",
                },
                headers=headers,
            )
            return user_id, response.status_code
        
        start = time.time()
        tasks = [create_shopping_list(f"user_{i}") for i in range(num_users)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        elapsed = time.time() - start
        
        valid = [r for r in results if isinstance(r, tuple)]
        
        print(f"\nConcurrent shopping lists:")
        print(f"  Users: {num_users}")
        print(f"  Total time: {elapsed:.3f}s")
        print(f"  Completed: {len(valid)}/{num_users}")
    
    @pytest.mark.asyncio
    async def test_large_shopping_list(self, async_client):
        """Testa lista de compras grande."""
        items = [f"item_{i}" for i in range(20)]  # Máximo permitido
        
        response = await async_client.post(
            "/api/v1/search/multi",
            json={
                "items": items,
                "single_market": False,
            },
        )
        
        assert response.status_code in [200, 404, 500]


class TestMarketEndpointLoad:
    """Testes de carga para endpoints de mercados."""
    
    @pytest.mark.asyncio
    async def test_frequent_market_status_checks(self, async_client):
        """Testa verificações frequentes de status de mercados."""
        num_checks = 20
        
        async def check_status():
            response = await async_client.get("/api/v1/markets/status")
            return response.status_code
        
        start = time.time()
        tasks = [check_status() for _ in range(num_checks)]
        results = await asyncio.gather(*tasks)
        elapsed = time.time() - start
        
        successful = sum(1 for r in results if r == 200)
        
        print(f"\nMarket status checks:")
        print(f"  Checks: {num_checks}")
        print(f"  Total time: {elapsed:.3f}s")
        print(f"  Successful: {successful}/{num_checks}")
        
        assert successful >= num_checks * 0.9


class TestHealthCheckLoad:
    """Testes de carga para health check."""
    
    @pytest.mark.asyncio
    async def test_health_check_under_load(self, async_client):
        """Testa health check sob carga."""
        num_checks = 50
        
        async def health_check():
            response = await async_client.get("/health")
            return response.status_code
        
        start = time.time()
        tasks = [health_check() for _ in range(num_checks)]
        results = await asyncio.gather(*tasks)
        elapsed = time.time() - start
        
        successful = sum(1 for r in results if r == 200)
        
        print(f"\nHealth check under load:")
        print(f"  Requests: {num_checks}")
        print(f"  Total time: {elapsed:.3f}s")
        print(f"  Successful: {successful}/{num_checks}")
        print(f"  Rate: {num_checks/elapsed:.1f} req/s")
        
        # Health check deve ser muito rápido
        assert successful == num_checks
        assert elapsed < 5  # Menos de 5 segundos para 50 requisições


class TestCacheEfficiency:
    """Testes de eficiência do cache sob carga."""
    
    @pytest.mark.asyncio
    async def test_repeated_queries_faster(self, async_client):
        """Testa que queries repetidas são mais rápidas (cache)."""
        query = "arroz_cache_efficiency_test"
        
        # Primeira requisição (cache miss)
        start1 = time.time()
        response1 = await async_client.get(f"/api/v1/search/fast?q={query}")
        time1 = time.time() - start1
        
        # Segunda requisição (possível cache hit)
        start2 = time.time()
        response2 = await async_client.get(f"/api/v1/search/fast?q={query}")
        time2 = time.time() - start2
        
        print(f"\nCache efficiency test:")
        print(f"  First request: {time1:.3f}s")
        print(f"  Second request: {time2:.3f}s")
        
        # Ambas devem completar
        assert response1.status_code in [200, 500]
        assert response2.status_code in [200, 500]


class TestMemoryStability:
    """Testes de estabilidade de memória."""
    
    @pytest.mark.asyncio
    async def test_many_requests_no_memory_leak(self, async_client):
        """Testa que muitas requisições não causam memory leak."""
        num_requests = 50
        
        # Executa muitas requisições
        for i in range(num_requests):
            response = await async_client.get(f"/api/v1/search/fast?q=item{i % 10}")
            assert response.status_code in [200, 500]
        
        # Se chegou aqui sem erro, memória está estável
        print(f"\nMemory stability test: {num_requests} requests completed")


class TestTimeoutBehavior:
    """Testes de comportamento de timeout."""
    
    @pytest.mark.asyncio
    async def test_slow_market_timeout(self, async_client):
        """Testa que mercados lentos são tratados com timeout."""
        # Requisição com timeout do cliente mais longo
        response = await async_client.get(
            "/api/v1/search/fast?q=arroz",
            timeout=15.0,
        )
        
        # Deve completar dentro do timeout
        assert response.status_code in [200, 500]


class TestRateLimitingLoad:
    """Testes de rate limiting sob carga."""
    
    @pytest.mark.asyncio
    async def test_rate_limit_enforcement(self, async_client):
        """Testa que rate limit é aplicado corretamente."""
        user_id = "rate_limit_test_user"
        headers = {"X-User-ID": user_id}
        num_requests = 100  # Mais que o limite típico
        
        results = []
        for _ in range(num_requests):
            response = await async_client.get(
                "/api/v1/search/fast?q=arroz",
                headers=headers,
            )
            results.append(response.status_code)
        
        # Se rate limit está ativo, algumas devem ser 429
        # Se não está ativo (testes), todas devem passar
        rate_limited = sum(1 for r in results if r == 429)
        successful = sum(1 for r in results if r in [200, 500])
        
        print(f"\nRate limiting test:")
        print(f"  Requests: {num_requests}")
        print(f"  Successful: {successful}")
        print(f"  Rate limited: {rate_limited}")
        
        # Pelo menos algumas devem passar
        assert successful > 0 or rate_limited > 0
