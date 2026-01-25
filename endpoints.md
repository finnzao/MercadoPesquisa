Implemente o cache multi-layer primeiro - maior impacto imediato
Ajuste os timeouts - limite o pior caso
Adicione métricas - monitore latência por mercado
Considere WebSocket para bots - reduz overhead de HTTP
Implemente queue para picos - RabbitMQ ou Redis Streams

# Explicação dos Endpoints de Busca Rápida

## Visão Geral

Os endpoints `/fast` foram criados especificamente para bots (WhatsApp/Telegram) que precisam de respostas rápidas e simplificadas.

---

## Endpoint 1: `/api/v1/search/fast` (GET)

### Propósito
Busca **um único produto** da forma mais rápida possível.

### Como usar

```bash
# Busca simples
GET /api/v1/search/fast?q=arroz

# Com CEP para priorizar mercados próximos
GET /api/v1/search/fast?q=arroz&cep=01310100
```

### Resposta

```json
{
  "found": true,
  "query": "arroz",
  "product": "Arroz Tio João 5kg",
  "price": "R$ 24,90",
  "market": "Carrefour",
  "url": "https://...",
  "total_results": 15,
  "cache_hit": false,
  "duration_ms": 1250
}
```

### Características
- **Timeout:** 5 segundos máximo
- **Early return:** Retorna assim que encontrar 3 resultados
- **Resposta mínima:** Só o essencial para o bot exibir

---

## Endpoint 2: `/api/v1/search/fast/multi` (POST)

### Propósito
Busca **múltiplos produtos** em paralelo (lista de compras).

### Como usar

```bash
POST /api/v1/search/fast/multi
Content-Type: application/json

{
  "items": ["arroz", "feijão", "óleo", "açúcar"],
  "cep": "01310100"
}
```

### Resposta

```json
{
  "success": true,
  "total_items": 4,
  "items_found": 4,
  "total": "R$ 52,60",
  "items": [
    {
      "query": "arroz",
      "found": true,
      "product": "Arroz Tio João 5kg",
      "price": "R$ 24,90",
      "market": "Carrefour",
      "url": "https://..."
    },
    {
      "query": "feijão",
      "found": true,
      "product": "Feijão Carioca Camil 1kg",
      "price": "R$ 8,90",
      "market": "Pão de Açúcar",
      "url": "https://..."
    }
  ],
  "duration_ms": 2100
}
```

### Características
- **Paralelo:** Todos os itens são buscados simultaneamente
- **Total calculado:** Soma os preços automaticamente
- **Limite:** Máximo 20 itens por requisição

---

## Por que GET vs POST?

| Aspecto | GET `/fast` | POST `/fast/multi` |
|---------|-------------|-------------------|
| **Dados** | Query string (`?q=arroz`) | Corpo JSON |
| **Cache HTTP** | Pode ser cacheado por CDN/proxy | Não cacheia |
| **Tamanho** | Limitado (~2000 caracteres) | Pode ser grande |
| **Uso** | Busca única | Lista de itens |

---

## Sobre Corpo JSON e Interpretação

### Como o FastAPI interpreta o corpo JSON

No FastAPI, o **tipo do parâmetro** determina como a requisição é interpretada:

```python
# 1. Query Parameters (GET) - Dados na URL
@router.get("/fast")
async def fast_search(
    q: str = Query(...),      # Vem de ?q=valor
    cep: str = Query(None),   # Vem de ?cep=valor
):
    pass

# 2. Body JSON (POST) - Dados no corpo
@router.post("/fast/multi")
async def fast_multi_search(
    body: MultiItemRequest,   # Vem do JSON no corpo
):
    pass
```

### Exemplo de como funciona internamente

```python
from pydantic import BaseModel

# Define o schema do corpo
class MultiItemRequest(BaseModel):
    items: list[str]      # ["arroz", "feijão"]
    cep: str | None       # "01310100" ou null

# FastAPI automaticamente:
# 1. Lê o corpo da requisição
# 2. Faz parse do JSON
# 3. Valida contra o schema
# 4. Converte para o objeto Python
```

### Mesmo endpoint, comportamentos diferentes?

Se você quer o **mesmo endpoint** aceitando formatos diferentes, pode usar `Union`:

```python
from typing import Union
from pydantic import BaseModel

# Schema para busca simples
class SingleSearch(BaseModel):
    query: str
    cep: str | None = None

# Schema para busca múltipla
class MultiSearch(BaseModel):
    items: list[str]
    cep: str | None = None

# Endpoint único que aceita ambos
@router.post("/search")
async def unified_search(
    body: Union[SingleSearch, MultiSearch],
):
    # Verifica qual tipo foi enviado
    if isinstance(body, MultiSearch):
        # Processa lista
        return await process_multi(body.items, body.cep)
    else:
        # Processa único
        return await process_single(body.query, body.cep)
```

### Uso:

```bash
# Busca simples
POST /search
{"query": "arroz", "cep": "01310100"}

# Busca múltipla (mesmo endpoint!)
POST /search
{"items": ["arroz", "feijão"], "cep": "01310100"}
```

O FastAPI tenta validar contra cada schema na ordem e usa o primeiro que funcionar.

---

## Exemplo Prático: Discriminador Explícito

Para deixar mais claro, você pode usar um campo `type`:

```python
from pydantic import BaseModel, Field
from typing import Literal

class SingleSearch(BaseModel):
    type: Literal["single"] = "single"
    query: str
    cep: str | None = None

class MultiSearch(BaseModel):
    type: Literal["multi"] = "multi"
    items: list[str]
    cep: str | None = None

# FastAPI usa o campo 'type' para decidir qual schema usar
@router.post("/search")
async def search(body: Union[SingleSearch, MultiSearch]):
    if body.type == "multi":
        # Lista de compras
        return await search_multi(body.items)
    else:
        # Produto único
        return await search_single(body.query)
```

### Uso:

```bash
# Explicitamente single
POST /search
{"type": "single", "query": "arroz"}

# Explicitamente multi
POST /search
{"type": "multi", "items": ["arroz", "feijão"]}
```

---

## Fluxo Completo de uma Requisição

```
Bot envia: POST /api/v1/search/fast/multi
           {"items": ["arroz", "feijão"]}
                    │
                    ▼
┌─────────────────────────────────────────┐
│           FastAPI                        │
│  1. Recebe requisição HTTP               │
│  2. Lê corpo (bytes)                     │
│  3. Decodifica JSON → dict               │
│  4. Valida contra MultiItemRequest       │
│  5. Cria objeto Python                   │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│      Sua função (endpoint)               │
│                                          │
│  body.items = ["arroz", "feijão"]       │
│  body.cep = None                         │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│      SearchService                       │
│  - Busca "arroz" ─┐                     │
│  - Busca "feijão" ┼─► Em paralelo       │
│                   │                      │
│  Retorna resultados                      │
└─────────────────────────────────────────┘
                    │
                    ▼
           Resposta JSON para o bot
```

---

## Resumo

| Conceito | Explicação |
|----------|------------|
| **GET com Query** | Parâmetros na URL (`?q=arroz`) |
| **POST com Body** | Dados no corpo JSON |
| **Pydantic Model** | Define estrutura esperada do JSON |
| **Union types** | Permite múltiplos schemas no mesmo endpoint |
| **Discriminador** | Campo `type` para decidir qual schema usar |

O FastAPI cuida de toda a validação e conversão automaticamente!