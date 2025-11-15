from __future__ import annotations

from typing import Any, Dict, Tuple

MIN_ATR_PCT = 0.0008  # 0.08% of price
MIN_VOL_SPIKE_RATIO = 1.15
MIN_AVG_VOLUME = 5_000.0
NEUTRAL_RSI_BAND = (45.0, 55.0)
MIN_OPTION_PRICE = 20.0


def should_trade_trend(
    logical: str,
    symbol: str,
    tf: str,
    indicators: Dict[str, Any] | None,
    price: float | None = None,
) -> Tuple[bool, str]:
    """
    Lightweight guard-rail that decides whether a trend signal is tradeable.

    Returns:
        (ok_to_trade, reason)
    """
    indicators = indicators or {}
    atr = float(indicators.get("atr") or 0.0)
    last_price = float(price or indicators.get("close") or 0.0)
    if atr <= 0:
        return False, "atr_unavailable"

    if last_price > 0:
        atr_pct = atr / last_price
        if atr_pct < MIN_ATR_PCT:
            return False, "vol_too_low"
        if "CE" in symbol.upper() or "PE" in symbol.upper():
            if last_price < MIN_OPTION_PRICE:
                return False, "price_too_low"

    avg_vol = float(indicators.get("avg_volume") or 0.0)
    if avg_vol > 0 and avg_vol < MIN_AVG_VOLUME:
        return False, "volume_thin"

    rsi = indicators.get("rsi14")
    if isinstance(rsi, (int, float)):
        low, high = NEUTRAL_RSI_BAND
        if low <= rsi <= high:
            return False, "momentum_neutral"

    ema20 = indicators.get("ema20")
    ema50 = indicators.get("ema50")
    if isinstance(ema20, (int, float)) and isinstance(ema50, (int, float)) and ema50 != 0:
        spread = abs(ema20 - ema50) / abs(ema50)
        if spread < 0.0006:
            return False, "trend_weak"

    vol_spike = indicators.get("vol_spike")
    volume = indicators.get("volume")
    if avg_vol and isinstance(volume, (int, float)):
        if not vol_spike and volume < avg_vol * MIN_VOL_SPIKE_RATIO:
            return False, "dull_volume"

    return True, "trend_confirmed"
