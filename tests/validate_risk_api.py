#!/usr/bin/env python3
"""
Manual validation of Risk API endpoints logic.
Tests the endpoint logic without requiring a running server.
"""

import sys
import json
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def simulate_get_risk_limits():
    """Simulate GET /api/risk/limits endpoint."""
    print("\n" + "="*70)
    print("SIMULATE: GET /api/risk/limits")
    print("="*70)
    
    import yaml
    from analytics.risk_metrics import load_risk_limits
    from core.config import LEARNED_OVERRIDES_PATH
    
    config_path = Path('configs/dev.yaml')
    
    # Load config
    config = {}
    if config_path.exists():
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f) or {}
    
    # Load overrides
    overrides = None
    if LEARNED_OVERRIDES_PATH.exists():
        with open(LEARNED_OVERRIDES_PATH, 'r') as f:
            overrides = yaml.safe_load(f) or {}
    
    # Call function
    limits = load_risk_limits(config, overrides)
    
    print("\nResponse:")
    print(json.dumps(limits, indent=2))
    
    # Validate response structure
    assert 'mode' in limits
    assert 'capital' in limits
    assert 'limits' in limits
    assert 'source' in limits
    
    print("\n✓ Response structure valid")
    return limits


def simulate_get_risk_breaches():
    """Simulate GET /api/risk/breaches endpoint."""
    print("\n" + "="*70)
    print("SIMULATE: GET /api/risk/breaches")
    print("="*70)
    
    import yaml
    from analytics.risk_metrics import compute_risk_breaches
    
    config_path = Path('configs/dev.yaml')
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    mode = config.get("trading", {}).get("mode", "paper")
    base_dir = Path('.')
    
    runtime_metrics_path = base_dir / "artifacts" / "analytics" / "runtime_metrics.json"
    checkpoint_path = base_dir / "artifacts" / "checkpoints" / "paper_state_latest.json"
    
    if not checkpoint_path.exists():
        checkpoint_path = base_dir / "artifacts" / "checkpoints" / "runtime_state_latest.json"
    
    orders_path = base_dir / "artifacts" / "orders.csv"
    
    # Call function
    result = compute_risk_breaches(
        config=config,
        runtime_metrics_path=runtime_metrics_path,
        checkpoint_path=checkpoint_path,
        orders_path=orders_path,
        mode=mode,
    )
    
    print("\nResponse:")
    print(json.dumps(result, indent=2))
    
    # Validate response structure
    assert 'mode' in result
    assert 'asof' in result
    assert 'breaches' in result
    assert isinstance(result['breaches'], list)
    
    print("\n✓ Response structure valid")
    return result


def simulate_get_risk_var():
    """Simulate GET /api/risk/var endpoint."""
    print("\n" + "="*70)
    print("SIMULATE: GET /api/risk/var (confidence=0.95)")
    print("="*70)
    
    import yaml
    from analytics.risk_metrics import compute_var
    
    config_path = Path('configs/dev.yaml')
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    capital = float(config.get("trading", {}).get("paper_capital", 500000))
    orders_path = Path("artifacts/orders.csv")
    mode = config.get("trading", {}).get("mode", "paper")
    
    # Call function
    result = compute_var(
        orders_path=orders_path,
        capital=capital,
        confidence=0.95,
        mode=mode,
    )
    
    print("\nResponse:")
    print(json.dumps(result, indent=2))
    
    # Validate response structure
    assert 'mode' in result
    assert 'confidence' in result
    assert 'var_rupees' in result
    assert 'var_pct' in result
    assert 'sample_trades' in result
    assert 'status' in result
    
    print("\n✓ Response structure valid")
    return result


def simulate_post_risk_limits():
    """Simulate POST /api/risk/limits endpoint logic (without actually writing)."""
    print("\n" + "="*70)
    print("SIMULATE: POST /api/risk/limits")
    print("="*70)
    
    import yaml
    from analytics.risk_metrics import load_risk_limits
    from core.config import LEARNED_OVERRIDES_PATH
    
    # Simulate payload
    payload = {
        "max_daily_loss_rupees": 6500.0,
        "max_trades_per_day": 125,
    }
    
    print(f"\nPayload:")
    print(json.dumps(payload, indent=2))
    
    # Validate payload
    allowed_fields = {
        "max_daily_loss_rupees": ("execution", "circuit_breakers"),
        "max_daily_drawdown_pct": ("execution", "circuit_breakers"),
        "max_trades_per_day": ("execution", "circuit_breakers"),
        "max_trades_per_strategy_per_day": ("execution", "circuit_breakers"),
        "max_loss_streak": ("execution", "circuit_breakers"),
        "max_exposure_pct": ("portfolio",),
        "max_leverage": ("portfolio",),
        "max_risk_per_trade_pct": ("portfolio",),
        "per_symbol_max_loss": ("trading",),
        "max_open_positions": ("trading",),
    }
    
    updates = {}
    for key, value in payload.items():
        if key not in allowed_fields:
            print(f"  ✗ Ignoring invalid field: {key}")
            continue
        
        # Type validation
        if key in ["max_trades_per_day", "max_trades_per_strategy_per_day", "max_loss_streak"]:
            value = int(value)
            if value <= 0:
                print(f"  ✗ Invalid value for {key}: must be positive")
                continue
        else:
            value = float(value)
            if value < 0:
                print(f"  ✗ Invalid value for {key}: must be non-negative")
                continue
        
        updates[key] = value
        print(f"  ✓ Validated {key} = {value}")
    
    # Load existing overrides (read-only for simulation)
    overrides = {}
    if LEARNED_OVERRIDES_PATH.exists():
        with open(LEARNED_OVERRIDES_PATH, 'r') as f:
            overrides = yaml.safe_load(f) or {}
    
    # Apply updates to structure
    for key, value in updates.items():
        path = allowed_fields[key]
        
        current = overrides
        for section in path[:-1]:
            if section not in current:
                current[section] = {}
            current = current[section]
        
        if len(path) == 1:
            if path[0] not in overrides:
                overrides[path[0]] = {}
            overrides[path[0]][key] = value
        else:
            final_section = path[-1]
            if final_section not in current:
                current[final_section] = {}
            current[final_section][key] = value
    
    # Load config and apply overrides
    config_path = Path('configs/dev.yaml')
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    limits = load_risk_limits(config, overrides)
    
    # Verify updates
    print("\n✓ Updates applied successfully (simulation only)")
    print(f"  max_daily_loss_rupees: {limits['limits']['max_daily_loss_rupees']}")
    print(f"  max_trades_per_day: {limits['limits']['max_trades_per_day']}")
    
    assert limits['limits']['max_daily_loss_rupees'] == 6500.0
    assert limits['limits']['max_trades_per_day'] == 125
    
    response = {
        "status": "ok",
        "limits": limits,
        "updated_fields": list(updates.keys()),
    }
    
    print("\nResponse (summary):")
    print(f"  status: {response['status']}")
    print(f"  updated_fields: {response['updated_fields']}")
    
    return response


def main():
    """Run all endpoint simulations."""
    print("\n" + "="*70)
    print("RISK API ENDPOINTS - MANUAL VALIDATION")
    print("="*70)
    
    simulations = [
        simulate_get_risk_limits,
        simulate_get_risk_breaches,
        simulate_get_risk_var,
        simulate_post_risk_limits,
    ]
    
    passed = 0
    failed = 0
    
    for simulation in simulations:
        try:
            simulation()
            passed += 1
        except Exception as e:
            print(f"\n✗ FAILED: {simulation.__name__}")
            print(f"  Error: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "="*70)
    print(f"VALIDATION SUMMARY: {passed} passed, {failed} failed")
    print("="*70)
    
    if failed > 0:
        sys.exit(1)
    else:
        print("\n✓ ALL VALIDATIONS PASSED")
        print("\nThe Risk API endpoints are ready for use!")
        print("\nTo test with a running server:")
        print("  1. Start dashboard: python -m uvicorn apps.dashboard:app --host 127.0.0.1 --port 8765")
        print("  2. Run manual test: python tests/manual_test_risk_api.py")
        sys.exit(0)


if __name__ == "__main__":
    main()
