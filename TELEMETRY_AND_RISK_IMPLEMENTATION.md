# Telemetry and Risk Service Implementation Summary

## Overview
This implementation adds comprehensive telemetry tracking, SSE streaming, benchmark tracking, and risk management features to the kite-algo-minimal trading system.

## New Modules

### 1. Telemetry Bus (`analytics/telemetry_bus.py`)

A centralized event publishing and streaming system for real-time strategy and market telemetry.

**Features:**
- Ring buffer (maxlen=1000) for event storage
- Thread-safe event publishing
- Subscriber pattern for event consumption
- SSE streaming support

**Key Methods:**
```python
from analytics.telemetry_bus import get_telemetry_bus, publish_signal_event

# Get singleton instance
bus = get_telemetry_bus()

# Publish events
bus.publish("signal_event", {"symbol": "NIFTY", "signal": "BUY"})

# Subscribe to events
def callback(event):
    print(f"Event: {event}")
bus.subscribe(callback)

# Get snapshot of recent events
events = bus.snapshot(since_ts="2024-11-18T10:00:00+00:00")
```

**Helper Functions:**
- `publish_signal_event()` - Strategy signals
- `publish_order_event()` - Order lifecycle events
- `publish_position_event()` - Position updates
- `publish_engine_health()` - Engine health status
- `publish_decision_trace()` - Strategy decision traces
- `publish_performance_update()` - Performance metrics
- `publish_mde_status()` - Market data engine status
- `publish_universe_summary()` - Universe summary events

### 2. Benchmarks Module (`analytics/benchmarks.py`)

Tracks and retrieves benchmark index prices over time.

**Usage:**
```python
from analytics.benchmarks import get_benchmarks

# Get benchmarks for last 7 days
benchmarks = get_benchmarks(days=7)
# Returns: [{"ts": "...", "nifty": 19500.25, "banknifty": 45234.80, ...}, ...]
```

**Data Format:**
Store benchmark data in `artifacts/benchmarks/*.json`:
```json
[
  {
    "ts": "2024-11-18T09:15:00+05:30",
    "nifty": 19500.25,
    "banknifty": 45234.80,
    "finnifty": 20456.50
  }
]
```

### 3. Risk Service (`analytics/risk_service.py`)

Manages risk limits, detects breaches, and computes Value at Risk (VaR).

**Risk Limits Configuration:**
```python
from analytics.risk_service import load_risk_limits, save_risk_limits

# Load current limits
limits = load_risk_limits()
# Returns: RiskLimits(max_daily_loss_rupees=5000.0, ...)

# Update limits
save_risk_limits({
    "max_daily_loss_rupees": 3000.0,
    "max_trades_per_day": 15
})
```

**Breach Detection:**
```python
from analytics.risk_service import compute_breaches

# Check for active breaches
breaches = compute_breaches()
# Returns: [{"type": "max_daily_loss", "limit": 5000.0, "current": 5500.0, ...}, ...]
```

**VaR Computation:**
```python
from analytics.risk_service import compute_var

# Compute 30-day VaR at 95% confidence
var_result = compute_var(days=30, confidence=0.95)
# Returns: {"var": 2500.0, "observations": 25, ...}
```

## New API Endpoints

### Telemetry Streaming

**GET /api/telemetry/stream**
- Server-Sent Events (SSE) endpoint for real-time telemetry
- Query params:
  - `event_type` (optional): Filter by event type
- Returns: SSE stream with `data: {...}\n\n` format
- Example:
  ```bash
  curl -N http://localhost:8765/api/telemetry/stream
  # or filter by type:
  curl -N http://localhost:8765/api/telemetry/stream?event_type=signal_event
  ```

### Benchmarks

**GET /api/benchmarks**
- Query params:
  - `days` (default: 1, range: 1-365): Number of days to look back
- Returns: Array of benchmark datapoints
- Example:
  ```bash
  curl http://localhost:8765/api/benchmarks?days=7
  ```

### Risk Management

**GET /api/risk/limits**
- Returns current risk limits configuration
- Example:
  ```bash
  curl http://localhost:8765/api/risk/limits
  ```

**POST /api/risk/limits**
- Updates risk limit overrides
- Request body: JSON with limit fields to update
- Example:
  ```bash
  curl -X POST http://localhost:8765/api/risk/limits \
    -H "Content-Type: application/json" \
    -d '{"max_daily_loss_rupees": 3000.0}'
  ```

**GET /api/risk/breaches**
- Returns list of active risk limit breaches
- Example:
  ```bash
  curl http://localhost:8765/api/risk/breaches
  ```

**GET /api/risk/var**
- Computes Value at Risk from historical data
- Query params:
  - `days` (default: 30, range: 1-365): Lookback window
  - `confidence` (default: 0.95, range: 0.5-0.99): Confidence level
- Example:
  ```bash
  curl "http://localhost:8765/api/risk/var?days=30&confidence=0.95"
  ```

## Engine Telemetry Integration

All engines now publish telemetry events at key points:

### 1. Engine Lifecycle
```python
# On startup
publish_engine_health("paper_engine", "starting", {"mode": "paper", ...})

# On shutdown
publish_engine_health("paper_engine", "stopped", {"mode": "paper"})

# On error
publish_engine_health("paper_engine", "error", {"mode": "paper", "error": "..."})
```

### 2. Strategy Decisions
```python
# Decision trace
publish_decision_trace(
    strategy_name="ema20_50_intraday",
    symbol="NIFTY24DECFUT",
    decision="BUY",
    trace_data={...}
)

# Signal event
publish_signal_event(
    symbol="NIFTY24DECFUT",
    strategy_name="ema20_50_intraday",
    signal="BUY",
    ...
)
```

### 3. Order Lifecycle
```python
# After order execution
publish_order_event(
    order_id="paper-123456",
    symbol="NIFTY24DECFUT",
    side="BUY",
    status="FILLED",
    ...
)
```

### 4. Position Snapshots
```python
# Periodically (every N loops or after order fills)
publish_position_event(
    symbol="portfolio",
    position_size=5,
    positions=[...],
    equity=502500.0,
    ...
)
```

## Configuration

### Risk Limits Configuration

Risk limits are configured in two files:

1. **Base configuration** (`configs/dev.yaml`):
   ```yaml
   risk:
     max_daily_loss_abs: 5000.0
     max_daily_drawdown_pct: 5.0
     max_trades_per_day: 20
     max_trades_per_symbol_per_day: 5
     max_loss_streak: 3
   ```

2. **Runtime overrides** (`configs/risk_overrides.yaml`):
   ```yaml
   max_daily_loss_rupees: 3000.0
   max_trades_per_day: 15
   ```

Overrides take precedence over base configuration.

## Directory Structure

```
artifacts/
├── benchmarks/          # Benchmark JSON files
│   └── *.json
├── analytics/
│   ├── runtime_metrics.json   # Current session metrics
│   └── daily/                 # Daily metrics for VaR
│       └── YYYY-MM-DD-metrics.json
└── ...

configs/
├── dev.yaml             # Base risk configuration
└── risk_overrides.yaml  # Runtime risk overrides
```

## Usage Examples

### Python Client for SSE Stream

```python
import requests
import json

url = "http://localhost:8765/api/telemetry/stream"
response = requests.get(url, stream=True)

for line in response.iter_lines():
    if line:
        line_str = line.decode('utf-8')
        if line_str.startswith('data: '):
            event_json = line_str[6:]  # Remove 'data: ' prefix
            event = json.loads(event_json)
            print(f"Event: {event['type']} at {event['timestamp']}")
```

### JavaScript Client for SSE Stream

```javascript
const evtSource = new EventSource('/api/telemetry/stream');

evtSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Event:', data.type, 'at', data.timestamp);
};

evtSource.onerror = (err) => {
  console.error('SSE error:', err);
};
```

## Testing

Sample data files are provided in `artifacts/`:

- `artifacts/benchmarks/sample.json` - Sample benchmark data
- `artifacts/analytics/runtime_metrics.json` - Sample runtime metrics

To test the endpoints:

```bash
# Start the dashboard
python -m uvicorn ui.dashboard:app --host 0.0.0.0 --port 8765

# Test telemetry stream
curl -N http://localhost:8765/api/telemetry/stream

# Test benchmarks
curl http://localhost:8765/api/benchmarks?days=1

# Test risk limits
curl http://localhost:8765/api/risk/limits

# Test risk breaches
curl http://localhost:8765/api/risk/breaches

# Test VaR
curl "http://localhost:8765/api/risk/var?days=30&confidence=0.95"
```

## Notes

- All changes are non-breaking and maintain backward compatibility
- Telemetry calls are lightweight and won't impact performance
- SSE stream automatically handles client disconnections
- Risk overrides persist across restarts
- VaR computation requires historical daily metrics files
