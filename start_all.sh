#!/bin/bash
# ===========================================
# Script para iniciar API + Bot WhatsApp (Linux/Mac)
# ===========================================

set -e

echo ""
echo "========================================"
echo "  PRICE COLLECTOR - INICIANDO SERVIÇOS"
echo "========================================"
echo ""

# Diretório do script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Função para verificar se porta está em uso
check_port() {
    lsof -i:$1 >/dev/null 2>&1
}

# Função para matar processo na porta
kill_port() {
    lsof -ti:$1 | xargs kill -9 2>/dev/null || true
}

# [1/3] Redis
echo -e "[1/3] Verificando Redis..."
if redis-cli ping >/dev/null 2>&1; then
    echo -e "      ${GREEN}Redis OK${NC}"
else
    echo -e "      ${YELLOW}Iniciando Redis...${NC}"
    redis-server --daemonize yes
    sleep 1
fi

# [2/3] API Python
echo -e "[2/3] Iniciando API Python..."
if check_port 8000; then
    echo -e "      ${YELLOW}Porta 8000 em uso. Reiniciando...${NC}"
    kill_port 8000
    sleep 1
fi

# Ativa venv e inicia API em background
source .venv/bin/activate 2>/dev/null || source venv/bin/activate 2>/dev/null || {
    echo -e "      ${RED}Erro: venv não encontrado${NC}"
    exit 1
}

nohup python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 > logs/api.log 2>&1 &
API_PID=$!
echo "      API PID: $API_PID"

# Aguarda API iniciar
echo "      Aguardando API..."
sleep 3

# Verifica se API está rodando
if curl -s http://localhost:8000/health >/dev/null 2>&1; then
    echo -e "      ${GREEN}API OK${NC}"
else
    echo -e "      ${YELLOW}API ainda iniciando...${NC}"
fi

# [3/3] Bot WhatsApp
echo -e "[3/3] Iniciando Bot WhatsApp..."
cd whatsapp_bot

# Verifica se node_modules existe
if [ ! -d "node_modules" ]; then
    echo "      Instalando dependências..."
    npm install
fi

# Inicia o bot (mantém em foreground para ver QR Code)
echo ""
echo "========================================"
echo "  SERVIÇOS INICIADOS"
echo "========================================"
echo ""
echo "  API:      http://localhost:8000"
echo "  Docs:     http://localhost:8000/docs"
echo "  Health:   http://localhost:8000/health"
echo ""
echo "  Bot WhatsApp: QR Code abaixo"
echo ""
echo "========================================"
echo ""

# Executa o bot (foreground para ver QR)
exec npm start
