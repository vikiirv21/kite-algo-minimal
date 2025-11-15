"""
Analyze strategy-level performance based on orders.csv.

- Reads:
    artifacts/orders.csv

- Computes:
    - Per (symbol, strategy):
        * number of orders
        * total volume
        * total notional
        * realized PnL
        * round trips (full position closures)
    - Aggregated per strategy across all symbols.

Usage:
    python -m scripts.analyze_strategy_performance
"""

from __future__ import annotations

from analytics.strategy_performance import (
    load_strategy_performance,
    aggregate_by_strategy,
)


def _fmt(x: float) -> str:
    return f"{x:,.2f}"


def main() -> None:
    stats_by_key = load_strategy_performance()

    print("=== Strategy Performance (per symbol & strategy) ===")
    if not stats_by_key:
        print("No orders found in artifacts/orders.csv")
    else:
        header = f"{'Symbol':18} {'Strategy':18} {'Orders':>6} {'Volume':>8} {'Notional':>14} {'RealPnL':>12} {'Trips':>6}"
        print(header)
        print("-" * len(header))
        for (symbol, strategy), st in sorted(
            stats_by_key.items(), key=lambda kv: (kv[0][1], kv[0][0])
        ):
            print(
                f"{symbol:18} "
                f"{strategy:18} "
                f"{st.num_orders:6d} "
                f"{st.total_volume:8d} "
                f"{_fmt(st.total_notional):>14} "
                f"{_fmt(st.realized_pnl):>12} "
                f"{st.round_trips:6d}"
            )

    print()
    print("=== Strategy Performance (aggregated by strategy) ===")
    if not stats_by_key:
        print("No data.")
        return

    agg = aggregate_by_strategy(stats_by_key)
    header2 = f"{'Strategy':18} {'Orders':>6} {'Volume':>8} {'Notional':>14} {'RealPnL':>12} {'Trips':>6}"
    print(header2)
    print("-" * len(header2))
    for strategy, st in sorted(agg.items(), key=lambda kv: kv[0]):
        print(
            f"{strategy:18} "
            f"{st.num_orders:6d} "
            f"{st.total_volume:8d} "
            f"{_fmt(st.total_notional):>14} "
            f"{_fmt(st.realized_pnl):>12} "
            f"{st.round_trips:6d}"
        )


if __name__ == "__main__":
    main()
