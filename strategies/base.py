from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

Signal = Literal["BUY", "SELL", "EXIT", "HOLD"]


@dataclass
class Decision:
    action: Signal
    reason: str = ""
    mode: str = ""
    confidence: float = 0.0


class BarStrategy(Protocol):
    def on_bar(self, symbol: str, bar: dict) -> Signal | Decision:
        ...
