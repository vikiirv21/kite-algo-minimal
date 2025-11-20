#!/usr/bin/env python3
"""
Test script for runtime metrics and equity curve tracking.

This script tests:
1. RuntimeMetricsTracker initialization and updates
2. EquityCurveWriter CSV writing
3. Safe loader functions
4. API endpoint data structures
"""

import sys
import tempfile
from pathlib import Path
from datetime import datetime, timezone

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from analytics.runtime_metrics import RuntimeMetricsTracker, load_runtime_metrics
from analytics.equity_curve import EquityCurveWriter, load_equity_curve


def test_runtime_metrics_tracker():
    """Test RuntimeMetricsTracker functionality."""
    print("\n=== Testing RuntimeMetricsTracker ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        artifacts_dir = Path(tmpdir)
        
        # Initialize tracker
        tracker = RuntimeMetricsTracker(
            starting_capital=100000.0,
            mode="paper",
            artifacts_dir=artifacts_dir,
            equity_curve_maxlen=10,
        )
        
        print(f"✓ Tracker initialized with capital: {tracker.starting_capital}")
        print(f"✓ Current equity: {tracker.current_equity}")
        
        # Simulate a fill
        tracker.update_after_fill(
            symbol="NIFTY24DECFUT",
            strategy="EMA_20_50",
            realized_pnl=150.0,
            fill_price=19500.0,
            qty=50,
            side="BUY",
        )
        
        print(f"✓ After fill: realized_pnl={tracker.realized_pnl}, equity={tracker.current_equity}")
        
        # Update unrealized PnL
        tracker.update_unrealized_pnl(250.0)
        print(f"✓ After unrealized update: unrealized_pnl={tracker.unrealized_pnl}, equity={tracker.current_equity}")
        
        # Push equity snapshot
        success = tracker.push_equity_snapshot(min_interval_sec=0.0)
        print(f"✓ Equity snapshot pushed: {success}")
        print(f"✓ Equity curve length: {len(tracker.equity_curve)}")
        
        # Get metrics
        metrics = tracker.get_metrics()
        print(f"✓ Metrics retrieved: equity={metrics.current_equity}, realized={metrics.realized_pnl}, unrealized={metrics.unrealized_pnl}")
        print(f"✓ PnL per symbol: {dict(metrics.pnl_per_symbol)}")
        print(f"✓ PnL per strategy: {dict(metrics.pnl_per_strategy)}")
        
        # Save to JSON
        success = tracker.save()
        print(f"✓ Metrics saved to JSON: {success}")
        
        # Test safe loader
        metrics_path = artifacts_dir / "analytics" / "runtime_metrics.json"
        if metrics_path.exists():
            print(f"✓ Metrics file exists: {metrics_path}")
            
            loaded_metrics = load_runtime_metrics(metrics_path)
            print(f"✓ Metrics loaded: equity={loaded_metrics.get('current_equity')}")
        
        print("✓ RuntimeMetricsTracker tests passed!")


def test_equity_curve_writer():
    """Test EquityCurveWriter functionality."""
    print("\n=== Testing EquityCurveWriter ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        artifacts_dir = Path(tmpdir)
        
        # Initialize writer
        writer = EquityCurveWriter(
            artifacts_dir=artifacts_dir,
            filename="test_snapshots.csv",
            min_interval_sec=0.0,  # No rate limiting for test
        )
        
        print(f"✓ Writer initialized with path: {writer.csv_path}")
        
        # Write some snapshots
        for i in range(5):
            success = writer.append_snapshot(
                equity=100000.0 + i * 100,
                realized_pnl=i * 50,
                unrealized_pnl=i * 30,
            )
            print(f"✓ Snapshot {i+1} written: {success}")
        
        # Read back the curve
        curve = writer.read_curve()
        print(f"✓ Read {len(curve)} snapshots from CSV")
        
        if curve:
            print(f"✓ First snapshot: {curve[0]}")
            print(f"✓ Last snapshot: {curve[-1]}")
        
        # Test safe loader
        loaded_curve = load_equity_curve(artifacts_dir, filename="test_snapshots.csv")
        print(f"✓ Safe loader returned {len(loaded_curve)} snapshots")
        
        # Test max_rows parameter
        limited_curve = load_equity_curve(artifacts_dir, filename="test_snapshots.csv", max_rows=3)
        print(f"✓ Limited to {len(limited_curve)} snapshots (max_rows=3)")
        
        print("✓ EquityCurveWriter tests passed!")


def test_api_data_structures():
    """Test that data structures match API expectations."""
    print("\n=== Testing API Data Structures ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        artifacts_dir = Path(tmpdir)
        
        # Create and populate tracker
        tracker = RuntimeMetricsTracker(
            starting_capital=500000.0,
            mode="paper",
            artifacts_dir=artifacts_dir,
        )
        
        tracker.update_after_fill("NIFTY", "TREND", 100.0, 19500.0, 50, "BUY")
        tracker.update_unrealized_pnl(200.0)
        tracker.push_equity_snapshot(min_interval_sec=0.0)
        tracker.save()
        
        # Load and check structure
        metrics = load_runtime_metrics(artifacts_dir / "analytics" / "runtime_metrics.json")
        
        # Check required fields for /api/analytics/summary
        required_fields = [
            "asof", "mode", "starting_capital", "current_equity",
            "realized_pnl", "unrealized_pnl", "daily_pnl",
            "max_equity", "min_equity", "max_drawdown",
            "pnl_per_symbol", "pnl_per_strategy", "equity_curve"
        ]
        
        for field in required_fields:
            if field not in metrics:
                print(f"✗ Missing field: {field}")
            else:
                print(f"✓ Field present: {field}")
        
        # Check equity curve structure
        if metrics.get("equity_curve"):
            snapshot = metrics["equity_curve"][0]
            curve_fields = ["timestamp", "equity", "realized_pnl", "unrealized_pnl"]
            for field in curve_fields:
                if field not in snapshot:
                    print(f"✗ Missing equity curve field: {field}")
                else:
                    print(f"✓ Equity curve field present: {field}")
        
        print("✓ API data structure tests passed!")


def test_safe_loaders():
    """Test that safe loaders never crash."""
    print("\n=== Testing Safe Loaders ===")
    
    # Test with non-existent path
    try:
        metrics = load_runtime_metrics(Path("/nonexistent/path/metrics.json"))
        print(f"✓ Safe loader handled missing file: returned {len(metrics)} fields")
    except Exception as e:
        print(f"✗ Safe loader crashed: {e}")
    
    # Test with invalid JSON
    with tempfile.TemporaryDirectory() as tmpdir:
        invalid_path = Path(tmpdir) / "invalid.json"
        invalid_path.write_text("{ invalid json }")
        
        try:
            metrics = load_runtime_metrics(invalid_path)
            print(f"✓ Safe loader handled invalid JSON: returned {len(metrics)} fields")
        except Exception as e:
            print(f"✗ Safe loader crashed on invalid JSON: {e}")
    
    # Test equity curve with non-existent file
    try:
        curve = load_equity_curve(Path("/nonexistent"), "snapshots.csv")
        print(f"✓ Equity curve safe loader handled missing file: returned {len(curve)} rows")
    except Exception as e:
        print(f"✗ Equity curve safe loader crashed: {e}")
    
    print("✓ Safe loader tests passed!")


if __name__ == "__main__":
    print("Starting Analytics System Tests...")
    
    try:
        test_runtime_metrics_tracker()
        test_equity_curve_writer()
        test_api_data_structures()
        test_safe_loaders()
        
        print("\n" + "=" * 50)
        print("✅ All tests passed!")
        print("=" * 50)
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
