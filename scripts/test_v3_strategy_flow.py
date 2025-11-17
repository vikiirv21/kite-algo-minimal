#!/usr/bin/env python3
"""
Test script for Phase 2 Architecture v3 Strategy Flow

This script validates the end-to-end pipeline:
1. Start InMemoryEventBus
2. Start StrategyService
3. Publish a fake strategy evaluation request
4. Assert that StrategyService publishes a SIGNAL event
5. Print the signal

This validates that the new v3 services work without touching v2 engines.
"""

import sys
import time
import logging
from pathlib import Path
from threading import Thread, Event as ThreadEvent

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.common.event_bus import InMemoryEventBus, Event
from services.strategy.service_strategy import StrategyService, ServiceConfig

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
        self.received_signal = False
        self.signal_data = None
        self.signal_event = ThreadEvent()


def signal_handler(ctx: TestContext):
    """
    Create a handler that captures signal events.
    
    Args:
        ctx: Test context to store results
    
    Returns:
        Handler function
    """
    def handler(event: Event):
        logger.info(f"RECEIVED SIGNAL on topic: {event.type}")
        logger.info(f"Signal payload: {event.payload}")
        ctx.received_signal = True
        ctx.signal_data = event.payload
        ctx.signal_event.set()
    
    return handler


def run_service_thread(service):
    """Run service in a separate thread."""
    try:
        service.run_forever()
    except Exception as e:
        logger.error(f"Service thread error: {e}", exc_info=True)


def test_strategy_flow():
    """
    Test the v3 strategy flow.
    
    Returns:
        True if test passes, False otherwise
    """
    logger.info("=" * 60)
    logger.info("TEST: Phase 2 Architecture v3 Strategy Flow")
    logger.info("=" * 60)
    
    # Step 1: Create and start EventBus
    logger.info("Step 1: Creating InMemoryEventBus...")
    bus = InMemoryEventBus(max_queue_size=100)
    bus.start()
    logger.info("✓ EventBus started")
    
    # Step 2: Create test context
    ctx = TestContext()
    
    # Subscribe to signals with wildcard pattern
    logger.info("Step 2: Subscribing to signals.*")
    bus.subscribe("signals.*", signal_handler(ctx))
    logger.info("✓ Subscribed to signals.*")
    
    # Step 3: Create and start StrategyService
    logger.info("Step 3: Creating StrategyService...")
    config = ServiceConfig(
        name="strategy",
        enabled=True,
        history_lookback=200,
        strategies=[],
        timeframe="5m"
    )
    service = StrategyService(event_bus=bus, config=config)
    
    # Run service in separate thread
    service_thread = Thread(target=run_service_thread, args=(service,), daemon=True)
    service_thread.start()
    logger.info("✓ StrategyService started in background thread")
    
    # Give service time to initialize and subscribe
    time.sleep(2)
    
    # Step 4: Publish a fake strategy evaluation request
    logger.info("Step 4: Publishing fake eval request to strategy.eval_request.fno.NIFTY")
    
    eval_request = {
        "symbol": "NIFTY",
        "logical": "NIFTY",
        "asset_class": "fno",
        "tf": "5m",
        "price": 18000.0,
        "mode": "test",
        "timestamp": "2025-11-17T14:00:00",
        "bar": {
            "open": 17995.0,
            "high": 18010.0,
            "low": 17990.0,
            "close": 18000.0,
            "volume": 1000,
            "timestamp": "2025-11-17T14:00:00"
        }
    }
    
    bus.publish("strategy.eval_request.fno.NIFTY", eval_request)
    logger.info("✓ Published eval request")
    
    # Step 5: Wait for signal with timeout
    logger.info("Step 5: Waiting for signal (timeout: 5 seconds)...")
    signal_received = ctx.signal_event.wait(timeout=5.0)
    
    # Step 6: Verify results
    logger.info("=" * 60)
    logger.info("TEST RESULTS")
    logger.info("=" * 60)
    
    if signal_received and ctx.received_signal:
        logger.info("✓ PASS: Signal received successfully!")
        logger.info(f"  Symbol: {ctx.signal_data.get('symbol')}")
        logger.info(f"  Asset Class: {ctx.signal_data.get('asset_class')}")
        logger.info(f"  Action: {ctx.signal_data.get('action')}")
        logger.info(f"  Price: {ctx.signal_data.get('price')}")
        logger.info(f"  Confidence: {ctx.signal_data.get('confidence')}")
        logger.info(f"  Reason: {ctx.signal_data.get('reason')}")
        result = True
    else:
        logger.error("✗ FAIL: No signal received within timeout")
        result = False
    
    # Cleanup
    logger.info("Cleaning up...")
    service.running = False
    bus.stop()
    logger.info("✓ Cleanup complete")
    
    logger.info("=" * 60)
    return result


def test_multiple_asset_classes():
    """
    Test strategy flow with multiple asset classes.
    
    Returns:
        True if test passes, False otherwise
    """
    logger.info("=" * 60)
    logger.info("TEST: Multiple Asset Classes")
    logger.info("=" * 60)
    
    bus = InMemoryEventBus(max_queue_size=100)
    bus.start()
    
    ctx = TestContext()
    signals_received = []
    
    def multi_signal_handler(event: Event):
        logger.info(f"RECEIVED SIGNAL on topic: {event.type}")
        signals_received.append(event.payload)
        if len(signals_received) >= 3:
            ctx.signal_event.set()
    
    bus.subscribe("signals.*", multi_signal_handler)
    
    config = ServiceConfig(name="strategy", enabled=True)
    service = StrategyService(event_bus=bus, config=config)
    
    service_thread = Thread(target=run_service_thread, args=(service,), daemon=True)
    service_thread.start()
    time.sleep(2)
    
    # Publish requests for different asset classes
    test_requests = [
        ("fno", "NIFTY", 18000.0),
        ("eq", "RELIANCE", 2500.0),
        ("options", "BANKNIFTY", 42000.0),
    ]
    
    logger.info("Publishing eval requests for 3 different asset classes...")
    for asset_class, symbol, price in test_requests:
        eval_request = {
            "symbol": symbol,
            "logical": symbol,
            "asset_class": asset_class,
            "tf": "5m",
            "price": price,
            "mode": "test",
            "timestamp": "2025-11-17T14:00:00",
        }
        topic = f"strategy.eval_request.{asset_class}.{symbol}"
        bus.publish(topic, eval_request)
        logger.info(f"  Published to {topic}")
        time.sleep(0.5)  # Small delay between publishes
    
    # Wait for all signals
    logger.info("Waiting for signals (timeout: 5 seconds)...")
    received = ctx.signal_event.wait(timeout=5.0)
    
    logger.info("=" * 60)
    logger.info("TEST RESULTS")
    logger.info("=" * 60)
    
    if len(signals_received) >= 3:
        logger.info(f"✓ PASS: Received {len(signals_received)} signals")
        for i, signal in enumerate(signals_received, 1):
            logger.info(f"  Signal {i}: {signal.get('symbol')} ({signal.get('asset_class')}) - {signal.get('action')}")
        result = True
    else:
        logger.error(f"✗ FAIL: Only received {len(signals_received)}/3 signals")
        result = False
    
    service.running = False
    bus.stop()
    logger.info("=" * 60)
    return result


def main():
    """Main test runner."""
    logger.info("\n" + "=" * 60)
    logger.info("V3 STRATEGY FLOW TEST SUITE")
    logger.info("=" * 60 + "\n")
    
    tests = [
        ("Basic Strategy Flow", test_strategy_flow),
        ("Multiple Asset Classes", test_multiple_asset_classes),
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
        time.sleep(1)
    
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
