# Arthayukti React Dashboard - Overview

## Architecture

The Arthayukti dashboard is a modern React-based HFT (High-Frequency Trading) control panel built with:

- **React 19** - UI framework
- **TypeScript** - Type safety
- **Vite** - Build tool
- **Tailwind CSS** - Styling (dark theme by default)
- **React Router** - Client-side routing
- **React Query** - Data fetching and caching
- **Recharts** - Charts and visualizations

## Project Structure

```
ui/frontend/
├── src/
│   ├── api/
│   │   └── client.ts           # API client with all endpoint definitions
│   ├── components/
│   │   ├── Card.tsx            # Card component with loading & error states
│   │   ├── ConnectionStatus.tsx # Connection status indicator
│   │   ├── Sidebar.tsx         # Main navigation sidebar
│   │   └── TopBar.tsx          # Top bar with page title & system info
│   ├── features/
│   │   ├── analytics/          # Analytics page with charts
│   │   ├── logs/               # Engine logs viewer
│   │   ├── overview/           # Dashboard overview
│   │   ├── portfolio/          # Portfolio & positions
│   │   ├── risk/               # Risk management dashboard
│   │   ├── signals/            # Signals & strategies
│   │   ├── system/             # System info & config
│   │   └── trading/            # Orders & executions
│   ├── hooks/
│   │   └── useApi.ts           # React Query hooks for all APIs
│   ├── types/
│   │   └── api.ts              # TypeScript type definitions
│   ├── utils/
│   │   └── format.ts           # Formatting utilities (currency, time, P&L)
│   ├── App.tsx                 # Main app with routes
│   ├── main.tsx               # App entry point
│   └── index.css              # Global styles
├── public/                     # Static assets
├── package.json               # Dependencies
├── vite.config.ts             # Vite configuration
├── tailwind.config.js         # Tailwind theme configuration
└── tsconfig.json              # TypeScript configuration
```

## Pages & Tabs

### 1. Overview (`/`)
The main dashboard showing:
- **Engines Status** - Running/stopped status, mode (PAPER/LIVE)
- **Portfolio Snapshot** - Equity, daily P&L, positions count, exposure
- **Today's Trading** - Realized P&L, trade count, win rate, avg R
- **Risk Budget** - Max daily loss tracking with progress bar
- **Recent Signals** - Last 10 signals with direction, price, strategy

**APIs Used:**
- `GET /api/engines/status`
- `GET /api/portfolio/summary`
- `GET /api/summary/today`
- `GET /api/signals/recent?limit=10`

### 2. Trading (`/trading`)
Order management:
- **Active Orders** - Open, pending, trigger-pending orders
- **Recent Orders** - Completed/filled orders with P&L

**APIs Used:**
- `GET /api/orders/recent?limit=50`

### 3. Portfolio (`/portfolio`)
Portfolio details:
- **Portfolio Summary** - Equity, realized/unrealized P&L, margin, exposure
- **Open Positions** - Current positions with live P&L
- **Closed Positions** - Trade history (placeholder - needs API)

**APIs Used:**
- `GET /api/portfolio/summary`
- `GET /api/positions/open`

### 4. Signals (`/signals`)
Signal monitoring and strategy management:
- **Active Strategies** - Strategy list with win rates, signal counts
- **Strategy Lab** - Placeholder for strategy controls (enable/disable, parameter adjustment)
- **Signal Stream** - Scrollable stream of recent signals

**APIs Used:**
- `GET /api/stats/strategies?days=1`
- `GET /api/signals/recent?limit=50`

### 5. Analytics (`/analytics`)
Performance analysis:
- **Equity Curve** - Line chart of equity over time
- **Benchmarks** - Placeholder for NIFTY/BANKNIFTY comparison
- **Strategy Performance** - Placeholder for per-strategy metrics

**APIs Used:**
- `GET /api/stats/equity?days=1`

**Placeholder APIs Needed:**
```
GET /api/benchmarks -> [{ ts, nifty, banknifty }]
GET /api/analytics/strategies -> [{ strategy, pnl, win_rate, max_drawdown, ... }]
```

### 6. Risk (`/risk`)
Risk management dashboard:
- **Daily Loss Limit** - Max loss tracking with gauge
- **Exposure Limit** - Current vs max exposure
- **Position Limit** - Open positions count
- **Risk Configuration** - Risk profile, risk per trade, capital
- **Capital at Risk** - Equity, unrealized P&L, free margin
- **Advanced Metrics** - Placeholder for VaR, drawdown monitoring

**APIs Used:**
- `GET /api/portfolio/summary`
- `GET /api/config/summary`
- `GET /api/summary/today`

**Placeholder APIs Needed:**
```
GET /api/risk/limits -> { max_positions, max_daily_loss, ... }
GET /api/risk/breaches -> [{ type, limit, current, ... }]
GET /api/risk/var -> { var_95, var_99, ... }
```

### 7. System (`/system`)
System information:
- **System Info** - Mode, risk profile, auth status
- **Config Summary** - FNO universe, capital, risk settings
- **Raw JSON** - Collapsible full config for debugging

**APIs Used:**
- `GET /api/config/summary`
- `GET /api/auth/status`

### 8. Logs (`/logs`)
Engine logs viewer:
- **Level Filter** - Filter by DEBUG/INFO/WARNING/ERROR
- **Auto-follow** - Automatically scroll to new logs
- **Scrollable Log Window** - 600px fixed height with custom scrollbar
- **Log Formatting** - Timestamp, level badge, source, message

**APIs Used:**
- `GET /api/logs?limit=200&level={level}`

## Design System

### Colors
Defined in `tailwind.config.js`:

**Backgrounds:**
- `background` - Main background (#0a0e1a)
- `surface` - Card/component background (#121825)
- `surface-light` - Hover states (#1a2332)
- `border` - Borders (#2a3447)

**Status:**
- `positive` - Gains (#10b981)
- `negative` - Losses (#ef4444)
- `warning` - Alerts (#f59e0b)
- `primary` - Primary actions (#3b82f6)

**Text:**
- `text-primary` - Main text (#f3f4f6)
- `text-secondary` - Secondary text (#9ca3af)
- `text-muted` - De-emphasized text (#6b7280)

### Components

**Card:**
```tsx
<Card title="Title" action={<button>Action</button>}>
  Content
</Card>
```

**CardSkeleton:**
Loading state for cards with animated bars.

**CardError:**
Error state displaying error message with icon.

### Utilities

**Format Functions** (`utils/format.ts`):
- `formatTimestamp(ts)` - Format ISO timestamp to IST
- `formatTime(ts)` - Format to time only (HH:MM:SS)
- `formatCurrency(value)` - Format as ₹X,XXX.XX
- `formatNumber(value, decimals)` - Format number with decimals
- `formatPercent(value)` - Format as percentage
- `getPnlClass(value)` - Get CSS class for P&L (pnl-positive/pnl-negative)
- `getPnlPrefix(value)` - Get '+' prefix for positive values

## API Integration

### React Query Configuration
```typescript
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 1000,
    },
  },
});
```

### Refetch Intervals
- Meta/market status: 2s
- Engines status: 3s
- Portfolio summary: 3s
- Open positions: 3s
- Recent signals: 2s
- Recent orders: 3s
- Orders: 5s
- Logs: 2s
- Strategy stats: 10s
- Equity curve: 10s

### Custom Hooks
All API calls are wrapped in custom hooks in `hooks/useApi.ts`:
```typescript
const { data, isLoading, error } = usePortfolioSummary();
```

## Features

### Connection Status Indicator
- Shows green pulsing dot when connected
- Turns red when no successful API calls in 15s
- Located in TopBar next to mode badge

### Dynamic Page Title
TopBar shows current page name based on route.

### Auto-scroll Logs
- Logs auto-scroll when "Follow Logs" is enabled
- Auto-follow disables on manual scroll up
- Click "Follow Logs" button to resume

### Responsive Layout
- Sidebar navigation
- Fixed TopBar with system info
- Scrollable content area
- Grid layouts adapt to screen size

### Error Handling
All pages gracefully handle:
- Loading states (skeletons)
- Error states (error cards)
- Empty states (friendly messages)

## Development

### Install Dependencies
```bash
cd ui/frontend
npm install
```

### Development Server
```bash
npm run dev
```
Runs on `http://localhost:3000` with API proxy to `http://localhost:9000`.

### Build for Production
```bash
npm run build
```
Output: `ui/static-react/` (served by FastAPI at root)

### Lint
```bash
npm run lint
```

## Future Enhancements

### Planned Features (Placeholders Added)
1. **Strategy Lab** - Enable/disable strategies, adjust parameters, backtest
2. **Risk Alerts** - Real-time limit breach notifications
3. **Advanced Analytics** - Correlation analysis, VaR calculations
4. **Benchmark Comparison** - Compare equity curve vs NIFTY/BANKNIFTY
5. **Trade History** - Detailed closed positions with exit analysis
6. **Keyboard Shortcuts** - Quick navigation (1-8 for tabs, Ctrl+L for logs)
7. **Command Palette** - Quick search for actions and pages

### Required Backend APIs
```
# Analytics
GET /api/benchmarks
GET /api/analytics/strategies

# Risk
GET /api/risk/limits
GET /api/risk/breaches
GET /api/risk/var

# Strategies
POST /api/strategies/{id}/enable
POST /api/strategies/{id}/disable
PUT  /api/strategies/{id}/params
POST /api/strategies/{id}/backtest

# Positions
GET /api/positions/closed?limit=50
```

## Deployment

The dashboard is integrated with the FastAPI server:
1. Build the React app: `npm run build` (or use `build-dashboard.sh`)
2. Start FastAPI: `python -m uvicorn apps.server:app --host 0.0.0.0 --port 9000`
3. Access at: `http://localhost:9000`

The server serves the React build at `/` and proxies API calls to `/api/*`.

## Best Practices

1. **Always use TypeScript types** from `types/api.ts`
2. **Use React Query hooks** from `hooks/useApi.ts` for data fetching
3. **Handle loading, error, and empty states** in every component
4. **Format values consistently** using `utils/format.ts`
5. **Follow Tailwind conventions** - use theme colors, not arbitrary values
6. **Keep components focused** - one responsibility per component
7. **Add error boundaries** for production resilience

## Troubleshooting

### Build fails with "Cannot find module"
- Run `npm install` to ensure dependencies are installed
- Check that all imports use correct paths

### API calls fail
- Ensure FastAPI server is running on port 9000
- Check network tab in browser DevTools
- Verify CORS settings in FastAPI

### Styling issues
- Clear browser cache
- Rebuild: `npm run build`
- Check Tailwind config for custom colors

### Logs not auto-scrolling
- Check "Follow Logs" button is enabled
- Scroll to bottom manually to re-enable auto-follow
- Verify logs are updating (check timestamp)
