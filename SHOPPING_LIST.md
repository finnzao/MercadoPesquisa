# 📋 Módulo de Lista de Compras

O módulo de Lista de Compras permite processar uma lista de itens e encontrar automaticamente o melhor preço para cada um nos supermercados disponíveis.

## 🚀 Funcionalidades

- ✅ Processar lista de compras com múltiplos itens
- ✅ Encontrar o melhor preço para cada item
- ✅ Suporte a quantidades personalizadas
- ✅ Mostrar alternativas de outros mercados
- ✅ Exportar resultados em múltiplos formatos (Text, JSON, HTML, Markdown, CSV)
- ✅ Resumo por mercado
- ✅ Cálculo do total estimado da compra

## 📦 Instalação

O módulo já faz parte do Price Collector. Certifique-se de ter todas as dependências instaladas:

```bash
pip install -r requirements.txt
```

## 🎯 Uso via CLI

### Processar lista de itens

```bash
# Lista simples
python -m src.shopping_list.cli process "arroz 5kg" "feijão 1kg" "leite 1L"

# Com CEP para localização
python -m src.shopping_list.cli process "arroz 5kg" "leite 1L" --cep 01310100

# Com mercado específico
python -m src.shopping_list.cli process "arroz 5kg" --market carrefour

# Exportar para HTML
python -m src.shopping_list.cli process "arroz 5kg" "feijão 1kg" --format html --output lista.html

# Mostrar alternativas
python -m src.shopping_list.cli process "arroz 5kg" "leite 1L" --alternatives
```

### Processar arquivo de lista

```bash
# Processar arquivo
python -m src.shopping_list.cli from-file lista_compras.txt

# Com CEP e exportação
python -m src.shopping_list.cli from-file lista.txt --cep 01310100 --format html --output resultado.html
```

### Modo interativo

```bash
python -m src.shopping_list.cli interactive
```

### Busca rápida de um item

```bash
# Busca simples
python -m src.shopping_list.cli quick "arroz 5kg"

# Com quantidade
python -m src.shopping_list.cli quick "leite 1L" --qty 12
```

## 📝 Uso via Python

### Exemplo básico

```python
import asyncio
from src.shopping_list import ShoppingItem, ShoppingListProcessor, ResultFormatter

async def main():
    # Cria lista de itens
    items = [
        ShoppingItem("arroz 5kg", quantity=2),
        ShoppingItem("feijão 1kg"),
        ShoppingItem("leite integral 1L", quantity=6),
    ]
    
    # Processa
    processor = ShoppingListProcessor()
    result = await processor.process(items, cep="01310100")
    
    # Exibe resultados
    for item in result.items:
        if item.found:
            print(f"✅ {item.item_name}")
            print(f"   Produto: {item.product_title}")
            print(f"   Preço: {item.formatted_price}")
            print(f"   Total: {item.formatted_total} ({item.item_quantity}x)")
            print(f"   Mercado: {item.market_name}")
            print(f"   Link: {item.product_url}")
            if item.image_url:
                print(f"   Imagem: {item.image_url}")
        else:
            print(f"❌ {item.item_name} - Não encontrado")
    
    # Total
    print(f"\n💰 TOTAL: {result.formatted_total}")

asyncio.run(main())
```

### Processar texto

```python
from src.shopping_list.processor import process_shopping_list_text

async def main():
    texto = """
    arroz 5kg
    2x feijão 1kg
    leite 1L (quantidade: 6)
    """
    
    result = await process_shopping_list_text(texto)
    print(f"Total: {result.formatted_total}")
```

### Exportar para HTML

```python
from src.shopping_list import ResultFormatter

# ... após processar a lista ...

html = ResultFormatter.to_html(result)
with open("lista_compras.html", "w") as f:
    f.write(html)
```

## 📊 Estrutura do Resultado

### ShoppingListResult

```python
result.total_items        # Total de itens na lista
result.items_found        # Itens encontrados
result.total_estimated    # Valor total estimado
result.formatted_total    # Total formatado (R$ X.XXX,XX)
result.items              # Lista de ItemResult
result.not_found          # Lista de itens não encontrados
result.get_by_market()    # Agrupa por mercado
```

### ItemResult

```python
item.item_name           # Nome original do item
item.item_quantity       # Quantidade
item.found               # Se foi encontrado
item.product_title       # Nome do produto encontrado
item.price               # Preço unitário
item.total_price         # Preço total (price * quantity)
item.formatted_price     # Preço formatado
item.normalized_price    # Preço por kg/L
item.price_display       # Ex: "R$ 5,98/kg"
item.market_id           # ID do mercado
item.market_name         # Nome do mercado
item.product_url         # Link do produto
item.image_url           # URL da imagem
item.alternatives        # Lista de alternativas
```

## 📄 Formatos de Saída

### Texto (padrão)
```
✅ arroz 5kg
   📦 Arroz Tipo 1 Tio João 5kg
   💰 Preço: R$ 29,90
   🏬 Local: Carrefour
   🔗 Link: https://...
```

### JSON
```json
{
  "items": [
    {
      "item_name": "arroz 5kg",
      "product_title": "Arroz Tipo 1 Tio João 5kg",
      "price": 29.90,
      "market_name": "Carrefour",
      "product_url": "https://...",
      "image_url": "https://..."
    }
  ],
  "total_estimated": 150.50
}
```

### HTML
Gera uma página HTML responsiva com cards para cada produto, imagens, links e resumo.

### Markdown
Gera documento Markdown com tabelas e seções organizadas.

### CSV
```
Item;Produto;Preço Unitário;Quantidade;Preço Total;Mercado;URL;Imagem
arroz 5kg;Arroz Tipo 1 Tio João 5kg;29.90;1;29.90;Carrefour;https://...;https://...
```

## 📁 Formato do Arquivo de Lista

O arquivo de entrada aceita os seguintes formatos:

```
# Comentários começam com #
# Linhas em branco são ignoradas

# Formato simples
arroz 5kg
feijão 1kg

# Com quantidade usando "x"
2x leite integral 1L
6x água mineral 500ml

# Com quantidade entre parênteses
café 500g (quantidade: 2)
açúcar 1kg (qty: 3)

# Com quantidade usando "-"
3 - óleo de soja 900ml
```

## 🏪 Mercados Suportados

- Carrefour
- Atacadão
- Pão de Açúcar

## ⚙️ Configurações

### RankingStrategy

```python
from src.ranking import RankingStrategy

processor = ShoppingListProcessor(
    ranking_strategy=RankingStrategy.PRICE_FIRST,  # Prioriza menor preço
    include_alternatives=True,                      # Inclui alternativas
    max_alternatives=2,                             # Máximo de alternativas
)
```

### Estratégias disponíveis:
- `PRICE_FIRST`: Prioriza o menor preço (padrão)
- `RELEVANCE_FIRST`: Prioriza relevância do produto
- `BALANCED`: Equilíbrio entre preço e relevância

## 🔧 Troubleshooting

### "Produto não encontrado"
- Tente termos mais genéricos (ex: "arroz" ao invés de "arroz tipo 1 tio joão")
- Verifique se o CEP está correto
- Alguns produtos podem não estar disponíveis em todos os mercados

### "Timeout na busca"
- Reduza o número de itens por busca
- Verifique sua conexão com a internet
- Alguns sites podem estar lentos ou bloqueando

## 📚 Exemplos Completos

Veja o arquivo `examples/shopping_list_example.py` para exemplos completos de uso.