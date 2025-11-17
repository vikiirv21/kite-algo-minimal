# Analytics and Risk API Gaps

This document lists the missing backend APIs and features for the Analytics and Risk pages in the React dashboard.

## Current Status

### ✅ Working Features

#### Analytics Page
- **Daily P&L Summary**: `GET /api/analytics/summary` ✓
  - Today's realized P&L
  - Win rate and trade statistics
  - Per-strategy performance breakdown
  - Per-symbol performance breakdown
  
- **Equity Curve**: `GET /api/analytics/equity_curve` ✓
  - Equity snapshots over time
  - Realized vs unrealized P&L tracking
  - Drawdown calculations
  
#### Risk Page
- **Risk Summary**: `GET /api/risk/summary` ✓
  - Current trading mode
  - Risk configuration (per-trade risk %)
  - Daily loss limits
  - Trading halt status
  
- **Portfolio Summary**: `GET /api/portfolio/summary` ✓
  - Current equity and exposure
  - Position count
  - Daily P&L
  
- **Configuration**: `GET /api/config/summary` ✓
  - Paper capital
  - Max daily loss
  - Max exposure percentage
  - Risk profile

---

## 🔴 Missing Features

### Analytics Page

#### 1. Benchmark Comparison
**Status**: Not implemented

**Required Endpoint**:
```
GET /api/benchmarks
Query params: 
  - days: int (default: 1) - lookback period
  - symbols: string (optional) - comma-separated list of benchmark symbols
```

**Expected Response**:
```json
[
  {
    "ts": "2024-11-17T10:00:00+00:00",
    "nifty": 19500.50,
    "banknifty": 45123.25,
    "finnifty": 20456.75
  }
]
```

**Implementation Notes**:
- Backend module: `analytics/benchmarks.py` (to be created)
- Data source: Could pull from market data engine or external feed
- Calculation: Should track benchmark indices during market hours
- Storage: Consider caching in artifacts/benchmarks.csv for historical comparison

**UI Location**: `ui/frontend/src/features/analytics/AnalyticsPage.tsx` (placeholder already exists)

---

### Risk Page

#### 1. Max Positions Configuration
**Status**: Hardcoded in frontend (value: 5)

**Required**: Add `max_positions` field to config or risk endpoints

**Suggested Changes**:
- Add to `GET /api/config/summary` response:
  ```json
  {
    "max_positions": 5,
    "max_positions_per_symbol": 1,
    "max_positions_per_strategy": 3
  }
  ```
- OR add to `GET /api/risk/summary` response

**Implementation Notes**:
- Backend module: `core/config.py` - add to AppConfig
- Config file: Add to `configs/*.yaml` under `risk` section:
  ```yaml
  risk:
    max_positions: 5
    max_positions_per_symbol: 1
    max_positions_per_strategy: 3
  ```

**UI Location**: `ui/frontend/src/features/risk/RiskPage.tsx:22` (TODO comment)

---

#### 2. Advanced Risk Metrics (Future Enhancement)
**Status**: Placeholder only

**Planned Features**:
- Max drawdown monitoring
- Per-symbol position limits
- Correlation-adjusted exposure
- Value at Risk (VaR) calculations
- Real-time risk alerts and notifications

**Suggested Endpoints**:

```
GET /api/risk/limits
Returns all configured risk limits and current usage
{
  "daily_loss": {
    "limit": 3000,
    "used": 250,
    "remaining": 2750
  },
  "exposure": {
    "limit_pct": 1.0,
    "current_pct": 0.45,
    "remaining_pct": 0.55
  },
  "positions": {
    "max_total": 5,
    "current": 2,
    "by_symbol": {
      "NIFTY": { "limit": 1, "current": 1 },
      "BANKNIFTY": { "limit": 1, "current": 1 }
    }
  }
}
```

```
GET /api/risk/breaches
Returns current limit breaches or warnings
{
  "breaches": [
    {
      "type": "daily_loss",
      "severity": "warning",
      "message": "Daily loss at 80% of limit",
      "timestamp": "2024-11-17T14:30:00+00:00"
    }
  ]
}
```

```
GET /api/risk/var
Returns Value at Risk calculations
{
  "var_95": 1500.0,
  "var_99": 2200.0,
  "confidence_level": 0.95,
  "lookback_days": 30,
  "calculated_at": "2024-11-17T15:30:00+00:00"
}
```

**Implementation Notes**:
- Backend module: `risk/metrics.py` (to be created)
- Requires: Historical P&L data for VaR calculations
- Requires: Position correlation analysis for correlation-adjusted exposure
- Storage: artifacts/risk/var_history.csv for tracking

**UI Location**: `ui/frontend/src/features/risk/RiskPage.tsx` (placeholder card exists)

---

## Implementation Priority

### High Priority
1. **Max Positions Config** - Simple config change, no new APIs needed

### Medium Priority
2. **Benchmark Comparison** - Enhances analytics, requires data feed integration

### Low Priority (Future)
3. **Advanced Risk Metrics** - Complex calculations, nice-to-have features

---

## Testing the APIs

Once implemented, test with:

```bash
# Test analytics summary
curl http://localhost:8765/api/analytics/summary | jq

# Test benchmarks (once implemented)
curl http://localhost:8765/api/benchmarks?days=1 | jq

# Test risk limits (once implemented)
curl http://localhost:8765/api/risk/limits | jq
```

---

## Notes for Developers

1. All new endpoints should follow the `/api/*` prefix convention
2. Use appropriate refetch intervals in React hooks (5-10 seconds for analytics/risk data)
3. Handle empty/null responses gracefully in the UI
4. Add TypeScript types to `ui/frontend/src/types/api.ts`
5. Add API client functions to `ui/frontend/src/api/client.ts`
6. Add React hooks to `ui/frontend/src/hooks/useApi.ts`
7. Consider rate limiting on data-heavy endpoints

---

Last Updated: 2024-11-17
