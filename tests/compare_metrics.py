#!/usr/bin/env python3
"""
Compare portfolio endpoint output with analyze_performance.py output.
"""

import sys
import json
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from analytics.performance import load_state

ARTIFACTS_DIR = Path(__file__).parent.parent / "artifacts"
ANALYTICS_DIR = ARTIFACTS_DIR / "analytics"


def compare_metrics():
    """Compare metrics from different sources."""
    print("=" * 70)
    print("Comparing Metrics from Different Sources")
    print("=" * 70)
    
    # Load from runtime_metrics.json
    metrics_path = ANALYTICS_DIR / "runtime_metrics.json"
    if metrics_path.exists():
        with metrics_path.open("r", encoding="utf-8") as f:
            runtime_metrics = json.load(f)
        
        equity_info = runtime_metrics.get("equity", {})
        print("\n[runtime_metrics.json]")
        print(f"  Starting Capital : {equity_info.get('starting_capital', 0):,.2f}")
        print(f"  Current Equity   : {equity_info.get('current_equity', 0):,.2f}")
        print(f"  Realized PnL     : {equity_info.get('realized_pnl', 0):,.2f}")
        print(f"  Unrealized PnL   : {equity_info.get('unrealized_pnl', 0):,.2f}")
        print(f"  Total Notional   : {equity_info.get('total_notional', 0):,.2f}")
    else:
        print(f"\n❌ runtime_metrics.json not found at {metrics_path}")
        runtime_metrics = None
    
    # Load from analyze_performance.py (using its load_state function)
    try:
        meta, positions = load_state()
        if meta:
            print("\n[analyze_performance.py - load_state()]")
            print(f"  Capital          : {meta.capital:,.2f}")
            print(f"  Equity           : {meta.equity:,.2f}")
            print(f"  Realized PnL     : {meta.realized:,.2f}")
            print(f"  Unrealized PnL   : {meta.unrealized:,.2f}")
            print(f"  Total Notional   : {meta.notional:,.2f}")
            
            if positions:
                print(f"\n  Positions ({len(positions)}):")
                for pos in positions:
                    print(f"    {pos.symbol:20} Qty: {pos.quantity:4d} "
                          f"Realized: {pos.realized_pnl:10.2f} "
                          f"Unrealized: {pos.unrealized_pnl:10.2f}")
        else:
            print("\n[analyze_performance.py] - No state found")
    except Exception as exc:
        print(f"\n❌ analyze_performance.py failed: {exc}")
        meta = None
    
    # Compare if both sources available
    if runtime_metrics and meta:
        print("\n" + "=" * 70)
        print("Comparison")
        print("=" * 70)
        
        equity_info = runtime_metrics.get("equity", {})
        
        def compare_field(name, runtime_val, analyze_val, tolerance=0.01):
            diff = abs(runtime_val - analyze_val)
            if diff < tolerance:
                print(f"  ✓ {name:20} Match: {runtime_val:,.2f}")
            else:
                print(f"  ✗ {name:20} DIFFER: runtime={runtime_val:,.2f}, "
                      f"analyze={analyze_val:,.2f}, diff={diff:,.2f}")
        
        compare_field("Equity", equity_info.get('current_equity', 0), meta.equity)
        compare_field("Realized PnL", equity_info.get('realized_pnl', 0), meta.realized)
        compare_field("Unrealized PnL", equity_info.get('unrealized_pnl', 0), meta.unrealized)
        compare_field("Total Notional", equity_info.get('total_notional', 0), meta.notional)
    
    print("\n" + "=" * 70)


if __name__ == "__main__":
    compare_metrics()
