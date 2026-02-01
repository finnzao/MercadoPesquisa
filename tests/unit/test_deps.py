"""
Testes unitários para as dependências da API (deps.py).
Testa validadores, rate limiting e identificação de usuário.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException

from src.api.deps import (
    validate_query,
    validate_cep,
    validate_markets,
)


class TestValidateQuery:
    """Testes para validador de query de busca."""
    
    def test_query_valida(self):
        """Testa query válida."""
        result = validate_query("arroz 5kg")
        assert result == "arroz 5kg"
    
    def test_query_com_espacos(self):
        """Testa que espaços são removidos das extremidades."""
        result = validate_query("  arroz 5kg  ")
        assert result == "arroz 5kg"
    
    def test_query_vazia_raises(self):
        """Testa que query vazia levanta exceção."""
        with pytest.raises(HTTPException) as exc_info:
            validate_query("")
        assert exc_info.value.status_code == 400
    
    def test_query_apenas_espacos_raises(self):
        """Testa que query com apenas espaços levanta exceção."""
        with pytest.raises(HTTPException) as exc_info:
            validate_query("   ")
        assert exc_info.value.status_code == 400
    
    def test_query_muito_curta_raises(self):
        """Testa que query com menos de 2 caracteres levanta exceção."""
        with pytest.raises(HTTPException) as exc_info:
            validate_query("a")
        assert exc_info.value.status_code == 400
        assert "2 caracteres" in exc_info.value.detail
    
    def test_query_muito_longa_raises(self):
        """Testa que query com mais de 100 caracteres levanta exceção."""
        long_query = "a" * 101
        with pytest.raises(HTTPException) as exc_info:
            validate_query(long_query)
        assert exc_info.value.status_code == 400
        assert "100 caracteres" in exc_info.value.detail
    
    def test_query_limite_minimo(self):
        """Testa query no limite mínimo (2 caracteres)."""
        result = validate_query("ar")
        assert result == "ar"
    
    def test_query_limite_maximo(self):
        """Testa query no limite máximo (100 caracteres)."""
        query = "a" * 100
        result = validate_query(query)
        assert result == query


class TestValidateCep:
    """Testes para validador de CEP."""
    
    def test_cep_valido_8_digitos(self):
        """Testa CEP válido com 8 dígitos."""
        result = validate_cep("01310100")
        assert result == "01310100"
    
    def test_cep_com_hifen(self):
        """Testa CEP com hífen."""
        result = validate_cep("01310-100")
        assert result == "01310100"
    
    def test_cep_com_ponto(self):
        """Testa CEP com ponto."""
        result = validate_cep("01.310.100")
        assert result == "01310100"
    
    def test_cep_none_retorna_none(self):
        """Testa que None retorna None."""
        result = validate_cep(None)
        assert result is None
    
    def test_cep_vazio_retorna_none(self):
        """Testa que string vazia retorna None."""
        result = validate_cep("")
        assert result is None
    
    def test_cep_invalido_raises(self):
        """Testa que CEP com tamanho errado levanta exceção."""
        with pytest.raises(HTTPException) as exc_info:
            validate_cep("1234")
        assert exc_info.value.status_code == 400
        assert "CEP inválido" in exc_info.value.detail
    
    def test_cep_muito_longo_raises(self):
        """Testa que CEP muito longo levanta exceção."""
        with pytest.raises(HTTPException) as exc_info:
            validate_cep("123456789")
        assert exc_info.value.status_code == 400
    
    def test_cep_com_letras_invalido(self):
        """Testa que CEP com letras é inválido."""
        with pytest.raises(HTTPException) as exc_info:
            validate_cep("0131010A")
        assert exc_info.value.status_code == 400


class TestValidateMarkets:
    """Testes para validador de mercados."""
    
    @pytest.fixture
    def mock_settings(self):
        """Mock das configurações."""
        mock = MagicMock()
        mock.mercados_enabled = ["carrefour", "atacadao", "pao_acucar"]
        mock.is_market_enabled = lambda m: m in mock.mercados_enabled
        return mock
    
    def test_markets_none_retorna_none(self, mock_settings):
        """Testa que None retorna None."""
        result = validate_markets(None, mock_settings)
        assert result is None
    
    def test_markets_vazio_retorna_none(self, mock_settings):
        """Testa que lista vazia retorna None."""
        result = validate_markets([], mock_settings)
        assert result is None
    
    def test_markets_validos(self, mock_settings):
        """Testa mercados válidos."""
        result = validate_markets(["carrefour", "atacadao"], mock_settings)
        assert result == ["carrefour", "atacadao"]
    
    def test_market_invalido_raises(self, mock_settings):
        """Testa que mercado inválido levanta exceção."""
        with pytest.raises(HTTPException) as exc_info:
            validate_markets(["mercado_invalido"], mock_settings)
        assert exc_info.value.status_code == 400
        assert "invalid_markets" in str(exc_info.value.detail)
    
    def test_mix_validos_invalidos_raises(self, mock_settings):
        """Testa mix de mercados válidos e inválidos."""
        with pytest.raises(HTTPException) as exc_info:
            validate_markets(["carrefour", "invalido"], mock_settings)
        assert exc_info.value.status_code == 400
    
    def test_retorna_mercados_validos(self, mock_settings):
        """Testa que apenas mercados válidos são retornados."""
        result = validate_markets(["carrefour"], mock_settings)
        assert "carrefour" in result


class TestUserIdentification:
    """Testes para identificação de usuário via headers."""
    
    @pytest.mark.asyncio
    async def test_user_id_from_x_user_id(self):
        """Testa extração de user_id do header X-User-ID."""
        from src.api.deps import get_user_id
        
        result = await get_user_id(
            x_user_id="user_123",
            x_telegram_user=None,
        )
        assert result == "user_123"
    
    @pytest.mark.asyncio
    async def test_user_id_from_telegram(self):
        """Testa extração de user_id do header X-Telegram-User."""
        from src.api.deps import get_user_id
        
        result = await get_user_id(
            x_user_id=None,
            x_telegram_user="telegram_456",
        )
        assert result == "telegram_456"
    
    @pytest.mark.asyncio
    async def test_user_id_priority(self):
        """Testa que X-User-ID tem prioridade sobre X-Telegram-User."""
        from src.api.deps import get_user_id
        
        result = await get_user_id(
            x_user_id="user_123",
            x_telegram_user="telegram_456",
        )
        assert result == "user_123"
    
    @pytest.mark.asyncio
    async def test_user_id_none_when_no_headers(self):
        """Testa que retorna None quando nenhum header está presente."""
        from src.api.deps import get_user_id
        
        result = await get_user_id(
            x_user_id=None,
            x_telegram_user=None,
        )
        assert result is None


class TestCheckRateLimit:
    """Testes para verificação de rate limit."""
    
    @pytest.fixture
    def mock_rate_limiter(self):
        """Mock do rate limiter."""
        mock = AsyncMock()
        mock.is_allowed.return_value = (True, 59, 60)
        return mock
    
    @pytest.fixture
    def mock_settings_rate_limit_enabled(self):
        """Mock de settings com rate limit habilitado."""
        mock = MagicMock()
        mock.rate_limit_enabled = True
        mock.rate_limit_requests_per_minute = 60
        return mock
    
    @pytest.fixture
    def mock_settings_rate_limit_disabled(self):
        """Mock de settings com rate limit desabilitado."""
        mock = MagicMock()
        mock.rate_limit_enabled = False
        return mock
    
    @pytest.mark.asyncio
    async def test_rate_limit_disabled_allows_all(self, mock_rate_limiter, mock_settings_rate_limit_disabled):
        """Testa que rate limit desabilitado permite tudo."""
        from src.api.deps import check_rate_limit
        
        request = MagicMock()
        request.client = MagicMock()
        request.client.host = "127.0.0.1"
        request.state = MagicMock()
        
        # Não deve levantar exceção
        await check_rate_limit(
            request=request,
            rate_limiter=mock_rate_limiter,
            settings=mock_settings_rate_limit_disabled,
            x_user_id="user_123",
            x_telegram_user=None,
        )
    
    @pytest.mark.asyncio
    async def test_rate_limit_allowed(self, mock_rate_limiter, mock_settings_rate_limit_enabled):
        """Testa que requisição dentro do limite é permitida."""
        from src.api.deps import check_rate_limit
        
        request = MagicMock()
        request.client = MagicMock()
        request.client.host = "127.0.0.1"
        request.state = MagicMock()
        
        mock_rate_limiter.is_allowed.return_value = (True, 59, 60)
        
        # Não deve levantar exceção
        await check_rate_limit(
            request=request,
            rate_limiter=mock_rate_limiter,
            settings=mock_settings_rate_limit_enabled,
            x_user_id="user_123",
            x_telegram_user=None,
        )
    
    @pytest.mark.asyncio
    async def test_rate_limit_exceeded_raises_429(self, mock_rate_limiter, mock_settings_rate_limit_enabled):
        """Testa que limite excedido levanta HTTPException 429."""
        from src.api.deps import check_rate_limit
        
        request = MagicMock()
        request.client = MagicMock()
        request.client.host = "127.0.0.1"
        request.state = MagicMock()
        
        mock_rate_limiter.is_allowed.return_value = (False, 0, 30)
        
        with pytest.raises(HTTPException) as exc_info:
            await check_rate_limit(
                request=request,
                rate_limiter=mock_rate_limiter,
                settings=mock_settings_rate_limit_enabled,
                x_user_id="user_123",
                x_telegram_user=None,
            )
        
        assert exc_info.value.status_code == 429
        assert "rate_limit_exceeded" in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    async def test_rate_limit_uses_ip_fallback(self, mock_rate_limiter, mock_settings_rate_limit_enabled):
        """Testa que usa IP como fallback quando não há user_id."""
        from src.api.deps import check_rate_limit
        
        request = MagicMock()
        request.client = MagicMock()
        request.client.host = "192.168.1.1"
        request.state = MagicMock()
        
        mock_rate_limiter.is_allowed.return_value = (True, 119, 60)
        
        await check_rate_limit(
            request=request,
            rate_limiter=mock_rate_limiter,
            settings=mock_settings_rate_limit_enabled,
            x_user_id=None,
            x_telegram_user=None,
        )
        
        # Verifica que foi chamado com identificador baseado em IP
        call_args = mock_rate_limiter.is_allowed.call_args
        assert "ip:" in call_args[0][0]
    
    @pytest.mark.asyncio
    async def test_rate_limit_headers_added(self, mock_rate_limiter, mock_settings_rate_limit_enabled):
        """Testa que headers de rate limit são adicionados ao request.state."""
        from src.api.deps import check_rate_limit
        
        request = MagicMock()
        request.client = MagicMock()
        request.client.host = "127.0.0.1"
        request.state = MagicMock()
        
        mock_rate_limiter.is_allowed.return_value = (True, 59, 60)
        
        await check_rate_limit(
            request=request,
            rate_limiter=mock_rate_limiter,
            settings=mock_settings_rate_limit_enabled,
            x_user_id="user_123",
            x_telegram_user=None,
        )
        
        # Verifica que headers foram definidos
        assert hasattr(request.state, 'rate_limit_headers')


class TestInputSanitization:
    """Testes para sanitização de inputs."""
    
    def test_query_com_caracteres_especiais(self):
        """Testa query com caracteres especiais."""
        # Caracteres especiais devem ser aceitos
        result = validate_query("arroz (tipo 1)")
        assert "arroz" in result
    
    def test_query_com_unicode(self):
        """Testa query com caracteres unicode."""
        result = validate_query("café açúcar")
        assert "café" in result
        assert "açúcar" in result
    
    def test_cep_com_espacos(self):
        """Testa CEP com espaços."""
        result = validate_cep(" 01310 100 ")
        assert result == "01310100"
    
    def test_query_normaliza_espacos_multiplos(self):
        """Testa que múltiplos espaços são preservados internamente."""
        result = validate_query("arroz   5kg")
        # A validação apenas remove espaços das extremidades
        assert result == "arroz   5kg"
