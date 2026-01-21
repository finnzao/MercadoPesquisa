# Price Tracker API - Documentacao Completa

## Visao Geral

O Price Tracker e um sistema de coleta e comparacao de precos de supermercados online. A aplicacao permite buscar produtos em multiplos mercados simultaneamente, normalizar precos por unidade (R$/kg, R$/L) e identificar as melhores ofertas.

## Arquitetura do Sistema

### Componentes Principais

1. **API FastAPI**: Camada de exposicao REST que recebe requisicoes HTTP
2. **Search Service**: Orquestrador principal que coordena cache, rate limiting, circuit breakers e fan-out paralelo
3. **Scraper Manager**: Gerencia os scrapers de cada mercado
4. **Processing Pipeline**: Processa produtos brutos, normaliza quantidades e calcula precos por unidade
5. **Ranking System**: Sistema de ranking fuzzy que combina relevancia e preco
6. **Cache Service**: Cache Redis para resultados de busca
7. **Storage Manager**: Persistencia em SQLite, CSV e Parquet

### Fluxo de Busca

1. Requisicao chega na API
2. Verificacao de rate limit do usuario
3. Consulta ao cache Redis
4. Se cache miss, verifica circuit breakers dos mercados
5. Executa fan-out paralelo para mercados disponiveis
6. Processa produtos pelo pipeline (parsing, normalizacao, calculo de preco)
7. Aplica ranking fuzzy
8. Cacheia resultado
9. Retorna resposta

## Configuracao Base

- **URL Base**: `http://localhost:8000`
- **Prefixo da API**: `/api/v1`
- **Documentacao Swagger**: `/docs` (apenas em modo debug)

## Mercados Suportados

| ID | Nome | Status |
|---|---|---|
| carrefour | Carrefour | Ativo |
| atacadao | Atacadao | Ativo |
| pao_acucar | Pao de Acucar | Ativo |
| gbarbosa | GBarbosa | Ativo |
| samsclub | Sam's Club | Ativo |
| redemix | Rede Mix | Ativo |
| mercantil | Mercantil Atacado | Ativo |
| hiperideal | Hiperideal | Ativo |

---

## Endpoints de Saude

### GET /health

Verifica a saude da API e seus componentes.

**Resposta:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "environment": "development",
  "components": {
    "api": "ok",
    "redis": "connected",
    "mercados_enabled": 8
  }
}
```

### GET /

Retorna informacoes basicas da API.

**Resposta:**
```json
{
  "name": "Price Tracker API",
  "version": "1.0.0",
  "docs": "/docs",
  "health": "/health",
  "api": "/api/v1"
}
```

---

## Endpoints de Busca

### GET /api/v1/search

Busca simples de produtos em multiplos supermercados.

**Parametros de Query:**

| Parametro | Tipo | Obrigatorio | Descricao |
|---|---|---|---|
| q | string | Sim | Termo de busca (2-100 caracteres) |
| cep | string | Nao | CEP para localizacao (8 digitos) |
| markets | string | Nao | Mercados separados por virgula |
| limit | integer | Nao | Limite de resultados (1-100, padrao: 20) |

**Exemplo de Requisicao:**
```
GET /api/v1/search?q=arroz%205kg&cep=01310100&limit=10
```

**Resposta:**
```json
{
  "request_id": "abc12345",
  "query": "arroz 5kg",
  "status": "success",
  "total_results": 45,
  "results": [
    {
      "rank": 1,
      "title": "Arroz Tipo 1 Tio Joao 5kg",
      "price": 24.99,
      "price_formatted": "R$ 24,99",
      "normalized_price": 4.998,
      "normalized_price_formatted": "R$ 5,00/kg",
      "market_id": "carrefour",
      "market_name": "Carrefour",
      "url": "https://...",
      "image_url": "https://...",
      "is_relevant": true,
      "is_comparable": true,
      "relevance_score": 0.95,
      "price_score": 0.87,
      "final_score": 0.89
    }
  ],
  "best_offer": { ... },
  "metadata": {
    "markets_searched": ["carrefour", "atacadao"],
    "markets_failed": [],
    "cache_hit": false,
    "duration_ms": 2450
  },
  "errors": null
}
```

### POST /api/v1/search

Busca avancada com mais opcoes de configuracao.

**Corpo da Requisicao:**
```json
{
  "query": "arroz 5kg",
  "cep": "01310100",
  "markets": ["carrefour", "atacadao"],
  "max_pages": 2,
  "include_unavailable": false
}
```

**Campos:**

| Campo | Tipo | Obrigatorio | Descricao |
|---|---|---|---|
| query | string | Sim | Termo de busca |
| cep | string | Nao | CEP para localizacao |
| markets | array | Nao | Lista de mercados especificos |
| max_pages | integer | Nao | Maximo de paginas por mercado (1-5) |
| include_unavailable | boolean | Nao | Incluir produtos indisponiveis |

### GET /api/v1/search/compare

Compara precos de um produto entre mercados.

**Parametros de Query:**

| Parametro | Tipo | Obrigatorio | Descricao |
|---|---|---|---|
| q | string | Sim | Termo de busca |
| cep | string | Nao | CEP para localizacao |

**Exemplo:**
```
GET /api/v1/search/compare?q=leite%20integral%201L
```

**Resposta:**
```json
{
  "query": "leite integral 1L",
  "total_offers": 32,
  "comparable_offers": 28,
  "best_offer": {
    "market_name": "Atacadao",
    "title": "Leite Integral Piracanjuba 1L",
    "price": 4.99,
    "normalized_price": 4.99,
    "url": "https://..."
  },
  "by_market": {
    "carrefour": {
      "market_name": "Carrefour",
      "offers_count": 12,
      "min_price": 5.29,
      "min_normalized_price": 5.29
    },
    "atacadao": {
      "market_name": "Atacadao",
      "offers_count": 8,
      "min_price": 4.99,
      "min_normalized_price": 4.99
    }
  },
  "potential_savings": [
    {
      "best_market": "Atacadao",
      "compared_market": "Carrefour",
      "savings_absolute": 0.30,
      "savings_percentage": 5.7
    }
  ]
}
```

### GET /api/v1/search/quick

Busca rapida que retorna apenas o melhor preco. Ideal para bots.

**Parametros de Query:**

| Parametro | Tipo | Obrigatorio | Descricao |
|---|---|---|---|
| q | string | Sim | Termo de busca |
| cep | string | Nao | CEP para localizacao |

**Exemplo:**
```
GET /api/v1/search/quick?q=banana%20prata
```

**Resposta:**
```json
{
  "found": true,
  "query": "banana prata",
  "product": "Banana Prata kg",
  "price": "R$ 5,99",
  "normalized_price": "R$ 5,99/kg",
  "market": "Carrefour",
  "url": "https://...",
  "total_results": 15,
  "cache_hit": false
}
```

---

## Endpoints de Busca Multipla

### POST /api/v1/search/multi

Busca multiplos itens de uma vez, com opcao de otimizacao por mercado unico.

**Corpo da Requisicao:**
```json
{
  "items": ["arroz 5kg", "feijao 1kg", "oleo 900ml"],
  "cep": "01310100",
  "markets": ["carrefour", "atacadao"],
  "single_market": false
}
```

**Campos:**

| Campo | Tipo | Obrigatorio | Descricao |
|---|---|---|---|
| items | array | Sim | Lista de itens (1-20 itens) |
| cep | string | Nao | CEP para localizacao |
| markets | array | Nao | Mercados especificos |
| single_market | boolean | Nao | Se true, encontra melhor mercado unico |

**Modos de Operacao:**

**single_market=false (padrao):** Retorna o melhor preco de cada item, mesmo que sejam de mercados diferentes.

**single_market=true:** Encontra qual mercado unico tem o menor valor total da lista.

**Resposta (single_market=false):**
```json
{
  "request_id": "abc12345",
  "mode": "best_per_item",
  "items_results": [
    {
      "query": "arroz 5kg",
      "status": "found",
      "best_offer": {
        "title": "Arroz Tipo 1 5kg",
        "price": 24.99,
        "price_formatted": "R$ 24,99",
        "market_id": "atacadao",
        "market_name": "Atacadao",
        "url": "https://..."
      },
      "alternatives": [...],
      "offers_count": 12
    }
  ],
  "summary": {
    "total_items": 3,
    "items_found": 3,
    "items_not_found": 0,
    "estimated_total": 45.97,
    "estimated_total_formatted": "R$ 45,97",
    "markets_involved": ["atacadao", "carrefour"],
    "markets_count": 2
  },
  "metadata": {
    "cep": "01310100",
    "single_market": false,
    "duration_ms": 3200
  }
}
```

**Resposta (single_market=true):**
```json
{
  "request_id": "abc12345",
  "mode": "single_market",
  "items_results": [...],
  "summary": {
    "total_items": 3,
    "items_found": 3,
    "best_per_item_total": 45.97,
    "single_market_total": 47.50,
    "winner_market": "Atacadao",
    "markets_analyzed": 5
  },
  "winner": {
    "market_id": "atacadao",
    "market_name": "Atacadao",
    "total": 47.50,
    "total_formatted": "R$ 47,50",
    "items_found": 3,
    "items_missing": [],
    "coverage_percent": 100.0
  },
  "comparison": [
    {
      "market_id": "atacadao",
      "market_name": "Atacadao",
      "total": 47.50,
      "items_found": 3,
      "coverage_percent": 100.0
    },
    {
      "market_id": "carrefour",
      "market_name": "Carrefour",
      "total": 49.80,
      "items_found": 3,
      "coverage_percent": 100.0
    }
  ],
  "savings": {
    "vs_worst": 4.30,
    "vs_worst_formatted": "R$ 4,30",
    "vs_worst_market": "Pao de Acucar",
    "note": "Comprar tudo no Atacadao e mais barato que item a item!"
  }
}
```

### POST /api/v1/search/multi/quick

Versao simplificada da busca multipla para integracao com bots.

**Corpo da Requisicao:** Mesmo do endpoint `/search/multi`

**Resposta (single_market=false):**
```json
{
  "success": true,
  "mode": "best_per_item",
  "total_items": 3,
  "items_found": 3,
  "total": "R$ 45,97",
  "markets_count": 2,
  "items": [
    {
      "query": "arroz 5kg",
      "found": true,
      "price": "R$ 24,99",
      "market": "Atacadao"
    }
  ]
}
```

---

## Endpoints de Mercados

### GET /api/v1/markets

Lista todos os mercados suportados pelo sistema.

**Resposta:**
```json
[
  {
    "id": "carrefour",
    "name": "Carrefour",
    "status": "active",
    "enabled": true,
    "requires_cep": false,
    "rate_limit": 8
  },
  {
    "id": "atacadao",
    "name": "Atacadao",
    "status": "active",
    "enabled": true,
    "requires_cep": false,
    "rate_limit": 10
  }
]
```

### GET /api/v1/markets/enabled

Retorna apenas os mercados habilitados para busca.

### GET /api/v1/markets/status

Retorna o status dos circuit breakers de cada mercado.

**Resposta:**
```json
{
  "carrefour": {
    "market_id": "carrefour",
    "state": "closed",
    "failure_count": 0,
    "success_count": 45,
    "last_failure": null,
    "last_success": "2024-01-15T10:30:00"
  },
  "atacadao": {
    "market_id": "atacadao",
    "state": "open",
    "failure_count": 3,
    "success_count": 12,
    "last_failure": "2024-01-15T10:25:00",
    "last_success": "2024-01-15T10:20:00"
  }
}
```

**Estados do Circuit Breaker:**

| Estado | Descricao |
|---|---|
| closed | Normal - aceita requisicoes |
| open | Bloqueado - muitas falhas recentes |
| half_open | Testando recuperacao |

### GET /api/v1/markets/{market_id}

Retorna informacoes detalhadas de um mercado especifico.

**Exemplo:**
```
GET /api/v1/markets/carrefour
```

**Resposta:**
```json
{
  "id": "carrefour",
  "name": "Carrefour",
  "base_url": "https://mercado.carrefour.com.br",
  "status": "active",
  "enabled": true,
  "requires_cep": false,
  "supports_pagination": true,
  "max_pages": 5,
  "rate_limit": 8,
  "circuit_breaker": {
    "state": "closed",
    "failure_count": 0,
    "success_count": 45
  }
}
```

### POST /api/v1/markets/{market_id}/reset

Reseta o circuit breaker de um mercado.

**Exemplo:**
```
POST /api/v1/markets/atacadao/reset
```

**Resposta:**
```json
{
  "status": "success",
  "message": "Circuit breaker do mercado atacadao resetado",
  "market_id": "atacadao"
}
```

---

## Endpoints de Lista de Compras

### POST /api/v1/shopping/list

Processa uma lista de compras estruturada.

**Corpo da Requisicao:**
```json
{
  "items": [
    {
      "name": "arroz 5kg",
      "quantity": 2,
      "unit": "un",
      "notes": "preferencia Tio Joao"
    },
    {
      "name": "feijao 1kg",
      "quantity": 1
    }
  ],
  "cep": "01310100",
  "markets": ["carrefour", "atacadao"],
  "budget": 100.00
}
```

**Campos do Item:**

| Campo | Tipo | Obrigatorio | Descricao |
|---|---|---|---|
| name | string | Sim | Nome do produto |
| quantity | integer | Nao | Quantidade (padrao: 1) |
| unit | string | Nao | Unidade (kg, L, un) |
| notes | string | Nao | Observacoes |

**Resposta:**
```json
{
  "items": [
    {
      "query": "arroz 5kg",
      "quantity": 2,
      "best_offer": {
        "name": "Arroz Tipo 1 5kg",
        "price": 24.99,
        "market_id": "atacadao",
        "market_name": "Atacadao"
      },
      "alternatives": [...],
      "total_price": 49.98,
      "status": "found"
    }
  ],
  "total_items": 2,
  "items_found": 2,
  "best_total": 57.97,
  "budget": 100.00,
  "within_budget": true,
  "savings_from_comparison": 8.50,
  "metadata": {
    "cep": "01310100",
    "markets_searched": ["carrefour", "atacadao"]
  }
}
```

### POST /api/v1/shopping/text

Processa lista de compras em texto livre (um item por linha).

**Corpo da Requisicao:**
```json
{
  "text": "2x arroz 5kg\nfeijao 1kg\n3 pacotes de cafe\noleo 900ml",
  "cep": "01310100",
  "markets": null,
  "budget": 150.00
}
```

**Formatos de texto suportados:**
- "arroz 5kg" - item simples
- "2x leite 1L" - quantidade com x
- "3 pacotes de cafe" - quantidade por extenso
- "feijao" - item sem especificacao de quantidade

### POST /api/v1/shopping/optimize

Analisa diferentes estrategias de compra para otimizar gastos.

**Corpo da Requisicao:** Mesmo do endpoint `/shopping/list`

**Resposta:**
```json
{
  "items": [...],
  "strategies": [
    {
      "name": "best_price",
      "description": "Melhor preco para cada item (pode exigir multiplos mercados)",
      "total": 85.50,
      "markets_count": 3,
      "items_found": 5,
      "items_total": 5,
      "coverage_percent": 100.0,
      "details": [...]
    },
    {
      "name": "single_market_atacadao",
      "description": "Tudo no Atacadao",
      "total": 89.00,
      "markets_count": 1,
      "items_found": 5,
      "items_total": 5,
      "coverage_percent": 100.0,
      "details": [...]
    }
  ],
  "recommended": "best_price",
  "potential_savings": 12.50,
  "metadata": {
    "cep": "01310100",
    "total_items": 5,
    "items_found": 5,
    "strategies_analyzed": 6
  }
}
```

### POST /api/v1/shopping/quick

Versao rapida para bots - retorna apenas totais.

**Corpo da Requisicao:** Mesmo do endpoint `/shopping/text`

**Resposta:**
```json
{
  "success": true,
  "total_items": 5,
  "items_found": 5,
  "total": 85.50,
  "by_market": {
    "Atacadao": 35.00,
    "Carrefour": 28.50,
    "GBarbosa": 22.00
  },
  "not_found": [],
  "within_budget": true
}
```

---

## Headers de Requisicao

### Autenticacao e Identificacao

| Header | Descricao |
|---|---|
| X-User-ID | Identificador do usuario (para rate limiting) |
| X-Telegram-User | ID do usuario Telegram (alternativa ao X-User-ID) |

### Headers de Resposta (Rate Limiting)

| Header | Descricao |
|---|---|
| X-RateLimit-Limit | Limite de requisicoes por minuto |
| X-RateLimit-Remaining | Requisicoes restantes |
| X-RateLimit-Reset | Segundos ate reset do contador |
| Retry-After | Segundos para aguardar (quando limite excedido) |

---

## Codigos de Resposta HTTP

| Codigo | Descricao |
|---|---|
| 200 | Sucesso |
| 400 | Requisicao invalida (parametros incorretos) |
| 404 | Recurso nao encontrado |
| 422 | Erro de validacao |
| 429 | Rate limit excedido |
| 500 | Erro interno do servidor |

---

## Sistema de Ranking

O sistema utiliza ranking fuzzy para priorizar resultados relevantes.

### Regra Principal

A primeira palavra da busca deve ser igual a primeira palavra do titulo do produto para ser considerado relevante.

**Exemplo:**
- Busca: "Arroz 5kg"
- "Arroz Tipo 1 Tio Joao 5kg" - Relevante (primeira palavra = "arroz")
- "Feijao Carioca 1kg" - Nao relevante (primeira palavra diferente)

### Estrategias de Ranking

| Estrategia | Descricao |
|---|---|
| PRICE_FIRST | Prioriza menor preco entre os relevantes |
| RELEVANCE_FIRST | Prioriza maior score de relevancia |
| BALANCED | Equilibrio entre preco e relevancia |

### Scores

- **relevance_score**: 0.0 a 1.0 (baseado no match da primeira palavra e quantidade)
- **price_score**: 0.0 a 1.0 (normalizado entre menor e maior preco)
- **final_score**: Combinacao ponderada dos dois scores

---

## Normalizacao de Precos

O sistema normaliza precos para unidades base, permitindo comparacao justa.

### Unidades Suportadas

| Categoria | Unidades | Unidade Base |
|---|---|---|
| Massa | kg, g, mg | kg |
| Volume | L, ml | L |
| Contagem | un, pack, dz | un |

### Exemplos de Normalizacao

- "Arroz 5kg por R$ 24,99" = R$ 5,00/kg
- "Leite 1L por R$ 4,99" = R$ 4,99/L
- "Oleo 900ml por R$ 8,99" = R$ 9,99/L
- "Cerveja 12x350ml por R$ 35,99" = R$ 8,57/L

---

## Circuit Breaker

O sistema implementa circuit breaker para proteger contra falhas em cascata.

### Parametros de Configuracao

| Parametro | Padrao | Descricao |
|---|---|---|
| failure_threshold | 3 | Falhas para abrir o circuito |
| recovery_timeout_seconds | 60 | Tempo para tentar recuperacao |
| half_open_max_calls | 1 | Chamadas de teste em half_open |

### Comportamento

1. **CLOSED**: Requisicoes fluem normalmente
2. **OPEN**: Requisicoes sao bloqueadas apos atingir threshold de falhas
3. **HALF_OPEN**: Apos timeout, permite uma requisicao de teste
4. Se teste bem-sucedido, volta para CLOSED
5. Se teste falhar, volta para OPEN

---

## Cache

O sistema utiliza Redis para cache de resultados.

### Configuracao

| Parametro | Padrao | Descricao |
|---|---|---|
| cache_enabled | true | Habilita/desabilita cache |
| cache_ttl_seconds | 300 | Tempo de vida do cache (5 minutos) |
| cache_prefix | price_tracker: | Prefixo das chaves |

### Chave de Cache

A chave e gerada a partir de:
- Termo de busca (normalizado)
- CEP (ou "all")
- Lista de mercados (ou "all")

---

## Rate Limiting

### Limites Padrao

| Tipo | Limite |
|---|---|
| Por usuario | 60 requisicoes/minuto |
| Por IP (sem identificacao) | 120 requisicoes/minuto |
| Por mercado (scraping) | 8-10 requisicoes/minuto |

### Resposta de Rate Limit Excedido

```json
{
  "error": "rate_limit_exceeded",
  "message": "Limite de requisicoes excedido. Tente novamente em 45 segundos.",
  "retry_after": 45
}
```

---

## Exemplos de Uso

### Busca Simples com cURL

```bash
curl -X GET "http://localhost:8000/api/v1/search?q=arroz%205kg" \
  -H "X-User-ID: usuario123"
```

### Busca Avancada

```bash
curl -X POST "http://localhost:8000/api/v1/search" \
  -H "Content-Type: application/json" \
  -H "X-User-ID: usuario123" \
  -d '{
    "query": "arroz tipo 1 5kg",
    "cep": "01310100",
    "markets": ["carrefour", "atacadao"],
    "max_pages": 2
  }'
```

### Lista de Compras

```bash
curl -X POST "http://localhost:8000/api/v1/shopping/text" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "arroz 5kg\nfeijao 1kg\noleo 900ml\nleite 1L",
    "cep": "01310100",
    "budget": 100.00
  }'
```

### Comparacao de Precos

```bash
curl -X GET "http://localhost:8000/api/v1/search/compare?q=leite%20integral%201L"
```

---

## Variaveis de Ambiente

| Variavel | Padrao | Descricao |
|---|---|---|
| ENV | development | Ambiente (development, production, testing) |
| DEBUG | false | Modo debug |
| LOG_LEVEL | INFO | Nivel de log |
| API_HOST | 0.0.0.0 | Host da API |
| API_PORT | 8000 | Porta da API |
| REDIS_URL | redis://localhost:6379/0 | URL do Redis |
| CACHE_TTL_SECONDS | 300 | TTL do cache |
| RATE_LIMIT_REQUESTS_PER_MINUTE | 60 | Limite de requisicoes |

---

## Executando a API

### Desenvolvimento

```bash
python -m src.api.main
```

### Producao (com Uvicorn)

```bash
uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### CLI

O sistema tambem oferece interface de linha de comando:

```bash
# Busca simples
python -m src.cli search "arroz 5kg"

# Busca com CEP
python -m src.cli search "arroz 5kg" --cep 01310100

# Comparacao de precos
python -m src.cli compare "leite integral 1L"

# Listar mercados
python -m src.cli markets

# Estatisticas
python -m src.cli stats --days 30
```