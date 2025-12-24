"""
Configuração de logging estruturado usando structlog.
Gera logs em formato JSON para produção e colorido para desenvolvimento.
"""

import logging
import sys
from pathlib import Path
from typing import Optional

import structlog
from structlog.typing import Processor


def setup_logging(
    level: str = "INFO",
    log_path: Optional[Path] = None,
    json_format: bool = False,
    market_id: Optional[str] = None,
) -> structlog.BoundLogger:
    """
    Configura o sistema de logging.
    
    Args:
        level: Nível de log (DEBUG, INFO, WARNING, ERROR)
        log_path: Diretório para salvar arquivos de log
        json_format: Se True, usa formato JSON (produção)
        market_id: ID do mercado para logs específicos
        
    Returns:
        Logger configurado
    """
    
    # Processadores comuns
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]
    
    if json_format:
        # Formato JSON para produção
        processors: list[Processor] = [
            *shared_processors,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        # Formato colorido para desenvolvimento
        processors = [
            *shared_processors,
            structlog.dev.ConsoleRenderer(
                colors=True,
                exception_formatter=structlog.dev.plain_traceback,
            ),
        ]
    
    # Configurar structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # Configurar logging padrão do Python também
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper()),
    )
    
    # Configurar handlers de arquivo se log_path fornecido
    if log_path:
        log_path.mkdir(parents=True, exist_ok=True)
        
        # Log geral
        general_handler = logging.FileHandler(
            log_path / "price_collector.log",
            encoding="utf-8",
        )
        general_handler.setLevel(getattr(logging, level.upper()))
        logging.getLogger().addHandler(general_handler)
        
        # Log específico do mercado
        if market_id:
            market_handler = logging.FileHandler(
                log_path / f"{market_id}.log",
                encoding="utf-8",
            )
            market_handler.setLevel(logging.DEBUG)
            logging.getLogger(f"scraper.{market_id}").addHandler(market_handler)
    
    # Criar logger base
    logger = structlog.get_logger()
    
    if market_id:
        logger = logger.bind(market=market_id)
    
    return logger


def get_logger(name: str = "price_collector", **context) -> structlog.BoundLogger:
    """
    Retorna um logger com contexto.
    
    Args:
        name: Nome do logger
        **context: Contexto adicional para bind
        
    Returns:
        Logger com contexto
    """
    logger = structlog.get_logger(name)
    if context:
        logger = logger.bind(**context)
    return logger


class LoggerMixin:
    """Mixin para adicionar logging a classes."""
    
    @property
    def logger(self) -> structlog.BoundLogger:
        """Retorna logger com nome da classe."""
        if not hasattr(self, "_logger"):
            self._logger = get_logger(self.__class__.__name__)
        return self._logger
    
    def log_operation(
        self,
        operation: str,
        **kwargs,
    ) -> structlog.BoundLogger:
        """Retorna logger com operação bindada."""
        return self.logger.bind(operation=operation, **kwargs)