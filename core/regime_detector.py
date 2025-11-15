from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Optional


class Regime(str, Enum):
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    CHOP = "CHOP"
    UNKNOWN = "UNKNOWN"


@dataclass
class _SymbolState:
    samples: int = 0
    short_ema: Optional[float] = None
    long_ema: Optional[float] = None
    prev_short_ema: Optional[float] = None
    atr: Optional[float] = None
    prev_close: Optional[float] = None
    last_updated: Optional[datetime] = None
    regime: Regime = Regime.UNKNOWN


class RegimeDetector:
    """
    Lightweight EMA / ATR based regime detector for index-level instruments.

    Keeps running EMAs and ATR per symbol and labels the market as trending
    when the short EMA cleanly pulls away from the long EMA with supporting slope.
    """

    def __init__(
        self,
        *,
        short_window: int = 21,
        long_window: int = 55,
        atr_window: int = 21,
        atr_threshold: float = 0.75,
        primary_symbol: Optional[str] = None,
    ) -> None:
        self.short_window = max(2, short_window)
        self.long_window = max(self.short_window + 1, long_window)
        self.atr_window = max(5, atr_window)
        self.atr_threshold = max(0.1, atr_threshold)
        self._short_alpha = 2.0 / (self.short_window + 1)
        self._long_alpha = 2.0 / (self.long_window + 1)
        self._atr_alpha = 2.0 / (self.atr_window + 1)
        self._state: Dict[str, _SymbolState] = {}
        self.primary_symbol = primary_symbol
        self._min_samples = max(self.short_window, self.long_window, self.atr_window) + 2

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _ema(prev: Optional[float], value: float, alpha: float) -> float:
        if prev is None:
            return value
        return prev + alpha * (value - prev)

    def set_primary_symbol(self, symbol: Optional[str]) -> None:
        if symbol and not self.primary_symbol:
            self.primary_symbol = symbol

    def _state_for(self, symbol: str) -> _SymbolState:
        st = self._state.setdefault(symbol, _SymbolState())
        if not self.primary_symbol:
            self.primary_symbol = symbol
        return st

    def _classify(self, state: _SymbolState) -> Regime:
        if (
            state.samples < self._min_samples
            or state.short_ema is None
            or state.long_ema is None
            or state.atr is None
            or state.atr <= 0
        ):
            return Regime.UNKNOWN

        diff = state.short_ema - state.long_ema
        slope = 0.0 if state.prev_short_ema is None else state.short_ema - state.prev_short_ema
        threshold = max(self.atr_threshold * state.atr, 1e-6)

        if diff > threshold and slope >= 0:
            return Regime.TREND_UP
        if diff < -threshold and slope <= 0:
            return Regime.TREND_DOWN
        return Regime.CHOP

    # ------------------------------------------------------------------- public
    def update(
        self,
        *,
        symbol: str,
        close: float,
        high: Optional[float] = None,
        low: Optional[float] = None,
        timestamp: Optional[datetime] = None,
    ) -> None:
        if not symbol or close is None or close <= 0:
            return

        state = self._state_for(symbol)
        state.samples += 1
        state.prev_short_ema = state.short_ema
        state.short_ema = self._ema(state.short_ema, close, self._short_alpha)
        state.long_ema = self._ema(state.long_ema, close, self._long_alpha)

        # Approximate ATR using high/low if provided, else fall back to close
        prev_close = state.prev_close if state.prev_close is not None else close
        hi = high if high is not None else close
        lo = low if low is not None else close
        tr_components = [abs(hi - lo), abs(hi - prev_close), abs(lo - prev_close)]
        valid_components = [comp for comp in tr_components if comp == comp]
        tr = max(valid_components) if valid_components else abs(close - prev_close)
        state.atr = self._ema(state.atr, tr, self._atr_alpha)

        state.prev_close = close
        state.last_updated = timestamp or datetime.now(timezone.utc)
        state.regime = self._classify(state)

    def current_regime(self, symbol: Optional[str] = None) -> str:
        target = symbol or self.primary_symbol
        if not target:
            return Regime.UNKNOWN.value
        state = self._state.get(target)
        if not state:
            return Regime.UNKNOWN.value
        return state.regime.value

    def snapshot(self) -> Dict[str, Dict[str, Optional[str]]]:
        snap: Dict[str, Dict[str, Optional[str]]] = {}
        for symbol, state in self._state.items():
            snap[symbol] = {
                "regime": state.regime.value,
                "last_updated": state.last_updated.isoformat() if state.last_updated else None,
                "short_ema": state.short_ema,
                "long_ema": state.long_ema,
                "atr": state.atr,
            }
        return snap


shared_regime_detector = RegimeDetector()
