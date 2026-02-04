#!/bin/bash
# ===========================================
# Setup inicial do projeto (Linux/Mac)
# ===========================================

set -e

echo ""
echo "========================================"
echo "  PRICE COLLECTOR - SETUP INICIAL"
echo "========================================"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# [1/5] Python
echo "[1/5] Verificando Python..."
if command -v python3 &> /dev/null; then
    PYTHON=python3
elif command -v python &> /dev/null; then
    PYTHON=python
else
    echo -e "      ${RED}ERRO: Python não encontrado!${NC}"
    echo "      Instale Python 3.11+"
    exit 1
fi
echo -e "      ${GREEN}$($PYTHON --version)${NC}"

# [2/5] Node.js
echo "[2/5] Verificando Node.js..."
if ! command -v node &> /dev/null; then
    echo -e "      ${RED}ERRO: Node.js não encontrado!${NC}"
    echo "      Instale Node.js 18+"
    exit 1
fi
echo -e "      ${GREEN}Node $(node --version)${NC}"

# [3/5] Redis (opcional)
echo "[3/5] Verificando Redis..."
if command -v redis-server &> /dev/null; then
    echo -e "      ${GREEN}Redis instalado${NC}"
else
    echo -e "      ${YELLOW}Redis não encontrado (opcional)${NC}"
fi

# [4/5] Setup Python
echo "[4/5] Configurando ambiente Python..."
if [ ! -d ".venv" ]; then
    $PYTHON -m venv .venv
    echo "      venv criado"
fi
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt
echo -e "      ${GREEN}Dependências Python OK${NC}"

# Cria .env se não existir
if [ ! -f ".env" ]; then
    cp .env.example .env 2>/dev/null || echo "# Configurações" > .env
    echo "      .env criado"
fi

# Cria diretórios
mkdir -p data logs

# [5/5] Setup Bot WhatsApp
echo "[5/5] Configurando Bot WhatsApp..."
cd whatsapp_bot

if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "      .env criado"
fi

npm install --silent
echo -e "      ${GREEN}Dependências Node.js OK${NC}"

cd ..

echo ""
echo "========================================"
echo -e "  ${GREEN}SETUP CONCLUÍDO!${NC}"
echo "========================================"
echo ""
echo "  Próximos passos:"
echo "  1. Edite o arquivo .env com suas configurações"
echo "  2. Edite whatsapp_bot/.env se necessário"
echo "  3. Execute: ./start_all.sh"
echo ""
echo "  Ou com Docker:"
echo "  docker-compose up -d"
echo ""
