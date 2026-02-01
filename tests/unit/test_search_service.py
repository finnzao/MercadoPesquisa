"""
Testes unitários para o SearchService.
Testa circuit breakers, cache, rate limiting e orquestração de busca.
"""

import pytest
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.search_service import (
    SearchService,
    SearchRequest,
    SearchResponse,
    CircuitBreaker,
    CircuitState,
)


class TestSearchRequest:
    """Testes para SearchRequest."""
    
    def test_request_normaliza_query(self):
        """Testa que query é normalizada."""
        request = SearchRequest(query="  arroz 5kg  ")
        assert request.query == "arroz 5kg"
    
    def test_request_normaliza_cep(self):
        """Testa que CEP é normalizado."""
        request = SearchRequest(
            query="arroz",
            cep="01310-100",
        )
        assert request.cep == "01310100"
    
    def test_request_gera_id_unico(self):
        """Testa que request_id é gerado automaticamente."""
        request = SearchRequest(query="arroz")
        assert request.request_id is not None
        assert len(request.request_id) == 8
    
    def test_request_ids_diferentes(self):
        """Testa que requests diferentes têm IDs diferentes."""
        request1 = SearchRequest(query="arroz")
        request2 = SearchRequest(query="arroz")
        assert request1.request_id != request2.request_id
    
    def test_request_defaults(self):
        """Testa valores padrão do request."""
        request = SearchRequest(query="arroz")
        
        assert request.timeout_seconds == 10.0
        assert request.market_timeout_seconds == 8.0
        assert request.min_results == 5
        assert request.enable_early_return is True
        assert request.max_pages == 1


class TestSearchResponse:
    """Testes para SearchResponse."""
    
    def test_response_to_dict(self):
        """Testa conversão para dicionário."""
        response = SearchResponse(
            request_id="test-123",
            query="arroz",
            status="success",
            total_results=5,
            results=[{"title": "Arroz 5kg"}],
            markets_searched=["carrefour"],
            cache_hit=False,
            duration_ms=500,
        )
        
        result = response.to_dict()
        
        assert result["request_id"] == "test-123"
        assert result["query"] == "arroz"
        assert result["status"] == "success"
        assert result["total_results"] == 5
        assert "metadata" in result
    
    def test_response_metadata(self):
        """Testa que metadata está presente."""
        response = SearchResponse(
            request_id="test-123",
            query="arroz",
            status="success",
            markets_searched=["carrefour", "atacadao"],
            markets_failed=["extra"],
            cache_hit=True,
            duration_ms=100,
        )
        
        result = response.to_dict()
        metadata = result["metadata"]
        
        assert metadata["markets_searched"] == ["carrefour", "atacadao"]
        assert metadata["markets_failed"] == ["extra"]
        assert metadata["cache_hit"] is True
        assert metadata["duration_ms"] == 100


class TestCircuitBreaker:
    """Testes para CircuitBreaker."""
    
    def test_circuit_breaker_inicial_closed(self):
        """Testa que circuit breaker inicia fechado."""
        cb = CircuitBreaker(market_id="carrefour")
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
        assert cb.success_count == 0
    
    def test_record_success(self):
        """Testa registro de sucesso."""
        cb = CircuitBreaker(market_id="carrefour")
        cb.record_success()
        
        assert cb.success_count == 1
        assert cb.last_success_time is not None
    
    def test_record_failure(self):
        """Testa registro de falha."""
        cb = CircuitBreaker(market_id="carrefour")
        cb.record_failure()
        
        assert cb.failure_count == 1
        assert cb.last_failure_time is not None
    
    def test_circuit_opens_after_threshold(self):
        """Testa que circuito abre após atingir threshold de falhas."""
        cb = CircuitBreaker(
            market_id="carrefour",
            failure_threshold=3,
        )
        
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        
        cb.record_failure()  # Atinge threshold
        assert cb.state == CircuitState.OPEN
    
    def test_circuit_denies_when_open(self):
        """Testa que circuito aberto nega execução."""
        cb = CircuitBreaker(
            market_id="carrefour",
            failure_threshold=1,
        )
        
        cb.record_failure()  # Abre o circuito
        assert cb.state == CircuitState.OPEN
        assert cb.can_execute() is False
    
    def test_circuit_half_open_after_recovery_timeout(self):
        """Testa transição para half-open após timeout."""
        cb = CircuitBreaker(
            market_id="carrefour",
            failure_threshold=1,
            recovery_timeout_seconds=0,  # Imediato para teste
        )
        
        cb.record_failure()  # Abre o circuito
        
        # Após o timeout, deve permitir tentativa
        assert cb.can_execute() is True  # Muda para HALF_OPEN
        assert cb.state == CircuitState.HALF_OPEN
    
    def test_circuit_closes_after_success_in_half_open(self):
        """Testa que circuito fecha após sucesso em half-open."""
        cb = CircuitBreaker(
            market_id="carrefour",
            failure_threshold=1,
            recovery_timeout_seconds=0,
        )
        
        cb.record_failure()  # Abre
        cb.can_execute()  # Vai para HALF_OPEN
        cb.record_success()  # Sucesso em HALF_OPEN
        
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
    
    def test_to_dict(self):
        """Testa conversão para dicionário."""
        cb = CircuitBreaker(market_id="carrefour")
        cb.record_success()
        
        result = cb.to_dict()
        
        assert result["market_id"] == "carrefour"
        assert result["state"] == "closed"
        assert result["success_count"] == 1
        assert result["last_success"] is not None


class TestSearchServiceBasic:
    """Testes básicos para SearchService."""
    
    def test_get_circuit_breakers_status(self):
        """Testa obtenção de status dos circuit breakers."""
        with patch('src.services.search_service.get_settings') as mock_settings:
            mock_settings.return_value.mercados_enabled = ["carrefour", "atacadao"]
            mock_settings.return_value.circuit_breaker_failure_threshold = 3
            mock_settings.return_value.circuit_breaker_recovery_timeout_seconds = 60
            mock_settings.return_value.circuit_breaker_half_open_max_calls = 1
            
            service = SearchService()
            status = service.get_circuit_breakers_status()
            
            assert "carrefour" in status
            assert "atacadao" in status
            assert status["carrefour"]["state"] == "closed"
    
    def test_reset_circuit_breaker(self):
        """Testa reset de circuit breaker."""
        with patch('src.services.search_service.get_settings') as mock_settings:
            mock_settings.return_value.mercados_enabled = ["carrefour"]
            mock_settings.return_value.circuit_breaker_failure_threshold = 3
            mock_settings.return_value.circuit_breaker_recovery_timeout_seconds = 60
            mock_settings.return_value.circuit_breaker_half_open_max_calls = 1
            
            service = SearchService()
            
            # Simula falhas para abrir circuito
            service._circuit_breakers["carrefour"].record_failure()
            service._circuit_breakers["carrefour"].record_failure()
            service._circuit_breakers["carrefour"].record_failure()
            
            assert service._circuit_breakers["carrefour"].state == CircuitState.OPEN
            
            # Reseta
            result = service.reset_circuit_breaker("carrefour")
            
            assert result is True
            assert service._circuit_breakers["carrefour"].state == CircuitState.CLOSED
    
    def test_reset_circuit_breaker_not_found(self):
        """Testa reset de circuit breaker inexistente."""
        with patch('src.services.search_service.get_settings') as mock_settings:
            mock_settings.return_value.mercados_enabled = ["carrefour"]
            mock_settings.return_value.circuit_breaker_failure_threshold = 3
            mock_settings.return_value.circuit_breaker_recovery_timeout_seconds = 60
            mock_settings.return_value.circuit_breaker_half_open_max_calls = 1
            
            service = SearchService()
            result = service.reset_circuit_breaker("mercado_inexistente")
            
            assert result is False


class TestSearchServicePrioritization:
    """Testes para priorização de mercados."""
    
    def test_prioritizes_markets_by_latency(self):
        """Testa que mercados são priorizados por latência."""
        with patch('src.services.search_service.get_settings') as mock_settings:
            mock_settings.return_value.mercados_enabled = ["carrefour", "atacadao", "extra"]
            mock_settings.return_value.circuit_breaker_failure_threshold = 3
            mock_settings.return_value.circuit_breaker_recovery_timeout_seconds = 60
            mock_settings.return_value.circuit_breaker_half_open_max_calls = 1
            
            service = SearchService()
            
            # Simula latências conhecidas
            service._market_latencies = {
                "extra": 2.0,
                "carrefour": 1.0,
                "atacadao": 0.5,
            }
            
            prioritized = service._get_prioritized_markets(None)
            
            # Atacadão (mais rápido) deve vir primeiro
            assert prioritized[0] == "atacadao"
    
    def test_filters_open_circuit_breakers(self):
        """Testa que mercados com circuito aberto são filtrados."""
        with patch('src.services.search_service.get_settings') as mock_settings:
            mock_settings.return_value.mercados_enabled = ["carrefour", "atacadao"]
            mock_settings.return_value.circuit_breaker_failure_threshold = 1
            mock_settings.return_value.circuit_breaker_recovery_timeout_seconds = 300
            mock_settings.return_value.circuit_breaker_half_open_max_calls = 1
            
            service = SearchService()
            
            # Abre circuito do carrefour
            service._circuit_breakers["carrefour"].record_failure()
            
            prioritized = service._get_prioritized_markets(None)
            
            assert "carrefour" not in prioritized
            assert "atacadao" in prioritized


class TestSearchServiceCacheIntegration:
    """Testes de integração do SearchService com cache."""
    
    @pytest.mark.asyncio
    async def test_returns_cached_result(self):
        """Testa que resultado cacheado é retornado."""
        with patch('src.services.search_service.get_settings') as mock_settings:
            mock_settings.return_value.mercados_enabled = ["carrefour"]
            mock_settings.return_value.circuit_breaker_failure_threshold = 3
            mock_settings.return_value.circuit_breaker_recovery_timeout_seconds = 60
            mock_settings.return_value.circuit_breaker_half_open_max_calls = 1
            
            service = SearchService()
            
            # Mock do cache
            mock_cache = AsyncMock()
            mock_cache.get_search_result.return_value = {
                "total_results": 5,
                "results": [{"title": "Arroz 5kg"}],
                "best_offer": {"title": "Arroz 5kg"},
                "markets_searched": ["carrefour"],
            }
            service._cache = mock_cache
            
            # Mock do rate limiter
            mock_rate_limiter = AsyncMock()
            mock_rate_limiter.check_user.return_value = MagicMock(allowed=True)
            service._rate_limiter = mock_rate_limiter
            
            request = SearchRequest(query="arroz", user_id="user_123")
            response = await service.search(request)
            
            assert response.cache_hit is True
            assert response.status == "cached"


class TestSearchServiceErrorHandling:
    """Testes de tratamento de erros no SearchService."""
    
    @pytest.mark.asyncio
    async def test_handles_rate_limit_exceeded(self):
        """Testa tratamento de rate limit excedido."""
        with patch('src.services.search_service.get_settings') as mock_settings:
            mock_settings.return_value.mercados_enabled = ["carrefour"]
            mock_settings.return_value.circuit_breaker_failure_threshold = 3
            mock_settings.return_value.circuit_breaker_recovery_timeout_seconds = 60
            mock_settings.return_value.circuit_breaker_half_open_max_calls = 1
            
            service = SearchService()
            
            # Mock do cache
            mock_cache = AsyncMock()
            mock_cache.get_search_result.return_value = None
            service._cache = mock_cache
            
            # Mock do rate limiter - excedido
            mock_rate_limiter = AsyncMock()
            mock_rate_limiter.check_user.return_value = MagicMock(
                allowed=False,
                reset_in_seconds=30,
            )
            service._rate_limiter = mock_rate_limiter
            
            request = SearchRequest(query="arroz", user_id="user_123")
            response = await service.search(request)
            
            assert response.status == "error"
            assert len(response.errors) > 0
    
    @pytest.mark.asyncio
    async def test_handles_no_markets_available(self):
        """Testa tratamento quando não há mercados disponíveis."""
        with patch('src.services.search_service.get_settings') as mock_settings:
            mock_settings.return_value.mercados_enabled = []
            mock_settings.return_value.circuit_breaker_failure_threshold = 3
            mock_settings.return_value.circuit_breaker_recovery_timeout_seconds = 60
            mock_settings.return_value.circuit_breaker_half_open_max_calls = 1
            
            service = SearchService()
            
            # Mock do cache
            mock_cache = AsyncMock()
            mock_cache.get_search_result.return_value = None
            service._cache = mock_cache
            
            # Mock do rate limiter
            mock_rate_limiter = AsyncMock()
            mock_rate_limiter.check_user.return_value = MagicMock(allowed=True)
            service._rate_limiter = mock_rate_limiter
            
            request = SearchRequest(query="arroz", user_id="user_123")
            response = await service.search(request)
            
            assert response.status == "error"
            assert "Nenhum mercado" in response.errors[0]
