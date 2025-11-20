"""
Tests for analytics/diagnostics.py

Tests the Strategy Real-Time Diagnostics Engine (SRDE) functionality.
"""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from analytics.diagnostics import (
    ensure_diagnostics_dir,
    path_for,
    append_diagnostic,
    load_diagnostics,
    build_diagnostic_record,
)


def test_ensure_diagnostics_dir():
    """Test that diagnostics directory is created."""
    diag_dir = ensure_diagnostics_dir()
    assert diag_dir is not None
    assert isinstance(diag_dir, Path)


def test_path_for():
    """Test path generation for symbol-strategy pairs."""
    path = path_for("NIFTY", "EMA_20_50")
    
    assert isinstance(path, Path)
    assert "NIFTY" in str(path)
    assert "EMA_20_50.jsonl" in str(path)
    
    # Test with special characters (should be sanitized)
    path2 = path_for("BANK/NIFTY", "RSI@MACD")
    assert "/" not in path2.name
    assert "@" not in path2.name


def test_build_diagnostic_record():
    """Test building a diagnostic record with all fields."""
    record = build_diagnostic_record(
        price=18500.50,
        decision="BUY",
        reason="Strong uptrend with EMA crossover",
        confidence=0.85,
        ema20=18480.0,
        ema50=18450.0,
        trend_strength=0.042,
        rr=2.5,
        regime="trend",
        risk_block="none",
    )
    
    assert record["price"] == 18500.50
    assert record["decision"] == "BUY"
    assert record["reason"] == "Strong uptrend with EMA crossover"
    assert record["confidence"] == 0.85
    assert record["ema20"] == 18480.0
    assert record["ema50"] == 18450.0
    assert record["trend_strength"] == 0.042
    assert record["rr"] == 2.5
    assert record["regime"] == "trend"
    assert record["risk_block"] == "none"
    assert "ts" in record


def test_build_diagnostic_record_minimal():
    """Test building a diagnostic record with minimal fields."""
    record = build_diagnostic_record(
        price=18500.0,
        decision="HOLD",
        reason="Low confidence",
    )
    
    assert record["price"] == 18500.0
    assert record["decision"] == "HOLD"
    assert record["reason"] == "Low confidence"
    assert record["confidence"] == 0.0
    assert record["risk_block"] == "none"
    assert "ts" in record


def test_append_and_load_diagnostics():
    """Test appending and loading diagnostic records."""
    # Use a temporary directory for testing
    with tempfile.TemporaryDirectory() as tmpdir:
        test_diag_dir = Path(tmpdir) / "diagnostics"
        
        # Patch the DIAGNOSTICS_DIR constant
        with patch('analytics.diagnostics.DIAGNOSTICS_DIR', test_diag_dir):
            symbol = "TEST_SYMBOL"
            strategy = "TEST_STRATEGY"
            
            # Create some test records
            records = [
                {
                    "ts": "2024-01-01T10:00:00Z",
                    "price": 100.0,
                    "decision": "BUY",
                    "reason": "Test buy signal",
                    "confidence": 0.8,
                    "ema20": 99.0,
                    "ema50": 98.0,
                    "risk_block": "none",
                },
                {
                    "ts": "2024-01-01T10:05:00Z",
                    "price": 101.0,
                    "decision": "HOLD",
                    "reason": "Waiting for confirmation",
                    "confidence": 0.5,
                    "ema20": 99.5,
                    "ema50": 98.5,
                    "risk_block": "none",
                },
                {
                    "ts": "2024-01-01T10:10:00Z",
                    "price": 102.0,
                    "decision": "SELL",
                    "reason": "Exit signal",
                    "confidence": 0.7,
                    "ema20": 100.0,
                    "ema50": 99.0,
                    "risk_block": "none",
                },
            ]
            
            # Append records
            for record in records:
                result = append_diagnostic(symbol, strategy, record)
                assert result is True
            
            # Load records
            loaded = load_diagnostics(symbol, strategy, limit=10)
            
            assert len(loaded) == 3
            # Records should be in reverse order (most recent first)
            assert loaded[0]["decision"] == "SELL"
            assert loaded[1]["decision"] == "HOLD"
            assert loaded[2]["decision"] == "BUY"


def test_load_nonexistent_diagnostics():
    """Test loading diagnostics when file doesn't exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_diag_dir = Path(tmpdir) / "diagnostics"
        
        with patch('analytics.diagnostics.DIAGNOSTICS_DIR', test_diag_dir):
            loaded = load_diagnostics("NONEXISTENT", "STRATEGY", limit=10)
            assert loaded == []


def test_append_diagnostic_limit():
    """Test that load_diagnostics respects the limit parameter."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_diag_dir = Path(tmpdir) / "diagnostics"
        
        with patch('analytics.diagnostics.DIAGNOSTICS_DIR', test_diag_dir):
            symbol = "TEST_LIMIT"
            strategy = "LIMIT_STRATEGY"
            
            # Append 10 records
            for i in range(10):
                record = {
                    "ts": f"2024-01-01T10:{i:02d}:00Z",
                    "price": 100.0 + i,
                    "decision": "HOLD",
                    "reason": f"Test record {i}",
                    "confidence": 0.5,
                    "risk_block": "none",
                }
                append_diagnostic(symbol, strategy, record)
            
            # Load only 5 records
            loaded = load_diagnostics(symbol, strategy, limit=5)
            assert len(loaded) == 5
            # Should get the most recent 5 records
            assert loaded[0]["price"] == 109.0  # Most recent
            assert loaded[4]["price"] == 105.0  # 5th most recent


def test_diagnostic_record_with_extra_fields():
    """Test that extra fields are included in diagnostic records."""
    record = build_diagnostic_record(
        price=18500.0,
        decision="BUY",
        reason="Test",
        rsi14=65.0,
        atr14=50.0,
        custom_field="custom_value",
    )
    
    assert record["rsi14"] == 65.0
    assert record["atr14"] == 50.0
    assert record["custom_field"] == "custom_value"


def test_append_diagnostic_error_handling():
    """Test that append_diagnostic handles errors gracefully."""
    # Try to append with invalid data (should not crash)
    with tempfile.TemporaryDirectory() as tmpdir:
        test_diag_dir = Path(tmpdir) / "diagnostics"
        
        with patch('analytics.diagnostics.DIAGNOSTICS_DIR', test_diag_dir):
            # Create a read-only directory to force a write error
            symbol_dir = test_diag_dir / "TEST"
            symbol_dir.mkdir(parents=True, exist_ok=True)
            
            # Make the parent directory read-only (will cause write to fail)
            import os
            original_mode = symbol_dir.stat().st_mode
            try:
                os.chmod(symbol_dir, 0o444)
                
                # This should fail but not crash
                result = append_diagnostic("TEST", "STRATEGY", {"ts": "test"})
                # Result may be True or False depending on OS permissions
                assert isinstance(result, bool)
            finally:
                # Restore permissions for cleanup
                os.chmod(symbol_dir, original_mode)


if __name__ == "__main__":
    # Run tests manually
    print("Running diagnostics tests...")
    
    test_ensure_diagnostics_dir()
    print("✓ test_ensure_diagnostics_dir")
    
    test_path_for()
    print("✓ test_path_for")
    
    test_build_diagnostic_record()
    print("✓ test_build_diagnostic_record")
    
    test_build_diagnostic_record_minimal()
    print("✓ test_build_diagnostic_record_minimal")
    
    test_append_and_load_diagnostics()
    print("✓ test_append_and_load_diagnostics")
    
    test_load_nonexistent_diagnostics()
    print("✓ test_load_nonexistent_diagnostics")
    
    test_append_diagnostic_limit()
    print("✓ test_append_diagnostic_limit")
    
    test_diagnostic_record_with_extra_fields()
    print("✓ test_diagnostic_record_with_extra_fields")
    
    test_append_diagnostic_error_handling()
    print("✓ test_append_diagnostic_error_handling")
    
    print("\nAll diagnostics tests passed! ✓")
