"""
Tests for engine/execution_engine.py (ExecutionEngine v2)
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.execution_engine import (
    ExecutionEngineV2,
    ExecutionResult,
    OrderIntent,
    SmartFillSimulator,
)


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


def test_smart_fill_simulator_market_order():
    """Test SmartFillSimulator with MARKET order."""
    print("\n=== Test: SmartFillSimulator MARKET Order ===")
    
    mde = MockMarketDataEngine()
    mde.set_price("NIFTY24DECFUT", 18500.0)
    
    config = {
        "execution": {
            "slippage_bps": 5.0,
        },
        "data": {
            "timeframe": "5m",
        }
    }
    
    import logging
    logger = logging.getLogger(__name__)
    
    simulator = SmartFillSimulator(mde, logger, config)
    
    # Test BUY order
    intent = OrderIntent(
        symbol="NIFTY24DECFUT",
        strategy_code="test_strategy",
        side="BUY",
        qty=50,
        order_type="MARKET",
    )
    
    result = simulator.execute(intent)
    
    print(f"Order ID: {result.order_id}")
    print(f"Status: {result.status}")
    print(f"Fill Price: {result.avg_price}")
    print(f"LTP: 18500.0")
    
    assert result.status == "FILLED"
    assert result.order_id is not None
    assert result.avg_price is not None
    # BUY should have positive slippage (higher price)
    assert result.avg_price > 18500.0
    print("✅ BUY order filled with positive slippage")
    
    # Test SELL order
    intent.side = "SELL"
    result = simulator.execute(intent)
    
    print(f"\nSELL Order ID: {result.order_id}")
    print(f"Fill Price: {result.avg_price}")
    
    assert result.status == "FILLED"
    # SELL should have negative slippage (lower price)
    assert result.avg_price < 18500.0
    print("✅ SELL order filled with negative slippage")


def test_smart_fill_simulator_limit_order():
    """Test SmartFillSimulator with LIMIT order."""
    print("\n=== Test: SmartFillSimulator LIMIT Order ===")
    
    mde = MockMarketDataEngine()
    mde.set_price("BANKNIFTY24DECFUT", 44000.0)
    
    config = {
        "execution": {
            "slippage_bps": 5.0,
        },
        "data": {
            "timeframe": "5m",
        }
    }
    
    import logging
    logger = logging.getLogger(__name__)
    
    simulator = SmartFillSimulator(mde, logger, config)
    
    # Test marketable BUY LIMIT (limit >= LTP)
    intent = OrderIntent(
        symbol="BANKNIFTY24DECFUT",
        strategy_code="test_strategy",
        side="BUY",
        qty=25,
        order_type="LIMIT",
        price=44050.0,  # Above LTP - should fill
    )
    
    result = simulator.execute(intent)
    
    print(f"Marketable BUY LIMIT Order: {result.status}")
    print(f"Fill Price: {result.avg_price}")
    
    assert result.status == "FILLED"
    assert result.avg_price == 44050.0  # Should fill at limit price
    print("✅ Marketable BUY LIMIT filled at limit price")
    
    # Test non-marketable BUY LIMIT (limit < LTP)
    intent.price = 43900.0  # Below LTP - should NOT fill
    result = simulator.execute(intent)
    
    print(f"\nNon-marketable BUY LIMIT Order: {result.status}")
    
    assert result.status == "REJECTED"
    print("✅ Non-marketable BUY LIMIT rejected")


def test_execution_engine_circuit_breakers():
    """Test ExecutionEngine v2 circuit breakers."""
    print("\n=== Test: ExecutionEngine Circuit Breakers ===")
    
    mde = MockMarketDataEngine()
    mde.set_price("NIFTY24DECFUT", 18500.0)
    
    state_store = MockStateStore()
    journal_store = MockJournalStore()
    
    config = {
        "execution": {
            "slippage_bps": 5.0,
            "circuit_breakers": {
                "max_daily_loss_rupees": 1000.0,
                "max_daily_drawdown_pct": 0.02,
                "max_trades_per_day": 100,
            },
        },
        "data": {
            "timeframe": "5m",
        }
    }
    
    import logging
    logger = logging.getLogger(__name__)
    
    engine = ExecutionEngineV2(
        mode="paper",
        broker=None,
        state_store=state_store,
        journal_store=journal_store,
        trade_throttler=None,
        logger_instance=logger,
        config=config,
        mde=mde,
    )
    
    # Test normal case - should allow trade
    intent = OrderIntent(
        symbol="NIFTY24DECFUT",
        strategy_code="test_strategy",
        side="BUY",
        qty=50,
    )
    
    can_trade = engine.apply_circuit_breakers(intent)
    print(f"Normal case - can trade: {can_trade}")
    assert can_trade is True
    print("✅ Circuit breakers allow normal trade")
    
    # Test max daily loss exceeded
    state_store.state["equity"]["realized_pnl"] = -1500.0
    can_trade = engine.apply_circuit_breakers(intent)
    print(f"\nMax loss exceeded - can trade: {can_trade}")
    assert can_trade is False
    print("✅ Circuit breakers block when max loss exceeded")
    
    # Reset state
    state_store.state["equity"]["realized_pnl"] = 0.0
    
    # Test trading halted by risk engine
    state_store.state["risk"]["trading_halted"] = True
    state_store.state["risk"]["halt_reason"] = "Test halt"
    can_trade = engine.apply_circuit_breakers(intent)
    print(f"\nTrading halted - can trade: {can_trade}")
    assert can_trade is False
    print("✅ Circuit breakers block when trading halted")


def test_execution_engine_paper_mode():
    """Test ExecutionEngine v2 in paper mode."""
    print("\n=== Test: ExecutionEngine Paper Mode ===")
    
    mde = MockMarketDataEngine()
    mde.set_price("FINNIFTY24DECFUT", 20000.0)
    
    state_store = MockStateStore()
    journal_store = MockJournalStore()
    
    config = {
        "execution": {
            "slippage_bps": 5.0,
            "circuit_breakers": {
                "max_daily_loss_rupees": 5000.0,
            },
        },
        "data": {
            "timeframe": "5m",
        }
    }
    
    import logging
    logger = logging.getLogger(__name__)
    
    engine = ExecutionEngineV2(
        mode="paper",
        broker=None,
        state_store=state_store,
        journal_store=journal_store,
        trade_throttler=None,
        logger_instance=logger,
        config=config,
        mde=mde,
    )
    
    intent = OrderIntent(
        symbol="FINNIFTY24DECFUT",
        strategy_code="test_strategy",
        side="BUY",
        qty=40,
        order_type="MARKET",
    )
    
    result = engine.execute_intent(intent)
    
    print(f"Order ID: {result.order_id}")
    print(f"Status: {result.status}")
    print(f"Fill Price: {result.avg_price}")
    
    assert result.status == "FILLED"
    assert result.order_id is not None
    assert result.avg_price is not None
    print("✅ Paper order executed successfully")
    
    # Check journal was updated
    assert len(journal_store.orders) == 1
    journal_entry = journal_store.orders[0]
    assert journal_entry["symbol"] == "FINNIFTY24DECFUT"
    assert journal_entry["status"] == "FILLED"
    print("✅ Journal updated correctly")


def test_execution_engine_live_mode_dry_run():
    """Test ExecutionEngine v2 in live mode with dry_run."""
    print("\n=== Test: ExecutionEngine Live Mode (Dry Run) ===")
    
    state_store = MockStateStore()
    journal_store = MockJournalStore()
    
    # Mock broker
    mock_broker = MagicMock()
    
    config = {
        "execution": {
            "dry_run": True,  # Dry run mode
            "circuit_breakers": {
                "max_daily_loss_rupees": 5000.0,
            },
        },
    }
    
    import logging
    logger = logging.getLogger(__name__)
    
    engine = ExecutionEngineV2(
        mode="live",
        broker=mock_broker,
        state_store=state_store,
        journal_store=journal_store,
        trade_throttler=None,
        logger_instance=logger,
        config=config,
        mde=None,
    )
    
    intent = OrderIntent(
        symbol="NIFTY24DECFUT",
        strategy_code="test_strategy",
        side="BUY",
        qty=50,
        order_type="MARKET",
    )
    
    result = engine.execute_intent(intent)
    
    print(f"Order ID: {result.order_id}")
    print(f"Status: {result.status}")
    print(f"Message: {result.message}")
    
    assert result.status == "PLACED"
    assert "dry run" in result.message.lower()
    # Broker should NOT have been called
    mock_broker.place_order.assert_not_called()
    print("✅ Dry run mode - broker not called")


def run_all_tests():
    """Run all tests."""
    print("=" * 60)
    print("EXECUTION ENGINE V2 TESTS")
    print("=" * 60)
    
    try:
        test_smart_fill_simulator_market_order()
        test_smart_fill_simulator_limit_order()
        test_execution_engine_circuit_breakers()
        test_execution_engine_paper_mode()
        test_execution_engine_live_mode_dry_run()
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED")
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
    logging.basicConfig(level=logging.INFO)
    
    success = run_all_tests()
    sys.exit(0 if success else 1)
