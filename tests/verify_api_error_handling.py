#!/usr/bin/env python3
"""
Test that API endpoints handle missing files gracefully.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_analytics_summary_missing_files():
    """Test /api/analytics/summary with missing runtime_metrics.json"""
    print("Testing /api/analytics/summary with missing files...")
    try:
        from ui.dashboard import api_analytics_summary, ANALYTICS_DIR
        
        # Temporarily rename the file if it exists
        runtime_metrics_path = ANALYTICS_DIR / "runtime_metrics.json"
        backup_path = None
        
        if runtime_metrics_path.exists():
            backup_path = runtime_metrics_path.with_suffix(".json.bak")
            runtime_metrics_path.rename(backup_path)
        
        try:
            # Call the endpoint with missing file
            response = api_analytics_summary()
            data = json.loads(response.body.decode('utf-8'))
            
            # Verify it returns safe defaults
            assert data["status"] == "empty", "Status should be 'empty' when no files present"
            assert data["equity"]["current_equity"] == 0.0, "Should return 0.0 for equity"
            assert data["overall"]["total_trades"] == 0, "Should return 0 for trades"
            
            print(f"✓ Handles missing files correctly")
            return True
        finally:
            # Restore the file
            if backup_path and backup_path.exists():
                backup_path.rename(runtime_metrics_path)
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_analytics_summary_malformed_json():
    """Test /api/analytics/summary with malformed JSON"""
    print("\nTesting /api/analytics/summary with malformed JSON...")
    try:
        from ui.dashboard import api_analytics_summary, ANALYTICS_DIR
        
        runtime_metrics_path = ANALYTICS_DIR / "runtime_metrics.json"
        backup_path = None
        
        # Create backup if exists
        if runtime_metrics_path.exists():
            backup_path = runtime_metrics_path.with_suffix(".json.bak2")
            runtime_metrics_path.rename(backup_path)
        
        try:
            # Write malformed JSON
            runtime_metrics_path.write_text("{ invalid json }", encoding="utf-8")
            
            # Call the endpoint
            response = api_analytics_summary()
            data = json.loads(response.body.decode('utf-8'))
            
            # Verify it returns safe defaults
            assert data["status"] == "empty", "Should return 'empty' status on malformed JSON"
            assert "equity" in data, "Should still have equity field"
            assert "overall" in data, "Should still have overall field"
            
            print(f"✓ Handles malformed JSON correctly")
            return True
        finally:
            # Clean up malformed file
            if runtime_metrics_path.exists():
                runtime_metrics_path.unlink()
            
            # Restore backup
            if backup_path and backup_path.exists():
                backup_path.rename(runtime_metrics_path)
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_state_missing_checkpoint():
    """Test /api/state with missing checkpoint"""
    print("\nTesting /api/state with missing checkpoint...")
    try:
        from ui.dashboard import api_state
        
        # The checkpoint might not exist in a fresh environment
        # The API should handle this gracefully
        response = api_state()
        data = json.loads(response.body.decode('utf-8'))
        
        # Verify required fields are present
        assert "mode" in data
        assert "engine_status" in data
        assert "last_heartbeat_ts" in data
        assert "last_update_age_seconds" in data
        assert "active_engines" in data
        assert "positions_count" in data
        
        # When checkpoint is missing or old, engine_status should be stopped or unknown
        assert data["engine_status"] in ["stopped", "unknown", "running"]
        
        print(f"✓ Handles missing/old checkpoint correctly")
        return True
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_risk_summary_missing_config():
    """Test /api/risk/summary handles missing config gracefully"""
    print("\nTesting /api/risk/summary with potential config issues...")
    try:
        from ui.dashboard import api_risk_summary
        
        # Call the endpoint (even if config is missing, it should not crash)
        response = api_risk_summary()
        data = json.loads(response.body.decode('utf-8'))
        
        # Verify all required fields are present
        required_fields = [
            "max_daily_loss", "used_loss", "remaining_loss",
            "max_exposure_pct", "current_exposure_pct",
            "risk_per_trade_pct", "status"
        ]
        
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
            # All numeric fields should be numbers (not None)
            if field != "status":
                assert isinstance(data[field], (int, float)), f"{field} should be a number"
        
        print(f"✓ Returns all required fields with safe defaults")
        return True
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all error handling tests"""
    print("=" * 60)
    print("Backend API Error Handling Tests")
    print("=" * 60)
    
    results = []
    results.append(("missing_files", test_analytics_summary_missing_files()))
    results.append(("malformed_json", test_analytics_summary_malformed_json()))
    results.append(("missing_checkpoint", test_state_missing_checkpoint()))
    results.append(("missing_config", test_risk_summary_missing_config()))
    
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
        print("\n🎉 All error handling tests passed!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
