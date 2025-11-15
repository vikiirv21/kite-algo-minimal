from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple


BASE_DIR = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = BASE_DIR / "artifacts"
STATE_PATH = ARTIFACTS_DIR / "paper_state.json"
ORDERS_PATH = ARTIFACTS_DIR / "orders.csv"


@dataclass
class PortfolioMeta:
    timestamp: str
    capital: float
    realized: float
    unrealized: float
    equity: float
    notional: float


@dataclass
class PositionSummary:
    symbol: str
    quantity: int
    avg_price: float
    last_price: float
    realized_pnl: float
    unrealized_pnl: float


@dataclass
class OrderStats:
    symbol: str
    total_orders: int
    buys: int
    sells: int
    total_notional: float
    avg_price: float


def load_state() -> Tuple[PortfolioMeta | None, List[PositionSummary]]:
    if not STATE_PATH.exists():
        return None, []

    with STATE_PATH.open("r", encoding="utf-8") as f:
        data: Dict[str, Any] = json.load(f)

    ts = data.get("timestamp", "")
    meta_raw = data.get("meta", {}) or {}
    broker = data.get("broker", {}) or {}
    positions_raw: List[Dict[str, Any]] = broker.get("positions", []) or []

    cap = float(meta_raw.get("paper_capital", 0.0))
    realized = float(meta_raw.get("total_realized_pnl", 0.0))
    unrealized = float(meta_raw.get("total_unrealized_pnl", 0.0))
    equity = float(meta_raw.get("equity", cap + realized + unrealized))
    notional = float(meta_raw.get("total_notional", 0.0))

    meta = PortfolioMeta(
        timestamp=ts,
        capital=cap,
        realized=realized,
        unrealized=unrealized,
        equity=equity,
        notional=notional,
    )

    positions: List[PositionSummary] = []
    for p in positions_raw:
        symbol = p.get("symbol", "")
        qty = int(p.get("quantity", 0))
        avg = float(p.get("avg_price", 0.0))
        last = float(p.get("last_price", avg))
        rp = float(p.get("realized_pnl", 0.0))
        up = float(p.get("unrealized_pnl", 0.0))
        positions.append(
            PositionSummary(
                symbol=symbol,
                quantity=qty,
                avg_price=avg,
                last_price=last,
                realized_pnl=rp,
                unrealized_pnl=up,
            )
        )

    return meta, positions


def load_order_stats() -> Dict[str, OrderStats]:
    """
    Aggregate order statistics per symbol from orders.csv.

    For each symbol we compute:
    - total_orders
    - buys / sells
    - total_notional (sum price * quantity)
    - avg_price (notional / total_qty)
    """
    if not ORDERS_PATH.exists():
        return {}

    stats: Dict[str, OrderStats] = {}
    with ORDERS_PATH.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            symbol = row.get("symbol", "")
            side = (row.get("side") or "").upper()
            qty = int(float(row.get("quantity", "0") or 0))
            price = float(row.get("price", "0") or 0.0)
            notional = abs(price * qty)

            if symbol not in stats:
                stats[symbol] = OrderStats(
                    symbol=symbol,
                    total_orders=0,
                    buys=0,
                    sells=0,
                    total_notional=0.0,
                    avg_price=0.0,
                )

            s = stats[symbol]
            s.total_orders += 1
            if side == "BUY":
                s.buys += 1
            elif side == "SELL":
                s.sells += 1
            s.total_notional += notional

    # compute average trade price per symbol
    for sym, s in stats.items():
        # We approximate total quantity as total_notional / avg_price,
        # but here we can just divide by number of orders for a rough price
        if s.total_orders > 0:
            s.avg_price = s.total_notional / max(s.total_orders, 1)

    return stats
