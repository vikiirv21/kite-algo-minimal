from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

import logging
import math
import pandas as pd

from .base import Decision

log = logging.getLogger(__name__)


@dataclass
class _SymbolState:
    prices: List[float] = field(default_factory=list)
    bars: List[Dict[str, float]] = field(default_factory=list)
    up_trend: bool = False
    down_trend: bool = False
    indicators: Dict[str, Any] = field(default_factory=dict)
    regime: str = "UNKNOWN"


class FnoIntradayTrendStrategy:
    name = "EMA_TREND"
    timeframe = "5m"
    mode = "SCALP"
    """
    Multi-timeframe EMA trend strategy used for all books (FUT, OPT, EQ).

    Idea:
        - Maintain a rolling series of closes per symbol.
        - Approximate two "timeframes" using EMAs:
            * Short timeframe: ema_fast (9), ema_slow (21)
            * Higher timeframe: ema_fast_htf (21), ema_slow_htf (55)
        - Define trend alignment:
            up_trend   = ema_fast > ema_slow and ema_fast_htf > ema_slow_htf
            down_trend = ema_fast < ema_slow and ema_fast_htf < ema_slow_htf

        - Emit signals only on transitions:
            * if was NOT in up_trend and now in up_trend   -> BUY
            * elif was NOT in down_trend and now in down_trend -> SELL
            * else -> HOLD

    Notes:
        - Engines call on_bar(symbol, {"close": price}) on a steady cadence (every few seconds).
        - We treat each call as one "sample" in time.
        - EMAs are computed over sample counts, not real minutes, but with consistent cadence
          this still gives a good notion of "short" vs "long" trend.
    """

    def __init__(
        self,
        fast_len: int = 9,
        slow_len: int = 21,
        fast_htf_len: int = 21,
        slow_htf_len: int = 55,
        max_history: int = 400,
        timeframe: str | None = None,
    ) -> None:
        self.fast_len = fast_len
        self.slow_len = slow_len
        self.fast_htf_len = fast_htf_len
        self.slow_htf_len = slow_htf_len
        self.max_history = max_history
        self.name = self.__class__.name
        self.mode = self.__class__.mode
        self.timeframe = timeframe or self.__class__.timeframe

        # the slowest EMA determines warmup length
        self.min_points = max(self.slow_len, self.slow_htf_len)
        self.indicator_min_points = 220

        # symbol -> _SymbolState
        self._state: Dict[str, _SymbolState] = {}

    def on_bar(self, symbol: str, bar: Dict[str, float]) -> Decision:
        """
        Accepts a dict {"close": price} and returns a Decision(Action: BUY/SELL/HOLD).
        """
        # Safely parse close value with robust error handling
        try:
            raw_close = bar.get("close", 0.0)
            if raw_close is None:
                log.debug("Symbol %s: bar['close'] is None, returning HOLD", symbol)
                return Decision(action="HOLD", reason="invalid_price_none", mode=self.mode, confidence=0.0)
            close = float(raw_close)
        except (TypeError, ValueError) as exc:
            log.debug("Symbol %s: invalid bar['close']=%r (%s), returning HOLD", symbol, bar.get("close"), exc)
            return Decision(action="HOLD", reason="invalid_price_conversion", mode=self.mode, confidence=0.0)
        
        if close <= 0:
            return Decision(action="HOLD", reason="invalid_price", mode=self.mode, confidence=0.0)

        st = self._state.setdefault(symbol, _SymbolState())
        st.prices.append(close)
        bar_entry = {
            "open": float(bar.get("open", close)),
            "high": float(bar.get("high", close)),
            "low": float(bar.get("low", close)),
            "close": close,
            "volume": float(bar.get("volume", 0.0)),
        }
        st.bars.append(bar_entry)

        # cap history length
        if len(st.prices) > self.max_history:
            st.prices = st.prices[-self.max_history :]
        if len(st.bars) > self.max_history:
            st.bars = st.bars[-self.max_history :]

        if len(st.prices) < self.min_points:
            # not enough data to form reliable trend
            return Decision(action="HOLD", reason="warmup", mode=self.mode, confidence=0.0)

        # compute EMAs
        ema_fast = self._ema(st.prices, self.fast_len)
        ema_slow = self._ema(st.prices, self.slow_len)
        ema_fast_htf = self._ema(st.prices, self.fast_htf_len)
        ema_slow_htf = self._ema(st.prices, self.slow_htf_len)

        up_trend = ema_fast > ema_slow and ema_fast_htf > ema_slow_htf
        down_trend = ema_fast < ema_slow and ema_fast_htf < ema_slow_htf

        prev_up = st.up_trend
        prev_down = st.down_trend

        # update stored state
        st.up_trend = up_trend
        st.down_trend = down_trend

        # compute indicators snapshot
        indicators: Dict[str, Any] = {}
        regime = "UNKNOWN"
        if len(st.bars) >= self.indicator_min_points:
            try:
                df = pd.DataFrame(st.bars)
                indicators = compute_indicators(df)
                regime = determine_regime(close, indicators)
            except Exception:
                indicators = {}
                regime = "UNKNOWN"

        st.indicators = indicators
        st.regime = regime

        # Transition-based signals
        if not prev_up and up_trend:
            confidence = self._compute_confidence(ema_fast, ema_slow, ema_fast_htf, ema_slow_htf)
            return Decision(action="BUY", reason="trend_alignment_up", mode=self.mode, confidence=confidence)
        if not prev_down and down_trend:
            confidence = self._compute_confidence(ema_fast, ema_slow, ema_fast_htf, ema_slow_htf)
            return Decision(action="SELL", reason="trend_alignment_down", mode=self.mode, confidence=confidence)

        return Decision(action="HOLD", reason="no_transition", mode=self.mode, confidence=0.0)

    def get_latest_indicators(self, symbol: str) -> Dict[str, Any]:
        st = self._state.get(symbol)
        return st.indicators if st and st.indicators else {}

    def get_latest_regime(self, symbol: str) -> str:
        st = self._state.get(symbol)
        return st.regime if st else "UNKNOWN"

    def _ema(self, series: List[float], length: int) -> float:
        """
        Compute EMA over the last `length` values of series.

        We recompute from scratch over the selected window for simplicity.
        """
        if length <= 1:
            return series[-1]

        window = series[-length:]
        alpha = 2.0 / (length + 1.0)

        ema = window[0]
        for v in window[1:]:
            ema = alpha * v + (1.0 - alpha) * ema
        return ema

    @staticmethod
    def _compute_confidence(ema_fast: float, ema_slow: float, ema_fast_htf: float, ema_slow_htf: float) -> float:
        def _spread(a: float, b: float) -> float:
            denom = abs(b) if b else abs(a)
            denom = denom if denom else 1.0
            return abs(a - b) / denom

        fast_spread = _spread(ema_fast, ema_slow)
        slow_spread = _spread(ema_fast_htf, ema_slow_htf)
        confidence = 0.5 * fast_spread + 0.5 * slow_spread
        return float(max(0.0, min(1.0, confidence)))


def compute_indicators(df: pd.DataFrame) -> Dict[str, Any]:
    if len(df) < 220:
        raise ValueError("insufficient data for indicators")

    close = df["close"]

    ema20 = close.ewm(span=20, adjust=False).mean().iloc[-1]
    ema50 = close.ewm(span=50, adjust=False).mean().iloc[-1]
    ema100 = close.ewm(span=100, adjust=False).mean().iloc[-1]
    ema200 = close.ewm(span=200, adjust=False).mean().iloc[-1]

    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    roll_up = gain.rolling(14).mean()
    roll_down = loss.rolling(14).mean()
    if roll_down.iloc[-1] == 0:
        rsi14 = 100.0
    else:
        rs = roll_up.iloc[-1] / roll_down.iloc[-1]
        rsi14 = 100.0 - (100.0 / (1.0 + rs))

    high = df["high"]
    low = df["low"]
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1]

    vol = float(df["volume"].iloc[-1])
    avg_vol = float(df["volume"].rolling(20).mean().iloc[-1])
    if math.isnan(avg_vol):
        avg_vol = 0.0
    vol_spike = bool(avg_vol and vol > 1.5 * avg_vol)

    def _ensure_float(val: float) -> float:
        if val is None or math.isnan(val):
            raise ValueError("indicator value NaN")
        return float(val)

    return {
        "ema20": _ensure_float(ema20),
        "ema50": _ensure_float(ema50),
        "ema100": _ensure_float(ema100),
        "ema200": _ensure_float(ema200),
        "rsi14": _ensure_float(rsi14),
        "atr": _ensure_float(atr),
        "volume": vol,
        "avg_volume": avg_vol,
        "vol_spike": vol_spike,
    }


def determine_regime(price: float, ind: Dict[str, Any]) -> str:
    ema200 = ind.get("ema200")
    ema50 = ind.get("ema50")
    if not ema200 or math.isnan(ema200):
        return "UNKNOWN"
    threshold = ema200 * 0.002
    if price - ema200 > threshold or (ema50 and ema50 > ema200):
        return "UP_TREND"
    if ema200 - price > threshold or (ema50 and ema50 < ema200):
        return "DOWN_TREND"
    return "RANGE"


def build_reason(price: float, ind: Dict[str, Any], regime: str, signal: str) -> str:
    # Extract indicators with None check
    ema20 = ind.get("ema20")
    ema50 = ind.get("ema50")
    ema100 = ind.get("ema100")
    ema200 = ind.get("ema200")
    
    # Guard: if any critical indicators or price is None, return early with diagnostic info
    if price is None or ema20 is None or ema50 is None or ema100 is None or ema200 is None:
        signal_str = getattr(signal, 'name', str(signal)) if signal is not None else 'None'
        return (
            f"Indicators warming up or missing for detailed reason: "
            f"price={price}, ema20={ema20}, ema50={ema50}, ema100={ema100}, "
            f"ema200={ema200}, regime={regime}, signal={signal_str}"
        )
    
    parts: List[str] = []
    parts.append(f"regime:{regime or 'UNKNOWN'}")

    # Safe fallback for indicators that can be missing
    rsi = ind.get("rsi14", 50.0)

    # Now safe to do chained comparisons - all values guaranteed non-None
    if price > ema20 > ema50:
        parts.append("above_fast_emas")
    elif price < ema20 < ema50:
        parts.append("below_fast_emas")

    if rsi >= 70:
        parts.append("rsi_overbought")
    elif rsi <= 30:
        parts.append("rsi_oversold")

    if ind.get("vol_spike"):
        parts.append("vol_spike")

    # Safe signal formatting
    signal_str = getattr(signal, 'name', str(signal)) if signal is not None else 'HOLD'
    if str(signal_str).upper() == "HOLD":
        parts.append("no_new_edge")

    return "|".join(parts)


def build_risk_side(
    price: float,
    ind: Dict[str, Any],
    capital: float,
    risk_pct_per_trade: float = 0.005,
    side: str = "BUY",
) -> Dict[str, float]:
    atr = float(ind.get("atr") or 0.0)
    if atr <= 0:
        raise ValueError("ATR not available for risk computation")

    sl_distance = 1.5 * atr

    if side.upper() == "BUY":
        stop = price - sl_distance
        target = price + 2.5 * atr
    else:
        stop = price + sl_distance
        target = price - 2.5 * atr

    risk_amount = capital * risk_pct_per_trade
    qty = 0.0
    if sl_distance > 0:
        qty = max(risk_amount / sl_distance, 0.0)

    return {
        "stop": float(round(stop, 2)),
        "trail_stop": float(round(stop, 2)),
        "target": float(round(target, 2)),
        "risk_pct": risk_pct_per_trade * 100.0,
        "implied_qty": float(int(qty)),
    }
