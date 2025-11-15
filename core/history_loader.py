from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Literal, Optional

import pandas as pd
from kiteconnect import KiteConnect

from core.kite_http import kite_request


BASE_DIR = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = BASE_DIR / "artifacts"
HISTORY_DIR = ARTIFACTS_DIR / "history"
INSTRUMENT_CACHE_FILE = ARTIFACTS_DIR / "instrument_tokens.json"


def _ensure_history_dir() -> None:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)


def _load_instrument_cache() -> Dict[str, int]:
    if not INSTRUMENT_CACHE_FILE.exists():
        return {}
    try:
        with INSTRUMENT_CACHE_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    mapping: Dict[str, int] = {}
    for key, value in data.items():
        try:
            mapping[key.upper()] = int(value)
        except Exception:
            continue
    return mapping


def _save_instrument_cache(mapping: Dict[str, int]) -> None:
    INSTRUMENT_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    serializable = {k: int(v) for k, v in mapping.items()}
    with INSTRUMENT_CACHE_FILE.open("w", encoding="utf-8") as f:
        json.dump(serializable, f, indent=2, sort_keys=True)


def _refresh_instrument_cache(kite: KiteConnect) -> Dict[str, int]:
    exchanges = ("NSE", "BSE", "NFO", "BFO")
    mapping: Dict[str, int] = {}
    for exchange in exchanges:
        try:
            instruments = kite_request(kite.instruments, exchange)
        except Exception:
            continue
        for inst in instruments:
            tradingsymbol = inst.get("tradingsymbol")
            token = inst.get("instrument_token")
            if tradingsymbol and token is not None:
                mapping[tradingsymbol.upper()] = int(token)
    if mapping:
        _save_instrument_cache(mapping)
    return mapping


def _resolve_instrument_token(kite: KiteConnect, symbol: str) -> int:
    symbol_key = symbol.upper()
    cache = _load_instrument_cache()
    token = cache.get(symbol_key)
    if token is not None:
        return token
    cache = _refresh_instrument_cache(kite)
    token = cache.get(symbol_key)
    if token is None:
        raise KeyError(f"Unable to resolve instrument token for {symbol}")
    return token


def _default_history_path(symbol: str, interval: str) -> Path:
    _ensure_history_dir()
    safe_symbol = symbol.replace(":", "_").replace("/", "_").upper()
    safe_interval = interval.replace(" ", "_")
    return HISTORY_DIR / f"{safe_symbol}_{safe_interval}.csv"


def fetch_and_store_history(
    kite: KiteConnect,
    symbol: str,
    interval: str,
    from_dt: datetime,
    to_dt: datetime,
    out_path: Optional[Path] = None,
) -> None:
    """
    Fetch historical candles from Kite and persist them under artifacts/history.
    """
    out_path = out_path or _default_history_path(symbol, interval)
    token = _resolve_instrument_token(kite, symbol)
    candles = kite_request(
        kite.historical_data,
        instrument_token=token,
        from_date=from_dt,
        to_date=to_dt,
        interval=interval,
        continuous=False,
        oi=False,
    )
    if not candles:
        out_path.touch(exist_ok=True)
        return

    rows = []
    for candle in candles:
        ts = candle.get("date")
        timestamp = ts.isoformat() if isinstance(ts, datetime) else str(ts)
        rows.append(
            {
                "timestamp": timestamp,
                "open": float(candle.get("open", 0.0)),
                "high": float(candle.get("high", 0.0)),
                "low": float(candle.get("low", 0.0)),
                "close": float(candle.get("close", 0.0)),
                "volume": float(candle.get("volume", 0.0)),
            }
        )

    df = pd.DataFrame(rows)
    df.sort_values("timestamp", inplace=True)
    df.to_csv(out_path, index=False)


def load_history(symbol: str, interval: str) -> pd.DataFrame:
    """
    Load cached history for the given symbol + interval.
    Returns columns: timestamp, open, high, low, close, volume.
    """
    path = _default_history_path(symbol, interval)
    if not path.exists():
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
    df = pd.read_csv(path)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp"]).copy()
    cols = ["timestamp", "open", "high", "low", "close", "volume"]
    for col in cols:
        if col not in df.columns:
            df[col] = pd.NA
    df = df[cols]
    df.sort_values("timestamp", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def resample_history(df_daily: pd.DataFrame, kind: Literal["1w", "1M"]) -> pd.DataFrame:
    """
    Resample a daily DataFrame into weekly or monthly aggregates (OHLCV).
    """
    if df_daily.empty:
        return df_daily

    df = df_daily.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp"])
    df.set_index("timestamp", inplace=True)

    if kind == "1w":
        period = df.index.to_period("W")
    elif kind == "1M":
        period = df.index.to_period("M")
    else:
        raise ValueError(f"Unsupported resample kind: {kind}")

    agg = df.groupby(period).agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    )
    agg = agg.dropna(subset=["open", "high", "low", "close"])
    agg.index = agg.index.to_timestamp()
    agg = agg.reset_index().rename(columns={"index": "timestamp"})
    return agg
