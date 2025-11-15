"""
Skeleton for an equity intraday strategy.

For now:
- Placeholder that always returns HOLD.
- Later: implement multi-timeframe filters (e.g., 5m + 15m trend alignment).
"""

from __future__ import annotations

from .base import Signal


class EquityIntradaySimpleStrategy:
    name = "EQ_SIMPLE"
    timeframe = "5m"
    mode = "INTRADAY"

    def __init__(self, timeframe: str | None = None) -> None:
        self.name = self.__class__.name
        self.mode = self.__class__.mode
        self.timeframe = timeframe or self.__class__.timeframe

    def on_bar(self, symbol: str, bar: dict) -> Signal:
        _ = (symbol, bar)
        return "HOLD"
