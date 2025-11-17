# Arthayukti Dashboard - API Endpoints Documentation

## Overview

This document describes all available API endpoints for the Arthayukti HFT Trading Dashboard. All endpoints return JSON responses and are designed for real-time data access and monitoring.

**Base URL**: `http://localhost:8765/api`

---

## Endpoint Categories

1. [Core System](#core-system)
2. [Trading Data](#trading-data)
3. [Portfolio & Positions](#portfolio--positions)
4. [Analytics](#analytics)
5. [Configuration](#configuration)
6. [Authentication](#authentication)
7. [Market Data](#market-data)
8. [Backtests](#backtests)

---

## Core System

### GET /api/state

Returns the complete application state including engines, P&L, and runtime metadata.

**Response:**
```json
{
  "engines": {},
  "pnl": {
    "total_realized_pnl": 1250.50,
    "total_unrealized_pnl": 325.00
  },
  "ts": "2024-11-17T08:00:00+00:00"
}
```

### GET /api/meta

Returns lightweight metadata for market clock and status updates.

**Response:**
```json
{
  "now_ist": "2024-11-17T13:30:00+05:30",
  "market_open": true,
  "market_status": "OPEN",
  "regime": "TRENDING",
  "status_payload": {
    "now_ist": "2024-11-17T13:30:00+05:30",
    "status": "OPEN",
    "seconds_to_close": 7200
  }
}
```

### GET /api/health

Aggregate engine status, log health, and market session info.

**Response:**
```json
{
  "engine_status": {
    "engines": [{
      "engine": "fno_paper",
      "running": true,
      "last_checkpoint_ts": "2024-11-17T13:25:00+00:00"
    }]
  },
  "log_health": {
    "last_log_ts": "2024-11-17T13:29:50+00:00",
    "error_count_recent": 0,
    "warning_count_recent": 2
  },
  "market_status": {
    "status": "OPEN",
    "ist_timestamp": "2024-11-17T13:30:00+05:30"
  }
}
```

### GET /api/system/time

Returns current UTC time.

**Response:**
```json
{
  "utc": "2024-11-17T08:00:00Z"
}
```

---

## Trading Data

### GET /api/signals

Get trading signals with optional date filtering.

**Query Parameters:**
- `limit` (int, default: 150): Number of signals to return
- `date` (string, optional): ISO date string for filtering (e.g., "2024-11-17")

**Response:**
```json
[
  {
    "timestamp": "2024-11-17T10:30:00+00:00",
    "symbol": "NIFTY24DECFUT",
    "signal": "BUY",
    "strategy": "ema_crossover",
    "tf": "5m",
    "price": 23850.50
  }
]
```

### GET /api/signals/recent

Get most recent signals.

**Query Parameters:**
- `limit` (int, default: 50, min: 1, max: 200)

**Response:**
```json
[
  {
    "ts": "2024-11-17T10:30:00+00:00",
    "symbol": "NIFTY24DECFUT",
    "logical": "NIFTY_5M_EMA",
    "signal": "BUY",
    "tf": "5m",
    "price": 23850.50,
    "profile": "default",
    "strategy": "ema_crossover"
  }
]
```

### GET /api/orders

Get order history with optional date filtering.

**Query Parameters:**
- `limit` (int, default: 150)
- `date` (string, optional): ISO date for filtering

**Response:**
```json
[
  {
    "timestamp": "2024-11-17T10:32:00+00:00",
    "symbol": "NIFTY24DECFUT",
    "side": "BUY",
    "quantity": 25,
    "price": 23850.50,
    "status": "FILLED",
    "pnl": 125.50
  }
]
```

### GET /api/orders/recent

Get most recent orders.

**Query Parameters:**
- `limit` (int, default: 50, min: 1, max: 200)

**Response:**
```json
{
  "orders": [
    {
      "ts": "2024-11-17T10:32:00+00:00",
      "symbol": "NIFTY24DECFUT",
      "side": "BUY",
      "quantity": 25,
      "price": 23850.50,
      "status": "FILLED"
    }
  ]
}
```

---

## Portfolio & Positions

### GET /api/portfolio/summary

Returns compact P&L and risk snapshot for the paper engine.

**Response:**
```json
{
  "paper_capital": 500000.00,
  "total_realized_pnl": 2500.50,
  "total_unrealized_pnl": 325.00,
  "equity": 502825.50,
  "total_notional": 150000.00,
  "free_notional": 352825.50,
  "exposure_pct": 0.298,
  "daily_pnl": 2825.50,
  "has_positions": true,
  "position_count": 3
}
```

### GET /api/positions/open

Returns open paper positions from latest checkpoint.

**Response:**
```json
[
  {
    "symbol": "NIFTY24DECFUT",
    "side": "LONG",
    "quantity": 25,
    "avg_price": 23800.00,
    "last_price": 23850.50,
    "unrealized_pnl": 1262.50
  }
]
```

### GET /api/positions_normalized

Returns normalized positions with detailed price sourcing.

**Response:**
```json
{
  "positions": [
    {
      "symbol": "NIFTY24DECFUT",
      "quantity": 25,
      "avg_price": 23800.00,
      "last_price": 23850.50,
      "price_source": "tick",
      "realized_pnl": 0.00,
      "unrealized_pnl": 1262.50,
      "info": {
        "productType": "FUT",
        "base": "NIFTY",
        "expiry": "24DEC",
        "strike": null,
        "optionType": null
      },
      "lot_size": 25,
      "lots": 1.0
    }
  ]
}
```

### GET /api/margins

Returns margin requirements (live mode only).

**Response:**
```json
{
  "mode": "paper",
  "required": null,
  "available": null,
  "utilized": null,
  "span": null,
  "exposure": null,
  "final": null
}
```

---

## Analytics

### GET /api/summary/today

Returns today's realized P&L and trade statistics.

**Response:**
```json
{
  "date": "2024-11-17",
  "realized_pnl": 2500.50,
  "num_trades": 12,
  "win_trades": 8,
  "loss_trades": 4,
  "win_rate": 66.67,
  "largest_win": 450.00,
  "largest_loss": -125.00,
  "avg_r": 1.85,
  "total_trades_allowed": 12,
  "total_trades_vetoed": 3,
  "avg_signal_score_executed": 7.5
}
```

### GET /api/quality/summary

Returns throttler and trade quality statistics.

**Response:**
```json
{
  "date": "2024-11-17",
  "total_signals": 15,
  "total_trades_taken": 12,
  "total_vetoed": 3,
  "veto_breakdown": {
    "QUALITY_SCORE": 2,
    "CAP_STRATEGY": 1
  },
  "trade_caps": {
    "per_strategy": 5,
    "per_symbol": 3,
    "total_daily": 20
  },
  "quality_summary": {
    "avg_signal_score_executed": 7.5
  },
  "trade_flow": {
    "signals_seen": 15,
    "orders_placed": 12,
    "orders_filled": 12
  },
  "drawdown_hit": false,
  "loss_streak": 0,
  "caps_active": false
}
```

### GET /api/stats/strategies

Aggregate strategy statistics from recent signals.

**Query Parameters:**
- `days` (int, default: 1, min: 1, max: 7): Lookback window in days

**Response:**
```json
[
  {
    "key": "NIFTY|ema_crossover",
    "logical": "NIFTY_5M_EMA",
    "symbol": "NIFTY24DECFUT",
    "strategy": "ema_crossover",
    "last_ts": "2024-11-17T10:30:00+00:00",
    "last_signal": "BUY",
    "last_price": 23850.50,
    "timeframe": "5m",
    "buy_count": 5,
    "sell_count": 3,
    "exit_count": 2,
    "hold_count": 10,
    "trades_today": 3,
    "winrate_20": 0.65,
    "avg_r_20": 1.85
  }
]
```

### GET /api/stats/equity

Returns equity curve snapshots for requested lookback.

**Query Parameters:**
- `days` (int, default: 1, min: 1, max: 7)

**Response:**
```json
[
  {
    "ts": "2024-11-17T09:15:00+00:00",
    "equity": 500000.00,
    "paper_capital": 500000.00,
    "realized": 0.00,
    "unrealized": 0.00
  },
  {
    "ts": "2024-11-17T10:30:00+00:00",
    "equity": 502500.50,
    "paper_capital": 500000.00,
    "realized": 2500.50,
    "unrealized": 0.00
  }
]
```

### GET /api/analytics/summary

Returns combined analytics summary from Strategy Analytics Engine.

**Response:**
```json
{
  "daily": {
    "realized_pnl": 2500.50,
    "num_trades": 12,
    "win_rate": 66.67,
    "avg_win": 312.56,
    "avg_loss": -93.75,
    "biggest_winner": 450.00,
    "biggest_loser": -125.00
  },
  "strategies": {
    "ema_crossover": {
      "pnl": 1250.25,
      "trades": 6,
      "win_rate": 66.67
    }
  },
  "symbols": {
    "NIFTY24DECFUT": {
      "pnl": 2500.50,
      "trades": 12
    }
  }
}
```

### GET /api/analytics/equity_curve

Returns equity curve and drawdown data with optional filters.

**Query Parameters:**
- `strategy` (string, optional): Filter by strategy code
- `symbol` (string, optional): Filter by symbol

**Response:**
```json
{
  "equity_curve": [
    {
      "timestamp": "2024-11-17T09:15:00+00:00",
      "equity": 500000.00
    },
    {
      "timestamp": "2024-11-17T10:30:00+00:00",
      "equity": 502500.50
    }
  ],
  "drawdown": {
    "max_drawdown": -250.00,
    "drawdown_series": [
      {"timestamp": "...", "drawdown": 0.00},
      {"timestamp": "...", "drawdown": -250.00}
    ]
  },
  "filters": {
    "strategy": null,
    "symbol": null
  }
}
```

### GET /api/strategy_performance

Returns strategy performance metrics.

**Response:**
```json
[
  {
    "name": "EMA Crossover",
    "code": "ema_crossover",
    "pnl": 1250.25,
    "wins": 4,
    "losses": 2,
    "entries": 6,
    "exits": 6
  }
]
```

---

## Configuration

### GET /api/config/summary

Returns compact summary of active trading configuration.

**Response:**
```json
{
  "config_path": "/path/to/configs/dev.yaml",
  "mode": "paper",
  "fno_universe": ["NIFTY", "BANKNIFTY"],
  "paper_capital": 500000.00,
  "risk_per_trade_pct": 0.005,
  "max_daily_loss": 3000.00,
  "max_exposure_pct": 2.0,
  "risk_profile": "Default",
  "meta_enabled": true
}
```

### GET /api/risk/summary

Returns risk configuration and current state.

**Response:**
```json
{
  "mode": "paper",
  "per_trade_risk_pct": 0.005,
  "max_daily_loss_abs": 3000.00,
  "max_daily_loss_pct": null,
  "trading_halted": false,
  "halt_reason": null,
  "current_day_pnl": 2500.50,
  "current_exposure": 150000.00
}
```

---

## Authentication

### GET /api/auth/status

Returns authentication status and token validity.

**Response:**
```json
{
  "is_logged_in": true,
  "user_id": "AB1234",
  "login_ts": "2024-11-17T07:00:00+00:00",
  "login_age_minutes": 150.5,
  "token_valid": true,
  "error": null
}
```

### GET /api/debug/auth

Debug endpoint to verify authentication quickly.

**Response:**
```json
{
  "ok": true,
  "detail": {
    "has_api_key": true,
    "has_secret": true,
    "has_access_token": true,
    "profile_ok": true,
    "instruments_sample": 2500
  }
}
```

---

## Logs

### GET /api/logs

Get system logs with optional filtering.

**Query Parameters:**
- `limit` (int, default: 150): Number of log entries
- `level` (string, optional): Filter by level (INFO/WARN/ERROR/DEBUG)
- `contains` (string, optional): Case-insensitive substring filter
- `kind` (string, optional): Logical stream (engine/trades/signals/system)

**Response:**
```json
{
  "logs": [
    {
      "ts": "2024-11-17T10:30:00+00:00",
      "level": "INFO",
      "logger": "engine",
      "message": "Signal processed: BUY NIFTY24DECFUT"
    }
  ],
  "entries": [...]
}
```

### GET /api/logs/recent

Alias for /api/logs with same parameters.

### GET /api/pm/log

Process manager logs (same format as /api/logs).

---

## Market Data

### GET /api/scanner/universe

Returns most recent instrument universe from MarketScanner.

**Response:**
```json
{
  "symbols": ["NIFTY24DECFUT", "BANKNIFTY24DECFUT"],
  "timestamp": "2024-11-17T08:00:00+00:00",
  "count": 2
}
```

### GET /api/quotes

Returns latest quotes from live_quotes.json.

**Query Parameters:**
- `keys` (string, optional): Comma-separated logical names to filter

**Response:**
```json
{
  "NIFTY24DECFUT": {
    "last_price": 23850.50,
    "bid": 23849.00,
    "ask": 23851.00,
    "volume": 125000
  }
}
```

### GET /api/market_data/window

Returns last N candles for specified symbol and timeframe.

**Query Parameters:**
- `symbol` (string, required): Trading symbol (e.g., NIFTY24DECFUT)
- `timeframe` (string, default: "5m"): Timeframe (1m, 5m, 15m, 1h, 1d)
- `limit` (int, default: 50, min: 1, max: 1000): Number of candles

**Response:**
```json
{
  "symbol": "NIFTY24DECFUT",
  "timeframe": "5m",
  "count": 50,
  "candles": [
    {
      "ts": "2024-11-17T10:30:00+00:00",
      "open": 23800.0,
      "high": 23865.0,
      "low": 23795.0,
      "close": 23850.5,
      "volume": 12345.0
    }
  ]
}
```

### GET /api/market_data/latest_tick

Get latest tick from Market Data Engine v2.

**Query Parameters:**
- `symbol` (string, required): Trading symbol

**Response:**
```json
{
  "symbol": "NIFTY24DECFUT",
  "ltp": 23850.0,
  "bid": 23849.0,
  "ask": 23851.0,
  "volume": 125000,
  "ts": "2024-11-17T10:30:15+00:00"
}
```

---

## Backtests

### GET /api/backtests/list

List all available backtest runs (legacy format).

**Response:**
```json
{
  "runs": [
    {
      "strategy": "ema_crossover",
      "run": "2024-11-14_1545",
      "path": "ema_crossover/2024-11-14_1545"
    }
  ]
}
```

### GET /api/backtests

List all backtest runs with summary information.

**Response:**
```json
{
  "runs": [
    {
      "run_id": "2024-11-14_1545",
      "strategy": "ema_crossover",
      "symbol": "NIFTY",
      "timeframe": "5m",
      "date_from": "2024-11-01",
      "date_to": "2024-11-14",
      "net_pnl": 12500.50,
      "win_rate": 65.5,
      "total_trades": 42,
      "created_at": 1700000000.0
    }
  ]
}
```

### GET /api/backtests/{run_id:path}/summary

Get full summary data for specific backtest run.

**Response:**
```json
{
  "run_id": "ema_crossover/2024-11-14_1545",
  "summary": {
    "net_pnl": 12500.50,
    "total_trades": 42,
    "win_rate": 65.5,
    "...": "..."
  }
}
```

### GET /api/backtests/{run_id:path}/equity_curve

Get equity curve data for specific backtest run.

**Response:**
```json
{
  "run_id": "ema_crossover/2024-11-14_1545",
  "equity_curve": [
    {
      "ts": "2024-11-14T10:30:00",
      "equity": 1000050.0,
      "pnl": 50.0
    }
  ]
}
```

### GET /api/backtests/result

Get backtest result by path.

**Query Parameters:**
- `path` (string, required): strategy/run path (e.g., "ema_crossover/2024-11-14_1545")

**Response:**
```json
{
  "...": "Full backtest result payload"
}
```

---

## Engine Status

### GET /api/engines/status

Returns status of all trading engines.

**Response:**
```json
{
  "engines": [
    {
      "engine": "fno_paper",
      "running": true,
      "last_checkpoint_ts": "2024-11-17T13:25:00+00:00",
      "checkpoint_age_seconds": 5.23,
      "market_open": true,
      "mode": "paper",
      "error": null,
      "checkpoint_path": "/path/to/checkpoint"
    }
  ]
}
```

---

## Utility Endpoints

### POST /api/resync

Resync state from journal or live broker.

**Response:**
```json
{
  "ok": true,
  "mode": "paper",
  "timestamp": "2024-11-17T13:30:00+00:00"
}
```

---

## Error Responses

All endpoints return standard error responses:

**4xx Client Errors:**
```json
{
  "detail": "Error message describing what went wrong"
}
```

**5xx Server Errors:**
```json
{
  "detail": "Internal server error message"
}
```

---

## Rate Limiting

Currently no rate limiting is implemented. API calls are processed synchronously.

**Recommendations:**
- Poll endpoints at reasonable intervals (10-30 seconds for data updates)
- Use WebSockets for real-time streaming (if/when available)
- Batch requests where possible

---

## CORS Policy

The API allows requests from all origins:
- `allow_origins`: ["*"]
- `allow_credentials`: True
- `allow_methods`: ["*"]
- `allow_headers`: ["*"]

---

## Testing

### Using cURL

```bash
# Get portfolio summary
curl http://localhost:8765/api/portfolio/summary

# Get recent signals
curl http://localhost:8765/api/signals/recent?limit=10

# Get today's summary
curl http://localhost:8765/api/summary/today
```

### Using JavaScript

```javascript
// Fetch portfolio data
const response = await fetch('/api/portfolio/summary');
const portfolio = await response.json();
console.log('Equity:', portfolio.equity);
```

---

## Changelog

### v2.0 (2024-11-17)
- Added comprehensive API documentation
- Documented all endpoint parameters and responses
- Added usage examples
- Structured by functionality

### v1.0 (Earlier)
- Initial API implementation
- Basic CRUD endpoints for trading data

---

## Support

For questions or issues with the API:
- Check logs at `/api/logs`
- Review authentication status at `/api/auth/status`
- Test with `/api/debug/auth`
