# Testes do Price Tracker API

Este diretório contém os testes automatizados para a API do Price Tracker, com foco especial em cenários de uso via bot WhatsApp com múltiplos usuários simultâneos.

## Estrutura

```
tests/
├── conftest.py           # Fixtures compartilhadas
├── __init__.py
├── unit/                 # Testes unitários
│   ├── test_deps.py      # Testes de dependências (validadores)
│   ├── test_search_service.py    # Testes do SearchService
│   ├── test_cache_service.py     # Testes do CacheService
│   └── test_multi_search.py      # Testes de busca múltipla
├── api/                  # Testes de endpoints
│   ├── test_routes_basic.py      # Testes básicos de rotas
│   └── test_concurrent_requests.py  # Testes de concorrência
├── integration/          # Testes de integração
│   └── test_api_endpoints.py     # Testes de fluxo completo
└── load/                 # Testes de carga
    └── test_load_scenarios.py    # Cenários de carga
```

## Instalação

```bash
pip install -r requirements-test.txt
```

## Execução

### Usando o script auxiliar

```bash
# Testes rápidos (recomendado para desenvolvimento)
./run_tests.sh quick

# Todos os testes
./run_tests.sh all

# Apenas testes unitários
./run_tests.sh unit

# Apenas testes de API
./run_tests.sh api

# Testes com cobertura
./run_tests.sh coverage
```

### Usando pytest diretamente

```bash
# Todos os testes
pytest tests/ -v

# Testes específicos
pytest tests/unit/ -v
pytest tests/api/ -v
pytest tests/integration/ -v

# Teste específico por nome
pytest tests/ -k "test_search" -v

# Para no primeiro erro
pytest tests/ -x -v

# Com cobertura
pytest tests/ --cov=src --cov-report=html
```

## Tipos de Teste

### Testes Unitários (`tests/unit/`)

Testam componentes isolados sem dependências externas:

- **test_deps.py**: Validadores de entrada (query, CEP, mercados)
- **test_search_service.py**: Lógica de busca, circuit breakers
- **test_cache_service.py**: Cache L1/L2, TTL dinâmico
- **test_multi_search.py**: Cálculos de totais por mercado

### Testes de API (`tests/api/`)

Testam endpoints HTTP:

- **test_routes_basic.py**: Validação de rotas, parâmetros, respostas
- **test_concurrent_requests.py**: Múltiplos usuários simultâneos

### Testes de Integração (`tests/integration/`)

Testam fluxos completos entre componentes:

- **test_api_endpoints.py**: Busca, lista de compras, mercados

### Testes de Carga (`tests/load/`)

Testam performance e estabilidade:

- **test_load_scenarios.py**: Simulação de múltiplos usuários de bot

## Fixtures Principais

As fixtures estão definidas em `conftest.py`:

| Fixture | Descrição |
|---------|-----------|
| `client` | TestClient síncrono do FastAPI |
| `async_client` | AsyncClient para testes assíncronos |
| `whatsapp_user` | Simula usuário do WhatsApp |
| `multiple_users` | Lista de 10 usuários simulados |
| `mock_search_service` | Mock do serviço de busca |
| `mock_cache_service` | Mock do serviço de cache |
| `raw_product_arroz` | Dados de produto para teste |
| `search_request_data` | Payload de requisição de busca |

## Cenários de Bot WhatsApp

Os testes cobrem cenários específicos de uso via bot:

### 1. Múltiplos Usuários Simultâneos
```python
@pytest.mark.asyncio
async def test_10_users_searching_simultaneously(async_client, multiple_users):
    """10 usuários fazendo buscas ao mesmo tempo."""
```

### 2. Rate Limiting por Usuário
```python
async def test_rate_limit_per_user(async_client):
    """Cada usuário tem seu próprio limite de requisições."""
```

### 3. Cache Isolado por CEP
```python
async def test_cache_isolated_by_cep(async_client):
    """Resultados são cacheados separadamente por CEP."""
```

### 4. Fluxo Típico de Conversa
```python
async def test_typical_bot_conversation_flow(async_client, whatsapp_user):
    """Simula: busca → comparação → lista de compras."""
```

## Configuração

### pytest.ini

```ini
[pytest]
testpaths = tests
asyncio_mode = auto
timeout = 30
```

### Variáveis de Ambiente para Testes

```bash
TESTING=true
CACHE_ENABLED=false
RATE_LIMIT_ENABLED=false
```

## Marcadores

```bash
# Rodar apenas testes marcados como 'unit'
pytest -m unit

# Rodar apenas testes assíncronos
pytest -m asyncio

# Excluir testes lentos
pytest -m "not slow"
```

## Cobertura de Código

```bash
# Gerar relatório de cobertura
pytest tests/ --cov=src --cov-report=html --cov-report=term-missing

# Verificar cobertura mínima (60%)
pytest tests/ --cov=src --cov-fail-under=60
```

O relatório HTML é gerado em `htmlcov/index.html`.

## CI/CD

Exemplo de configuração para GitHub Actions:

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt -r requirements-test.txt
      - run: pytest tests/ --ignore=tests/load/ -v --cov=src
```

## Troubleshooting

### Testes assíncronos falhando
```bash
# Certifique-se de ter pytest-asyncio instalado
pip install pytest-asyncio
```

### Timeout em testes de carga
```bash
# Aumente o timeout
pytest tests/load/ --timeout=120
```

### Importação de módulos falhando
```bash
# Execute do diretório raiz do projeto
cd /path/to/price-tracker
pytest tests/ -v
```
