"""
Logging setup helpers.

Usage:
    from core.logging_utils import setup_logging
    setup_logging(config.logging)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Dict, Any

from core.event_logging import (
    DEFAULT_DATE_FORMAT,
    DEFAULT_FORMAT,
    build_stream_handler,
)


def setup_logging(logging_cfg: Dict[str, Any]) -> None:
    level_name = logging_cfg.get("level", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    log_dir = logging_cfg.get("directory", "logs")
    prefix = logging_cfg.get("file_prefix", "kite_algo")

    os.makedirs(log_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d")
    log_file = os.path.join(log_dir, f"{prefix}_{ts}.log")

    stream_handler = build_stream_handler()
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(DEFAULT_FORMAT, datefmt=DEFAULT_DATE_FORMAT))
    logging.basicConfig(
        level=level,
        handlers=[
            stream_handler,
            file_handler,
        ],
    )
