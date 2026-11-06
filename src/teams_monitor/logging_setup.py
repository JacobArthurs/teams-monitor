from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
MAX_LOG_BYTES = 5 * 1024 * 1024
LOG_BACKUPS = 3


def configure_logging(verbose: bool = False, log_file: Path | None = None) -> None:
    handler: logging.Handler
    if log_file is not None:
        handler = RotatingFileHandler(
            log_file, maxBytes=MAX_LOG_BYTES, backupCount=LOG_BACKUPS, encoding="utf-8"
        )
    else:
        handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(LOG_FORMAT))

    logger = logging.getLogger("teams_monitor")
    for existing in list(logger.handlers):
        logger.removeHandler(existing)
        existing.close()
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.propagate = False
