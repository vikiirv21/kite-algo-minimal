from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Generator, Iterable, List, Optional

from kiteconnect import KiteConnect

from core.kite_http import kite_request
from core.universe_builder import load_universe

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = BASE_DIR / "artifacts"
DEFAULT_CACHE_DIR = ARTIFACTS_DIR / "market_data"

TIMEFRAME_TO_INTERVAL = {
    "1m": "minute",
    "3m": "3minute",
    "5m": "5minute",
    "10m": "10minute",
    "15m": "15minute",
    "30m": "30minute",
    "60m": "60minute",
    "1h": "60minute",
    "day": "day",
    "1d": "day",
}


class MarketDataEngine:
    """
    Candle cache + fetch helper backed by Kite historical/ltp endpoints.
    """

    def __init__(
        self,
        kite_client: Optional[KiteConnect],
        universe: Optional[Dict[str, Any]] = None,
        cache_dir: Optional[Path] = None,
    ) -> None:
        self.kite = kite_client
        self.cache_dir = Path(cache_dir or DEFAULT_CACHE_DIR)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        universe_data = universe or load_universe()
        self.meta = (universe_data.get("meta") or {}) if isinstance(universe_data, dict) else {}
        self._cache: Dict[tuple[str, str], List[Dict[str, Any]]] = {}

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def load_cache(self, symbol: str, timeframe: str) -> List[Dict[str, Any]]:
        key = self._cache_key(symbol, timeframe)
        if key in self._cache:
            return list(self._cache[key])
        path = self._cache_path(symbol, timeframe)
        if not path.exists():
            self._cache[key] = []
            return []
        try:
            candles = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(candles, list):
                normalized = [self._normalize_candle(entry) for entry in candles if isinstance(entry, dict)]
                normalized = [c for c in normalized if c]
                self._cache[key] = normalized
                return list(normalized)
        except json.JSONDecodeError as exc:
            logger.warning("Failed to decode market cache %s: %s", path, exc)
        self._cache[key] = []
        return []

    def save_cache(self, symbol: str, timeframe: str, candles: List[Dict[str, Any]]) -> None:
        key = self._cache_key(symbol, timeframe)
        path = self._cache_path(symbol, timeframe)
        path.parent.mkdir(parents=True, exist_ok=True)
        candles_sorted = sorted(candles, key=lambda c: c.get("ts") or "")
        path.write_text(json.dumps(candles_sorted, indent=2), encoding="utf-8")
        self._cache[key] = candles_sorted

    def fetch_historical(self, symbol: str, timeframe: str, count: int = 200) -> List[Dict[str, Any]]:
        if not self.kite:
            logger.debug("No Kite client; cannot fetch historical for %s/%s", symbol, timeframe)
            return []
        interval = self._map_timeframe(timeframe)
        if not interval:
            logger.warning("Unsupported timeframe=%s; cannot fetch historical.", timeframe)
            return []
        span = self._timeframe_delta(timeframe, count)
        to_dt = datetime.utcnow().replace(tzinfo=timezone.utc)
        from_dt = to_dt - span
        token = self._resolve_token(symbol)
        if token is None:
            logger.warning("No instrument token for %s; historical fetch skipped.", symbol)
            return []
        try:
            candles = kite_request(
                self.kite.historical_data,
                instrument_token=token,
                from_date=from_dt,
                to_date=to_dt,
                interval=interval,
                continuous=False,
                oi=False,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Historical fetch failed for %s/%s: %s", symbol, timeframe, exc)
            return []
        results: List[Dict[str, Any]] = []
        for candle in candles or []:
            entry = self._normalize_candle(candle)
            if entry:
                results.append(entry)
        return results

    def fetch_latest(self, symbol: str, timeframe: str) -> Optional[Dict[str, Any]]:
        candles = self.fetch_historical(symbol, timeframe, count=1)
        return candles[-1] if candles else None

    def update_cache(self, symbol: str, timeframe: str, count: int = 200) -> None:
        symbol = symbol.upper()
        timeframe = timeframe or "1m"
        existing = self.load_cache(symbol, timeframe)
        latest_ts = existing[-1]["ts"] if existing else None
        new_candles = self.fetch_historical(symbol, timeframe, count=count)
        if not new_candles:
            return
        merged: Dict[str, Dict[str, Any]] = {entry["ts"]: entry for entry in existing if entry.get("ts")}
        for candle in new_candles:
            merged[candle["ts"]] = candle
        merged_list = sorted(merged.values(), key=lambda c: c["ts"])
        self.save_cache(symbol, timeframe, merged_list)

    def get_latest_candle(self, symbol: str, timeframe: str) -> Optional[Dict[str, Any]]:
        cache = self.load_cache(symbol, timeframe)
        if cache:
            return cache[-1]
        # cache empty -> attempt fetch
        latest = self.fetch_latest(symbol, timeframe)
        if latest:
            self.save_cache(symbol, timeframe, [latest])
        return latest

    def get_window(self, symbol: str, timeframe: str, window_size: int) -> List[Dict[str, Any]]:
        cache = self.load_cache(symbol, timeframe)
        if not cache:
            self.update_cache(symbol, timeframe, count=max(window_size, 200))
            cache = self.load_cache(symbol, timeframe)
        return cache[-window_size:]

    def replay(
        self,
        symbol: str,
        timeframe: str,
        start_ts: str,
        end_ts: Optional[str] = None,
    ) -> Generator[Dict[str, Any], None, None]:
        cache = self.load_cache(symbol, timeframe)
        if not cache:
            self.update_cache(symbol, timeframe, count=500)
            cache = self.load_cache(symbol, timeframe)
        start = self._parse_ts(start_ts)
        end = self._parse_ts(end_ts) if end_ts else None
        for candle in cache:
            ts = self._parse_ts(candle.get("ts"))
            if ts is None:
                continue
            if start and ts < start:
                continue
            if end and ts > end:
                break
            yield candle

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _cache_key(self, symbol: str, timeframe: str) -> tuple[str, str]:
        return (symbol.upper(), timeframe or "1m")

    def _cache_path(self, symbol: str, timeframe: str) -> Path:
        safe_symbol = symbol.replace(":", "_").replace("/", "_").upper()
        safe_tf = (timeframe or "1m").replace(" ", "").lower()
        return self.cache_dir / f"{safe_symbol}_{safe_tf}.json"

    def _normalize_candle(self, candle: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(candle, dict):
            return None
        ts = candle.get("ts") or candle.get("timestamp") or candle.get("date")
        if isinstance(ts, datetime):
            ts_iso = ts.replace(tzinfo=timezone.utc).isoformat()
        else:
            ts_iso = str(ts)
        try:
            entry = {
                "ts": ts_iso,
                "open": float(candle.get("open", 0.0)),
                "high": float(candle.get("high", 0.0)),
                "low": float(candle.get("low", 0.0)),
                "close": float(candle.get("close", 0.0)),
                "volume": float(candle.get("volume", 0.0)),
            }
        except (TypeError, ValueError):
            return None
        return entry

    def _map_timeframe(self, timeframe: str) -> Optional[str]:
        tf = (timeframe or "1m").lower()
        return TIMEFRAME_TO_INTERVAL.get(tf, TIMEFRAME_TO_INTERVAL.get(f"{tf}"))

    def _timeframe_delta(self, timeframe: str, count: int) -> timedelta:
        tf = (timeframe or "1m").lower()
        if tf.endswith("m"):
            minutes = int(tf.rstrip("m") or "1")
            return timedelta(minutes=minutes * max(1, count))
        if tf.endswith("h"):
            hours = int(tf.rstrip("h") or "1")
            return timedelta(hours=hours * max(1, count))
        if tf in {"day", "1d"}:
            return timedelta(days=max(1, count))
        return timedelta(minutes=max(1, count))

    def _resolve_token(self, symbol: str) -> Optional[int]:
        meta_entry = self.meta.get(symbol.upper())
        if isinstance(meta_entry, dict):
            token = meta_entry.get("token")
            if token is not None:
                return int(token)
        # fallback: try to match by tradingsymbol field
        for entry in self.meta.values():
            if isinstance(entry, dict) and entry.get("tradingsymbol", "").upper() == symbol.upper():
                token = entry.get("token")
                if token is not None:
                    return int(token)
        return None

    @staticmethod
    def _parse_ts(value: Any) -> Optional[datetime]:
        if value in (None, ""):
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
