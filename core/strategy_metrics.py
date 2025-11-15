from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from core.state_store import record_strategy_fill


def _classify_position_change(prev_qty: int, new_qty: int) -> Tuple[bool, bool, bool]:
    """
    Determine whether the updated position represents an entry, exit, or both.
    Returns a tuple of (entry_flag, exit_flag, closed_trade_flag).
    """
    prev_sign = 0 if prev_qty == 0 else (1 if prev_qty > 0 else -1)
    new_sign = 0 if new_qty == 0 else (1 if new_qty > 0 else -1)

    if prev_sign == new_sign:
        if new_sign == 0:
            return False, False, False
        if abs(new_qty) > abs(prev_qty):
            return True, False, False
        if abs(new_qty) < abs(prev_qty):
            return False, True, False
        return False, False, False

    entry = new_sign != 0
    exit = prev_sign != 0
    closed = exit and (new_sign == 0 or new_sign != prev_sign)
    return entry, exit, closed


@dataclass
class StrategyMetricsTracker:
    """
    Helper that keeps track of the last strategy_code per symbol and updates
    the shared runtime metrics via record_strategy_fill().
    """

    default_code: Optional[str] = None
    _symbol_codes: Dict[str, str] = field(default_factory=dict)

    def remember(self, symbol: str, strategy_code: Optional[str]) -> None:
        if symbol and strategy_code:
            self._symbol_codes[symbol] = strategy_code

    def infer(self, symbol: str, override: Optional[str] = None) -> Optional[str]:
        if override:
            return override
        if symbol in self._symbol_codes:
            return self._symbol_codes[symbol]
        return self.default_code

    def record_fill(
        self,
        symbol: str,
        *,
        prev_qty: int,
        new_qty: int,
        pnl_delta: float,
        strategy_code: Optional[str] = None,
    ) -> None:
        code = self.infer(symbol, override=strategy_code)
        if not code:
            return
        entry, exit, closed = _classify_position_change(prev_qty, new_qty)
        if not entry and not exit:
            return
        record_strategy_fill(
            code,
            entry=entry,
            exit=exit,
            closed_trade=closed,
            pnl_delta=float(pnl_delta),
        )
        if new_qty == 0:
            self._symbol_codes.pop(symbol, None)
        else:
            self._symbol_codes[symbol] = code
