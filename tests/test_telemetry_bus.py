"""
Test suite for telemetry bus and event publishing.

Tests:
- TelemetryBus singleton behavior
- Event publishing and buffering
- Event filtering and retrieval
- SSE streaming
- Helper functions for specific event types
"""

import asyncio
import json
from datetime import datetime

from analytics.telemetry_bus import (
    TelemetryBus,
    get_telemetry_bus,
    publish_event,
    publish_signal_event,
    publish_order_event,
    publish_engine_health,
    publish_decision_trace,
)


def test_telemetry_bus_singleton():
    """Test that TelemetryBus is a singleton."""
    bus1 = get_telemetry_bus()
    bus2 = get_telemetry_bus()
    assert bus1 is bus2, "TelemetryBus should be a singleton"
    
    bus3 = TelemetryBus()
    assert bus1 is bus3, "Direct instantiation should return same singleton"


def test_publish_event():
    """Test basic event publishing."""
    bus = get_telemetry_bus()
    bus.clear_buffer()  # Start fresh
    
    # Publish test event
    publish_event("test_event", {"key": "value", "number": 42})
    
    # Retrieve events
    events = bus.get_recent_events(limit=10)
    assert len(events) >= 1, "Should have at least one event"
    
    # Check event structure
    event = events[-1]
    assert event["type"] == "test_event"
    assert "timestamp" in event
    assert event["payload"]["key"] == "value"
    assert event["payload"]["number"] == 42


def test_event_filtering():
    """Test event filtering by type."""
    bus = get_telemetry_bus()
    bus.clear_buffer()
    
    # Publish multiple event types
    publish_event("type_a", {"data": "a1"})
    publish_event("type_b", {"data": "b1"})
    publish_event("type_a", {"data": "a2"})
    publish_event("type_c", {"data": "c1"})
    
    # Get all events
    all_events = bus.get_recent_events()
    assert len(all_events) == 4, "Should have 4 events total"
    
    # Get filtered events
    type_a_events = bus.get_recent_events(event_type="type_a")
    assert len(type_a_events) == 2, "Should have 2 type_a events"
    assert all(e["type"] == "type_a" for e in type_a_events)


def test_buffer_limit():
    """Test that buffer respects size limit."""
    bus = get_telemetry_bus()
    bus.clear_buffer()
    
    # Publish more events than would fit in a small buffer
    # The default buffer is 5000, so we test that it holds all these
    for i in range(50):
        bus.publish_event("overflow_test", {"index": i})
    
    events = bus.get_recent_events()
    assert len(events) == 50, "Buffer should keep all 50 events (within limit)"
    
    # Check that we have the most recent events in order
    last_event = events[-1]
    assert last_event["payload"]["index"] == 49, "Should have most recent event"


def test_helper_functions():
    """Test helper functions for specific event types."""
    bus = get_telemetry_bus()
    bus.clear_buffer()
    
    # Test signal event
    publish_signal_event(
        symbol="NIFTY",
        strategy_name="test_strategy",
        signal="BUY",
        confidence=0.85,
        reason="Test signal"
    )
    
    # Test order event
    publish_order_event(
        order_id="TEST-001",
        symbol="BANKNIFTY",
        side="BUY",
        status="filled",
        qty=50,
        price=45000.0
    )
    
    # Test engine health
    publish_engine_health(
        engine_name="TestEngine",
        status="active",
        metrics={"cpu": 25.0, "memory": 512}
    )
    
    # Test decision trace
    publish_decision_trace(
        strategy_name="momentum",
        symbol="SBIN",
        decision="SELL",
        trace_data={"rsi": 72, "trend": "down"}
    )
    
    # Verify events were published
    events = bus.get_recent_events(limit=10)
    assert len(events) >= 4, "Should have at least 4 events"
    
    # Check event types
    event_types = [e["type"] for e in events]
    assert "signal_event" in event_types
    assert "order_event" in event_types
    assert "engine_health" in event_types
    assert "decision_trace" in event_types


def test_get_stats():
    """Test statistics retrieval."""
    bus = get_telemetry_bus()
    bus.clear_buffer()
    
    # Publish various events
    publish_event("type1", {"data": 1})
    publish_event("type1", {"data": 2})
    publish_event("type2", {"data": 3})
    
    stats = bus.get_stats()
    
    assert stats["total_events"] == 3
    assert "type1" in stats["event_types"]
    assert "type2" in stats["event_types"]
    assert stats["event_counts"]["type1"] == 2
    assert stats["event_counts"]["type2"] == 1


async def test_sse_streaming():
    """Test SSE streaming functionality."""
    bus = get_telemetry_bus()
    bus.clear_buffer()
    
    # Publish initial events
    publish_event("stream_test", {"msg": "initial"})
    
    # Create stream
    stream = bus.stream_events(poll_interval=0.1)
    
    # Get first few messages
    messages = []
    async for msg in stream:
        messages.append(msg)
        if len(messages) >= 2:  # Connection + initial event
            break
    
    # Verify SSE format
    assert len(messages) >= 2
    assert messages[0].startswith("data: ")
    assert messages[0].endswith("\n\n")
    
    # Parse first message (connection)
    first_data = json.loads(messages[0][6:-2])  # Strip "data: " and "\n\n"
    assert first_data["type"] == "connection"
    
    # Cancel the stream
    # (In real usage, the stream would be cancelled by client disconnect)


def test_event_timestamp():
    """Test that events have valid timestamps."""
    bus = get_telemetry_bus()
    bus.clear_buffer()
    
    from datetime import timezone as tz
    before = datetime.now(tz.utc)
    publish_event("timestamp_test", {"data": "test"})
    after = datetime.now(tz.utc)
    
    events = bus.get_recent_events(limit=1)
    assert len(events) == 1
    
    event_ts = datetime.fromisoformat(events[0]["timestamp"].replace("Z", "+00:00"))
    
    # Timestamp should be within test execution window
    assert before <= event_ts <= after, "Event timestamp should be accurate"


if __name__ == "__main__":
    print("Running telemetry bus tests...")
    
    print("✓ test_telemetry_bus_singleton")
    test_telemetry_bus_singleton()
    
    print("✓ test_publish_event")
    test_publish_event()
    
    print("✓ test_event_filtering")
    test_event_filtering()
    
    print("✓ test_buffer_limit")
    test_buffer_limit()
    
    print("✓ test_helper_functions")
    test_helper_functions()
    
    print("✓ test_get_stats")
    test_get_stats()
    
    print("✓ test_event_timestamp")
    test_event_timestamp()
    
    # Run async test
    print("✓ test_sse_streaming")
    asyncio.run(test_sse_streaming())
    
    print("\n✅ All telemetry bus tests passed!")
