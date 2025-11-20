"""
Integration test for SRDE (Strategy Real-Time Diagnostics Engine).

This test validates the full end-to-end flow:
1. Diagnostic emission from strategy engines
2. JSONL persistence
3. REST API retrieval via dashboard endpoint

Run with: python tests/test_diagnostics_integration.py
"""

import json
import sys
from pathlib import Path

# Setup paths
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.diagnostics import (
    append_diagnostic,
    build_diagnostic_record,
    load_diagnostics,
)


def test_end_to_end_flow():
    """Test complete diagnostics flow from emission to retrieval."""
    print("Testing end-to-end diagnostics flow...")
    
    # 1. Simulate strategy engine emitting diagnostics
    symbol = "NIFTY_INTEGRATION_TEST"
    strategy = "EMA_20_50"
    
    # Create multiple diagnostic records
    diagnostics = []
    for i in range(10):
        record = build_diagnostic_record(
            price=19500.0 + i * 5,
            decision="BUY" if i % 3 == 0 else "HOLD",
            reason=f"Integration test decision {i}",
            confidence=0.65 + i * 0.03,
            ema20=19450.0 + i * 5,
            ema50=19400.0 + i * 5,
            trend_strength=0.75 + i * 0.02,
            rr=2.5 if i % 3 == 0 else None,
            regime="trend" if i < 5 else "low_vol",
            risk_block="none" if i % 3 == 0 else "cooldown",
            strategy_id=strategy,
            timeframe="5m",
        )
        diagnostics.append(record)
        
        # Emit diagnostic
        success = append_diagnostic(symbol, strategy, record)
        assert success, f"Failed to append diagnostic {i}"
    
    print(f"  ✓ Emitted {len(diagnostics)} diagnostics")
    
    # 2. Verify JSONL persistence
    from analytics.diagnostics import path_for
    
    file_path = path_for(symbol, strategy)
    assert file_path.exists(), "Diagnostic file should exist"
    
    # Count lines in JSONL file
    with file_path.open("r") as f:
        lines = [line for line in f if line.strip()]
    
    assert len(lines) >= len(diagnostics), "All diagnostics should be persisted"
    print(f"  ✓ Verified JSONL persistence: {len(lines)} records")
    
    # 3. Retrieve diagnostics via load function
    retrieved = load_diagnostics(symbol, strategy, limit=5)
    
    assert len(retrieved) == 5, "Should retrieve exactly 5 records"
    assert retrieved[0]["price"] > retrieved[-1]["price"], "Should be in reverse chronological order"
    print(f"  ✓ Retrieved {len(retrieved)} diagnostics (newest first)")
    
    # 4. Verify data integrity
    for record in retrieved:
        assert "ts" in record, "Timestamp should be present"
        assert "price" in record, "Price should be present"
        assert "decision" in record, "Decision should be present"
        assert "reason" in record, "Reason should be present"
        assert "confidence" in record, "Confidence should be present"
        assert record["decision"] in ["BUY", "SELL", "HOLD"], "Decision should be valid"
    
    print("  ✓ Data integrity validated")
    
    # 5. Test filtering by limit
    all_records = load_diagnostics(symbol, strategy, limit=100)
    assert len(all_records) >= 10, "Should retrieve all records when limit is high"
    print(f"  ✓ Retrieved all records: {len(all_records)}")
    
    # 6. Test dashboard API format compatibility
    # Simulate what the dashboard endpoint returns
    dashboard_response = {
        "symbol": symbol,
        "strategy": strategy,
        "data": retrieved,
        "count": len(retrieved),
    }
    
    # Verify it's JSON serializable
    json_str = json.dumps(dashboard_response)
    assert len(json_str) > 0, "Response should be JSON serializable"
    
    # Parse it back
    parsed = json.loads(json_str)
    assert parsed["symbol"] == symbol, "Symbol should match"
    assert parsed["strategy"] == strategy, "Strategy should match"
    assert parsed["count"] == 5, "Count should match"
    
    print("  ✓ Dashboard API format validated")
    
    print("\n✓ All integration tests passed!")
    return True


def test_crash_resilience():
    """Test that diagnostics never crash on errors."""
    print("\nTesting crash resilience...")
    
    # Test with invalid data
    try:
        # This should not crash
        result = append_diagnostic("", "", {})
        print("  ✓ Handles empty inputs gracefully")
    except Exception as e:
        print(f"  ✗ Failed on empty inputs: {e}")
        return False
    
    # Test with missing file
    try:
        result = load_diagnostics("NONEXISTENT_SYMBOL_XYZ", "NONEXISTENT_STRATEGY_ABC", limit=10)
        assert result == [], "Should return empty list for nonexistent file"
        print("  ✓ Handles missing files gracefully")
    except Exception as e:
        print(f"  ✗ Failed on missing file: {e}")
        return False
    
    print("✓ Crash resilience validated")
    return True


def test_performance():
    """Test that diagnostics operations are fast enough."""
    import time
    
    print("\nTesting performance...")
    
    symbol = "PERF_TEST"
    strategy = "PERF_STRATEGY"
    
    # Test append performance
    start = time.time()
    for i in range(100):
        record = build_diagnostic_record(
            price=100.0 + i,
            decision="HOLD",
            reason="Perf test",
            confidence=0.5,
        )
        append_diagnostic(symbol, strategy, record)
    
    append_time = time.time() - start
    avg_append = append_time / 100 * 1000  # ms per append
    
    print(f"  ✓ Append: {avg_append:.2f}ms per record (100 records in {append_time:.3f}s)")
    
    # Test load performance
    start = time.time()
    for i in range(10):
        load_diagnostics(symbol, strategy, limit=50)
    
    load_time = time.time() - start
    avg_load = load_time / 10 * 1000  # ms per load
    
    print(f"  ✓ Load: {avg_load:.2f}ms per query (10 queries in {load_time:.3f}s)")
    
    # Ensure operations are fast enough (< 100ms per operation)
    assert avg_append < 100, f"Append too slow: {avg_append:.2f}ms"
    assert avg_load < 100, f"Load too slow: {avg_load:.2f}ms"
    
    print("✓ Performance validated (all ops < 100ms)")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("SRDE Integration Test Suite")
    print("=" * 60)
    
    success = True
    
    try:
        success = test_end_to_end_flow() and success
        success = test_crash_resilience() and success
        success = test_performance() and success
    except Exception as e:
        print(f"\n✗ Test suite failed with exception: {e}")
        import traceback
        traceback.print_exc()
        success = False
    
    print("\n" + "=" * 60)
    if success:
        print("✓ ALL INTEGRATION TESTS PASSED")
        print("=" * 60)
        sys.exit(0)
    else:
        print("✗ SOME TESTS FAILED")
        print("=" * 60)
        sys.exit(1)
