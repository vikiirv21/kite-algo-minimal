#!/usr/bin/env python3
"""
Smoke test for LIVE engine components.

Tests imports, instantiation, and basic functionality WITHOUT placing real orders.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

def test_imports():
    """Test that all components can be imported."""
    print("Testing imports...")
    
    try:
        from broker.kite_bridge import KiteBroker
        print("  ✅ KiteBroker imported")
    except Exception as e:
        print(f"  ❌ KiteBroker import failed: {e}")
        return False
    
    try:
        from engine.live_engine import LiveEngine
        print("  ✅ LiveEngine imported")
    except Exception as e:
        print(f"  ❌ LiveEngine import failed: {e}")
        return False
    
    try:
        from core.market_data_engine import MarketDataEngine
        print("  ✅ MarketDataEngine imported")
    except Exception as e:
        print(f"  ❌ MarketDataEngine import failed: {e}")
        return False
    
    try:
        from core.strategy_engine_v2 import StrategyEngineV2
        print("  ✅ StrategyEngineV2 imported")
    except Exception as e:
        print(f"  ❌ StrategyEngineV2 import failed: {e}")
        return False
    
    try:
        from core.risk_engine import RiskEngine
        print("  ✅ RiskEngine imported")
    except Exception as e:
        print(f"  ❌ RiskEngine import failed: {e}")
        return False
    
    return True


def test_kite_broker():
    """Test KiteBroker instantiation without login."""
    print("\nTesting KiteBroker...")
    
    try:
        from broker.kite_bridge import KiteBroker
        
        # Create broker (without login)
        broker = KiteBroker({})
        print("  ✅ KiteBroker instantiated")
        
        # Test that methods exist
        assert hasattr(broker, 'ensure_logged_in')
        assert hasattr(broker, 'place_order')
        assert hasattr(broker, 'modify_order')
        assert hasattr(broker, 'cancel_order')
        assert hasattr(broker, 'fetch_positions')
        assert hasattr(broker, 'fetch_open_orders')
        assert hasattr(broker, 'subscribe_ticks')
        print("  ✅ KiteBroker has all required methods")
        
        return True
    except Exception as e:
        print(f"  ❌ KiteBroker test failed: {e}")
        return False


def test_paper_engine_unchanged():
    """Verify that PaperEngine still works as expected."""
    print("\nTesting PaperEngine (unchanged)...")
    
    try:
        from broker.paper_broker import PaperBroker
        
        broker = PaperBroker()
        print("  ✅ PaperBroker instantiated")
        
        # Place order
        order = broker.place_order("TEST", "BUY", 10, 100.0)
        assert order.status == "FILLED"
        print(f"  ✅ Paper order placed: {order.status}")
        
        # Check position
        pos = broker.get_position("TEST")
        assert pos.quantity == 10
        assert pos.avg_price == 100.0
        print(f"  ✅ Position correct: qty={pos.quantity}, avg={pos.avg_price}")
        
        # Exit position
        exit_order = broker.place_order("TEST", "SELL", 10, 110.0)
        pos_after = broker.get_position("TEST")
        assert pos_after.quantity == 0
        assert pos_after.realized_pnl == 100.0  # (110-100)*10
        print(f"  ✅ Exit order correct: realized_pnl={pos_after.realized_pnl}")
        
        return True
    except Exception as e:
        print(f"  ❌ PaperEngine test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_mode_detection():
    """Test mode detection in config."""
    print("\nTesting mode detection...")
    
    try:
        from core.config import AppConfig
        
        # Test paper mode
        paper_config = AppConfig(raw={
            "trading": {"mode": "paper"},
        })
        trading = getattr(paper_config, "trading", {})
        mode = trading.get("mode", "paper")
        assert mode.upper() == "PAPER"
        print(f"  ✅ Paper mode detected: {mode}")
        
        # Test live mode
        live_config = AppConfig(raw={
            "trading": {"mode": "live"},
        })
        trading = getattr(live_config, "trading", {})
        mode = trading.get("mode", "paper")
        assert mode.upper() == "LIVE"
        print(f"  ✅ Live mode detected: {mode}")
        
        return True
    except Exception as e:
        print(f"  ❌ Mode detection test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all smoke tests."""
    print("=" * 60)
    print("LIVE ENGINE SMOKE TESTS")
    print("=" * 60)
    print()
    print("⚠️  These tests do NOT place real orders")
    print("⚠️  They only test imports and basic functionality")
    print()
    
    results = []
    
    # Run tests
    results.append(("Imports", test_imports()))
    results.append(("KiteBroker", test_kite_broker()))
    results.append(("PaperEngine", test_paper_engine_unchanged()))
    results.append(("Mode Detection", test_mode_detection()))
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    all_passed = True
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{name:20s} {status}")
        if not passed:
            all_passed = False
    
    print()
    if all_passed:
        print("✅ All smoke tests PASSED")
        return 0
    else:
        print("❌ Some smoke tests FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
