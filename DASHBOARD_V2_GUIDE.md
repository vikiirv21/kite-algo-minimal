# Dashboard V2 - User Guide

## Quick Start

### Starting the Dashboard

```bash
# From project root
cd kite-algo-minimal

# Start the dashboard
python -m uvicorn ui.dashboard:app --host 127.0.0.1 --port 8765 --reload
```

Or using the full server:

```bash
python -m apps.server
```

### Accessing the Dashboard

Open your browser and navigate to:
```
http://localhost:8765
```

## Dashboard Overview

### Top Bar

The top bar displays critical real-time information:

1. **Dashboard Title:** "Arthayukti Algo Dashboard"
2. **Server Time:** Updates every second (🕒 HH:MM:SS)
3. **Market Status:** Shows OPEN/CLOSED with color-coded badge
4. **Mode Indicator:** Shows PAPER or LIVE mode

### Left Sidebar Navigation

The sidebar contains 10 navigation items:

1. **📊 Overview** - Dashboard summary and equity curve
2. **💼 Portfolio** - Open positions and portfolio details
3. **⚙️ Engines** - Engine status and health
4. **📈 Strategies** - Strategy performance metrics
5. **📋 Orders** - Recent orders (last 40)
6. **📡 Signals** - Recent signals (last 40)
7. **💰 PnL Analytics** - Profit & Loss analysis
8. **📄 Logs** - Engine logs (last 150)
9. **🔄 Trade Flow** - Trade flow metrics
10. **❤️ System Health** - Configuration and health status

## Page Details

### 1. Overview Page

**Purpose:** High-level summary of trading activity

**Sections:**
- **Today's Summary:** Realized PnL, trades count, win rate, avg R
- **Portfolio:** Equity, unrealized PnL, exposure, positions
- **Engines Status:** Engine running status and last checkpoint
- **Equity Curve:** 30-day equity chart

**Refresh Rate:** 10-60s depending on section

### 2. Portfolio Page

**Purpose:** View all open positions

**Sections:**
- **Open Positions Table:** Symbol, Qty, Avg Price, LTP, Realized/Unrealized PnL, Strategy

**Refresh Rate:** 5s (real-time updates)

**Features:**
- Color-coded PnL (green = profit, red = loss)
- Shows "No open positions" when empty

### 3. Engines Page

**Purpose:** Monitor engine health and status

**Sections:**
- **Engine Details:** Running status, mode, market status, checkpoint info

**Refresh Rate:** 10s

**Information Shown:**
- Engine name (e.g., fno_paper)
- Running status (RUNNING/STOPPED)
- Last checkpoint timestamp
- Checkpoint age in seconds
- Any errors

### 4. Strategies Page

**Purpose:** Track strategy performance

**Sections:**
- **Strategy Performance Table:** Name, PnL, Wins, Losses, Win Rate, Entries, Exits

**Refresh Rate:** 15s

**Features:**
- Win rate calculation
- Color-coded PnL
- Entry/exit counts

### 5. Orders Page

**Purpose:** View recent order history

**Sections:**
- **Recent Orders:** Last 40 orders with time, symbol, side, qty, price, status, strategy

**Refresh Rate:** 3s (fast updates)

**Features:**
- Scrollable table
- Color-coded side (BUY = green, SELL = red)
- Status badges
- Shows "No orders yet" when empty

### 6. Signals Page

**Purpose:** Monitor trading signals

**Sections:**
- **Recent Signals:** Last 40 signals with time, symbol, signal type, price, timeframe, strategy

**Refresh Rate:** 3s (fast updates)

**Features:**
- Color-coded signals (BUY = green, SELL = red, HOLD = neutral)
- Scrollable table
- Real-time updates

### 7. PnL Analytics Page

**Purpose:** Detailed profit & loss analysis

**Sections:**
- **Today's Performance:** Realized PnL, trades, win/loss stats, largest win/loss
- **Portfolio PnL:** Total equity, realized/unrealized PnL, daily PnL
- **Equity Curve:** 7-day equity chart

**Refresh Rate:** 10-60s

**Features:**
- Comprehensive PnL breakdown
- Visual equity curve
- Win rate and R-multiple tracking

### 8. Logs Page

**Purpose:** View engine logs

**Sections:**
- **Recent Logs:** Last 150 engine log entries

**Refresh Rate:** 5s

**Features:**
- Color-coded log levels (INFO = gray, WARNING = yellow, ERROR = red)
- Auto-scroll to bottom
- Scrollable container
- Monospace font for readability

### 9. Trade Flow Page

**Purpose:** Monitor trade execution funnel

**Sections:**
- **Trade Flow Metrics:** Signals seen, evaluated, allowed, vetoed, orders placed/filled

**Refresh Rate:** 3s

**Features:**
- Real-time funnel metrics
- Shows trade execution pipeline

### 10. System Health Page

**Purpose:** Monitor system configuration and health

**Sections:**
- **Configuration:** Mode, capital, risk settings, exposure limits
- **Health Status:** Engine health, log health, market status

**Refresh Rate:** 15-30s

**Features:**
- Config summary with risk profile
- Engine health indicators
- Recent error/warning counts
- Market status

## Features

### Real-Time Updates

The dashboard uses HTMX for automatic updates:
- **Topbar:** Server time updates every second
- **Fast Data:** Orders, signals, logs update every 3-5 seconds
- **Medium Data:** Portfolio, engines update every 10-15 seconds
- **Slow Data:** Config, health update every 30-60 seconds

### Visual Feedback

- **Color Coding:** 
  - Green = positive/profit/buy
  - Red = negative/loss/sell
  - Gray/neutral = hold/closed
- **Badges:** Status indicators with appropriate colors
- **Loading States:** Shows "Loading..." while fetching data
- **Empty States:** Shows appropriate messages when no data

### Navigation

- Click any sidebar item to switch pages
- Active page is highlighted in the sidebar
- Navigation is instant (no page reload)
- Previous page data is cleared on navigation

## API Endpoints Used

The dashboard communicates with these backend endpoints:

- `/api/system/time` - Server time
- `/api/engines/status` - Engine status
- `/api/summary/today` - Today's summary
- `/api/portfolio/summary` - Portfolio data
- `/api/orders/recent?limit=40` - Recent orders
- `/api/signals/recent?limit=40` - Recent signals
- `/api/logs?limit=150&kind=engine` - Engine logs
- `/api/monitor/trade_flow` - Trade flow
- `/api/strategy_performance` - Strategy stats
- `/api/config/summary` - Configuration
- `/api/stats/equity?days=N` - Equity curve
- `/api/meta` - Market metadata
- `/api/health` - System health
- `/api/positions/open` - Open positions

## Troubleshooting

### Dashboard Not Loading

1. Check if server is running: `ps aux | grep uvicorn`
2. Check port is not in use: `lsof -i :8765`
3. Check logs: `tail -f artifacts/logs/app.log`

### Data Not Updating

1. Check browser console for errors (F12)
2. Verify API endpoints are accessible: `curl http://localhost:8765/api/system/time`
3. Check HTMX is loaded (check browser Network tab)

### HTMX Not Loading

If HTMX CDN is blocked:
1. Download HTMX from https://unpkg.com/htmx.org@1.9.10
2. Save to `ui/static/js/htmx.min.js`
3. Update `base.html` to use local file

### Slow Performance

1. Check polling intervals are not too aggressive
2. Check backend API response times
3. Clear browser cache
4. Check network connection

## Best Practices

1. **Keep Browser Tab Active:** Some browsers throttle inactive tabs
2. **Use Modern Browser:** Chrome/Edge 90+ recommended
3. **Monitor Console:** Check for JavaScript errors
4. **Refresh on Issues:** F5 to reload if dashboard seems stuck

## Technical Notes

### Architecture

- **Frontend:** HTML + CSS + JavaScript + HTMX
- **Backend:** FastAPI + Jinja2
- **Communication:** REST APIs with JSON responses
- **Updates:** HTMX polling with configurable intervals

### File Structure

```
ui/
├── templates/
│   ├── base.html              # Main layout
│   ├── layout/                # Reusable components
│   └── pages/                 # Individual pages
└── static/
    ├── css/dashboard.css      # Styling
    └── js/dashboard.js        # JavaScript utilities
```

### Customization

To customize polling intervals, edit the `hx-trigger` attributes in page templates:

```html
<!-- Fast update (3s) -->
<div hx-get="/api/orders/recent?limit=40" hx-trigger="load, every 3s">

<!-- Medium update (15s) -->
<div hx-get="/api/portfolio/summary" hx-trigger="load, every 15s">

<!-- Slow update (60s) -->
<div hx-get="/api/stats/equity?days=30" hx-trigger="load, every 60s">
```

## Support

For issues or questions:
1. Check validation report: `DASHBOARD_V2_VALIDATION.md`
2. Check server logs: `artifacts/logs/`
3. Review API documentation in backend code

---

**Dashboard V2** - Modern, Fast, Production-Ready
