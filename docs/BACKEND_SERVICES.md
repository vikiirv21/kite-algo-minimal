# Backend Services

## Overview

The backend consists of trading engines, services, strategies, and supporting infrastructure.

## Main Backend Apps

### Apps Directory (`apps/`)
- `dashboard.py` - Web dashboard FastAPI application
- `dashboard_logs.py` - Log streaming and management
- `api_strategies.py` - Strategy-related API endpoints
- `server.py` - Main server orchestrator (if present)
- `run_service.py` - Service runner
- `run_equity_paper.py`, `run_fno_paper.py`, `run_options_paper.py` - Mode-specific runners

### Engine Directory (`engine/`)
- `paper_engine.py` - Paper trading engine with simulated fills
- `live_engine.py` - Live trading engine with real order placement
- `equity_paper_engine.py` - Equity-specific paper engine
- `options_paper_engine.py` - Options-specific paper engine
- `execution_bridge.py` - Unified execution interface
- `execution_engine.py` - Order execution logic
- `meta_strategy_engine.py` - Meta-strategy coordinator
- `bootstrap.py` - Engine initialization

### Core Directory (`core/`)
- `strategy_engine_v3.py` - Strategy execution framework v3
- `market_data_engine_v2.py` - Market data management v2
- `risk_engine_v2.py` - Risk validation and management v2
- `portfolio_engine.py` - Portfolio tracking and P&L
- `execution_engine_v3.py` - Execution engine v3
- `trade_guardian.py` - Pre-trade validation
- `scanner.py` - Technical pattern scanner
- `orchestrator.py` - System orchestration (if present)

### Analytics Directory (`analytics/`)
- `telemetry.py` - System metrics collection
- `trade_recorder.py` - Trade journaling
- `strategy_performance.py` - Strategy analytics

## Entry Points

### Main Day Trading
```bash
python scripts/run_day.py --login --engines all
```
Orchestrates the full trading day with login, engine startup, and shutdown.

### Paper Trading
```bash
# Equity paper trading
python scripts/run_paper_equity.py

# F&O paper trading
python scripts/run_paper_fno.py

# Options paper trading
python scripts/run_paper_options.py
```

### Session-Based Trading
```bash
python scripts/run_session.py
```
Runs a trading session with configurable parameters.

## FastAPI Services

### Detected Endpoints

| Method | Path | Handler | Module |
|--------|------|---------|--------|
| POST | `/admin/login` | `admin_login` | kite-algo-minimal/apps/server.py |
| POST | `/admin/mode` | `admin_mode` | kite-algo-minimal/apps/server.py |
| POST | `/admin/resync` | `admin_resync` | kite-algo-minimal/apps/server.py |
| POST | `/admin/start` | `admin_start` | kite-algo-minimal/apps/server.py |
| POST | `/admin/stop` | `admin_stop` | kite-algo-minimal/apps/server.py |
| GET | `/api/analytics/equity_curve` | `api_equity_curve` | kite-algo-minimal/ui/dashboard.py |
| GET | `/api/analytics/summary` | `api_analytics_summary` | kite-algo-minimal/ui/dashboard.py |
| GET | `/api/debug/auth` | `api_debug_auth` | kite-algo-minimal/ui/dashboard.py |
| GET | `/api/margins` | `api_margins` | kite-algo-minimal/ui/dashboard.py |
| GET | `/api/market/context` | `get_market_context` | kite-algo-minimal/apps/server.py |
| GET | `/api/meta` | `api_meta` | kite-algo-minimal/ui/dashboard.py |
| GET | `/api/orders` | `api_orders` | kite-algo-minimal/ui/dashboard.py |
| GET | `/api/portfolio/limits` | `get_portfolio_limits` | kite-algo-minimal/apps/server.py |
| GET | `/api/positions_normalized` | `api_positions_normalized` | kite-algo-minimal/ui/dashboard.py |
| GET | `/api/quotes` | `api_quotes` | kite-algo-minimal/ui/dashboard.py |
| POST | `/api/resync` | `api_resync` | kite-algo-minimal/ui/dashboard.py |
| GET | `/api/risk/summary` | `api_risk_summary` | kite-algo-minimal/ui/dashboard.py |
| GET | `/api/signals` | `api_signals` | kite-algo-minimal/ui/dashboard.py |
| GET | `/api/state` | `api_state` | kite-algo-minimal/ui/dashboard.py |
| GET | `/api/strategy_performance` | `api_strategy_performance` | kite-algo-minimal/ui/dashboard.py |
| GET | `/api/telemetry/events` | `telemetry_events` | kite-algo-minimal/apps/server.py |
| GET | `/api/telemetry/stats` | `telemetry_stats` | kite-algo-minimal/apps/server.py |
| GET | `/healthz` | `healthz` | kite-algo-minimal/apps/server.py |


## Trading Engines

### Paper Engine
**File**: `engine/paper_engine.py`

Simulates trading with virtual capital:
- Instant fills at requested prices
- No slippage (unless configured)
- Position tracking in memory
- P&L calculation
- Risk-free strategy testing

### Live Engine
**File**: `engine/live_engine.py`

Places real orders via Kite API:
- WebSocket tick processing
- Real order placement and tracking
- Fill confirmations via API
- Safety guardrails and validation
- Market hours enforcement

### Execution Bridge
**File**: `engine/execution_bridge.py`

Mode-aware routing:
- Routes orders to appropriate broker (paper/live)
- Unified interface for all modes
- Order lifecycle management

## Strategies

### Available Strategies

| File | Class | Description |
|------|-------|-------------|
| `mean_reversion_intraday.py` | `MeanReversionIntradayStrategy` | Strategy implementation |
| `fno_intraday_trend.py` | `FnoIntradayTrendStrategy` | Strategy implementation |


### Strategy Framework

All strategies inherit from `BaseStrategy` and implement:
- `generate_signal()` - Core signal generation logic
- Configuration via YAML
- State management
- Risk integration

## Configuration

Backend services are configured via YAML files in `configs/`:

```yaml
trading:
  mode: paper  # or live
  paper_capital: 500000
  fno_universe: [NIFTY, BANKNIFTY]

risk:
  risk_per_trade_pct: 0.005
  max_daily_loss: 3000
  max_exposure_pct: 2.0

strategies:
  enabled: true
  # Strategy-specific config
```

## Broker Integration

### Kite Client (`broker/`)
- `kite_client.py` - Kite API wrapper
- `auth.py` - Authentication handling
- `live_broker.py` - Live broker implementation
- `execution_router.py` - Order routing logic

### Authentication Flow
1. Login via `scripts/login_kite.py`
2. Store access token in `secrets/`
3. Engines load token on startup
4. Token validation before each session

## Service Architecture

```
FastAPI App (Dashboard)
        ↓
   Engine Layer (Paper/Live)
        ↓
   Strategy Engine v3
        ↓
   Market Data Engine v2
        ↓
   Risk Engine v2
        ↓
   Execution Engine v3
        ↓
   Broker Layer (Kite)
```

## Monitoring & Health

Services expose health endpoints:
- `/health` - Basic health check
- `/api/state` - Detailed system state
- `/api/metrics` - Performance metrics

Logs are written to `artifacts/logs/`:
- `engine.log` - Engine events
- `events.jsonl` - Structured JSON logs
- `trades.log` - Trade journal

---
*Auto-generated from repository analysis*
