"""
Entry point principal da API FastAPI.

Esta é a aplicação principal que expõe os endpoints REST
para o bot Telegram e outros clientes.
"""

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import structlog

from config.settings import get_settings
from src.api.v1.router import api_router
from src.services.cache_service import RedisClient


settings = get_settings()
logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gerencia ciclo de vida da aplicação.
    
    - Startup: Conecta ao Redis, inicializa serviços
    - Shutdown: Fecha conexões, limpa recursos
    """
    logger.info(
        "Iniciando aplicação",
        environment=settings.env,
        debug=settings.debug,
    )
    
    # Conecta ao Redis (se disponível)
    try:
        redis_client = await RedisClient.get_instance()
        if redis_client.is_connected:
            logger.info("Redis conectado com sucesso")
        else:
            logger.warning("Redis não disponível - cache desabilitado")
    except Exception as e:
        logger.warning("Erro ao conectar Redis", error=str(e))
    
    logger.info(
        "Aplicação iniciada",
        api_version=settings.api_version,
        mercados_habilitados=len(settings.mercados_enabled),
    )
    
    yield
    
    # SHUTDOWN
    logger.info("Encerrando aplicação")
    
    # Desconecta Redis
    try:
        redis_client = await RedisClient.get_instance()
        await redis_client.disconnect()
    except Exception:
        pass
    
    logger.info("Aplicação encerrada")


def create_app() -> FastAPI:
    """
    Factory function para criar a aplicação FastAPI.
    
    Returns:
        Instância configurada do FastAPI
    """
    
    app = FastAPI(
        title=settings.api_title,
        version=settings.api_version,
        description="""
# Price Tracker API
        """,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        openapi_url="/openapi.json" if settings.debug else "/openapi.json",
        lifespan=lifespan,
    )
    
    # MIDDLEWARES
    
    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.debug else [
            "https://seudominio.com",
            "https://api.telegram.org",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Compressão GZip
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    
    # EXCEPTION HANDLERS
    
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """Handler para erros de validação."""
        errors = []
        for error in exc.errors():
            field = ".".join(str(loc) for loc in error["loc"])
            errors.append({
                "field": field,
                "message": error["msg"],
                "type": error["type"],
            })
        
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "status": "error",
                "message": "Erro de validação nos dados enviados",
                "errors": errors,
            },
        )
    
    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        """Handler genérico para exceções não tratadas."""
        logger.error(
            "Erro não tratado",
            path=request.url.path,
            method=request.method,
            error=str(exc),
            exc_info=True,
        )
        
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "status": "error",
                "message": "Erro interno do servidor",
                "detail": str(exc) if settings.debug else None,
            },
        )
    
    # ROTAS
    
    # API v1
    app.include_router(api_router, prefix=settings.api_prefix)
    
    # Health check (root)
    @app.get("/health", tags=["Health"])
    async def health_check():
        """
        Verifica saúde da API.
        
        Retorna status dos componentes:
        - API: sempre "ok" se respondeu
        - Redis: "connected" ou "disconnected"
        - Mercados: quantidade habilitada
        """
        redis_status = "disconnected"
        try:
            redis_client = await RedisClient.get_instance()
            redis_status = "connected" if redis_client.is_connected else "disconnected"
        except Exception:
            pass
        
        return {
            "status": "healthy",
            "version": settings.api_version,
            "environment": settings.env,
            "components": {
                "api": "ok",
                "redis": redis_status,
                "mercados_enabled": len(settings.mercados_enabled),
            },
        }
    
    @app.get("/", tags=["Root"])
    async def root():
        """Endpoint raiz com informações básicas."""
        return {
            "name": settings.api_title,
            "version": settings.api_version,
            "docs": "/docs" if settings.debug else None,
            "health": "/health",
            "api": settings.api_prefix,
        }
    
    return app


# Cria instância da aplicação
app = create_app()


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "src.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
