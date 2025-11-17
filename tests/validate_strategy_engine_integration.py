"""
Validation script for StrategyEngineV2 integration with PaperEngine.

This script validates:
1. Config-driven initialization (v1 vs v2)
2. Backward compatibility with existing APIs
3. Signal/order journal format compatibility
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_config_loading():
    """Test that config loads with strategy_engine settings."""
    from core.config import AppConfig
    
    # Load dev config
    config_path = Path(__file__).parent.parent / "configs" / "dev.yaml"
    cfg = AppConfig.from_yaml(config_path)
    
    # Check strategy_engine config exists
    assert "strategy_engine" in cfg.raw, "strategy_engine config missing"
    
    strategy_config = cfg.raw["strategy_engine"]
    assert "version" in strategy_config, "strategy_engine.version missing"
    assert "enabled" in strategy_config, "strategy_engine.enabled missing"
    
    print("✓ Config loading: strategy_engine configuration is valid")
    return True


def test_strategy_engine_v1_default():
    """Test that v1 (StrategyRunner) is used by default."""
    from core.config import AppConfig
    
    config_path = Path(__file__).parent.parent / "configs" / "dev.yaml"
    cfg = AppConfig.from_yaml(config_path)
    
    # Check default version is 1
    version = cfg.raw.get("strategy_engine", {}).get("version", 1)
    assert version == 1, f"Expected version 1 by default, got {version}"
    
    print("✓ Default behavior: strategy_engine.version defaults to 1 (v1)")
    return True


def test_strategy_engine_imports():
    """Test that all strategy engine components can be imported."""
    try:
        from core.strategy_engine import StrategyRunner
        from core.strategy_engine_v2 import (
            StrategyEngineV2,
            StrategyState,
            OrderIntent,
            StrategySignal,
            BaseStrategy,
        )
        print("✓ Imports: All strategy engine components imported successfully")
        return True
    except ImportError as e:
        print(f"✗ Imports: Failed to import strategy engine components: {e}")
        return False


def test_strategy_state_api():
    """Test that StrategyState has expected API."""
    from core.strategy_engine_v2 import StrategyState
    
    state = StrategyState()
    
    # Test position tracking methods
    assert hasattr(state, "is_position_open"), "Missing is_position_open method"
    assert hasattr(state, "is_long"), "Missing is_long method"
    assert hasattr(state, "is_short"), "Missing is_short method"
    assert hasattr(state, "update_position"), "Missing update_position method"
    
    # Test PnL tracking methods (new in v2)
    assert hasattr(state, "record_decision"), "Missing record_decision method"
    assert hasattr(state, "update_pnl"), "Missing update_pnl method"
    
    # Test attributes
    assert hasattr(state, "trades_today"), "Missing trades_today attribute"
    assert hasattr(state, "win_streak"), "Missing win_streak attribute"
    assert hasattr(state, "loss_streak"), "Missing loss_streak attribute"
    assert hasattr(state, "recent_pnl"), "Missing recent_pnl attribute"
    assert hasattr(state, "recent_decisions"), "Missing recent_decisions attribute"
    
    print("✓ API: StrategyState has all expected methods and attributes")
    return True


def test_strategy_engine_v2_api():
    """Test that StrategyEngineV2 has expected API."""
    from core.strategy_engine_v2 import StrategyEngineV2
    
    # Check expected methods exist
    expected_methods = [
        "register_strategy",
        "set_paper_engine",
        "compute_indicators",
        "run_strategy",
        "run",
        "normalize_signal",
        "filter_signal_basic",
        "filter_signal_risk",
        "resolve_conflicts",
        "generate_decisions",
        "on_candle_close",
    ]
    
    for method_name in expected_methods:
        assert hasattr(StrategyEngineV2, method_name), f"Missing method: {method_name}"
    
    print("✓ API: StrategyEngineV2 has all expected methods")
    return True


def test_decision_compatibility():
    """Test that Decision objects from strategies are compatible."""
    from strategies.base import Decision
    
    # Create decision
    decision = Decision(action="BUY", reason="test_reason", confidence=0.8)
    
    # Test attributes
    assert hasattr(decision, "action"), "Missing action attribute"
    assert hasattr(decision, "reason"), "Missing reason attribute"
    assert hasattr(decision, "confidence"), "Missing confidence attribute"
    
    assert decision.action == "BUY"
    assert decision.reason == "test_reason"
    assert decision.confidence == 0.8
    
    print("✓ Compatibility: Decision objects maintain expected structure")
    return True


def test_order_intent_structure():
    """Test OrderIntent structure for execution."""
    from core.strategy_engine_v2 import OrderIntent
    
    intent = OrderIntent(
        symbol="NIFTY",
        action="BUY",
        qty=1,
        reason="test_reason",
        strategy_code="test_strategy",
        confidence=0.8,
        metadata={"key": "value"}
    )
    
    # Test attributes
    assert intent.symbol == "NIFTY"
    assert intent.action == "BUY"
    assert intent.qty == 1
    assert intent.reason == "test_reason"
    assert intent.strategy_code == "test_strategy"
    assert intent.confidence == 0.8
    assert intent.metadata["key"] == "value"
    
    # Test to_dict for serialization
    d = intent.to_dict()
    assert d["symbol"] == "NIFTY"
    assert d["action"] == "BUY"
    
    print("✓ Data Model: OrderIntent has expected structure and serialization")
    return True


def test_strategy_signal_structure():
    """Test StrategySignal structure for filtering."""
    from core.strategy_engine_v2 import StrategySignal
    from datetime import datetime, timezone
    
    signal = StrategySignal(
        timestamp=datetime.utcnow().replace(tzinfo=timezone.utc),
        symbol="NIFTY",
        strategy_name="test_strategy",
        direction="long",
        strength=0.8,
        tags={"reason": "test_reason"}
    )
    
    # Test attributes
    assert signal.symbol == "NIFTY"
    assert signal.strategy_name == "test_strategy"
    assert signal.direction == "long"
    assert signal.strength == 0.8
    assert signal.tags["reason"] == "test_reason"
    
    # Test to_dict for serialization
    d = signal.to_dict()
    assert d["symbol"] == "NIFTY"
    assert d["direction"] == "long"
    
    print("✓ Data Model: StrategySignal has expected structure and serialization")
    return True


def run_validation():
    """Run all validation tests."""
    print("=" * 60)
    print("StrategyEngineV2 Integration Validation")
    print("=" * 60)
    print()
    
    tests = [
        ("Config Loading", test_config_loading),
        ("Default Behavior", test_strategy_engine_v1_default),
        ("Import Tests", test_strategy_engine_imports),
        ("StrategyState API", test_strategy_state_api),
        ("StrategyEngineV2 API", test_strategy_engine_v2_api),
        ("Decision Compatibility", test_decision_compatibility),
        ("OrderIntent Structure", test_order_intent_structure),
        ("StrategySignal Structure", test_strategy_signal_structure),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        print(f"\nRunning: {test_name}")
        print("-" * 60)
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
                print(f"✗ {test_name}: Test returned False")
        except Exception as e:
            failed += 1
            print(f"✗ {test_name}: {e}")
            import traceback
            traceback.print_exc()
    
    print()
    print("=" * 60)
    print(f"Validation Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = run_validation()
    sys.exit(0 if success else 1)
