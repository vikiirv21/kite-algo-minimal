from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PositionState:
    quantity: int = 0
    avg_price: float = 0.0
    realized_pnl: float = 0.0
    last_price: float = 0.0


@dataclass
class OrderRecord:
    ts: str
    symbol: str
    side: str
    quantity: int
    price: float
    strategy: Optional[str] = None
    status: str = "FILLED"


@dataclass
class FillRecord:
    ts: str
    symbol: str
    side: str
    quantity: int
    price: float
    realized_pnl: float
    strategy: Optional[str] = None


@dataclass
class TradeRecord:
    timestamp: str
    symbol: str
    side: str
    qty: int
    entry_price: float
    exit_price: float
    pnl: float
    holding_time: str
    strategy_code: Optional[str] = None


class BacktestBroker:
    """
    Lightweight broker simulator that fills orders at provided prices.
    """

    def __init__(self, starting_cash: float = 0.0) -> None:
        self.starting_cash = starting_cash
        self.cash = starting_cash
        self.positions: Dict[str, PositionState] = {}
        self.orders: List[OrderRecord] = []
        self.fills: List[FillRecord] = []
        self.last_prices: Dict[str, float] = {}
        self.realized_pnl: float = 0.0
        self.equity_curve: List[Dict[str, float]] = []
        self.open_lots: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.trades: List[TradeRecord] = []

    def update_mark(self, symbol: str, price: float) -> None:
        if price is None:
            return
        state = self.positions.get(symbol)
        if state:
            state.last_price = price
        self.last_prices[symbol] = price

    def execute_order(
        self,
        *,
        timestamp: datetime,
        symbol: str,
        side: str,
        quantity: int,
        price: float,
        strategy: Optional[str] = None,
    ) -> FillRecord:
        if quantity <= 0:
            raise ValueError("quantity must be > 0")
        side = side.upper()
        if side not in ("BUY", "SELL"):
            raise ValueError("side must be BUY or SELL")

        state = self.positions.setdefault(symbol, PositionState())
        signed_qty = quantity if side == "BUY" else -quantity
        realized = 0.0

        if state.quantity == 0 or _same_direction(state.quantity, signed_qty):
            total_qty = abs(state.quantity) + abs(signed_qty)
            if total_qty == 0:
                avg_price = price
            else:
                avg_price = (
                    state.avg_price * abs(state.quantity) + price * abs(signed_qty)
                ) / total_qty
            state.avg_price = avg_price
            state.quantity += signed_qty
        else:
            close_qty = min(abs(state.quantity), abs(signed_qty))
            if state.quantity > 0:
                realized = (price - state.avg_price) * close_qty
            else:
                realized = (state.avg_price - price) * close_qty
            state.quantity += signed_qty
            if state.quantity == 0:
                state.avg_price = 0.0

        state.realized_pnl += realized
        state.last_price = price
        self.cash -= signed_qty * price
        self.realized_pnl += realized

        order = OrderRecord(
            ts=timestamp.isoformat(),
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            strategy=strategy,
        )
        self.orders.append(order)
        trade_records = self._process_lots(
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            timestamp=timestamp,
            strategy=strategy,
        )
        self.trades.extend(trade_records)

        fill = FillRecord(
            ts=timestamp.isoformat(),
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            realized_pnl=realized,
            strategy=strategy,
        )
        self.fills.append(fill)
        self._record_equity_point(timestamp)
        return fill

    def positions_snapshot(self) -> List[Dict[str, float]]:
        snapshot: List[Dict[str, float]] = []
        for symbol, state in self.positions.items():
            if state.quantity == 0:
                continue
            last = self.last_prices.get(symbol, state.avg_price)
            unreal = (last - state.avg_price) * state.quantity
            snapshot.append(
                {
                    "symbol": symbol,
                    "quantity": state.quantity,
                    "avg_price": state.avg_price,
                    "last_price": last,
                    "realized_pnl": state.realized_pnl,
                    "unrealized_pnl": unreal,
                }
            )
        return snapshot

    def portfolio_state(self) -> Dict[str, float]:
        return {
            "positions": self.positions_snapshot(),
            "day_pnl": self.realized_pnl,
        }

    def equity_series(self) -> List[Dict[str, float]]:
        return list(self.equity_curve)

    def max_drawdown(self) -> float:
        peak = float("-inf")
        max_dd = 0.0
        for point in self.equity_curve:
            equity = point["equity"]
            peak = max(peak, equity)
            max_dd = max(max_dd, peak - equity)
        return max_dd

    def record_equity_snapshot(self, ts: datetime) -> None:
        self._record_equity_point(ts)

    def _record_equity_point(self, ts: datetime) -> None:
        equity = self.cash
        for symbol, state in self.positions.items():
            last = self.last_prices.get(symbol, state.avg_price)
            equity += state.quantity * last
        self.equity_curve.append({"ts": ts.isoformat(), "equity": equity})

    def _process_lots(
        self,
        *,
        symbol: str,
        side: str,
        quantity: int,
        price: float,
        timestamp: datetime,
        strategy: Optional[str],
    ) -> List[TradeRecord]:
        lots = self.open_lots[symbol]
        incoming_side = "LONG" if side == "BUY" else "SHORT"
        trades: List[TradeRecord] = []
        remaining = quantity

        def _lot_side_to_entry_action(lot_side: str) -> str:
            return "BUY" if lot_side == "LONG" else "SELL"

        while remaining > 0 and lots and lots[0]["side"] != incoming_side:
            lot = lots[0]
            close_qty = min(remaining, lot["qty"])
            pnl = (price - lot["entry_price"]) * close_qty
            if lot["side"] == "SHORT":
                pnl = (lot["entry_price"] - price) * close_qty
            holding = timestamp - lot["entry_ts"]
            trades.append(
                TradeRecord(
                    timestamp=timestamp.isoformat(),
                    symbol=symbol,
                    side=_lot_side_to_entry_action(lot["side"]),
                    qty=close_qty,
                    entry_price=lot["entry_price"],
                    exit_price=price,
                    pnl=pnl,
                    holding_time=str(holding),
                    strategy_code=lot.get("strategy_code") or strategy,
                )
            )
            lot["qty"] -= close_qty
            remaining -= close_qty
            if lot["qty"] <= 0:
                lots.pop(0)

        if remaining > 0:
            lots.append(
                {
                    "side": incoming_side,
                    "qty": remaining,
                    "entry_price": price,
                    "entry_ts": timestamp,
                    "strategy_code": strategy,
                }
            )

        return trades


def _same_direction(current: int, delta: int) -> bool:
    return (current >= 0 and delta >= 0) or (current <= 0 and delta <= 0)
