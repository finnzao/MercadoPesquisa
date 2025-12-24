# Price Collector - Comparador de Preços de Supermercados

Sistema de coleta e comparação de preços para compras online em supermercados 
e atacados com e-commerce próprio.


## Licença

MIT License
```

---

## Diagrama de Arquitetura Geral
```
┌─────────────────────────────────────────────────────────────────────────┐
│                              CLI / API                                   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          PriceCollector                                  │
│  (Orquestrador: coordena scrapers, pipeline e storage)                  │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          ▼                         ▼                         ▼
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│  ScraperManager  │    │     Pipeline     │    │  StorageManager  │
│                  │    │                  │    │                  │
│ • Plugin loader  │    │ • Parser         │    │ • SQLite         │
│ • Rate limiter   │    │ • Normalizer     │    │ • CSV            │
│ • Retry handler  │    │ • PriceCalc      │    │ • Parquet        │
└──────────────────┘    └──────────────────┘    └──────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        Market Scrapers (Plugins)                         │
├──────────────────┬──────────────────┬──────────────────┬────────────────┤
│    Carrefour     │    Atacadão      │   Pão de Açúcar  │     Extra      │
│    Scraper       │    Scraper       │    Scraper       │    Scraper     │
└──────────────────┴──────────────────┴──────────────────┴────────────────┘


### Diagrama de Fluxo dos Modelos
```
┌──────────────┐     ┌────────────────────┐     ┌─────────────┐
│  RawProduct  │ ──► │ NormalizedProduct  │ ──► │ PriceOffer  │
│              │     │                    │     │             │
│ • title      │     │ • title            │     │ • title     │
│ • price_raw  │     │ • price (Decimal)  │     │ • price     │
│ • url        │     │ • quantity         │     │ • norm_price│
│ • market_id  │     │ • status           │     │ • unit      │
└──────────────┘     └────────────────────┘     └─────────────┘
     Scraper              Normalizer            PriceCalculator

```

---


---

### Diagrama de Fluxo do Pipeline
```
┌─────────────────────────────────────────────────────────────────────────┐
│                        ProcessingPipeline                               │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  ETAPA 1: ProductParser.parse_raw_product()                             │
│  ─────────────────────────────────────────                              │
│  • Converte price_raw ("R$ 12,99") → Decimal(12.99)                    │
│  • Extrai disponibilidade do texto                                      │
│  • Valida dados obrigatórios                                            │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  ETAPA 2: QuantityNormalizer.extract_quantity()                         │
│  ─────────────────────────────────────────────                          │
│  • Extrai do título: "Arroz Tipo 1 5kg" → value=5, unit=kg             │
│  • Detecta packs: "12x500ml" → value=500ml, multiplier=12              │
│  • Converte para base: 500g → 0.5kg                                    │
│  • Calcula total: 0.5kg × 12 = 6kg                                     │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  ETAPA 3: Cria NormalizedProduct                                        │
│  ──────────────────────────────────                                     │
│  • Combina dados parseados + quantidade normalizada                     │
│  • Define status de normalização (SUCCESS/PARTIAL)                      │
│  • Mantém referência ao RawProduct original                            │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  ETAPA 4: PriceCalculator.create_price_offer()                          │
│  ───────────────────────────────────────────                            │
│  • Calcula: R$ 29,90 / 5kg = R$ 5,98/kg                                │
│  • Formata para exibição: "R$ 5,98/kg"                                 │
│  • Gera PriceOffer final para comparação                               │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
                           ┌─────────────┐
                           │ PriceOffer  │
                           └─────────────┘


```

---

## Resumo do Diretório `src/scrapers/`

| Arquivo | Responsabilidade |
|---------|------------------|
| `__init__.py` | Registry de scrapers e exports |
| `rate_limiter.py` | Controle de requisições por domínio |
| `base.py` | `BaseScraper`: classe abstrata com funcionalidades comuns |
| `manager.py` | `ScraperManager`: orquestra execução paralela |
| `carrefour.py` | `CarrefourScraper`: implementação Carrefour |
| `atacadao.py` | `AtacadaoScraper`: implementação Atacadão |
| `pao_acucar.py` | `PaoDeAcucarScraper`: implementação Pão de Açúcar |
| `extra.py` | `ExtraScraper`: implementação Extra |

---

### Diagrama da Arquitetura de Scrapers
```
┌─────────────────────────────────────────────────────────────────────────┐
│                          ScraperManager                                  │
│  • Coordena execução paralela                                           │
│  • Agrega resultados                                                    │
│  • Health checks                                                        │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
            ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
            │ RateLimiter │ │  Registry   │ │   Config    │
            │             │ │             │ │             │
            │ Token bucket│ │ Scrapers    │ │ Markets     │
            │ por domínio │ │ disponíveis │ │ settings    │
            └─────────────┘ └─────────────┘ └─────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           BaseScraper (ABC)                              │
│                                                                         │
│  Métodos Comuns:                    Métodos Abstratos:                  │
│  • search()                         • extract_products()                │
│  • _init_browser()                  • set_location()                    │
│  • _scrape_page()                                                       │
│  • _check_for_blocks()                                                  │
│  • _safe_get_text()                                                     │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
        ┌───────────────┬───────────┴───────────┬───────────────┐
        ▼               ▼                       ▼               ▼
┌───────────────┐ ┌───────────────┐ ┌───────────────┐ ┌───────────────┐
│  Carrefour    │ │   Atacadão    │ │ Pão de Açúcar │ │     Extra     │
│   Scraper     │ │   Scraper     │ │   Scraper     │ │   Scraper     │
│               │ │               │ │               │ │               │
│ Playwright    │ │ Playwright    │ │ Playwright    │ │ Playwright    │
│ Seletores     │ │ Seletores     │ │ + Scroll lazy │ │ + Scroll lazy │
│ específicos   │ │ específicos   │ │ Seletores     │ │ Seletores     │
└───────────────┘ └───────────────┘ └───────────────┘ └───────────────┘




```

---

## Resumo do Diretório `src/storage/`

| Arquivo | Responsabilidade |
|---------|------------------|
| `__init__.py` | Exports do módulo |
| `base.py` | `BaseStorage`: interface abstrata para backends |
| `sqlite_storage.py` | `SQLiteStorage`: persistência estruturada com queries |
| `file_storage.py` | `CSVStorage` e `ParquetStorage`: exportação e análise |
| `manager.py` | `StorageManager`: unifica acesso a múltiplos backends |

---

### Diagrama de Storage
```
┌─────────────────────────────────────────────────────────────────────────┐
│                          StorageManager                                  │
│  • Unifica acesso a backends                                            │
│  • Permite salvar em múltiplos formatos                                 │
│  • Exportação entre formatos                                            │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          ▼                         ▼                         ▼
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│  SQLiteStorage   │    │   CSVStorage     │    │ ParquetStorage   │
│                  │    │                  │    │                  │
│ • Queries SQL    │    │ • Fácil leitura  │    │ • Compressão     │
│ • Histórico      │    │ • Excel/Sheets   │    │ • Big data       │
│ • Estatísticas   │    │ • Portável       │    │ • Analytics      │
└──────────────────┘    └──────────────────┘    └──────────────────┘
          │                         │                         │
          ▼                         ▼                         ▼
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│ data/            │    │ data/csv/        │    │ data/parquet/    │
│   price_         │    │   offers_        │    │   offers_        │
│   collector.db   │    │   20240101.csv   │    │   20240101.      │
└──────────────────┘    └──────────────────┘    │   parquet        │
                                                └──────────────────┘



```

---


| Arquivo | Responsabilidade |
|---------|------------------|
| `collector.py` | `PriceCollector`: Orquestra todo o sistema (scrapers + pipeline + storage) |
| `cli.py` | Interface de linha de comando com Rich para output bonito |

---

### Diagrama do Fluxo Completo
```
┌─────────────────────────────────────────────────────────────────────────┐
│                               CLI                                        │
│  price-collector search "arroz 5kg" --cep 40000000                      │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          PriceCollector                                  │
│  Orquestrador principal                                                 │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        ▼                           ▼                           ▼
┌───────────────┐         ┌───────────────┐         ┌───────────────┐
│ScraperManager │         │   Pipeline    │         │StorageManager │
│               │         │               │         │               │
│ • Carrefour   │         │ • Parser      │         │ • SQLite      │
│ • Atacadão    │ ──────► │ • Normalizer  │ ──────► │ • CSV         │
│ • Pão Açúcar  │         │ • Calculator  │         │ • Parquet     │
│ • Extra       │         │               │         │               │
└───────────────┘         └───────────────┘         └───────────────┘
        │                           │                           │
        ▼                           ▼                           ▼
┌───────────────┐         ┌───────────────┐         ┌───────────────┐
│  RawProduct   │         │  PriceOffer   │         │    Files      │
│  (HTML/JSON)  │         │ (Normalizado) │         │  (Persistido) │
└───────────────┘         └───────────────┘         └───────────────┘