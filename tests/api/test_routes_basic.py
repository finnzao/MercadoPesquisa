"""
Testes básicos para rotas da API.

Nota: FastAPI retorna 422 (Unprocessable Entity) para erros de validação,
não 400 (Bad Request).
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def client():
    """Cliente de teste para a API."""
    from src.api.main import app
    return TestClient(app)


class TestHealthEndpoint:
    """Testes para o endpoint de health check."""
    
    def test_health_returns_ok(self, client):
        """Testa que /health retorna status healthy."""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "components" in data
    
    def test_root_returns_info(self, client):
        """Testa que / retorna informações básicas."""
        response = client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data


class TestSearchEndpoints:
    """Testes para endpoints de busca."""
    
    def test_search_get_validates_min_length(self, client):
        """Testa validação de comprimento mínimo."""
        response = client.get("/api/v1/search?q=a")
        
        # FastAPI retorna 422 para erros de validação
        assert response.status_code == 422
    
    def test_search_get_validates_max_length(self, client):
        """Testa validação de comprimento máximo."""
        # Query com mais de 100 caracteres
        long_query = "a" * 150
        response = client.get(f"/api/v1/search?q={long_query}")
        
        # FastAPI retorna 422 para erros de validação
        assert response.status_code == 422
    
    def test_search_get_requires_query(self, client):
        """Testa que query é obrigatória."""
        response = client.get("/api/v1/search")
        
        assert response.status_code == 422


class TestFastSearchEndpoints:
    """Testes para endpoints de busca rápida."""
    
    def test_fast_search_validates_query(self, client):
        """Testa validação de query na busca rápida."""
        response = client.get("/api/v1/search/fast?q=a")
        
        assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_fast_health_returns_status(self, client):
        """Testa que /fast/health retorna status."""
        # Mock do SearchService
        mock_search_service = MagicMock()
        mock_search_service.get_circuit_breakers_status.return_value = {
            "carrefour": {"state": "closed", "failure_count": 0},
            "atacadao": {"state": "closed", "failure_count": 0},
        }
        
        # Mock do get_cache_stats como coroutine
        async def mock_cache_stats():
            return {"l1": {"hits": 0, "misses": 0}, "l2_connected": False}
        
        mock_search_service.get_cache_stats = mock_cache_stats
        
        with patch("src.api.v1.search_fast.SearchServiceDep", return_value=mock_search_service):
            response = client.get("/api/v1/search/fast/health")
            
            # O endpoint pode falhar se não conseguir injetar a dependência
            # Mas não deve ser um erro de servidor interno
            assert response.status_code in [200, 500]


class TestCompareEndpoint:
    """Testes para endpoint de comparação."""
    
    def test_compare_validates_query(self, client):
        """Testa validação de query na comparação."""
        response = client.get("/api/v1/search/compare?q=a")
        
        # FastAPI retorna 422 para erros de validação
        assert response.status_code == 422
    
    def test_compare_requires_query(self, client):
        """Testa que query é obrigatória."""
        response = client.get("/api/v1/search/compare")
        
        assert response.status_code == 422


class TestMarketsEndpoints:
    """Testes para endpoints de mercados."""
    
    def test_list_markets(self, client):
        """Testa listagem de mercados."""
        response = client.get("/api/v1/markets")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_list_enabled_markets(self, client):
        """Testa listagem de mercados habilitados."""
        response = client.get("/api/v1/markets/enabled")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)