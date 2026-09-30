import os
import sys
import json
import logging
import datetime
from typing import Any, Dict, Optional


class JSONFormatter(logging.Formatter):
    """
    Formateador de logs en formato JSON estructurado para Azure Application Insights
    y Container Apps Log Analytics.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_payload: Dict[str, Any] = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Extraer campos personalizados inyectados vía extra={}
        if hasattr(record, "session_id") and record.session_id:
            log_payload["session_id"] = record.session_id
        if hasattr(record, "step") and record.step:
            log_payload["step"] = record.step
        if hasattr(record, "latency_ms") and record.latency_ms is not None:
            log_payload["latency_ms"] = record.latency_ms
        if hasattr(record, "status") and record.status:
            log_payload["status"] = record.status
        if hasattr(record, "custom_data") and record.custom_data:
            log_payload["data"] = record.custom_data

        if record.exc_info:
            log_payload["error"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else "UnknownException",
                "message": str(record.exc_info[1]) if record.exc_info[1] else "",
                "traceback": self.formatException(record.exc_info),
            }

        return json.dumps(log_payload, ensure_ascii=False)


def setup_logging(level: Optional[str] = None) -> None:
    """Configura el handler raíz para salida en JSON estructurado."""
    log_level = level or os.getenv("LOG_LEVEL", "INFO").upper()
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level, logging.INFO))

    # Limpiar handlers previos para evitar duplicación
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root_logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Obtiene una instancia de logger configurada con el nombre del módulo."""
    logger = logging.getLogger(name)
    if not logging.getLogger().handlers:
        setup_logging()
    return logger


def log_event(
    logger: logging.Logger,
    level: str,
    message: str,
    session_id: Optional[str] = None,
    step: Optional[str] = None,
    latency_ms: Optional[float] = None,
    status: Optional[str] = None,
    **kwargs: Any,
) -> None:
    """
    Función de utilidad para emitir un log estructurado con metadatos de sesión.
    """
    lvl = getattr(logging, level.upper(), logging.INFO)
    extra_fields = {
        "session_id": session_id,
        "step": step,
        "latency_ms": latency_ms,
        "status": status,
        "custom_data": kwargs if kwargs else None,
    }
    logger.log(lvl, message, extra=extra_fields)
