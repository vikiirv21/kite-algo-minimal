"""
Telemetry module for engine health monitoring.

Provides lightweight telemetry reporting for multi-process engine architecture.
Each engine process writes a JSON telemetry file with health status, which
is aggregated by the dashboard API.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

TELEMETRY_DIR = Path("artifacts/telemetry")


def ensure_telemetry_dir() -> None:
    """Ensure the telemetry directory exists."""
    TELEMETRY_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class EngineTelemetry:
    """Telemetry data structure for engine health monitoring."""

    name: str
    mode: str
    pid: int
    status: str  # "starting", "running", "stopped", "error"
    started_at: str
    last_heartbeat: str
    loop_tick: int = 0
    universe_size: int = 0
    open_positions: int = 0
    last_error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


class EngineTelemetryReporter:
    """
    Lightweight helper for engine processes to write JSON telemetry.

    Each engine instance writes to artifacts/telemetry/{name}_engine.json
    with health status updates.
    """

    def __init__(self, name: str, mode: str = "paper"):
        """
        Initialize telemetry reporter.

        Args:
            name: Engine name (e.g., "fno", "equity", "options")
            mode: Trading mode (e.g., "paper", "live")
        """
        ensure_telemetry_dir()
        self.name = name
        self.mode = mode
        self.pid = os.getpid()
        now = datetime.now().isoformat()
        self._data = EngineTelemetry(
            name=name,
            mode=mode,
            pid=self.pid,
            status="starting",
            started_at=now,
            last_heartbeat=now,
        )
        self._path = TELEMETRY_DIR / f"{name}_engine.json"
        self._write()

    def _write(self) -> None:
        """Write telemetry data to JSON file."""
        try:
            with self._path.open("w", encoding="utf-8") as f:
                json.dump(self._data.to_dict(), f)
        except Exception:
            logger.exception("Failed to write telemetry for engine=%s", self.name)

    def heartbeat(
        self,
        loop_tick: Optional[int] = None,
        universe_size: Optional[int] = None,
        open_positions: Optional[int] = None,
        status: Optional[str] = None,
        last_error: Optional[str] = None,
    ) -> None:
        """
        Update telemetry with latest health information.

        Args:
            loop_tick: Current loop iteration count
            universe_size: Number of symbols in trading universe
            open_positions: Number of open positions
            status: Engine status (e.g., "running", "error")
            last_error: Error message if status is "error"
        """
        self._data.last_heartbeat = datetime.now().isoformat()
        if loop_tick is not None:
            self._data.loop_tick = loop_tick
        if universe_size is not None:
            self._data.universe_size = universe_size
        if open_positions is not None:
            self._data.open_positions = open_positions
        if status is not None:
            self._data.status = status
        if last_error is not None:
            self._data.last_error = last_error
        self._write()

    def mark_stopped(self) -> None:
        """Mark engine as stopped."""
        self._data.status = "stopped"
        self._data.last_heartbeat = datetime.now().isoformat()
        self._write()
