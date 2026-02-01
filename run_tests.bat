@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

cd /d "%~dp0"

where pytest >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo pytest nao encontrado. Instalando dependencias
    pip install -r requirements-test.txt
)

set "TEST_TYPE=%~1"
if "%TEST_TYPE%"=="" set "TEST_TYPE=quick"

set "EXTRA_ARGS="
shift
:parse_args
if "%~1"=="" goto run
set "EXTRA_ARGS=%EXTRA_ARGS% %~1"
shift
goto parse_args

:run
if /i "%TEST_TYPE%"=="all" (
    echo.
    echo ============================================================
    echo                   EXECUTANDO TODOS OS TESTES
    echo ============================================================
    echo.
    pytest tests/ -v --tb=short %EXTRA_ARGS%
    set "PYTEST_EXIT=!ERRORLEVEL!"
    goto show_summary
)

if /i "%TEST_TYPE%"=="unit" (
    echo.
    echo ============================================================
    echo                 EXECUTANDO TESTES UNITARIOS
    echo ============================================================
    echo.
    pytest tests/unit/ -v --tb=short %EXTRA_ARGS%
    set "PYTEST_EXIT=!ERRORLEVEL!"
    goto show_summary
)

if /i "%TEST_TYPE%"=="api" (
    echo.
    echo ============================================================
    echo                   EXECUTANDO TESTES DE API
    echo ============================================================
    echo.
    pytest tests/api/ -v --tb=short %EXTRA_ARGS%
    set "PYTEST_EXIT=!ERRORLEVEL!"
    goto show_summary
)

if /i "%TEST_TYPE%"=="integration" (
    echo.
    echo ============================================================
    echo                EXECUTANDO TESTES DE INTEGRACAO
    echo ============================================================
    echo.
    pytest tests/integration/ -v --tb=short %EXTRA_ARGS%
    set "PYTEST_EXIT=!ERRORLEVEL!"
    goto show_summary
)

if /i "%TEST_TYPE%"=="load" (
    echo.
    echo ============================================================
    echo                  EXECUTANDO TESTES DE CARGA
    echo ============================================================
    echo.
    pytest tests/load/ -v --tb=short %EXTRA_ARGS%
    set "PYTEST_EXIT=!ERRORLEVEL!"
    goto show_summary
)

if /i "%TEST_TYPE%"=="quick" (
    echo.
    echo ============================================================
    echo                  EXECUTANDO TESTES RAPIDOS
    echo ============================================================
    echo.
    pytest tests/ --ignore=tests/load/ -v --tb=short %EXTRA_ARGS%
    set "PYTEST_EXIT=!ERRORLEVEL!"
    goto show_summary
)

if /i "%TEST_TYPE%"=="coverage" (
    echo.
    echo ============================================================
    echo               EXECUTANDO TESTES COM COBERTURA
    echo ============================================================
    echo.
    pytest tests/ --ignore=tests/load/ --cov=src --cov-report=html --cov-report=term-missing --cov-fail-under=60 -v --tb=short %EXTRA_ARGS%
    set "PYTEST_EXIT=!ERRORLEVEL!"
    echo.
    echo Relatorio HTML gerado em: htmlcov\index.html
    goto show_summary
)

if /i "%TEST_TYPE%"=="help" goto show_help
if /i "%TEST_TYPE%"=="-h" goto show_help
if /i "%TEST_TYPE%"=="--help" goto show_help

echo Tipo de teste desconhecido: %TEST_TYPE%
goto show_help

:show_summary
echo.
echo.
echo ============================================================
if !PYTEST_EXIT! EQU 0 (
    echo                      TODOS OS TESTES OK
    echo ============================================================
    echo.
    echo   Status: SUCESSO
    echo   Todos os testes passaram!
) else (
    echo                    ALGUNS TESTES FALHARAM
    echo ============================================================
    echo.
    echo   Status: FALHA
    echo   Codigo de saida: !PYTEST_EXIT!
    echo.
    echo   Dica: Execute novamente com -v para mais detalhes
    echo   Dica: Use --tb=long para traceback completo
)
echo.
echo ============================================================
goto end

:show_help
echo.
echo Uso: run_tests.bat [tipo] [opcoes]
echo.
echo Tipos de teste:
echo   all         - Executa todos os testes
echo   unit        - Apenas testes unitarios
echo   api         - Apenas testes de API
echo   integration - Apenas testes de integracao
echo   load        - Apenas testes de carga
echo   quick       - Testes rapidos, padrao
echo   coverage    - Testes com cobertura
echo.
echo Opcoes uteis do pytest:
echo   -v          - Modo verbose
echo   -x          - Para no primeiro erro
echo   -k "nome"   - Filtra testes pelo nome
echo   --tb=long   - Traceback completo
echo.
goto end

:end
echo.
pause
endlocal