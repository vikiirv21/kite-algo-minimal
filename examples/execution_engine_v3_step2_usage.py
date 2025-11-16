"""
Example usage of Execution Engine V3 Step 2 features.

This script demonstrates:
1. Creating orders with new OrderStatus values
2. Tracking order lifecycle via events
3. Using standalone PaperExecutionEngine
4. Safe default configuration
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime, timezone

from core.execution_engine_v3 import EventBus, EventType, Order, OrderStatus
from engine.paper_execution import PaperExecutionEngine


class MockMarketDataEngine:
    """Simple mock for demonstration."""
    
    def get_latest_candle(self, symbol, timeframe):
        return {
            "open": 18500.0,
            "high": 18520.0,
            "low": 18480.0,
            "close": 18500.0,
            "volume": 10000,
        }


class MockStateStore:
    """Simple mock for demonstration."""
    
    def __init__(self):
        self.state = {"positions": []}
    
    def load(self):
        return self.state
    
    def save(self, state):
        self.state = state


async def example_basic_order():
    """Example 1: Basic order with lifecycle tracking."""
    print("\n" + "=" * 60)
    print("Example 1: Basic Order with Lifecycle Tracking")
    print("=" * 60)
    
    # Setup
    mde = MockMarketDataEngine()
    state_store = MockStateStore()
    config = {}  # Safe defaults: all simulation OFF
    
    engine = PaperExecutionEngine(
        market_data_engine=mde,
        state_store=state_store,
        config=config
    )
    
    # Create order
    order = Order(
        order_id="",
        symbol="NIFTY24DECFUT",
        side="BUY",
        qty=50,
        order_type="MARKET",
        strategy="example_strategy"
    )
    
    print(f"\n1. Order Created")
    print(f"   Status: {order.status}")
    print(f"   Symbol: {order.symbol}")
    print(f"   Qty: {order.qty}")
    print(f"   Remaining: {order.remaining_qty}")
    
    # Place order
    result = await engine.place_order(order)
    
    print(f"\n2. Order Executed")
    print(f"   Status: {result.status}")
    print(f"   Filled Qty: {result.filled_qty}")
    print(f"   Remaining Qty: {result.remaining_qty}")
    print(f"   Fill Price: {result.avg_fill_price}")
    
    print(f"\n3. Order Events (audit trail):")
    for i, event in enumerate(result.events, 1):
        print(f"   Event {i}:")
        print(f"     Time: {event['timestamp']}")
        print(f"     Status: {event['status']}")
        print(f"     Message: {event['message']}")


async def main():
    """Run example."""
    print("\n" + "=" * 60)
    print("Execution Engine V3 Step 2 - Usage Example")
    print("=" * 60)
    
    await example_basic_order()
    
    print("\n" + "=" * 60)
    print("Example completed successfully! ✅")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
