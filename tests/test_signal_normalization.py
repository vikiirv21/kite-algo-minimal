#!/usr/bin/env python3
"""
Test script to verify signal normalization in trade_recorder.py.

This script tests:
1. normalize_signal_for_csv() with various inputs
2. log_signal properly normalizes signal values
3. log_fused_signal properly normalizes action values
4. signals.csv only contains BUY, SELL, HOLD, UNKNOWN values
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

from analytics.trade_recorder import TradeRecorder, normalize_signal_for_csv


def test_normalize_signal_for_csv():
    """Test the normalize_signal_for_csv function with various inputs."""
    print("=" * 80)
    print("TEST: normalize_signal_for_csv function")
    print("=" * 80)
    
    test_cases = [
        # (input, expected_output)
        (None, "UNKNOWN"),
        ("", "UNKNOWN"),
        (0, "UNKNOWN"),
        ("0", "UNKNOWN"),
        ("NaN", "UNKNOWN"),
        ("None", "UNKNOWN"),
        ("regime=UNKNOWN", "UNKNOWN"),
        ("REGIME=HIGH", "UNKNOWN"),
        (" regime=LOW", "UNKNOWN"),
        ("BUY", "BUY"),
        ("buy", "BUY"),
        (" BUY ", "BUY"),
        ("SELL", "SELL"),
        ("sell", "SELL"),
        ("HOLD", "HOLD"),
        ("hold", "HOLD"),
        ("UNKNOWN", "UNKNOWN"),
        ("invalid_signal", "UNKNOWN"),
        (123, "UNKNOWN"),
        ("WAIT", "UNKNOWN"),
    ]
    
    passed = 0
    failed = 0
    
    for input_val, expected in test_cases:
        result = normalize_signal_for_csv(input_val)
        status = "✓" if result == expected else "✗"
        if result == expected:
            passed += 1
        else:
            failed += 1
        print(f"{status} normalize_signal_for_csv({input_val!r}) = {result!r} (expected: {expected!r})")
    
    print(f"\nPassed: {passed}/{len(test_cases)}")
    if failed > 0:
        print(f"Failed: {failed}/{len(test_cases)}")
        return False
    return True


def test_log_signal_normalization():
    """Test that log_signal properly normalizes signal values."""
    print("\n" + "=" * 80)
    print("TEST: log_signal normalization")
    print("=" * 80)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        recorder = TradeRecorder(base_dir=tmpdir)
        
        # Test various signal values
        test_signals = [
            ("BUY", "BUY"),
            ("SELL", "SELL"),
            ("HOLD", "HOLD"),
            (None, "UNKNOWN"),
            ("", "UNKNOWN"),
            (0, "UNKNOWN"),
            ("regime=UNKNOWN", "UNKNOWN"),
            ("INVALID", "UNKNOWN"),
        ]
        
        for input_signal, expected_signal in test_signals:
            signal_id = recorder.log_signal(
                logical="TEST_LOGICAL",
                symbol="TESTSTOCK",
                price=100.0,
                signal=input_signal,
                tf="5m",
                reason="test_normalization",
                profile="INTRADAY"
            )
            print(f"✓ Logged signal with input={input_signal!r}, signal_id={signal_id}")
        
        # Verify all signals were normalized in the CSV
        signals_path = os.path.join(tmpdir, "artifacts", "signals.csv")
        with open(signals_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        print(f"\nVerifying {len(rows)} signals in CSV...")
        
        all_valid = True
        for i, row in enumerate(rows):
            signal = row["signal"]
            if signal not in ("BUY", "SELL", "HOLD", "UNKNOWN"):
                print(f"✗ Row {i}: Invalid signal value: {signal!r}")
                all_valid = False
            else:
                print(f"✓ Row {i}: Valid signal: {signal}")
        
        if all_valid:
            print("\n✓ All signals properly normalized!")
            return True
        else:
            print("\n✗ Some signals were not properly normalized")
            return False


def test_log_fused_signal_normalization():
    """Test that log_fused_signal properly normalizes action values."""
    print("\n" + "=" * 80)
    print("TEST: log_fused_signal normalization")
    print("=" * 80)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        recorder = TradeRecorder(base_dir=tmpdir)
        
        # Test various action values
        test_actions = [
            ("BUY", "BUY"),
            ("SELL", "SELL"),
            ("HOLD", "HOLD"),
            (None, "UNKNOWN"),
            ("", "UNKNOWN"),
            ("regime=HIGH", "UNKNOWN"),
        ]
        
        for input_action, expected_action in test_actions:
            signal_id = recorder.log_fused_signal(
                symbol="TESTSTOCK",
                price=100.0,
                action=input_action,
                confidence=0.8,
                setup="TEST_SETUP",
                fuse_reason="test",
                multi_tf_status="aligned",
                num_strategies=2,
                strategy_codes=["S1", "S2"]
            )
            print(f"✓ Logged fused signal with action={input_action!r}, signal_id={signal_id}")
        
        # Verify all actions were normalized in the CSV
        signals_path = os.path.join(tmpdir, "artifacts", "signals_fused.csv")
        with open(signals_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        print(f"\nVerifying {len(rows)} fused signals in CSV...")
        
        all_valid = True
        for i, row in enumerate(rows):
            action = row["action"]
            if action not in ("BUY", "SELL", "HOLD", "UNKNOWN"):
                print(f"✗ Row {i}: Invalid action value: {action!r}")
                all_valid = False
            else:
                print(f"✓ Row {i}: Valid action: {action}")
        
        if all_valid:
            print("\n✓ All actions properly normalized!")
            return True
        else:
            print("\n✗ Some actions were not properly normalized")
            return False


def main():
    """Run all signal normalization tests."""
    print("Starting signal normalization tests...\n")
    
    results = []
    
    # Test 1: normalize_signal_for_csv function
    results.append(("normalize_signal_for_csv", test_normalize_signal_for_csv()))
    
    # Test 2: log_signal normalization
    results.append(("log_signal normalization", test_log_signal_normalization()))
    
    # Test 3: log_fused_signal normalization
    results.append(("log_fused_signal normalization", test_log_fused_signal_normalization()))
    
    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    
    all_passed = True
    for test_name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"{status}: {test_name}")
        if not passed:
            all_passed = False
    
    if all_passed:
        print("\n✓ All tests passed!")
        return 0
    else:
        print("\n✗ Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
