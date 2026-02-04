# ===========================================
# Dockerfile para WhatsApp Bot (Node.js)
# ===========================================

FROM node:20-slim

# Metadados
LABEL maintainer="Price Collector Team"
LABEL description="WhatsApp Bot para Price Collector"

# Diretório de trabalho
WORKDIR /app

# Copia package.json primeiro (cache de dependências)
COPY package*.json ./

# Instala dependências
RUN npm ci --only=production

# Copia código fonte
COPY src/ ./src/

# Cria diretório de auth
RUN mkdir -p /app/auth

# Variáveis de ambiente padrão
ENV NODE_ENV=production
ENV LOG_LEVEL=info

# Comando de inicialização
CMD ["node", "src/index.js"]
