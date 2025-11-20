"""
Test suite for Strategy Real-Time Diagnostics Engine (SRDE).

Tests:
- Directory creation and path generation
- Diagnostic record appending (JSONL)
- Diagnostic record loading with limits
- Error handling and crash resilience
- Helper functions
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path

# We'll test by importing the module
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.diagnostics import (
    ensure_diagnostics_dir,
    path_for,
    append_diagnostic,
    load_diagnostics,
    build_diagnostic_record,
    DIAGNOSTICS_DIR,
)


def test_ensure_diagnostics_dir():
    """Test that diagnostics directory is created."""
    diag_dir = ensure_diagnostics_dir()
    assert diag_dir.exists(), "Diagnostics directory should exist"
    assert diag_dir.is_dir(), "Diagnostics directory should be a directory"
    assert diag_dir == DIAGNOSTICS_DIR, "Should return correct path"


def test_path_for():
    """Test path generation for symbol/strategy combinations."""
    # Test normal case
    path = path_for("NIFTY", "EMA_20_50")
    assert path.parent.name == "NIFTY", "Symbol directory should match"
    assert path.name == "EMA_20_50.jsonl", "File name should be strategy + .jsonl"
    
    # Test with special characters (should be sanitized in the name components)
    path2 = path_for("NIFTY/FUT", "STRATEGY\\TEST")
    assert path2.parent.name == "NIFTY_FUT", "Forward slash should be sanitized in directory name"
    assert path2.name == "STRATEGY_TEST.jsonl", "Backslash should be sanitized in file name"
    
    # Test that parent directory is created
    assert path.parent.exists(), "Symbol directory should be auto-created"


def test_append_diagnostic_basic():
    """Test basic diagnostic appending."""
    symbol = "TEST_NIFTY"
    strategy = "TEST_EMA"
    
    record = {
        "price": 19500.0,
        "ema20": 19450.0,
        "ema50": 19400.0,
        "trend_strength": 0.85,
        "confidence": 0.75,
        "rr": 2.5,
        "regime": "trend",
        "risk_block": "none",
        "decision": "BUY",
        "reason": "Strong uptrend with EMA20 > EMA50",
    }
    
    # Append record
    success = append_diagnostic(symbol, strategy, record)
    assert success, "Append should succeed"
    
    # Verify file was created
    file_path = path_for(symbol, strategy)
    assert file_path.exists(), "JSONL file should be created"
    
    # Verify content
    with file_path.open("r", encoding="utf-8") as f:
        lines = f.readlines()
        assert len(lines) >= 1, "Should have at least one line"
        
        last_line = lines[-1].strip()
        parsed = json.loads(last_line)
        assert parsed["price"] == 19500.0, "Price should match"
        assert parsed["decision"] == "BUY", "Decision should match"
        assert "ts" in parsed, "Timestamp should be auto-added"


def test_append_diagnostic_auto_timestamp():
    """Test that timestamp is auto-added if missing."""
    symbol = "TEST_AUTO_TS"
    strategy = "TEST_STRATEGY"
    
    record = {
        "price": 100.0,
        "decision": "HOLD",
        "reason": "Test",
    }
    
    append_diagnostic(symbol, strategy, record)
    
    # Load and verify
    records = load_diagnostics(symbol, strategy, limit=1)
    assert len(records) == 1, "Should have one record"
    assert "ts" in records[0], "Timestamp should be present"
    
    # Verify timestamp is valid ISO format
    ts_str = records[0]["ts"]
    datetime.fromisoformat(ts_str.replace("Z", "+00:00"))  # Should not raise


def test_load_diagnostics_basic():
    """Test loading diagnostics from JSONL."""
    symbol = "TEST_LOAD"
    strategy = "TEST_STRATEGY"
    
    # Append multiple records
    for i in range(5):
        record = {
            "price": 100.0 + i,
            "decision": "HOLD",
            "reason": f"Test {i}",
        }
        append_diagnostic(symbol, strategy, record)
    
    # Load all
    records = load_diagnostics(symbol, strategy, limit=100)
    assert len(records) >= 5, "Should have at least 5 records"
    
    # Verify order (newest first)
    prices = [r["price"] for r in records]
    assert prices[0] > prices[-1], "Should be in reverse chronological order (newest first)"


def test_load_diagnostics_with_limit():
    """Test that limit parameter works correctly."""
    symbol = "TEST_LIMIT"
    strategy = "TEST_STRATEGY"
    
    # Append 10 records
    for i in range(10):
        record = {
            "price": 100.0 + i,
            "decision": "HOLD",
            "reason": f"Test {i}",
        }
        append_diagnostic(symbol, strategy, record)
    
    # Load with limit=3
    records = load_diagnostics(symbol, strategy, limit=3)
    assert len(records) == 3, "Should return exactly 3 records"
    
    # Should be the most recent 3
    prices = [r["price"] for r in records]
    assert prices[0] >= 107.0, "Should be most recent records"


def test_load_diagnostics_nonexistent():
    """Test loading diagnostics for nonexistent symbol/strategy."""
    records = load_diagnostics("NONEXISTENT_SYMBOL", "NONEXISTENT_STRATEGY", limit=10)
    assert records == [], "Should return empty list for nonexistent file"


def test_build_diagnostic_record():
    """Test diagnostic record builder helper."""
    record = build_diagnostic_record(
        price=19500.0,
        decision="BUY",
        reason="Test reason",
        confidence=0.85,
        ema20=19450.0,
        ema50=19400.0,
        trend_strength=0.9,
        rr=2.5,
        regime="trend",
        risk_block="none",
    )
    
    # Verify all fields
    assert record["price"] == 19500.0
    assert record["decision"] == "BUY"
    assert record["reason"] == "Test reason"
    assert record["confidence"] == 0.85
    assert record["ema20"] == 19450.0
    assert record["ema50"] == 19400.0
    assert record["trend_strength"] == 0.9
    assert record["rr"] == 2.5
    assert record["regime"] == "trend"
    assert record["risk_block"] == "none"
    assert "ts" in record


def test_build_diagnostic_record_with_none():
    """Test builder handles None values correctly."""
    record = build_diagnostic_record(
        price=100.0,
        decision="HOLD",
        reason="Test",
        confidence=0.5,
        ema20=None,
        ema50=None,
        trend_strength=None,
        rr=None,
        regime=None,
    )
    
    assert record["ema20"] is None
    assert record["ema50"] is None
    assert record["trend_strength"] is None
    assert record["rr"] is None
    assert record["regime"] is None


def test_error_handling():
    """Test that errors don't crash the module."""
    # Try to append with invalid data (should not crash)
    result = append_diagnostic("TEST", "TEST", {"invalid": float("nan")})
    # Should return False or handle gracefully
    # The important thing is it doesn't crash


def test_multiple_strategies_per_symbol():
    """Test that multiple strategies can write to same symbol."""
    symbol = "TEST_MULTI"
    
    for strategy in ["STRATEGY_A", "STRATEGY_B", "STRATEGY_C"]:
        record = {
            "price": 100.0,
            "decision": "HOLD",
            "reason": f"Test for {strategy}",
        }
        append_diagnostic(symbol, strategy, record)
    
    # Verify each has its own file
    for strategy in ["STRATEGY_A", "STRATEGY_B", "STRATEGY_C"]:
        records = load_diagnostics(symbol, strategy, limit=10)
        assert len(records) >= 1, f"Should have records for {strategy}"


if __name__ == "__main__":
    # Run tests
    print("Running diagnostics tests...")
    
    test_ensure_diagnostics_dir()
    print("✓ test_ensure_diagnostics_dir")
    
    test_path_for()
    print("✓ test_path_for")
    
    test_append_diagnostic_basic()
    print("✓ test_append_diagnostic_basic")
    
    test_append_diagnostic_auto_timestamp()
    print("✓ test_append_diagnostic_auto_timestamp")
    
    test_load_diagnostics_basic()
    print("✓ test_load_diagnostics_basic")
    
    test_load_diagnostics_with_limit()
    print("✓ test_load_diagnostics_with_limit")
    
    test_load_diagnostics_nonexistent()
    print("✓ test_load_diagnostics_nonexistent")
    
    test_build_diagnostic_record()
    print("✓ test_build_diagnostic_record")
    
    test_build_diagnostic_record_with_none()
    print("✓ test_build_diagnostic_record_with_none")
    
    test_error_handling()
    print("✓ test_error_handling")
    
    test_multiple_strategies_per_symbol()
    print("✓ test_multiple_strategies_per_symbol")
    
    print("\nAll tests passed! ✓")
