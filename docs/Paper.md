# Paper Trading Mode

## Overview

The **Paper Trading Engine** simulates trading without placing real orders. It provides a risk-free environment to test strategies and track hypothetical performance.

## Architecture

### Core Components

- **PaperEngine** (`engine/paper_engine.py`): Main paper trading orchestrator
- **PaperBroker** (`broker/paper_broker.py`): In-memory position tracking
- **StrategyEngine v2**: Strategy logic and signal generation
- **RiskEngine**: Risk checks and position sizing
- **MarketDataEngine**: Market data fetching and caching

### Execution Router

The `ExecutionRouter` in paper mode routes all orders to `PaperBroker`:
- Orders filled instantly at requested price
- No slippage simulation (optional enhancement)
- No brokerage costs (unless using CostModel)

## How It Works

1. **Initialization**
   - Loads config and paper capital amount
   - Initializes in-memory broker with zero positions
   - Sets up strategy and risk engines
   - Configures universe of symbols to trade

2. **Main Loop**
   - Fetches LTP (Last Traded Price) for each symbol
   - Runs strategy engine to generate signals
   - Validates signals through risk engine
   - Places simulated orders via PaperBroker
   - Updates positions and P&L

3. **Position Tracking**
   - Entry price averaging for multiple entries
   - Realized P&L on exits
   - Unrealized P&L on open positions
   - Position-level stop loss tracking

4. **State Management**
   - Periodic checkpoints to disk
   - Order and fill journaling
   - Equity curve snapshots
   - Trade performance metrics

## Key Classes

### ActiveTrade

**Methods:**
- `direction_multiplier()`
- `update_price()`

### PaperEngine

Paper engine for FnO symbols (NIFTY, BANKNIFTY, FINNIFTY).

Flow:
- Read logical FnO names from config.
- Resolve them to current NFO FUT tradingsymbols using instruments().
- Initialize paper broker, execution router, data feed, and strategy.
- Loop (only when market is open):
  - For each symbol:
    - Fetch LTP from NFO.
    - Run strategy to get signal.
    - Record every signal (with strategy tag in 'logical').
    - If BUY/SELL:
      - Check capital / notional constraints.
      - Enforce per-symbol loss limit ("kill switch").
      - Place order via ExecutionRouter (PAPER by default).
      - Record order.
  - Enforce per-trade max loss (stop-loss per position).
  - Periodically snapshot paper broker state, including P&L metrics.
  - Enforce global and per-symbol risk checks.

**Methods:**
- `__init__()`
- `run_forever()`


## Running Paper Mode

```bash
# Run paper trading for equities
python scripts/run_paper_equity.py

# Run paper trading for F&O
python scripts/run_paper_fno.py
```

## Configuration

Paper mode configuration in `configs/config.yaml`:

```yaml
trading:
  mode: PAPER
  paper_capital: 100000
  
risk:
  max_positions_total: 5
  per_trade_risk_pct: 2.0
```

## Benefits

- **Risk-Free Testing**: No real capital at risk
- **Fast Iteration**: Quick strategy validation
- **Full Logging**: Complete audit trail
- **Realistic Simulation**: Same code path as live

## Limitations

- **Instant Fills**: No slippage or partial fills
- **No Market Impact**: Assumes infinite liquidity
- **Perfect Execution**: No rejected orders

---
*Auto-generated on 2025-11-15T21:51:37.952533+00:00*
