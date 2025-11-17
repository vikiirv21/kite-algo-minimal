#!/usr/bin/env python3
"""
Test script to verify trade_recorder.py handles None and invalid price values robustly.

This script tests:
1. log_signal with price=None
2. log_signal with invalid price values (string, list, etc.)
3. Ensuring signals are still logged even when price conversion fails
4. Verifying no exceptions crash the recorder
"""

from __future__ import annotations

import sys
import csv
import os
import tempfile
from pathlib import Path

# Add project root to path
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from analytics.trade_recorder import TradeRecorder


def test_log_signal_with_none_price():
    """Test that log_signal handles None price gracefully."""
    print("=" * 80)
    print("TEST: log_signal with None price")
    print("=" * 80)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        recorder = TradeRecorder(base_dir=tmpdir)
        
        # Call log_signal with None price - should not raise exception
        signal_id = recorder.log_signal(
            logical="TEST_LOGICAL",
            symbol="RELIANCE",
            price=None,
            signal="BUY",
            tf="5m",
            reason="test_none_price",
            profile="INTRADAY"
        )
        
        print(f"✓ Signal logged with signal_id: {signal_id}")
        
        # Verify the signal was written to CSV
        signals_path = os.path.join(tmpdir, "artifacts", "signals.csv")
        assert os.path.exists(signals_path), "signals.csv should exist"
        
        with open(signals_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            
        assert len(rows) == 1, "Should have exactly one signal"
        signal = rows[0]
        assert signal["signal_id"] == signal_id
        assert signal["symbol"] == "RELIANCE"
        assert signal["signal"] == "BUY"
        assert signal["price"] == "", "Price should be empty string when None"
        
        print("✓ Signal recorded correctly with empty price field")
        print()


def test_log_signal_with_invalid_price():
    """Test that log_signal handles invalid price values gracefully."""
    print("=" * 80)
    print("TEST: log_signal with invalid price values")
    print("=" * 80)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        recorder = TradeRecorder(base_dir=tmpdir)
        
        # Test with string that cannot be converted
        signal_id1 = recorder.log_signal(
            logical="TEST_LOGICAL",
            symbol="TCS",
            price="invalid_string",
            signal="SELL",
            tf="5m",
            reason="test_invalid_string",
            profile="INTRADAY"
        )
        print(f"✓ Signal logged with invalid string price, signal_id: {signal_id1}")
        
        # Test with list (should fail conversion)
        signal_id2 = recorder.log_signal(
            logical="TEST_LOGICAL",
            symbol="INFY",
            price=[100, 200],
            signal="BUY",
            tf="5m",
            reason="test_list_price",
            profile="INTRADAY"
        )
        print(f"✓ Signal logged with list price, signal_id: {signal_id2}")
        
        # Verify signals were written to CSV
        signals_path = os.path.join(tmpdir, "artifacts", "signals.csv")
        with open(signals_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        assert len(rows) == 2, "Should have exactly two signals"
        
        # Both signals should have empty price fields
        for idx, row in enumerate(rows):
            assert row["price"] == "", f"Signal {idx+1} should have empty price field"
            print(f"✓ Signal {idx+1} ({row['symbol']}) recorded with empty price field")
        
        print()


def test_log_signal_with_valid_price():
    """Test that log_signal still works correctly with valid prices."""
    print("=" * 80)
    print("TEST: log_signal with valid price values")
    print("=" * 80)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        recorder = TradeRecorder(base_dir=tmpdir)
        
        # Test with float
        signal_id1 = recorder.log_signal(
            logical="TEST_LOGICAL",
            symbol="RELIANCE",
            price=2500.50,
            signal="BUY",
            tf="5m",
            reason="test_float_price",
            profile="INTRADAY"
        )
        
        # Test with int
        signal_id2 = recorder.log_signal(
            logical="TEST_LOGICAL",
            symbol="TCS",
            price=3500,
            signal="SELL",
            tf="5m",
            reason="test_int_price",
            profile="INTRADAY"
        )
        
        # Test with string that can be converted
        signal_id3 = recorder.log_signal(
            logical="TEST_LOGICAL",
            symbol="INFY",
            price="1500.75",
            signal="BUY",
            tf="5m",
            reason="test_string_price",
            profile="INTRADAY"
        )
        
        print(f"✓ Signal logged with float price, signal_id: {signal_id1}")
        print(f"✓ Signal logged with int price, signal_id: {signal_id2}")
        print(f"✓ Signal logged with convertible string price, signal_id: {signal_id3}")
        
        # Verify signals were written to CSV
        signals_path = os.path.join(tmpdir, "artifacts", "signals.csv")
        with open(signals_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        assert len(rows) == 3, "Should have exactly three signals"
        
        # Check prices were converted correctly
        assert rows[0]["price"] == "2500.5", "Float price should be 2500.5"
        assert rows[1]["price"] == "3500.0", "Int price should be 3500.0"
        assert rows[2]["price"] == "1500.75", "String price should be 1500.75"
        
        print("✓ All prices converted and recorded correctly")
        print()


def test_record_signal_with_none_price():
    """Test that record_signal (legacy method) handles None price."""
    print("=" * 80)
    print("TEST: record_signal with None price")
    print("=" * 80)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        recorder = TradeRecorder(base_dir=tmpdir)
        
        # Call record_signal with None price
        signal_id = recorder.record_signal(
            logical="TEST_LOGICAL",
            symbol="RELIANCE",
            price=None,
            signal="BUY"
        )
        
        print(f"✓ Signal logged with signal_id: {signal_id}")
        
        # Verify the signal was written
        signals_path = os.path.join(tmpdir, "artifacts", "signals.csv")
        with open(signals_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        assert len(rows) == 1, "Should have exactly one signal"
        assert rows[0]["price"] == "", "Price should be empty string"
        
        print("✓ record_signal handled None price correctly")
        print()


def test_all_fields_logged_despite_invalid_price():
    """Test that all other fields are logged even when price is invalid."""
    print("=" * 80)
    print("TEST: All fields logged despite invalid price")
    print("=" * 80)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        recorder = TradeRecorder(base_dir=tmpdir)
        
        # Log signal with invalid price but all other fields populated
        signal_id = recorder.log_signal(
            logical="TEST_LOGICAL",
            symbol="RELIANCE",
            price="INVALID",
            signal="BUY",
            tf="5m",
            reason="comprehensive_test",
            profile="INTRADAY",
            mode="LIVE",
            confidence=0.85,
            trend_context="UPTREND",
            vol_regime="HIGH",
            htf_trend="BULLISH",
            playbook="BREAKOUT",
            setup_type="MOMENTUM",
            ema20=2480.0,
            ema50=2450.0,
            ema100=2420.0,
            ema200=2400.0,
            rsi14=65.5,
            atr=50.25,
            adx14=25.0,
            vwap=2485.0,
            rel_volume=1.5,
            vol_spike=True,
            strategy="TREND_FOLLOW"
        )
        
        print(f"✓ Signal logged with signal_id: {signal_id}")
        
        # Verify all fields except price are populated
        signals_path = os.path.join(tmpdir, "artifacts", "signals.csv")
        with open(signals_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        assert len(rows) == 1, "Should have exactly one signal"
        signal = rows[0]
        
        # Check key fields are populated
        assert signal["symbol"] == "RELIANCE"
        assert signal["signal"] == "BUY"
        assert signal["price"] == "", "Price should be empty"
        assert signal["tf"] == "5m"
        assert signal["mode"] == "LIVE"
        assert signal["confidence"] == "0.85"
        assert signal["trend_context"] == "UPTREND"
        assert signal["vol_regime"] == "HIGH"
        assert signal["ema20"] == "2480.0"
        assert signal["strategy"] == "TREND_FOLLOW"
        
        print("✓ All fields logged correctly despite invalid price")
        print()


def main():
    """Run all tests."""
    print("\n" + "=" * 80)
    print("TRADE RECORDER ROBUSTNESS TESTS")
    print("=" * 80 + "\n")
    
    try:
        test_log_signal_with_none_price()
        test_log_signal_with_invalid_price()
        test_log_signal_with_valid_price()
        test_record_signal_with_none_price()
        test_all_fields_logged_despite_invalid_price()
        
        print("=" * 80)
        print("ALL TESTS PASSED!")
        print("=" * 80)
        return 0
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
