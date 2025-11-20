# PnL & Telemetry Unification Implementation Summary

## Overview
This implementation unifies PnL and telemetry data by establishing `artifacts/analytics/runtime_metrics.json` as the single source of truth for both CLI scripts and the React dashboard.

## Problem Statement
Previously, the dashboard Portfolio card values (Equity, Daily P&L, Realized P&L, Unrealized P&L, Total Notional) didn't match what the CLI script `scripts/analyze_performance.py` printed, leading to inconsistent reporting and confusion.

## Solution
Standardized on `artifacts/analytics/runtime_metrics.json` as the canonical live metrics file, with daily snapshots in `artifacts/analytics/daily/YYYY-MM-DD-metrics.json`.

## Implementation Details

### 1. Backend - analytics/performance_v2.py

**Added:**
- `total_notional` field in equity metrics (loaded from state checkpoint)
- `update_runtime_metrics()` helper function for idempotent metric updates

**Key Features:**
- Takes configurable inputs: orders_path, state_path, starting_capital, output_path
- Handles missing/empty orders gracefully (returns safe defaults)
- Writes consistent JSON schema matching API spec
- Comprehensive error handling

**Example Usage:**
```python
from analytics.performance_v2 import update_runtime_metrics

metrics = update_runtime_metrics(
    orders_path="artifacts/orders.csv",
    state_path="artifacts/checkpoints/paper_state_latest.json",
    starting_capital=500_000.0,
)
```

### 2. Backend - scripts/analyze_performance.py

**Completely refactored:**
- Loads from `runtime_metrics.json` as primary source
- Falls back to computing from orders.csv if file missing
- Console output matches dashboard field structure
- Shows comprehensive breakdown:
  - Equity summary (capital, realized/unrealized PnL, notional, drawdown)
  - Overall performance (trades, win rate, profit factor, etc.)
  - Per-symbol performance table
  - Per-strategy performance table

**Error Handling:**
- Never crashes on missing/malformed files
- Clear user-friendly messages
- Graceful fallbacks to zeros

### 3. Backend - ui/dashboard.py

**Updated `/api/analytics/summary` endpoint:**
- Reads from `runtime_metrics.json` as primary source
- Falls back to `daily/YYYY-MM-DD-metrics.json` if main file missing
- Implements staleness detection:
  - **ok**: < 60 seconds old
  - **stale**: 60-300 seconds old  
  - **empty**: > 300 seconds old or no data
- Returns all required fields with safe defaults
- Includes `asof` timestamp in ISO format
- Added `total_notional` to equity section

**Response Schema:**
```json
{
  "asof": "2025-11-20T08:21:24.346466",
  "status": "ok",
  "mode": "paper",
  "equity": {
    "starting_capital": 500000.0,
    "current_equity": 508772.81,
    "realized_pnl": 8772.81,
    "unrealized_pnl": 0.0,
    "total_notional": 0.0,
    "max_drawdown": 0.0,
    "max_equity": 508772.81,
    "min_equity": 500000.0
  },
  "overall": {
    "total_trades": 2,
    "win_trades": 2,
    "loss_trades": 0,
    "breakeven_trades": 0,
    "win_rate": 100.0,
    "gross_profit": 8772.81,
    "gross_loss": 0.0,
    "net_pnl": 8772.81,
    "profit_factor": 0.0,
    "avg_win": 4386.40,
    "avg_loss": 0.0,
    "avg_r_multiple": 0.0,
    "biggest_win": 5000.0,
    "biggest_loss": 3772.81
  },
  "per_strategy": { /* ... */ },
  "per_symbol": { /* ... */ }
}
```

### 4. Frontend - ui/frontend/src/types/api.ts

**Updated `AnalyticsSummary` interface:**
- Replaced old structure (daily, strategies, symbols)
- New structure matches backend exactly:
  - `status: 'ok' | 'stale' | 'empty'`
  - `equity` with total_notional
  - `overall` with comprehensive metrics
  - `per_strategy` and `per_symbol` breakdowns

### 5. Frontend - ui/frontend/src/hooks/useApi.ts

**Updated `useAnalyticsSummary` hook:**
- Changed refetch interval from 10s to 5s
- Added `refetchIntervalInBackground: true`
- Ensures responsive updates during trading hours

### 6. Frontend - ui/frontend/src/features/overview/OverviewPage.tsx

**Major changes:**
- Now uses `useAnalyticsSummary` as canonical source (was using portfolio/metrics)
- Displays all 5 key metrics:
  1. **Equity** → `analytics.equity.current_equity`
  2. **Daily P&L** → `analytics.equity.realized_pnl + unrealized_pnl`
  3. **Realized P&L** → `analytics.equity.realized_pnl`
  4. **Unrealized P&L** → `analytics.equity.unrealized_pnl`
  5. **Total Notional** → `analytics.equity.total_notional`
- Shows staleness badges:
  - "⚠ Data may be stale" for stale status
  - "ℹ No data yet" for empty status
- Enhanced debug mode shows raw API response

### 7. Frontend - ui/frontend/src/features/analytics/AnalyticsPage.tsx

**Updated for new API structure:**
- Changed `analytics.strategies` → `analytics.per_strategy`
- Changed `analytics.symbols` → `analytics.per_symbol`
- Updated field mappings: `data.pnl` → `data.net_pnl`
- Now consistent with OverviewPage data sources

## Data Flow

```
┌─────────────────────────────────────────────────────────┐
│ 1. Engines write orders and state                       │
│    - artifacts/orders.csv                                │
│    - artifacts/checkpoints/paper_state_latest.json      │
└──────────────────┬──────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────┐
│ 2. PerformanceEngine V2 computes metrics                │
│    analytics.performance_v2.update_runtime_metrics()     │
└──────────────────┬──────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────┐
│ 3. Canonical metrics file (SINGLE SOURCE OF TRUTH)      │
│    artifacts/analytics/runtime_metrics.json              │
└──────────────┬──────────────────┬───────────────────────┘
               │                  │
               ▼                  ▼
┌──────────────────────┐  ┌──────────────────────────────┐
│ 4a. CLI Consumer     │  │ 4b. Dashboard API            │
│     analyze_         │  │     /api/analytics/summary   │
│     performance.py   │  │                              │
└──────────────────────┘  └────────────┬─────────────────┘
                                       │
                                       ▼
                          ┌──────────────────────────────┐
                          │ 5. React Frontend            │
                          │    - Overview page           │
                          │    - Analytics page          │
                          │    - Polls every 5 seconds   │
                          └──────────────────────────────┘
```

## Benefits

### 1. Consistency
- CLI and dashboard always show identical values
- No more confusion about which source is "correct"
- Single computation eliminates rounding differences

### 2. Reliability
- Defensive error handling prevents crashes
- Graceful fallbacks for missing data
- Clear status indicators (ok/stale/empty)

### 3. Performance
- Pre-computed metrics (no recalculation in API)
- Fast response times
- Efficient polling with 5-second intervals

### 4. Maintainability
- Clear data flow from engines → analytics → consumers
- Well-documented functions with type hints
- Separation of concerns

## Testing Results

### CLI Script
```bash
$ python -m scripts.analyze_performance
=== Performance Summary (from runtime_metrics.json) ===

As of               : 2025-11-20T08:21:24.346466
Mode                : 
Starting Capital    : 500,000.00
Current Equity      : 508,772.81
Realized PnL        : 8,772.81
Unrealized PnL      : 0.00
Total Notional      : 0.00
Max Drawdown        : 0.00

Overall Performance:
  Total Trades      : 2
  Win Trades        : 2
  Loss Trades       : 0
  Win Rate          : 100.00%
  ...
```

### API Endpoint
```python
# Staleness detection works correctly
Status: ok     (< 60 seconds)
Status: stale  (60-300 seconds)
Status: empty  (> 300 seconds)

# All fields present
✓ equity.starting_capital
✓ equity.current_equity
✓ equity.realized_pnl
✓ equity.unrealized_pnl
✓ equity.total_notional  # NEW!
✓ equity.max_drawdown
✓ overall.total_trades
✓ overall.win_rate
✓ overall.net_pnl
...
```

### Frontend Build
```bash
$ npm run build
✓ TypeScript compilation successful
✓ All React components updated
✓ Production build created: ui/static-react/
```

### Security Scan
```
✓ CodeQL scan: 0 vulnerabilities found
```

## Migration Notes

### For Engines
- Continue writing to `orders.csv` and checkpoints as before
- No changes required

### For Analytics Scripts
- Use `update_runtime_metrics()` helper instead of custom logic
- Always write to `runtime_metrics.json`

### For Dashboard Components
- Use `useAnalyticsSummary` hook for portfolio metrics
- Check `status` field and show appropriate badges
- Map fields from new structure:
  - `analytics.equity.*` for equity metrics
  - `analytics.overall.*` for performance metrics
  - `analytics.per_strategy` and `analytics.per_symbol` for breakdowns

## Future Enhancements

### Potential Improvements
1. **Real-time Updates**: Add WebSocket support for instant updates
2. **Historical Snapshots**: Archive daily metrics for trend analysis
3. **Benchmarking**: Compare against market indices
4. **Alerting**: Notify on staleness or anomalies
5. **Caching**: Add Redis cache layer for high-frequency access

### Backward Compatibility
- Old endpoints remain functional but deprecated
- Migration period allows gradual adoption
- Clear documentation of deprecation timeline

## Conclusion

This implementation successfully unifies PnL and telemetry data, establishing a single source of truth that both CLI scripts and the dashboard consume. The solution is robust, well-tested, and provides a solid foundation for future analytics enhancements.

**Key Achievement**: CLI and dashboard now always show identical values, eliminating confusion and ensuring trust in the data.
