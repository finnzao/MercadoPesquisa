# 🛒 Price Collector WhatsApp Bot

Bot para WhatsApp que integra com o sistema Price Collector, permitindo buscar e comparar preços de supermercados diretamente pelo WhatsApp.

## 📋 Funcionalidades

- **Busca de Produtos**: Encontre o melhor preço para qualquer produto
- **Comparação de Preços**: Compare preços entre diferentes mercados
- **Lista de Compras**: Processe múltiplos itens de uma vez
- **Configuração de CEP**: Personalize sua localização para melhor precisão
- **Rate Limiting**: Controle de requisições por usuário
- **Sessões de Usuário**: Mantém preferências entre conversas

## 🚀 Instalação

### Pré-requisitos

- Node.js 18+
- API do Price Collector rodando
- Conta no WhatsApp

### Passos

1. **Clone ou copie os arquivos para seu servidor**

```bash
cd whatsapp-bot
```

2. **Instale as dependências**

```bash
npm install
```

3. **Configure as variáveis de ambiente**

```bash
cp .env.example .env
nano .env
```

Edite o arquivo `.env` com suas configurações:

```env
# URL da API do Price Collector
API_BASE_URL=http://localhost:8000/api/v1

# CEP padrão
DEFAULT_CEP=01310100

# Nome do bot
BOT_NAME=PriceBot

# Prefixo dos comandos
BOT_PREFIX=!
```

4. **Inicie o bot**

```bash
npm start
```

5. **Escaneie o QR Code**

Na primeira execução, um QR Code será exibido no terminal. Escaneie-o com o WhatsApp do seu celular:
- Abra o WhatsApp
- Vá em Configurações > Aparelhos Conectados
- Toque em "Conectar um aparelho"
- Escaneie o QR Code

## 📱 Comandos Disponíveis

| Comando | Descrição | Exemplo |
|---------|-----------|---------|
| `!buscar <produto>` | Busca um produto | `!buscar arroz 5kg` |
| `!comparar <produto>` | Compara preços | `!comparar leite integral` |
| `!lista` | Inicia modo lista de compras | `!lista` |
| `!cep <numero>` | Define seu CEP | `!cep 01310100` |
| `!mercados` | Lista mercados disponíveis | `!mercados` |
| `!status` | Status do sistema | `!status` |
| `!ajuda` | Mostra ajuda | `!ajuda` |

### Lista de Compras

Você pode enviar uma lista de compras de duas formas:

**1. Comando + itens na mesma mensagem:**
```
!lista arroz 5kg, feijão 1kg, leite 1L
```

**2. Comando seguido de lista:**
```
!lista
```
E depois envie os itens (um por linha):
```
arroz 5kg
feijão 1kg
2x leite 1L
óleo 900ml
```

### Flags Especiais

Adicione flags às buscas para comportamentos especiais:

- `/total` - Encontra o melhor mercado único para toda a lista
- `/compare` - Força modo de comparação

Exemplo:
```
!lista arroz, feijão, leite /total
```

## 🏗️ Arquitetura

```
whatsapp-bot/
├── src/
│   ├── index.js          # Entry point - conexão Baileys
│   ├── config.js         # Configurações
│   ├── handlers/
│   │   └── commands.js   # Handler de comandos
│   ├── services/
│   │   ├── api.js        # Cliente da API Price Collector
│   │   ├── session.js    # Gerenciador de sessões
│   │   └── rateLimiter.js # Rate limiting
│   └── utils/
│       ├── formatter.js  # Formatação de mensagens
│       └── parser.js     # Parser de comandos
├── auth/                 # Credenciais (não committar!)
├── package.json
├── .env
└── .env.example
```

## ⚙️ Configurações Avançadas

### Autorização de Usuários

Para restringir o bot a números específicos:

```env
# Apenas estes números podem usar o bot
ALLOWED_NUMBERS=5511999999999,5511888888888

# Números de administradores
ADMIN_NUMBERS=5511999999999
```

### Rate Limiting

```env
# Máximo de requisições por minuto por usuário
RATE_LIMIT_PER_USER=10
```

### Logging

```env
# Níveis: trace, debug, info, warn, error, fatal
LOG_LEVEL=info
```

## 🔄 Integração com a API

O bot se comunica com os seguintes endpoints da API:

| Endpoint | Uso |
|----------|-----|
| `GET /search/fast` | Busca rápida (otimizada) |
| `GET /search` | Busca completa |
| `GET /search/compare` | Comparação de preços |
| `POST /search/multi` | Lista de compras |
| `GET /markets` | Lista mercados |
| `GET /health` | Health check |

## 🐛 Troubleshooting

### QR Code não aparece

- Verifique se o terminal suporta caracteres unicode
- Tente aumentar o tamanho da janela do terminal

### "Sessão encerrada"

1. Delete a pasta `auth/`
2. Reinicie o bot
3. Escaneie o QR Code novamente

### Erro de conexão com API

- Verifique se a API está rodando
- Confirme a URL em `API_BASE_URL`
- Teste: `curl http://localhost:8000/health`

### Rate limit excedido

- Aumente `RATE_LIMIT_PER_USER` no `.env`
- Ou aguarde 1 minuto entre requisições

## 📝 Logs

Os logs são exibidos no console. Em desenvolvimento:

```bash
npm run dev  # Com hot-reload
```

Para produção, considere usar PM2:

```bash
npm install -g pm2
pm2 start src/index.js --name price-bot
pm2 logs price-bot
```

## 🔒 Segurança

- **Nunca commite a pasta `auth/`** - contém credenciais do WhatsApp
- Use `ALLOWED_NUMBERS` para restringir acesso em produção
- Mantenha o `.env` fora do controle de versão
- Use HTTPS se a API estiver em servidor remoto

## 📄 Licença

MIT

## 🤝 Contribuição

1. Fork o repositório
2. Crie uma branch (`git checkout -b feature/nova-feature`)
3. Commit suas mudanças (`git commit -am 'Adiciona nova feature'`)
4. Push para a branch (`git push origin feature/nova-feature`)
5. Abra um Pull Request
