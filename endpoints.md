# Guia de Uso da API Price Collector

Este documento descreve como utilizar os endpoints da API REST do Price Collector. A API foi construída com FastAPI e segue padrões REST.

---

## Configuração Base

### URL Base

```
http://localhost:8000/api/v1
```

A porta padrão é `8000`, configurável via variável de ambiente `API_PORT`.

### Headers Padrão

Todas as requisições devem incluir:

```http
Content-Type: application/json
Accept: application/json
```

### Formato de Resposta

Todas as respostas seguem o formato JSON. Em caso de erro, o formato padrão é:

```json
{
    "detail": "Descrição do erro",
    "status_code": 400
}
```

---

## Endpoints de Busca

### GET /search

Realiza uma busca simples por produtos em todos os mercados disponíveis.

**Parâmetros de Query**

|Parâmetro|Tipo|Obrigatório|Descrição|
|---|---|---|---|
|q|string|Sim|Termo de busca|
|cep|string|Não|CEP para filtrar mercados regionais|
|limit|integer|Não|Limite de resultados por mercado (padrão: 10)|
|markets|string|Não|IDs dos mercados separados por vírgula|

**Exemplo de Requisição**

```bash
curl -X GET "http://localhost:8000/api/v1/search?q=arroz%205kg&limit=5"
```

**Exemplo de Resposta**

```json
{
    "request_id": "abc12345-def6-7890-ghij-klmnopqrstuv",
    "query": "arroz 5kg",
    "status": "success",
    "total_results": 45,
    "search_time_ms": 1234,
    "markets_searched": 8,
    "markets_responded": 8,
    "best_offer": {
        "title": "Arroz Tipo 1 Tio João 5kg",
        "price": 24.99,
        "normalized_price": 5.00,
        "unit": "kg",
        "market_id": "atacadao",
        "market_name": "Atacadão",
        "url": "https://www.atacadao.com.br/arroz-tio-joao-5kg",
        "image_url": "https://...",
        "availability": "available"
    },
    "results": [
        {
            "title": "Arroz Tipo 1 Tio João 5kg",
            "price": 24.99,
            "normalized_price": 5.00,
            "unit": "kg",
            "quantity": 5.0,
            "market_id": "atacadao",
            "market_name": "Atacadão",
            "url": "https://...",
            "image_url": "https://...",
            "availability": "available",
            "relevance_score": 0.95,
            "rank": 1
        }
    ]
}
```

---

### POST /search

Realiza uma busca avançada com mais opções de configuração.

**Corpo da Requisição**

```json
{
    "query": "string",
    "cep": "string",
    "limit": 10,
    "markets": ["carrefour", "atacadao"],
    "ranking_strategy": "PRICE_FIRST",
    "min_relevance": 0.5,
    "include_unavailable": false,
    "timeout_seconds": 10
}
```

**Parâmetros do Body**

|Campo|Tipo|Obrigatório|Descrição|
|---|---|---|---|
|query|string|Sim|Termo de busca|
|cep|string|Não|CEP para mercados regionais|
|limit|integer|Não|Limite de resultados por mercado (padrão: 10)|
|markets|array|Não|Lista de IDs de mercados específicos|
|ranking_strategy|string|Não|Estratégia de ranking: PRICE_FIRST, RELEVANCE_FIRST, BALANCED|
|min_relevance|float|Não|Score mínimo de relevância (0.0 a 1.0)|
|include_unavailable|boolean|Não|Incluir produtos indisponíveis|
|timeout_seconds|integer|Não|Timeout máximo da busca|

**Estratégias de Ranking**

|Estratégia|Peso Relevância|Peso Preço|Descrição|
|---|---|---|---|
|PRICE_FIRST|20%|80%|Prioriza menor preço|
|RELEVANCE_FIRST|80%|20%|Prioriza relevância da busca|
|BALANCED|40%|60%|Equilíbrio entre ambos|

**Exemplo de Requisição**

```bash
curl -X POST "http://localhost:8000/api/v1/search" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "leite integral 1L",
    "cep": "01310100",
    "limit": 20,
    "markets": ["carrefour", "pao_acucar", "atacadao"],
    "ranking_strategy": "PRICE_FIRST",
    "min_relevance": 0.6
  }'
```

---

### GET /search/compare

Compara o preço de um produto específico entre todos os mercados.

**Parâmetros de Query**

|Parâmetro|Tipo|Obrigatório|Descrição|
|---|---|---|---|
|q|string|Sim|Termo de busca|
|cep|string|Não|CEP para filtrar mercados|

**Exemplo de Requisição**

```bash
curl -X GET "http://localhost:8000/api/v1/search/compare?q=coca-cola%202L"
```

**Exemplo de Resposta**

```json
{
    "request_id": "xyz98765",
    "query": "coca-cola 2L",
    "status": "success",
    "comparison": {
        "best_price": {
            "market_id": "atacadao",
            "market_name": "Atacadão",
            "price": 7.99,
            "normalized_price": 4.00,
            "unit": "L"
        },
        "worst_price": {
            "market_id": "pao_acucar",
            "market_name": "Pão de Açúcar",
            "price": 10.99,
            "normalized_price": 5.50,
            "unit": "L"
        },
        "average_price": 9.25,
        "price_range": 3.00,
        "savings_percentage": 27.3
    },
    "by_market": [
        {
            "market_id": "atacadao",
            "market_name": "Atacadão",
            "best_offer": {
                "title": "Coca-Cola Original 2L",
                "price": 7.99,
                "normalized_price": 4.00,
                "url": "https://..."
            },
            "total_offers": 3
        },
        {
            "market_id": "carrefour",
            "market_name": "Carrefour",
            "best_offer": {
                "title": "Refrigerante Coca-Cola 2 Litros",
                "price": 8.49,
                "normalized_price": 4.25,
                "url": "https://..."
            },
            "total_offers": 5
        }
    ]
}
```

---

### GET /search/fast

Endpoint otimizado para bots e integrações que precisam de resposta rápida. Retorna apenas os dados essenciais.

**Parâmetros de Query**

|Parâmetro|Tipo|Obrigatório|Descrição|
|---|---|---|---|
|q|string|Sim|Termo de busca|
|limit|integer|Não|Limite total de resultados (padrão: 5)|

**Características**

- Timeout reduzido (5 segundos)
- Early return quando encontrar resultados mínimos
- Resposta compacta sem metadados extras
- Ideal para chatbots e automações

**Exemplo de Requisição**

```bash
curl -X GET "http://localhost:8000/api/v1/search/fast?q=banana&limit=3"
```

**Exemplo de Resposta**

```json
{
    "query": "banana",
    "best": {
        "title": "Banana Prata kg",
        "price": 5.99,
        "market": "Atacadão",
        "url": "https://..."
    },
    "alternatives": [
        {
            "title": "Banana Nanica kg",
            "price": 4.99,
            "market": "Carrefour"
        },
        {
            "title": "Banana Prata Premium kg",
            "price": 7.49,
            "market": "Pão de Açúcar"
        }
    ]
}
```

---

### POST /search/multi

Busca múltiplos itens de uma vez, ideal para listas de compras.

**Corpo da Requisição**

```json
{
    "items": [
        {"query": "arroz 5kg", "quantity": 2},
        {"query": "feijão 1kg", "quantity": 1},
        {"query": "óleo de soja 900ml", "quantity": 3}
    ],
    "cep": "01310100",
    "optimize_by": "total_price"
}
```

**Parâmetros do Body**

|Campo|Tipo|Obrigatório|Descrição|
|---|---|---|---|
|items|array|Sim|Lista de itens para buscar|
|items[].query|string|Sim|Termo de busca do item|
|items[].quantity|integer|Não|Quantidade desejada (padrão: 1)|
|cep|string|Não|CEP para mercados regionais|
|optimize_by|string|Não|Critério de otimização: total_price, single_market, balanced|

**Opções de Otimização**

|Opção|Descrição|
|---|---|
|total_price|Busca o menor preço para cada item, independente do mercado|
|single_market|Tenta encontrar todos os itens no mesmo mercado|
|balanced|Equilíbrio entre preço e conveniência|

**Exemplo de Requisição**

```bash
curl -X POST "http://localhost:8000/api/v1/search/multi" \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
        {"query": "arroz 5kg", "quantity": 1},
        {"query": "feijão carioca 1kg", "quantity": 2},
        {"query": "açúcar 1kg", "quantity": 1}
    ],
    "cep": "01310100",
    "optimize_by": "total_price"
  }'
```

**Exemplo de Resposta**

```json
{
    "request_id": "multi-123456",
    "status": "success",
    "items_found": 3,
    "items_not_found": 0,
    "estimated_total": 45.97,
    "results": [
        {
            "query": "arroz 5kg",
            "quantity": 1,
            "found": true,
            "best_offer": {
                "title": "Arroz Tipo 1 Tio João 5kg",
                "price": 24.99,
                "market_name": "Atacadão",
                "url": "https://..."
            },
            "subtotal": 24.99
        },
        {
            "query": "feijão carioca 1kg",
            "quantity": 2,
            "found": true,
            "best_offer": {
                "title": "Feijão Carioca Camil 1kg",
                "price": 7.49,
                "market_name": "Carrefour",
                "url": "https://..."
            },
            "subtotal": 14.98
        },
        {
            "query": "açúcar 1kg",
            "quantity": 1,
            "found": true,
            "best_offer": {
                "title": "Açúcar Refinado União 1kg",
                "price": 6.00,
                "market_name": "Atacadão",
                "url": "https://..."
            },
            "subtotal": 6.00
        }
    ],
    "by_market": {
        "atacadao": {
            "items": 2,
            "subtotal": 30.99
        },
        "carrefour": {
            "items": 1,
            "subtotal": 14.98
        }
    }
}
```

---

## Endpoints de Mercados

### GET /markets

Lista todos os mercados disponíveis no sistema.

**Exemplo de Requisição**

```bash
curl -X GET "http://localhost:8000/api/v1/markets"
```

**Exemplo de Resposta**

```json
{
    "total": 8,
    "markets": [
        {
            "id": "carrefour",
            "name": "Carrefour",
            "active": true,
            "requires_cep": false,
            "logo_url": "https://...",
            "website": "https://www.carrefour.com.br"
        },
        {
            "id": "atacadao",
            "name": "Atacadão",
            "active": true,
            "requires_cep": false,
            "logo_url": "https://...",
            "website": "https://www.atacadao.com.br"
        },
        {
            "id": "pao_acucar",
            "name": "Pão de Açúcar",
            "active": true,
            "requires_cep": true,
            "logo_url": "https://...",
            "website": "https://www.paodeacucar.com"
        },
        {
            "id": "gbarbosa",
            "name": "GBarbosa",
            "active": true,
            "requires_cep": false,
            "logo_url": "https://...",
            "website": "https://www.gbarbosa.com.br"
        },
        {
            "id": "samsclub",
            "name": "Sam's Club",
            "active": true,
            "requires_cep": false,
            "logo_url": "https://...",
            "website": "https://www.samsclub.com.br"
        },
        {
            "id": "redemix",
            "name": "Rede Mix",
            "active": true,
            "requires_cep": false,
            "logo_url": "https://...",
            "website": "https://www.redemix.com.br"
        },
        {
            "id": "mercantil",
            "name": "Mercantil Atacado",
            "active": true,
            "requires_cep": false,
            "logo_url": "https://...",
            "website": "https://www.mercantilatacado.com.br"
        },
        {
            "id": "hiperideal",
            "name": "Hiperideal",
            "active": true,
            "requires_cep": false,
            "logo_url": "https://...",
            "website": "https://www.hiperideal.com.br"
        }
    ]
}
```

---

### GET /markets/status

Retorna o status dos circuit breakers de cada mercado. Útil para monitoramento.

**Exemplo de Requisição**

```bash
curl -X GET "http://localhost:8000/api/v1/markets/status"
```

**Exemplo de Resposta**

```json
{
    "timestamp": "2025-01-25T15:30:00Z",
    "markets": [
        {
            "id": "carrefour",
            "name": "Carrefour",
            "circuit_state": "CLOSED",
            "is_available": true,
            "failure_count": 0,
            "last_failure": null,
            "last_success": "2025-01-25T15:29:45Z",
            "avg_response_time_ms": 1234
        },
        {
            "id": "atacadao",
            "name": "Atacadão",
            "circuit_state": "CLOSED",
            "is_available": true,
            "failure_count": 0,
            "last_failure": null,
            "last_success": "2025-01-25T15:29:50Z",
            "avg_response_time_ms": 890
        },
        {
            "id": "pao_acucar",
            "name": "Pão de Açúcar",
            "circuit_state": "HALF_OPEN",
            "is_available": true,
            "failure_count": 3,
            "last_failure": "2025-01-25T15:25:00Z",
            "last_success": "2025-01-25T15:28:00Z",
            "avg_response_time_ms": 2100
        }
    ],
    "summary": {
        "total_markets": 8,
        "available": 7,
        "unavailable": 1,
        "circuit_states": {
            "CLOSED": 6,
            "HALF_OPEN": 1,
            "OPEN": 1
        }
    }
}
```

**Estados do Circuit Breaker**

|Estado|Descrição|Comportamento|
|---|---|---|
|CLOSED|Normal|Aceita todas as requisições|
|OPEN|Bloqueado|Rejeita requisições por tempo determinado|
|HALF_OPEN|Testando|Permite uma requisição de teste para verificar recuperação|

---

## Códigos de Status HTTP

|Código|Significado|Quando ocorre|
|---|---|---|
|200|OK|Requisição bem-sucedida|
|400|Bad Request|Parâmetros inválidos|
|404|Not Found|Recurso não encontrado|
|408|Request Timeout|Timeout da busca excedido|
|422|Unprocessable Entity|Erro de validação do corpo da requisição|
|429|Too Many Requests|Rate limit excedido|
|500|Internal Server Error|Erro interno do servidor|
|503|Service Unavailable|Todos os mercados indisponíveis|

---

## Rate Limiting

A API implementa rate limiting para proteger os servidores dos mercados.

**Limites Padrão**

|Escopo|Limite|Janela|
|---|---|---|
|Global|100 requisições|1 minuto|
|Por IP|30 requisições|1 minuto|
|Por mercado|10 requisições|1 minuto|

**Headers de Rate Limit**

As respostas incluem headers informativos:

```http
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1706191800
```

**Resposta quando limite excedido**

```json
{
    "detail": "Rate limit exceeded. Try again in 45 seconds.",
    "status_code": 429,
    "retry_after": 45
}
```

---

## Exemplos de Uso Prático

### Encontrar o arroz mais barato

```bash
curl -X GET "http://localhost:8000/api/v1/search?q=arroz%205kg&limit=1"
```

### Comparar preços de um produto específico

```bash
curl -X GET "http://localhost:8000/api/v1/search/compare?q=leite%20integral%201L"
```

### Buscar em mercados específicos

```bash
curl -X POST "http://localhost:8000/api/v1/search" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "café 500g",
    "markets": ["carrefour", "atacadao"],
    "ranking_strategy": "PRICE_FIRST"
  }'
```

### Criar lista de compras otimizada

```bash
curl -X POST "http://localhost:8000/api/v1/search/multi" \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
        {"query": "arroz 5kg"},
        {"query": "feijão 1kg", "quantity": 2},
        {"query": "óleo 900ml", "quantity": 2},
        {"query": "açúcar 1kg"},
        {"query": "sal 1kg"},
        {"query": "macarrão 500g", "quantity": 3}
    ],
    "optimize_by": "total_price"
  }'
```

### Verificar saúde dos mercados

```bash
curl -X GET "http://localhost:8000/api/v1/markets/status"
```

---

## Integração com Aplicações

### Python

```python
import httpx

async def search_product(query: str) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "http://localhost:8000/api/v1/search",
            params={"q": query, "limit": 10}
        )
        return response.json()

# Uso
import asyncio
result = asyncio.run(search_product("arroz 5kg"))
print(f"Melhor preço: R$ {result['best_offer']['price']}")
```

### JavaScript/Node.js

```javascript
async function searchProduct(query) {
    const response = await fetch(
        `http://localhost:8000/api/v1/search?q=${encodeURIComponent(query)}&limit=10`
    );
    return response.json();
}

// Uso
searchProduct("arroz 5kg").then(result => {
    console.log(`Melhor preço: R$ ${result.best_offer.price}`);
});
```

### cURL em Shell Script

```bash
#!/bin/bash

QUERY="$1"
API_URL="http://localhost:8000/api/v1"

# Busca simples
result=$(curl -s "$API_URL/search?q=$(echo $QUERY | jq -sRr @uri)&limit=5")

# Extrai melhor preço
best_price=$(echo $result | jq -r '.best_offer.price')
best_market=$(echo $result | jq -r '.best_offer.market_name')

echo "Produto: $QUERY"
echo "Melhor preço: R$ $best_price em $best_market"
```

---

## Documentação Interativa

A API disponibiliza documentação interativa gerada automaticamente pelo FastAPI.

**Swagger UI**

```
http://localhost:8000/docs
```

**ReDoc**

```
http://localhost:8000/redoc
```

**OpenAPI Schema**

```
http://localhost:8000/openapi.json
```

Através do Swagger UI é possível testar todos os endpoints diretamente no navegador.