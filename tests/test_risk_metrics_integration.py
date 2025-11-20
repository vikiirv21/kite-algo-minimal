#!/usr/bin/env python3
"""
Integration test for Risk Metrics API endpoints.
Tests the functions directly without requiring a running server.
"""

import sys
import json
import yaml
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from analytics.risk_metrics import load_risk_limits, compute_risk_breaches, compute_var


def test_load_risk_limits():
    """Test load_risk_limits function."""
    print("\n" + "="*70)
    print("TEST: load_risk_limits()")
    print("="*70)
    
    # Load config
    config_path = Path('configs/dev.yaml')
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    # Load overrides
    overrides_path = Path('configs/learned_overrides.yaml')
    overrides = None
    if overrides_path.exists():
        with open(overrides_path, 'r') as f:
            overrides = yaml.safe_load(f)
    
    # Test without overrides
    limits = load_risk_limits(config, None)
    
    print("✓ Limits loaded successfully (no overrides)")
    print(f"  Mode: {limits['mode']}")
    print(f"  Capital: {limits['capital']}")
    print(f"  Limits keys: {list(limits['limits'].keys())}")
    
    assert limits['mode'] in ['paper', 'live'], "Invalid mode"
    assert limits['capital'] > 0, "Capital should be positive"
    assert 'max_daily_loss_rupees' in limits['limits'], "Missing max_daily_loss_rupees"
    assert 'max_exposure_pct' in limits['limits'], "Missing max_exposure_pct"
    
    # Test with overrides
    if overrides:
        limits_with_overrides = load_risk_limits(config, overrides)
        print("\n✓ Limits loaded successfully (with overrides)")
        print(f"  Source overrides file: {limits_with_overrides['source']['overrides_file']}")
    
    print("\n✓ PASSED: load_risk_limits()")
    return True


def test_compute_risk_breaches():
    """Test compute_risk_breaches function."""
    print("\n" + "="*70)
    print("TEST: compute_risk_breaches()")
    print("="*70)
    
    # Load config
    config_path = Path('configs/dev.yaml')
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    runtime_metrics_path = Path('artifacts/analytics/runtime_metrics.json')
    checkpoint_path = Path('artifacts/checkpoints/runtime_state_latest.json')
    
    # Try alternative checkpoint names
    if not checkpoint_path.exists():
        checkpoint_path = Path('artifacts/checkpoints/paper_state_latest.json')
    
    orders_path = Path('artifacts/orders.csv')
    
    result = compute_risk_breaches(
        config=config,
        runtime_metrics_path=runtime_metrics_path,
        checkpoint_path=checkpoint_path,
        orders_path=orders_path,
        mode='paper'
    )
    
    print("✓ Breaches computed successfully")
    print(f"  Mode: {result['mode']}")
    print(f"  AsOf: {result['asof']}")
    print(f"  Breaches count: {len(result['breaches'])}")
    
    if result['breaches']:
        print("\n  Active breaches:")
        for breach in result['breaches']:
            print(f"    - [{breach['severity']}] {breach['id']}: {breach['message']}")
    else:
        print("  No breaches detected ✓")
    
    assert 'mode' in result, "Missing mode in result"
    assert 'asof' in result, "Missing asof in result"
    assert 'breaches' in result, "Missing breaches in result"
    assert isinstance(result['breaches'], list), "Breaches should be a list"
    
    print("\n✓ PASSED: compute_risk_breaches()")
    return True


def test_compute_var():
    """Test compute_var function."""
    print("\n" + "="*70)
    print("TEST: compute_var()")
    print("="*70)
    
    orders_path = Path('artifacts/orders.csv')
    
    # Test with default confidence
    result = compute_var(
        orders_path=orders_path,
        capital=500000.0,
        confidence=0.95,
        mode='paper'
    )
    
    print("✓ VaR computed successfully (confidence=0.95)")
    print(f"  Mode: {result['mode']}")
    print(f"  Confidence: {result['confidence']}")
    print(f"  Status: {result['status']}")
    print(f"  Sample trades: {result['sample_trades']}")
    print(f"  VaR (rupees): {result['var_rupees']:.2f}")
    print(f"  VaR (%): {result['var_pct']:.4%}")
    
    assert 'status' in result, "Missing status in result"
    assert result['status'] in ['ok', 'insufficient_data', 'error'], "Invalid status"
    assert 'var_rupees' in result, "Missing var_rupees in result"
    assert 'var_pct' in result, "Missing var_pct in result"
    
    # Test with different confidence
    result_99 = compute_var(
        orders_path=orders_path,
        capital=500000.0,
        confidence=0.99,
        mode='paper'
    )
    
    print("\n✓ VaR computed successfully (confidence=0.99)")
    print(f"  VaR (rupees): {result_99['var_rupees']:.2f}")
    
    print("\n✓ PASSED: compute_var()")
    return True


def test_override_update_logic():
    """Test override update logic (without actually writing file)."""
    print("\n" + "="*70)
    print("TEST: Override update logic")
    print("="*70)
    
    # Load config
    config_path = Path('configs/dev.yaml')
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    # Simulate creating overrides structure
    overrides = {}
    
    updates = {
        "max_daily_loss_rupees": 7000.0,
        "max_trades_per_day": 150,
        "max_exposure_pct": 0.9,
    }
    
    allowed_fields = {
        "max_daily_loss_rupees": ("execution", "circuit_breakers"),
        "max_trades_per_day": ("execution", "circuit_breakers"),
        "max_exposure_pct": ("portfolio",),
    }
    
    for key, value in updates.items():
        path = allowed_fields[key]
        
        # Navigate to nested dict location
        current = overrides
        for section in path[:-1]:
            if section not in current:
                current[section] = {}
            current = current[section]
        
        # Set the value
        if len(path) == 1:
            if path[0] not in overrides:
                overrides[path[0]] = {}
            overrides[path[0]][key] = value
        else:
            final_section = path[-1]
            if final_section not in current:
                current[final_section] = {}
            current[final_section][key] = value
    
    print("✓ Override structure created")
    print(f"  Updates: {list(updates.keys())}")
    
    # Verify overrides can be applied
    limits = load_risk_limits(config, overrides)
    
    print("\n✓ Overrides applied successfully")
    print(f"  max_daily_loss_rupees: {limits['limits']['max_daily_loss_rupees']} (expected: 7000.0)")
    print(f"  max_trades_per_day: {limits['limits']['max_trades_per_day']} (expected: 150)")
    print(f"  max_exposure_pct: {limits['limits']['max_exposure_pct']} (expected: 0.9)")
    
    assert limits['limits']['max_daily_loss_rupees'] == 7000.0, "Override not applied"
    assert limits['limits']['max_trades_per_day'] == 150, "Override not applied"
    assert limits['limits']['max_exposure_pct'] == 0.9, "Override not applied"
    
    print("\n✓ PASSED: Override update logic")
    return True


def main():
    """Run all tests."""
    print("\n" + "="*70)
    print("RISK METRICS API - INTEGRATION TESTS")
    print("="*70)
    
    tests = [
        test_load_risk_limits,
        test_compute_risk_breaches,
        test_compute_var,
        test_override_update_logic,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"\n✗ FAILED: {test.__name__}")
            print(f"  Error: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "="*70)
    print(f"TEST SUMMARY: {passed} passed, {failed} failed")
    print("="*70)
    
    if failed > 0:
        sys.exit(1)
    else:
        print("\n✓ ALL TESTS PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
