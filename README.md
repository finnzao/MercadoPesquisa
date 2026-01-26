# Documentação do Sistema Price Collector

## Visão Geral

O Price Collector é um sistema de coleta e comparação de preços de supermercados online. Desenvolvido em Python, o sistema permite buscar produtos em múltiplos mercados simultaneamente, normalizar preços por unidade de medida e encontrar as melhores ofertas disponíveis.

O projeto foi construído com foco em escalabilidade, manutenibilidade e performance, utilizando arquitetura modular que separa claramente as responsabilidades de cada componente.

---

## Arquitetura do Sistema

O sistema segue uma arquitetura em camadas, onde cada módulo possui responsabilidades bem definidas:

```
┌─────────────────────────────────────────────────────────────┐
│                         API REST                             │
│                    (FastAPI - src/api)                       │
├─────────────────────────────────────────────────────────────┤
│                      Serviços                                │
│              (Cache, Search, Rate Limiting)                  │
├─────────────────────────────────────────────────────────────┤
│                      Collector                               │
│              (Orquestrador Principal)                        │
├──────────────┬──────────────┬──────────────┬────────────────┤
│   Scrapers   │   Pipeline   │   Ranking    │    Storage     │
│  (Coleta)    │(Processamento)│  (Ordenação) │ (Persistência) │
└──────────────┴──────────────┴──────────────┴────────────────┘
```

---

## Estrutura de Diretórios

```
price-collector/
├── config/                 # Configurações do sistema
│   ├── __init__.py
│   ├── settings.py         # Configurações globais via Pydantic
│   ├── markets.py          # Configuração dos mercados suportados
│   └── logging_config.py   # Configuração de logging estruturado
├── src/                    # Código fonte principal
│   ├── api/                # API REST FastAPI
│   ├── core/               # Componentes centrais
│   ├── pipeline/           # Processamento de dados
│   ├── ranking/            # Sistema de relevância e ordenação
│   ├── scrapers/           # Coletores por mercado
│   ├── services/           # Serviços de negócio
│   ├── shopping_list/      # Processador de lista de compras
│   ├── storage/            # Persistência de dados
│   ├── cli.py              # Interface de linha de comando
│   └── collector.py        # Orquestrador principal
├── data/                   # Diretório de dados gerados
├── logs/                   # Arquivos de log
└── pyproject.toml          # Configuração do projeto Python
```

---

## Módulos Principais

### Config

O módulo de configuração centraliza todas as definições do sistema.

#### settings.py

Utiliza Pydantic Settings para carregar configurações de variáveis de ambiente e arquivo `.env`. As principais configurações incluem:

|Categoria|Configuração|Descrição|Padrão|
|---|---|---|---|
|Ambiente|`env`|Ambiente de execução|development|
|Ambiente|`debug`|Modo debug|False|
|Ambiente|`log_level`|Nível de log|INFO|
|API|`api_port`|Porta da API|8000|
|API|`api_prefix`|Prefixo das rotas|/api/v1|
|Cache|`redis_url`|URL do Redis|redis://localhost:6379/0|
|Cache|`cache_ttl_seconds`|TTL do cache|300|
|Collector|`collector_timeout_seconds`|Timeout por mercado|30|
|Collector|`collector_concurrent_limit`|Limite de concorrência|5|

#### markets.py

Define a configuração de cada mercado suportado através da classe `MarketConfig`:

|Mercado|ID|Status|Método|Requer CEP|
|---|---|---|---|---|
|Carrefour|carrefour|Ativo|API|Não|
|Atacadão|atacadao|Ativo|API|Não|
|Pão de Açúcar|pao_acucar|Ativo|API|Sim|
|GBarbosa|gbarbosa|Ativo|API|Não|
|Sam's Club|samsclub|Ativo|API|Não|
|Rede Mix|redemix|Ativo|API|Não|
|Mercantil Atacado|mercantil|Ativo|API|Não|
|Hiperideal|hiperideal|Ativo|API|Não|
|Extra|extra|Descontinuado|Playwright|Não|

---

### Core

O módulo core contém os componentes fundamentais do sistema.

#### models.py

Define os modelos de dados usando Pydantic:

**RawProduct**: Produto bruto extraído do scraper, contendo dados exatamente como vieram do site.

**QuantityInfo**: Informação de quantidade extraída e normalizada, incluindo valor, unidade e multiplicador para packs.

**NormalizedProduct**: Produto com dados normalizados e validados, pronto para cálculo de preço por unidade.

**PriceOffer**: Oferta final com preço normalizado por unidade, estrutura principal para comparação de preços.

**SearchResult**: Resultado completo de uma busca, contendo metadados e lista de ofertas.

#### types.py

Define tipos customizados e enumerações:

|Enumeração|Valores|Uso|
|---|---|---|
|Unit|kg, g, mg, L, ml, un, pack, dz|Unidades de medida|
|Availability|available, unavailable, low_stock, unknown|Status de disponibilidade|
|NormalizationStatus|success, partial, failed, n/a|Status da normalização|
|CollectionStatus|success, partial, failed, timeout, blocked|Status da coleta|

#### http_client.py

Implementa um pool de clientes HTTP com as seguintes características:

- HTTP/2 com multiplexing para melhor performance
- Connection pooling por mercado
- Rate limiting automático por domínio
- Semáforos para controle de concorrência
- Headers anti-detecção configurados

#### browser_pool.py

Gerencia instâncias do Playwright para scrapers que necessitam de renderização JavaScript:

- Reutilização de contextos por mercado
- Scripts anti-detecção injetados
- Limite de páginas simultâneas via semáforo
- User agents rotativos

---

### Scrapers

Cada mercado possui seu próprio scraper, todos herdando de uma classe base comum.

#### Hierarquia de Classes

```
BaseScraper (base.py)
    └── BaseAPIScraper (base_api.py)
            ├── CarrefourScraper
            ├── AtacadaoScraper
            ├── PaoDeAcucarScraper
            └── VTEXOptimizedScraper (vtex_graphql.py)
                    ├── GBarbosaScraper
                    ├── SamsClubScraper
                    ├── RedeMixScraper
                    ├── MercantilAtacadoScraper
                    └── HiperidealScraper
```

#### BaseAPIScraper

Classe base para scrapers que utilizam APIs HTTP. Características:

- Tratamento de respostas comprimidas (Brotli, gzip, deflate)
- Retry automático com backoff exponencial
- Parsing de JSON com fallback para múltiplos encodings

#### VTEXOptimizedScraper

Classe especializada para lojas que utilizam plataforma VTEX:

- Suporta Intelligent Search API com fallback para Legacy Search
- 50 produtos por página (máximo VTEX)
- Parsing padronizado de produtos VTEX

#### ScraperManager

Orquestra a execução de múltiplos scrapers em paralelo:

```python
manager = ScraperManager()
products, metadata = await manager.search_all(
    query="arroz 5kg",
    cep="01310100",
    max_pages=2
)
```

---

### Pipeline

O pipeline processa os dados brutos extraídos pelos scrapers.

#### Fluxo de Processamento

```
RawProduct → Parser → NormalizedProduct → Calculator → PriceOffer → Ranker → RankedOffer
```

#### ProductParser

Converte strings de preço para Decimal, tratando formatos brasileiros:

- "R$ 12,99" ou "12.99" para Decimal
- Extrai preço unitário quando disponível no site
- Determina disponibilidade a partir de texto

#### QuantityNormalizer

Extrai e normaliza quantidades do título do produto:

|Formato de Entrada|Quantidade Extraída|
|---|---|
|"Arroz 5kg"|5.0 kg|
|"Leite 1L"|1.0 L|
|"Cerveja 12x350ml"|4.2 L (12 * 350ml)|
|"Pack c/ 6 unidades"|6 un|
|"Banana por kg"|1.0 kg (inferido)|

#### PriceCalculator

Calcula o preço normalizado por unidade base:

```
Preço Normalizado = Preço Total / Quantidade em Unidade Base
```

Exemplo: Arroz 5kg por R$ 25,00 resulta em R$ 5,00/kg

---

### Ranking

Sistema de classificação de resultados por relevância e preço.

#### FuzzyMatcher

Verifica se um produto é relevante para a busca. A regra principal é que a primeira palavra da busca deve ser igual à primeira palavra do título do produto.

|Busca|Título|Relevante|
|---|---|---|
|"arroz 5kg"|"Arroz Tipo 1 Tio João 5kg"|Sim|
|"arroz 5kg"|"Feijão Carioca 1kg"|Não|
|"leite integral"|"Leite Integral Piracanjuba 1L"|Sim|

#### ResultRanker

Combina relevância e preço para criar ranking final. Estratégias disponíveis:

|Estratégia|Peso Relevância|Peso Preço|Uso|
|---|---|---|---|
|PRICE_FIRST|0.2|0.8|Prioriza menor preço|
|RELEVANCE_FIRST|0.8|0.2|Prioriza relevância|
|BALANCED|0.4|0.6|Equilíbrio entre ambos|

---

### Services

Camada de serviços que orquestra a lógica de negócio.

#### CacheService

Implementa cache em duas camadas:

|Camada|Tecnologia|TTL|Latência|
|---|---|---|---|
|L1|Memória (LRU)|60s|~0.1ms|
|L2|Redis|300s|~1-5ms|

Fluxo de leitura:

1. Verifica L1 (memória)
2. Se não encontrar, verifica L2 (Redis)
3. Se encontrar em L2, popula L1

#### SearchService

Serviço principal de busca com as seguintes otimizações:

- Early return quando atingir número mínimo de resultados
- Streaming de resultados conforme mercados completam
- Circuit breaker por mercado para isolar falhas
- Timeout por mercado e timeout global

Os circuit breakers possuem três estados:

|Estado|Descrição|Ação|
|---|---|---|
|CLOSED|Normal|Aceita requisições|
|OPEN|Bloqueado|Rejeita requisições|
|HALF_OPEN|Testando|Permite uma requisição de teste|

---

### API

API REST construída com FastAPI.

#### Endpoints Principais

|Método|Rota|Descrição|
|---|---|---|
|GET|/api/v1/search|Busca produtos|
|POST|/api/v1/search|Busca avançada|
|GET|/api/v1/search/compare|Compara preços entre mercados|
|GET|/api/v1/search/fast|Busca otimizada para bots|
|POST|/api/v1/search/multi|Busca múltiplos itens|
|GET|/api/v1/markets|Lista mercados disponíveis|
|GET|/api/v1/markets/status|Status dos circuit breakers|

#### Exemplo de Resposta de Busca

```json
{
    "request_id": "abc12345",
    "query": "arroz 5kg",
    "status": "success",
    "total_results": 45,
    "best_offer": {
        "title": "Arroz Tipo 1 Tio João 5kg",
        "price": 24.99,
        "normalized_price": 5.00,
        "market_name": "Atacadão",
        "url": "https://..."
    },
    "results": [...]
}
```

---

### Storage

Persistência de dados com suporte a múltiplos backends.

|Backend|Formato|Uso Recomendado|
|---|---|---|
|SQLite|Banco relacional|Consultas complexas, histórico|
|CSV|Texto estruturado|Exportação, visualização|
|Parquet|Binário comprimido|Grandes volumes, análise|

#### StorageManager

Unifica acesso aos diferentes backends:

```python
manager = StorageManager(base_path=Path("./data"))

# Salva em SQLite (padrão)
await manager.save_search_result(result)

# Exporta para CSV
await manager.export_to_csv(search_query="arroz")

# Exporta para Parquet
await manager.export_to_parquet(market_id="carrefour")
```

---

### Shopping List

Módulo para processamento de listas de compras completas.

#### Funcionalidades

- Busca cada item da lista em todos os mercados
- Encontra o melhor preço para cada item
- Calcula total estimado da compra
- Agrupa resultados por mercado
- Exporta em múltiplos formatos (texto, HTML, JSON, Markdown, CSV)

#### Exemplo de Uso

```python
processor = ShoppingListProcessor()

items = [
    ShoppingItem("arroz 5kg", quantity=2),
    ShoppingItem("feijão 1kg"),
    ShoppingItem("leite 1L", quantity=6)
]

result = await processor.process(items, cep="01310100")

print(f"Total: {result.formatted_total}")
for item in result.items:
    print(f"{item.item_name}: {item.formatted_price}")
```

---

### CLI

Interface de linha de comando usando Typer e Rich para formatação.

#### Comandos Disponíveis

|Comando|Descrição|
|---|---|
|search|Busca produtos com ranking|
|smart-search|Busca inteligente com detalhes de ranking|
|compare|Compara preços entre mercados|
|markets|Lista mercados disponíveis|
|stats|Exibe estatísticas de coleta|
|history|Mostra histórico de preços|
|export|Exporta dados para arquivo|

#### Exemplos

```bash
# Busca simples
price-collector search "arroz 5kg"

# Busca com CEP
price-collector search "leite 1L" --cep 01310100

# Comparação de preços
price-collector compare "banana prata"

# Exportar resultados
price-collector export resultado.csv --format csv
```

---

## Fluxo de Execução

### Busca Simples

1. Usuário envia requisição de busca
2. SearchService verifica cache (L1 -> L2)
3. Se cache miss, executa busca nos scrapers
4. Scrapers coletam dados em paralelo
5. Pipeline processa e normaliza dados
6. Ranker ordena por relevância e preço
7. Resultado é cacheado e retornado

### Busca com Early Return

1. Tasks são criadas para todos os mercados
2. Conforme cada mercado completa, resultados são agregados
3. Quando atingir número mínimo de resultados, retorna imediatamente
4. Tasks pendentes são canceladas

---

## Dependências Principais

|Pacote|Versão|Uso|
|---|---|---|
|httpx|>=0.27.0|Cliente HTTP async com HTTP/2|
|playwright|>=1.40.0|Automação de browser|
|pydantic|>=2.5.0|Validação de dados|
|fastapi|-|Framework web (via uvicorn)|
|structlog|>=23.2.0|Logging estruturado|
|pandas|>=2.1.0|Manipulação de dados|
|pyarrow|>=14.0.0|Suporte a Parquet|
|redis|-|Cache distribuído|
|aiosqlite|>=0.19.0|SQLite assíncrono|
|tenacity|>=8.2.0|Retry com backoff|
|typer|>=0.9.0|CLI|
|rich|>=13.7.0|Formatação de terminal|

---

## Considerações de Performance

### Otimizações Implementadas

1. **Connection Pooling**: Reutilização de conexões HTTP por mercado
2. **HTTP/2 Multiplexing**: Múltiplas requisições na mesma conexão
3. **Cache Multi-camada**: Reduz latência de 5ms para 0.1ms
4. **Early Return**: Retorna assim que tiver resultados suficientes
5. **Streaming**: Processa resultados conforme chegam
6. **Compressão**: Suporte a gzip, brotli e deflate

### Limites e Configurações

|Configuração|Valor|Descrição|
|---|---|---|
|Timeout global|10s|Tempo máximo para busca completa|
|Timeout por mercado|8s|Tempo máximo por scraper|
|Min results early return|5|Resultados mínimos para retorno antecipado|
|Max concurrent markets|5|Mercados simultâneos|
|Cache L1 max size|1000|Entradas em memória|
|Rate limit padrão|10 req/min|Requisições por mercado|

---

## Tratamento de Erros

O sistema implementa uma hierarquia de exceções customizadas:

```
PriceCollectorError
    ├── ScraperError
    │       ├── NetworkError
    │       ├── RateLimitError
    │       ├── BlockedError
    │       └── HTMLChangedError
    ├── ParsingError
    ├── NormalizationError
    ├── StorageError
    │       ├── DatabaseError
    │       └── FileStorageError
    └── ValidationError
```

Cada exceção carrega contexto adicional como market_id, URL, e detalhes específicos do erro.

---

## Extensibilidade

### Adicionando Novo Mercado

1. Criar configuração em `config/markets.py`
2. Implementar scraper herdando de `BaseAPIScraper` ou `VTEXOptimizedScraper`
3. Registrar no `SCRAPER_REGISTRY` em `src/scrapers/__init__.py`
4. Adicionar rate limit em `config/settings.py`

### Adicionando Novo Backend de Storage

1. Criar classe herdando de `BaseStorage`
2. Implementar métodos abstratos
3. Registrar no `StorageManager`