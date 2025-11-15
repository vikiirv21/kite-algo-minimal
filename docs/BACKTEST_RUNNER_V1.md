# Backtest Runner v1 - Documentation

## Overview

The Backtest Runner v1 (`scripts/run_backtest_v1.py`) is a clean implementation that uses MarketDataEngine to replay historical candle data and simulate trading strategies. It integrates seamlessly with StrategyEngine and RiskEngine to provide realistic backtest results.

## Key Features

- **MarketDataEngine Integration**: Uses `MarketDataEngine.replay()` to iterate through historical candles chronologically
- **Strategy Integration**: Leverages existing StrategyEngine and strategy registry
- **Risk Management**: Applies RiskEngine checks to all order intents
- **Realistic Simulation**: Uses BacktestBroker to simulate fills and track P&L
- **Comprehensive Output**: Generates detailed metrics, equity curves, and trade logs

## Usage

### Basic Command

```bash
python scripts/run_backtest_v1.py \
  --strategy ema20_50_intraday \
  --symbol NIFTY \
  --from 2024-01-01 \
  --to 2024-01-31
```

### Advanced Options

```bash
python scripts/run_backtest_v1.py \
  --config configs/dev.yaml \
  --strategy ema20_50_intraday \
  --symbol BANKNIFTY \
  --from 2024-01-01 \
  --to 2024-03-31 \
  --timeframe 1m \
  --capital 500000 \
  --qty 2
```

### Command Line Arguments

- `--config`: Path to config YAML file (default: `configs/dev.yaml`)
- `--strategy`: **Required** - Strategy code from `core.strategy_registry` (e.g., `ema20_50_intraday`)
- `--symbol`: **Required** - Logical symbol (e.g., `NIFTY`, `BANKNIFTY`)
- `--from`: **Required** - Start date in YYYY-MM-DD format
- `--to`: **Required** - End date in YYYY-MM-DD format
- `--timeframe`: Candle timeframe (e.g., `1m`, `5m`, `15m`). Defaults to strategy's default timeframe
- `--capital`: Starting capital (default: 1,000,000)
- `--qty`: Default order quantity per trade (default: 1)

## Output Structure

### Run ID Format

```
{strategy_code}_{symbol}_{timeframe}_{from_date}_{to_date}_{timestamp}
```

Example: `ema20_50_intraday_NIFTY_5m_2024-01-01_2024-01-31_20241115120530`

### Output Directory

```
artifacts/backtests/{run_id}/
├── result.json       # Complete backtest results with metrics
├── orders.csv        # All orders placed during backtest
├── fills.csv         # All order fills with P&L
└── trades.csv        # Completed trades with entry/exit details
```

### result.json Structure

```json
{
  "strategy": "ema20_50_intraday",
  "config": {
    "symbol": "NIFTY24DECFUT",
    "logical_name": "NIFTY",
    "timeframe": "5m",
    "from": "2024-01-01",
    "to": "2024-01-31",
    "capital": 1000000.0,
    "strategy": "ema20_50_intraday"
  },
  "summary": {
    "total_pnl": 12500.50,
    "win_rate": 65.00,
    "total_trades": 20,
    "wins": 13,
    "losses": 7,
    "max_drawdown": 2500.00,
    "max_drawdown_pct": 0.25,
    "final_equity": 1012500.50
  },
  "equity_curve": [
    ["2024-01-01T09:15:00+00:00", 1000000.0],
    ["2024-01-01T09:20:00+00:00", 1000250.0],
    ...
  ],
  "trades": [
    {
      "timestamp": "2024-01-01T09:30:00",
      "symbol": "NIFTY24DECFUT",
      "side": "BUY",
      "qty": 1,
      "entry_price": 19500.0,
      "exit_price": 19550.0,
      "pnl": 50.0,
      "holding_time": "00:15:00",
      "strategy_code": "ema20_50_intraday"
    },
    ...
  ]
}
```

## Architecture

### Flow Diagram

```
1. Load Configuration & Strategy
   ↓
2. Resolve Symbol (NIFTY → NIFTY24DECFUT)
   ↓
3. Initialize Components:
   - MarketDataEngine
   - BacktestEngine
   - StrategyRunner
   - RiskEngine
   ↓
4. Replay Loop:
   For each candle in date range:
     - Update broker with price
     - Record equity snapshot
     - Run strategy on tick
     - Strategy generates signal
     - RiskEngine validates order
     - Execute order (simulate fill)
     - Track P&L
   ↓
5. Generate Results:
   - Calculate metrics
   - Build equity curve
   - Compile trade list
   ↓
6. Write Output:
   - result.json
   - orders.csv
   - fills.csv
   - trades.csv
```

### Component Integration

**MarketDataEngine**
- Loads cached historical candles
- Provides `replay()` generator for chronological iteration
- Auto-fetches data if cache is missing

**StrategyEngine**
- Receives market ticks (candle closes)
- Runs enabled strategies
- Generates trading signals (BUY/SELL)

**RiskEngine**
- Validates order intents
- Enforces capital limits
- Applies position size constraints
- Can ALLOW, BLOCK, REDUCE, or HALT_SESSION

**BacktestBroker**
- Simulates order fills at provided prices
- Tracks positions and P&L
- Records equity curve
- Maintains trade history

## Symbol Resolution

The script resolves logical symbols to actual tradingsymbols in the following order:

1. **Universe Snapshot**: Checks `artifacts/universe.json` for symbol metadata
2. **FnO Resolver**: Falls back to `data.instruments.resolve_fno_symbols()` if Kite client available
3. **As-Is**: Uses logical symbol directly if resolution fails

Example:
```
NIFTY → NIFTY24DECFUT (from universe snapshot)
BANKNIFTY → BANKNIFTY24DECFUT (from universe snapshot)
CUSTOM → CUSTOM (as-is)
```

## Metrics Explained

### Performance Metrics

- **Total P&L**: Sum of all realized profits and losses
- **Win Rate**: Percentage of profitable trades
- **Total Trades**: Number of completed round-trip trades
- **Wins**: Number of profitable trades
- **Losses**: Number of losing trades
- **Final Equity**: Starting capital + total P&L + unrealized P&L

### Risk Metrics

- **Max Drawdown**: Maximum peak-to-trough decline in absolute terms
- **Max Drawdown %**: Maximum drawdown as percentage of peak equity

## Example Output

```
======================================================================
BACKTEST RESULTS
======================================================================
Run ID:           ema20_50_intraday_NIFTY_5m_2024-01-01_2024-01-31_20241115120530
Strategy:         ema20_50_intraday
Symbol:           NIFTY24DECFUT (NIFTY)
Timeframe:        5m
Period:           2024-01-01 to 2024-01-31
----------------------------------------------------------------------
Starting Capital: ₹1,000,000.00
Final Equity:     ₹1,012,500.50
Total P&L:        ₹12,500.50
Max Drawdown:     ₹2,500.00 (0.25%)
----------------------------------------------------------------------
Total Trades:     20
Wins:             13
Losses:           7
Win Rate:         65.00%
======================================================================
Results saved to: artifacts/backtests/ema20_50_intraday_NIFTY_5m_2024-01-01_2024-01-31_20241115120530
======================================================================
```

## Requirements

### Cache Data

Before running backtests, ensure historical data is cached:

```bash
# Refresh cache for specific symbols
python scripts/refresh_market_cache.py --symbols NIFTY BANKNIFTY --timeframe 5m --count 1000
```

The backtest will auto-fetch if cache is missing, but pre-warming is recommended for better performance.

### Strategy Registry

Strategy must be registered in `core.strategy_registry.STRATEGY_REGISTRY`:

```python
STRATEGY_REGISTRY = {
    "ema20_50_intraday": StrategyInfo(
        name="EMA 20-50 Intraday",
        strategy_code="ema20_50_intraday",
        timeframe="5m",
        version="1.0",
        enabled=True,
        tags=["equity", "intraday", "trend"],
    ),
}
```

## Differences from Original run_backtest.py

| Feature | Original | v1 |
|---------|----------|-----|
| Data Source | LocalCSVHistoricalSource | MarketDataEngine.replay() |
| Multiple Symbols | Yes | Single symbol per run |
| Multiple Strategies | Yes | Single strategy per run |
| Date Range | Multi-day scanner | Simple from/to dates |
| Output Format | JSON only | JSON + CSV files |
| Run ID | Simple timestamp | Detailed with symbol/dates |

## Troubleshooting

### No candles in date range

**Problem**: `Backtest complete: processed 0 candles`

**Solution**: 
1. Check if cache exists: `ls artifacts/market_data/{SYMBOL}_{TIMEFRAME}.json`
2. Refresh cache: `python scripts/refresh_market_cache.py --symbols SYMBOL --timeframe TIMEFRAME`
3. Verify date range matches cached data

### Strategy not found

**Problem**: `Strategy 'xyz' not found in registry`

**Solution**: Check `core.strategy_registry.STRATEGY_REGISTRY` for available strategies

### Symbol resolution fails

**Problem**: Symbol resolved incorrectly or not found

**Solution**:
1. Check `artifacts/universe.json` for symbol metadata
2. Manually specify tradingsymbol if needed
3. Update universe snapshot with scanner

## Future Enhancements

Potential improvements (not in current scope):

- Multi-symbol backtests
- Multi-strategy comparison
- Parameter optimization
- Walk-forward analysis
- Monte Carlo simulation
- Custom performance metrics
- Benchmark comparison
- Slippage and commission modeling

## Related Documentation

- [Market Data Engine v2](MARKET_DATA_ENGINE_V2.md)
- Strategy Development Guide (TBD)
- Risk Engine Configuration (TBD)
