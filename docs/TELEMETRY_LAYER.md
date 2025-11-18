# Real-Time Strategy & Market Telemetry Layer

## Overview

The telemetry layer provides real-time event streaming and monitoring for all engine components in the kite-algo-minimal backend. It enables observability into strategy execution, market data processing, order management, and system health.

## Architecture

### Core Components

1. **TelemetryBus** (`analytics/telemetry_bus.py`)
   - Singleton pattern for centralized event management
   - Thread-safe event publishing
   - In-memory event buffering (default: 5000 events)
   - SSE (Server-Sent Events) streaming support

2. **Engine Integration**
   - MarketDataEngine: Status updates every 3 seconds
   - StrategyEngineV2: Health metrics every 5 seconds
   - ExecutionEngine: Order lifecycle events
   - UniverseBuilder: Scan results on refresh

3. **REST API Endpoints**
   - `GET /api/telemetry/stream` - SSE event stream
   - `GET /api/telemetry/stats` - Statistics
   - `GET /api/telemetry/events` - Recent events query

## Event Types

### 1. signal_event
Strategy signals when decisions are made.

```json
{
  "type": "signal_event",
  "timestamp": "2025-11-18T07:55:41.123456Z",
  "payload": {
    "symbol": "NIFTY",
    "strategy_name": "momentum",
    "signal": "BUY",
    "confidence": 0.85,
    "reason": "RSI oversold + EMA crossover",
    "timeframe": "5m"
  }
}
```

### 2. indicator_event
Indicator calculations from strategies.

```json
{
  "type": "indicator_event",
  "timestamp": "2025-11-18T07:55:41.234567Z",
  "payload": {
    "symbol": "NIFTY",
    "timeframe": "5m",
    "indicators": {
      "rsi": 45.2,
      "ema_20": 19750.5,
      "ema_50": 19700.3,
      "atr": 50.8
    },
    "strategy": "momentum"
  }
}
```

### 3. order_event
Order lifecycle events (create/fill/reject).

```json
{
  "type": "order_event",
  "timestamp": "2025-11-18T07:55:41.345678Z",
  "payload": {
    "order_id": "PAPER-20251118-0001",
    "symbol": "NIFTY",
    "side": "BUY",
    "status": "filled",
    "qty": 50,
    "price": 19755.0,
    "remaining_qty": 0,
    "strategy": "momentum",
    "order_type": "MARKET"
  }
}
```

### 4. position_event
Position updates when trades execute.

```json
{
  "type": "position_event",
  "timestamp": "2025-11-18T07:55:41.456789Z",
  "payload": {
    "symbol": "NIFTY",
    "position_size": 50,
    "entry_price": 19755.0,
    "strategy": "momentum"
  }
}
```

### 5. engine_health
Engine health and performance metrics.

```json
{
  "type": "engine_health",
  "timestamp": "2025-11-18T07:55:41.567890Z",
  "payload": {
    "engine_name": "StrategyEngineV2",
    "status": "active",
    "metrics": {
      "total_strategies": 3,
      "avg_win_rate": 0.62,
      "max_loss_streak": 2,
      "avg_confidence": 0.75,
      "strategies": {
        "momentum": {
          "win_rate": 0.65,
          "loss_streak": 1,
          "open_positions": 2
        }
      }
    }
  }
}
```

### 6. decision_trace
Detailed strategy decision traces.

```json
{
  "type": "decision_trace",
  "timestamp": "2025-11-18T07:55:41.678901Z",
  "payload": {
    "strategy_name": "momentum",
    "symbol": "NIFTY",
    "decision": "BUY",
    "trace_data": {
      "reason": "RSI oversold + EMA crossover",
      "confidence": 0.85,
      "timeframe": "5m",
      "close_price": 19755.0
    }
  }
}
```

### 7. universe_scan
Universe scanning results.

```json
{
  "type": "universe_scan",
  "timestamp": "2025-11-18T07:55:41.789012Z",
  "payload": {
    "scan_type": "equity",
    "universe_size": 250,
    "summary": {
      "exchange": "NSE",
      "instrument_types": ["EQ"]
    }
  }
}
```

### 8. performance_update
Performance metrics updates.

```json
{
  "type": "performance_update",
  "timestamp": "2025-11-18T07:55:41.890123Z",
  "payload": {
    "metrics": {
      "total_pnl": 12500.0,
      "win_rate": 0.68,
      "sharpe_ratio": 1.85
    }
  }
}
```

## Usage Examples

### Python API

```python
from analytics.telemetry_bus import (
    get_telemetry_bus,
    publish_signal_event,
    publish_order_event,
    publish_engine_health,
)

# Get telemetry bus instance
bus = get_telemetry_bus()

# Publish events
publish_signal_event(
    symbol="NIFTY",
    strategy_name="momentum",
    signal="BUY",
    confidence=0.85,
)

publish_order_event(
    order_id="ORDER-001",
    symbol="NIFTY",
    side="BUY",
    status="filled",
    qty=50,
    price=19755.0,
)

# Query events
recent_events = bus.get_recent_events(limit=100)
signal_events = bus.get_recent_events(event_type="signal_event")

# Get statistics
stats = bus.get_stats()
print(f"Total events: {stats['total_events']}")
print(f"Event types: {stats['event_types']}")
```

### REST API

**Get telemetry statistics:**
```bash
curl http://localhost:9000/api/telemetry/stats
```

**Get recent events:**
```bash
curl "http://localhost:9000/api/telemetry/events?limit=50"
```

**Filter by event type:**
```bash
curl "http://localhost:9000/api/telemetry/events?event_type=order_event&limit=20"
```

**Stream events via SSE:**
```bash
curl -N "http://localhost:9000/api/telemetry/stream"
```

**Stream specific event type:**
```bash
curl -N "http://localhost:9000/api/telemetry/stream?event_type=order_event"
```

### JavaScript/Frontend

```javascript
// Connect to SSE stream
const eventSource = new EventSource('/api/telemetry/stream');

eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(`Event: ${data.type}`, data.payload);
  
  // Handle different event types
  switch (data.type) {
    case 'signal_event':
      handleSignal(data.payload);
      break;
    case 'order_event':
      handleOrder(data.payload);
      break;
    case 'engine_health':
      updateHealthMetrics(data.payload);
      break;
  }
};

eventSource.onerror = (error) => {
  console.error('SSE error:', error);
};

// Filter by event type
const orderStream = new EventSource('/api/telemetry/stream?event_type=order_event');
orderStream.onmessage = (event) => {
  const order = JSON.parse(event.data);
  updateOrderBook(order.payload);
};
```

## Engine-Specific Features

### MarketDataEngine
- **Status Updates**: Published every 3 seconds via background thread
- **Metrics**: cached_symbols, total_candles, lookup_failures, stale_symbols_count
- **Lookup Failures**: Published once per failed symbol lookup
- **Stale Symbols**: Published when symbols haven't updated in > 60 minutes

### StrategyEngineV2
- **Health Metrics**: Published every 5 seconds via background thread
- **Per-Strategy Stats**: win_rate, loss_streak, win_streak, open_positions
- **Indicator Events**: Published on every indicator computation
- **Signal Events**: Published on BUY/SELL/EXIT signals
- **Decision Traces**: Detailed traces of strategy decisions

### ExecutionEngine
- **Order Creation**: Published when orders are placed
- **Order Fills**: Published with fill price and quantity
- **Order Rejections**: Published with rejection reason
- **Full Lifecycle**: All order state transitions tracked

### UniverseBuilder
- **Scan Results**: Published on universe refresh
- **Exchange Breakdown**: Separate events for NSE/NFO
- **Instrument Counts**: Total count and breakdown by type

## Performance Considerations

### Buffer Management
- Default buffer size: 5000 events
- Events are stored in-memory using `collections.deque`
- Oldest events are automatically evicted when buffer is full
- Consider increasing buffer size for high-frequency trading

### Background Threads
- MarketDataEngine: 1 thread, publishes every 3 seconds
- StrategyEngineV2: 1 thread, publishes every 5 seconds
- Minimal CPU overhead: < 1% on typical hardware
- Graceful shutdown via `stop_telemetry()` methods

### Network Considerations
- SSE streams maintain persistent connections
- Heartbeat messages sent to keep connections alive
- Client reconnection handled automatically
- Consider rate limiting for production deployments

## Testing

Run the comprehensive test suite:

```bash
# Unit tests
PYTHONPATH=. python3 tests/test_telemetry_bus.py

# Integration tests
PYTHONPATH=. python3 tests/test_telemetry_integration.py
```

## Monitoring & Debugging

### View Live Events
```bash
# Watch all events
curl -N http://localhost:9000/api/telemetry/stream

# Watch only order events
curl -N "http://localhost:9000/api/telemetry/stream?event_type=order_event"

# Pretty print with jq
curl -N http://localhost:9000/api/telemetry/stream | \
  while read line; do
    echo "$line" | sed 's/^data: //' | jq '.'
  done
```

### Debug Event Counts
```python
from analytics.telemetry_bus import get_telemetry_bus

bus = get_telemetry_bus()
stats = bus.get_stats()

print("Event breakdown:")
for event_type, count in sorted(stats['event_counts'].items()):
    print(f"  {event_type}: {count}")
```

### Clear Buffer
```python
from analytics.telemetry_bus import get_telemetry_bus

bus = get_telemetry_bus()
bus.clear_buffer()  # Clear all events
```

## Future Enhancements

Potential improvements for the telemetry layer:

1. **Persistence**: Store events to database for historical analysis
2. **Filtering**: More sophisticated event filtering (by strategy, symbol, etc.)
3. **Aggregation**: Pre-computed aggregates and statistics
4. **Alerting**: Webhook notifications for critical events
5. **WebSocket**: Alternative to SSE for bidirectional communication
6. **Compression**: Event compression for reduced bandwidth
7. **Authentication**: API key or JWT authentication for telemetry endpoints

## Support

For issues or questions:
- Check test files for usage examples
- Review engine source code for integration details
- Examine server.py for API endpoint implementations
