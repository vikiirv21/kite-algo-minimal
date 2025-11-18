# Dashboard API Endpoint Mapping

This document maps React dashboard UI components to FastAPI backend endpoints.

## Core Dashboard Endpoints

### Portfolio & P&L
| Purpose | Method | Endpoint | Response Fields | Frontend Hook |
|---------|--------|----------|-----------------|---------------|
| Portfolio snapshot | GET | `/api/portfolio/summary` | `paper_capital`, `total_realized_pnl`, `total_unrealized_pnl`, `equity`, `total_notional`, `free_notional`, `exposure_pct`, `daily_pnl`, `has_positions`, `position_count`, `note` | `usePortfolioSummary()` |
| Open positions | GET | `/api/positions/open` | Array of: `symbol`, `side`, `quantity`, `avg_price`, `last_price`, `unrealized_pnl` | `useOpenPositions()` |
| Today's summary | GET | `/api/summary/today` | `date`, `realized_pnl`, `num_trades`, `win_trades`, `loss_trades`, `win_rate`, `largest_win`, `largest_loss`, `avg_r` | `useTodaySummary()` |

### Orders
| Purpose | Method | Endpoint | Response Fields | Frontend Hook |
|---------|--------|----------|-----------------|---------------|
| Recent orders | GET | `/api/orders/recent?limit=50` | `{ orders: [...] }` where each order has: `timestamp`, `symbol`, `side`, `quantity`, `price`, `status`, `order_id`, `pnl` | `useRecentOrders(limit)` |
| All orders | GET | `/api/orders?limit=150` | Array of orders (same fields as above) | `useOrders(limit)` |

### Signals
| Purpose | Method | Endpoint | Response Fields | Frontend Hook |
|---------|--------|----------|-----------------|---------------|
| Recent signals | GET | `/api/signals/recent?limit=50` | Array of: `ts`, `symbol`, `logical`, `signal`, `tf`, `price`, `profile`, `strategy` | `useRecentSignals(limit)` |
| All signals | GET | `/api/signals?limit=150` | Array of signals (same fields as above) | `useSignals(limit)` |

### Logs
| Purpose | Method | Endpoint | Response Fields | Frontend Hook |
|---------|--------|----------|-----------------|---------------|
| Engine logs | GET | `/api/logs?limit=150&level=...&contains=...&kind=...` | `{ logs: [...], entries: [...] }` where each entry has: `timestamp`/`ts`, `level`, `source`/`logger`, `message`, `raw` | `useLogs(params)` |

### Engines & System
| Purpose | Method | Endpoint | Response Fields | Frontend Hook |
|---------|--------|----------|-----------------|---------------|
| Engine status | GET | `/api/engines/status` | `{ engines: [...] }` where each engine has: `engine`, `running`, `last_checkpoint_ts`, `checkpoint_age_seconds`, `market_open`, `mode`, `error`, `checkpoint_path` | `useEnginesStatus()` |
| Meta/clock | GET | `/api/meta` | `now_ist`, `market_open`, `market_status`, `status_payload`, `regime`, `regime_snapshot` | `useMeta()` |
| Config summary | GET | `/api/config/summary` | `config_path`, `mode`, `fno_universe`, `paper_capital`, `risk_per_trade_pct`, `max_daily_loss`, `max_exposure_pct`, `max_positions`, `risk_profile`, `meta_enabled` | `useConfigSummary()` |
| Auth status | GET | `/api/auth/status` | `is_logged_in`, `user_id`, `login_ts`, `login_age_minutes`, `token_valid`, `error` | `useAuthStatus()` |
| System time | GET | `/api/system/time` | `{ utc: "..." }` | `useSystemTime()` |

### Analytics
| Purpose | Method | Endpoint | Response Fields | Frontend Hook |
|---------|--------|----------|-----------------|---------------|
| Strategy stats | GET | `/api/stats/strategies?days=1` | Array of strategy metrics | `useStrategyStats(days)` |
| Equity curve | GET | `/api/stats/equity?days=1` | Array of equity snapshots | `useEquityCurve(days)` |
| Analytics summary | GET | `/api/analytics/summary` | `daily`, `strategies`, `symbols` aggregates | `useAnalyticsSummary()` |
| Risk summary | GET | `/api/risk/summary` | `mode`, `per_trade_risk_pct`, `max_daily_loss_abs`, etc. | `useRiskSummary()` |

## Endpoint Status Summary

### ✅ Working (signals and logs are updating)
- `/api/signals` - Signals endpoint
- `/api/signals/recent` - Recent signals
- `/api/logs` - Engine logs

### ✅ Implemented and Mapped
- `/api/portfolio/summary` - Portfolio snapshot **[MAPPED]**
- `/api/positions/open` - Open positions **[MAPPED]**
- `/api/orders/recent` - Recent orders **[MAPPED]**
- `/api/orders` - All orders **[MAPPED]**
- `/api/summary/today` - Today's trade summary **[MAPPED]**
- `/api/engines/status` - Engine status **[MAPPED]**
- `/api/meta` - Market clock/status **[MAPPED]**

### Polling Configuration
All critical dashboard hooks have `refetchInterval` configured:
- Portfolio: 2000ms (2 seconds)
- Positions: 3000ms (3 seconds)
- Orders: 3000-5000ms (3-5 seconds)
- Signals: 2000-5000ms (2-5 seconds)
- Logs: 2000ms (2 seconds)
- Meta: 2000ms (2 seconds)
- Engines: 3000ms (3 seconds)

## Page → Hook → Endpoint Mapping

### OverviewPage (`/`)
- `useEnginesStatus()` → `/api/engines/status` - Shows mode and engine status
- `usePortfolioSummary()` → `/api/portfolio/summary` - Shows equity, daily P&L, positions, exposure
- `useRecentSignals(10)` → `/api/signals/recent?limit=10` - Recent signals table
- `useTodaySummary()` → `/api/summary/today` - Today's trades, realized P&L, win rate

### PortfolioPage (`/portfolio`)
- `usePortfolioSummary()` → `/api/portfolio/summary` - Full portfolio metrics
- `useOpenPositions()` → `/api/positions/open` - Open positions table with unrealized P&L

### TradingPage (`/trading`)
- `useRecentOrders(50)` → `/api/orders/recent?limit=50` - Active and completed orders

### SignalsPage (`/signals`)
- `useSignals(150)` → `/api/signals?limit=150` - Full signals list

### LogsPage (`/logs`)
- `useLogs(params)` → `/api/logs?...` - Filtered engine logs

### AnalyticsPage (`/analytics`)
- `useAnalyticsSummary()` → `/api/analytics/summary` - Strategy and symbol analytics
- `useAnalyticsEquityCurve()` → `/api/analytics/equity_curve` - Equity curve data

### RiskPage (`/risk`)
- `useRiskSummary()` → `/api/risk/summary` - Risk config and current state

## Notes

### Data Flow
1. Backend FastAPI serves endpoints from `ui/dashboard.py`
2. Frontend React calls these via `api/client.ts`
3. React Query hooks in `hooks/useApi.ts` wrap the API calls with caching/polling
4. Pages import and use the hooks to display data
5. All hooks have `refetchInterval` configured for live updates

### Current Status
- **Backend**: All necessary endpoints are implemented ✅
- **Frontend Hooks**: All hooks are properly mapped to endpoints ✅
- **Page Usage**: All pages are using the correct hooks ✅
- **Polling**: All hooks have refetchInterval configured ✅

The mapping is complete and correct. If data is not updating:
1. Check that the backend server is running
2. Check that the engine/paper engine is running and writing checkpoints
3. Check browser DevTools Network tab to verify API calls are being made
4. Check API responses contain non-zero/non-null values
5. Verify checkpoint files exist in `artifacts/checkpoints/`
