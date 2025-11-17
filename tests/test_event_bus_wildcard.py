#!/usr/bin/env python3
"""
Unit tests for InMemoryEventBus wildcard subscription support.

Tests the wildcard prefix matching feature added for v3 architecture.
"""

import sys
import time
from pathlib import Path
from threading import Event as ThreadEvent

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.common.event_bus import InMemoryEventBus, Event


def test_wildcard_single_subscription():
    """Test that wildcard subscriptions work for a single pattern."""
    print("Test: Wildcard single subscription")
    
    bus = InMemoryEventBus()
    bus.start()
    
    received_events = []
    wait_event = ThreadEvent()
    
    def handler(event: Event):
        received_events.append(event.type)
        if len(received_events) >= 2:
            wait_event.set()
    
    # Subscribe with wildcard
    bus.subscribe("strategy.eval_request.*", handler)
    
    # Publish matching events
    bus.publish("strategy.eval_request.fno.NIFTY", {"test": 1})
    bus.publish("strategy.eval_request.eq.RELIANCE", {"test": 2})
    
    # Publish non-matching event
    bus.publish("signals.fno.NIFTY", {"test": 3})
    
    # Wait for events
    wait_event.wait(timeout=2.0)
    
    bus.stop()
    
    # Verify
    assert len(received_events) == 2, f"Expected 2 events, got {len(received_events)}"
    assert "strategy.eval_request.fno.NIFTY" in received_events
    assert "strategy.eval_request.eq.RELIANCE" in received_events
    assert "signals.fno.NIFTY" not in received_events
    
    print("✓ PASS")


def test_wildcard_multiple_levels():
    """Test that wildcards work at different levels."""
    print("Test: Wildcard multiple levels")
    
    bus = InMemoryEventBus()
    bus.start()
    
    bars_received = []
    signals_received = []
    wait_bars = ThreadEvent()
    wait_signals = ThreadEvent()
    
    def bars_handler(event: Event):
        bars_received.append(event.type)
        if len(bars_received) >= 2:
            wait_bars.set()
    
    def signals_handler(event: Event):
        signals_received.append(event.type)
        if len(signals_received) >= 2:
            wait_signals.set()
    
    # Subscribe to different wildcards
    bus.subscribe("bars.*", bars_handler)
    bus.subscribe("signals.*", signals_handler)
    
    # Publish events
    bus.publish("bars.fno.NIFTY", {})
    bus.publish("bars.eq.RELIANCE", {})
    bus.publish("signals.fno.NIFTY", {})
    bus.publish("signals.eq.TCS", {})
    
    # Wait for events
    wait_bars.wait(timeout=2.0)
    wait_signals.wait(timeout=2.0)
    
    bus.stop()
    
    # Verify
    assert len(bars_received) == 2, f"Expected 2 bars events, got {len(bars_received)}"
    assert len(signals_received) == 2, f"Expected 2 signals events, got {len(signals_received)}"
    
    print("✓ PASS")


def test_exact_match_still_works():
    """Test that exact matches still work alongside wildcards."""
    print("Test: Exact match still works")
    
    bus = InMemoryEventBus()
    bus.start()
    
    exact_received = []
    wildcard_received = []
    wait_event = ThreadEvent()
    
    def exact_handler(event: Event):
        exact_received.append(event.type)
        if len(exact_received) >= 1:
            wait_event.set()
    
    def wildcard_handler(event: Event):
        wildcard_received.append(event.type)
    
    # Subscribe with both exact and wildcard
    bus.subscribe("bars.fno.NIFTY", exact_handler)
    bus.subscribe("bars.*", wildcard_handler)
    
    # Publish matching event
    bus.publish("bars.fno.NIFTY", {})
    
    # Wait for events
    wait_event.wait(timeout=2.0)
    
    bus.stop()
    
    # Verify - should receive on both handlers
    assert len(exact_received) == 1
    assert len(wildcard_received) == 1
    assert exact_received[0] == "bars.fno.NIFTY"
    assert wildcard_received[0] == "bars.fno.NIFTY"
    
    print("✓ PASS")


def test_no_wildcard_in_middle():
    """Test that wildcard only works at the end."""
    print("Test: Wildcard only at end")
    
    bus = InMemoryEventBus()
    bus.start()
    
    received = []
    
    def handler(event: Event):
        received.append(event.type)
    
    # Subscribe with wildcard at end (valid)
    bus.subscribe("strategy.eval_request.*", handler)
    
    # Publish events
    bus.publish("strategy.eval_request.fno.NIFTY", {})
    bus.publish("strategy.eval_request.eq.RELIANCE", {})
    
    time.sleep(0.5)
    bus.stop()
    
    # Should receive both
    assert len(received) == 2
    
    print("✓ PASS")


def run_all_tests():
    """Run all tests."""
    tests = [
        test_wildcard_single_subscription,
        test_wildcard_multiple_levels,
        test_exact_match_still_works,
        test_no_wildcard_in_middle,
    ]
    
    print("=" * 60)
    print("InMemoryEventBus Wildcard Tests")
    print("=" * 60)
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"✗ FAIL: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ ERROR: {e}")
            failed += 1
    
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
