# Web Dashboard

> **Status**: OBSOLETE – Last validated: 2025-11-19  
> **Superseded by**: [docs/DASHBOARD.md](./DASHBOARD.md)  
> **Note**: This document contains outdated information. Please refer to DASHBOARD.md for current dashboard documentation.

## Overview

The web dashboard provides real-time monitoring and control of the trading system via a FastAPI-based web interface.

## Architecture

### Components

1. **Dashboard API** (`ui/dashboard.py`)
   - FastAPI application
   - RESTful API endpoints
   - WebSocket support (future)

2. **Dashboard Services** (`ui/services.py`)
   - Business logic layer
   - State aggregation
   - Data formatting

3. **Frontend** (`ui/templates/` and `ui/static/`)
   - HTML templates (Jinja2)
   - JavaScript for interactivity
   - CSS styling

## API Endpoints

### `/api/state`

Description: [Auto-extracted endpoint]

### `/api/meta`

Description: [Auto-extracted endpoint]

### `/api/config/summary`

Description: [Auto-extracted endpoint]

### `/api/summary/today`

Description: [Auto-extracted endpoint]

### `/api/quality/summary`

Description: [Auto-extracted endpoint]

### `/api/signals`

Description: [Auto-extracted endpoint]

### `/api/orders`

Description: [Auto-extracted endpoint]

### `/api/logs`

Description: [Auto-extracted endpoint]

### `/api/auth/status`

Description: [Auto-extracted endpoint]

### `/api/engines/status`

Description: [Auto-extracted endpoint]

### `/api/portfolio/summary`

Description: [Auto-extracted endpoint]

### `/api/monitor/trade_flow`

Description: [Auto-extracted endpoint]

### `/api/trade_flow`

Description: [Auto-extracted endpoint]

### `/api/signals/recent`

Description: [Auto-extracted endpoint]

### `/api/positions/open`

Description: [Auto-extracted endpoint]

### `/api/orders/recent`

Description: [Auto-extracted endpoint]

### `/api/stats/strategies`

Description: [Auto-extracted endpoint]

### `/api/stats/equity`

Description: [Auto-extracted endpoint]

### `/api/scanner/universe`

Description: [Auto-extracted endpoint]

### `/api/market_data/window`

Description: [Auto-extracted endpoint]

### `/api/market_data/latest_tick`

Description: [Auto-extracted endpoint]

### `/api/market_data/candles`

Description: [Auto-extracted endpoint]

### `/api/market_data/v2/stats`

Description: [Auto-extracted endpoint]

### `/api/backtests/list`

Description: [Auto-extracted endpoint]

### `/api/backtests/result`

Description: [Auto-extracted endpoint]

### `/api/backtests`

Description: [Auto-extracted endpoint]

### `/api/backtests/{run_id:path}/summary`

Description: [Auto-extracted endpoint]

### `/api/backtests/{run_id:path}/equity_curve`

Description: [Auto-extracted endpoint]

### `/api/logs/recent`

Description: [Auto-extracted endpoint]

### `/api/pm/log`

Description: [Auto-extracted endpoint]

### `/api/system/time`

Description: [Auto-extracted endpoint]

### `/api/health`

Description: [Auto-extracted endpoint]

### `/api/risk/summary`

Description: [Auto-extracted endpoint]

### `/api/strategy_performance`

Description: [Auto-extracted endpoint]

### `/api/quotes`

Description: [Auto-extracted endpoint]

### `/api/positions_normalized`

Description: [Auto-extracted endpoint]

### `/api/margins`

Description: [Auto-extracted endpoint]

### `/api/debug/auth`

Description: [Auto-extracted endpoint]

### `/api/resync`

Description: [Auto-extracted endpoint]

### `/api/analytics/summary`

Description: [Auto-extracted endpoint]

### `/api/analytics/equity_curve`

Description: [Auto-extracted endpoint]


## Key Features

### Real-Time Monitoring
- Live positions and P&L
- Recent trades
- Order status
- Strategy performance

### Control Panel
- Start/stop trading
- Emergency halt
- Strategy enable/disable
- Risk parameter adjustment

### Analytics
- Equity curve
- Trade history
- Performance metrics
- Win/loss analysis

### System Status
- Market hours
- Kite connection status
- Engine health
- Last heartbeat

## Running the Dashboard

```bash
# Start dashboard server
python scripts/run_dashboard.py

# Or use uvicorn directly
uvicorn ui.dashboard:app --reload --port 8000
```

## Accessing the Dashboard

```
http://localhost:8000
```

## API Usage

### Get Current State

```bash
curl http://localhost:8000/api/state
```

### Get Positions

```bash
curl http://localhost:8000/api/positions
```

### Get Trade History

```bash
curl http://localhost:8000/api/trades
```

## Configuration

```yaml
dashboard:
  host: "0.0.0.0"
  port: 8000
  reload: false
  log_level: "info"
```

## Security

⚠️ **Important**: The dashboard should not be exposed to the public internet without:
- Authentication
- HTTPS/TLS
- API rate limiting
- CORS configuration

## Development

### Local Development

```bash
# Run with auto-reload
uvicorn ui.dashboard:app --reload --port 8000
```

### Adding New Endpoints

1. Define route in `ui/dashboard.py`
2. Implement logic in `ui/services.py`
3. Update frontend templates
4. Test endpoint

---
*Auto-generated on 2025-11-17T19:09:52.567436+00:00*
