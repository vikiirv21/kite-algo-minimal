#!/usr/bin/env python3
"""
Test edge cases for the refactored /api/portfolio endpoint.
"""

import sys
import json
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

BASE_URL = "http://127.0.0.1:8765"
ARTIFACTS_DIR = Path(__file__).parent.parent / "artifacts"
ANALYTICS_DIR = ARTIFACTS_DIR / "analytics"
CHECKPOINTS_DIR = ARTIFACTS_DIR / "checkpoints"


def test_missing_files():
    """Test behavior when runtime_metrics.json and checkpoint are missing."""
    print("\n" + "="*70)
    print("Test 1: Missing both runtime_metrics.json and checkpoint")
    print("="*70)
    
    # Backup existing files
    metrics_path = ANALYTICS_DIR / "runtime_metrics.json"
    checkpoint_path = CHECKPOINTS_DIR / "paper_state_latest.json"
    
    metrics_backup = None
    checkpoint_backup = None
    
    if metrics_path.exists():
        metrics_backup = metrics_path.read_text()
        metrics_path.unlink()
    
    if checkpoint_path.exists():
        checkpoint_backup = checkpoint_path.read_text()
        checkpoint_path.unlink()
    
    try:
        response = requests.get(f"{BASE_URL}/api/portfolio", timeout=5)
        data = response.json()
        
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(data, indent=2)}")
        
        # Should still return valid structure with defaults
        assert "equity" in data, "Missing equity field"
        assert "starting_capital" in data, "Missing starting_capital field"
        assert "positions" in data, "Missing positions field"
        
        # Should fallback to config default (500000)
        assert data["starting_capital"] == 500000.0, f"Expected 500000, got {data['starting_capital']}"
        
        print("\n✓ Correctly handles missing files with config fallback")
        
    finally:
        # Restore backups
        if metrics_backup:
            metrics_path.write_text(metrics_backup)
        if checkpoint_backup:
            checkpoint_path.write_text(checkpoint_backup)


def test_only_checkpoint():
    """Test behavior when only checkpoint exists (no runtime_metrics.json)."""
    print("\n" + "="*70)
    print("Test 2: Only checkpoint exists (no runtime_metrics.json)")
    print("="*70)
    
    metrics_path = ANALYTICS_DIR / "runtime_metrics.json"
    
    metrics_backup = None
    if metrics_path.exists():
        metrics_backup = metrics_path.read_text()
        metrics_path.unlink()
    
    try:
        response = requests.get(f"{BASE_URL}/api/portfolio", timeout=5)
        data = response.json()
        
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(data, indent=2)}")
        
        # Should use checkpoint data
        assert response.status_code == 200, "Expected success"
        assert "positions" in data, "Missing positions field"
        
        print("\n✓ Correctly falls back to checkpoint when runtime_metrics missing")
        
    finally:
        # Restore backup
        if metrics_backup:
            metrics_path.write_text(metrics_backup)


def test_empty_positions():
    """Test behavior with empty positions list."""
    print("\n" + "="*70)
    print("Test 3: Empty positions list")
    print("="*70)
    
    checkpoint_path = CHECKPOINTS_DIR / "paper_state_latest.json"
    checkpoint_backup = None
    
    if checkpoint_path.exists():
        checkpoint_backup = checkpoint_path.read_text()
    
    # Create checkpoint with empty positions
    test_state = {
        "timestamp": "2025-11-19T00:00:00",
        "mode": "paper",
        "equity": {
            "paper_capital": 500000.0,
            "realized_pnl": 1000.0,
            "unrealized_pnl": 0.0,
        },
        "positions": []
    }
    
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    with checkpoint_path.open("w") as f:
        json.dump(test_state, f)
    
    try:
        response = requests.get(f"{BASE_URL}/api/portfolio", timeout=5)
        data = response.json()
        
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(data, indent=2)}")
        
        assert response.status_code == 200, "Expected success"
        assert data["open_positions"] == 0, f"Expected 0 positions, got {data['open_positions']}"
        assert data["positions"] == [], "Expected empty positions list"
        
        print("\n✓ Correctly handles empty positions")
        
    finally:
        # Restore backup
        if checkpoint_backup:
            checkpoint_path.write_text(checkpoint_backup)


def test_position_without_ltp():
    """Test position PnL calculation when LTP is missing."""
    print("\n" + "="*70)
    print("Test 4: Position without LTP (should fallback to avg_price)")
    print("="*70)
    
    checkpoint_path = CHECKPOINTS_DIR / "paper_state_latest.json"
    checkpoint_backup = None
    
    if checkpoint_path.exists():
        checkpoint_backup = checkpoint_path.read_text()
    
    # Create checkpoint with position missing LTP
    test_state = {
        "timestamp": "2025-11-19T00:00:00",
        "mode": "paper",
        "equity": {
            "paper_capital": 500000.0,
            "realized_pnl": 0.0,
            "unrealized_pnl": 0.0,
        },
        "positions": [
            {
                "symbol": "TESTFUT",
                "quantity": 100,
                "avg_price": 1000.0,
                # No ltp or last_price
            }
        ]
    }
    
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    with checkpoint_path.open("w") as f:
        json.dump(test_state, f)
    
    try:
        response = requests.get(f"{BASE_URL}/api/portfolio", timeout=5)
        data = response.json()
        
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(data, indent=2)}")
        
        assert response.status_code == 200, "Expected success"
        assert len(data["positions"]) == 1, "Expected 1 position"
        
        pos = data["positions"][0]
        # Should fallback to avg_price, resulting in 0 PnL
        assert pos["ltp"] == pos["avg_price"], "LTP should fallback to avg_price"
        assert pos["pnl"] == 0.0, f"Expected 0 PnL, got {pos['pnl']}"
        
        print(f"\n✓ Position: {pos['symbol']}, LTP={pos['ltp']} (fallback), PnL={pos['pnl']}")
        print("✓ Correctly falls back to avg_price when LTP missing")
        
    finally:
        # Restore backup
        if checkpoint_backup:
            checkpoint_path.write_text(checkpoint_backup)


def main():
    """Run all edge case tests."""
    print("\n" + "="*70)
    print("Portfolio API Edge Case Testing")
    print("="*70)
    print("\nNOTE: Dashboard server must be running on port 8765")
    
    try:
        # Check if server is running
        response = requests.get(f"{BASE_URL}/api/health", timeout=2)
        if response.status_code != 200:
            print("❌ Server not responding correctly")
            return 1
    except Exception:
        print("❌ Could not connect to server. Start with:")
        print("  uvicorn ui.dashboard:app --reload --port 8765")
        return 1
    
    try:
        test_missing_files()
        test_only_checkpoint()
        test_empty_positions()
        test_position_without_ltp()
        
        print("\n" + "="*70)
        print("✓ All edge case tests passed!")
        print("="*70)
        return 0
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
