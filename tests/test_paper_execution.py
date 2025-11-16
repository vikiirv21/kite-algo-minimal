"""
Tests for engine/paper_execution.py
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import Mock

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.execution_engine_v3 import EventBus, EventType, Order, OrderStatus
from engine.paper_execution import PaperExecutionEngine


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
            "positions": [],
        }
    
    def load(self):
        return self.state
    
    def save(self, state):
        self.state = state


# ============================================================================
# Tests
# ============================================================================

def test_paper_execution_safe_defaults():
    """Test that paper execution has safe defaults (all simulation OFF)."""
    print("\n=== Test: Paper Execution Safe Defaults ===")
    
    async def run_test():
        mde = MockMarketDataEngine()
        state_store = MockStateStore()
        config = {}  # Empty config should use safe defaults
        
        engine = PaperExecutionEngine(
            market_data_engine=mde,
            state_store=state_store,
            config=config
        )
        
        # Verify all simulation features are OFF by default
        assert engine.slippage_enabled == False, "Slippage should be OFF by default"
        assert engine.spread_enabled == False, "Spread should be OFF by default"
        assert engine.partial_fill_enabled == False, "Partial fills should be OFF by default"
        assert engine.latency_enabled == False, "Latency should be OFF by default"
        
        print("✅ All simulation features default to OFF (safe)")
    
    asyncio.run(run_test())


def test_paper_execution_deterministic_fill():
    """Test that paper execution fills are deterministic with defaults OFF."""
    print("\n=== Test: Paper Execution Deterministic Fill ===")
    
    async def run_test():
        mde = MockMarketDataEngine()
        mde.set_price("NIFTY24DECFUT", 18500.0)
        
        state_store = MockStateStore()
        config = {
            "execution": {
                "paper": {
                    "slippage_enabled": False,
                    "spread_enabled": False,
                    "partial_fill_enabled": False,
                    "latency_enabled": False
                }
            }
        }
        
        engine = PaperExecutionEngine(
            market_data_engine=mde,
            state_store=state_store,
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
        
        # With all simulation OFF, fill price should equal LTP exactly
        assert result.status == OrderStatus.FILLED
        assert result.avg_fill_price == 18500.0, "Fill price should equal LTP with no simulation"
        assert result.filled_qty == 50
        assert result.remaining_qty == 0
        assert len(result.events) >= 2  # SUBMITTED and FILLED events
        
        print(f"✅ Deterministic fill: price={result.avg_fill_price}, status={result.status}")
    
    asyncio.run(run_test())


def test_paper_execution_with_slippage():
    """Test that slippage simulation works when enabled."""
    print("\n=== Test: Paper Execution With Slippage ===")
    
    async def run_test():
        mde = MockMarketDataEngine()
        mde.set_price("NIFTY24DECFUT", 18500.0)
        
        state_store = MockStateStore()
        config = {
            "execution": {
                "paper": {
                    "slippage_enabled": True,
                    "slippage_bps": 10.0,  # 10 bps = 0.1%
                }
            }
        }
        
        engine = PaperExecutionEngine(
            market_data_engine=mde,
            state_store=state_store,
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
        
        # With slippage enabled, BUY should fill at higher price
        expected_fill = 18500.0 * (1 + 10.0 / 10000.0)  # 18518.5
        assert result.status == OrderStatus.FILLED
        assert abs(result.avg_fill_price - expected_fill) < 0.01
        
        print(f"✅ Slippage applied: LTP=18500.0, fill={result.avg_fill_price}")
    
    asyncio.run(run_test())


def test_paper_execution_limit_order_not_marketable():
    """Test that non-marketable LIMIT orders remain OPEN."""
    print("\n=== Test: Paper Execution LIMIT Order Not Marketable ===")
    
    async def run_test():
        mde = MockMarketDataEngine()
        mde.set_price("NIFTY24DECFUT", 18500.0)
        
        state_store = MockStateStore()
        config = {}
        
        engine = PaperExecutionEngine(
            market_data_engine=mde,
            state_store=state_store,
            config=config
        )
        
        # BUY limit at 18400 when LTP is 18500 - not marketable
        order = Order(
            order_id="",
            symbol="NIFTY24DECFUT",
            side="BUY",
            qty=50,
            order_type="LIMIT",
            price=18400.0,
            strategy="test_strategy"
        )
        
        result = await engine.place_order(order)
        
        # Order should be OPEN, not filled
        assert result.status == OrderStatus.OPEN
        assert result.filled_qty == 0
        assert result.remaining_qty == 50
        
        print(f"✅ LIMIT order not marketable: status={result.status}")
    
    asyncio.run(run_test())


def test_paper_execution_limit_order_marketable():
    """Test that marketable LIMIT orders fill immediately."""
    print("\n=== Test: Paper Execution LIMIT Order Marketable ===")
    
    async def run_test():
        mde = MockMarketDataEngine()
        mde.set_price("NIFTY24DECFUT", 18500.0)
        
        state_store = MockStateStore()
        config = {}
        
        engine = PaperExecutionEngine(
            market_data_engine=mde,
            state_store=state_store,
            config=config
        )
        
        # BUY limit at 18600 when LTP is 18500 - marketable
        order = Order(
            order_id="",
            symbol="NIFTY24DECFUT",
            side="BUY",
            qty=50,
            order_type="LIMIT",
            price=18600.0,
            strategy="test_strategy"
        )
        
        result = await engine.place_order(order)
        
        # Order should be FILLED at limit price
        assert result.status == OrderStatus.FILLED
        assert result.avg_fill_price == 18600.0
        assert result.filled_qty == 50
        assert result.remaining_qty == 0
        
        print(f"✅ LIMIT order marketable: filled at {result.avg_fill_price}")
    
    asyncio.run(run_test())


def test_paper_execution_position_tracking():
    """Test that positions are tracked correctly."""
    print("\n=== Test: Paper Execution Position Tracking ===")
    
    async def run_test():
        mde = MockMarketDataEngine()
        mde.set_price("NIFTY24DECFUT", 18500.0)
        
        state_store = MockStateStore()
        config = {}
        
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
        
        print("✅ Position tracked after BUY")
        
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
        
        print("✅ Position closed after SELL")
    
    asyncio.run(run_test())


def test_paper_execution_event_publishing():
    """Test that events are published correctly."""
    print("\n=== Test: Paper Execution Event Publishing ===")
    
    async def run_test():
        mde = MockMarketDataEngine()
        mde.set_price("NIFTY24DECFUT", 18500.0)
        
        state_store = MockStateStore()
        config = {}
        event_bus = EventBus()
        
        # Track published events
        events = []
        
        def event_callback(event):
            events.append(event)
        
        event_bus.subscribe(EventType.ORDER_FILLED, event_callback)
        
        engine = PaperExecutionEngine(
            market_data_engine=mde,
            state_store=state_store,
            config=config,
            event_bus=event_bus
        )
        
        order = Order(
            order_id="",
            symbol="NIFTY24DECFUT",
            side="BUY",
            qty=50,
            order_type="MARKET",
            strategy="test_strategy"
        )
        
        await engine.place_order(order)
        
        # Give async tasks time to complete
        await asyncio.sleep(0.1)
        
        # Check events were published
        assert len(events) > 0, "ORDER_FILLED event should be published"
        assert events[0].type == EventType.ORDER_FILLED
        
        print(f"✅ Events published: {len(events)} events")
    
    asyncio.run(run_test())


if __name__ == "__main__":
    print("Running paper_execution tests...")
    test_paper_execution_safe_defaults()
    test_paper_execution_deterministic_fill()
    test_paper_execution_with_slippage()
    test_paper_execution_limit_order_not_marketable()
    test_paper_execution_limit_order_marketable()
    test_paper_execution_position_tracking()
    test_paper_execution_event_publishing()
    print("\n✅ All tests passed!")
