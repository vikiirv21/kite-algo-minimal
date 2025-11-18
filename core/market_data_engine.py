from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Generator, Iterable, List, Optional

from kiteconnect import KiteConnect

from analytics.telemetry_bus import publish_engine_health
from core.kite_http import kite_request
from core.universe_builder import load_universe
from data.instruments import get_instrument_token

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
        enable_telemetry: bool = True,
    ) -> None:
        self.kite = kite_client
        self.cache_dir = Path(cache_dir or DEFAULT_CACHE_DIR)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        universe_data = universe or load_universe()
        self.meta = (universe_data.get("meta") or {}) if isinstance(universe_data, dict) else {}
        self._cache: Dict[tuple[str, str], List[Dict[str, Any]]] = {}
        self._warned_missing_token: set[str] = set()  # Track symbols already warned about
        self._lookup_failures: set[str] = set()  # Track lookup failures for telemetry
        
        # Telemetry support
        self._enable_telemetry = enable_telemetry
        self._telemetry_thread: Optional[threading.Thread] = None
        self._telemetry_stop = threading.Event()
        
        if self._enable_telemetry:
            self._start_telemetry_thread()

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

    def log_token_summary(self) -> None:
        """
        Log a summary of resolved vs missing instrument tokens.
        Useful for debugging token resolution issues.
        """
        resolved_count = len([k for k, v in self.meta.items() if isinstance(v, dict) and v.get("token")])
        missing_count = len(self._warned_missing_token)
        logger.info(
            "MDE tokens: resolved=%d missing=%d (%s)",
            resolved_count,
            missing_count,
            sorted(self._warned_missing_token) if missing_count > 0 else "none"
        )

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
        """
        Resolve instrument token for a symbol.
        
        First tries universe meta, then falls back to instrument lookup.
        Automatically detects exchange based on symbol suffix:
        - Symbols ending with "FUT" -> NFO exchange
        - All other symbols -> NSE exchange
        
        Logs warning only once per missing symbol.
        """
        symbol_upper = symbol.upper()
        
        # Try universe meta first
        meta_entry = self.meta.get(symbol_upper)
        if isinstance(meta_entry, dict):
            token = meta_entry.get("token")
            if token is not None:
                return int(token)
        
        # Fallback: try to match by tradingsymbol field in meta
        for entry in self.meta.values():
            if isinstance(entry, dict) and entry.get("tradingsymbol", "").upper() == symbol_upper:
                token = entry.get("token")
                if token is not None:
                    return int(token)
        
        # Auto-detect exchange based on symbol
        exchange = "NFO" if symbol_upper.endswith("FUT") else "NSE"
        
        # Try resolving from instrument dump
        token = get_instrument_token(exchange, symbol_upper)
        if token is not None:
            # Cache it in meta for future lookups
            if symbol_upper not in self.meta:
                self.meta[symbol_upper] = {"token": token, "tradingsymbol": symbol_upper}
            return int(token)
        
        # Still None? Log warning once
        if symbol_upper not in self._warned_missing_token:
            logger.warning("No instrument token for %s; historical fetch skipped.", symbol_upper)
            self._warned_missing_token.add(symbol_upper)
            self._lookup_failures.add(symbol_upper)
            
            # Publish lookup failure event (once per symbol)
            if self._enable_telemetry:
                from analytics.telemetry_bus import publish_event
                publish_event("mde_lookup_failure", {
                    "symbol": symbol_upper,
                    "exchange_tried": exchange
                })
        
        return None
    
    def _start_telemetry_thread(self) -> None:
        """Start background thread for publishing MDE status."""
        self._telemetry_stop.clear()
        self._telemetry_thread = threading.Thread(
            target=self._telemetry_loop,
            name="mde-telemetry",
            daemon=True
        )
        self._telemetry_thread.start()
        logger.debug("MarketDataEngine telemetry thread started")
    
    def _telemetry_loop(self) -> None:
        """Background loop to publish MDE status every 3 seconds."""
        try:
            while not self._telemetry_stop.wait(3.0):
                self._publish_status()
        except Exception as exc:
            logger.error("MDE telemetry loop error: %s", exc, exc_info=True)
    
    def _publish_status(self) -> None:
        """Publish current MDE status to telemetry bus."""
        try:
            # Get cache statistics
            total_symbols = len(self._cache)
            total_candles = sum(len(candles) for candles in self._cache.values())
            
            # Get stale symbol information (symbols with no recent data)
            stale_symbols = []
            now = datetime.now(timezone.utc)
            for (symbol, timeframe), candles in self._cache.items():
                if candles:
                    last_candle_ts = self._parse_ts(candles[-1].get("ts"))
                    if last_candle_ts:
                        age_minutes = (now - last_candle_ts).total_seconds() / 60
                        # Consider stale if > 60 minutes old
                        if age_minutes > 60:
                            stale_symbols.append({
                                "symbol": symbol,
                                "timeframe": timeframe,
                                "last_update": last_candle_ts.isoformat(),
                                "age_minutes": int(age_minutes)
                            })
            
            # Publish status
            status = {
                "cached_symbols": total_symbols,
                "total_candles": total_candles,
                "meta_entries": len(self.meta),
                "lookup_failures": len(self._lookup_failures),
                "stale_symbols_count": len(stale_symbols),
                "has_kite_client": self.kite is not None,
            }
            
            publish_engine_health(
                engine_name="MarketDataEngine",
                status="active",
                metrics=status
            )
            
            # Publish stale symbols separately if any exist
            if stale_symbols:
                from analytics.telemetry_bus import publish_event
                publish_event("mde_stale_symbols", {
                    "count": len(stale_symbols),
                    "symbols": stale_symbols[:10]  # Limit to first 10 for brevity
                })
        
        except Exception as exc:
            logger.error("Failed to publish MDE status: %s", exc, exc_info=True)
    
    def stop_telemetry(self) -> None:
        """Stop the telemetry thread."""
        if self._telemetry_thread and self._telemetry_thread.is_alive():
            self._telemetry_stop.set()
            self._telemetry_thread.join(timeout=5.0)
            logger.debug("MarketDataEngine telemetry thread stopped")

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
