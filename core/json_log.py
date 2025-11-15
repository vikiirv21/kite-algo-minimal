from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


BASE_DIR = Path(__file__).resolve().parents[1]
LOGS_DIR = BASE_DIR / "artifacts" / "logs"
ENGINE_LOG_PATH = LOGS_DIR / "engine_events.jsonl"


class JsonLineFileHandler(logging.Handler):
    """Logging handler that appends structured JSON lines to ENGINE_LOG_PATH."""

    def __init__(self, path: Optional[Path] = None) -> None:
        super().__init__()
        self.path = path or ENGINE_LOG_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            payload = self._serialize_record(record)
            line = json.dumps(payload, ensure_ascii=False)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except Exception:  # noqa: BLE001
            self.handleError(record)

    def _serialize_record(self, record: logging.LogRecord) -> Dict[str, Any]:
        timestamp = datetime.fromtimestamp(record.created, timezone.utc).isoformat()
        payload: Dict[str, Any] = {
            "ts": timestamp,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = logging.Formatter().formatException(record.exc_info)
        elif record.exc_text:
            payload["exc_info"] = record.exc_text
        return payload


def install_engine_json_logger() -> None:
    """Attach the JSON line handler to the root logger (idempotent)."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    for handler in root.handlers:
        if isinstance(handler, JsonLineFileHandler) and handler.path == ENGINE_LOG_PATH:
            return

    handler = JsonLineFileHandler(ENGINE_LOG_PATH)
    handler.setLevel(logging.DEBUG)
    root.addHandler(handler)
