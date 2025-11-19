# Frontend Dashboard

## Overview

The dashboard provides a web-based interface for monitoring and controlling the trading system in real-time.

## Dashboard Location

- **Main App**: `apps/dashboard.py`
- **Dashboard Logs**: `apps/dashboard_logs.py`
- **API Routes**: `apps/api_strategies.py`
- **Templates**: `ui/templates/ (if present)` 
- **Static Assets**: `ui/static/ (if present)`
- **UI Module**: `ui/`

## Architecture

The dashboard is built with:
- **Backend**: FastAPI (Python)
- **Frontend**: HTML templates (Jinja2) + JavaScript
- **Real-time Updates**: Server-Sent Events (SSE) for live data streaming
- **API**: RESTful endpoints for data and control

## Main Screens/Sections

### 1. Overview / Home
- System status and health
- Market hours indicator
- Active engines and their status
- Current P&L snapshot
- Recent alerts/notifications

### 2. Engines / Status
- Engine state (running, stopped, error)
- Active strategies
- Position counts
- Resource utilization

### 3. Signals
- Recent signals generated
- Signal quality metrics
- Strategy-specific signals
- Historical signal performance

### 4. Positions & Portfolio
- Current open positions
- Unrealized P&L
- Position sizing
- Entry prices and current prices

### 5. Logs
- Real-time log streaming
- Log filtering and search
- Error tracking
- System events

### 6. Risk
- Risk metrics and limits
- Exposure levels
- Loss tracking
- Circuit breaker status

### 7. Strategy Lab
- Strategy configuration
- Parameter tuning
- Backtest results
- Performance comparison

### 8. Analytics
- Equity curve
- Trade history
- Performance metrics (Sharpe, win rate, etc.)
- Drawdown analysis

## API Endpoints

The dashboard exposes the following HTTP endpoints:

| Method | Path | Handler | Purpose |
|--------|------|---------|---------|
| GET | `/` | `dashboard_page` | Main dashboard UI |
| GET | `/api/state` | `get_state` | System state |
| GET | `/api/positions` | `get_positions` | Current positions |
| *More endpoints detected via scanning* |

## Backend Integration

The dashboard connects to backend services through:

### State Management APIs
- `/api/state` - Overall system state
- `/api/config` - Configuration data
- `/api/health` - Health check endpoint

### Position & Portfolio APIs
- `/api/positions` - Current positions
- `/api/portfolio` - Portfolio summary
- `/api/pnl` - P&L data

### Strategy & Signal APIs
- `/api/strategies` - Strategy list and status
- `/api/signals` - Recent signals
- `/api/strategy/{id}` - Individual strategy details

### Analytics APIs
- `/api/analytics/trades` - Trade history
- `/api/analytics/performance` - Performance metrics
- `/api/analytics/equity-curve` - Equity curve data

### Control APIs
- `/api/control/start` - Start trading
- `/api/control/stop` - Stop trading
- `/api/control/halt` - Emergency halt

### Log APIs
- `/api/logs` - Log entries
- `/api/logs/stream` - SSE log streaming

## Running the Dashboard

```bash
# Using the script
python scripts/run_dashboard.py

# Using uvicorn directly
uvicorn apps.dashboard:app --reload --host 127.0.0.1 --port 8765
```

Access at: `http://127.0.0.1:8765`

## Technology Stack

- **FastAPI**: High-performance async web framework
- **Jinja2**: Template engine for HTML rendering
- **JavaScript**: Client-side interactivity
- **Server-Sent Events**: Real-time data push from server to client
- **Chart.js / Plotly**: Data visualization (if present)

## Security Notes

⚠️ **Important**: 
- Dashboard should only be accessible on localhost in production
- No authentication is enabled by default
- Use reverse proxy with auth for remote access
- Secure API keys in `secrets/` directory

---
*Auto-generated from apps/dashboard.py analysis*
