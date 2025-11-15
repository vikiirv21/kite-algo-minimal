from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = BASE_DIR / "artifacts"
MODE_FILE = ARTIFACTS_DIR / "runtime_mode.json"
VALID_MODES = {"paper", "live"}

_lock = threading.Lock()
_callbacks: List[Callable[[str], None]] = []
_cached_mode: Optional[str] = None


def _ensure_artifacts_dir() -> None:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


def _write_mode(mode: str) -> None:
    _ensure_artifacts_dir()
    payload = {
        "mode": mode,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    MODE_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def get_mode() -> str:
    """
    Return the persisted runtime mode, defaulting to 'paper'.
    """
    global _cached_mode  # noqa: PLW0603
    with _lock:
        if _cached_mode:
            return _cached_mode
        mode = "paper"
        if MODE_FILE.exists():
            try:
                data = json.loads(MODE_FILE.read_text(encoding="utf-8"))
                candidate = str(data.get("mode", "paper")).lower()
                if candidate in VALID_MODES:
                    mode = candidate
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to read %s (%s). Resetting to paper mode.", MODE_FILE, exc)
        _cached_mode = mode
        if not MODE_FILE.exists():
            _write_mode(mode)
        return mode


def set_mode(mode: str) -> str:
    """
    Persist runtime mode and notify change callbacks.
    """
    mode_normalized = str(mode).strip().lower()
    if mode_normalized not in VALID_MODES:
        raise ValueError(f"Unsupported runtime mode '{mode}'. Valid modes: {sorted(VALID_MODES)}")

    global _cached_mode  # noqa: PLW0603
    with _lock:
        current = get_mode()
        if current == mode_normalized:
            logger.debug("Runtime mode already %s; nothing to update.", mode_normalized)
            return current
        _cached_mode = mode_normalized
        _write_mode(mode_normalized)
        callbacks = list(_callbacks)

    for callback in callbacks:
        try:
            callback(mode_normalized)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Runtime mode change callback failed: %s", exc)
    logger.info("Runtime mode switched to %s", mode_normalized)
    return mode_normalized


def on_change(callback: Callable[[str], None]) -> None:
    """
    Register a callback that fires whenever set_mode commits a change.
    """
    with _lock:
        _callbacks.append(callback)
