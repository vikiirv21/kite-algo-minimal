"""
Tests for core/reconciliation_engine.py (ReconciliationEngine)
"""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.execution_engine_v3 import (
    EventBus,
    EventType,
    Order,
    OrderStatus,
    PaperExecutionEngine,
)
from core.reconciliation_engine import ReconciliationEngine

# Mark all async tests in this module to use pytest-asyncio
pytestmark = pytest.mark.asyncio


# ============================================================================
# Mock Classes
# ============================================================================

class MockExecutionEngine:
    """Mock execution engine for testing."""
    
    def __init__(self):
        self.orders = {}
    
    async def poll_orders(self):
        """Return mock orders."""
        return list(self.orders.values())
    
    def add_order(self, order):
        """Add order to mock engine."""
        self.orders[order.order_id] = order


class MockStateStore:
    """Mock state store for testing."""
    
    def __init__(self):
        self.state = {
            "positions": [],
            "equity": {"paper_capital": 100000.0},
        }
    
    def load(self):
        return self.state
    
    def save(self, state):
        self.state = state


class MockKiteBroker:
    """Mock Kite broker for testing."""
    
    def __init__(self):
        self.kite = Mock()
        self.positions_response = {"net": []}
    
    def setup_positions(self, positions):
        """Setup mock positions response."""
        self.positions_response = {"net": positions}
        self.kite.positions = Mock(return_value=self.positions_response)


# ============================================================================
# Test Functions
# ============================================================================

async def test_reconciliation_engine_initialization():
    """Test ReconciliationEngine initialization."""
    print("\n=== Test: ReconciliationEngine Initialization ===")
    
    execution_engine = MockExecutionEngine()
    state_store = MockStateStore()
    event_bus = EventBus()
    
    # Test PAPER mode initialization
    reconciler = ReconciliationEngine(
        execution_engine=execution_engine,
        state_store=state_store,
        event_bus=event_bus,
        mode="PAPER",
        config={"reconciliation": {"interval_seconds": 5}}
    )
    
    assert reconciler.mode == "PAPER"
    assert reconciler.interval_seconds == 5
    assert reconciler.enabled is True
    assert reconciler.reconciliation_count == 0
    assert reconciler.discrepancy_count == 0
    
    print("✅ PAPER mode initialization passed")
    
    # Test LIVE mode initialization
    reconciler_live = ReconciliationEngine(
        execution_engine=execution_engine,
        state_store=state_store,
        event_bus=event_bus,
        mode="LIVE",
        config={"reconciliation": {"interval_seconds": 2}}
    )
    
    assert reconciler_live.mode == "LIVE"
    assert reconciler_live.interval_seconds == 2
    
    print("✅ LIVE mode initialization passed")
    print("✅ All initialization tests passed\n")


async def test_order_reconciliation_no_discrepancy():
    """Test order reconciliation when states match."""
    print("\n=== Test: Order Reconciliation - No Discrepancy ===")
    
    execution_engine = MockExecutionEngine()
    state_store = MockStateStore()
    event_bus = EventBus()
    
    reconciler = ReconciliationEngine(
        execution_engine=execution_engine,
        state_store=state_store,
        event_bus=event_bus,
        mode="PAPER"
    )
    
    # Create matching orders
    order = Order(
        order_id="TEST-001",
        symbol="NIFTY24DECFUT",
        side="BUY",
        qty=50,
        order_type="MARKET",
        status=OrderStatus.FILLED,
        strategy="test_strategy",
        filled_qty=50,
        avg_price=21000.0
    )
    
    # Register in both local and broker
    await reconciler.register_order(order)
    execution_engine.add_order(order)
    
    # Reconcile
    await reconciler.reconcile_orders()
    
    assert reconciler.reconciliation_count == 1
    assert reconciler.discrepancy_count == 0
    
    print("✅ No discrepancy detected as expected")
    print("✅ Order reconciliation test passed\n")


async def test_order_status_discrepancy_pending_to_placed():
    """Test reconciliation when broker shows PLACED but local is PENDING."""
    print("\n=== Test: Order Status Discrepancy - PENDING → PLACED ===")
    
    execution_engine = MockExecutionEngine()
    state_store = MockStateStore()
    event_bus = EventBus()
    
    # Track published events
    published_events = []
    
    def event_callback(event):
        published_events.append(event)
    
    event_bus.subscribe(EventType.ORDER_UPDATED, event_callback)
    event_bus.subscribe(EventType.RECONCILIATION_DISCREPANCY, event_callback)
    
    reconciler = ReconciliationEngine(
        execution_engine=execution_engine,
        state_store=state_store,
        event_bus=event_bus,
        mode="PAPER"
    )
    
    # Local order is PENDING
    local_order = Order(
        order_id="TEST-002",
        symbol="NIFTY24DECFUT",
        side="BUY",
        qty=50,
        order_type="MARKET",
        status=OrderStatus.PENDING,
        strategy="test_strategy"
    )
    
    # Broker order is PLACED
    broker_order = Order(
        order_id="TEST-002",
        symbol="NIFTY24DECFUT",
        side="BUY",
        qty=50,
        order_type="MARKET",
        status=OrderStatus.PLACED,
        strategy="test_strategy"
    )
    
    await reconciler.register_order(local_order)
    execution_engine.add_order(broker_order)
    
    # Reconcile
    await reconciler.reconcile_orders()
    
    # Wait for async event publishing
    await asyncio.sleep(0.1)
    
    assert local_order.status == OrderStatus.PLACED
    assert reconciler.discrepancy_count == 1
    assert len(published_events) > 0
    
    print(f"✅ Status reconciled: PENDING → PLACED")
    print(f"✅ Events published: {len(published_events)}")
    print("✅ Order status discrepancy test passed\n")


async def test_order_fill_reconciliation():
    """Test reconciliation when broker shows FILLED but local is PLACED."""
    print("\n=== Test: Order Fill Reconciliation - PLACED → FILLED ===")
    
    execution_engine = MockExecutionEngine()
    state_store = MockStateStore()
    event_bus = EventBus()
    
    # Track published events
    published_events = []
    
    def event_callback(event):
        published_events.append(event)
    
    event_bus.subscribe(EventType.ORDER_FILLED, event_callback)
    event_bus.subscribe(EventType.POSITION_UPDATED, event_callback)
    
    reconciler = ReconciliationEngine(
        execution_engine=execution_engine,
        state_store=state_store,
        event_bus=event_bus,
        mode="PAPER"
    )
    
    # Local order is PLACED
    local_order = Order(
        order_id="TEST-003",
        symbol="NIFTY24DECFUT",
        side="BUY",
        qty=50,
        order_type="MARKET",
        status=OrderStatus.PLACED,
        strategy="test_strategy",
        filled_qty=0,
        avg_price=None
    )
    
    # Broker order is FILLED
    broker_order = Order(
        order_id="TEST-003",
        symbol="NIFTY24DECFUT",
        side="BUY",
        qty=50,
        order_type="MARKET",
        status=OrderStatus.FILLED,
        strategy="test_strategy",
        filled_qty=50,
        avg_price=21000.0
    )
    
    await reconciler.register_order(local_order)
    execution_engine.add_order(broker_order)
    
    # Reconcile
    await reconciler.reconcile_orders()
    
    # Wait for async event publishing
    await asyncio.sleep(0.1)
    
    assert local_order.status == OrderStatus.FILLED
    assert local_order.filled_qty == 50
    assert local_order.avg_price == 21000.0
    assert reconciler.discrepancy_count == 1
    
    # Check position was updated
    state = state_store.load()
    positions = state.get("positions", [])
    assert len(positions) == 1
    assert positions[0]["symbol"] == "NIFTY24DECFUT"
    assert positions[0]["qty"] == 50
    
    print(f"✅ Status reconciled: PLACED → FILLED")
    print(f"✅ Fill details updated: qty={local_order.filled_qty}, price={local_order.avg_price}")
    print(f"✅ Position created in StateStore")
    print("✅ Order fill reconciliation test passed\n")


async def test_order_partial_fill_reconciliation():
    """Test reconciliation for partial fills."""
    print("\n=== Test: Partial Fill Reconciliation ===")
    
    execution_engine = MockExecutionEngine()
    state_store = MockStateStore()
    event_bus = EventBus()
    
    reconciler = ReconciliationEngine(
        execution_engine=execution_engine,
        state_store=state_store,
        event_bus=event_bus,
        mode="PAPER"
    )
    
    # Local order has partial fill (20 qty)
    local_order = Order(
        order_id="TEST-004",
        symbol="NIFTY24DECFUT",
        side="BUY",
        qty=50,
        order_type="MARKET",
        status=OrderStatus.PARTIAL,
        strategy="test_strategy",
        filled_qty=20,
        avg_price=21000.0
    )
    
    # Broker order has more fills (35 qty)
    broker_order = Order(
        order_id="TEST-004",
        symbol="NIFTY24DECFUT",
        side="BUY",
        qty=50,
        order_type="MARKET",
        status=OrderStatus.PARTIAL,
        strategy="test_strategy",
        filled_qty=35,
        avg_price=21000.0
    )
    
    await reconciler.register_order(local_order)
    execution_engine.add_order(broker_order)
    
    # Reconcile
    await reconciler.reconcile_orders()
    
    # Wait for async operations
    await asyncio.sleep(0.1)
    
    assert local_order.filled_qty == 35
    assert reconciler.discrepancy_count == 1
    
    print(f"✅ Partial fill reconciled: 20 → 35 qty")
    print("✅ Partial fill reconciliation test passed\n")


async def test_order_cancelled_reconciliation():
    """Test reconciliation when broker shows CANCELLED."""
    print("\n=== Test: Order Cancellation Reconciliation ===")
    
    execution_engine = MockExecutionEngine()
    state_store = MockStateStore()
    event_bus = EventBus()
    
    # Track published events
    published_events = []
    
    def event_callback(event):
        published_events.append(event)
    
    event_bus.subscribe(EventType.ORDER_CANCELLED, event_callback)
    
    reconciler = ReconciliationEngine(
        execution_engine=execution_engine,
        state_store=state_store,
        event_bus=event_bus,
        mode="PAPER"
    )
    
    # Local order is PLACED
    local_order = Order(
        order_id="TEST-005",
        symbol="NIFTY24DECFUT",
        side="BUY",
        qty=50,
        order_type="LIMIT",
        price=21000.0,
        status=OrderStatus.PLACED,
        strategy="test_strategy"
    )
    
    # Broker order is CANCELLED
    broker_order = Order(
        order_id="TEST-005",
        symbol="NIFTY24DECFUT",
        side="BUY",
        qty=50,
        order_type="LIMIT",
        price=21000.0,
        status=OrderStatus.CANCELLED,
        strategy="test_strategy"
    )
    
    await reconciler.register_order(local_order)
    execution_engine.add_order(broker_order)
    
    # Reconcile
    await reconciler.reconcile_orders()
    
    # Wait for async event publishing
    await asyncio.sleep(0.1)
    
    assert local_order.status == OrderStatus.CANCELLED
    assert reconciler.discrepancy_count == 1
    assert len(published_events) > 0
    
    print(f"✅ Status reconciled: PLACED → CANCELLED")
    print("✅ Order cancellation reconciliation test passed\n")


async def test_order_rejected_reconciliation():
    """Test reconciliation when broker shows REJECTED."""
    print("\n=== Test: Order Rejection Reconciliation ===")
    
    execution_engine = MockExecutionEngine()
    state_store = MockStateStore()
    event_bus = EventBus()
    
    # Track published events
    published_events = []
    
    def event_callback(event):
        published_events.append(event)
    
    event_bus.subscribe(EventType.ORDER_REJECTED, event_callback)
    event_bus.subscribe(EventType.RECONCILIATION_DISCREPANCY, event_callback)
    
    reconciler = ReconciliationEngine(
        execution_engine=execution_engine,
        state_store=state_store,
        event_bus=event_bus,
        mode="PAPER"
    )
    
    # Local order is PLACED
    local_order = Order(
        order_id="TEST-006",
        symbol="NIFTY24DECFUT",
        side="BUY",
        qty=50,
        order_type="MARKET",
        status=OrderStatus.PLACED,
        strategy="test_strategy"
    )
    
    # Broker order is REJECTED
    broker_order = Order(
        order_id="TEST-006",
        symbol="NIFTY24DECFUT",
        side="BUY",
        qty=50,
        order_type="MARKET",
        status=OrderStatus.REJECTED,
        strategy="test_strategy",
        message="Insufficient funds"
    )
    
    await reconciler.register_order(local_order)
    execution_engine.add_order(broker_order)
    
    # Reconcile
    await reconciler.reconcile_orders()
    
    # Wait for async event publishing
    await asyncio.sleep(0.1)
    
    assert local_order.status == OrderStatus.REJECTED
    assert "Insufficient funds" in local_order.message
    assert reconciler.discrepancy_count == 1
    
    # Check that risk alert was published
    rejection_events = [e for e in published_events if e.type == EventType.ORDER_REJECTED]
    assert len(rejection_events) > 0
    
    print(f"✅ Status reconciled: PLACED → REJECTED")
    print(f"✅ Risk alert published")
    print("✅ Order rejection reconciliation test passed\n")


async def test_missing_order_in_broker():
    """Test reconciliation when order is missing from broker."""
    print("\n=== Test: Missing Order in Broker State ===")
    
    execution_engine = MockExecutionEngine()
    state_store = MockStateStore()
    event_bus = EventBus()
    
    # Track published events
    published_events = []
    
    def event_callback(event):
        published_events.append(event)
    
    event_bus.subscribe(EventType.RECONCILIATION_DISCREPANCY, event_callback)
    
    reconciler = ReconciliationEngine(
        execution_engine=execution_engine,
        state_store=state_store,
        event_bus=event_bus,
        mode="PAPER"
    )
    
    # Local order exists
    local_order = Order(
        order_id="TEST-007",
        symbol="NIFTY24DECFUT",
        side="BUY",
        qty=50,
        order_type="MARKET",
        status=OrderStatus.PLACED,
        strategy="test_strategy"
    )
    
    await reconciler.register_order(local_order)
    # Note: NOT adding order to execution_engine (simulates missing from broker)
    
    # Reconcile
    await reconciler.reconcile_orders()
    
    # Wait for async event publishing
    await asyncio.sleep(0.1)
    
    # Order should remain PLACED (will retry next cycle)
    assert local_order.status == OrderStatus.PLACED
    
    # Discrepancy event should be published
    discrepancy_events = [e for e in published_events if e.type == EventType.RECONCILIATION_DISCREPANCY]
    assert len(discrepancy_events) > 0
    
    print(f"✅ Missing order detected and logged")
    print(f"✅ Discrepancy event published")
    print("✅ Missing order test passed\n")


async def test_position_reconciliation_live():
    """Test position reconciliation in LIVE mode."""
    print("\n=== Test: Position Reconciliation (LIVE) ===")
    
    execution_engine = MockExecutionEngine()
    state_store = MockStateStore()
    event_bus = EventBus()
    kite_broker = MockKiteBroker()
    
    # Track published events
    published_events = []
    
    def event_callback(event):
        published_events.append(event)
    
    event_bus.subscribe(EventType.POSITION_SYNCED, event_callback)
    
    reconciler = ReconciliationEngine(
        execution_engine=execution_engine,
        state_store=state_store,
        event_bus=event_bus,
        kite_broker=kite_broker,
        mode="LIVE"
    )
    
    # Setup local positions
    state = state_store.load()
    state["positions"] = [
        {"symbol": "NIFTY24DECFUT", "qty": 50, "avg_price": 21000.0}
    ]
    state_store.save(state)
    
    # Setup broker positions (different)
    kite_broker.setup_positions([
        {
            "tradingsymbol": "NIFTY24DECFUT",
            "quantity": 75,  # Different quantity
            "average_price": 21000.0
        }
    ])
    
    # Reconcile positions
    await reconciler.reconcile_positions()
    
    # Wait for async event publishing
    await asyncio.sleep(0.1)
    
    # Check positions were synced
    state = state_store.load()
    positions = state.get("positions", [])
    assert len(positions) == 1
    assert positions[0]["qty"] == 75  # Should match broker
    
    # Check event was published
    assert len(published_events) > 0
    
    print(f"✅ Position mismatch detected")
    print(f"✅ Local positions rebuilt from broker")
    print(f"✅ POSITION_SYNCED event published")
    print("✅ Position reconciliation test passed\n")


async def test_position_reconciliation_paper_skip():
    """Test that position reconciliation is skipped in PAPER mode."""
    print("\n=== Test: Position Reconciliation Skip (PAPER) ===")
    
    execution_engine = MockExecutionEngine()
    state_store = MockStateStore()
    event_bus = EventBus()
    
    reconciler = ReconciliationEngine(
        execution_engine=execution_engine,
        state_store=state_store,
        event_bus=event_bus,
        mode="PAPER"
    )
    
    # Attempt position reconciliation
    await reconciler.reconcile_positions()
    
    print(f"✅ Position reconciliation skipped in PAPER mode (as expected)")
    print("✅ Position reconciliation skip test passed\n")


async def test_reconciliation_statistics():
    """Test reconciliation statistics tracking."""
    print("\n=== Test: Reconciliation Statistics ===")
    
    execution_engine = MockExecutionEngine()
    state_store = MockStateStore()
    event_bus = EventBus()
    
    reconciler = ReconciliationEngine(
        execution_engine=execution_engine,
        state_store=state_store,
        event_bus=event_bus,
        mode="PAPER"
    )
    
    # Initial state
    assert reconciler.reconciliation_count == 0
    assert reconciler.discrepancy_count == 0
    assert reconciler.last_reconciliation_time is None
    
    # Perform reconciliation
    await reconciler.reconcile_orders()
    
    assert reconciler.reconciliation_count == 1
    assert reconciler.last_reconciliation_time is not None
    
    # Add discrepancy
    local_order = Order(
        order_id="TEST-008",
        symbol="NIFTY24DECFUT",
        side="BUY",
        qty=50,
        order_type="MARKET",
        status=OrderStatus.PENDING,
        strategy="test_strategy"
    )
    
    broker_order = Order(
        order_id="TEST-008",
        symbol="NIFTY24DECFUT",
        side="BUY",
        qty=50,
        order_type="MARKET",
        status=OrderStatus.FILLED,
        strategy="test_strategy",
        filled_qty=50,
        avg_price=21000.0
    )
    
    await reconciler.register_order(local_order)
    execution_engine.add_order(broker_order)
    
    await reconciler.reconcile_orders()
    
    assert reconciler.reconciliation_count == 2
    assert reconciler.discrepancy_count == 1
    
    print(f"✅ Reconciliation count: {reconciler.reconciliation_count}")
    print(f"✅ Discrepancy count: {reconciler.discrepancy_count}")
    print(f"✅ Last reconciliation time: {reconciler.last_reconciliation_time}")
    print("✅ Statistics tracking test passed\n")


async def test_reconciliation_error_handling():
    """Test that reconciliation handles errors gracefully."""
    print("\n=== Test: Reconciliation Error Handling ===")
    
    # Create a mock execution engine that raises an exception
    class FailingExecutionEngine:
        async def poll_orders(self):
            raise Exception("Simulated broker failure")
    
    execution_engine = FailingExecutionEngine()
    state_store = MockStateStore()
    event_bus = EventBus()
    
    reconciler = ReconciliationEngine(
        execution_engine=execution_engine,
        state_store=state_store,
        event_bus=event_bus,
        mode="PAPER"
    )
    
    # Should not raise exception
    await reconciler.reconcile_orders()
    
    # Reconciliation count should NOT increment on failure (expected behavior)
    assert reconciler.reconciliation_count == 0
    
    print(f"✅ Exception caught and logged")
    print(f"✅ Reconciliation continued without crashing")
    print("✅ Error handling test passed\n")


# ============================================================================
# Main Test Runner
# ============================================================================

async def run_all_tests():
    """Run all tests."""
    print("\n" + "="*70)
    print("Running ReconciliationEngine Tests")
    print("="*70)
    
    try:
        await test_reconciliation_engine_initialization()
        await test_order_reconciliation_no_discrepancy()
        await test_order_status_discrepancy_pending_to_placed()
        await test_order_fill_reconciliation()
        await test_order_partial_fill_reconciliation()
        await test_order_cancelled_reconciliation()
        await test_order_rejected_reconciliation()
        await test_missing_order_in_broker()
        await test_position_reconciliation_live()
        await test_position_reconciliation_paper_skip()
        await test_reconciliation_statistics()
        await test_reconciliation_error_handling()
        
        print("\n" + "="*70)
        print("✅ ALL TESTS PASSED")
        print("="*70 + "\n")
        
    except Exception as exc:
        print(f"\n❌ TEST FAILED: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_all_tests())
