"""
Tests for core/execution_engine_v3.py (ExecutionEngine V3)
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock, Mock

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.execution_engine_v3 import (
    Event,
    EventBus,
    EventType,
    ExecutionEngine,
    LiveExecutionEngine,
    Order,
    OrderStatus,
    PaperExecutionEngine,
)


# ============================================================================
# Mock Classes
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


class MockBroker:
    """Mock broker for testing."""
    
    def __init__(self):
        self.placed_orders = []
        self.cancelled_orders = []
        self.should_fail = False
    
    def place_order(self, intent):
        """Mock place order."""
        if self.should_fail:
            raise Exception("Broker error")
        
        order_id = f"BROKER-{len(self.placed_orders) + 1}"
        self.placed_orders.append(intent)
        
        return {
            "order_id": order_id,
            "status": "SUBMITTED",
            "message": "Order placed successfully"
        }
    
    def cancel_order(self, order_id):
        """Mock cancel order."""
        self.cancelled_orders.append(order_id)
        return {"status": "CANCELLED"}
    
    def get_orders(self):
        """Mock get orders."""
        return []


# ============================================================================
# Tests
# ============================================================================

def test_order_model():
    """Test Order model creation and validation."""
    print("\n=== Test: Order Model ===")
    
    order = Order(
        order_id="TEST-001",
        symbol="NIFTY24DECFUT",
        side="BUY",
        qty=50,
        order_type="MARKET",
        strategy="test_strategy",
        tags={"test": "value"}
    )
    
    assert order.order_id == "TEST-001"
    assert order.symbol == "NIFTY24DECFUT"
    assert order.side == "BUY"
    assert order.qty == 50
    assert order.status == OrderStatus.PENDING
    assert order.filled_qty == 0
    print("✅ Order model created successfully")
    
    # Test dict conversion
    order_dict = order.dict()
    assert order_dict["order_id"] == "TEST-001"
    assert order_dict["symbol"] == "NIFTY24DECFUT"
    print("✅ Order dict conversion works")


def test_event_bus():
    """Test EventBus functionality."""
    print("\n=== Test: EventBus ===")
    
    async def run_test():
        bus = EventBus(buffer_size=10)
        
        # Test event publishing
        await bus.publish(EventType.ORDER_PLACED, {
            "order_id": "TEST-001",
            "symbol": "NIFTY24DECFUT"
        })
        
        events = bus.get_recent_events()
        assert len(events) == 1
        assert events[0].type == EventType.ORDER_PLACED
        print("✅ Event published and retrieved")
        
        # Test event filtering
        await bus.publish(EventType.ORDER_FILLED, {
            "order_id": "TEST-002",
            "symbol": "BANKNIFTY24DECFUT"
        })
        
        filled_events = bus.get_recent_events(event_type=EventType.ORDER_FILLED)
        assert len(filled_events) == 1
        assert filled_events[0].type == EventType.ORDER_FILLED
        print("✅ Event filtering works")
        
        # Test subscriber
        callback_called = []
        
        def callback(event):
            callback_called.append(event)
        
        bus.subscribe(EventType.ORDER_REJECTED, callback)
        
        await bus.publish(EventType.ORDER_REJECTED, {
            "order_id": "TEST-003",
            "reason": "Test rejection"
        })
        
        assert len(callback_called) == 1
        print("✅ Subscriber callback invoked")
    
    asyncio.run(run_test())


def test_paper_execution_engine_basic():
    """Test PaperExecutionEngine basic order execution."""
    print("\n=== Test: PaperExecutionEngine Basic ===")
    
    async def run_test():
        mde = MockMarketDataEngine()
        mde.set_price("NIFTY24DECFUT", 18500.0)
        
        state_store = MockStateStore()
        
        config = {
            "execution": {
                "paper": {
                    "slippage_bps": 5.0,
                    "slippage_enabled": True,
                    "spread_enabled": False,
                    "partial_fill_enabled": False,
                    "latency_enabled": False,
                }
            },
            "data": {
                "timeframe": "5m"
            }
        }
        
        engine = PaperExecutionEngine(
            market_data_engine=mde,
            state_store=state_store,
            config=config
        )
        
        # Test BUY order
        order = Order(
            order_id="",
            symbol="NIFTY24DECFUT",
            side="BUY",
            qty=50,
            order_type="MARKET",
            strategy="test_strategy"
        )
        
        result = await engine.place_order(order)
        
        print(f"Order ID: {result.order_id}")
        print(f"Status: {result.status}")
        print(f"Fill Price: {result.avg_price}")
        
        assert result.status == OrderStatus.FILLED
        assert result.order_id is not None
        assert result.avg_price is not None
        assert result.avg_price > 18500.0  # BUY should have positive slippage
        assert result.filled_qty == 50
        print("✅ BUY order filled with slippage")
        
        # Test SELL order
        order2 = Order(
            order_id="",
            symbol="NIFTY24DECFUT",
            side="SELL",
            qty=50,
            order_type="MARKET",
            strategy="test_strategy"
        )
        
        result2 = await engine.place_order(order2)
        
        assert result2.status == OrderStatus.FILLED
        assert result2.avg_price < 18500.0  # SELL should have negative slippage
        print("✅ SELL order filled with slippage")
    
    asyncio.run(run_test())


def test_paper_execution_engine_limit_orders():
    """Test PaperExecutionEngine LIMIT order handling."""
    print("\n=== Test: PaperExecutionEngine LIMIT Orders ===")
    
    async def run_test():
        mde = MockMarketDataEngine()
        mde.set_price("BANKNIFTY24DECFUT", 44000.0)
        
        state_store = MockStateStore()
        
        config = {
            "execution": {
                "paper": {
                    "slippage_bps": 5.0,
                    "slippage_enabled": False,
                }
            },
            "data": {
                "timeframe": "5m"
            }
        }
        
        engine = PaperExecutionEngine(
            market_data_engine=mde,
            state_store=state_store,
            config=config
        )
        
        # Test marketable BUY LIMIT
        order = Order(
            order_id="",
            symbol="BANKNIFTY24DECFUT",
            side="BUY",
            qty=25,
            order_type="LIMIT",
            price=44050.0,  # Above LTP - should fill
            strategy="test_strategy"
        )
        
        result = await engine.place_order(order)
        
        print(f"Marketable BUY LIMIT: {result.status}")
        print(f"Fill Price: {result.avg_price}")
        
        assert result.status == OrderStatus.FILLED
        assert result.avg_price == 44050.0
        print("✅ Marketable BUY LIMIT filled at limit price")
        
        # Test non-marketable BUY LIMIT
        order2 = Order(
            order_id="",
            symbol="BANKNIFTY24DECFUT",
            side="BUY",
            qty=25,
            order_type="LIMIT",
            price=43900.0,  # Below LTP - should NOT fill
            strategy="test_strategy"
        )
        
        result2 = await engine.place_order(order2)
        
        print(f"Non-marketable BUY LIMIT: {result2.status}")
        
        assert result2.status == OrderStatus.REJECTED
        print("✅ Non-marketable BUY LIMIT rejected")
    
    asyncio.run(run_test())


def test_paper_execution_engine_partial_fills():
    """Test PaperExecutionEngine partial fill simulation."""
    print("\n=== Test: PaperExecutionEngine Partial Fills ===")
    
    async def run_test():
        mde = MockMarketDataEngine()
        mde.set_price("FINNIFTY24DECFUT", 20000.0)
        
        state_store = MockStateStore()
        
        config = {
            "execution": {
                "paper": {
                    "slippage_enabled": False,
                    "partial_fill_enabled": True,
                    "partial_fill_probability": 1.0,  # Always partial fill
                    "partial_fill_ratio": 0.5,
                }
            },
            "data": {
                "timeframe": "5m"
            }
        }
        
        engine = PaperExecutionEngine(
            market_data_engine=mde,
            state_store=state_store,
            config=config
        )
        
        order = Order(
            order_id="",
            symbol="FINNIFTY24DECFUT",
            side="BUY",
            qty=100,
            order_type="MARKET",
            strategy="test_strategy"
        )
        
        result = await engine.place_order(order)
        
        print(f"Status: {result.status}")
        print(f"Ordered: {result.qty}, Filled: {result.filled_qty}")
        
        assert result.status == OrderStatus.PARTIAL
        assert result.filled_qty < result.qty
        print("✅ Partial fill simulation works")
    
    asyncio.run(run_test())


def test_paper_execution_engine_cancel():
    """Test PaperExecutionEngine order cancellation."""
    print("\n=== Test: PaperExecutionEngine Cancel ===")
    
    async def run_test():
        mde = MockMarketDataEngine()
        mde.set_price("NIFTY24DECFUT", 18500.0)
        
        state_store = MockStateStore()
        
        config = {
            "execution": {
                "paper": {}
            },
            "data": {
                "timeframe": "5m"
            }
        }
        
        engine = PaperExecutionEngine(
            market_data_engine=mde,
            state_store=state_store,
            config=config
        )
        
        # Place order
        order = Order(
            order_id="TEST-CANCEL-001",
            symbol="NIFTY24DECFUT",
            side="BUY",
            qty=50,
            order_type="MARKET",
            strategy="test_strategy"
        )
        
        result = await engine.place_order(order)
        order_id = result.order_id
        
        # Cancel order (note: paper orders fill immediately, so this tests filled order cancel)
        cancelled = await engine.cancel_order(order_id)
        
        print(f"Cancelled status: {cancelled.status}")
        
        # Filled orders should remain filled
        assert cancelled.status in [OrderStatus.FILLED, OrderStatus.CANCELLED]
        print("✅ Order cancellation works")
    
    asyncio.run(run_test())


def test_live_execution_engine_basic():
    """Test LiveExecutionEngine basic functionality."""
    print("\n=== Test: LiveExecutionEngine Basic ===")
    
    async def run_test():
        broker = MockBroker()
        guardian = MockGuardian(allow=True)
        state_store = MockStateStore()
        journal_store = MockJournalStore()
        
        config = {
            "execution": {
                "live": {
                    "retry_enabled": True,
                    "max_retries": 3,
                    "reconciliation_enabled": False,  # Disable for test
                    "guardian_enabled": True,
                }
            }
        }
        
        engine = LiveExecutionEngine(
            broker=broker,
            guardian=guardian,
            state_store=state_store,
            journal_store=journal_store,
            config=config
        )
        
        # Place order
        order = Order(
            order_id="",
            symbol="NIFTY24DECFUT",
            side="BUY",
            qty=50,
            order_type="MARKET",
            strategy="test_strategy",
            tags={"exchange": "NFO", "product": "MIS"}
        )
        
        result = await engine.place_order(order)
        
        print(f"Order ID: {result.order_id}")
        print(f"Status: {result.status}")
        
        assert result.status == OrderStatus.PLACED
        assert result.order_id is not None
        assert len(broker.placed_orders) == 1
        assert len(journal_store.orders) == 1
        print("✅ Live order placed successfully")
    
    asyncio.run(run_test())


def test_live_execution_engine_guardian_block():
    """Test LiveExecutionEngine with Guardian blocking order."""
    print("\n=== Test: LiveExecutionEngine Guardian Block ===")
    
    async def run_test():
        broker = MockBroker()
        guardian = MockGuardian(allow=False)
        guardian.reason = "Risk limit exceeded"
        state_store = MockStateStore()
        journal_store = MockJournalStore()
        
        config = {
            "execution": {
                "live": {
                    "guardian_enabled": True,
                    "reconciliation_enabled": False,
                }
            }
        }
        
        engine = LiveExecutionEngine(
            broker=broker,
            guardian=guardian,
            state_store=state_store,
            journal_store=journal_store,
            config=config
        )
        
        order = Order(
            order_id="",
            symbol="NIFTY24DECFUT",
            side="BUY",
            qty=50,
            order_type="MARKET",
            strategy="test_strategy"
        )
        
        result = await engine.place_order(order)
        
        print(f"Status: {result.status}")
        print(f"Message: {result.message}")
        
        assert result.status == OrderStatus.REJECTED
        assert "Guardian blocked" in result.message
        assert len(broker.placed_orders) == 0
        print("✅ Guardian successfully blocked order")
    
    asyncio.run(run_test())


def test_live_execution_engine_retry():
    """Test LiveExecutionEngine retry logic."""
    print("\n=== Test: LiveExecutionEngine Retry ===")
    
    async def run_test():
        broker = MockBroker()
        broker.should_fail = True  # First attempt will fail
        
        guardian = MockGuardian(allow=True)
        state_store = MockStateStore()
        journal_store = MockJournalStore()
        
        config = {
            "execution": {
                "live": {
                    "retry_enabled": True,
                    "max_retries": 3,
                    "retry_delay": 0.1,
                    "reconciliation_enabled": False,
                    "guardian_enabled": False,
                }
            }
        }
        
        engine = LiveExecutionEngine(
            broker=broker,
            guardian=guardian,
            state_store=state_store,
            journal_store=journal_store,
            config=config
        )
        
        order = Order(
            order_id="",
            symbol="NIFTY24DECFUT",
            side="BUY",
            qty=50,
            order_type="MARKET",
            strategy="test_strategy"
        )
        
        result = await engine.place_order(order)
        
        print(f"Status: {result.status}")
        print(f"Message: {result.message}")
        
        assert result.status == OrderStatus.REJECTED
        assert "Broker error" in result.message
        print("✅ Retry logic executed (failed as expected)")
    
    asyncio.run(run_test())


def test_live_execution_engine_cancel():
    """Test LiveExecutionEngine order cancellation."""
    print("\n=== Test: LiveExecutionEngine Cancel ===")
    
    async def run_test():
        broker = MockBroker()
        guardian = MockGuardian(allow=True)
        state_store = MockStateStore()
        journal_store = MockJournalStore()
        
        config = {
            "execution": {
                "live": {
                    "reconciliation_enabled": False,
                    "guardian_enabled": False,
                }
            }
        }
        
        engine = LiveExecutionEngine(
            broker=broker,
            guardian=guardian,
            state_store=state_store,
            journal_store=journal_store,
            config=config
        )
        
        # Place order
        order = Order(
            order_id="TEST-CANCEL-001",
            symbol="NIFTY24DECFUT",
            side="BUY",
            qty=50,
            order_type="MARKET",
            strategy="test_strategy"
        )
        
        result = await engine.place_order(order)
        order_id = result.order_id
        
        # Cancel order
        cancelled = await engine.cancel_order(order_id)
        
        print(f"Cancelled status: {cancelled.status}")
        
        assert cancelled.status == OrderStatus.CANCELLED
        assert len(broker.cancelled_orders) == 1
        print("✅ Live order cancelled successfully")
    
    asyncio.run(run_test())


def test_paper_execution_engine_position_tracking():
    """Test PaperExecutionEngine position tracking."""
    print("\n=== Test: PaperExecutionEngine Position Tracking ===")
    
    async def run_test():
        mde = MockMarketDataEngine()
        mde.set_price("NIFTY24DECFUT", 18500.0)
        
        state_store = MockStateStore()
        
        config = {
            "execution": {
                "paper": {
                    "slippage_enabled": False,
                }
            },
            "data": {
                "timeframe": "5m"
            }
        }
        
        engine = PaperExecutionEngine(
            market_data_engine=mde,
            state_store=state_store,
            config=config
        )
        
        # Place BUY order
        order1 = Order(
            order_id="",
            symbol="NIFTY24DECFUT",
            side="BUY",
            qty=50,
            order_type="MARKET",
            strategy="test_strategy"
        )
        
        await engine.place_order(order1)
        
        # Check position
        state = state_store.load()
        positions = state.get("positions", [])
        assert len(positions) == 1
        assert positions[0]["symbol"] == "NIFTY24DECFUT"
        assert positions[0]["qty"] == 50
        print("✅ BUY order created position")
        
        # Place SELL order to close
        order2 = Order(
            order_id="",
            symbol="NIFTY24DECFUT",
            side="SELL",
            qty=50,
            order_type="MARKET",
            strategy="test_strategy"
        )
        
        await engine.place_order(order2)
        
        # Check position closed
        state = state_store.load()
        positions = state.get("positions", [])
        assert len(positions) == 0
        print("✅ SELL order closed position")
    
    asyncio.run(run_test())


def run_all_tests():
    """Run all tests."""
    print("=" * 60)
    print("EXECUTION ENGINE V3 TESTS")
    print("=" * 60)
    
    try:
        test_order_model()
        test_event_bus()
        test_paper_execution_engine_basic()
        test_paper_execution_engine_limit_orders()
        test_paper_execution_engine_partial_fills()
        test_paper_execution_engine_cancel()
        test_live_execution_engine_basic()
        test_live_execution_engine_guardian_block()
        test_live_execution_engine_retry()
        test_live_execution_engine_cancel()
        test_paper_execution_engine_position_tracking()
        
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
