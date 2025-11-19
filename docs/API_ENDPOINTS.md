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
| GET | `/api/analytics/summary` | `api_analytics_summary` | `kite-algo-minimal/ui/dashboard.py` | Return combined analytics summary: |
| GET | `/api/debug/auth` | `api_debug_auth` | `kite-algo-minimal/ui/dashboard.py` |  |
| GET | `/api/margins` | `api_margins` | `kite-algo-minimal/ui/dashboard.py` |  |
| GET | `/api/market/context` | `get_market_context` | `kite-algo-minimal/apps/server.py` | Get current market context snapshot. |
| GET | `/api/meta` | `api_meta` | `kite-algo-minimal/ui/dashboard.py` | Lightweight metadata endpoint for market clock/pil... |
| GET | `/api/orders` | `api_orders` | `kite-algo-minimal/ui/dashboard.py` |  |
| GET | `/api/portfolio/limits` | `get_portfolio_limits` | `kite-algo-minimal/apps/server.py` | Get current portfolio limits and usage. |
| GET | `/api/positions_normalized` | `api_positions_normalized` | `kite-algo-minimal/ui/dashboard.py` |  |
| GET | `/api/quotes` | `api_quotes` | `kite-algo-minimal/ui/dashboard.py` | Return latest quotes from artifacts/live_quotes.js... |
| POST | `/api/resync` | `api_resync` | `kite-algo-minimal/ui/dashboard.py` |  |
| GET | `/api/risk/summary` | `api_risk_summary` | `kite-algo-minimal/ui/dashboard.py` |  |
| GET | `/api/signals` | `api_signals` | `kite-algo-minimal/ui/dashboard.py` |  |
| GET | `/api/state` | `api_state` | `kite-algo-minimal/ui/dashboard.py` |  |
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
*Auto-generated via AST scanning of FastAPI routes*
