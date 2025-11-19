# API Endpoints

## Overview

This document lists all HTTP API endpoints exposed by the trading system's backend services.

## Endpoint Summary


### /admin

| Method | Path | Handler | Module | Description |
|--------|------|---------|--------|-------------|
| POST | `/admin/login` | `admin_login` | `kite-algo-minimal/apps/server.py` |  |
| POST | `/admin/mode` | `admin_mode` | `kite-algo-minimal/apps/server.py` |  |
| POST | `/admin/resync` | `admin_resync` | `kite-algo-minimal/apps/server.py` |  |
| POST | `/admin/start` | `admin_start` | `kite-algo-minimal/apps/server.py` |  |
| POST | `/admin/stop` | `admin_stop` | `kite-algo-minimal/apps/server.py` |  |

### /api

| Method | Path | Handler | Module | Description |
|--------|------|---------|--------|-------------|
| GET | `/api/analytics/equity_curve` | `api_equity_curve` | `kite-algo-minimal/ui/dashboard.py` | Return equity curve and drawdown data. |
| GET | `/api/analytics/summary` | `api_analytics_summary` | `kite-algo-minimal/ui/dashboard.py` | Return combined analytics summary from runtime_metrics.json. |
| GET | `/api/debug/auth` | `api_debug_auth` | `kite-algo-minimal/ui/dashboard.py` |  |
| GET | `/api/margins` | `api_margins` | `kite-algo-minimal/ui/dashboard.py` |  |
| GET | `/api/market/context` | `get_market_context` | `kite-algo-minimal/apps/server.py` | Get current market context snapshot. |
| GET | `/api/meta` | `api_meta` | `kite-algo-minimal/ui/dashboard.py` | Lightweight metadata endpoint for market clock/pil... |
| GET | `/api/orders` | `api_orders` | `kite-algo-minimal/ui/dashboard.py` |  |
| GET | `/api/portfolio/limits` | `get_portfolio_limits` | `kite-algo-minimal/apps/server.py` | Get current portfolio limits and usage. |
| GET | `/api/positions_normalized` | `api_positions_normalized` | `kite-algo-minimal/ui/dashboard.py` |  |
| GET | `/api/quotes` | `api_quotes` | `kite-algo-minimal/ui/dashboard.py` | Return latest quotes from artifacts/live_quotes.js... |
| POST | `/api/resync` | `api_resync` | `kite-algo-minimal/ui/dashboard.py` |  |
| GET | `/api/risk/summary` | `api_risk_summary` | `kite-algo-minimal/ui/dashboard.py` | Return risk summary with all required fields. |
| GET | `/api/signals` | `api_signals` | `kite-algo-minimal/ui/dashboard.py` |  |
| GET | `/api/state` | `api_state` | `kite-algo-minimal/ui/dashboard.py` | Return engine status based on available runtime state. |
| GET | `/api/strategy_performance` | `api_strategy_performance` | `kite-algo-minimal/ui/dashboard.py` |  |
| GET | `/api/telemetry/events` | `telemetry_events` | `kite-algo-minimal/apps/server.py` | Get recent telemetry events. |
| GET | `/api/telemetry/stats` | `telemetry_stats` | `kite-algo-minimal/apps/server.py` | Get telemetry bus statistics. |

### /healthz

| Method | Path | Handler | Module | Description |
|--------|------|---------|--------|-------------|
| GET | `/healthz` | `healthz` | `kite-algo-minimal/apps/server.py` |  |


## API Categories

### Dashboard & UI Endpoints
Routes serving the web dashboard interface and frontend assets.
- Typically found in `apps/dashboard.py`
- Includes HTML pages, static files, and UI-related APIs

### State & System Endpoints
System state, health checks, and configuration.
- `/api/state` - Overall system state
- `/api/health` - Health check
- `/api/config` - Configuration data

### Position & Portfolio Endpoints
Current positions, P&L, and portfolio data.
- `/api/positions` - Current positions
- `/api/portfolio` - Portfolio summary
- `/api/pnl` - P&L data

### Strategy & Signal Endpoints
Strategy management and signal monitoring.
- `/api/strategies` - Strategy list
- `/api/signals` - Recent signals
- `/api/strategy/{id}` - Strategy details

### Analytics Endpoints
Performance metrics, trade history, and analytics.
- `/api/analytics/trades` - Trade history
- `/api/analytics/performance` - Performance metrics
- `/api/analytics/equity-curve` - Equity curve

### Control Endpoints
Trading control and management.
- `/api/control/start` - Start trading
- `/api/control/stop` - Stop trading
- `/api/control/halt` - Emergency halt

### Log Endpoints
Log streaming and management.
- `/api/logs` - Log entries
- `/api/logs/stream` - SSE log stream

## Authentication

⚠️ **Note**: Most endpoints currently do not require authentication. This is suitable for local-only deployments but should be secured for remote access.

## CORS Configuration

CORS is typically configured to allow:
- `localhost` origins during development
- Specific domains in production

## Rate Limiting

Consider implementing rate limiting for:
- Analytics endpoints (high data volume)
- Control endpoints (security)
- Log streaming (resource intensive)

## Example Usage

### Get System State
```bash
curl http://localhost:8765/api/state
```

### Get Current Positions
```bash
curl http://localhost:8765/api/positions
```

### Stream Logs (SSE)
```bash
curl -N http://localhost:8765/api/logs/stream
```

### Control Trading
```bash
# Start trading
curl -X POST http://localhost:8765/api/control/start

# Emergency halt
curl -X POST http://localhost:8765/api/control/halt
```

## Response Formats

All API responses are typically JSON:

```json
{
  "status": "success",
  "data": { ... },
  "timestamp": "2024-01-15T10:30:00Z"
}
```

Error responses:

```json
{
  "status": "error",
  "message": "Error description",
  "code": "ERROR_CODE"
}
```

## WebSocket Endpoints

Some endpoints may support WebSocket connections for real-time updates:
- Log streaming
- Position updates
- Signal notifications

---

## Detailed Endpoint Documentation

### /api/analytics/summary

**Method:** GET  
**Path:** `/api/analytics/summary`  
**Handler:** `api_analytics_summary`  
**Module:** `kite-algo-minimal/ui/dashboard.py`

**Description:**  
Return combined analytics summary from runtime_metrics.json. Uses artifacts/analytics/runtime_metrics.json as the main source. Falls back to today's YYYY-MM-DD-metrics.json if runtime file missing.

**Response Schema:**
```json
{
  "asof": "2025-11-19T10:30:00+05:30",  // ISO timestamp or null
  "status": "ok",  // "ok" | "stale" | "empty"
  "mode": "paper",  // "paper" | "live"
  "equity": {
    "starting_capital": 500000.0,
    "current_equity": 502500.0,
    "realized_pnl": 2500.0,
    "unrealized_pnl": 150.0,
    "max_drawdown": 1200.0,
    "max_equity": 503000.0,
    "min_equity": 498500.0
  },
  "overall": {
    "total_trades": 15,
    "win_trades": 10,
    "loss_trades": 5,
    "breakeven_trades": 0,
    "win_rate": 66.7,
    "gross_profit": 5000.0,
    "gross_loss": -2500.0,
    "net_pnl": 2500.0,
    "profit_factor": 2.0,
    "avg_win": 500.0,
    "avg_loss": -500.0,
    "avg_r_multiple": 1.5,
    "biggest_win": 1200.0,
    "biggest_loss": -800.0
  },
  "per_strategy": {
    "ema20_50_intraday": {
      "total_trades": 10,
      "net_pnl": 1500.0,
      "win_rate": 70.0
    }
  },
  "per_symbol": {
    "NIFTY24DECFUT": {
      "total_trades": 8,
      "net_pnl": 1200.0,
      "win_rate": 75.0
    }
  }
}
```

**Error Handling:**
- Never crashes on missing or malformed files
- Returns safe empty defaults with status: "empty"
- All datetime values converted to ISO strings

---

### /api/state

**Method:** GET  
**Path:** `/api/state`  
**Handler:** `api_state`  
**Module:** `kite-algo-minimal/ui/dashboard.py`

**Description:**  
Return engine status based on available runtime state. Checks artifacts/checkpoints/* or any engine state file for heartbeat information.

**Response Schema:**
```json
{
  "mode": "paper",  // "paper" | "live" | "unknown"
  "engine_status": "running",  // "running" | "stopped" | "unknown"
  "last_heartbeat_ts": "2025-11-19T10:30:00+00:00",  // ISO timestamp or null
  "last_update_age_seconds": 15,  // Number (0 if unknown)
  "active_engines": ["paper_engine"],  // Array of engine identifiers
  "positions_count": 3  // Number of open positions
}
```

**Status Determination:**
- `running`: Last checkpoint updated within 3 minutes
- `stopped`: Last checkpoint older than 3 minutes or not found
- `unknown`: Unable to determine status

**Error Handling:**
- Graceful fallback to defaults
- Never throws exceptions
- Returns safe defaults on any error

---

### /api/risk/summary

**Method:** GET  
**Path:** `/api/risk/summary`  
**Handler:** `api_risk_summary`  
**Module:** `kite-algo-minimal/ui/dashboard.py`

**Description:**  
Return risk summary with all required fields. Sources config from configs/dev.yaml and PnL from analytics (runtime_metrics.json).

**Response Schema:**
```json
{
  "max_daily_loss": 3000.0,  // Maximum daily loss limit in rupees
  "used_loss": -1200.0,  // Current day loss (negative value)
  "remaining_loss": 1800.0,  // Remaining loss allowance
  "max_exposure_pct": 200.0,  // Maximum exposure as percentage
  "current_exposure_pct": 45.5,  // Current exposure as percentage
  "risk_per_trade_pct": 0.5,  // Risk per trade as percentage
  "status": "ok"  // "ok" | "empty" | "stale"
}
```

**Field Calculations:**
- `used_loss`: Current day's realized PnL if negative, 0 otherwise
- `remaining_loss`: max_daily_loss + used_loss (since used_loss is negative)
- `current_exposure_pct`: (total_notional / equity) * 100

**Error Handling:**
- Defaults to zeros if any field missing
- Must always return JSON with correct fields
- Never crashes - returns safe defaults on error

---
*Auto-generated via AST scanning of FastAPI routes*
