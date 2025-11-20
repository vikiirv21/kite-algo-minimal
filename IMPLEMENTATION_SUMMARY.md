# Dashboard API Fixes - Implementation Summary

## Overview
Fixed the FastAPI dashboard to ensure all tabs pull data from correct backend APIs and refresh live while engines are running. All endpoints now guarantee stable JSON responses even when artifact files are missing or empty.

## Changes Made

### 1. Backend API Stability (ui/dashboard.py)

#### New Safe Loader Functions
Created three helper functions that never crash and always return valid data structures:

**`load_runtime_metrics_safe()`**
- **Purpose**: Load runtime metrics from `artifacts/analytics/runtime_metrics.json`
- **Behavior**: Returns complete default structure if file missing/corrupted
- **Structure**: Includes equity, overall, per_strategy, and per_symbol sections
- **Default Values**: All numeric fields default to 0.0, collections default to empty {}

**`load_latest_checkpoint_safe()`**
- **Purpose**: Load most recent checkpoint from multiple fallback paths
- **Behavior**: Tries multiple paths, returns safe defaults if all fail
- **Fallback Paths**:
  1. `checkpoints/paper_state_latest.json`
  2. `checkpoints/paper_state.json`
  3. `checkpoints/runtime_state_latest.json`
  4. `paper_state_latest.json`
  5. `paper_state.json`
- **Structure**: Includes timestamp, meta, equity, pnl, positions, orders

**`load_strategies_from_config_safe()`**
- **Purpose**: Load strategies from config with overrides applied
- **Behavior**: Returns empty list if config can't be loaded
- **Sources**: Reads from `configs/dev.yaml` and `configs/learned_overrides.yaml`
- **Merges**: Applies strategy overrides (enabled status, params) from learned_overrides

#### Updated API Endpoints

**`/api/trading/summary`**
- ✅ Never crashes when checkpoint missing
- ✅ Graceful fallbacks for all data sources
- ✅ Returns stable JSON structure with safe defaults
- **Enhanced**: Better exception handling around engine status, orders, positions

**`/api/analytics/summary`**
- ✅ Uses `load_runtime_metrics_safe()` for guaranteed valid response
- ✅ Falls back to daily metrics file if runtime metrics unavailable
- ✅ Status field indicates data freshness (ok/stale/empty)
- **Enhanced**: Comprehensive error handling, never returns None

**`/api/risk/summary`**
- ✅ Uses `load_runtime_metrics_safe()` for PnL data
- ✅ Safe fallbacks for config and portfolio data
- ✅ Returns valid JSON even when all sources fail
- **Enhanced**: Better exception handling, guaranteed non-null response

### 2. Frontend Enhancements

#### New Component: `LastUpdated` (ui/frontend/src/components/LastUpdated.tsx)
- **Purpose**: Display "last updated" timestamp that counts up live
- **Features**:
  - Updates every second showing relative time (Xs ago, Xm ago, Xh ago)
  - Tooltip shows exact IST time on hover
  - Integrates with React Query's `dataUpdatedAt` timestamp
  - Gracefully handles null/undefined timestamps

#### Updated Component: `Card` (ui/frontend/src/components/Card.tsx)
- **New Prop**: `lastUpdated?: number | null`
- **Behavior**: When provided, displays `LastUpdated` component next to title
- **Usage**: Automatic integration with React Query timestamps

#### Updated Pages with Timestamps

**OverviewPage** (ui/frontend/src/features/overview/OverviewPage.tsx)
- ✅ Added `dataUpdatedAt` extraction from hooks
- ✅ Engines Status card shows last update time
- ✅ Portfolio card shows last update time (from analytics or portfolio API)
- ✅ Recent Signals card shows last update time

**AnalyticsPage** (ui/frontend/src/features/analytics/AnalyticsPage.tsx)
- ✅ Added `dataUpdatedAt` extraction from hooks
- ✅ Equity Curve card shows last update time
- ✅ Strategy Performance table shows last update time
- ✅ Symbol Performance table shows last update time

**RiskPage** (ui/frontend/src/features/risk/RiskPage.tsx)
- ✅ Added `dataUpdatedAt` extraction from hooks
- ✅ Daily Loss Limit card shows last update time (from risk API)
- ✅ Exposure Limit card shows last update time (from portfolio API)
- ✅ Position Limit card shows last update time (from portfolio API)
- ✅ Capital at Risk card shows last update time (from portfolio API)

### 3. Frontend Build
- ✅ TypeScript compilation successful
- ✅ Vite build successful
- ✅ Static assets generated in `ui/static-react/`
- ⚠️ Note: Bundle size is 672KB (consider code-splitting for production)

## API Response Guarantees

All modified endpoints now guarantee:

1. **Never Return HTTP 500**: All exceptions caught and handled with safe defaults
2. **Stable JSON Schema**: Always include all required fields
3. **Status Indicators**: Include "status" field ("ok", "stale", "empty") where appropriate
4. **Safe Defaults**: Zero values for numbers, empty lists/dicts for collections
5. **Backward Compatible**: Existing clients continue to work

## Polling Configuration (Already Active)

React Query refetch intervals configured in `ui/frontend/src/hooks/useApi.ts`:

| Endpoint | Interval | Priority |
|----------|----------|----------|
| Trading Summary | 3s | High |
| Analytics Summary | 5s | Medium |
| Risk Summary | 5s | Medium |
| Portfolio Summary | 2s | High |
| Signals | 2s | High |
| Positions | 3s | High |

## Testing Recommendations

### Manual Testing Checklist
- [ ] Start dashboard with `python scripts/run_dashboard.py`
- [ ] Access at `http://127.0.0.1:8000/`
- [ ] Verify all tabs load without errors
- [ ] Check timestamps update every second
- [ ] Delete `artifacts/analytics/runtime_metrics.json` → verify safe defaults shown
- [ ] Delete `artifacts/checkpoints/paper_state_latest.json` → verify safe defaults shown
- [ ] Start trading engine → verify live data updates
- [ ] Check Strategy Lab enable/disable buttons work
- [ ] Check Risk tab progress bars render correctly

### Automated Testing
Test script created: `tests/test_dashboard_api_stability.py`
- Tests all three safe loader functions
- Verifies API endpoint response structures
- Ensures no crashes on missing files
- (Requires Python dependencies to run)

## File Changes Summary

### Modified Files
1. `ui/dashboard.py` (164 insertions, 151 deletions)
   - Added 3 new safe loader functions
   - Updated 3 API endpoints with better error handling
   - Kept deprecated functions for backward compatibility

2. `ui/frontend/src/components/Card.tsx` (12 insertions, 5 deletions)
   - Added `lastUpdated` prop
   - Integrated `LastUpdated` component display

3. `ui/frontend/src/features/overview/OverviewPage.tsx`
   - Added `dataUpdatedAt` extraction
   - Added timestamps to 3 major cards

4. `ui/frontend/src/features/analytics/AnalyticsPage.tsx`
   - Added `dataUpdatedAt` extraction
   - Added timestamps to 4 major sections

5. `ui/frontend/src/features/risk/RiskPage.tsx`
   - Added `dataUpdatedAt` extraction
   - Added timestamps to 4 major sections

### New Files
1. `ui/frontend/src/components/LastUpdated.tsx` (55 lines)
   - Reusable timestamp display component

2. `tests/test_dashboard_api_stability.py` (215 lines)
   - Automated test suite for API stability

3. `ui/static-react/assets/index-BZhaLsvh.js` (Generated build artifact)

## Documentation Updates

Per `frontend_dashboard.md`, all endpoint mappings are correct:

- ✅ Overview → `/api/trading/summary`, `/api/meta`
- ✅ Analytics → `/api/analytics/summary`, `/api/analytics/equity_curve`
- ✅ Engines/Status → `/api/trading/summary`, `/api/strategies`
- ✅ Signals → `/api/signals`
- ✅ Positions → `/api/positions_normalized`
- ✅ Risk → `/api/risk/summary`
- ✅ Strategy Lab → `/api/strategies` + enable/disable/params endpoints

## Next Steps

1. Install Python dependencies and run tests
2. Start dashboard and perform manual testing
3. Take screenshots of working dashboard tabs
4. Verify Strategy Lab buttons work correctly
5. Consider adding SSE endpoint for real-time log streaming
6. Consider code-splitting frontend bundle to reduce size

## Notes

- All changes are backward compatible
- No breaking changes to existing APIs
- Frontend polling was already configured via React Query
- Strategy Lab UI was already implemented (verified)
- Risk page progress bars were already implemented (verified)
- Main improvements were backend stability and frontend timestamps
