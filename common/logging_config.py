from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from .config import Settings, load_settings


def setup_logger(name: str = "pkb", settings: Settings | None = None) -> logging.Logger:
    settings = settings or load_settings()
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    log_path = Path(settings.log_dir) / f"{name}.log"
    if not any(isinstance(handler, TimedRotatingFileHandler) and getattr(handler, "baseFilename", "") == str(log_path) for handler in logger.handlers):
        file_handler = TimedRotatingFileHandler(
            log_path,
            when="midnight",
            interval=1,
            backupCount=30,
            encoding="utf-8",
        )
        formatter = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    if not logger.handlers:
        logger.addHandler(logging.StreamHandler())
    return logger
