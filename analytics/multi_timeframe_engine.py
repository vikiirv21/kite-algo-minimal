from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


TF_5M = "5m"
TF_15M = "15m"
TF_1H = "1h"
TF_1D = "1d"
TF_1W = "1w"
TF_1M = "1mo"

ALL_TIMEFRAMES: Tuple[str, ...] = (TF_5M, TF_15M, TF_1H, TF_1D, TF_1W, TF_1M)


_TIMEFRAME_SPECS: Dict[str, Dict[str, int]] = {
    TF_5M: {"seconds": 5 * 60, "lookback": 120},
    TF_15M: {"seconds": 15 * 60, "lookback": 120},
    TF_1H: {"seconds": 60 * 60, "lookback": 200},
    TF_1D: {"seconds": 24 * 60 * 60, "lookback": 200},
    TF_1W: {"seconds": 7 * 24 * 60 * 60, "lookback": 260},
    TF_1M: {"seconds": 30 * 24 * 60 * 60, "lookback": 260},
}


BASE_DIR = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = BASE_DIR / "artifacts"
SIGNALS_PATH = ARTIFACTS_DIR / "signals.csv"


@dataclass
class TimeframeSnapshot:
    symbol: str
    timeframe: str
    trend: str
    volatility: float
    structure: str
    momentum_score: float
    mean_revert_score: float


def _parse_timestamp(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class MultiTimeframeEngine:
    """
    Lightweight analytics engine that converts the recorded signal stream into
    multi-timeframe snapshots (trend, volatility, structure, momentum).

    For now we derive price history from artifacts/signals.csv since every engine
    already records logical price samples there. In the future we can plug in
    BrokerDataFeed.get_history or a scanner feed without touching the rest of the stack.
    """

    def __init__(
        self,
        symbols: Iterable[str],
        signals_path: Path | None = None,
        cache_ttl_sec: int = 90,
        max_rows: int = 10_000,
    ) -> None:
        self.symbols = sorted({s.upper() for s in symbols if s})
        self.signals_path = signals_path or SIGNALS_PATH
        self.max_rows = max_rows
        self.cache_ttl = cache_ttl_sec

        self._signal_rows: Dict[str, List[Tuple[datetime, float]]] = {}
        self._signals_mtime: Optional[float] = None

        self._snapshot_cache: Dict[Tuple[str, str], TimeframeSnapshot] = {}
        self._snapshot_cache_ts: Dict[Tuple[str, str], float] = {}

    # ------------------------------------------------------------------ utils
    def _reload_signals(self) -> None:
        path = Path(self.signals_path)
        if not path.exists():
            self._signal_rows = {}
            self._signals_mtime = None
            return

        mtime = path.stat().st_mtime
        if self._signals_mtime is not None and mtime <= self._signals_mtime:
            return

        symbol_rows: Dict[str, List[Tuple[datetime, float]]] = {}
        with path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                symbol = (row.get("symbol") or "").strip().upper()
                if not symbol:
                    continue
                ts_raw = row.get("timestamp") or ""
                price_raw = row.get("price") or row.get("close") or ""
                ts = _parse_timestamp(ts_raw)
                if ts is None:
                    continue
                try:
                    price = float(price_raw)
                except Exception:
                    continue
                if price <= 0:
                    continue
                symbol_rows.setdefault(symbol, []).append((_ensure_utc(ts), price))

        # sort + cap per symbol
        for sym, rows in symbol_rows.items():
            rows.sort(key=lambda x: x[0])
            if len(rows) > self.max_rows:
                symbol_rows[sym] = rows[-self.max_rows :]

        self._signal_rows = symbol_rows
        self._signals_mtime = mtime

    def _get_symbol_rows(self, symbol: str) -> List[Tuple[datetime, float]]:
        self._reload_signals()
        return list(self._signal_rows.get(symbol.upper(), []))

    # ---------------------------------------------------------------- snapshots
    def _bucketize(self, rows: List[Tuple[datetime, float]], timeframe: str) -> List[Tuple[datetime, float]]:
        spec = _TIMEFRAME_SPECS.get(timeframe)
        if not spec or not rows:
            return []

        bucket_seconds = spec["seconds"]
        buckets: Dict[int, float] = {}
        for ts, price in rows:
            ts = _ensure_utc(ts)
            epoch = int(ts.timestamp())
            bucket_start = epoch - (epoch % bucket_seconds)
            buckets[bucket_start] = price  # keep last price per bucket

        items = sorted((datetime.fromtimestamp(b, tz=timezone.utc), p) for b, p in buckets.items())
        lookback = spec.get("lookback", len(items))
        if len(items) > lookback:
            return items[-lookback:]
        return items

    @staticmethod
    def _compute_volatility(closes: List[float]) -> float:
        if len(closes) < 2:
            return 0.0
        mean = sum(closes) / len(closes)
        if mean <= 0:
            return 0.0
        variance = sum((c - mean) ** 2 for c in closes) / (len(closes) - 1)
        return math.sqrt(max(variance, 0.0)) / mean

    @staticmethod
    def _compute_trend(closes: List[float]) -> Tuple[str, float]:
        if len(closes) < 2:
            return "sideways", 0.0
        slope = closes[-1] - closes[0]
        avg_price = sum(closes) / len(closes)
        if avg_price <= 0:
            avg_price = abs(closes[-1]) or 1.0
        normalized = slope / avg_price
        threshold = 0.001
        if normalized > threshold:
            return "up", normalized
        if normalized < -threshold:
            return "down", normalized
        return "sideways", normalized

    @staticmethod
    def _detect_structure(closes: List[float]) -> str:
        if len(closes) < 3:
            return "range"
        last = closes[-1]
        prev = closes[-2]
        prior_high = max(closes[:-1])
        prior_low = min(closes[:-1])
        if last >= prior_high and prev >= prior_low:
            return "HH_HL"
        if last <= prior_low and prev <= prior_high:
            return "LH_LL"
        return "range"

    def _build_snapshot(self, symbol: str, timeframe: str) -> TimeframeSnapshot:
        rows = self._get_symbol_rows(symbol)
        buckets = self._bucketize(rows, timeframe)
        closes = [p for _, p in buckets]

        if not closes:
            return TimeframeSnapshot(
                symbol=symbol,
                timeframe=timeframe,
                trend="sideways",
                volatility=0.0,
                structure="range",
                momentum_score=0.0,
                mean_revert_score=0.0,
            )

        trend, momentum = self._compute_trend(closes)
        volatility = self._compute_volatility(closes)
        structure = self._detect_structure(closes)
        momentum_score = max(-1.0, min(1.0, momentum / (volatility + 1e-6)))
        mean_revert_score = max(0.0, 1.0 - abs(momentum_score))

        return TimeframeSnapshot(
            symbol=symbol,
            timeframe=timeframe,
            trend=trend,
            volatility=volatility,
            structure=structure,
            momentum_score=momentum_score,
            mean_revert_score=mean_revert_score,
        )

    # ---------------------------------------------------------------- public
    def get_snapshot(self, symbol: str, timeframe: str, now_ts: Optional[float] = None) -> TimeframeSnapshot:
        key = (symbol.upper(), timeframe)
        now_ts = now_ts or datetime.utcnow().timestamp()

        cached = self._snapshot_cache.get(key)
        cache_ts = self._snapshot_cache_ts.get(key, 0.0)
        if cached and now_ts - cache_ts <= self.cache_ttl:
            return cached

        snapshot = self._build_snapshot(symbol, timeframe)
        self._snapshot_cache[key] = snapshot
        self._snapshot_cache_ts[key] = now_ts
        return snapshot

    def get_all(self, symbol: str) -> List[TimeframeSnapshot]:
        return [self.get_snapshot(symbol, tf) for tf in ALL_TIMEFRAMES]

    def refresh_symbols(self, symbols: Iterable[str]) -> None:
        for sym in symbols:
            for tf in ALL_TIMEFRAMES:
                key = (sym.upper(), tf)
                self._snapshot_cache.pop(key, None)
                self._snapshot_cache_ts.pop(key, None)
