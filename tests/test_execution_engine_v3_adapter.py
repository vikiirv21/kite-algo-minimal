"""
Tests for engine/execution_engine_v3_adapter.py

This ensures backward compatibility between V2 and V3 execution engines.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, Mock

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.execution_engine import OrderIntent, ExecutionResult
from engine.execution_engine_v3_adapter import (
    ExecutionEngineV2ToV3Adapter,
    create_execution_engine,
)


# ============================================================================
# Mock Classes (reuse from test_execution_engine_v3.py)
# ============================================================================

class MockMarketDataEngine:
    """Mock market data engine for testing."""
    
    def __init__(self):
        self.candles = {}
    
    def get_latest_candle(self, symbol, timeframe):
        """Return mock candle."""
        return self.candles.get(symbol, {
            "open": 100.0,
            "high": 105.0,
            "low": 95.0,
            "close": 100.0,
            "volume": 1000,
        })
    
    def set_price(self, symbol, price):
        """Set mock price for symbol."""
        self.candles[symbol] = {
            "open": price,
            "high": price * 1.01,
            "low": price * 0.99,
            "close": price,
            "volume": 1000,
        }


class MockStateStore:
    """Mock state store for testing."""
    
    def __init__(self):
        self.state = {
            "equity": {
                "paper_capital": 100000.0,
                "realized_pnl": 0.0,
            },
            "risk": {
                "trading_halted": False,
            },
            "positions": [],
        }
    
    def load(self):
        return self.state
    
    def save(self, state):
        self.state = state


class MockJournalStore:
    """Mock journal store for testing."""
    
    def __init__(self):
        self.orders = []
    
    def append_orders(self, rows):
        self.orders.extend(rows)


class MockGuardian:
    """Mock TradeGuardian for testing."""
    
    def __init__(self, allow=True):
        self.allow = allow
        self.reason = "Test reason"
    
    def validate_pre_trade(self, intent, market_snapshot):
        """Mock validation."""
        result = Mock()
        result.allow = self.allow
        result.reason = self.reason
        return result


# ============================================================================
# Tests
# ============================================================================

def test_adapter_paper_mode_basic():
    """Test V2-to-V3 adapter in paper mode with basic order."""
    print("\n=== Test: Adapter Paper Mode Basic ===")
    
    mde = MockMarketDataEngine()
    mde.set_price("NIFTY24DECFUT", 18500.0)
    
    state_store = MockStateStore()
    journal_store = MockJournalStore()
    guardian = MockGuardian(allow=True)
    
    config = {
        "execution": {
            "paper": {
                "slippage_bps": 5.0,
                "slippage_enabled": True,
            }
        },
        "data": {
            "timeframe": "5m"
        }
    }
    
    # Create adapter
    adapter = ExecutionEngineV2ToV3Adapter(
        mode="paper",
        broker=None,
        state_store=state_store,
        journal_store=journal_store,
        trade_throttler=None,
        logger_instance=None,
        config=config,
        mde=mde,
        guardian=guardian,
    )
    
    # Create V2-style OrderIntent
    intent = OrderIntent(
        symbol="NIFTY24DECFUT",
        strategy_code="test_strategy",
        side="BUY",
        qty=50,
        order_type="MARKET",
    )
    
    # Execute using V2 interface
    result = adapter.execute_intent(intent)
    
    print(f"Order ID: {result.order_id}")
    print(f"Status: {result.status}")
    print(f"Fill Price: {result.avg_price}")
    
    assert result.status == "FILLED"
    assert result.order_id is not None
    assert result.avg_price is not None
    assert result.avg_price > 18500.0  # Should have slippage
    print("✅ V2 interface works with V3 engine in paper mode")


def test_adapter_circuit_breaker():
    """Test circuit breaker compatibility."""
    print("\n=== Test: Adapter Circuit Breaker ===")
    
    mde = MockMarketDataEngine()
    state_store = MockStateStore()
    journal_store = MockJournalStore()
    guardian = MockGuardian(allow=True)
    
    config = {
        "execution": {
            "paper": {}
        },
        "data": {
            "timeframe": "5m"
        }
    }
    
    adapter = ExecutionEngineV2ToV3Adapter(
        mode="paper",
        broker=None,
        state_store=state_store,
        journal_store=journal_store,
        trade_throttler=None,
        logger_instance=None,
        config=config,
        mde=mde,
        guardian=guardian,
    )
    
    intent = OrderIntent(
        symbol="NIFTY24DECFUT",
        strategy_code="test_strategy",
        side="BUY",
        qty=50,
    )
    
    # Test normal case
    can_trade = adapter.apply_circuit_breakers(intent)
    assert can_trade is True
    print("✅ Circuit breaker allows normal trade")
    
    # Test halted case
    state_store.state["risk"]["trading_halted"] = True
    state_store.state["risk"]["halt_reason"] = "Test halt"
    
    can_trade = adapter.apply_circuit_breakers(intent)
    assert can_trade is False
    print("✅ Circuit breaker blocks halted trading")


def test_adapter_with_throttler():
    """Test adapter with trade throttler."""
    print("\n=== Test: Adapter with Throttler ===")
    
    mde = MockMarketDataEngine()
    mde.set_price("NIFTY24DECFUT", 18500.0)
    
    state_store = MockStateStore()
    journal_store = MockJournalStore()
    guardian = MockGuardian(allow=True)
    
    # Mock throttler
    throttler = Mock()
    throttler.can_trade = Mock(return_value=(False, "Throttler blocked"))
    
    config = {
        "execution": {
            "paper": {}
        },
        "data": {
            "timeframe": "5m"
        }
    }
    
    adapter = ExecutionEngineV2ToV3Adapter(
        mode="paper",
        broker=None,
        state_store=state_store,
        journal_store=journal_store,
        trade_throttler=throttler,
        logger_instance=None,
        config=config,
        mde=mde,
        guardian=guardian,
    )
    
    intent = OrderIntent(
        symbol="NIFTY24DECFUT",
        strategy_code="test_strategy",
        side="BUY",
        qty=50,
    )
    
    result = adapter.execute_intent(intent)
    
    print(f"Status: {result.status}")
    print(f"Message: {result.message}")
    
    assert result.status == "REJECTED"
    assert "Throttler blocked" in result.message
    print("✅ Throttler integration works")


def test_factory_function():
    """Test factory function for creating engines."""
    print("\n=== Test: Factory Function ===")
    
    mde = MockMarketDataEngine()
    state_store = MockStateStore()
    journal_store = MockJournalStore()
    
    config = {
        "execution": {
            "paper": {}
        }
    }
    
    # Create V3 engine
    engine_v3 = create_execution_engine(
        mode="paper",
        config=config,
        state_store=state_store,
        journal_store=journal_store,
        mde=mde,
        use_v3=True,
    )
    
    assert isinstance(engine_v3, ExecutionEngineV2ToV3Adapter)
    print("✅ Factory creates V3 adapter when use_v3=True")
    
    # Create V2 engine
    engine_v2 = create_execution_engine(
        mode="paper",
        config=config,
        state_store=state_store,
        journal_store=journal_store,
        mde=mde,
        use_v3=False,
    )
    
    from engine.execution_engine import ExecutionEngineV2
    assert isinstance(engine_v2, ExecutionEngineV2)
    print("✅ Factory creates V2 engine when use_v3=False")


def test_adapter_live_mode():
    """Test adapter in live mode."""
    print("\n=== Test: Adapter Live Mode ===")
    
    # Mock broker
    broker = Mock()
    broker.place_order = Mock(return_value={
        "order_id": "LIVE-123",
        "status": "SUBMITTED",
        "message": "Order placed"
    })
    
    state_store = MockStateStore()
    journal_store = MockJournalStore()
    guardian = MockGuardian(allow=True)
    
    config = {
        "execution": {
            "live": {
                "retry_enabled": False,
                "reconciliation_enabled": False,
                "guardian_enabled": True,
            }
        }
    }
    
    adapter = ExecutionEngineV2ToV3Adapter(
        mode="live",
        broker=broker,
        state_store=state_store,
        journal_store=journal_store,
        trade_throttler=None,
        logger_instance=None,
        config=config,
        mde=None,
        guardian=guardian,
    )
    
    intent = OrderIntent(
        symbol="NIFTY24DECFUT",
        strategy_code="test_strategy",
        side="BUY",
        qty=50,
        order_type="MARKET",
    )
    
    result = adapter.execute_intent(intent)
    
    print(f"Order ID: {result.order_id}")
    print(f"Status: {result.status}")
    
    assert result.status == "PLACED"
    assert result.order_id == "LIVE-123"
    print("✅ V2 interface works with V3 engine in live mode")


def test_adapter_intent_conversion():
    """Test OrderIntent to Order conversion."""
    print("\n=== Test: Intent Conversion ===")
    
    mde = MockMarketDataEngine()
    state_store = MockStateStore()
    journal_store = MockJournalStore()
    guardian = MockGuardian(allow=True)
    
    config = {
        "execution": {
            "paper": {}
        }
    }
    
    adapter = ExecutionEngineV2ToV3Adapter(
        mode="paper",
        broker=None,
        state_store=state_store,
        journal_store=journal_store,
        trade_throttler=None,
        logger_instance=None,
        config=config,
        mde=mde,
        guardian=guardian,
    )
    
    # Create complex V2 intent
    intent = OrderIntent(
        symbol="BANKNIFTY24DECFUT",
        strategy_code="test_strategy",
        side="BUY",
        qty=25,
        order_type="LIMIT",
        product="MIS",
        validity="DAY",
        price=44000.0,
        trigger_price=43900.0,
        tag="test_tag",
        reason="Test reason",
        confidence=0.85,
        metadata={"custom": "value"}
    )
    
    # Convert to V3 Order
    order = adapter._convert_intent_to_order(intent)
    
    assert order.symbol == "BANKNIFTY24DECFUT"
    assert order.side == "BUY"
    assert order.qty == 25
    assert order.order_type == "LIMIT"
    assert order.price == 44000.0
    assert order.strategy == "test_strategy"
    assert order.tags["product"] == "MIS"
    assert order.tags["validity"] == "DAY"
    assert order.tags["trigger_price"] == 43900.0
    assert order.tags["reason"] == "Test reason"
    assert order.tags["confidence"] == 0.85
    assert order.tags["custom"] == "value"
    print("✅ Intent conversion preserves all fields")


def run_all_tests():
    """Run all adapter tests."""
    print("=" * 60)
    print("EXECUTION ENGINE V3 ADAPTER TESTS")
    print("=" * 60)
    
    try:
        test_adapter_paper_mode_basic()
        test_adapter_circuit_breaker()
        test_adapter_with_throttler()
        test_factory_function()
        test_adapter_live_mode()
        test_adapter_intent_conversion()
        
        print("\n" + "=" * 60)
        print("✅ ALL ADAPTER TESTS PASSED")
        print("=" * 60)
        return True
    except Exception as exc:
        print("\n" + "=" * 60)
        print(f"❌ TEST FAILED: {exc}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.WARNING)  # Reduce noise
    
    success = run_all_tests()
    sys.exit(0 if success else 1)
