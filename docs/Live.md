# Live Trading Mode

## Overview

The **Live Trading Engine** places **REAL orders** via the Kite broker API. It runs in parallel with the Paper engine but diverges at the execution layer.

## Architecture

### Shared Components

Live mode shares the following components with Paper mode:

- **StrategyEngine v2**: Strategy logic and signal generation
- **RiskEngine**: Risk checks, position sizing, and safety guardrails
- **MarketDataEngine**: Market data fetching and candle management
- **StateStore**: Checkpoint and state management

### Live-Specific Components

- **LiveEngine** (`engine/live_engine.py`): Main live trading orchestrator
- **KiteBroker** (`broker/kite_bridge.py`): Kite API adapter for orders and ticks
- **WebSocket Ticker**: Real-time price updates via Kite WebSocket

## How It Works

1. **Initialization**
   - Validates Kite session (requires valid access token)
   - Subscribes to WebSocket ticks for configured symbols
   - Loads risk settings and universe from config

2. **Tick Processing**
   - Receives ticks via WebSocket
   - Updates market data engine
   - Runs strategy engine for each symbol
   - Generates signals (BUY, SELL, EXIT, HOLD)

3. **Order Placement**
   - Signal → Order Intent
   - Intent → RiskEngine validation
   - If approved → Place REAL order via KiteBroker
   - Track pending orders and handle updates

4. **Safety Guardrails**
   - Login validation before every order
   - Market hours check (IST 9:15 AM - 3:30 PM)
   - RiskEngine blocks (BLOCK, REDUCE, HALT_SESSION)
   - Robust exception handling
   - Clear log warnings

## Key Classes

### LiveEngine

LIVE trading engine that places real orders via Kite.

Key features:
- WebSocket-based tick processing
- Real order placement through KiteBroker
- Shared strategy and risk engines with paper mode
- Safety guardrails (login checks, market hours, risk engine)

**Methods:**
- `__init__()`
- `start()`
- `on_tick()`
- `place_order()`
- `handle_order_update()`
- `stop()`


## Running Live Mode

**⚠️ WARNING: Live mode places REAL orders with REAL money!**

```bash
# First, authenticate with Kite
python scripts/login_kite.py

# Then run live engine
python scripts/run_live.py
```

## Configuration

Live mode configuration in `configs/config.yaml`:

```yaml
trading:
  mode: LIVE
  capital: 100000
  
risk:
  mode: live
  max_daily_loss_pct: 5.0
  max_positions_total: 3
  per_trade_risk_pct: 1.0
```

## Safety Features

- **Pre-Order Validation**: Login check before every order
- **Market Hours**: Only trades during market hours
- **Risk Limits**: Hard caps on position size and daily loss
- **Emergency Halt**: Can halt all trading instantly
- **Order Tracking**: Full order lifecycle monitoring

## Live vs Paper Differences

| Feature | Paper | Live |
|---------|-------|------|
| Order Placement | Simulated | Real Kite API |
| Fill Timing | Instant | Async via WebSocket |
| Slippage | None | Real market slippage |
| Costs | Optional | Real brokerage fees |
| Risk | Zero | Real capital |

## Monitoring

- Check dashboard at `http://localhost:8000`
- Monitor logs in `artifacts/logs/`
- Track positions in real-time
- View P&L and performance metrics

---
*Auto-generated on 2025-11-15T21:51:37.957135+00:00*
