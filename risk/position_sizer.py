from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict


@dataclass
class PortfolioState:
    capital: float = 0.0
    equity: float = 0.0
    total_notional: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    free_notional: float = 0.0
    open_positions: int = 0
    positions: Dict[str, int] = field(default_factory=dict)

    @property
    def day_pnl(self) -> float:
        return self.realized_pnl + self.unrealized_pnl

    @property
    def day_pnl_pct(self) -> float:
        base = self.capital or (self.equity - self.day_pnl) or self.equity
        if base <= 0:
            return 0.0
        return self.day_pnl / base


@dataclass
class SizerConfig:
    max_exposure_pct: float = 2.0
    risk_per_trade_pct: float = 0.005
    min_order_notional: float = 5000.0
    max_order_notional_pct: float = 0.2
    max_trades: int = 10
    risk_scale_min: float = 0.3
    risk_scale_max: float = 2.0
    risk_down_threshold: float = -0.02
    risk_up_threshold: float = 0.02


class DynamicPositionSizer:
    def __init__(self, config: SizerConfig | None = None) -> None:
        self.config = config or SizerConfig()

    def _risk_scale(self, day_pnl_pct: float) -> float:
        """
        Scale size between risk_scale_min and risk_scale_max depending on daily PnL%.
        Losses push size towards the min, profits allow scaling towards the max.
        """
        if day_pnl_pct is None:
            return 1.0

        low = self.config.risk_down_threshold
        high = self.config.risk_up_threshold
        if high <= low:
            return 1.0

        pct = max(low, min(high, day_pnl_pct))
        span = high - low
        normalized = (pct - low) / span
        return self.config.risk_scale_min + normalized * (self.config.risk_scale_max - self.config.risk_scale_min)

    def size_order(
        self,
        state: PortfolioState,
        symbol: str,
        last_price: float,
        side: str,
        lot_size: int = 1,
    ) -> int:
        """
        Return signed quantity (positive=BUY, negative=SELL). 0 means skip.
        """
        if last_price <= 0 or state.equity <= 0:
            return 0

        lot_size = max(1, int(lot_size))
        unit_notional = last_price * lot_size
        if unit_notional <= 0:
            return 0

        gross_limit = state.equity * self.config.max_exposure_pct
        free_notional = state.free_notional if state.free_notional > 0 else max(0.0, gross_limit - state.total_notional)
        if free_notional < self.config.min_order_notional:
            return 0

        already_open = abs(state.positions.get(symbol, 0)) > 0
        if not already_open and state.open_positions >= self.config.max_trades:
            return 0

        per_trade_notional = max(self.config.min_order_notional, state.equity * self.config.risk_per_trade_pct)
        scaled_notional = per_trade_notional * self._risk_scale(state.day_pnl_pct)

        order_notional_cap = self.config.max_order_notional_pct * state.equity
        if order_notional_cap <= 0:
            order_notional_cap = scaled_notional

        target_notional = min(scaled_notional, free_notional, order_notional_cap)
        if target_notional <= 0:
            return 0

        lots = int(target_notional // unit_notional)
        if lots <= 0:
            return 0

        quantity = lots * lot_size
        if side.upper() == "SELL":
            quantity = -quantity
        return quantity


def load_portfolio_state(
    state_path: Path,
    capital: float,
    fallback_meta: Dict[str, Any],
    fallback_positions: Dict[str, int],
    config: SizerConfig,
) -> PortfolioState:
    """
    Load PortfolioState from artifacts/paper_state.json if available, else fall back to in-memory meta.
    """
    payload: Dict[str, Any] = {}
    if state_path.exists():
        try:
            with state_path.open("r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception:
            payload = {}

    meta = payload.get("meta") or fallback_meta or {}
    broker = payload.get("broker") or {}
    positions_raw = broker.get("positions") or []

    positions: Dict[str, int] = {}
    for pos in positions_raw:
        symbol = pos.get("symbol")
        if not symbol:
            continue
        positions[symbol] = int(pos.get("quantity", 0) or 0)

    if not positions:
        positions = fallback_positions

    equity = float(meta.get("equity", fallback_meta.get("equity", capital)))
    realized = float(meta.get("total_realized_pnl", fallback_meta.get("total_realized_pnl", 0.0)))
    unrealized = float(meta.get("total_unrealized_pnl", fallback_meta.get("total_unrealized_pnl", 0.0)))
    total_notional = float(meta.get("total_notional", fallback_meta.get("total_notional", 0.0)))

    free_notional = meta.get("free_notional")
    if free_notional is None:
        free_notional = max(0.0, equity * config.max_exposure_pct - total_notional)
    else:
        free_notional = float(free_notional)

    open_positions = sum(1 for qty in positions.values() if qty != 0)

    return PortfolioState(
        capital=float(capital),
        equity=equity,
        total_notional=total_notional,
        realized_pnl=realized,
        unrealized_pnl=unrealized,
        free_notional=free_notional,
        open_positions=open_positions,
        positions=positions,
    )
