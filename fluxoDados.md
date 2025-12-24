┌─────────────────────────────────────────────────────────────────────────────┐
│ ENTRADA                                                                      │
│ query: "arroz tipo 1 5kg"                                                   │
│ cep: "40000000" (opcional)                                                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ ETAPA 1: SCRAPING (paralelo)                                                │
│                                                                             │
│ Carrefour ──┐                                                               │
│ Atacadão ───┼──▶ [RawProduct, RawProduct, RawProduct, ...]                 │
│ Pão Açúcar ─┤                                                               │
│ Extra ──────┘                                                               │
│                                                                             │
│ RawProduct = {                                                              │
│   market_id: "carrefour",                                                   │
│   title: "Arroz Tipo 1 Tio João 5kg",                                      │
│   price_raw: "R$ 29,90",                                                    │
│   url: "https://...",                                                       │
│   ...                                                                       │
│ }                                                                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ ETAPA 2: PARSING                                                            │
│                                                                             │
│ "R$ 29,90" ──▶ Decimal("29.90")                                            │
│ "Disponível" ──▶ Availability.AVAILABLE                                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ ETAPA 3: NORMALIZAÇÃO DE QUANTIDADE                                         │
│                                                                             │
│ "Arroz Tipo 1 Tio João 5kg" ──▶ QuantityInfo {                             │
│                                   value: 5.0,                               │
│                                   unit: kg,                                 │
│                                   base_value: 5.0,                          │
│                                   base_unit: kg,                            │
│                                   multiplier: 1                             │
│                                 }                                           │
│                                                                             │
│ "Cerveja 350ml Pack c/ 12" ──▶ QuantityInfo {                              │
│                                  value: 350.0,                              │
│                                  unit: ml,                                  │
│                                  base_value: 0.35,                          │
│                                  base_unit: L,                              │
│                                  multiplier: 12                             │
│                                  total: 4.2L                                │
│                                }                                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ ETAPA 4: CÁLCULO DE PREÇO NORMALIZADO                                       │
│                                                                             │
│ Arroz:   R$ 29,90 / 5kg = R$ 5,98/kg                                       │
│ Cerveja: R$ 39,90 / 4.2L = R$ 9,50/L                                       │
│                                                                             │
│ PriceOffer = {                                                              │
│   market_id: "carrefour",                                                   │
│   title: "Arroz Tipo 1 Tio João 5kg",                                      │
│   price: 29.90,                                                             │
│   normalized_price: 5.98,                                                   │
│   normalized_unit: "kg",                                                    │
│   price_display: "R$ 5,98/kg",                                             │
│   is_comparable: true                                                       │
│ }                                                                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ ETAPA 5: COMPARAÇÃO E ORDENAÇÃO                                             │
│                                                                             │
│ 1. Atacadão  - R$ 5,50/kg  ← MELHOR OFERTA                                 │
│ 2. Carrefour - R$ 5,98/kg  (economia: R$ 0,48/kg = 8%)                     │
│ 3. Extra     - R$ 6,58/kg  (economia: R$ 1,08/kg = 16%)                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ ETAPA 6: PERSISTÊNCIA                                                       │
│                                                                             │
│ SQLite: data/price_collector.db (queries, histórico)                        │
│ CSV: data/csv/offers/offers_20240115_143022.csv (exportação)               │
│ Parquet: data/parquet/offers/offers_20240115_143022.parquet (big data)     │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ SAÍDA                                                                        │
│                                                                             │
│ SearchResult {                                                              │
│   metadata: { query, cep, duration, markets... },                           │
│   offers: [PriceOffer, PriceOffer, ...],                                   │
│   best_offer: PriceOffer,                                                   │
│   comparable_offers: 15,                                                    │
│   total_offers: 18                                                          │
│ }                                                                           │
└─────────────────────────────────────────────────────────────────────────────┘