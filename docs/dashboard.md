# Dashboard Documentation – kite-algo-minimal

> **Status**: CURRENT – Last updated: 2025-11-19  
> **Purpose**: Complete dashboard API and UI documentation

---

## Table of Contents

1. [Dashboard Overview](#dashboard-overview)
2. [Architecture](#architecture)
3. [Quick Start](#quick-start)
4. [API Endpoints](#api-endpoints)
5. [Frontend Pages](#frontend-pages)
6. [Real-Time Updates](#real-time-updates)
7. [Development](#development)
8. [Troubleshooting](#troubleshooting)

---

## Dashboard Overview

The kite-algo-minimal dashboard is a **modern, real-time web interface** for monitoring and controlling the trading system.

### Key Features

- **7 Pages**: Overview, Trading, Portfolio, Signals, Analytics, System, Logs
- **Real-time Updates**: Auto-polling with React Query (1-5s intervals)
- **Dark Theme**: Professional futuristic design with Tailwind CSS
- **Live Metrics**: P&L, positions, orders, signals with color coding
- **Log Viewer**: Filterable engine logs with auto-scroll
- **Charts**: Equity curve visualization with Recharts
- **Responsive**: Works on desktop, tablet, and mobile

### Tech Stack

**Backend**:
- FastAPI (Python async web framework)
- Uvicorn (ASGI server)
- Pydantic (data validation)

**Frontend**:
- React 18 (UI framework)
- TypeScript (type safety)
- Tailwind CSS (styling)
- React Query (data fetching, caching, auto-polling)
- React Router (navigation)
- Recharts (charting)

---

## Architecture

```
┌─────────────────────────────────────────────┐
│         Browser (React Frontend)            │
│  ┌────────┬────────┬─────────┬──────────┐  │
│  │Overview│Trading │Portfolio│ Signals  │  │
│  ├────────┼────────┼─────────┼──────────┤  │
│  │Analytics│System │  Logs   │          │  │
│  └────────┴────────┴─────────┴──────────┘  │
└──────────────────┬──────────────────────────┘
                   │ HTTP/REST API
                   │ (React Query polling 1-5s)
                   │
┌──────────────────▼──────────────────────────┐
│       FastAPI Server (apps/server.py)       │
│  ┌──────────────────────────────────────┐  │
│  │  REST API Endpoints                  │  │
│  │  - /api/state                        │  │
│  │  - /api/positions                    │  │
│  │  - /api/orders                       │  │
│  │  - /api/signals                      │  │
│  │  - /api/logs                         │  │
│  │  - /api/analytics/*                  │  │
│  └──────────────────────────────────────┘  │
└──────────────────┬──────────────────────────┘
                   │
      ┌────────────┼────────────┐
      │            │            │
      ▼            ▼            ▼
┌──────────┐ ┌──────────┐ ┌──────────┐
│ Equity   │ │   FnO    │ │ Options  │
│ Engine   │ │ Engine   │ │ Engine   │
└────┬─────┘ └────┬─────┘ └────┬─────┘
     │            │            │
     └────────────┼────────────┘
                  │
                  ▼
           ┌──────────────┐
           │  Artifacts/  │
           │ - state.json │
           │ - orders.csv │
           │ - logs/      │
           └──────────────┘
```

---

## Quick Start

### 1. Build Frontend (First Time Only)

```bash
./build-dashboard.sh
```

This script:
- Installs npm dependencies
- Builds React app for production
- Copies build to `static/` directory

**Output**: `static/` directory with `index.html`, `assets/`, etc.

### 2. Start Server

```bash
# Start FastAPI server
python -m uvicorn apps.server:app --host 0.0.0.0 --port 9000

# With auto-reload (development)
python -m uvicorn apps.server:app --host 0.0.0.0 --port 9000 --reload
```

### 3. Access Dashboard

Open browser: **http://localhost:9000**

Default port: **9000**

---

## API Endpoints

### Core State Endpoints

#### GET /api/state

**Purpose**: Get current trading session state

**Response**:
```json
{
  "mode": "paper",
  "session_id": "2025-11-19-equity-paper",
  "portfolio": {
    "equity": 500000.0,
    "realized_pnl": 1250.50,
    "unrealized_pnl": -320.00,
    "total_pnl": 930.50,
    "exposure": 245000.00,
    "margin_used": 0.0
  },
  "positions_count": 3,
  "orders_count": 25,
  "market_open": true,
  "last_updated": "2025-11-19T14:30:00+05:30"
}
```

**Polling**: 1 second

#### GET /api/positions

**Purpose**: Get all open positions

**Response**:
```json
{
  "positions": [
    {
      "symbol": "RELIANCE",
      "qty": 10,
      "avg_price": 2450.25,
      "ltp": 2462.00,
      "unrealized_pnl": 117.50,
      "pnl_pct": 0.48,
      "side": "LONG"
    },
    {
      "symbol": "TCS",
      "qty": 5,
      "avg_price": 3520.00,
      "ltp": 3515.00,
      "unrealized_pnl": -25.00,
      "pnl_pct": -0.14,
      "side": "LONG"
    }
  ],
  "count": 2
}
```

**Polling**: 2 seconds

#### GET /api/orders

**Purpose**: Get all orders with optional filtering

**Query Parameters**:
- `status`: Filter by status (FILLED, PENDING, CANCELLED, REJECTED)
- `symbol`: Filter by symbol
- `strategy`: Filter by strategy
- `limit`: Max results (default: 100)

**Response**:
```json
{
  "orders": [
    {
      "order_id": "uuid-123",
      "timestamp": "2025-11-19T09:30:15+05:30",
      "symbol": "RELIANCE",
      "side": "BUY",
      "qty": 10,
      "order_type": "MARKET",
      "status": "FILLED",
      "filled_qty": 10,
      "avg_fill_price": 2450.25,
      "strategy": "EMA_20_50",
      "reason": "EMA crossover up"
    }
  ],
  "count": 25,
  "filtered_count": 1
}
```

**Polling**: 2 seconds

#### GET /api/signals

**Purpose**: Get recent strategy signals

**Query Parameters**:
- `signal`: Filter by signal type (BUY, SELL, EXIT, HOLD)
- `strategy`: Filter by strategy
- `limit`: Max results (default: 50)

**Response**:
```json
{
  "signals": [
    {
      "timestamp": "2025-11-19T09:30:00+05:30",
      "symbol": "RELIANCE",
      "signal": "BUY",
      "strategy": "EMA_20_50",
      "confidence": 0.75,
      "reason": "EMA 20 crossed above EMA 50",
      "price": 2450.25
    }
  ],
  "count": 48
}
```

**Polling**: 3 seconds

#### GET /api/logs

**Purpose**: Get engine logs with filtering

**Query Parameters**:
- `level`: Filter by log level (INFO, WARNING, ERROR)
- `category`: Filter by category (engine, trades, signals, risk)
- `limit`: Max results (default: 100)

**Response**:
```json
{
  "logs": [
    {
      "timestamp": "2025-11-19T09:30:15",
      "level": "INFO",
      "logger": "engine.equity_paper",
      "message": "Placed BUY order for RELIANCE @ 2450.25",
      "category": "trades"
    }
  ],
  "count": 156
}
```

**Polling**: 5 seconds

### Analytics Endpoints

#### GET /api/analytics/summary

**Purpose**: Get performance summary

**Response**:
```json
{
  "total_pnl": 1250.50,
  "realized_pnl": 1100.00,
  "unrealized_pnl": 150.50,
  "win_rate": 0.65,
  "profit_factor": 2.15,
  "sharpe_ratio": 1.42,
  "max_drawdown": -850.00,
  "max_drawdown_pct": -0.17,
  "total_trades": 20,
  "winning_trades": 13,
  "losing_trades": 7,
  "avg_win": 180.50,
  "avg_loss": -85.20
}
```

**Polling**: 10 seconds

#### GET /api/analytics/equity_curve

**Purpose**: Get equity curve data for charting

**Response**:
```json
{
  "equity_curve": [
    {"timestamp": "2025-11-19T09:15:00", "equity": 500000.00},
    {"timestamp": "2025-11-19T09:30:00", "equity": 500117.50},
    {"timestamp": "2025-11-19T10:00:00", "equity": 500342.00},
    ...
  ],
  "start_equity": 500000.00,
  "end_equity": 501250.50,
  "peak_equity": 501500.00
}
```

**Polling**: 30 seconds

### System Endpoints

#### GET /api/engines/status

**Purpose**: Get engine health and status

**Response**:
```json
{
  "engines": [
    {
      "name": "equity_paper",
      "status": "running",
      "uptime_seconds": 18000,
      "last_tick": "2025-11-19T14:30:00+05:30",
      "symbols_tracked": 95,
      "orders_placed": 25
    },
    {
      "name": "fno_paper",
      "status": "running",
      "uptime_seconds": 18000,
      "last_tick": "2025-11-19T14:30:00+05:30",
      "symbols_tracked": 3,
      "orders_placed": 10
    }
  ]
}
```

**Polling**: 5 seconds

#### GET /api/health

**Purpose**: System health check

**Response**:
```json
{
  "status": "healthy",
  "timestamp": "2025-11-19T14:30:00+05:30",
  "components": {
    "api_server": "ok",
    "kite_token": "valid",
    "equity_engine": "running",
    "fno_engine": "running",
    "options_engine": "stopped"
  }
}
```

**Polling**: 10 seconds

### Admin Endpoints

#### POST /admin/login

**Purpose**: Kite login (generate access token)

**Request Body**:
```json
{
  "request_token": "abc123..."
}
```

**Response**:
```json
{
  "success": true,
  "access_token": "xyz789...",
  "message": "Login successful"
}
```

#### POST /admin/mode

**Purpose**: Switch runtime mode (paper/live)

**Request Body**:
```json
{
  "mode": "paper"
}
```

**Response**:
```json
{
  "success": true,
  "mode": "paper",
  "message": "Mode switched to paper"
}
```

#### POST /admin/start

**Purpose**: Start trading engines

**Response**:
```json
{
  "success": true,
  "message": "Engines started"
}
```

#### POST /admin/stop

**Purpose**: Stop trading engines

**Response**:
```json
{
  "success": true,
  "message": "Engines stopped"
}
```

### Complete Endpoint List

| Endpoint | Method | Purpose | Polling |
|----------|--------|---------|---------|
| `/` | GET | Serve React app | N/A |
| `/api/state` | GET | Session state | 1s |
| `/api/positions` | GET | Open positions | 2s |
| `/api/orders` | GET | All orders | 2s |
| `/api/signals` | GET | Strategy signals | 3s |
| `/api/logs` | GET | Engine logs | 5s |
| `/api/logs/tail` | GET | Recent logs (streaming) | N/A |
| `/api/analytics/summary` | GET | Performance summary | 10s |
| `/api/analytics/equity_curve` | GET | Equity curve | 30s |
| `/api/engines/status` | GET | Engine status | 5s |
| `/api/health` | GET | Health check | 10s |
| `/api/portfolio/summary` | GET | Portfolio summary | 2s |
| `/api/stats/strategies` | GET | Strategy performance | 10s |
| `/api/risk/summary` | GET | Risk metrics | 10s |
| `/api/market/context` | GET | Market context | 30s |
| `/admin/login` | POST | Kite login | N/A |
| `/admin/mode` | POST | Switch mode | N/A |
| `/admin/start` | POST | Start engines | N/A |
| `/admin/stop` | POST | Stop engines | N/A |

---

## Frontend Pages

### 1. Overview Page

**Route**: `/`

**Purpose**: High-level portfolio summary

**Displays**:
- Total equity
- Realized P&L (today)
- Unrealized P&L (current positions)
- Total P&L (realized + unrealized)
- Win rate
- Open positions count
- Orders count (today)
- Market status (open/closed)

**Layout**:
```
┌─────────────┬─────────────┬─────────────┬─────────────┐
│   Equity    │ Realized PnL│Unrealized PnL│  Total PnL  │
│  ₹500,000   │   +₹1,250   │    -₹320    │   +₹930     │
└─────────────┴─────────────┴─────────────┴─────────────┘

┌─────────────────────────────────────────────────────────┐
│  Positions: 3 open                                       │
│  Orders: 25 today                                        │
│  Market: OPEN (09:15 - 15:30)                           │
└─────────────────────────────────────────────────────────┘
```

**Polling**: 1 second

### 2. Trading Page

**Route**: `/trading`

**Purpose**: Real-time position tracking

**Displays**:
- All open positions with live P&L
- Symbol, quantity, avg price, LTP
- Unrealized P&L (absolute and %)
- Color coding: Green (profit), Red (loss)
- Side indicator (LONG/SHORT)

**Table**:
```
┌────────┬─────┬──────────┬──────────┬──────────┬────────┐
│ Symbol │ Qty │ Avg Price│   LTP    │  Unreal  │  %     │
├────────┼─────┼──────────┼──────────┼──────────┼────────┤
│RELIANCE│  10 │ 2,450.25 │ 2,462.00 │ +₹117.50 │ +0.48% │
│  TCS   │   5 │ 3,520.00 │ 3,515.00 │  -₹25.00 │ -0.14% │
│  INFY  │  20 │ 1,450.50 │ 1,455.00 │  +₹90.00 │ +0.31% │
└────────┴─────┴──────────┴──────────┴──────────┴────────┘
```

**Features**:
- Auto-refresh every 2 seconds
- Click row to see position details
- Sort by symbol, P&L, %

**Polling**: 2 seconds

### 3. Portfolio Page

**Route**: `/portfolio`

**Purpose**: Detailed portfolio analysis

**Displays**:
- Position allocation pie chart
- Exposure by symbol
- Risk metrics (max drawdown, Sharpe ratio)
- Capital allocation by strategy

**Sections**:
1. **Allocation Chart**: Pie chart of positions
2. **Exposure Table**: Notional value per position
3. **Risk Metrics**: Drawdown, volatility, Sharpe
4. **Strategy Budgets**: Capital allocated per strategy

**Polling**: 5 seconds

### 4. Signals Page

**Route**: `/signals`

**Purpose**: Recent strategy signals

**Displays**:
- All signals generated today
- Signal type (BUY/SELL/EXIT/HOLD)
- Confidence score (0.0 to 1.0)
- Strategy name
- Reason/explanation

**Table**:
```
┌──────────┬────────┬────────┬──────────┬────────────┬─────────────────┐
│   Time   │ Symbol │ Signal │ Strategy │ Confidence │     Reason      │
├──────────┼────────┼────────┼──────────┼────────────┼─────────────────┤
│09:30:00  │RELIANCE│  BUY   │EMA_20_50 │    0.75    │EMA crossover up │
│09:31:30  │  TCS   │  HOLD  │EMA_20_50 │    0.40    │No clear trend   │
└──────────┴────────┴────────┴──────────┴────────────┴─────────────────┘
```

**Filters**:
- Signal type (BUY/SELL/EXIT/HOLD)
- Strategy
- Confidence threshold

**Polling**: 3 seconds

### 5. Analytics Page

**Route**: `/analytics`

**Purpose**: Performance visualization

**Displays**:
- Equity curve chart
- Performance metrics
- Trade statistics
- Win/loss distribution

**Charts**:
1. **Equity Curve**: Line chart of portfolio value over time
2. **Drawdown Chart**: Underwater plot showing drawdowns
3. **Trade Distribution**: Histogram of P&L per trade

**Metrics**:
- Total P&L
- Win rate
- Profit factor
- Sharpe ratio
- Max drawdown
- Calmar ratio

**Polling**: 30 seconds

### 6. System Page

**Route**: `/system`

**Purpose**: Engine health monitoring

**Displays**:
- Engine status (running/stopped)
- Uptime
- Last tick timestamp
- Symbols tracked
- Orders placed today

**Table**:
```
┌──────────────┬─────────┬─────────┬───────────┬────────┐
│    Engine    │ Status  │ Uptime  │ Symbols   │ Orders │
├──────────────┼─────────┼─────────┼───────────┼────────┤
│equity_paper  │ RUNNING │  5h 0m  │    95     │   25   │
│fno_paper     │ RUNNING │  5h 0m  │     3     │   10   │
│options_paper │ STOPPED │   0m    │     0     │    0   │
└──────────────┴─────────┴─────────┴───────────┴────────┘
```

**Health Indicators**:
- 🟢 Green: Healthy
- 🟡 Yellow: Warning
- 🔴 Red: Error

**Polling**: 5 seconds

### 7. Logs Page

**Route**: `/logs`

**Purpose**: Real-time log viewer

**Displays**:
- Recent log entries (last 100)
- Log level (INFO/WARNING/ERROR)
- Timestamp
- Logger name
- Message

**Features**:
- Auto-scroll to bottom
- Filter by level (INFO/WARNING/ERROR)
- Filter by category (engine/trades/signals/risk)
- Search by text
- Pause/resume auto-refresh

**Example**:
```
[09:30:15] [INFO] engine.equity_paper: Evaluating RELIANCE
[09:30:16] [INFO] strategy.ema_20_50: BUY signal, confidence=0.75
[09:30:17] [INFO] execution.paper: Placed order uuid-123
[09:30:18] [INFO] execution.paper: Order FILLED @ 2450.25
```

**Polling**: 5 seconds (with pause button)

---

## Real-Time Updates

### Polling Strategy

The dashboard uses **React Query** for intelligent polling:

| Data Type | Polling Interval | Rationale |
|-----------|------------------|-----------|
| Portfolio state | 1s | Critical for real-time P&L |
| Positions | 2s | Frequent enough for monitoring |
| Orders | 2s | Need to see order status quickly |
| Signals | 3s | Less critical than positions |
| Logs | 5s | Balance between freshness and load |
| Analytics | 30s | Expensive to compute, changes slowly |

### React Query Configuration

```typescript
// Example: Portfolio query with 1s polling
const { data: portfolio } = useQuery({
  queryKey: ['portfolio'],
  queryFn: fetchPortfolio,
  refetchInterval: 1000,    // Poll every 1 second
  staleTime: 500,           // Consider stale after 0.5s
  cacheTime: 5000,          // Cache for 5 seconds
})
```

### Future: WebSocket Support

**Planned Enhancement**: Replace polling with WebSocket push updates

**Benefits**:
- True real-time updates (sub-second latency)
- Lower server load (no polling overhead)
- Efficient bandwidth usage

**Implementation**:
```python
# Server-side (FastAPI WebSocket)
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        # Push updates when state changes
        if state_changed():
            await websocket.send_json(get_state())
        await asyncio.sleep(0.1)
```

---

## Development

### Frontend Development

**Directory**: `ui/frontend/`

**Install Dependencies**:
```bash
cd ui/frontend
npm install
```

**Run Dev Server**:
```bash
npm run dev
# Opens http://localhost:5173 (Vite dev server)
```

**Build for Production**:
```bash
npm run build
# Outputs to ui/frontend/dist/
```

**Copy to Static**:
```bash
./build-dashboard.sh
# Copies dist/ to static/
```

### Backend Development

**File**: `apps/server.py`, `ui/dashboard.py`

**Run with Auto-Reload**:
```bash
python -m uvicorn apps.server:app --host 0.0.0.0 --port 9000 --reload
```

**Add New Endpoint**:
```python
# In ui/dashboard.py or apps/server.py

@router.get("/api/new_endpoint")
def new_endpoint() -> JSONResponse:
    data = {"key": "value"}
    return JSONResponse(content=data)
```

**Testing**:
```bash
# Test endpoint
curl http://localhost:9000/api/new_endpoint

# Or use httpie
http http://localhost:9000/api/new_endpoint
```

### Project Structure

```
ui/
├── frontend/                # React app
│   ├── src/
│   │   ├── pages/          # 7 page components
│   │   ├── components/     # Reusable UI components
│   │   ├── services/       # API client
│   │   ├── hooks/          # Custom React hooks
│   │   └── App.tsx         # Main app
│   ├── public/
│   └── package.json
├── dashboard.py            # Backend routes
├── templates/              # Legacy Jinja2 templates
└── static/                 # Built React app (static files)

apps/
├── server.py               # FastAPI server entry point
└── dashboard.py            # Dashboard routes (legacy)

static/                     # Served at /
├── index.html
└── assets/
```

---

## Troubleshooting

### Dashboard Won't Load

**Symptoms**: Blank page or 404 errors

**Solutions**:
1. Build frontend:
   ```bash
   ./build-dashboard.sh
   ```
2. Check static files exist:
   ```bash
   ls -la static/index.html
   ```
3. Restart server:
   ```bash
   python -m uvicorn apps.server:app --host 0.0.0.0 --port 9000
   ```

### API Errors (500/502)

**Symptoms**: API calls fail with server errors

**Solutions**:
1. Check server logs:
   ```bash
   tail -f artifacts/logs/server.log
   ```
2. Check artifacts exist:
   ```bash
   ls -la artifacts/checkpoints/runtime_state_latest.json
   ```
3. Verify engines are running:
   ```bash
   ps aux | grep python
   ```

### Stale Data

**Symptoms**: Dashboard shows old data

**Solutions**:
1. Hard refresh: Ctrl+Shift+R (Chrome) or Cmd+Shift+R (Mac)
2. Clear browser cache
3. Check polling is working (open DevTools → Network tab)

### Missing Logs

**Symptoms**: Log page is empty

**Solutions**:
1. Check log files exist:
   ```bash
   ls -la artifacts/logs/
   ```
2. Check log path in server.py:
   ```python
   LOG_DIR = ARTIFACTS_ROOT / "logs"
   ```
3. Verify engines are writing logs

---

## Related Documentation

- **[REPO_OVERVIEW.md](./REPO_OVERVIEW.md)**: Repository overview
- **[ARCHITECTURE.md](./ARCHITECTURE.md)**: System architecture
- **[MODULES.md](./MODULES.md)**: Module reference
- **[ENGINES.md](./ENGINES.md)**: Engine documentation
- **[STRATEGIES.md](./STRATEGIES.md)**: Strategy guide
- **[RUNBOOKS.md](./RUNBOOKS.md)**: Operational runbook

---

**Last Updated**: 2025-11-19  
**Version**: 1.0
