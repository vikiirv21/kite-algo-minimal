from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from kiteconnect import KiteTicker, KiteConnect, exceptions as kite_exceptions

from core.history_loader import _resolve_instrument_token  # type: ignore import
from core.kite_env import (
    make_kite_client_from_env,
    print_loaded_paths,
    read_kite_api_secrets,
    read_kite_token,
    token_is_valid,
)
from core.market_session import now_ist
from core.universe import fno_underlyings, load_equity_universe
from data.instruments import resolve_fno_symbols

log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACTS = BASE_DIR / "artifacts"
ARTIFACTS_ROOT = Path(os.environ.get("KITE_ALGO_ARTIFACTS", str(DEFAULT_ARTIFACTS))).expanduser()
if not ARTIFACTS_ROOT.is_absolute():
    ARTIFACTS_ROOT = (BASE_DIR / ARTIFACTS_ROOT).resolve()
QUOTES_PATH = ARTIFACTS_ROOT / "live_quotes.json"

WRITE_INTERVAL_SEC = 1.5


@dataclass(frozen=True)
class SubscriptionEntry:
    logical: str
    tradingsymbol: str
    token: int


class QuoteStore:
    """
    Thread-safe dict of the latest quotes keyed by logical symbol.
    """

    def __init__(self) -> None:
        self._data: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def update(self, logical: str, quote: Dict[str, Any]) -> None:
        with self._lock:
            self._data[logical] = quote

    def snapshot(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return {key: dict(value) for key, value in self._data.items()}


class QuoteWriter:
    """
    Periodically writes the latest quote snapshot to artifacts/live_quotes.json.
    """

    def __init__(self, store: QuoteStore, out_path: Path, interval_sec: float, stop_event: threading.Event) -> None:
        self._store = store
        self._out_path = out_path
        self._interval = max(0.5, interval_sec)
        self._stop = stop_event
        self._thread = threading.Thread(target=self._run, name="quotes-writer", daemon=True)
        self._out_path.parent.mkdir(parents=True, exist_ok=True)

    def start(self) -> None:
        self._thread.start()

    def join(self, timeout: Optional[float] = None) -> None:
        self._thread.join(timeout=timeout)

    def _run(self) -> None:
        # Always write once at start to ensure the dashboard sees a file.
        self._flush_snapshot()
        while not self._stop.wait(self._interval):
            self._flush_snapshot()
        # Final flush after stop.
        self._flush_snapshot()

    def _flush_snapshot(self) -> None:
        snapshot = self._store.snapshot()
        tmp_path = self._out_path.with_suffix(".tmp")
        try:
            with tmp_path.open("w", encoding="utf-8") as handle:
                json.dump(snapshot, handle, indent=2, sort_keys=True)
            os.replace(tmp_path, self._out_path)
            log.debug("Wrote %d quotes to %s", len(snapshot), self._out_path)
        except Exception as exc:  # noqa: BLE001
            log.error("Failed to write quotes file: %s", exc, exc_info=True)
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except Exception:  # noqa: BLE001
                pass


def _float_or_none(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _tick_to_quote(tick: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    last_price = _float_or_none(tick.get("last_price"))
    if last_price is None:
        return None

    ohlc = tick.get("ohlc") or {}
    close = _float_or_none(ohlc.get("close")) or _float_or_none(tick.get("close")) or last_price
    high = _float_or_none(ohlc.get("high"))
    low = _float_or_none(ohlc.get("low"))

    change = last_price - close if close else 0.0
    pchange = (change / close * 100.0) if close else 0.0

    ts_raw = tick.get("last_trade_time") or tick.get("timestamp")
    if isinstance(ts_raw, datetime):
        ts_value = ts_raw.isoformat()
    elif isinstance(ts_raw, str) and ts_raw:
        ts_value = ts_raw
    else:
        ts_value = now_ist().isoformat()

    return {
        "last_price": last_price,
        "change": change,
        "pchange": pchange,
        "high": high,
        "low": low,
        "close": close,
        "timestamp": ts_value,
    }


def _build_fno_entries(kite: KiteConnect) -> List[SubscriptionEntry]:
    logicals = fno_underlyings()
    shim = SimpleNamespace(api=kite)
    resolved = resolve_fno_symbols(logicals, kite_client=shim)

    entries: List[SubscriptionEntry] = []
    for logical in logicals:
        tradingsymbol = resolved.get(logical)
        if not tradingsymbol:
            log.warning("FnO logical %s did not resolve to a tradingsymbol.", logical)
            continue
        try:
            token = _resolve_instrument_token(kite, tradingsymbol)
        except KeyError as exc:
            log.warning("Unable to resolve instrument token for %s (%s): %s", logical, tradingsymbol, exc)
            continue
        entries.append(SubscriptionEntry(logical=logical, tradingsymbol=tradingsymbol, token=token))
    return entries


def _build_equity_entries(kite: KiteConnect) -> List[SubscriptionEntry]:
    entries: List[SubscriptionEntry] = []
    for symbol in load_equity_universe():
        try:
            token = _resolve_instrument_token(kite, symbol)
        except KeyError as exc:
            log.warning("Unable to resolve instrument token for equity %s: %s", symbol, exc)
            continue
        entries.append(SubscriptionEntry(logical=symbol, tradingsymbol=symbol, token=token))
    return entries


def build_subscription_entries(kite: KiteConnect) -> List[SubscriptionEntry]:
    entries = _build_fno_entries(kite)
    entries.extend(_build_equity_entries(kite))

    unique: Dict[int, SubscriptionEntry] = {}
    for entry in entries:
        if entry.token in unique:
            log.debug(
                "Token %s already mapped to %s; skipping duplicate logical %s",
                entry.token,
                unique[entry.token].logical,
                entry.logical,
            )
            continue
        unique[entry.token] = entry

    ordered = sorted(unique.values(), key=lambda e: (e.logical, e.tradingsymbol))
    return ordered


def _run_live_quotes_session(
    kite: KiteConnect,
    api_key: str,
    access_token: str,
    stop_event: Optional[threading.Event] = None,
) -> None:
    if not api_key:
        raise RuntimeError("Kite API key missing. Please configure secrets/kite.env or environment variables.")
    if not access_token:
        raise RuntimeError(
            "Kite access token missing. Run 'python -m scripts.run_day --login --engines all' once to login and store the token."
        )

    log.info("Starting live quotes streamer...")

    entries = build_subscription_entries(kite)
    if not entries:
        raise RuntimeError("No instruments resolved for live quotes subscription.")

    for entry in entries:
        log.info("Subscribe: %s -> %s (token=%s)", entry.logical, entry.tradingsymbol, entry.token)

    token_lookup = {entry.token: entry for entry in entries}
    tokens = list(token_lookup.keys())

    store = QuoteStore()
    local_stop = stop_event or threading.Event()
    writer = QuoteWriter(store, QUOTES_PATH, WRITE_INTERVAL_SEC, local_stop)
    writer.start()

    ticker = KiteTicker(api_key, access_token)

    def handle_ticks(_ws, ticks: List[Dict[str, Any]]) -> None:
        for tick in ticks or []:
            token = tick.get("instrument_token")
            if token not in token_lookup:
                continue
            quote = _tick_to_quote(tick)
            if not quote:
                continue
            logical = token_lookup[token].logical
            store.update(logical, quote)

    def handle_connect(ws, _response) -> None:
        ws.subscribe(tokens)
        ws.set_mode(ws.MODE_FULL, tokens)
        log.info("Subscribed to %d tokens (mode=FULL).", len(tokens))

    def handle_close(_ws, code, reason) -> None:
        log.info("Ticker closed (code=%s reason=%s)", code, reason)
        local_stop.set()

    def handle_error(_ws, code, reason) -> None:
        log.error("Ticker error code=%s reason=%s", code, reason)

    def handle_reconnect(_ws, attempts) -> None:
        log.warning("Ticker reconnecting (attempt=%s).", attempts)

    def handle_noreconnect(_ws) -> None:
        log.error("Ticker gave up reconnecting.")
        local_stop.set()

    ticker.on_ticks = handle_ticks
    ticker.on_connect = handle_connect
    ticker.on_close = handle_close
    ticker.on_error = handle_error
    ticker.on_reconnect = handle_reconnect
    ticker.on_noreconnect = handle_noreconnect

    try:
        ticker.connect(threaded=True)
        log.info("KiteTicker connected. Ctrl+C to exit.")
        while not local_stop.wait(1.0):
            continue
    finally:
        local_stop.set()
        try:
            ticker.close()
        except Exception:  # noqa: BLE001
            pass
        writer.join(timeout=3.0)
        log.info("Live quotes streamer stopped.")


def run_live_quotes_service(stop_event: Optional[threading.Event] = None) -> None:
    """
    Continuously stream quotes, reloading credentials after failures so other terminals can refresh tokens.
    """
    local_stop = stop_event or threading.Event()
    while not local_stop.is_set():
        try:
            secrets = read_kite_api_secrets()
            api_key = secrets.get("KITE_API_KEY")
            access_token = read_kite_token()
            if not api_key or not access_token:
                log.error(
                    "Kite credentials missing (api_key=%s, token=%s). Sleeping before retry.",
                    bool(api_key),
                    bool(access_token),
                )
                time.sleep(30)
                continue

            print_loaded_paths(log)
            kite = make_kite_client_from_env(reload=True)
            if not token_is_valid(kite):
                log.error(
                    "Stored Kite token invalid or expired. Please run: python -m scripts.run_day --login --engines all"
                )
                time.sleep(30)
                continue

            _run_live_quotes_session(kite, api_key, access_token, local_stop)
        except kite_exceptions.TokenException:
            if local_stop.is_set():
                break
            log.error(
                "profile() 401/TokenException – token invalid, please re-login (python -m scripts.run_day --login --engines all)."
            )
            time.sleep(5)
        except KeyboardInterrupt:
            raise
        except Exception as exc:  # noqa: BLE001
            if local_stop.is_set():
                break
            log.exception("Live quotes loop crashed: %s", exc)
            time.sleep(5)

def main() -> None:
    parser = argparse.ArgumentParser(description="Stream live quotes to artifacts/live_quotes.json.")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Log additional diagnostics about credential sources and preflight checks.",
    )
    args = parser.parse_args()

    log_level_name = os.environ.get("LOG_LEVEL")
    if not log_level_name:
        log_level_name = "DEBUG" if args.verbose else "INFO"
    logging.basicConfig(
        level=getattr(logging, log_level_name.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    log.info("Starting live quotes streamer...")
    stop_event = threading.Event()
    try:
        run_live_quotes_service(stop_event=stop_event)
    except KeyboardInterrupt:
        log.info("Interrupted by user, shutting down...")
        stop_event.set()
    except Exception as exc:  # noqa: BLE001
        log.exception("Live quotes streamer failed")
        print(f"Live quotes streamer failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
