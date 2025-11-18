# Dashboard API Audit Results

**Date**: 2025-11-18  
**Status**: ✅ COMPLETE - All mappings verified and working

## Executive Summary

The audit of the React dashboard and FastAPI backend revealed that **all API mappings are correct and functioning properly**. The issue of portfolio/P&L/positions/orders not updating is NOT due to incorrect API mappings or missing hooks.

## Key Findings

### ✅ Backend Status
- All required API endpoints are implemented and responding correctly
- Portfolio summary endpoint: `/api/portfolio/summary` ✅
- Open positions endpoint: `/api/positions/open` ✅
- Orders endpoints: `/api/orders` and `/api/orders/recent` ✅
- Summary endpoint: `/api/summary/today` ✅
- All other dashboard endpoints functioning ✅

### ✅ Frontend Status
- All React Query hooks are correctly mapped to backend endpoints
- All hooks have appropriate `refetchInterval` configured for live updates
- All pages are using the correct hooks to fetch data
- TypeScript types match backend response shapes
- No hardcoded or mock data found in dashboard pages

### ✅ Polling Configuration
All critical hooks have polling enabled:
- `usePortfolioSummary()`: 2000ms (2 seconds)
- `useOpenPositions()`: 3000ms (3 seconds)
- `useRecentOrders()`: 3000ms (3 seconds)
- `useTodaySummary()`: 3000ms (3 seconds)
- `useEnginesStatus()`: 3000ms (3 seconds)
- `useMeta()`: 2000ms (2 seconds)

### ✅ Manual Testing Results

**Test Environment:**
- Backend server running on http://127.0.0.1:8765
- React frontend built and served from `/ui/static-react`
- Checkpoint file present at `artifacts/checkpoints/runtime_state_latest.json`

**API Tests:**
```bash
# Portfolio Summary
curl http://127.0.0.1:8765/api/portfolio/summary
# Response: {"paper_capital": 0.0, "equity": 0.0, "position_count": 1, ...}

# Open Positions  
curl http://127.0.0.1:8765/api/positions/open
# Response: [{"symbol": "BANKNIFTY25NOV59000CE", "quantity": 60, "avg_price": 429.70, ...}]

# Orders
curl http://127.0.0.1:8765/api/orders/recent
# Response: {"orders": []}

# Engine Status
curl http://127.0.0.1:8765/api/engines/status
# Response: {"engines": [{"running": false, "checkpoint_age_seconds": 81571.51, ...}]}
```

**Browser Tests:**
- ✅ Overview page loads and displays all metrics
- ✅ Portfolio page shows open position (BANKNIFTY25NOV59000CE - 60 qty)
- ✅ Trading page shows "No active orders" (correct)
- ✅ Network tab shows API calls being made repeatedly
- ✅ All endpoints returning 200 OK status

**Network Activity Observed:**
```
/api/meta - polled every 2 seconds ✅
/api/engines/status - polled every 3 seconds ✅
/api/portfolio/summary - polled every 2 seconds ✅
/api/positions/open - polled every 3 seconds ✅
/api/orders/recent - polled every 3 seconds ✅
```

## Why Data Shows Zeros

The audit revealed that the APIs are returning valid data, but most values are **zero because**:

1. **Engine Not Running**: `checkpoint_age_seconds: 81571.51` (~22.6 hours old)
   - Last checkpoint: 2025-11-17T10:02:15
   - Current time: 2025-11-18T14:13:25
   - The paper engine hasn't been running to generate new P&L

2. **No Recent Trading Activity**: 
   - `num_trades: 0` in today's summary
   - No orders in recent orders list
   - Position exists but with `unrealized_pnl: 0.0` (likely using stale prices)

3. **Zero Capital Initialization**:
   - `paper_capital: 0.0` in checkpoint
   - This needs to be set in the engine configuration

## Recommendations

### For Users Seeing "Zero" Data:

1. **Start the Engine**: 
   ```bash
   python scripts/run_paper_engine.py
   ```
   The engine needs to be running to:
   - Update checkpoint files regularly
   - Calculate unrealized P&L with current prices
   - Generate new signals and orders

2. **Check Configuration**:
   ```yaml
   # In configs/dev.yaml or your config file
   trading:
     paper_capital: 500000  # Set your starting capital
     mode: paper
   ```

3. **Verify Engine is Running**:
   - Check `artifacts/checkpoints/runtime_state_latest.json` timestamp
   - Should be updated within last few minutes
   - Engine status should show `"running": true`

4. **Enable Live Market Data** (if needed):
   - Ensure Kite API credentials are configured
   - For paper trading, engine can use cached/simulated prices
   - For zero unrealized P&L, engine needs current LTP (last traded price)

### For Developers:

1. **Debug Mode**: The debug blocks added to pages will show in development mode:
   ```bash
   cd ui/frontend
   npm run dev  # Start Vite dev server
   ```
   This will show raw API responses on Overview, Portfolio, and Trading pages.

2. **Check Logs**:
   ```bash
   tail -f artifacts/logs/app.log
   ```

3. **Manually Update Checkpoint** (for testing):
   Edit `artifacts/checkpoints/runtime_state_latest.json` to set:
   ```json
   {
     "equity": {"paper_capital": 500000, "realized_pnl": 1500, ...},
     "pnl": {"day_pnl": 1500, ...}
   }
   ```

## Conclusion

✅ **API Mapping Audit: PASSED**

All frontend-backend mappings are correct. The dashboard will update properly once:
1. The paper engine is running
2. Trading activity generates non-zero P&L
3. Current market prices are available for positions

The architecture is sound - this is a data availability issue, not a mapping issue.

## Files Modified

1. `docs/api_dashboard_mapping.md` - Complete API endpoint mapping documentation
2. `ui/frontend/src/hooks/useApi.ts` - Added endpoint mapping comments
3. `ui/frontend/src/features/overview/OverviewPage.tsx` - Added debug blocks
4. `ui/frontend/src/features/portfolio/PortfolioPage.tsx` - Added debug blocks
5. `ui/frontend/src/features/trading/TradingPage.tsx` - Added debug blocks

## Next Steps

For the user to see live updating data:
1. Configure paper capital in `configs/dev.yaml`
2. Start the paper engine: `python scripts/run_paper_engine.py`
3. Wait for signals and trades to be generated
4. Monitor the dashboard - metrics will update automatically

The dashboard is ready and working correctly! 🎉
