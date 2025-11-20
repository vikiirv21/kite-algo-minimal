"""
Analyze paper trading performance based on artifacts.

Reads:
- artifacts/analytics/runtime_metrics.json (canonical source)
- Falls back to computing from orders.csv if needed

Prints:
- portfolio meta (capital, P&L, equity, notional)
- per-symbol stats from metrics
- overall performance metrics

Usage:
    python -m scripts.analyze_performance
"""

from __future__ import annotations

if __name__ == "__main__" and __package__ is None:
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).resolve().parents[1]))

import json
from pathlib import Path
from analytics.performance_v2 import update_runtime_metrics


# Paths
BASE_DIR = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = BASE_DIR / "artifacts"
ANALYTICS_DIR = ARTIFACTS_DIR / "analytics"
RUNTIME_METRICS_PATH = ANALYTICS_DIR / "runtime_metrics.json"
ORDERS_PATH = ARTIFACTS_DIR / "orders.csv"
CHECKPOINTS_DIR = ARTIFACTS_DIR / "checkpoints"
STATE_PATH = CHECKPOINTS_DIR / "paper_state_latest.json"


def _fmt_pnl(x: float) -> str:
    return f"{x:,.2f}"


def _fmt_pct(x: float) -> str:
    return f"{x:.2f}%"


def load_runtime_metrics() -> dict | None:
    """Load metrics from runtime_metrics.json."""
    if not RUNTIME_METRICS_PATH.exists():
        return None
    try:
        with RUNTIME_METRICS_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️  Failed to load runtime metrics: {e}")
        return None


def main() -> None:
    print("=== Performance Summary (from runtime_metrics.json) ===\n")
    
    # Try to load existing runtime metrics
    metrics = load_runtime_metrics()
    
    # If missing or invalid, compute from orders
    if metrics is None:
        print("ℹ️  Runtime metrics not found. Computing from orders.csv...")
        try:
            # Default starting capital (can be read from config if needed)
            starting_capital = 500_000.0
            
            # Update runtime metrics (creates the file)
            metrics = update_runtime_metrics(
                orders_path=ORDERS_PATH,
                state_path=STATE_PATH if STATE_PATH.exists() else None,
                starting_capital=starting_capital,
                output_path=RUNTIME_METRICS_PATH,
            )
            print(f"✓ Runtime metrics computed and saved to {RUNTIME_METRICS_PATH}")
        except Exception as e:
            print(f"❌ Failed to compute metrics: {e}")
            print("\nNo data available. Run an engine first to generate orders.")
            return
    
    # Extract metrics
    equity = metrics.get("equity", {})
    overall = metrics.get("overall", {})
    per_symbol = metrics.get("per_symbol", {})
    per_strategy = metrics.get("per_strategy", {})
    
    # Print equity summary
    print(f"As of               : {metrics.get('asof', 'N/A')}")
    print(f"Mode                : {metrics.get('mode', 'paper')}")
    print(f"Starting Capital    : {_fmt_pnl(equity.get('starting_capital', 0.0))}")
    print(f"Current Equity      : {_fmt_pnl(equity.get('current_equity', 0.0))}")
    print(f"Realized PnL        : {_fmt_pnl(equity.get('realized_pnl', 0.0))}")
    print(f"Unrealized PnL      : {_fmt_pnl(equity.get('unrealized_pnl', 0.0))}")
    print(f"Total Notional      : {_fmt_pnl(equity.get('total_notional', 0.0))}")
    print(f"Max Drawdown        : {_fmt_pnl(equity.get('max_drawdown', 0.0))}")
    print()
    
    # Print overall performance
    print("Overall Performance:")
    print(f"  Total Trades      : {overall.get('total_trades', 0)}")
    print(f"  Win Trades        : {overall.get('win_trades', 0)}")
    print(f"  Loss Trades       : {overall.get('loss_trades', 0)}")
    print(f"  Win Rate          : {_fmt_pct(overall.get('win_rate', 0.0))}")
    print(f"  Gross Profit      : {_fmt_pnl(overall.get('gross_profit', 0.0))}")
    print(f"  Gross Loss        : {_fmt_pnl(overall.get('gross_loss', 0.0))}")
    print(f"  Net PnL           : {_fmt_pnl(overall.get('net_pnl', 0.0))}")
    print(f"  Profit Factor     : {overall.get('profit_factor', 0.0):.2f}")
    print(f"  Avg Win           : {_fmt_pnl(overall.get('avg_win', 0.0))}")
    print(f"  Avg Loss          : {_fmt_pnl(overall.get('avg_loss', 0.0))}")
    print(f"  Biggest Win       : {_fmt_pnl(overall.get('biggest_win', 0.0))}")
    print(f"  Biggest Loss      : {_fmt_pnl(overall.get('biggest_loss', 0.0))}")
    print()
    
    # Print per-symbol stats
    if per_symbol:
        print("Per-Symbol Performance:")
        print(f"{'Symbol':20} {'Trades':>8} {'Win%':>8} {'Net PnL':>15} {'PF':>8}")
        print("-" * 70)
        for symbol, stats in sorted(per_symbol.items()):
            trades = stats.get("trades", 0)
            win_rate = stats.get("win_rate", 0.0)
            net_pnl = stats.get("net_pnl", 0.0)
            pf = stats.get("profit_factor", 0.0)
            print(f"{symbol:20} {trades:8d} {win_rate:7.1f}% {net_pnl:15.2f} {pf:7.2f}")
    else:
        print("  (No per-symbol data available)")
    print()
    
    # Print per-strategy stats
    if per_strategy:
        print("Per-Strategy Performance:")
        print(f"{'Strategy':20} {'Trades':>8} {'Win%':>8} {'Net PnL':>15} {'PF':>8}")
        print("-" * 70)
        for strategy, stats in sorted(per_strategy.items()):
            trades = stats.get("trades", 0)
            win_rate = stats.get("win_rate", 0.0)
            net_pnl = stats.get("net_pnl", 0.0)
            pf = stats.get("profit_factor", 0.0)
            print(f"{strategy:20} {trades:8d} {win_rate:7.1f}% {net_pnl:15.2f} {pf:7.2f}")
    else:
        print("  (No per-strategy data available)")


if __name__ == "__main__":
    main()
