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

**Data Source:** `/api/health`, `/api/trading/summary`

### 2. Analytics
- Equity curve from runtime metrics
- Overall performance metrics (total_trades, win_rate, profit_factor)
- Per-strategy breakdown with P&L
- Per-symbol breakdown with P&L
- Max drawdown tracking

**Data Source:** `/api/analytics/summary` → `artifacts/analytics/runtime_metrics.json`

### 3. Engines / Status
- Engine state (running, stopped, error)
- Active strategies from config
- Position counts
- Resource utilization

**Data Source:** `/api/trading/summary`, `/api/strategies`

### 4. Signals
- Recent signals generated
- Signal quality metrics
- Strategy-specific signals
- Historical signal performance

**Data Source:** `/api/signals` → `artifacts/signals.csv`

### 5. Positions & Portfolio
- Current open positions
- Unrealized P&L
- Position sizing
- Entry prices and current prices

**Data Source:** `/api/positions_normalized` → `artifacts/checkpoints/paper_state_latest.json`

### 6. Logs
- Real-time log streaming
- Log filtering and search
- Error tracking
- System events

**Data Source:** `/api/logs/recent` → log files

### 7. Risk
- Risk metrics and limits (max_daily_loss, max_exposure_pct, risk_per_trade_pct)
- Exposure levels (current vs. max)
- Loss tracking (used_loss, remaining_loss)
- Circuit breaker status

**Data Source:** `/api/risk/summary` → config + runtime metrics

### 8. Strategy Lab
- Strategy list with enabled/disabled status
- Parameter configuration per strategy
- Tags and engine type (equity/fno/options)
- Backtest results (when available)
- Performance comparison

**Data Source:** `/api/strategies` → `configs/dev.yaml` + `configs/learned_overrides.yaml`

### 9. Trading
- Mode (paper/live) and engine status (RUNNING/STOPPED)
- Server time in IST
- Active orders (PENDING/OPEN status)
- Recent orders (last 10)
- Active positions count

**Data Source:** `/api/trading/summary` → checkpoints + orders.csv

## API Endpoints

The dashboard exposes the following HTTP endpoints:

### Core Dashboard APIs

| Method | Path | Purpose | Data Source |
|--------|------|---------|-------------|
| GET | `/` | Main dashboard UI (React SPA) | - |
| GET | `/risk` | Risk page route (SPA) | - |
| GET | `/analytics` | Analytics page route (SPA) | - |
| GET | `/strategies` | Strategies page route (SPA) | - |

### Analytics APIs

| Method | Path | Purpose | Data Source |
|--------|------|---------|-------------|
| GET | `/api/analytics/summary` | Comprehensive analytics | `artifacts/analytics/runtime_metrics.json` |
| GET | `/api/analytics/equity_curve` | Equity curve data | snapshots.csv |
| GET | `/api/performance` | Performance metrics | runtime_metrics.json |

### Trading & Orders APIs

| Method | Path | Purpose | Data Source |
|--------|------|---------|-------------|
| GET | `/api/trading/summary` | Trading status + orders | checkpoints + orders.csv |
| GET | `/api/trading/status` | Engine status | checkpoint age |
| GET | `/api/orders` | Order history | orders.csv |
| GET | `/api/signals` | Signal history | signals.csv |

### Portfolio & Positions APIs

| Method | Path | Purpose | Data Source |
|--------|------|---------|-------------|
| GET | `/api/positions_normalized` | Current positions | paper_state_latest.json |
| GET | `/api/state` | Overall system state | checkpoint |
| GET | `/api/portfolio/limits` | Portfolio limits | config |

### Strategy APIs

| Method | Path | Purpose | Data Source |
|--------|------|---------|-------------|
| GET | `/api/strategies` | List all strategies | config + overrides |
| POST | `/api/strategies/{id}/enable` | Enable strategy | learned_overrides.yaml |
| POST | `/api/strategies/{id}/disable` | Disable strategy | learned_overrides.yaml |
| PUT | `/api/strategies/{id}/params` | Update params | learned_overrides.yaml |

### Risk & Circuit Breakers

| Method | Path | Purpose | Data Source |
|--------|------|---------|-------------|
| GET | `/api/risk/summary` | Risk metrics + limits | config + runtime metrics |
| GET | `/api/risk/limits` | Risk limit config | config |
| GET | `/api/risk/breaches` | Active breaches | runtime state |
| GET | `/api/risk/var` | Value at Risk | historical trades |

### System & Health

| Method | Path | Purpose | Data Source |
|--------|------|---------|-------------|
| GET | `/api/health` | System health check | engine status + logs |
| GET | `/api/meta` | IST time + market status | - |
| GET | `/healthz` | Basic health check | - |
| POST | `/api/resync` | Rebuild state from journal | journal + orders |

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
