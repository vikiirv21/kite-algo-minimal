from __future__ import annotations

import inspect
import logging
import os
import sys
from typing import Any, Dict, Literal, Optional

DEFAULT_FORMAT = "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

EventKind = Literal[
    "SIGNAL",
    "ORDER_NEW",
    "ORDER_FILL",
    "STOP_HIT",
    "TP_HIT",
    "RISK_BLOCK",
    "TIME_BLOCK",
    "INFO",
    "WARN",
    "ERROR",
]

_EVENT_COLOR_MAP = {
    "SIGNAL": "\033[36m",       # cyan
    "ORDER_NEW": "\033[35m",    # magenta
    "ORDER_FILL": "\033[32m",   # green
    "STOP_HIT": "\033[31m",     # red
    "TP_HIT": "\033[34m",       # blue
    "RISK_BLOCK": "\033[33m",   # yellow
    "TIME_BLOCK": "\033[33m",
    "INFO": "\033[37m",
    "WARN": "\033[33m",
    "ERROR": "\033[31m",
}
_COLOR_RESET = "\033[0m"


def _stream_supports_color(stream: Any) -> bool:
    if os.getenv("NO_COLOR"):
        return False
    if os.name == "nt":
        return True  # modern Windows terminals support ANSI sequences
    return hasattr(stream, "isatty") and stream.isatty()


class EventLogFormatter(logging.Formatter):
    def __init__(self, *, use_color: bool = False) -> None:
        super().__init__(fmt=DEFAULT_FORMAT, datefmt=DEFAULT_DATE_FORMAT)
        self.use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        line = super().format(record)
        kind = getattr(record, "event_kind", None)
        if not (self.use_color and kind):
            return line
        color = _EVENT_COLOR_MAP.get(str(kind).upper())
        if not color:
            return line
        target = f"[KIND:{kind}]"
        if target not in line:
            return line
        return line.replace(target, f"{color}{target}{_COLOR_RESET}", 1)


def build_stream_handler() -> logging.Handler:
    handler = logging.StreamHandler()
    handler.setFormatter(
        EventLogFormatter(use_color=_stream_supports_color(handler.stream))
    )
    return handler


def _ensure_root_logger_configured() -> None:
    root = logging.getLogger()
    if root.handlers:
        return
    handler = build_stream_handler()
    root.addHandler(handler)
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    root.setLevel(getattr(logging, level_name, logging.INFO))


_ensure_root_logger_configured()


def _resolve_caller_logger_name() -> str:
    frame = inspect.currentframe()
    module_name: Optional[str] = None
    try:
        caller = frame.f_back if frame else None
        while caller:
            module_name = caller.f_globals.get("__name__")
            if module_name and module_name != __name__:
                break
            caller = caller.f_back
    finally:
        del frame
    return module_name or "kite-algo.events"


def log_event(
    kind: EventKind,
    msg: str,
    *,
    symbol: Optional[str] = None,
    strategy_id: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
    level: Optional[int] = None,
) -> None:
    """
    Structured-ish log wrapper used by engine/strategies.

    The dashboard log viewer will color-code based on [KIND:...] prefix.
    """
    logger_name = _resolve_caller_logger_name()
    logger = logging.getLogger(logger_name)

    tags: list[str] = []
    if symbol:
        tags.append(f"sym={symbol}")
    if strategy_id:
        tags.append(f"strategy={strategy_id}")
    if extra:
        parts = []
        for key, value in extra.items():
            parts.append(f"{key}={value}")
        if parts:
            tags.append(",".join(parts))

    suffix = f" | {' | '.join(tags)}" if tags else ""
    line = f"[KIND:{kind}] {msg}{suffix}"

    if level is None:
        if kind in {"WARN", "RISK_BLOCK", "TIME_BLOCK"}:
            level = logging.WARNING
        elif kind in {"ERROR"}:
            level = logging.ERROR
        else:
            level = logging.INFO

    logger.log(
        level,
        line,
        extra={
            "event_kind": kind,
            "event_tags": tags,
        },
    )
