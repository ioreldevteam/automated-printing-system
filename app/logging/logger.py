"""Three-tier logging setup (Section 57-58): application, production, printer,
and error logs, each with rotation. Production/audit *business* events are
additionally persisted to the database (system_events / audit_logs tables) by
the repository layer -- these files are the technical/operational trail.
"""
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from app.config.loader import LoggingConfig

_configured = False


def configure_logging(config: LoggingConfig) -> None:
    global _configured
    if _configured:
        return

    log_dir = Path(config.directory)
    log_dir.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    root = logging.getLogger()
    root.setLevel(config.level)

    def _rotating_handler(filename: str, level: int) -> logging.Handler:
        handler = logging.handlers.RotatingFileHandler(
            log_dir / filename, maxBytes=config.max_bytes, backupCount=config.backup_count, encoding="utf-8"
        )
        handler.setFormatter(formatter)
        handler.setLevel(level)
        return handler

    root.addHandler(_rotating_handler("application.log", logging.DEBUG))

    error_handler = _rotating_handler("error.log", logging.ERROR)
    root.addHandler(error_handler)

    production_logger = logging.getLogger("production")
    production_logger.addHandler(_rotating_handler("production.log", logging.INFO))
    production_logger.propagate = True

    printer_logger = logging.getLogger("printer")
    printer_logger.addHandler(_rotating_handler("printer.log", logging.INFO))
    printer_logger.propagate = True

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    _configured = True
