# WhatsApp Price Bot

Bot de WhatsApp para comparacao de precos usando Baileys 6.6.0

## Instalacao

```bash
rm -rf node_modules package-lock.json auth/
npm install
npm start
```

## Primeira Conexao

1. Execute `npm start`
2. Um QR Code aparecera no terminal
3. No WhatsApp do celular:
   - Configuracoes > Aparelhos conectados
   - Conectar um aparelho
   - Escaneie o QR Code

## Comandos

| Comando | Descricao |
|---------|-----------|
| !buscar <produto> | Busca um produto |
| !comparar <produto> | Compara precos |
| !lista | Lista de compras |
| !cep <numero> | Define CEP |
| !mercados | Lista mercados |
| !status | Status do sistema |
| !ajuda | Mostra ajuda |

## Configuracao (.env)

```env
API_BASE_URL=http://localhost:8000/api/v1
DEFAULT_CEP=01310100
BOT_PREFIX=!
```
