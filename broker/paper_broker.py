"""
In-memory paper broker.

- Tracks positions and P&L locally.
- Does NOT talk to Kite or place real orders.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional


@dataclass
class PaperPosition:
    symbol: str
    quantity: int = 0
    avg_price: float = 0.0
    realized_pnl: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PaperOrder:
    symbol: str
    side: str           # "BUY" or "SELL"
    quantity: int
    price: float
    status: str = "FILLED"  # for now we assume immediate fill

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PaperBroker:
    positions: Dict[str, PaperPosition] = field(default_factory=dict)
    orders: List[PaperOrder] = field(default_factory=list)

    def place_order(self, symbol: str, side: str, quantity: int, price: float) -> PaperOrder:
        if quantity <= 0:
            raise ValueError("quantity must be > 0")

        side = side.upper()
        if side not in ("BUY", "SELL"):
            raise ValueError("side must be BUY or SELL")

        order = PaperOrder(symbol=symbol, side=side, quantity=quantity, price=price)
        self.orders.append(order)
        self._update_position(order)
        return order

    def _update_position(self, order: PaperOrder) -> None:
        pos = self.positions.get(order.symbol)
        if pos is None:
            pos = PaperPosition(symbol=order.symbol)
            self.positions[order.symbol] = pos

        qty = order.quantity if order.side == "BUY" else -order.quantity

        # Realized P&L when flipping/reducing positions
        if pos.quantity == 0:
            pos.quantity = qty
            pos.avg_price = order.price
            return

        # Same direction averaging
        if (pos.quantity > 0 and qty > 0) or (pos.quantity < 0 and qty < 0):
            total_qty = abs(pos.quantity) + abs(qty)
            pos.avg_price = (pos.avg_price * abs(pos.quantity) + order.price * abs(qty)) / total_qty
            pos.quantity += qty
            return

        # Opposite direction: partial or full exit
        if (pos.quantity > 0 and qty < 0) or (pos.quantity < 0 and qty > 0):
            if abs(qty) < abs(pos.quantity):
                # Partial exit
                pnl_per_unit = (order.price - pos.avg_price) if pos.quantity > 0 else (pos.avg_price - order.price)
                realized = pnl_per_unit * abs(qty)
                pos.realized_pnl += realized
                pos.quantity += qty
            else:
                # Full exit (maybe reverse)
                exit_qty = -pos.quantity
                pnl_per_unit = (order.price - pos.avg_price) if pos.quantity > 0 else (pos.avg_price - order.price)
                realized = pnl_per_unit * abs(exit_qty)
                pos.realized_pnl += realized

                remaining = qty + pos.quantity
                pos.quantity = remaining
                pos.avg_price = order.price if remaining != 0 else 0.0

    def get_position(self, symbol: str) -> PaperPosition | None:
        return self.positions.get(symbol)

    def get_all_positions(self) -> Dict[str, PaperPosition]:
        return self.positions

    def to_state_dict(self, last_prices: Optional[Dict[str, float]] = None) -> dict:
        """
        Serialize current state for analytics / audit / learning.

        If last_prices are provided, also include:

        - last_price per position
        - unrealized_pnl per position
        """
        positions_data: List[dict] = []
        last_prices = last_prices or {}

        for p in self.positions.values():
            d = p.to_dict()
            avg = float(p.avg_price or 0.0)
            qty = float(p.quantity or 0.0)
            last = last_prices.get(p.symbol)
            if last is None:
                last = avg
            last = float(last)
            d["last_price"] = last
            d["unrealized_pnl"] = (last - avg) * qty
            positions_data.append(d)

        return {
            "positions": positions_data,
            "orders": [o.to_dict() for o in self.orders],
        }
