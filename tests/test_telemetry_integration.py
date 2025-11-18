"""
Integration test demonstrating the full telemetry flow.

This test simulates:
1. MarketDataEngine publishing status and lookup failures
2. StrategyEngineV2 publishing signals and decision traces
3. ExecutionEngine publishing order events
4. Universe scanner publishing scan results
5. Retrieving events via the telemetry bus

Run this test to verify all components integrate correctly.
"""

import time
from analytics.telemetry_bus import (
    get_telemetry_bus,
    publish_signal_event,
    publish_order_event,
    publish_engine_health,
    publish_decision_trace,
    publish_universe_scan,
    publish_indicator_event,
)


def simulate_market_data_engine():
    """Simulate MarketDataEngine telemetry publishing."""
    print("\n📊 Simulating MarketDataEngine...")
    
    # Publish MDE status
    publish_engine_health(
        engine_name="MarketDataEngine",
        status="active",
        metrics={
            "cached_symbols": 15,
            "total_candles": 3000,
            "meta_entries": 150,
            "lookup_failures": 2,
            "stale_symbols_count": 1,
            "has_kite_client": True,
        }
    )
    print("  ✓ Published MDE status")
    
    # Publish lookup failure
    from analytics.telemetry_bus import publish_event
    publish_event("mde_lookup_failure", {
        "symbol": "INVALID",
        "exchange_tried": "NSE"
    })
    print("  ✓ Published lookup failure")
    
    # Publish stale symbols
    publish_event("mde_stale_symbols", {
        "count": 1,
        "symbols": [{"symbol": "OLDSYM", "timeframe": "5m", "age_minutes": 120}]
    })
    print("  ✓ Published stale symbols")


def simulate_strategy_engine():
    """Simulate StrategyEngineV2 telemetry publishing."""
    print("\n🎯 Simulating StrategyEngineV2...")
    
    # Publish strategy health
    publish_engine_health(
        engine_name="StrategyEngineV2",
        status="active",
        metrics={
            "total_strategies": 3,
            "avg_win_rate": 0.62,
            "max_loss_streak": 2,
            "avg_confidence": 0.75,
            "strategies": {
                "momentum": {"win_rate": 0.65, "loss_streak": 1, "open_positions": 2},
                "mean_reversion": {"win_rate": 0.58, "loss_streak": 2, "open_positions": 1},
            }
        }
    )
    print("  ✓ Published strategy health")
    
    # Publish indicator event
    publish_indicator_event(
        symbol="NIFTY",
        timeframe="5m",
        indicators={
            "rsi": 45.2,
            "ema_20": 19750.5,
            "ema_50": 19700.3,
            "atr": 50.8,
        },
        strategy="momentum"
    )
    print("  ✓ Published indicator calculations")
    
    # Publish decision trace
    publish_decision_trace(
        strategy_name="momentum",
        symbol="NIFTY",
        decision="BUY",
        trace_data={
            "reason": "RSI oversold + EMA crossover",
            "confidence": 0.85,
            "timeframe": "5m",
            "close_price": 19755.0,
        }
    )
    print("  ✓ Published decision trace")
    
    # Publish signal event
    publish_signal_event(
        symbol="NIFTY",
        strategy_name="momentum",
        signal="BUY",
        confidence=0.85,
        reason="RSI oversold + EMA crossover",
        timeframe="5m",
    )
    print("  ✓ Published signal event")


def simulate_execution_engine():
    """Simulate ExecutionEngine telemetry publishing."""
    print("\n⚡ Simulating ExecutionEngine...")
    
    # Publish order creation
    publish_order_event(
        order_id="PAPER-20251118-0001",
        symbol="NIFTY",
        side="BUY",
        status="new",
        strategy="momentum",
        order_type="MARKET",
    )
    print("  ✓ Published order creation")
    
    # Simulate small delay
    time.sleep(0.1)
    
    # Publish order fill
    publish_order_event(
        order_id="PAPER-20251118-0001",
        symbol="NIFTY",
        side="BUY",
        status="filled",
        qty=50,
        price=19755.0,
        remaining_qty=0,
        strategy="momentum",
        order_type="MARKET",
    )
    print("  ✓ Published order fill")
    
    # Publish order rejection (different order)
    publish_order_event(
        order_id="PAPER-20251118-0002",
        symbol="BANKNIFTY",
        side="SELL",
        status="rejected",
        reason="Insufficient margin",
        strategy="mean_reversion",
    )
    print("  ✓ Published order rejection")


def simulate_universe_scanner():
    """Simulate universe scanner telemetry publishing."""
    print("\n🌐 Simulating Universe Scanner...")
    
    # Publish equity universe scan
    publish_universe_scan(
        scan_type="equity",
        universe_size=250,
        summary={
            "exchange": "NSE",
            "instrument_types": ["EQ"],
        }
    )
    print("  ✓ Published equity universe scan")
    
    # Publish FnO universe scan
    publish_universe_scan(
        scan_type="fno",
        universe_size=1500,
        summary={
            "exchange": "NFO",
            "instrument_types": ["FUT", "CE", "PE"],
        }
    )
    print("  ✓ Published FnO universe scan")


def analyze_telemetry():
    """Analyze collected telemetry data."""
    print("\n📈 Analyzing Telemetry Data...")
    
    bus = get_telemetry_bus()
    
    # Get overall statistics
    stats = bus.get_stats()
    print(f"\nOverall Statistics:")
    print(f"  Total events: {stats['total_events']}")
    print(f"  Event types: {len(stats['event_types'])}")
    print(f"  Event type breakdown:")
    for event_type, count in sorted(stats['event_counts'].items()):
        print(f"    - {event_type}: {count}")
    
    # Get events by type
    print(f"\n📋 Events by Type:")
    for event_type in stats['event_types']:
        events = bus.get_recent_events(event_type=event_type, limit=10)
        print(f"  {event_type}: {len(events)} event(s)")
    
    # Show some sample events
    print(f"\n🔍 Sample Events:")
    all_events = bus.get_recent_events(limit=5)
    for i, event in enumerate(all_events[-5:], 1):
        print(f"  {i}. [{event['type']}] @ {event['timestamp'][:19]}")
        print(f"     Payload: {event['payload']}")


def main():
    """Run the complete integration test."""
    print("=" * 70)
    print("🚀 Telemetry System Integration Test")
    print("=" * 70)
    
    # Clear buffer for clean test
    bus = get_telemetry_bus()
    bus.clear_buffer()
    
    # Simulate all engines
    simulate_market_data_engine()
    simulate_strategy_engine()
    simulate_execution_engine()
    simulate_universe_scanner()
    
    # Analyze collected data
    analyze_telemetry()
    
    print("\n" + "=" * 70)
    print("✅ Integration test completed successfully!")
    print("=" * 70)
    print("\nAll telemetry events are now available via:")
    print("  - GET /api/telemetry/stats")
    print("  - GET /api/telemetry/events")
    print("  - GET /api/telemetry/stream (SSE)")


if __name__ == "__main__":
    main()
