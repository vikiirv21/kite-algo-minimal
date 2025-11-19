#!/usr/bin/env python3
"""
Simple verification script for the three API endpoints.
Tests that they return correct data and don't crash.
"""
import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

def test_analytics_summary():
    """Test /api/analytics/summary endpoint"""
    print("Testing /api/analytics/summary...")
    try:
        from ui.dashboard import api_analytics_summary
        
        # Call the endpoint
        response = api_analytics_summary()
        data = json.loads(response.body.decode('utf-8'))
        
        # Verify structure
        assert "asof" in data, "Missing 'asof' field"
        assert "status" in data, "Missing 'status' field"
        assert "mode" in data, "Missing 'mode' field"
        assert "equity" in data, "Missing 'equity' field"
        assert "overall" in data, "Missing 'overall' field"
        assert "per_strategy" in data, "Missing 'per_strategy' field"
        assert "per_symbol" in data, "Missing 'per_symbol' field"
        
        # Verify equity fields
        equity = data["equity"]
        required_equity_fields = [
            "starting_capital", "current_equity", "realized_pnl", 
            "unrealized_pnl", "max_drawdown", "max_equity", "min_equity"
        ]
        for field in required_equity_fields:
            assert field in equity, f"Missing equity field: {field}"
        
        # Verify overall fields
        overall = data["overall"]
        required_overall_fields = [
            "total_trades", "win_trades", "loss_trades", "breakeven_trades",
            "win_rate", "gross_profit", "gross_loss", "net_pnl", "profit_factor",
            "avg_win", "avg_loss", "avg_r_multiple", "biggest_win", "biggest_loss"
        ]
        for field in required_overall_fields:
            assert field in overall, f"Missing overall field: {field}"
        
        # Verify status is valid
        assert data["status"] in ["ok", "stale", "empty"], f"Invalid status: {data['status']}"
        
        print(f"✓ Analytics summary test passed")
        print(f"  - Status: {data['status']}")
        print(f"  - Mode: {data['mode']}")
        print(f"  - Equity: ${data['equity']['current_equity']:,.2f}")
        print(f"  - Total trades: {data['overall']['total_trades']}")
        return True
    except Exception as e:
        print(f"✗ Analytics summary test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_state():
    """Test /api/state endpoint"""
    print("\nTesting /api/state...")
    try:
        from ui.dashboard import api_state
        
        # Call the endpoint
        response = api_state()
        data = json.loads(response.body.decode('utf-8'))
        
        # Verify structure
        assert "mode" in data, "Missing 'mode' field"
        assert "engine_status" in data, "Missing 'engine_status' field"
        assert "last_heartbeat_ts" in data, "Missing 'last_heartbeat_ts' field"
        assert "last_update_age_seconds" in data, "Missing 'last_update_age_seconds' field"
        assert "active_engines" in data, "Missing 'active_engines' field"
        assert "positions_count" in data, "Missing 'positions_count' field"
        
        # Verify types
        assert data["mode"] in ["paper", "live", "unknown"], f"Invalid mode: {data['mode']}"
        assert data["engine_status"] in ["running", "stopped", "unknown"], f"Invalid engine_status: {data['engine_status']}"
        assert isinstance(data["last_update_age_seconds"], (int, float)), "last_update_age_seconds must be a number"
        assert isinstance(data["active_engines"], list), "active_engines must be a list"
        assert isinstance(data["positions_count"], int), "positions_count must be an integer"
        
        print(f"✓ State test passed")
        print(f"  - Mode: {data['mode']}")
        print(f"  - Engine status: {data['engine_status']}")
        print(f"  - Heartbeat age: {data['last_update_age_seconds']}s")
        print(f"  - Active engines: {data['active_engines']}")
        print(f"  - Positions: {data['positions_count']}")
        return True
    except Exception as e:
        print(f"✗ State test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_risk_summary():
    """Test /api/risk/summary endpoint"""
    print("\nTesting /api/risk/summary...")
    try:
        from ui.dashboard import api_risk_summary
        
        # Call the endpoint
        response = api_risk_summary()
        data = json.loads(response.body.decode('utf-8'))
        
        # Verify structure
        required_fields = [
            "max_daily_loss", "used_loss", "remaining_loss",
            "max_exposure_pct", "current_exposure_pct",
            "risk_per_trade_pct", "status"
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
        
        # Verify types
        for field in ["max_daily_loss", "used_loss", "remaining_loss", 
                      "max_exposure_pct", "current_exposure_pct", "risk_per_trade_pct"]:
            assert isinstance(data[field], (int, float)), f"{field} must be a number"
        
        assert data["status"] in ["ok", "empty", "stale"], f"Invalid status: {data['status']}"
        
        print(f"✓ Risk summary test passed")
        print(f"  - Status: {data['status']}")
        print(f"  - Max daily loss: ${data['max_daily_loss']:,.2f}")
        print(f"  - Used loss: ${data['used_loss']:,.2f}")
        print(f"  - Remaining loss: ${data['remaining_loss']:,.2f}")
        print(f"  - Current exposure: {data['current_exposure_pct']:.1f}%")
        print(f"  - Max exposure: {data['max_exposure_pct']:.1f}%")
        return True
    except Exception as e:
        print(f"✗ Risk summary test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print("=" * 60)
    print("Backend API Endpoints Verification")
    print("=" * 60)
    
    results = []
    results.append(("analytics_summary", test_analytics_summary()))
    results.append(("state", test_state()))
    results.append(("risk_summary", test_risk_summary()))
    
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "PASSED" if result else "FAILED"
        symbol = "✓" if result else "✗"
        print(f"{symbol} {name}: {status}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
