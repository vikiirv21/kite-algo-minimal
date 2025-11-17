# New Dashboard Overview

## Architecture

The new Arthayukti HFT Dashboard is a modern, single-page application built with:
- **Server**: FastAPI (unchanged)
- **Frontend**: Vanilla JavaScript ES modules
- **Styling**: Custom CSS with design system (CSS variables)
- **Layout**: CSS Grid + Flexbox
- **Data Flow**: Centralized state management with polling

## Design System

### Dark Theme Colors
- **Background**: `--bg-main` (#0a0e14), `--bg-elevated` (#13171f), `--bg-card` (#1a1f2a)
- **Text**: `--text-primary` (#e6edf3), `--text-secondary` (#8b949e), `--text-muted` (#6e7681)
- **Accent**: `--accent` (#3b82f6), `--accent-soft` (#1e40af)
- **Status**: `--success` (#10b981), `--warning` (#f59e0b), `--danger` (#ef4444)

### Typography
- **Font**: Inter (Google Fonts) with system fallbacks
- **Sizes**: xs (12px), sm (14px), md (16px), lg (18px), xl (20px), 2xl (24px), 3xl (30px)
- **Weights**: light (300), normal (400), medium (500), semibold (600), bold (700)

### Spacing Scale
- `--space-1` through `--space-8` (4px to 64px increments)
- Consistent use across padding, margins, gaps

## File Structure

```
ui/
├── templates/
│   └── dashboard.html          # Main HTML template
├── static/
│   ├── css/
│   │   └── dashboard.css       # Design system + styles
│   └── js/
│       └── dashboard/
│           ├── main.js         # Bootstrap & polling
│           ├── api_client.js   # API calls
│           ├── state.js        # State management
│           ├── tabs.js         # Tab rendering
│           └── components/
│               └── index.js    # Reusable UI components
```

## Tabs

### 1. Overview
**Purpose**: At-a-glance view of key metrics

**Cards**:
- Engine Status (running/stopped, mode)
- Portfolio Snapshot (equity, P&L, exposure)
- Recent Signals (last 5 signals)

**Data Sources**:
- `/api/engines/status`
- `/api/portfolio/summary`
- `/api/signals?limit=50`

**Refresh**: 2s

---

### 2. Trading
**Purpose**: Active orders and execution monitoring

**Cards**:
- Active Orders (real-time order book)

**Data Sources**:
- `/api/orders?limit=50`

**Refresh**: 3s

---

### 3. Portfolio
**Purpose**: Detailed portfolio and positions view

**Cards**:
- Portfolio Summary (all portfolio metrics)
- Open Positions (symbol, side, qty, avg, LTP, P&L)

**Data Sources**:
- `/api/portfolio/summary`
- `/api/positions/open`

**Refresh**: 2-3s

---

### 4. Signals
**Purpose**: All generated signals

**Cards**:
- All Signals (time, symbol, TF, signal, price, strategy)

**Data Sources**:
- `/api/signals?limit=50`

**Refresh**: 2s

---

### 5. Analytics
**Purpose**: Performance analytics and visualizations

**Cards**:
- Today at a Glance (realized P&L, trades, win rate, avg R)
- Equity Curve (placeholder for chart)
- Analytics Features (notes on planned features)

**Data Sources**:
- `/api/summary/today`
- `/api/stats/equity?days=1`
- `/api/analytics/summary` (optional, may not exist)

**Refresh**: 10s

**Missing Backend Endpoints** (to be implemented):
- `/api/analytics/benchmarks` - NIFTY, BANKNIFTY equity comparison
- `/api/analytics/strategy_perf` - Per-strategy metrics with win rate, max DD, etc.

**Suggested Response Format for Benchmarks**:
```json
{
  "equity_curve": [
    {"ts": "2024-01-15T09:15:00", "equity": 100000, "nifty": 19500, "banknifty": 43000}
  ]
}
```

**Suggested Response Format for Strategy Performance**:
```json
{
  "strategies": [
    {
      "name": "EMA Crossover",
      "total_trades": 42,
      "win_rate": 65.5,
      "avg_pnl": 850.0,
      "max_drawdown": -2500.0,
      "sharpe_ratio": 1.8
    }
  ]
}
```

---

### 6. System
**Purpose**: Configuration and system information

**Cards**:
- Configuration (mode, capital, risk parameters, exposure limits)
- System Info (server time, market status)

**Data Sources**:
- `/api/config/summary`
- `/api/meta`

**Refresh**: 30s (config), 1s (time)

---

### 7. Logs
**Purpose**: Engine logs with filtering

**Features**:
- Level filter (ALL, INFO, WARNING, ERROR)
- Auto-scroll toggle (follows new logs when enabled)
- Real-time updates

**Data Sources**:
- `/api/logs?limit=150`

**Refresh**: 3s

---

## State Management

**Central State Object**:
```javascript
{
  serverTime: null,
  marketOpen: false,
  mode: 'IDLE',  // Derived from engines
  engines: [],
  portfolioSnapshot: null,
  todaySummary: null,
  positionsOpen: [],
  orders: [],
  signals: [],
  logs: [],
  equityCurve: [],
  analyticsSummary: null,
  config: null,
  activeTab: 'overview',
  connectionStatus: 'checking'
}
```

**Mode Derivation Logic**:
- If any engine has `mode='live'` and `running=true` → **LIVE**
- Else if any engine has `mode='paper'` and `running=true` → **PAPER**
- Else → **IDLE**

## Polling Strategy

| Data Type | Interval | Reason |
|-----------|----------|--------|
| Server time | 1s | Clock display |
| Engines | 2s | Critical - mode badge |
| Portfolio | 2s | Live P&L tracking |
| Positions | 3s | Live position monitoring |
| Orders | 3s | Order book updates |
| Signals | 2s | Signal stream |
| Logs | 3s | Log tailing |
| Analytics | 10s | Slow-changing metrics |
| Config | 30s | Very slow-changing |

**Optimization**: Polling pauses when page is hidden (visibility API) and resumes on focus.

## API Mapping

### Overview Tab
- Engines: `/api/engines/status`
- Portfolio: `/api/portfolio/summary`
- Signals: `/api/signals?limit=50`

### Trading Tab
- Orders: `/api/orders?limit=50`

### Portfolio Tab
- Summary: `/api/portfolio/summary`
- Positions: `/api/positions/open`

### Signals Tab
- All signals: `/api/signals?limit=50`

### Analytics Tab
- Today: `/api/summary/today`
- Equity: `/api/stats/equity?days=1`
- Summary: `/api/analytics/summary` (optional)

### System Tab
- Config: `/api/config/summary`
- Meta: `/api/meta`
- Time: `/api/system/time`

### Logs Tab
- Logs: `/api/logs?limit=150&level=INFO&kind=engine`

## Component Reusability

**Available Components** (`components/index.js`):
- `createCard(title, subtitle, content)` - Card wrapper
- `createTable(headers, rows)` - Data tables
- `createBadge(label, variant)` - Status badges
- `createSkeletonLines(count)` - Loading skeletons
- `createMetricRow(label, value)` - Key-value pairs

**Formatters**:
- `formatCurrency(value, decimals)` - INR currency
- `formatNumber(value, decimals)` - Numbers with precision
- `formatPercent(value, decimals)` - Percentage
- `formatTime(isoString)` - HH:MM:SS IST
- `formatShortTime(isoString)` - HH:MM IST

## Extending the Dashboard

### Adding a New Tab

1. **HTML**: Add tab button to `dashboard.html`:
   ```html
   <button class="tab" data-tab="mytab">My Tab</button>
   ```

2. **Render Function**: Add to `tabs.js`:
   ```javascript
   function renderMyTab() {
     const container = document.createElement('div');
     // Build UI
     return container;
   }
   ```

3. **Switch Case**: Update `renderTab()` in `tabs.js`:
   ```javascript
   case 'mytab':
     content.appendChild(renderMyTab());
     break;
   ```

4. **Data Fetching**: Add API call in `main.js`:
   ```javascript
   async function fetchMyData() {
     const data = await API.getMyData();
     setState({ myData: data });
     if (getState().activeTab === 'mytab') {
       renderTab('mytab');
     }
   }
   ```

5. **Polling**: Add interval in `main.js`:
   ```javascript
   timers.myData = setInterval(fetchMyData, 5000);
   ```

### Adding a New API Endpoint

1. Add function to `api_client.js`:
   ```javascript
   export async function getMyData() {
     return fetchAPI('/api/my/endpoint');
   }
   ```

2. Use in fetch functions in `main.js`

## Skeleton Loaders

All cards show skeleton loaders while data is loading:
- `createSkeletonLines(count)` - Animated shimmer effect
- Automatically replaced with real data once fetched

## Error Handling

- API errors are logged to console
- Connection status dot shows:
  - 🟢 Green (ok) - All APIs responding
  - 🔴 Red (error) - API failures detected
  - ⚪ Gray (checking) - Initial state

## Performance

- **ES Modules**: Code-split by module, only loads what's needed
- **Conditional Rendering**: Only active tab is rendered
- **Polling Pause**: Stops when page is hidden
- **Debounced Updates**: State changes trigger single re-render

## Browser Compatibility

- Modern browsers with ES6+ support required
- Chrome 90+, Firefox 88+, Safari 14+, Edge 90+
- No polyfills included

## Future Enhancements

### Short Term
- Chart.js or ECharts integration for equity curve
- Benchmark comparison charts (NIFTY, BANKNIFTY)
- Real-time WebSocket data (replace polling)
- Export logs/data to CSV

### Medium Term
- Dark/light theme toggle
- Customizable dashboard layouts (drag & drop cards)
- Alert notifications (browser notifications API)
- Multi-strategy P&L breakdown with charts

### Long Term
- Historical performance replay
- Strategy backtesting UI integration
- Mobile-responsive enhancements
- Multi-account support

## Development

**Run Dashboard**:
```bash
cd /home/runner/work/kite-algo-minimal/kite-algo-minimal
uvicorn ui.dashboard:app --reload --port 8765
```

**Access**:
- Dashboard: http://localhost:8765/
- API Docs: http://localhost:8765/docs

**Hot Reload**:
- CSS: Instant (browser refresh)
- JS: Instant (ES modules reload on import)
- Python: Automatic (uvicorn --reload)

## Notes

- Old dashboard archived to `archive/old_dashboard/`
- No external JS dependencies (Chart.js to be added for charts)
- All data fetched from real backend APIs
- No fake/mock data in production code
