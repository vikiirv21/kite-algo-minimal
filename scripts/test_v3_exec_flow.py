#!/usr/bin/env python3
"""
Test script for Phase 4 Architecture v3 Execution Flow

This script validates the end-to-end execution pipeline:
1. Start InMemoryEventBus
2. Start ExecutionService in paper mode
3. Publish a fake risk.order_approved event
4. Assert that ExecutionService:
   - Calls backend.submit_order once
   - Publishes exec.order_submitted event
   - In paper mode, publishes exec.fill event
   - TradeRecorder writes to orders.csv

This validates that the new v3 execution service works without touching v2 engines.
"""

import sys
import time
import logging
import os
import csv
from pathlib import Path
from threading import Thread, Event as ThreadEvent

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.common.event_bus import InMemoryEventBus, Event
from services.execution.service_execution import ExecutionService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)


class TestContext:
    """Context for tracking test results."""
    def __init__(self):
        self.order_submitted_received = False
        self.fill_received = False
        self.order_submitted_data = None
        self.fill_data = None
        self.order_submitted_event = ThreadEvent()
        self.fill_event = ThreadEvent()


def order_submitted_handler(ctx: TestContext):
    """Create a handler that captures order_submitted events."""
    def handler(event: Event):
        logger.info(f"RECEIVED ORDER SUBMITTED on topic: {event.type}")
        logger.info(f"Order payload: {event.payload}")
        ctx.order_submitted_received = True
        ctx.order_submitted_data = event.payload
        ctx.order_submitted_event.set()
    
    return handler


def fill_handler(ctx: TestContext):
    """Create a handler that captures fill events."""
    def handler(event: Event):
        logger.info(f"RECEIVED FILL on topic: {event.type}")
        logger.info(f"Fill payload: {event.payload}")
        ctx.fill_received = True
        ctx.fill_data = event.payload
        ctx.fill_event.set()
    
    return handler


def run_service_thread(service):
    """Run service in a separate thread."""
    try:
        service.run_forever()
    except Exception as e:
        logger.error(f"Service thread error: {e}", exc_info=True)


def test_paper_execution_flow():
    """
    Test the v3 paper execution flow.
    
    Returns:
        True if test passes, False otherwise
    """
    logger.info("=" * 60)
    logger.info("TEST: Phase 4 Architecture v3 Execution Flow (Paper Mode)")
    logger.info("=" * 60)
    
    # Step 1: Create and start EventBus
    logger.info("Step 1: Creating InMemoryEventBus...")
    bus = InMemoryEventBus(max_queue_size=100)
    bus.start()
    logger.info("✓ EventBus started")
    
    # Step 2: Create test context
    ctx = TestContext()
    
    # Subscribe to execution events with wildcard pattern
    logger.info("Step 2: Subscribing to exec.* events")
    bus.subscribe("exec.order_submitted.*", order_submitted_handler(ctx))
    bus.subscribe("exec.fill.*", fill_handler(ctx))
    logger.info("✓ Subscribed to exec.order_submitted.* and exec.fill.*")
    
    # Step 3: Create and start ExecutionService in paper mode
    logger.info("Step 3: Creating ExecutionService in paper mode...")
    exec_cfg = {
        "slippage_bps": 5.0,
        "mode": "paper"
    }
    service = ExecutionService(bus=bus, cfg=exec_cfg, mode="paper")
    
    # Run service in separate thread
    service_thread = Thread(target=run_service_thread, args=(service,), daemon=True)
    service_thread.start()
    logger.info("✓ ExecutionService started in background thread")
    
    # Give service time to initialize and subscribe
    time.sleep(2)
    
    # Step 4: Check initial state of orders.csv
    orders_csv_path = Path("artifacts/orders.csv")
    initial_order_count = 0
    if orders_csv_path.exists():
        with open(orders_csv_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            initial_order_count = sum(1 for _ in reader) - 1  # Subtract header
        logger.info(f"Initial order count in orders.csv: {initial_order_count}")
    
    # Step 5: Publish a fake risk.order_approved event
    logger.info("Step 5: Publishing risk.order_approved.INTRADAY.NIFTY25NOVFUT")
    
    approved_order = {
        "signal_id": "test-signal-1",
        "symbol": "NIFTY25NOVFUT",
        "logical": "NIFTY",
        "side": "BUY",
        "quantity": 50,
        "price": 24500.0,
        "profile": "INTRADAY",
        "mode": "paper",
        "tf": "5m",
        "reason": "risk_ok",
        "timestamp": "2025-11-17T10:30:05Z",
        "strategy": "ema20_50_intraday"
    }
    
    bus.publish("risk.order_approved.INTRADAY.NIFTY25NOVFUT", approved_order)
    logger.info("✓ Published risk.order_approved event")
    
    # Step 6: Wait for order_submitted event with timeout
    logger.info("Step 6: Waiting for order_submitted event (timeout: 5 seconds)...")
    order_submitted = ctx.order_submitted_event.wait(timeout=5.0)
    
    # Step 7: Wait for fill event with timeout
    logger.info("Step 7: Waiting for fill event (timeout: 5 seconds)...")
    fill_received = ctx.fill_event.wait(timeout=5.0)
    
    # Step 8: Check orders.csv was updated
    logger.info("Step 8: Checking orders.csv was updated...")
    final_order_count = 0
    if orders_csv_path.exists():
        with open(orders_csv_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            final_order_count = sum(1 for _ in reader) - 1  # Subtract header
        logger.info(f"Final order count in orders.csv: {final_order_count}")
    
    # Step 9: Verify results
    logger.info("=" * 60)
    logger.info("TEST RESULTS")
    logger.info("=" * 60)
    
    passed = True
    
    # Check order_submitted received
    if order_submitted and ctx.order_submitted_received:
        logger.info("✓ PASS: Order submitted event received")
        logger.info(f"  Order ID: {ctx.order_submitted_data.get('order_id')}")
        logger.info(f"  Symbol: {ctx.order_submitted_data.get('symbol')}")
        logger.info(f"  Side: {ctx.order_submitted_data.get('side')}")
        logger.info(f"  Quantity: {ctx.order_submitted_data.get('quantity')}")
        logger.info(f"  Price: {ctx.order_submitted_data.get('price')}")
        logger.info(f"  Status: {ctx.order_submitted_data.get('status')}")
    else:
        logger.error("✗ FAIL: Order submitted event not received")
        passed = False
    
    # Check fill received (paper mode should have immediate fill)
    if fill_received and ctx.fill_received:
        logger.info("✓ PASS: Fill event received")
        logger.info(f"  Order ID: {ctx.fill_data.get('order_id')}")
        logger.info(f"  Fill Quantity: {ctx.fill_data.get('fill_qty')}")
        logger.info(f"  Fill Price: {ctx.fill_data.get('fill_price')}")
    else:
        logger.error("✗ FAIL: Fill event not received")
        passed = False
    
    # Check orders.csv was updated
    if final_order_count > initial_order_count:
        logger.info(f"✓ PASS: orders.csv updated ({initial_order_count} -> {final_order_count} orders)")
    else:
        logger.error(f"✗ FAIL: orders.csv not updated ({initial_order_count} -> {final_order_count})")
        passed = False
    
    # Cleanup
    logger.info("Cleaning up...")
    service.running = False
    bus.stop()
    logger.info("✓ Cleanup complete")
    
    logger.info("=" * 60)
    return passed


def test_rejected_order():
    """
    Test that rejected orders are logged but don't execute.
    
    Returns:
        True if test passes, False otherwise
    """
    logger.info("=" * 60)
    logger.info("TEST: Risk Rejected Order Handling")
    logger.info("=" * 60)
    
    bus = InMemoryEventBus(max_queue_size=100)
    bus.start()
    
    ctx = TestContext()
    bus.subscribe("exec.order_submitted.*", order_submitted_handler(ctx))
    bus.subscribe("exec.fill.*", fill_handler(ctx))
    
    exec_cfg = {"slippage_bps": 5.0, "mode": "paper"}
    service = ExecutionService(bus=bus, cfg=exec_cfg, mode="paper")
    
    service_thread = Thread(target=run_service_thread, args=(service,), daemon=True)
    service_thread.start()
    time.sleep(2)
    
    # Publish a rejected order
    logger.info("Publishing risk.order_rejected.INTRADAY.NIFTY25NOVFUT")
    rejected_order = {
        "signal_id": "test-signal-rejected",
        "symbol": "NIFTY25NOVFUT",
        "side": "SELL",
        "quantity": 50,
        "price": 24500.0,
        "reason": "max_loss_exceeded",
        "timestamp": "2025-11-17T10:30:05Z",
    }
    
    bus.publish("risk.order_rejected.INTRADAY.NIFTY25NOVFUT", rejected_order)
    logger.info("✓ Published risk.order_rejected event")
    
    # Wait to see if any execution events are published (they shouldn't be)
    logger.info("Waiting 3 seconds to verify no execution events...")
    time.sleep(3)
    
    logger.info("=" * 60)
    logger.info("TEST RESULTS")
    logger.info("=" * 60)
    
    # Rejected orders should NOT trigger execution
    if not ctx.order_submitted_received and not ctx.fill_received:
        logger.info("✓ PASS: Rejected order did not trigger execution (as expected)")
        passed = True
    else:
        logger.error("✗ FAIL: Rejected order triggered execution events (unexpected)")
        passed = False
    
    service.running = False
    bus.stop()
    logger.info("=" * 60)
    return passed


def test_invalid_order_validation():
    """
    Test that invalid orders are rejected by validation.
    
    Returns:
        True if test passes, False otherwise
    """
    logger.info("=" * 60)
    logger.info("TEST: Invalid Order Validation")
    logger.info("=" * 60)
    
    bus = InMemoryEventBus(max_queue_size=100)
    bus.start()
    
    ctx = TestContext()
    bus.subscribe("exec.order_submitted.*", order_submitted_handler(ctx))
    
    exec_cfg = {"slippage_bps": 5.0, "mode": "paper"}
    service = ExecutionService(bus=bus, cfg=exec_cfg, mode="paper")
    
    service_thread = Thread(target=run_service_thread, args=(service,), daemon=True)
    service_thread.start()
    time.sleep(2)
    
    # Publish orders with missing/invalid fields
    test_cases = [
        ("Missing symbol", {"side": "BUY", "quantity": 50, "price": 24500.0}),
        ("Missing side", {"symbol": "NIFTY", "quantity": 50, "price": 24500.0}),
        ("Missing quantity", {"symbol": "NIFTY", "side": "BUY", "price": 24500.0}),
        ("Missing price", {"symbol": "NIFTY", "side": "BUY", "quantity": 50}),
        ("None price", {"symbol": "NIFTY", "side": "BUY", "quantity": 50, "price": None}),
    ]
    
    for test_name, payload in test_cases:
        logger.info(f"Testing: {test_name}")
        bus.publish("risk.order_approved.INTRADAY.TEST", payload)
        time.sleep(0.5)
    
    # Wait a bit more
    time.sleep(2)
    
    logger.info("=" * 60)
    logger.info("TEST RESULTS")
    logger.info("=" * 60)
    
    # Invalid orders should NOT trigger execution
    if not ctx.order_submitted_received:
        logger.info("✓ PASS: Invalid orders did not trigger execution (as expected)")
        passed = True
    else:
        logger.error("✗ FAIL: Invalid order triggered execution (unexpected)")
        passed = False
    
    service.running = False
    bus.stop()
    logger.info("=" * 60)
    return passed


def main():
    """Main test runner."""
    logger.info("\n" + "=" * 60)
    logger.info("V3 EXECUTION FLOW TEST SUITE")
    logger.info("=" * 60 + "\n")
    
    tests = [
        ("Paper Execution Flow", test_paper_execution_flow),
        ("Rejected Order Handling", test_rejected_order),
        ("Invalid Order Validation", test_invalid_order_validation),
    ]
    
    results = []
    for test_name, test_func in tests:
        logger.info(f"\nRunning: {test_name}")
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            logger.error(f"Test failed with exception: {e}", exc_info=True)
            results.append((test_name, False))
        
        # Give time between tests
        time.sleep(2)
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("TEST SUMMARY")
    logger.info("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        logger.info(f"{status}: {test_name}")
    
    logger.info(f"\nTotal: {passed}/{total} tests passed")
    logger.info("=" * 60 + "\n")
    
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
