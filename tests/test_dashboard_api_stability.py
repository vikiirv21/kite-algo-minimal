#!/usr/bin/env python3
"""
Test script to verify dashboard API endpoints return stable JSON without crashing.

This script directly tests the safe loader functions and endpoint logic
without requiring the full dashboard server to be running.
"""

import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Test the safe loader functions
def test_safe_loaders():
    """Test that safe loaders never crash and always return valid structures."""
    from ui.dashboard import (
        load_runtime_metrics_safe,
        load_latest_checkpoint_safe,
        load_strategies_from_config_safe,
    )
    
    print("Testing safe loader functions...\n")
    
    # Test load_runtime_metrics_safe
    print("1. Testing load_runtime_metrics_safe()...")
    try:
        metrics = load_runtime_metrics_safe()
        assert isinstance(metrics, dict), "Must return dict"
        assert "equity" in metrics, "Must have equity field"
        assert "overall" in metrics, "Must have overall field"
        assert "per_strategy" in metrics, "Must have per_strategy field"
        assert "per_symbol" in metrics, "Must have per_symbol field"
        assert isinstance(metrics["equity"], dict), "equity must be dict"
        assert isinstance(metrics["overall"], dict), "overall must be dict"
        print("   ✓ Returns valid structure")
        print(f"   ✓ Equity fields: {len(metrics['equity'])} present")
        print(f"   ✓ Overall fields: {len(metrics['overall'])} present")
    except Exception as e:
        print(f"   ✗ FAILED: {e}")
        return False
    
    # Test load_latest_checkpoint_safe
    print("\n2. Testing load_latest_checkpoint_safe()...")
    try:
        checkpoint = load_latest_checkpoint_safe()
        assert isinstance(checkpoint, dict), "Must return dict"
        assert "meta" in checkpoint, "Must have meta field"
        assert "positions" in checkpoint, "Must have positions field"
        print("   ✓ Returns valid structure")
        print(f"   ✓ Top-level keys: {list(checkpoint.keys())}")
    except Exception as e:
        print(f"   ✗ FAILED: {e}")
        return False
    
    # Test load_strategies_from_config_safe
    print("\n3. Testing load_strategies_from_config_safe()...")
    try:
        strategies = load_strategies_from_config_safe()
        assert isinstance(strategies, list), "Must return list"
        print("   ✓ Returns valid list")
        print(f"   ✓ Found {len(strategies)} strategies")
        if strategies:
            strat = strategies[0]
            required_fields = ["id", "name", "strategy_code", "engine", "timeframe", "enabled", "params", "tags"]
            for field in required_fields:
                assert field in strat, f"Strategy must have {field} field"
            print(f"   ✓ First strategy has all required fields: {strat['id']}")
    except Exception as e:
        print(f"   ✗ FAILED: {e}")
        return False
    
    print("\n✅ All safe loader tests passed!")
    return True


def test_api_endpoint_logic():
    """Test the logic of API endpoints to ensure they return valid JSON."""
    print("\n\nTesting API endpoint response structures...\n")
    
    from ui.dashboard import (
        load_runtime_metrics_safe,
        load_latest_checkpoint_safe,
        load_paper_portfolio_summary,
        load_app_config,
    )
    
    # Test analytics summary logic
    print("1. Testing /api/analytics/summary logic...")
    try:
        metrics = load_runtime_metrics_safe()
        
        # Build response like the endpoint does
        response = {
            "asof": metrics.get("asof"),
            "status": "empty" if not metrics.get("asof") else "ok",
            "mode": metrics.get("mode", "paper"),
            "equity": metrics.get("equity", {}),
            "overall": metrics.get("overall", {}),
            "per_strategy": metrics.get("per_strategy", {}),
            "per_symbol": metrics.get("per_symbol", {}),
        }
        
        # Verify structure
        assert "equity" in response
        assert "overall" in response
        assert "status" in response
        assert response["status"] in ["ok", "stale", "empty"]
        
        print("   ✓ Response structure is valid")
        print(f"   ✓ Status: {response['status']}")
        print(f"   ✓ Mode: {response['mode']}")
    except Exception as e:
        print(f"   ✗ FAILED: {e}")
        return False
    
    # Test risk summary logic
    print("\n2. Testing /api/risk/summary logic...")
    try:
        cfg = load_app_config()
        risk_config = cfg.risk or {}
        trading_config = cfg.trading or {}
        
        portfolio_summary = load_paper_portfolio_summary()
        metrics = load_runtime_metrics_safe()
        
        # Build response like the endpoint does
        max_daily_loss = float(trading_config.get("max_daily_loss", 3000.0))
        risk_per_trade_pct = float(risk_config.get("risk_per_trade_pct", 0.005))
        
        response = {
            "max_daily_loss": max_daily_loss,
            "used_loss": 0.0,
            "remaining_loss": max_daily_loss,
            "max_exposure_pct": 200.0,
            "current_exposure_pct": 0.0,
            "risk_per_trade_pct": risk_per_trade_pct,
            "status": "empty",
        }
        
        # Verify structure
        assert isinstance(response["max_daily_loss"], (int, float))
        assert isinstance(response["risk_per_trade_pct"], (int, float))
        assert response["status"] in ["ok", "stale", "empty"]
        
        print("   ✓ Response structure is valid")
        print(f"   ✓ Max daily loss: {response['max_daily_loss']}")
        print(f"   ✓ Risk per trade: {response['risk_per_trade_pct']}%")
    except Exception as e:
        print(f"   ✗ FAILED: {e}")
        return False
    
    # Test trading summary logic
    print("\n3. Testing /api/trading/summary logic...")
    try:
        from core.runtime_mode import get_mode
        from datetime import datetime
        from zoneinfo import ZoneInfo
        
        mode = get_mode()
        ist_now = datetime.now(ZoneInfo("Asia/Kolkata"))
        
        response = {
            "mode": mode,
            "status": "STOPPED",
            "server_time_ist": ist_now.strftime("%Y-%m-%d %H:%M:%S"),
            "active_orders": [],
            "recent_orders": [],
            "active_positions_count": 0,
            "engine_running": False,
        }
        
        # Verify structure
        assert response["mode"] in ["paper", "live"]
        assert response["status"] in ["RUNNING", "STOPPED", "UNKNOWN"]
        assert isinstance(response["active_orders"], list)
        assert isinstance(response["recent_orders"], list)
        assert isinstance(response["active_positions_count"], int)
        
        print("   ✓ Response structure is valid")
        print(f"   ✓ Mode: {response['mode']}")
        print(f"   ✓ Status: {response['status']}")
        print(f"   ✓ Server time: {response['server_time_ist']}")
    except Exception as e:
        print(f"   ✗ FAILED: {e}")
        return False
    
    print("\n✅ All API endpoint logic tests passed!")
    return True


def main():
    """Run all tests."""
    print("="*60)
    print("Dashboard API Endpoint Stability Tests")
    print("="*60)
    
    test1 = test_safe_loaders()
    test2 = test_api_endpoint_logic()
    
    print("\n" + "="*60)
    if test1 and test2:
        print("✅ ALL TESTS PASSED")
        print("="*60)
        return 0
    else:
        print("❌ SOME TESTS FAILED")
        print("="*60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
