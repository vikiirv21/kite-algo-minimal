# Unified Analytics System Implementation

## Overview
This implementation adds a comprehensive runtime analytics system to kite-algo-minimal that tracks live equity, PnL, per-symbol PnL, per-strategy PnL, and equity curve, exposing them via API endpoints to the dashboard.

## Implementation Summary

### 1. New Analytics Modules

#### `analytics/runtime_metrics.py`
- **RuntimeMetricsTracker**: Thread-safe class for tracking live performance metrics
  - Tracks current equity, realized PnL, unrealized PnL, daily PnL
  - Maintains per-symbol and per-strategy PnL breakdowns
  - Rolling equity curve with configurable window (default: 500 snapshots)
  - Automatic persistence to `artifacts/analytics/runtime_metrics.json`
  - Thread-safe with `threading.RLock()`
  
- **load_runtime_metrics()**: Safe loader function that never crashes
  - Returns sensible defaults if file doesn't exist or is invalid
  - Fills in missing fields automatically

#### `analytics/equity_curve.py`
- **EquityCurveWriter**: Thread-safe CSV writer for equity snapshots
  - Appends to `artifacts/snapshots.csv`
  - Rate-limited to every 5 seconds (configurable)
  - Includes timestamp, equity, realized_pnl, unrealized_pnl
  - Automatic CSV header creation
  
- **load_equity_curve()**: Safe loader function that never crashes
  - Returns empty list if file doesn't exist or is invalid
  - Supports max_rows parameter for pagination

### 2. Engine Integration

#### `engine/paper_engine.py`
**Initialization (`__init__`):**
- Creates RuntimeMetricsTracker with starting capital from config
- Creates EquityCurveWriter with 5-second interval
- Gracefully continues if initialization fails

**After Fills (`_close_position` and order placement):**
- Calls `metrics_tracker.update_after_fill()` with:
  - Symbol, strategy, realized PnL, fill price, quantity, side
- Saves metrics to JSON after each fill

**On Every Tick (`_loop_once`):**
- Calculates total unrealized PnL from all positions
- Updates metrics with `update_unrealized_pnl()`
- Pushes equity snapshot (rate-limited to 5 seconds)
- Writes to CSV equity curve (rate-limited to 5 seconds)

#### `engine/live_engine.py`
**Initialization (`__init__`):**
- Creates RuntimeMetricsTracker with live capital from config
- Creates EquityCurveWriter with 5-second interval
- Gracefully continues if initialization fails

**After Fills (`handle_order_update`):**
- When order status is COMPLETE, updates metrics with fill data
- Saves metrics to JSON after each fill

**In Event Loop (`_run_event_loop`):**
- Gets current positions from broker
- Calculates total unrealized PnL
- Updates metrics with `update_unrealized_pnl()`
- Pushes equity snapshot (rate-limited to 5 seconds)
- Writes to CSV equity curve (rate-limited to 5 seconds)

### 3. API Endpoints

#### `GET /api/analytics/summary`
Returns comprehensive analytics summary:
```json
{
  "asof": "2025-11-20T18:30:00Z",
  "mode": "paper",
  "starting_capital": 500000.0,
  "current_equity": 502500.0,
  "realized_pnl": 2000.0,
  "unrealized_pnl": 500.0,
  "daily_pnl": 2500.0,
  "max_equity": 503000.0,
  "min_equity": 499000.0,
  "max_drawdown": 0.012,
  "pnl_per_symbol": {
    "NIFTY24DECFUT": 1200.0,
    "BANKNIFTY24DECFUT": 800.0
  },
  "pnl_per_strategy": {
    "EMA_20_50": 1500.0,
    "FNO_TREND": 500.0
  },
  "equity_curve": [
    {
      "timestamp": "2025-11-20T18:29:00Z",
      "equity": 500000.0,
      "realized_pnl": 0.0,
      "unrealized_pnl": 0.0
    }
  ]
}
```

**Features:**
- Uses safe loader that never crashes
- Returns sensible defaults if data unavailable
- Includes error field if loading fails

#### `GET /api/analytics/equity_curve?max_rows=500`
Returns historical equity curve:
```json
{
  "data": [
    {
      "timestamp": "2025-11-20T18:29:00Z",
      "equity": "500000.00",
      "realized_pnl": "0.00",
      "unrealized_pnl": "0.00"
    }
  ],
  "count": 1
}
```

**Features:**
- Uses safe loader that never crashes
- Supports max_rows parameter (default: 500, max: 10000)
- Returns empty list if data unavailable
- Includes error field if loading fails

### 4. Testing

#### `test_analytics.py`
Comprehensive test script covering:
- RuntimeMetricsTracker initialization and updates
- EquityCurveWriter CSV operations
- Safe loaders with missing/invalid data
- API data structure compatibility

**All tests pass successfully!**

## File Structure

```
kite-algo-minimal/
├── analytics/
│   ├── runtime_metrics.py     # NEW: Runtime metrics tracking
│   ├── equity_curve.py         # NEW: Equity curve CSV writer
│   └── ...
├── apps/
│   └── dashboard.py            # MODIFIED: Added API endpoints
├── engine/
│   ├── paper_engine.py         # MODIFIED: Integrated metrics
│   ├── live_engine.py          # MODIFIED: Integrated metrics
│   └── ...
├── artifacts/                  # Created at runtime
│   ├── analytics/
│   │   └── runtime_metrics.json
│   └── snapshots.csv
└── test_analytics.py           # NEW: Test script
```

## Usage

### For Engine Developers
No changes needed - metrics tracking is automatic when engines run.

### For Dashboard Developers
Use the new API endpoints:
```javascript
// Fetch analytics summary
fetch('/api/analytics/summary')
  .then(res => res.json())
  .then(data => {
    console.log('Current equity:', data.current_equity);
    console.log('PnL per symbol:', data.pnl_per_symbol);
  });

// Fetch equity curve
fetch('/api/analytics/equity_curve?max_rows=1000')
  .then(res => res.json())
  .then(data => {
    console.log('Equity curve:', data.data);
  });
```

### For Backtest/Analysis
Read the persisted data:
```python
from analytics.runtime_metrics import load_runtime_metrics
from analytics.equity_curve import load_equity_curve

# Load latest metrics
metrics = load_runtime_metrics()
print(f"Final equity: {metrics['current_equity']}")

# Load equity curve
curve = load_equity_curve(max_rows=1000)
for snapshot in curve:
    print(f"{snapshot['timestamp']}: {snapshot['equity']}")
```

## Design Decisions

### Thread Safety
- Used `threading.RLock()` for all shared state
- Rate limiting prevents excessive writes
- All methods are thread-safe for concurrent access

### Error Handling
- Safe loaders never crash
- Return sensible defaults on errors
- Log errors but don't propagate to engines
- Graceful degradation if analytics fails

### Performance
- Rate-limited snapshots (5 seconds minimum)
- Rolling window limits memory usage
- Async writes to avoid blocking engines
- Debug-level logging for normal operations

### Persistence
- JSON for structured metrics (human-readable)
- CSV for time-series data (easy to analyze)
- Atomic writes to prevent corruption
- Backward compatible field defaults

## Security
- No security vulnerabilities detected by CodeQL
- No SQL injection risks (file-based storage)
- No XSS risks (JSON API responses)
- Thread-safe operations prevent race conditions

## Testing Results

All tests pass:
```
✅ RuntimeMetricsTracker initialization and updates
✅ EquityCurveWriter CSV operations
✅ Safe loaders handle missing data
✅ Safe loaders handle invalid JSON
✅ API data structures match expectations
✅ CodeQL security scan: 0 alerts
```

## Future Enhancements

Possible improvements:
1. Add Sharpe ratio and other risk metrics
2. Add trade-by-trade journal integration
3. Add real-time streaming via WebSocket
4. Add historical comparison (day-over-day)
5. Add alerts for drawdown thresholds
6. Add export to multiple formats (Parquet, HDF5)

## Conclusion

The unified analytics system is fully implemented, tested, and integrated into both paper and live trading engines. It provides comprehensive real-time performance tracking with safe API endpoints that never crash the dashboard.
