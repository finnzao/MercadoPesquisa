# Buscar produtos
price-collector search "arroz tipo 1 5kg"
price-collector search "leite integral 1L" --cep 40000000
price-collector search "banana prata" --market carrefour --pages 2

# Comparar preços
price-collector compare "café 500g"
price-collector compare "açúcar 1kg" --cep 40000000 --json

# Listar mercados
price-collector markets

# Ver estatísticas
price-collector stats
price-collector stats --market carrefour --days 7

# Histórico de preços
price-collector history "arroz tipo 1"
price-collector history "leite" --market atacadao --days 60

# Exportar dados
price-collector export resultados.csv
price-collector export dados.parquet --format parquet --query "arroz"

# Versão
price-collector version