"""
Analyze paper trading performance based on artifacts.

Reads:
- artifacts/paper_state.json
- artifacts/orders.csv

Prints:
- portfolio meta (capital, P&L, equity, notional)
- per-symbol realized/unrealized PnL
- per-symbol order stats (count, buy/sell, notional, avg trade price)

Usage:
    python -m scripts.analyze_performance
"""

from __future__ import annotations

if __name__ == "__main__" and __package__ is None:
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from analytics.performance import load_state, load_order_stats


def _fmt_pnl(x: float) -> str:
    return f"{x:,.2f}"


def main() -> None:
    meta, positions = load_state()
    order_stats = load_order_stats()

    print("=== Performance Summary (paper) ===")
    if meta is None:
        print("No paper_state.json found. Run an engine first.")
        return

    print(f"Snapshot time     : {meta.timestamp}")
    print(f"Capital           : {_fmt_pnl(meta.capital)}")
    print(f"Realized PnL      : {_fmt_pnl(meta.realized)}")
    print(f"Unrealized PnL    : {_fmt_pnl(meta.unrealized)}")
    print(f"Equity            : {_fmt_pnl(meta.equity)}")
    print(f"Total notional    : {_fmt_pnl(meta.notional)}")
    print()

    print("Per-symbol positions & PnL:")
    if not positions:
        print("  (No open positions in snapshot.)")
    else:
        print(f"{'Symbol':15} {'Qty':>6} {'Avg':>10} {'Last':>10} {'RealPnL':>12} {'UnrealPnL':>12}")
        tot_r = tot_u = 0.0
        for p in positions:
            tot_r += p.realized_pnl
            tot_u += p.unrealized_pnl
            print(
                f"{p.symbol:15} "
                f"{p.quantity:6d} "
                f"{p.avg_price:10.2f} "
                f"{p.last_price:10.2f} "
                f"{p.realized_pnl:12.2f} "
                f"{p.unrealized_pnl:12.2f}"
            )
        print(f"{'-' * 70}")
        print(f"{'TOTAL':15} {'':6} {'':10} {'':10} {_fmt_pnl(tot_r):>12} {_fmt_pnl(tot_u):>12}")
    print()

    print("Per-symbol order stats (from orders.csv):")
    if not order_stats:
        print("  (No orders recorded yet.)")
    else:
        print(f"{'Symbol':15} {'Orders':>6} {'Buys':>6} {'Sells':>6} {'Notional':>14} {'AvgPrice':>10}")
        for sym, s in sorted(order_stats.items()):
            print(
                f"{sym:15} "
                f"{s.total_orders:6d} "
                f"{s.buys:6d} "
                f"{s.sells:6d} "
                f"{s.total_notional:14.2f} "
                f"{s.avg_price:10.2f}"
            )


if __name__ == "__main__":
    main()
