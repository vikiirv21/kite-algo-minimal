from __future__ import annotations

import csv
import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Tuple

logger = logging.getLogger(__name__)


class HistoricalDataSource:
    """
    Abstract interface for replay/backtest data feeds.
    """

    def iter_day(self, symbols: Iterable[str], day: datetime.date) -> Iterator[Tuple[datetime, Dict[str, Dict[str, float]]]]:
        raise NotImplementedError


class LocalCSVHistoricalSource(HistoricalDataSource):
    """
    Simple CSV-based historical data loader.

    Expected file layout:
        data/historical/<symbol>/<YYYY-MM-DD>.csv

    CSV columns (flexible, but these are preferred):
        timestamp (ISO string) | open | high | low | close | volume
    """

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root or Path("data") / "historical")

    def _load_symbol_day(self, symbol: str, day: datetime.date) -> List[Dict[str, float]]:
        path = self.root / symbol.upper() / f"{day.isoformat()}.csv"
        if not path.exists():
            logger.warning("Historical CSV missing for %s on %s (%s)", symbol, day, path)
            return []

        candles: List[Dict[str, float]] = []
        try:
            with path.open("r", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    candle = {
                        "ts": row.get("timestamp") or row.get("ts") or "",
                        "open": _to_float(row.get("open")),
                        "high": _to_float(row.get("high")),
                        "low": _to_float(row.get("low")),
                        "close": _to_float(row.get("close")),
                        "volume": _to_float(row.get("volume")),
                    }
                    candles.append(candle)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to load historical data for %s (%s): %s", symbol, path, exc)
            return []
        return candles

    def iter_day(
        self,
        symbols: Iterable[str],
        day: datetime.date,
    ) -> Iterator[Tuple[datetime, Dict[str, Dict[str, float]]]]:
        timeline: Dict[datetime, Dict[str, Dict[str, float]]] = defaultdict(dict)
        for symbol in symbols:
            for candle in self._load_symbol_day(symbol, day):
                ts = _normalize_ts(candle.get("ts"), day)
                if ts is None:
                    continue
                timeline[ts][symbol] = candle

        for ts in sorted(timeline.keys()):
            yield ts, timeline[ts]


def _to_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _normalize_ts(raw: str | None, fallback_day: datetime.date) -> datetime | None:
    if raw:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%H:%M:%S"):
            try:
                dt = datetime.strptime(raw, fmt)
                if fmt == "%H:%M:%S":
                    return datetime.combine(fallback_day, dt.time())
                return dt
            except ValueError:
                continue
    # If timestamp missing, synthesize chronological ordering by using fallback day midnight increments.
    # None signals caller to skip.
    return None
