#!/usr/bin/env python3
"""
Manual test script for Portfolio API endpoint.
Tests that /api/portfolio correctly reads from runtime_metrics.json and paper_state_latest.json
"""

import sys
import json
import time
import requests
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

BASE_URL = "http://127.0.0.1:8765"
ARTIFACTS_DIR = Path(__file__).parent.parent / "artifacts"
ANALYTICS_DIR = ARTIFACTS_DIR / "analytics"
CHECKPOINTS_DIR = ARTIFACTS_DIR / "checkpoints"


def create_test_runtime_metrics():
    """Create a sample runtime_metrics.json for testing."""
    metrics = {
        "asof": datetime.now().isoformat(),
        "mode": "paper",
        "equity": {
            "starting_capital": 500000.0,
            "current_equity": 502500.50,
            "realized_pnl": 2500.50,
            "unrealized_pnl": 0.0,
            "total_notional": 0.0,
            "max_drawdown": 500.0,
            "max_equity": 503000.0,
            "min_equity": 499500.0,
        },
        "overall": {
            "total_trades": 10,
            "win_trades": 6,
            "loss_trades": 4,
            "breakeven_trades": 0,
            "win_rate": 60.0,
            "gross_profit": 5000.0,
            "gross_loss": 2499.50,
            "net_pnl": 2500.50,
            "profit_factor": 2.0,
            "avg_win": 833.33,
            "avg_loss": 624.87,
            "avg_r_multiple": 1.2,
            "biggest_win": 1500.0,
            "biggest_loss": -800.0,
        },
        "per_strategy": {},
        "per_symbol": {},
    }
    
    ANALYTICS_DIR.mkdir(parents=True, exist_ok=True)
    metrics_path = ANALYTICS_DIR / "runtime_metrics.json"
    
    with metrics_path.open("w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)
    
    print(f"✓ Created test runtime_metrics.json at {metrics_path}")
    return metrics


def create_test_checkpoint():
    """Create a sample paper_state_latest.json for testing."""
    state = {
        "timestamp": datetime.now().isoformat(),
        "mode": "paper",
        "equity": {
            "paper_capital": 500000.0,
            "realized_pnl": 2500.50,
            "unrealized_pnl": 150.0,
            "total_notional": 45000.0,
        },
        "pnl": {
            "day_pnl": 2650.50,
            "realized_pnl": 2500.50,
            "unrealized_pnl": 150.0,
        },
        "positions": [
            {
                "symbol": "NIFTY24DECFUT",
                "quantity": 50,
                "avg_price": 23500.0,
                "ltp": 23550.0,
                "last_price": 23550.0,
            },
            {
                "symbol": "BANKNIFTY24DECFUT",
                "quantity": -30,
                "avg_price": 49800.0,
                "ltp": 49750.0,
                "last_price": 49750.0,
            },
        ],
    }
    
    CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)
    checkpoint_path = CHECKPOINTS_DIR / "paper_state_latest.json"
    
    with checkpoint_path.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    
    print(f"✓ Created test paper_state_latest.json at {checkpoint_path}")
    return state


def test_portfolio_endpoint():
    """Test the /api/portfolio endpoint."""
    url = f"{BASE_URL}/api/portfolio"
    
    try:
        response = requests.get(url, timeout=5)
        
        print(f"\n{'='*70}")
        print(f"GET /api/portfolio")
        print(f"Status: {response.status_code}")
        print(f"Response:")
        print(json.dumps(response.json(), indent=2))
        print(f"{'='*70}")
        
        if response.status_code == 200:
            data = response.json()
            
            # Validate structure
            required_fields = [
                "equity", "starting_capital", "daily_pnl",
                "realized_pnl", "unrealized_pnl", "total_notional",
                "free_margin", "open_positions", "positions"
            ]
            
            missing = [f for f in required_fields if f not in data]
            if missing:
                print(f"\n❌ Missing fields: {missing}")
                return False
            
            print("\n✓ All required fields present")
            
            # Validate positions structure
            positions = data.get("positions", [])
            if positions:
                pos_required = ["symbol", "side", "quantity", "avg_price", "ltp", "pnl", "pnl_pct"]
                for i, pos in enumerate(positions):
                    pos_missing = [f for f in pos_required if f not in pos]
                    if pos_missing:
                        print(f"\n❌ Position {i} missing fields: {pos_missing}")
                        return False
                
                print(f"✓ All {len(positions)} positions have required fields")
                
                # Print position details
                print("\nPosition Details:")
                for pos in positions:
                    print(f"  {pos['symbol']:20} {pos['side']:6} Qty: {pos['quantity']:4} "
                          f"Avg: {pos['avg_price']:8.2f} LTP: {pos['ltp']:8.2f} "
                          f"PnL: {pos['pnl']:8.2f} ({pos['pnl_pct']:+6.2f}%)")
            
            # Validate numbers match expected values
            print("\nValidation:")
            expected_realized = 2500.50
            actual_realized = data.get("realized_pnl", 0.0)
            if abs(actual_realized - expected_realized) < 0.01:
                print(f"✓ Realized PnL matches: {actual_realized:.2f}")
            else:
                print(f"❌ Realized PnL mismatch: expected {expected_realized:.2f}, got {actual_realized:.2f}")
            
            expected_starting = 500000.0
            actual_starting = data.get("starting_capital", 0.0)
            if abs(actual_starting - expected_starting) < 0.01:
                print(f"✓ Starting capital matches: {actual_starting:.2f}")
            else:
                print(f"❌ Starting capital mismatch: expected {expected_starting:.2f}, got {actual_starting:.2f}")
            
            return True
        else:
            print(f"\n❌ Request failed with status {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        print(f"\n❌ Could not connect to {BASE_URL}")
        print("Make sure the dashboard server is running:")
        print("  python -m ui.dashboard")
        return False
    except Exception as exc:
        print(f"\n❌ Error: {exc}")
        return False


def main():
    """Run the test."""
    print("\n" + "="*70)
    print("Portfolio API Endpoint Testing")
    print("="*70)
    
    # Create test data
    print("\nStep 1: Creating test data files...")
    create_test_runtime_metrics()
    create_test_checkpoint()
    
    print("\nStep 2: Testing /api/portfolio endpoint...")
    print("\nNOTE: Make sure the dashboard server is running:")
    print("  uvicorn ui.dashboard:app --reload --port 8765")
    print("\nWaiting 2 seconds for server to be ready...")
    time.sleep(2)
    
    success = test_portfolio_endpoint()
    
    print("\n" + "="*70)
    if success:
        print("✓ Testing Complete - All checks passed!")
    else:
        print("✗ Testing Complete - Some checks failed")
    print("="*70)
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
