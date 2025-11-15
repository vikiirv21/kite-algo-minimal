from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class _MRState:
    prices: List[float] = field(default_factory=list)


class MeanReversionIntradayStrategy:
    name = "MEAN_REVERT"
    timeframe = "15m"
    mode = "CONTEXT"
    """
    Simple intraday mean-reversion strategy used in SHADOW mode.

    Idea:
        - Maintain a rolling series of closes per symbol.
        - Compute an EMA over the last `ema_len` prices.
        - Measure deviation = (close - ema) / ema.
        - If price is sufficiently ABOVE the EMA band -> SELL (expect reversion down).
        - If price is sufficiently BELOW the EMA band -> BUY (expect reversion up).
        - Otherwise -> HOLD.

    This strategy does NOT place trades directly. Engines use it in shadow mode,
    recording its signals for analytics and future adaptive logic.
    """

    def __init__(
        self,
        ema_len: int = 20,
        band_pct: float = 0.003,  # 0.3% band
        max_history: int = 300,
        timeframe: str | None = None,
    ) -> None:
        self.ema_len = ema_len
        self.band_pct = band_pct
        self.max_history = max_history
        self.name = self.__class__.name
        self.mode = self.__class__.mode
        self.timeframe = timeframe or self.__class__.timeframe

        self._state: Dict[str, _MRState] = {}

    def on_bar(self, symbol: str, bar: Dict[str, float]) -> str:
        close = float(bar.get("close", 0.0))
        if close <= 0:
            return "HOLD"

        st = self._state.setdefault(symbol, _MRState())
        st.prices.append(close)

        # cap history
        if len(st.prices) > self.max_history:
            st.prices = st.prices[-self.max_history :]

        if len(st.prices) < self.ema_len:
            return "HOLD"

        ema = self._ema(st.prices, self.ema_len)
        if ema <= 0:
            return "HOLD"

        deviation = (close - ema) / ema

        if deviation >= self.band_pct:
            return "SELL"
        if deviation <= -self.band_pct:
            return "BUY"
        return "HOLD"

    def _ema(self, series: List[float], length: int) -> float:
        if length <= 1:
            return series[-1]

        window = series[-length:]
        alpha = 2.0 / (length + 1.0)

        ema = window[0]
        for v in window[1:]:
            ema = alpha * v + (1.0 - alpha) * ema
        return ema
