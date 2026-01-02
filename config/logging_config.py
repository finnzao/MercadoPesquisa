"""
Configuracao de logging estruturado usando structlog.
Formato compacto em linha unica.
"""

import logging
import sys
from pathlib import Path
from typing import Optional

import structlog
from structlog.typing import Processor


def _compact_renderer(_, __, event_dict):
    """
    Renderiza log em formato compacto de linha unica.
    Formato: HH:MM:SS [LEVEL] Mensagem                  param1=valor1 param2=valor2
    """
    timestamp = event_dict.pop("timestamp", "")
    level = event_dict.pop("level", "info").upper()
    event = event_dict.pop("event", "")
    
    # Remove campos internos do structlog
    event_dict.pop("_record", None)
    event_dict.pop("_from_structlog", None)
    
    # Cores ANSI
    colors = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[35m",
    }
    reset = "\033[0m"
    dim = "\033[2m"
    
    level_color = colors.get(level, "")
    
    # Formata parametros inline
    params = " ".join(f"{k}={v}" for k, v in event_dict.items())
    
    if params:
        return f"{timestamp} [{level_color}{level:7}{reset}] {event:<40} {dim}{params}{reset}"
    return f"{timestamp} [{level_color}{level:7}{reset}] {event}"


def setup_logging(
    level: str = "INFO",
    log_path: Optional[Path] = None,
    json_format: bool = False,
    market_id: Optional[str] = None,
) -> structlog.BoundLogger:
    """
    Configura o sistema de logging.
    
    Args:
        level: Nivel de log (DEBUG, INFO, WARNING, ERROR)
        log_path: Diretorio para salvar arquivos de log
        json_format: Se True, usa formato JSON (producao)
        market_id: ID do mercado para logs especificos
        
    Returns:
        Logger configurado
    """
    timestamper = structlog.processors.TimeStamper(fmt="%H:%M:%S")
    
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]
    
    if json_format:
        processors: list[Processor] = [
            *shared_processors,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        processors = [
            *shared_processors,
            _compact_renderer,
        ]
    
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper()),
    )
    
    if log_path:
        log_path.mkdir(parents=True, exist_ok=True)
        
        general_handler = logging.FileHandler(
            log_path / "price_collector.log",
            encoding="utf-8",
        )
        general_handler.setLevel(getattr(logging, level.upper()))
        logging.getLogger().addHandler(general_handler)
        
        if market_id:
            market_handler = logging.FileHandler(
                log_path / f"{market_id}.log",
                encoding="utf-8",
            )
            market_handler.setLevel(logging.DEBUG)
            logging.getLogger(f"scraper.{market_id}").addHandler(market_handler)
    
    logger = structlog.get_logger()
    
    if market_id:
        logger = logger.bind(market=market_id)
    
    return logger


def get_logger(name: str = "price_collector", **context) -> structlog.BoundLogger:
    """Retorna um logger com contexto."""
    logger = structlog.get_logger(name)
    if context:
        logger = logger.bind(**context)
    return logger


class LoggerMixin:
    """Mixin para adicionar logging a classes."""
    
    @property
    def logger(self) -> structlog.BoundLogger:
        if not hasattr(self, "_logger"):
            self._logger = get_logger(self.__class__.__name__)
        return self._logger
    
    def log_operation(self, operation: str, **kwargs) -> structlog.BoundLogger:
        return self.logger.bind(operation=operation, **kwargs)