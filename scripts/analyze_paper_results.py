"""
Basic end-of-day analysis for paper trading results.

Reads:
- artifacts/orders.csv
- artifacts/signals.csv
- artifacts/paper_state.json (for latest P&L snapshot, if present)

Prints:
- Overall order stats (count, BUY/SELL counts).
- Per-symbol order counts.
- If P&L snapshot exists: portfolio meta and realized P&L per symbol.

Usage:
    python -m scripts.analyze_paper_results
"""

import csv
import json
import os
from collections import Counter, defaultdict
from typing import Dict, Any, List


BASE_DIR = os.path.dirname(os.path.dirname(__file__))
ARTIFACTS_DIR = os.path.join(BASE_DIR, "artifacts")
ORDERS_PATH = os.path.join(ARTIFACTS_DIR, "orders.csv")
SIGNALS_PATH = os.path.join(ARTIFACTS_DIR, "signals.csv")
STATE_PATH = os.path.join(ARTIFACTS_DIR, "paper_state.json")


def _load_csv(path: str) -> List[Dict[str, str]]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def _load_state() -> Dict[str, Any]:
    if not os.path.exists(STATE_PATH):
        return {}
    with open(STATE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    orders = _load_csv(ORDERS_PATH)
    signals = _load_csv(SIGNALS_PATH)
    state = _load_state()

    print("=== Paper Trading Analysis ===")
    print(f"Orders file : {ORDERS_PATH}")
    print(f"Signals file: {SIGNALS_PATH}")
    print(f"State file  : {STATE_PATH}")
    print()

    # Orders stats
    print("== Orders ==")
    if not orders:
        print("No orders recorded.")
    else:
        total_orders = len(orders)
        side_counts = Counter(o["side"] for o in orders)
        by_symbol = Counter(o["symbol"] for o in orders)
        print(f"Total orders: {total_orders}")
        print(f"  BUY : {side_counts.get('BUY', 0)}")
        print(f"  SELL: {side_counts.get('SELL', 0)}")
        print("Orders per symbol:")
        for sym, cnt in by_symbol.most_common():
            print(f"  {sym:25} {cnt:3}")
    print()

    # Signals stats
    print("== Signals ==")
    if not signals:
        print("No signals recorded.")
    else:
        total_signals = len(signals)
        sig_counts = Counter(s["signal"] for s in signals)
        print(f"Total signals: {total_signals}")
        for sig, cnt in sig_counts.items():
            print(f"  {sig:5}: {cnt}")

    print()

    # P&L from state snapshot if available
    print("== P&L Snapshot (from paper_state.json, if any) ==")
    if not state:
        print("No paper_state.json found or could not load.")
        return

    meta = state.get("meta", {})
    broker = state.get("broker", {})
    positions = broker.get("positions", [])

    if meta:
        cap = float(meta.get("paper_capital", 0.0))
        tr = float(meta.get("total_realized_pnl", 0.0))
        tu = float(meta.get("total_unrealized_pnl", 0.0))
        eq = float(meta.get("equity", cap + tr + tu))
        tn = float(meta.get("total_notional", 0.0))

        print(f"Capital        : {cap:12.2f}")
        print(f"Realized PnL   : {tr:12.2f}")
        print(f"Unrealized PnL : {tu:12.2f}")
        print(f"Equity         : {eq:12.2f}")
        print(f"Total notional : {tn:12.2f}")
    else:
        print("No meta section present in state snapshot.")

    if positions:
        print()
        print("Per-symbol realized PnL:")
        by_sym_real = defaultdict(float)
        for p in positions:
            sym = p.get("symbol")
            rp = float(p.get("realized_pnl", 0.0))
            by_sym_real[sym] += rp
        for sym, rp in sorted(by_sym_real.items(), key=lambda kv: kv[0]):
            print(f"  {sym:25} {rp:10.2f}")


if __name__ == "__main__":
    main()
