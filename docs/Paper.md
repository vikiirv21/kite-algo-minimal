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

## Running Paper Mode

### Start Paper Engine

```bash
# Default (paper mode via config)
python -m scripts.run_day --engines fno

# Explicit paper mode
python -m scripts.run_day --mode paper --engines fno

# With login
python -m scripts.run_day --login --mode paper --engines all
```

### Engine Options

- `--engines fno`: FnO futures only
- `--engines options`: Index options only
- `--engines equity`: Equity only
- `--engines all`: All engines
- `--engines none`: Login only (no trading)

## Configuration

Basic config for Paper mode:

```yaml
trading:
  mode: "paper"
  paper_capital: 500000  # Starting capital in INR
  
  logical_universe:
    - "NIFTY"
    - "BANKNIFTY"
    - "FINNIFTY"
  
  max_daily_loss: 3000  # Max loss in INR
  per_symbol_max_loss: 1500  # Per-symbol loss limit
  max_loss_pct_per_trade: 0.01  # 1% per-trade stop
  
  default_lot_size: 1
  
risk:
  risk_per_trade_pct: 0.005  # 0.5% risk per trade
  max_exposure_pct: 2.0  # 200% max notional exposure
  max_concurrent_trades: 10
```

## Artifacts & State

### Checkpoint Path

`artifacts/checkpoints/paper_state_latest.json`

Contains:
- Current positions
- Realized and unrealized P&L
- Open orders
- Strategy metrics
- Last update timestamp

### Journal Path

`artifacts/journal/<YYYY-MM-DD>/`

Files:
- `orders.csv`: All order executions
- `fills.csv`: Order fills (same as orders in paper mode)
- `trades.csv`: Complete trades (entry + exit)
- `equity.csv`: Equity curve snapshots

### Example Order Record

```csv
timestamp,order_id,symbol,side,quantity,price,status,strategy,pnl
2024-01-15T10:30:00Z,paper-12345-1,NIFTY24JANFUT,BUY,25,21500,FILLED,ema20_50_intraday,0.0
2024-01-15T11:45:00Z,paper-12346-2,NIFTY24JANFUT,SELL,25,21550,FILLED,ema20_50_intraday,1250.0
```

## Features

### Position Management

- **Long and Short**: Support for both directions
- **Averaging**: Multiple entries average entry price
- **Partial Exits**: Reduce position size gradually
- **Automatic P&L**: Realized on exits, unrealized on open

### Risk Controls

1. **Per-Trade Stop Loss**: Percentage-based stop per position
2. **Per-Symbol Loss Limit**: Symbol banned after reaching limit
3. **Daily Loss Limit**: Engine stops when reached
4. **Position Sizing**: Dynamic sizing based on risk and capital
5. **Max Notional Exposure**: Caps total position size

### Trailing Stops

```yaml
trading:
  enable_trailing_stops: true
  trail_start_r_multiple: 1.0  # Start trailing at 1R profit
  trail_step_r_multiple: 0.5  # Trail 0.5R behind peak
  trail_lock_r_multiple: 0.5  # Lock in 0.5R minimum
```

### ATR-Based Stop Loss

```yaml
risk:
  atr:
    enabled: true
    lookback: 14
    sl_r_multiple: 1.0  # Stop loss = entry ± 1 ATR
    tp_r_multiple: 2.0  # Take profit = entry ± 2 ATR
    hard_sl_pct_cap: 0.03  # Max 3% stop
    hard_tp_pct_cap: 0.06  # Max 6% target
```

## Monitoring

### Real-Time State

Check current state:
```bash
python -m scripts.show_paper_state
```

### Performance Analysis

```bash
python -m scripts.analyze_paper_results
```

Shows:
- Total P&L
- Win rate
- Average R multiple
- Largest win/loss
- Trade distribution
- Strategy breakdown

### Dashboard

Run the web dashboard:
```bash
python -m scripts.run_dashboard
```

Access at: `http://localhost:8000`

## Strategy Engine Integration

Paper mode supports both v1 and v2 strategy engines:

### Strategy Engine v1 (Legacy)

```yaml
# Enabled by default if v2 not configured
```

### Strategy Engine v2

```yaml
strategy_engine:
  version: 2
  window_size: 200
  strategies_v2:
    - "ema20_50_intraday_v2"
```

Strategies inherit from `BaseStrategy` and implement:
- `generate_signal()`: Produce BUY/SELL/EXIT/HOLD
- State management
- Indicator calculations

## Meta Strategy Engine

Combines multiple timeframes and styles:

```yaml
meta:
  enabled: true
  symbols_focus:
    - "NIFTY"
  styles:
    - "intraday"
    - "swing"
```

## Testing Strategies

### Backtesting

Use `scripts/run_backtest.py` for historical testing.

### Paper Forward Testing

Run paper mode live during market hours to test strategies in real-time without risk.

### Replay Mode

```yaml
trading:
  mode: "replay"
  replay_date: "2024-01-15"
```

Replays historical data through the engine.

## Differences from Live Mode

| Aspect | Paper | Live |
|--------|-------|------|
| Order Execution | Instant | Real broker API |
| Fill Price | Requested price | Market price |
| Slippage | None (configurable) | Real |
| Costs | Optional simulation | Real brokerage |
| Latency | Zero | Network + broker |
| Risk | Zero | Real capital |
| Validation | Pre-deployment | Production |

## Best Practices

1. **Start in Paper**: Always test new strategies in paper mode first
2. **Realistic Capital**: Use capital amount you'd trade live
3. **Include Costs**: Enable cost model for realistic results
4. **Track Metrics**: Review performance regularly
5. **Risk Sizing**: Use same risk as you would live
6. **Market Hours**: Test during actual market hours
7. **Data Quality**: Ensure market data feed is reliable
8. **Journaling**: Review orders and trades post-session

## Limitations

### No Slippage

Paper mode fills at exact price. Live may experience:
- Bid-ask spread
- Market impact
- Partial fills

### Instant Execution

Paper orders fill immediately. Live orders may:
- Wait in queue
- Get rejected
- Experience delays

### Perfect Data

Paper mode assumes perfect data feed. Live may have:
- Tick delays
- Missing data
- Feed interruptions

### Psychological Factors

Paper trading doesn't account for:
- Emotional decision-making
- Fear and greed
- Real money stress

## Enhancements

### Cost Model

Add realistic brokerage simulation:

```yaml
risk:
  cost_model:
    enabled: true
    brokerage_per_order: 20.0
    exchange_txn_charge: 0.00053
    stt: 0.00025
    gst: 0.18
```

### Quality Filters

Filter low-quality signals:

```yaml
risk:
  trade_quality:
    enabled: true
    min_edge_bps: 20
    max_cost_bps: 10
```

## Troubleshooting

### Engine Not Starting

- Check config file syntax
- Verify Kite credentials
- Review error logs

### No Signals Generated

- Check universe configuration
- Verify strategy is enabled
- Review market data availability

### Orders Not Filling

- Should never happen in paper mode
- Check PaperBroker state
- Review logs for exceptions

### State Not Saving

- Check file permissions
- Verify artifacts directory exists
- Review checkpoint logs

## Migration to Live

When ready to go live:

1. Review paper performance over multiple days/weeks
2. Verify win rate and risk metrics are acceptable
3. Test with minimal position size first
4. Gradually increase size as confidence builds
5. Monitor closely for differences from paper

## Support

For questions or issues:
- Review logs in `artifacts/logs/`
- Check journal files for trade details
- Analyze performance metrics
- Verify configuration settings
