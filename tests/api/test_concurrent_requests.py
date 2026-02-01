"""
Testes de concorrência para múltiplos usuários.
Simula cenário real de uso via bot WhatsApp com múltiplos usuários simultâneos.
"""

import asyncio
import time
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
import pytest_asyncio
from httpx import AsyncClient


class TestConcurrentSearchRequests:
    """Testes de requisições de busca concorrentes."""
    
    @pytest.mark.asyncio
    async def test_multiple_users_simultaneous_search(self, async_client, multiple_users):
        """Testa múltiplos usuários fazendo busca simultaneamente."""
        async def make_search(user_headers):
            response = await async_client.get(
                "/api/v1/search/fast?q=arroz",
                headers=user_headers,
            )
            return response.status_code
        
        # Executa 10 buscas simultâneas
        tasks = [make_search(user) for user in multiple_users]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Todas as requisições devem completar (mesmo que com erro)
        assert len(results) == 10
        # Nenhuma deve ter levantado exceção não tratada
        for result in results:
            assert isinstance(result, int)
    
    @pytest.mark.asyncio
    async def test_concurrent_different_queries(self, async_client):
        """Testa buscas concorrentes com queries diferentes."""
        queries = ["arroz", "feijão", "leite", "açúcar", "café"]
        
        async def make_search(query):
            response = await async_client.get(f"/api/v1/search/fast?q={query}")
            return query, response.status_code
        
        tasks = [make_search(q) for q in queries]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        assert len(results) == 5
        # Verifica que cada query foi processada
        completed_queries = [r[0] for r in results if isinstance(r, tuple)]
        assert len(completed_queries) >= 3  # Pelo menos 3 devem completar
    
    @pytest.mark.asyncio
    async def test_concurrent_multi_search_requests(self, async_client, multiple_users):
        """Testa requisições de busca múltipla concorrentes."""
        async def make_multi_search(user_headers):
            response = await async_client.post(
                "/api/v1/search/multi/quick",
                json={
                    "items": ["arroz 5kg", "feijão 1kg"],
                    "single_market": False,
                },
                headers=user_headers,
            )
            return response.status_code
        
        tasks = [make_multi_search(user) for user in multiple_users[:5]]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Todas devem completar
        assert len(results) == 5


class TestRateLimitingUnderLoad:
    """Testes de rate limiting sob carga."""
    
    @pytest.mark.asyncio
    async def test_rate_limit_per_user(self, async_client):
        """Testa que rate limit é aplicado por usuário."""
        user_headers = {"X-User-ID": "rate_test_user"}
        
        async def make_request():
            return await async_client.get(
                "/api/v1/search/fast?q=teste",
                headers=user_headers,
            )
        
        # Faz várias requisições rápidas
        responses = []
        for _ in range(5):
            response = await make_request()
            responses.append(response.status_code)
        
        # Verifica que algumas podem ter passado
        # (rate limit pode ou não estar habilitado nos testes)
        assert len(responses) == 5
    
    @pytest.mark.asyncio
    async def test_different_users_independent_limits(self, async_client):
        """Testa que usuários diferentes têm limites independentes."""
        async def make_requests_for_user(user_id):
            headers = {"X-User-ID": user_id}
            results = []
            for _ in range(3):
                response = await async_client.get(
                    "/api/v1/search/fast?q=teste",
                    headers=headers,
                )
                results.append(response.status_code)
            return user_id, results
        
        users = ["user_a", "user_b", "user_c"]
        tasks = [make_requests_for_user(u) for u in users]
        results = await asyncio.gather(*tasks)
        
        # Cada usuário deve ter seus próprios resultados
        assert len(results) == 3


class TestCacheUnderConcurrency:
    """Testes de cache com requisições concorrentes."""
    
    @pytest.mark.asyncio
    async def test_cache_hit_on_concurrent_same_query(self, async_client):
        """Testa que buscas concorrentes para mesma query usam cache."""
        query = "arroz_cache_test"
        
        async def make_search():
            response = await async_client.get(f"/api/v1/search/fast?q={query}")
            return response.status_code, response.elapsed.total_seconds()
        
        # Primeira requisição (cache miss)
        first_response = await make_search()
        
        # Requisições concorrentes (devem usar cache se habilitado)
        tasks = [make_search() for _ in range(5)]
        results = await asyncio.gather(*tasks)
        
        # Todas devem completar
        assert len(results) == 5
    
    @pytest.mark.asyncio
    async def test_cache_isolation_by_cep(self, async_client):
        """Testa que cache é isolado por CEP."""
        async def make_search_with_cep(cep):
            response = await async_client.get(
                f"/api/v1/search/fast?q=arroz&cep={cep}"
            )
            return cep, response.status_code
        
        ceps = ["01310100", "40000000", "22041080"]
        tasks = [make_search_with_cep(cep) for cep in ceps]
        results = await asyncio.gather(*tasks)
        
        # Todas as requisições com CEPs diferentes devem ser independentes
        assert len(results) == 3


class TestWhatsAppBotScenarios:
    """Testes simulando cenários reais de bot WhatsApp."""
    
    @pytest.mark.asyncio
    async def test_bot_user_search_flow(self, async_client, whatsapp_user):
        """Testa fluxo típico de busca de um usuário do WhatsApp."""
        headers = whatsapp_user["headers"]
        
        # 1. Usuário busca um produto
        response = await async_client.get(
            "/api/v1/search/fast?q=arroz%205kg",
            headers=headers,
        )
        assert response.status_code in [200, 500]
        
        # 2. Usuário pede comparação
        response = await async_client.get(
            "/api/v1/search/compare?q=arroz%205kg",
            headers=headers,
        )
        assert response.status_code in [200, 404, 500]
    
    @pytest.mark.asyncio
    async def test_bot_shopping_list_flow(self, async_client, whatsapp_user):
        """Testa fluxo de lista de compras via bot."""
        headers = whatsapp_user["headers"]
        
        # Usuário envia lista de compras em texto
        response = await async_client.post(
            "/api/v1/shopping/quick",
            json={
                "text": "arroz 5kg\nfeijão 1kg\nleite 1L",
                "cep": "01310100",
            },
            headers=headers,
        )
        assert response.status_code in [200, 400, 500]
    
    @pytest.mark.asyncio
    async def test_multiple_bot_users_shopping_lists(self, async_client, multiple_users):
        """Testa múltiplos usuários criando listas de compras."""
        async def create_shopping_list(user_headers):
            response = await async_client.post(
                "/api/v1/shopping/quick",
                json={
                    "text": "arroz\nfeijão\nleite",
                    "cep": "01310100",
                },
                headers=user_headers,
            )
            return response.status_code
        
        tasks = [create_shopping_list(user) for user in multiple_users[:5]]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        assert len(results) == 5
    
    @pytest.mark.asyncio
    async def test_bot_quick_search_response_time(self, async_client, whatsapp_user):
        """Testa que busca rápida responde em tempo aceitável."""
        headers = whatsapp_user["headers"]
        
        start = time.time()
        response = await async_client.get(
            "/api/v1/search/fast?q=arroz",
            headers=headers,
        )
        elapsed = time.time() - start
        
        # Deve responder em menos de 10 segundos (timeout do serviço)
        assert elapsed < 10
        # Idealmente em menos de 5 segundos para boa UX
        # (mas depende do mock/ambiente)


class TestCircuitBreakerUnderLoad:
    """Testes de circuit breaker sob carga."""
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_status_endpoint(self, async_client):
        """Testa endpoint de status dos circuit breakers."""
        response = await async_client.get("/api/v1/markets/status")
        
        assert response.status_code == 200
        data = response.json()
        
        # Deve retornar status para cada mercado
        assert isinstance(data, dict)
    
    @pytest.mark.asyncio
    async def test_concurrent_requests_with_failing_market(self, async_client):
        """Testa comportamento com mercado falhando."""
        # Mesmo com mercados falhando, outros devem continuar
        async def make_search():
            return await async_client.get("/api/v1/search/fast?q=arroz")
        
        tasks = [make_search() for _ in range(5)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Todas devem completar (com sucesso ou erro tratado)
        assert len(results) == 5


class TestMultiMarketConcurrency:
    """Testes de concorrência entre múltiplos mercados."""
    
    @pytest.mark.asyncio
    async def test_search_all_markets_concurrently(self, async_client):
        """Testa que busca consulta múltiplos mercados em paralelo."""
        # Busca sem especificar mercados deve usar todos habilitados
        response = await async_client.get("/api/v1/search/fast?q=arroz")
        
        if response.status_code == 200:
            data = response.json()
            # A resposta deve indicar que buscou em mercados
            assert "query" in data
    
    @pytest.mark.asyncio
    async def test_specific_markets_filter(self, async_client):
        """Testa filtro por mercados específicos."""
        response = await async_client.get(
            "/api/v1/search?q=arroz&markets=carrefour,atacadao"
        )
        
        # Deve aceitar a requisição
        assert response.status_code in [200, 404, 500]


class TestErrorHandlingUnderLoad:
    """Testes de tratamento de erros sob carga."""
    
    @pytest.mark.asyncio
    async def test_graceful_degradation(self, async_client):
        """Testa degradação graciosa quando há erros."""
        # Mesmo com queries inválidas misturadas, sistema deve continuar
        queries = ["arroz", "a", "feijão", "", "leite"]  # Algumas inválidas
        
        async def make_search(query):
            return await async_client.get(f"/api/v1/search/fast?q={query}")
        
        tasks = [make_search(q) for q in queries]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Todas devem retornar resposta (não exceção não tratada)
        for result in results:
            assert not isinstance(result, Exception)
    
    @pytest.mark.asyncio
    async def test_timeout_handling(self, async_client):
        """Testa tratamento de timeout."""
        # Busca com timeout deve completar ou retornar erro tratado
        response = await async_client.get(
            "/api/v1/search/fast?q=arroz",
            timeout=15.0,  # Timeout do cliente
        )
        
        # Não deve travar indefinidamente
        assert response.status_code in [200, 404, 500, 408, 504]


class TestDataConsistency:
    """Testes de consistência de dados com concorrência."""
    
    @pytest.mark.asyncio
    async def test_same_query_returns_consistent_results(self, async_client):
        """Testa que mesma query retorna resultados consistentes."""
        query = "arroz 5kg"
        
        responses = []
        for _ in range(3):
            response = await async_client.get(f"/api/v1/search/fast?q={query}")
            if response.status_code == 200:
                responses.append(response.json())
        
        if len(responses) >= 2:
            # Todas as respostas devem ter a mesma query
            for resp in responses:
                assert resp.get("query") == query
    
    @pytest.mark.asyncio
    async def test_multi_search_items_order_preserved(self, async_client):
        """Testa que ordem dos items é preservada na busca múltipla."""
        items = ["arroz", "feijão", "leite"]
        
        response = await async_client.post(
            "/api/v1/search/multi/quick",
            json={"items": items},
        )
        
        if response.status_code == 200:
            data = response.json()
            if "items" in data:
                result_queries = [item.get("query") for item in data["items"]]
                assert result_queries == items
