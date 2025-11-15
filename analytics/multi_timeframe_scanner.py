from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

import numpy as np
import pandas as pd

from core.history_loader import load_history, resample_history


TIMEFRAME_CONFIG: Dict[str, Dict[str, object]] = {
    "5m": {"interval": "5minute", "intraday": True, "resample": None},
    "15m": {"interval": "15minute", "intraday": True, "resample": None},
    "1h": {"interval": "60minute", "intraday": False, "resample": None},
    "1d": {"interval": "day", "intraday": False, "resample": None},
    "1w": {"interval": "day", "intraday": False, "resample": "1w"},
    "1M": {"interval": "day", "intraday": False, "resample": "1M"},
}

INTRADAY_TF = {"5m", "15m"}


@dataclass
class IndicatorSnapshot:
    symbol: str
    timeframe: str
    timestamp: pd.Timestamp
    close: float
    ema20: Optional[float]
    ema50: Optional[float]
    ema100: Optional[float]
    ema200: Optional[float]
    rsi14: Optional[float]
    atr14: Optional[float]
    adx14: Optional[float]
    vwap: Optional[float]
    rel_volume: Optional[float]


def _ensure_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp", "close"])
    df.sort_values("timestamp", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False, min_periods=span).mean()


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    return atr


def _adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]

    up_move = high.diff()
    down_move = low.diff() * -1

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr = _atr(df, period=1)
    atr = tr.rolling(window=period, min_periods=period).mean()

    plus_di = 100 * pd.Series(plus_dm).rolling(window=period, min_periods=period).sum() / atr
    minus_di = 100 * pd.Series(minus_dm).rolling(window=period, min_periods=period).sum() / atr

    dx = (abs(plus_di - minus_di) / (plus_di + minus_di)).replace([np.inf, -np.inf], np.nan) * 100
    adx = dx.rolling(window=period, min_periods=period).mean()
    adx.index = df.index
    return adx


def _intraday_vwap(df: pd.DataFrame) -> pd.Series:
    if df.empty or "volume" not in df.columns:
        return pd.Series(index=df.index, dtype=float)
    dates = df["timestamp"].dt.date
    typical_price = (df["high"] + df["low"] + df["close"]) / 3.0
    tpv = typical_price * df["volume"].fillna(0)
    result = pd.Series(index=df.index, dtype=float)
    for current_date in sorted(dates.dropna().unique()):
        mask = dates == current_date
        if mask.sum() == 0:
            continue
        vol = df.loc[mask, "volume"].fillna(0).cumsum()
        tpv_cum = tpv.loc[mask].cumsum()
        with np.errstate(divide="ignore", invalid="ignore"):
            local_vwap = tpv_cum / vol.replace(0, np.nan)
        result.loc[mask] = local_vwap
    return result


def _compute_indicator_frame(df: pd.DataFrame, timeframe: str, intraday: bool) -> pd.DataFrame:
    if df.empty:
        return df

    df = _ensure_dataframe(df)
    if df.empty:
        return df

    df["ema20"] = _ema(df["close"], 20)
    df["ema50"] = _ema(df["close"], 50)
    df["ema100"] = _ema(df["close"], 100)
    df["ema200"] = _ema(df["close"], 200)
    df["rsi14"] = _rsi(df["close"], 14)
    df["atr14"] = _atr(df, 14)
    df["adx14"] = _adx(df, 14)
    if intraday:
        df["vwap"] = _intraday_vwap(df)
    else:
        df["vwap"] = np.nan
    rel_vol = df["volume"].rolling(20, min_periods=5).mean()
    with np.errstate(divide="ignore", invalid="ignore"):
        df["rel_volume"] = df["volume"] / rel_vol
    df["timeframe"] = timeframe
    return df


class MultiTimeframeScanner:
    """
    Builds indicator snapshots for multiple timeframes using cached history.
    """

    def __init__(self, timeframes: Iterable[str] | None = None) -> None:
        if timeframes:
            self.timeframes = [tf for tf in timeframes if tf in TIMEFRAME_CONFIG]
        else:
            self.timeframes = list(TIMEFRAME_CONFIG.keys())

    def _load_df(self, symbol: str, tf: str) -> pd.DataFrame:
        cfg = TIMEFRAME_CONFIG[tf]
        interval = cfg["interval"]
        resample_kind = cfg["resample"]

        base_df = load_history(symbol, interval=str(interval))
        if resample_kind and not base_df.empty:
            base_df = resample_history(base_df, resample_kind)  # type: ignore[arg-type]
        return base_df

    def scan_symbol(self, symbol: str) -> List[IndicatorSnapshot]:
        snapshots: List[IndicatorSnapshot] = []
        daily_df_cache: Optional[pd.DataFrame] = None

        for tf in self.timeframes:
            cfg = TIMEFRAME_CONFIG[tf]
            if cfg.get("resample"):
                if daily_df_cache is None:
                    daily_df_cache = load_history(symbol, "day")
                df_source = daily_df_cache
            else:
                df_source = load_history(symbol, cfg["interval"])  # type: ignore[arg-type]
                if cfg["interval"] == "day":
                    daily_df_cache = df_source

            if df_source.empty:
                continue

            if cfg.get("resample"):
                df = resample_history(df_source, cfg["resample"])  # type: ignore[arg-type]
            else:
                df = df_source

            enriched = _compute_indicator_frame(df, timeframe=tf, intraday=bool(cfg.get("intraday")))
            enriched = enriched.dropna(subset=["close"])
            if enriched.empty:
                continue
            last = enriched.iloc[-1]
            snapshots.append(
                IndicatorSnapshot(
                    symbol=symbol.upper(),
                    timeframe=tf,
                    timestamp=last["timestamp"],
                    close=float(last["close"]),
                    ema20=_safe_float(last.get("ema20")),
                    ema50=_safe_float(last.get("ema50")),
                    ema100=_safe_float(last.get("ema100")),
                    ema200=_safe_float(last.get("ema200")),
                    rsi14=_safe_float(last.get("rsi14")),
                    atr14=_safe_float(last.get("atr14")),
                    adx14=_safe_float(last.get("adx14")),
                    vwap=_safe_float(last.get("vwap")),
                    rel_volume=_safe_float(last.get("rel_volume")),
                )
            )
        return snapshots


def _safe_float(value: object) -> Optional[float]:
    try:
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return None
        return float(value)
    except Exception:
        return None
