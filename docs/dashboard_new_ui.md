# React Dashboard - Arthayukti HFT Control Panel

## Overview

This is a modern React-based single-page application (SPA) that replaces the old vanilla JavaScript dashboard. Built with:

- **Vite** - Fast build tool
- **React + TypeScript** - Type-safe component architecture
- **Tailwind CSS** - Utility-first styling with dark theme
- **React Router** - Client-side routing
- **React Query (TanStack Query)** - Data fetching and caching
- **Recharts** - Chart visualization

## Directory Structure

```
ui/frontend/
├── src/
│   ├── api/          # API client and fetch utilities
│   │   └── client.ts
│   ├── components/   # Reusable UI components
│   │   ├── Card.tsx
│   │   ├── Sidebar.tsx
│   │   └── TopBar.tsx
│   ├── features/     # Feature-specific pages
│   │   ├── overview/
│   │   ├── trading/
│   │   ├── portfolio/
│   │   ├── signals/
│   │   ├── analytics/
│   │   ├── system/
│   │   └── logs/
│   ├── hooks/        # Custom React hooks
│   │   └── useApi.ts # React Query hooks for API calls
│   ├── types/        # TypeScript type definitions
│   │   └── api.ts
│   ├── utils/        # Utility functions
│   │   └── format.ts # Formatting helpers
│   ├── App.tsx       # Main app component with routing
│   ├── main.tsx      # App entry point
│   └── index.css     # Global styles + Tailwind imports
├── package.json
├── tsconfig.json
├── tailwind.config.js
└── vite.config.ts
```

## Features

### Pages

1. **Overview** (`/`)
   - Engine status (paper/live)
   - Portfolio snapshot
   - Today's trading summary
   - Risk budget usage
   - Recent signals stream

2. **Trading** (`/trading`)
   - Active orders table
   - Recent/completed orders
   - Real-time updates (3s polling)

3. **Portfolio** (`/portfolio`)
   - Portfolio summary (equity, P&L, exposure)
   - Open positions table
   - P&L coloring (green/red)
   - Real-time price updates

4. **Signals** (`/signals`)
   - Active strategies list
   - Signal stream with filtering
   - Strategy performance metrics

5. **Analytics** (`/analytics`)
   - Equity curve chart
   - Benchmark comparison placeholder
   - Per-strategy performance placeholder

6. **System** (`/system`)
   - System information
   - Configuration summary
   - Raw config JSON viewer

7. **Logs** (`/logs`)
   - Engine logs with syntax highlighting
   - Level filtering (ALL/INFO/WARNING/ERROR/DEBUG)
   - Category filtering (engine/trades/signals/system)
   - Auto-scroll functionality
   - Manual scroll detection

### API Integration

All API calls are handled through React Query with automatic:
- Polling intervals (1-5 seconds based on data type)
- Error handling
- Loading states
- Caching
- Refetch on window focus

### Styling

Dark theme with Tailwind CSS:
- Background: `#0a0e1a`
- Surface: `#121825`
- Primary: `#3b82f6` (blue)
- Positive: `#10b981` (green for profits)
- Negative: `#ef4444` (red for losses)
- Warning: `#f59e0b` (orange)

## Development

### Prerequisites

- Node.js 20.x or later
- npm 10.x or later

### Install Dependencies

```bash
cd ui/frontend
npm install
```

### Development Server

```bash
npm run dev
```

This starts a development server at `http://localhost:3000` with:
- Hot module replacement (HMR)
- API proxy to `http://localhost:9000`
- Fast refresh

### Build for Production

```bash
npm run build
```

This creates an optimized production build in `ui/static-react/`:
- Minified JavaScript and CSS
- Code splitting
- Asset optimization
- Cache-friendly filenames

### Type Checking

```bash
npm run type-check
```

## Integration with FastAPI

The FastAPI backend serves the React app:

1. Build the React app: `cd ui/frontend && npm run build`
2. The build output is created in `ui/static-react/`
3. FastAPI serves `index.html` at the root route `/`
4. Static assets are mounted at `/assets`

### FastAPI Changes

In `ui/dashboard.py`:

```python
REACT_BUILD_DIR = BASE_DIR / "ui" / "static-react"

@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """Serve React SPA"""
    react_index = REACT_BUILD_DIR / "index.html"
    if react_index.exists():
        return HTMLResponse(content=react_index.read_text())
    # Fallback to old dashboard if React build doesn't exist
    ...

# Mount React assets
app.mount("/assets", StaticFiles(directory=REACT_BUILD_DIR / "assets"))
```

## API Endpoints Used

The dashboard consumes the following FastAPI endpoints:

### Core
- `GET /api/meta` - Market status, server time
- `GET /api/config/summary` - Configuration summary
- `GET /api/auth/status` - Authentication status

### Trading
- `GET /api/engines/status` - Engine status
- `GET /api/orders?limit=150` - All orders
- `GET /api/orders/recent?limit=50` - Recent orders
- `GET /api/signals?limit=150` - All signals
- `GET /api/signals/recent?limit=50` - Recent signals

### Portfolio
- `GET /api/portfolio/summary` - Portfolio snapshot
- `GET /api/positions/open` - Open positions

### Analytics
- `GET /api/stats/strategies?days=1` - Strategy stats
- `GET /api/stats/equity?days=1` - Equity curve
- `GET /api/summary/today` - Today's trading summary

### Logs
- `GET /api/logs?limit=200&level=INFO&kind=engine` - Engine logs

## Missing Backend APIs (Placeholders)

The Analytics page shows placeholders for these missing endpoints:

### Benchmarks
```
GET /api/benchmarks
Returns:
[
  { ts: "2024-11-17T10:00:00+00:00", nifty: 19500, banknifty: 45000 },
  ...
]
```

### Strategy Performance
```
GET /api/analytics/strategies
Returns:
[
  {
    strategy: "ema_crossover",
    pnl: 5000,
    win_rate: 65.5,
    max_drawdown: -1200,
    avg_trade_pnl: 150,
    ...
  },
  ...
]
```

## Formatting Utilities

Located in `src/utils/format.ts`:

- `formatTimestamp(ts)` - Format ISO timestamp to IST
- `formatTime(ts)` - Format to time only (HH:MM:SS)
- `formatCurrency(value)` - Format as ₹1,234.56
- `formatNumber(value, decimals)` - Format with decimals
- `formatPercent(value)` - Format as percentage
- `getPnlClass(value)` - Get CSS class for P&L coloring
- `getPnlPrefix(value)` - Get + or - prefix

## Customization

### Add a New Page

1. Create page component in `src/features/<name>/<Name>Page.tsx`
2. Add route to `src/App.tsx`
3. Add navigation item to `src/components/Sidebar.tsx`

### Add a New API Endpoint

1. Add type to `src/types/api.ts`
2. Add API function to `src/api/client.ts`
3. Add React Query hook to `src/hooks/useApi.ts`
4. Use hook in your component

### Customize Theme

Edit `tailwind.config.js`:

```javascript
theme: {
  extend: {
    colors: {
      background: '#your-color',
      surface: '#your-color',
      // ...
    },
  },
}
```

## Troubleshooting

### Build Errors

**Problem**: `Cannot apply unknown utility class`

**Solution**: Make sure Tailwind CSS and PostCSS are properly configured. Check:
- `tailwind.config.js` exists
- `postcss.config.js` has `@tailwindcss/postcss`
- `index.css` imports Tailwind

### API Errors

**Problem**: 404 on API calls

**Solution**: 
- Check FastAPI is running on port 9000
- Check API endpoint paths match backend
- Check CORS is configured in FastAPI

### Stale Data

**Problem**: Dashboard shows old data

**Solution**: React Query has automatic refetch intervals. Check:
- Network connectivity
- Backend is running
- Check browser console for errors

## Production Deployment

1. Build the React app:
   ```bash
   cd ui/frontend
   npm run build
   ```

2. Start FastAPI server:
   ```bash
   python -m uvicorn apps.server:app --host 0.0.0.0 --port 9000
   ```

3. Access dashboard at `http://localhost:9000/`

## Performance

- Initial bundle size: ~620KB (gzipped: ~187KB)
- React Query caches API responses
- Automatic polling keeps data fresh
- Code splitting for faster initial loads
- Optimized images and assets

## Browser Support

- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

## Future Enhancements

- [ ] Add WebSocket support for real-time updates
- [ ] Implement dark/light theme toggle
- [ ] Add more chart types (candlestick, bar charts)
- [ ] Implement benchmark comparison charts
- [ ] Add per-strategy performance analytics
- [ ] Add trade history timeline
- [ ] Implement advanced filtering and search
- [ ] Add export to CSV functionality
- [ ] Mobile responsive improvements
- [ ] Add unit tests with Vitest
- [ ] Add E2E tests with Playwright
