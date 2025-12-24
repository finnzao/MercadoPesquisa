┌─────────────────────────────────────────┐
│              offers                      │
├─────────────────────────────────────────┤
│ id                  TEXT PK             │
│ market_id           TEXT NOT NULL       │
│ market_name         TEXT NOT NULL       │
│ title               TEXT NOT NULL       │
│ url                 TEXT NOT NULL       │
│ price               REAL NOT NULL       │
│ quantity_value      REAL                │
│ quantity_unit       TEXT                │
│ normalized_price    REAL                │
│ normalized_unit     TEXT                │
│ price_display       TEXT                │
│ availability        TEXT                │
│ normalization_status TEXT               │
│ search_query        TEXT NOT NULL       │
│ cep                 TEXT                │
│ collected_at        TIMESTAMP           │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│            collections                   │
├─────────────────────────────────────────┤
│ id                  TEXT PK             │
│ search_query        TEXT NOT NULL       │
│ cep                 TEXT                │
│ markets_requested   TEXT (JSON)         │
│ started_at          TIMESTAMP           │
│ finished_at         TIMESTAMP           │
│ total_products      INTEGER             │
│ total_normalized    INTEGER             │
│ total_errors        INTEGER             │
│ results_json        TEXT                │
│ errors_json         TEXT                │
└─────────────────────────────────────────┘