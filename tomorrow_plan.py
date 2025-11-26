#!/usr/bin/env python
"""
tomorrow_plan.py - Single daily planner for index + equity options using Zerodha Kite.

Usage (from repo root: kite-algo-minimal/):

    python tomorrow_plan.py

Requirements:
    pip install kiteconnect python-dotenv pandas numpy

It expects:
    secrets/kite.env         (KITE_API_KEY, KITE_API_SECRET)
    secrets/kite_tokens.env  (KITE_ACCESS_TOKEN, KITE_LOGIN_TS, optional KITE_PUBLIC_TOKEN)

It ONLY reads data and prints a plan; it does NOT place orders.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Optional, Literal, Tuple, List
from pathlib import Path
import datetime as dt

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from kiteconnect import KiteConnect
from kiteconnect.exceptions import KiteException

# =========================
# CONFIG
# =========================

# Your total Zerodha capital to base risk % on.
# This will be overridden dynamically using Kite funds() if available.
DEFAULT_CAPITAL = 150000.0
RISK_PCT_PER_TRADE = 0.01      # 1% of capital per underlying
SL_PCT_OF_PREMIUM = 0.25       # 25% below entry

# Where secrets live (relative to repo root = this file's parent)
BASE_DIR = Path(__file__).resolve().parent
SECRETS_DIR = BASE_DIR / "secrets"
KITE_ENV = SECRETS_DIR / "kite.env"
TOKENS_ENV = SECRETS_DIR / "kite_tokens.env"

# Cache for instruments
ARTIFACTS_DIR = BASE_DIR / "artifacts"
ARTIFACTS_DIR.mkdir(exist_ok=True)
NSE_CACHE = ARTIFACTS_DIR / "instruments_nse.csv"
NFO_CACHE = ARTIFACTS_DIR / "instruments_nfo.csv"

# How many trading days of history for EMAs/ATR
HISTORY_DAYS = 250

# Universe config
INDEX_UNIVERSE = ["NIFTY", "BANKNIFTY", "FINNIFTY"]

# You can edit this list to add/remove equity F&O underlyings you care about
EQUITY_UNIVERSE = [
    "RELIANCE",
    "HDFCBANK",
    "ICICIBANK",
    "TCS",
]

# Strike step approximations
STRIKE_STEP = {
    "NIFTY": 50,
    "BANKNIFTY": 100,
    "FINNIFTY": 50,
}

TrendBias = Literal["LONG", "SHORT", "NEUTRAL", "NO-TRADE"]


@dataclass
class TrendSignal:
    bias: TrendBias
    reason: str
    close: float
    ema20: float
    ema50: float
    ema100: float
    ema200: float
    atr: float


@dataclass
class OptionCandidate:
    underlying: str          # e.g., NIFTY, BANKNIFTY, RELIANCE
    category: str            # 'INDEX' or 'EQUITY'
    expiry: dt.date
    strike: float
    side: Literal["CE", "PE"]
    trading_symbol: str
    instrument_token: int
    lot_size: int
    ltp: float
    oi: int


@dataclass
class TradePlan:
    underlying: str
    category: str
    trade_date: dt.date
    trend: TrendSignal
    option: Optional[OptionCandidate]
    lots: int
    entry: Optional[float]
    sl: Optional[float]
    target1: Optional[float]
    target2: Optional[float]
    notes: str


# =========================
# Helpers
# =========================

def get_kite() -> KiteConnect:
    if not KITE_ENV.exists() or not TOKENS_ENV.exists():
        raise SystemExit(
            f"Expected secrets in:\n  {KITE_ENV}\n  {TOKENS_ENV}\n"
            "Make sure kite.env and kite_tokens.env exist (same as your HFT login)."
        )

    load_dotenv(KITE_ENV)
    load_dotenv(TOKENS_ENV)

    api_key = os.getenv("KITE_API_KEY")
    api_secret = os.getenv("KITE_API_SECRET")
    access_token = os.getenv("KITE_ACCESS_TOKEN")

    if not api_key or not api_secret:
        raise SystemExit("Missing KITE_API_KEY or KITE_API_SECRET in secrets/kite.env")

    if not access_token:
        raise SystemExit(
            "Missing KITE_ACCESS_TOKEN in secrets/kite_tokens.env\n"
            "Run your existing login flow (e.g., scripts.run_day --login) first."
        )

    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)

    # Sanity check: try a lightweight call
    try:
        _ = kite.margins()
    except KiteException as e:
        raise SystemExit(
            f"Kite access token seems invalid/expired: {e}\n"
            "Run your login flow again to refresh tokens."
        )

    return kite


def load_or_fetch_instruments(kite: KiteConnect) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Load NSE & NFO instruments from cache or fetch from API once per day.
    """
    nse_df = None
    nfo_df = None

    if NSE_CACHE.exists():
        nse_df = pd.read_csv(NSE_CACHE)
    if NFO_CACHE.exists():
        nfo_df = pd.read_csv(NFO_CACHE)

    if nse_df is None:
        print("Fetching instruments for NSE from Kite...")
        nse_list = kite.instruments("NSE")
        nse_df = pd.DataFrame(nse_list)
        nse_df.to_csv(NSE_CACHE, index=False)

    if nfo_df is None:
        print("Fetching instruments for NFO from Kite...")
        nfo_list = kite.instruments("NFO")
        nfo_df = pd.DataFrame(nfo_list)
        nfo_df.to_csv(NFO_CACHE, index=False)

    return nse_df, nfo_df


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def compute_trend_signal(df: pd.DataFrame) -> TrendSignal:
    """
    df: DataFrame with columns: date, open, high, low, close, volume
    """
    close = df["close"]

    df["ema20"] = ema(close, 20)
    df["ema50"] = ema(close, 50)
    df["ema100"] = ema(close, 100)
    df["ema200"] = ema(close, 200)
    df["atr14"] = atr(df, 14)

    last = df.iloc[-1]
    c = float(last["close"])
    e20 = float(last["ema20"])
    e50 = float(last["ema50"])
    e100 = float(last["ema100"])
    e200 = float(last["ema200"])
    a14 = float(last["atr14"])

    if c > e50 > e100 and e20 > e50:
        bias: TrendBias = "LONG"
        reason = "Strong uptrend (close > EMA50 > EMA100 and EMA20 > EMA50)"
    elif c < e50 < e100 and e20 < e50:
        bias = "SHORT"
        reason = "Downtrend (close < EMA50 < EMA100 and EMA20 < EMA50)"
    elif (c > e200 and e50 > e200) or (c < e200 and e50 < e200):
        bias = "NEUTRAL"
        reason = "Directional but short-term EMAs mixed; trade small or skip"
    else:
        bias = "NO-TRADE"
        reason = "Choppy / sideways; EMAs not aligned"

    return TrendSignal(
        bias=bias,
        reason=reason,
        close=c,
        ema20=e20,
        ema50=e50,
        ema100=e100,
        ema200=e200,
        atr=a14,
    )


def get_tomorrow(today: Optional[dt.date] = None) -> dt.date:
    if today is None:
        today = dt.date.today()
    return today + dt.timedelta(days=1)


def strike_step_for_underlying(underlying: str) -> int:
    return STRIKE_STEP.get(underlying, 50)


def round_to_strike(underlying: str, price: float) -> float:
    step = strike_step_for_underlying(underlying)
    return round(price / step) * step


# =========================
# Resolving instruments
# =========================

def resolve_underlying_trend_token_index(
    underlying: str, nfo_df: pd.DataFrame
) -> Optional[int]:
    """
    For indices (NIFTY/BANKNIFTY/FINNIFTY), use front-month FUT as proxy for trend.
    """
    df = nfo_df[
        (nfo_df["name"] == underlying)
        & (nfo_df["segment"] == "NFO-FUT")
        & (nfo_df["instrument_type"] == "FUT")
    ].copy()
    if df.empty:
        return None
    today = dt.date.today()
    df["expiry"] = pd.to_datetime(df["expiry"]).dt.date
    df = df[df["expiry"] >= today].sort_values("expiry")
    if df.empty:
        return None
    return int(df.iloc[0]["instrument_token"])


def resolve_underlying_trend_token_equity(
    symbol: str, nse_df: pd.DataFrame
) -> Optional[int]:
    """
    For equities, use NSE cash symbol as underlying for trend.
    """
    df = nse_df[(nse_df["tradingsymbol"] == symbol) & (nse_df["segment"] == "NSE")]
    if df.empty:
        return None
    return int(df.iloc[0]["instrument_token"])


def fetch_history_for_token(
    kite: KiteConnect, token: int, days: int = HISTORY_DAYS
) -> pd.DataFrame:
    today = dt.date.today()
    from_date = today - dt.timedelta(days=days * 2)  # extra margin for non-trading days
    to_date = today
    data = kite.historical_data(
        instrument_token=token,
        from_date=from_date,
        to_date=to_date,
        interval="day",
    )
    if not data:
        raise RuntimeError(f"No historical data for token {token}")
    df = pd.DataFrame(data)
    # columns: date, open, high, low, close, volume
    return df


def get_option_instruments_for_underlying(
    underlying: str, nfo_df: pd.DataFrame
) -> pd.DataFrame:
    """
    Filter NFO instruments for options for this underlying.
    """
    df = nfo_df[
        (nfo_df["name"] == underlying)
        & (nfo_df["segment"] == "NFO-OPT")
        & (nfo_df["instrument_type"].isin(["CE", "PE"]))
    ].copy()
    if df.empty:
        raise RuntimeError(f"No options found in NFO for {underlying}")
    df["expiry"] = pd.to_datetime(df["expiry"]).dt.date
    return df


def pick_nearest_expiry(
    expiry_dates: List[dt.date], today: dt.date
) -> Optional[dt.date]:
    tomorrow = get_tomorrow(today)
    future = [d for d in expiry_dates if d >= tomorrow]
    if not future:
        return None
    return min(future)


def choose_expiry_for_underlying(
    underlying: str, category: str, opt_df: pd.DataFrame, today: dt.date
) -> dt.date:
    unique_expiries = sorted(opt_df["expiry"].unique())
    if not unique_expiries:
        raise RuntimeError("No expiries found")

    if category == "INDEX":
        # For indices, pick nearest weekly expiry >= tomorrow
        chosen = pick_nearest_expiry(unique_expiries, today)
        if chosen is None:
            chosen = unique_expiries[0]
        return chosen
    else:
        # For equities: nearest (mostly monthly)
        chosen = pick_nearest_expiry(unique_expiries, today)
        if chosen is None:
            chosen = unique_expiries[0]
        return chosen


def build_option_candidates_window(
    underlying: str,
    category: str,
    trend: TrendSignal,
    opt_df: pd.DataFrame,
    expiry: dt.date,
    spot: float,
    side: Literal["CE", "PE"],
    kite: KiteConnect,
) -> List[OptionCandidate]:
    """
    Build a small list of CE/PE candidates around ATM and fetch quote for LTP/OI.
    """
    df = opt_df[(opt_df["expiry"] == expiry) & (opt_df["instrument_type"] == side)]
    if df.empty:
        return []
    
    df = df.copy()  # avoid SettingWithCopyWarning

    # ATM strike
    df["abs_diff"] = (df["strike"].astype(float) - spot).abs()
    atm_row = df.sort_values("abs_diff").iloc[0]
    atm_strike = float(atm_row["strike"])

    step = strike_step_for_underlying(underlying)
    strikes_window = [atm_strike - step, atm_strike, atm_strike + step]

    window_df = df[df["strike"].astype(float).isin(strikes_window)].copy()
    if window_df.empty:
        window_df = df.nsmallest(5, "abs_diff")

    tokens = [int(x) for x in window_df["instrument_token"].tolist()]
    token_to_row = {int(r["instrument_token"]): r for _, r in window_df.iterrows()}

    quotes = {}
    try:
        quotes = kite.quote(tokens)
    except KiteException as e:
        print(f"Quote fetch error for {underlying} {side}: {e}")

    candidates: List[OptionCandidate] = []
    for token in tokens:
        row = token_to_row[token]
        q = quotes.get(str(token)) or quotes.get(token) or {}
        oi = q.get("oi") or 0
        last_price = q.get("last_price") or 0.0

        candidates.append(
            OptionCandidate(
                underlying=underlying,
                category=category,
                expiry=expiry,
                strike=float(row["strike"]),
                side=side,
                trading_symbol=row["tradingsymbol"],
                instrument_token=int(row["instrument_token"]),
                lot_size=int(row["lot_size"]),
                ltp=float(last_price),
                oi=int(oi),
            )
        )

    return candidates


def choose_best_candidate(cands: List[OptionCandidate], spot: float) -> Optional[OptionCandidate]:
    if not cands:
        return None

    # Score = OI rank + closeness-to-ATM rank
    strikes = np.array([c.strike for c in cands], dtype=float)
    ois = np.array([c.oi for c in cands], dtype=float)

    if ois.max() == 0:
        oi_rank = np.zeros_like(ois)
    else:
        oi_rank = ois / ois.max()

    closeness = 1.0 - (np.abs(strikes - spot) / (np.max(np.abs(strikes - spot)) + 1e-6))
    score = oi_rank + 0.5 * closeness

    best_idx = int(np.argmax(score))
    return cands[best_idx]


def compute_position_sizing(
    capital: float,
    risk_pct: float,
    lot_size: int,
    option_price: float,
    sl_pct_of_premium: float,
) -> Tuple[int, float, float, float, float]:
    """
    Size = always 1 lot if option is tradable.
    We still compute SL / T1 / T2 from premium, but ignore capital/risk_pct.
    """
    if option_price <= 0 or lot_size <= 0:
        return 0, 0.0, 0.0, 0.0, 0.0

    entry = option_price
    sl = option_price * (1.0 - sl_pct_of_premium)
    risk_per_unit = max(entry - sl, 0.1)

    # Targets as R-multiples of premium risk
    t1 = entry + risk_per_unit * 1.5
    t2 = entry + risk_per_unit * 2.5

    lots = 1  # <-- always suggest 1 lot; you manage risk & scaling

    return lots, entry, sl, t1, t2


# =========================
# Planner
# =========================

def build_trade_plan(
    underlying: str,
    category: str,
    kite: KiteConnect,
    nse_df: pd.DataFrame,
    nfo_df: pd.DataFrame,
    today: dt.date,
    capital: float,
) -> TradePlan:
    # 1) Resolve underlying token for trend
    if category == "INDEX":
        token = resolve_underlying_trend_token_index(underlying, nfo_df)
    else:
        token = resolve_underlying_trend_token_equity(underlying, nse_df)

    if token is None:
        raise RuntimeError(f"Could not resolve underlying token for {underlying}")

    # 2) Fetch history & compute trend
    hist = fetch_history_for_token(kite, token, HISTORY_DAYS)
    trend = compute_trend_signal(hist)

    spot = trend.close

    notes_parts: List[str] = []

    # If no trade bias, we stop early
    if trend.bias in ("NO-TRADE", "NEUTRAL"):
        notes_parts.append(f"Bias={trend.bias}. {trend.reason}")
        return TradePlan(
            underlying=underlying,
            category=category,
            trade_date=get_tomorrow(today),
            trend=trend,
            option=None,
            lots=0,
            entry=None,
            sl=None,
            target1=None,
            target2=None,
            notes=" ".join(notes_parts),
        )

    side: Literal["CE", "PE"] = "CE" if trend.bias == "LONG" else "PE"

    # 3) Get option instruments and expiries
    opt_df = get_option_instruments_for_underlying(underlying, nfo_df)
    expiry = choose_expiry_for_underlying(underlying, category, opt_df, today)

    # 4) Build candidates and pick best
    candidates = build_option_candidates_window(
        underlying=underlying,
        category=category,
        trend=trend,
        opt_df=opt_df,
        expiry=expiry,
        spot=spot,
        side=side,
        kite=kite,
    )

    best = choose_best_candidate(candidates, spot)

    if best is None:
        notes_parts.append(
            f"Bias={trend.bias}, but no suitable {side} option found around ATM."
        )
        return TradePlan(
            underlying=underlying,
            category=category,
            trade_date=get_tomorrow(today),
            trend=trend,
            option=None,
            lots=0,
            entry=None,
            sl=None,
            target1=None,
            target2=None,
            notes=" ".join(notes_parts),
        )

    # 5) Position sizing
    lots, entry, sl, t1, t2 = compute_position_sizing(
        capital=capital,
        risk_pct=RISK_PCT_PER_TRADE,
        lot_size=best.lot_size,
        option_price=best.ltp,
        sl_pct_of_premium=SL_PCT_OF_PREMIUM,
    )


    return TradePlan(
        underlying=underlying,
        category=category,
        trade_date=get_tomorrow(today),
        trend=trend,
        option=best,
        lots=lots,
        entry=entry if lots > 0 else None,
        sl=sl if lots > 0 else None,
        target1=t1 if lots > 0 else None,
        target2=t2 if lots > 0 else None,
        notes=" ".join(notes_parts),
    )


def pretty_print_plan(plan: TradePlan):
    print(f"[ {plan.underlying} ({plan.category}) ]")

    t = plan.trend
    print(f"  Bias       : {t.bias}")
    print(f"  Structure  : {t.reason}")
    print(
        f"  Spot close : {t.close:.2f} "
        f"(EMA20={t.ema20:.2f}, EMA50={t.ema50:.2f}, "
        f"EMA100={t.ema100:.2f}, EMA200={t.ema200:.2f}, ATR14={t.atr:.2f})"
    )

    if plan.option is None:
        print("  Option     : No trade / no suitable strike.")
        if plan.notes:
            print(f"  Notes      : {plan.notes}")
        print()
        return

    o = plan.option
    print(
        f"  Chosen     : {o.trading_symbol}  ({o.strike:.0f}{o.side}, "
        f"expiry {o.expiry}, lot={o.lot_size})"
    )
    print(
        f"  LTP / OI   : {o.ltp:.2f} / {o.oi:,}"
    )

    if plan.lots <= 0 or plan.entry is None:
        print("  Position   : NO POSITION (risk/price constraints)")
        if plan.notes:
            print(f"  Notes      : {plan.notes}")
        print()
        return

    total_qty = plan.lots * o.lot_size
    approx_notional = plan.lots * o.lot_size * (plan.entry or 0.0)

    print(f"  Position   : {plan.lots} lot(s), qty={total_qty}")
    print(f"  Entry      : {plan.entry:.2f}")
    print(f"  SL (opt)   : {plan.sl:.2f}")
    print(f"  T1 / T2    : {plan.target1:.2f} / {plan.target2:.2f}")
    print(f"  Notional   : ≈ ₹{approx_notional:,.0f}")

    if plan.notes:
        print(f"  Notes      : {plan.notes}")
    print()


def main():
    today = dt.date.today()
    kite = get_kite()
    nse_df, nfo_df = load_or_fetch_instruments(kite)

    # Derive capital from Kite funds if possible
    capital = DEFAULT_CAPITAL
    try:
        funds = kite.margins()["equity"]
        available = funds.get("available", {})
        net = available.get("cash", 0.0)
        if net:
            capital = float(net)
    except Exception:
        pass

    print(f"=== Daily Plan for {get_tomorrow(today)} ===\n")
    print(f"Capital used for sizing: ₹{capital:,.0f}")
    print(f"Risk per underlying    : {RISK_PCT_PER_TRADE*100:.1f}%")
    print(f"SL per trade (option)  : {SL_PCT_OF_PREMIUM*100:.1f}% of premium\n")

    # 1) Index universe
    for idx in INDEX_UNIVERSE:
        try:
            plan = build_trade_plan(
                underlying=idx,
                category="INDEX",
                kite=kite,
                nse_df=nse_df,
                nfo_df=nfo_df,
                today=today,
                capital=capital,
            )
            pretty_print_plan(plan)
        except Exception as e:
            print(f"[ {idx} (INDEX) ] ERROR: {e}\n")

    # 2) Equity universe
    for symbol in EQUITY_UNIVERSE:
        try:
            plan = build_trade_plan(
                underlying=symbol,
                category="EQUITY",
                kite=kite,
                nse_df=nse_df,
                nfo_df=nfo_df,
                today=today,
                capital=capital,
            )
            pretty_print_plan(plan)
        except Exception as e:
            print(f"[ {symbol} (EQUITY) ] ERROR: {e}\n")


if __name__ == "__main__":
    main()
