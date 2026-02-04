@echo off
REM ===========================================
REM Setup inicial do projeto (Windows)
REM ===========================================

echo.
echo ========================================
echo   PRICE COLLECTOR - SETUP INICIAL
echo ========================================
echo.

cd /d %~dp0

REM [1/4] Verifica Python
echo [1/4] Verificando Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo      ERRO: Python nao encontrado!
    echo      Instale Python 3.11+ de https://python.org
    pause
    exit /b 1
)
echo      Python OK

REM [2/4] Setup Python venv
echo [2/4] Configurando ambiente Python...
if not exist ".venv" (
    python -m venv .venv
    echo      venv criado
)
call .venv\Scripts\activate
pip install -r requirements.txt --quiet
echo      Dependencias Python OK

REM [3/4] Verifica Node.js
echo [3/4] Verificando Node.js...
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo      ERRO: Node.js nao encontrado!
    echo      Instale Node.js 18+ de https://nodejs.org
    pause
    exit /b 1
)
echo      Node.js OK

REM [4/4] Setup Bot WhatsApp
echo [4/4] Configurando Bot WhatsApp...
cd whatsapp_bot
if not exist ".env" (
    copy .env.example .env >nul
    echo      .env criado
)
call npm install --silent
echo      Dependencias Node.js OK

cd ..

REM Cria .env principal se não existir
if not exist ".env" (
    copy .env.example .env >nul
    echo      .env principal criado
)

echo.
echo ========================================
echo   SETUP CONCLUIDO!
echo ========================================
echo.
echo   Proximos passos:
echo   1. Edite o arquivo .env com suas configuracoes
echo   2. Edite whatsapp_bot\.env se necessario
echo   3. Execute: start_all.bat
echo.
pause
