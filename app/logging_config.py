"""
Structured JSON logging.
Все логи пишутся в формате JSON — удобно для сбора в ELK/Loki/Datadog.
"""
import logging
import sys
from typing import Any

import json_log_formatter

from app.config import settings


def configure_logging() -> None:
    formatter = json_log_formatter.JSONFormatter()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(settings.log_level.upper())
    root_logger.handlers = [handler]

    # Отключаем лишние логи от uvicorn/sqlalchemy
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
