from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from threading import Lock
from typing import Dict


@dataclass
class TradeFlowSnapshot:
    date: str
    signals_seen: int = 0
    entries_allowed: int = 0
    entries_blocked_risk: int = 0
    entries_blocked_time: int = 0
    orders_submitted: int = 0
    orders_filled: int = 0

    def to_dict(self) -> Dict:
        return asdict(self)


class TradeMonitor:
    """
    In-memory daily counters. Reset when date changes.
    This is per-process; OK for local lab + dashboard.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._snapshot = self._new_snapshot()

    def _new_snapshot(self) -> TradeFlowSnapshot:
        today = datetime.now().strftime("%Y-%m-%d")
        return TradeFlowSnapshot(date=today)

    def _ensure_today(self) -> None:
        with self._lock:
            today = datetime.now().strftime("%Y-%m-%d")
            if self._snapshot.date != today:
                self._snapshot = self._new_snapshot()

    def increment(self, field: str, value: int = 1) -> None:
        self._ensure_today()
        with self._lock:
            if hasattr(self._snapshot, field):
                setattr(self._snapshot, field, getattr(self._snapshot, field) + value)

    def snapshot(self) -> Dict:
        self._ensure_today()
        with self._lock:
            return self._snapshot.to_dict()


trade_monitor = TradeMonitor()
