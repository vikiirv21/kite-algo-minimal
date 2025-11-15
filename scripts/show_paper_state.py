"""
Inspect paper broker state.

Reads artifacts/paper_state.json and prints:

- timestamp of snapshot
- portfolio meta (capital, notional, realized/unrealized P&L, equity)
- positions (symbol, qty, avg_price, last_price, realized + unrealized P&L)
- simple aggregates

Usage:
    python -m scripts.show_paper_state
"""

import json
import os
from typing import Any, Dict, List


BASE_DIR = os.path.dirname(os.path.dirname(__file__))
STATE_PATH = os.path.join(BASE_DIR, "artifacts", "paper_state.json")


def _load_state() -> Dict[str, Any]:
    if not os.path.exists(STATE_PATH):
        raise FileNotFoundError(f"No paper state snapshot found at {STATE_PATH}. Run the engine first.")
    with open(STATE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    data = _load_state()
    ts = data.get("timestamp")
    broker = data.get("broker", {})
    meta = data.get("meta", {}) or {}

    positions: List[Dict[str, Any]] = broker.get("positions", [])
    orders: List[Dict[str, Any]] = broker.get("orders", [])

    print(f"Paper state snapshot @ {ts}")
    print("=" * 70)

    if meta:
        cap = float(meta.get("paper_capital", 0.0))
        tr = float(meta.get("total_realized_pnl", 0.0))
        tu = float(meta.get("total_unrealized_pnl", 0.0))
        eq = float(meta.get("equity", cap + tr + tu))
        tn = float(meta.get("total_notional", 0.0))

        print("Portfolio meta:")
        print(f"  Capital        : {cap:12.2f}")
        print(f"  Realized PnL   : {tr:12.2f}")
        print(f"  Unrealized PnL : {tu:12.2f}")
        print(f"  Equity         : {eq:12.2f}")
        print(f"  Total notional : {tn:12.2f}")
    else:
        print("No meta info present in snapshot.")

    print("-" * 70)
    if not positions:
        print("No positions.")
    else:
        print("Positions:")
        print(f"{'Symbol':15} {'Qty':>6} {'Avg':>10} {'Last':>10} {'RealPnL':>10} {'UnrealPnL':>10}")
        total_realized = 0.0
        total_unreal = 0.0
        for p in positions:
            symbol = p.get("symbol")
            qty = p.get("quantity")
            avg_price = float(p.get("avg_price", 0.0))
            last_price = float(p.get("last_price", avg_price))
            realized = float(p.get("realized_pnl", 0.0))
            unreal = float(p.get("unrealized_pnl", 0.0))
            total_realized += realized
            total_unreal += unreal
            print(f"{symbol:15} {qty:6} {avg_price:10.2f} {last_price:10.2f} {realized:10.2f} {unreal:10.2f}")
        print("-" * 70)
        print(f"Sum realized PnL   : {total_realized:.2f}")
        print(f"Sum unrealized PnL : {total_unreal:.2f}")

    print()
    print(f"Total orders recorded in snapshot: {len(orders)}")


if __name__ == "__main__":
    main()
