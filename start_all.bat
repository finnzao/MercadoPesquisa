@echo off
REM ===========================================
REM Script para iniciar API + Bot WhatsApp (Windows)
REM ===========================================

echo.
echo ========================================
echo   PRICE COLLECTOR - INICIANDO SERVICOS
echo ========================================
echo.

REM Verifica se Redis está rodando
echo [1/3] Verificando Redis...
redis-cli ping >nul 2>&1
if %errorlevel% neq 0 (
    echo      Redis nao encontrado. Iniciando...
    start "Redis" redis-server
    timeout /t 2 >nul
) else (
    echo      Redis OK
)

REM Inicia a API Python em uma nova janela
echo [2/3] Iniciando API Python...
start "Price Collector API" cmd /k "cd /d %~dp0 && call .venv\Scripts\activate && python -m uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000"

REM Aguarda a API iniciar
echo      Aguardando API iniciar (5s)...
timeout /t 5 >nul

REM Inicia o Bot WhatsApp em uma nova janela
echo [3/3] Iniciando Bot WhatsApp...
start "WhatsApp Bot" cmd /k "cd /d %~dp0whatsapp_bot && npm start"

echo.
echo ========================================
echo   SERVICOS INICIADOS
echo ========================================
echo.
echo   API:      http://localhost:8000
echo   Docs:     http://localhost:8000/docs
echo   Health:   http://localhost:8000/health
echo.
echo   Bot WhatsApp: Escaneie o QR Code na janela do bot
echo.
echo ========================================
echo.

pause
