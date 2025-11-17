# Arthayukti Dashboard - Technical Overview

## Current Dashboard Implementation

### Frontend Structure
- **Main Template**: `ui/templates/index.html` - Single-page dashboard with tabbed layout
- **JavaScript Modules**:
  - `static/js/api.js` - API utilities with retry logic
  - `static/js/arthayukti.js` - Main controller with polling
  - `static/js/tabs.js` - Tab management
  - `static/dashboard.js` - Legacy implementation (931 lines)
- **CSS**: Inline in `index.html` with dark theme CSS variables
- **Pages**: HTMX-loaded pages in `ui/templates/pages/` (overview, portfolio, engines, etc.)

### Current Issues & Gaps
1. **Live Refresh**: Portfolio, positions, and orders tabs need consistent live-refresh restoration
2. **Architecture**: Mixed inline and external JS - needs centralization
3. **Analytics**: Backend analytics endpoints exist but frontend charting needs implementation
4. **Documentation**: API usage patterns scattered across files

## Backend API Endpoints

### System & Meta
| Endpoint | Method | Description | Response Keys |
|----------|--------|-------------|---------------|
| `/api/system/time` | GET | Current UTC time | `{utc: string}` |
| `/api/meta` | GET | Market status & metadata | `{now_ist, market_open, market_status, regime}` |
| `/api/health` | GET | Aggregate health check | `{engine_status, log_health, market_status}` |
| `/api/config/summary` | GET | Trading configuration | `{mode, fno_universe, paper_capital, risk_profile}` |

### Engines & Execution
| Endpoint | Method | Description | Response Keys |
|----------|--------|-------------|---------------|
| `/api/engines/status` | GET | Engine runtime status | `{engines: [{engine, running, mode, last_checkpoint_ts}]}` |
| `/api/state` | GET | Full runtime state | Complete state checkpoint |
| `/api/auth/status` | GET | Kite API authentication | `{is_logged_in, token_valid, user_id}` |

### Portfolio & Positions
| Endpoint | Method | Description | Response Keys |
|----------|--------|-------------|---------------|
| `/api/portfolio/summary` | GET | Portfolio snapshot | `{equity, paper_capital, total_realized_pnl, total_unrealized_pnl, exposure_pct, position_count}` |
| `/api/positions/open` | GET | Open positions | `[{symbol, side, quantity, avg_price, last_price, unrealized_pnl}]` |
| `/api/positions_normalized` | GET | Detailed positions with LTP | Enhanced position data with lot sizes |
| `/api/risk/summary` | GET | Risk metrics | `{mode, per_trade_risk_pct, trading_halted, current_day_pnl}` |
| `/api/margins` | GET | Margin availability (live mode) | `{available, utilized, span, exposure}` |

### Orders & Trades
| Endpoint | Method | Description | Response Keys |
|----------|--------|-------------|---------------|
| `/api/orders` | GET | Orders list | Array of order objects |
| `/api/orders/recent` | GET | Recent orders (limit param) | `{orders: [...]}` |
| `/api/summary/today` | GET | Today's P&L summary | `{realized_pnl, num_trades, win_rate, largest_win/loss}` |

### Signals & Strategies
| Endpoint | Method | Description | Response Keys |
|----------|--------|-------------|---------------|
| `/api/signals` | GET | Signals list | Array of signal objects |
| `/api/signals/recent` | GET | Recent signals (limit param) | Array of signals |
| `/api/stats/strategies` | GET | Strategy statistics | Array of strategy metrics |
| `/api/strategy_performance` | GET | Per-strategy P&L | `[{name, code, pnl, wins, losses}]` |
| `/api/quality/summary` | GET | Signal quality & throttler | `{total_signals, total_trades_taken, veto_breakdown}` |

### Logs & Monitoring
| Endpoint | Method | Description | Response Keys |
|----------|--------|-------------|---------------|
| `/api/logs` | GET | Engine logs | `{logs: [{timestamp, level, source, message}]}` |
| `/api/logs/recent` | GET | Recent logs with filters | Supports `level`, `contains`, `kind` params |
| `/api/pm/log` | GET | PM-specific logs | Same as logs endpoint |
| `/api/monitor/trade_flow` | GET | Trade funnel metrics | `{signals_seen, trades_allowed, orders_filled}` |
| `/api/trade_flow` | GET | Enhanced trade flow | Includes funnel and recent hits |

### Analytics & Performance (✅ AVAILABLE)
| Endpoint | Method | Description | Response Keys |
|----------|--------|-------------|---------------|
| `/api/stats/equity` | GET | Equity curve data | `[{ts, equity, realized, unrealized}]` |
| `/api/analytics/summary` | GET | Combined analytics | `{daily, strategies, symbols}` |
| `/api/analytics/equity_curve` | GET | Equity curve with drawdown | `{equity_curve, drawdown}` |

### Market Data
| Endpoint | Method | Description | Response Keys |
|----------|--------|-------------|---------------|
| `/api/quotes` | GET | Live quotes cache | Symbol-keyed quote data |
| `/api/scanner/universe` | GET | Instrument universe | Universe snapshot from MarketScanner |
| `/api/market_data/window` | GET | Historical candles | `{symbol, timeframe, candles: [...]}` |
| `/api/market_data/latest_tick` | GET | Latest tick (MDE v2) | `{symbol, ltp, bid, ask, volume}` |
| `/api/market_data/candles` | GET | Candles from MDE v2 | Enhanced candle data |
| `/api/market_data/v2/stats` | GET | MDE v2 statistics | Feed stats and symbol count |

### Backtests
| Endpoint | Method | Description | Response Keys |
|----------|--------|-------------|---------------|
| `/api/backtests` | GET | List backtest runs | `{runs: [{run_id, strategy, symbol, net_pnl}]}` |
| `/api/backtests/{run_id}/summary` | GET | Backtest details | Full backtest result |
| `/api/backtests/{run_id}/equity_curve` | GET | Backtest equity curve | Time-series equity data |

### Actions
| Endpoint | Method | Description | Response Keys |
|----------|--------|-------------|---------------|
| `/api/resync` | POST | Rebuild state from journal | `{ok: bool, mode, timestamp}` |

## Live-Refresh Mechanisms

### Previous Working Behavior
The dashboard previously had live-refresh for:
1. **Portfolio Summary** - polled every ~3-5 seconds
2. **Open Positions** - polled every ~3-5 seconds  
3. **Orders** - polled every ~3-5 seconds
4. **Engine Status** - polled every ~10 seconds

### Implementation Pattern
```javascript
// Previous pattern (from arthayukti.js)
const POLL_INTERVALS = {
    serverTime: 1000,        // 1 second
    meta: 5000,              // 5 seconds
    engines: 10000,          // 10 seconds
    portfolio: 10000,        // 10 seconds (should be faster)
    logs: 5000,              // 5 seconds
    signals: 10000,          // 10 seconds
};
```

### Recommended Intervals
Based on data volatility and user needs:
- **Critical (1-3s)**: Portfolio summary, open positions, orders (during market hours)
- **Important (5-10s)**: Signals, engine status, logs
- **Background (30-60s)**: Config, health, strategies

## Analytics Implementation Status

### ✅ Backend Ready
- Equity curve endpoint: `/api/stats/equity`
- Strategy analytics: `/api/analytics/summary`
- Drawdown calculation: `/api/analytics/equity_curve`

### 📊 Frontend Needs
1. **Chart Library**: Need to add lightweight chart library (e.g., Chart.js, uPlot, or Lightweight Charts)
2. **Analytics Tab**: Wire equity curve and strategy performance charts
3. **Benchmark Comparison**: If NIFTY/BANKNIFTY index data available, add overlay

### Missing Backend Features (for future)
These would enhance analytics but are NOT blocking:
- `/api/perf/benchmark` - NIFTY/BANKNIFTY historical data for overlay comparison
- `/api/perf/sharpe` - Risk-adjusted metrics (Sharpe, Sortino)
- `/api/perf/monthly` - Monthly P&L breakdown

## Architecture Recommendations

### Frontend File Structure (Target)
```
static/
  js/
    api_client.js       # Centralized API calls with error handling
    state_store.js      # Global state and polling lifecycle
    dashboard_tabs.js   # Tab switching and per-tab renderers
    components/
      card.js           # Reusable card component
      table.js          # Data table helpers
      badge.js          # Status badges
  css/
    dashboard.css       # Dark theme with CSS variables
templates/
  index.html           # Main dashboard template
  pages/              # HTMX page partials (keep existing)
```

### State Management Pattern
```javascript
// Centralized state
const state = {
    meta: {},
    engines: [],
    portfolio: {},
    positions: [],
    orders: [],
    signals: [],
    logs: [],
    strategies: [],
    activeTab: 'overview',
};

// Update and render
function updateState(key, data) {
    state[key] = data;
    renderActiveTab();
}
```

### Tab-Specific Polling
```javascript
// Start polling for active tab only
function activateTab(tabName) {
    clearAllIntervals();
    state.activeTab = tabName;
    
    // Common intervals (always active)
    startInterval('time', 1000);
    startInterval('meta', 5000);
    
    // Tab-specific intervals
    if (tabName === 'portfolio') {
        startInterval('portfolio', 3000);
        startInterval('positions', 3000);
        startInterval('orders', 3000);
    } else if (tabName === 'engines') {
        startInterval('engines', 5000);
        startInterval('logs', 5000);
    }
    // ... etc
}
```

## Mode Detection

Mode is derived from engine status:
```javascript
function detectMode(engines) {
    const hasLive = engines.some(e => e.running && e.mode === 'live');
    const hasPaper = engines.some(e => e.running && e.mode === 'paper');
    
    if (hasLive) return 'LIVE';
    if (hasPaper) return 'PAPER';
    return 'IDLE';
}
```

## Next Steps

1. ✅ Create this documentation
2. Implement `api_client.js` with all endpoint wrappers
3. Implement `state_store.js` with polling lifecycle
4. Implement `dashboard_tabs.js` with tab-specific renderers
5. Add charting library for analytics tab
6. Restore live-refresh intervals for portfolio tab
7. Test end-to-end with running engine
8. Take screenshots and validate
