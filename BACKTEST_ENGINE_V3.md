# Backtest Engine v3 Documentation

## Overview

Backtest Engine v3 is an offline backtesting framework that reuses the same core components as live/paper trading:
- **StrategyEngine v2/v3**: Strategy orchestration and signal generation
- **PortfolioEngine v1**: Position sizing and capital management
- **RegimeEngine v2**: Market regime detection
- **RiskEngine v2**: Risk management and checks
- **TradeGuardian**: Pre-execution validation (optional)
- **ExecutionEngine**: Simulated fills (sim-only mode)

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    BacktestEngineV3                         │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  HistoricalDataLoader (CSV/HDF/Kite API)           │  │
│  └──────────────────────────────────────────────────────┘  │
│                          ↓                                  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  For each bar:                                       │  │
│  │    1. Update RegimeEngine                           │  │
│  │    2. Generate signals (StrategyEngine v2)          │  │
│  │    3. Size positions (PortfolioEngine)              │  │
│  │    4. Apply risk checks (RiskEngine)                │  │
│  │    5. Validate (TradeGuardian - optional)           │  │
│  │    6. Simulate fills                                │  │
│  │    7. Update state & journal                        │  │
│  └──────────────────────────────────────────────────────┘  │
│                          ↓                                  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Compute Results (StrategyAnalyticsEngine)          │  │
│  └──────────────────────────────────────────────────────┘  │
│                          ↓                                  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Output: summary.json, trades.csv, equity_curve.json│  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Key Features

### 1. Complete Isolation
- **No broker connections**: Runs entirely offline
- **No token/auth code**: No login or credentials needed
- **Separate artifacts**: All outputs go to `artifacts/backtests/{run_id}/`
- **No interference**: Does not modify live/paper paths

### 2. Core Component Reuse
Reuses production components for maximum fidelity:
- Same strategies as live trading
- Same position sizing logic
- Same risk management rules
- Same regime detection

### 3. Multiple Data Sources
- **CSV**: Load from `artifacts/market_data/*.csv`
- **HDF5**: (Future) Load from HDF5 files
- **Kite Historical API**: (Future) Fetch historical data

### 4. Comprehensive Outputs
- `config.json`: Backtest configuration
- `summary.json`: Complete results with metrics
- `trades.csv`: All trades/fills
- `equity_curve.json`: Equity over time
- Journal files: Order/fill logs

## Usage

### Basic Usage

```bash
# Run backtest with default config
python -m scripts.run_backtest_v3 \
    --config configs/dev.yaml \
    --symbols NIFTY,BANKNIFTY \
    --start 2025-01-01 \
    --end 2025-01-05 \
    --data-source csv \
    --timeframe 5m
```

### Using Backtest Config File

```bash
# Use separate backtest config
python -m scripts.run_backtest_v3 \
    --config configs/dev.yaml \
    --bt-config configs/backtest.dev.yaml \
    --start 2025-01-01 \
    --end 2025-01-05
```

### Advanced Options

```bash
# With custom settings
python -m scripts.run_backtest_v3 \
    --config configs/dev.yaml \
    --symbols NIFTY \
    --strategies ema20_50_intraday_v2 \
    --start 2025-01-01 \
    --end 2025-01-05 \
    --data-source csv \
    --timeframe 5m \
    --initial-equity 100000 \
    --position-sizing fixed_qty \
    --enable-guardian \
    --log-level DEBUG
```

## Configuration

### Main Config (configs/dev.yaml)

Uses existing config sections:
- `portfolio`: Position sizing, budgets, leverage
- `risk`: Risk management rules
- `regime`: Regime detection parameters
- `guardian`: Trade guardian settings

### Backtest Config (configs/backtest.dev.yaml)

```yaml
backtest:
  symbols:
    - "NIFTY"
    - "BANKNIFTY"
  
  strategies:
    - "ema20_50_intraday_v2"
  
  start_date: "2025-01-01"
  end_date: "2025-01-05"
  
  data_source: "csv"
  timeframe: "5m"
  
  initial_equity: 100000.0
  position_sizing_mode: "fixed_qty"
  
  enable_guardian: false
```

## Data Preparation

### CSV Format

Place CSV files in `artifacts/market_data/` with naming convention:
- `{SYMBOL}_{TIMEFRAME}.csv` (all data)
- `{SYMBOL}_{DATE}_{TIMEFRAME}.csv` (date-specific)

CSV structure:
```csv
timestamp,open,high,low,close,volume
2025-01-01T09:15:00+00:00,24000.0,24050.0,23990.0,24020.0,1000000
2025-01-01T09:20:00+00:00,24020.0,24080.0,24010.0,24060.0,1100000
```

Supported timestamp formats:
- ISO 8601 with timezone: `2025-01-01T09:15:00+00:00`
- ISO 8601 with Z: `2025-01-01T09:15:00Z`
- Simple: `2025-01-01 09:15:00`

## Output Structure

```
artifacts/backtests/{run_id}/
├── config.json              # Backtest configuration
├── summary.json             # Complete results and metrics
├── trades.csv               # All trades (if any)
├── equity_curve.json        # Equity snapshots over time
├── state_checkpoint.json    # Final state
├── events.jsonl            # Event log
└── journal/                # Isolated journal directory
    └── {date}/
        └── orders.csv      # Order/fill logs
```

### summary.json Structure

```json
{
  "run_id": "bt_20251116_180924_b89f9c2e",
  "config": {
    "symbols": ["NIFTY"],
    "strategies": ["ema20_50_intraday_v2"],
    "start_date": "2025-01-01",
    "end_date": "2025-01-05",
    "data_source": "csv",
    "timeframe": "5m",
    "initial_equity": 100000.0
  },
  "equity_curve": [
    {
      "timestamp": "2025-01-01T09:15:00+00:00",
      "equity": 100000.0,
      "cash": 100000.0,
      "unrealized_pnl": 0.0,
      "bar_index": 1
    }
  ],
  "per_strategy": {
    "ema20_50_intraday_v2": {
      "trades": 0,
      "pnl": 0.0,
      "win_rate": 0.0
    }
  },
  "per_symbol": {
    "NIFTY": {
      "trades": 0,
      "pnl": 0.0,
      "win_rate": 0.0
    }
  },
  "trades": [],
  "overall_metrics": {
    "initial_equity": 100000.0,
    "final_equity": 100000.0,
    "total_return": 0.0,
    "total_return_pct": 0.0,
    "total_trades": 0,
    "bars_processed": 31
  }
}
```

## CLI Arguments

### Required
- `--config`: Main trading config YAML file
- `--start`: Start date (YYYY-MM-DD)
- `--end`: End date (YYYY-MM-DD)

### Optional
- `--bt-config`: Backtest-specific config file
- `--symbols`: Comma-separated symbol list
- `--strategies`: Comma-separated strategy codes
- `--data-source`: Data source (csv|hdf|kite_historical)
- `--timeframe`: Bar timeframe (1m|5m|15m|1h|1d)
- `--initial-equity`: Starting capital
- `--position-sizing`: Position sizing mode (fixed_qty|fixed_risk_atr)
- `--enable-guardian`: Enable TradeGuardian checks
- `--log-level`: Logging level (DEBUG|INFO|WARNING|ERROR)

## Testing

Run the test suite:

```bash
python tests/test_backtest_engine_v3.py
```

Tests cover:
- Configuration initialization
- Data loading
- Engine initialization
- Full backtest execution
- Output file generation
- Isolation from live/paper paths

## Safety Guarantees

### What Backtest Engine v3 DOES NOT Do
- ❌ Contact brokers or execute real trades
- ❌ Require authentication or tokens
- ❌ Modify live/paper state or journals
- ❌ Import or run live trading code
- ❌ Interfere with `run_day` or `run_trader` scripts

### What Backtest Engine v3 DOES
- ✅ Run completely offline on historical data
- ✅ Reuse core components for accuracy
- ✅ Write outputs to isolated directory
- ✅ Provide structured analytics
- ✅ Support multiple data sources
- ✅ Generate reproducible results

## Extension Points

### Adding Data Sources

Extend `HistoricalDataLoader` in `backtest/data_loader.py`:

```python
def _iter_bars_hdf(self, symbol, start_date, end_date):
    """Load bars from HDF5 files."""
    # Implementation here
    pass
```

### Custom Analytics

Integrate with `StrategyAnalyticsEngine` for advanced metrics:

```python
from analytics.strategy_analytics import StrategyAnalyticsEngine

analytics = StrategyAnalyticsEngine(
    journal_store=engine.journal_store,
    state_store=engine.state_store,
    logger=logger,
)
analytics.load_fills(today_only=False)
metrics = analytics.compute_metrics()
```

### Strategy Integration

Future enhancement: Full StrategyEngine v2 integration with actual strategy execution.

## Troubleshooting

### No bars loaded
- Check CSV files exist in `artifacts/market_data/`
- Verify file naming: `{SYMBOL}_{TIMEFRAME}.csv`
- Check timestamp format in CSV

### Import errors
- Install dependencies: `pip install -r requirements.txt`
- Verify Python path includes repository root

### Permission errors
- Check write permissions on `artifacts/` directory
- Verify `logs/` directory is writable

## Future Enhancements

- [ ] HDF5 data source support
- [ ] Kite historical API integration
- [ ] Full StrategyEngine v2 integration
- [ ] Multi-symbol coordinated execution
- [ ] Advanced analytics (Sharpe, drawdown, etc.)
- [ ] Dashboard integration for visualization
- [ ] Parallel backtesting
- [ ] Walk-forward optimization
- [ ] Parameter sensitivity analysis

## Related Documentation

- [Portfolio Engine](PORTFOLIO_ENGINE_IMPLEMENTATION.md)
- [Strategy Engine v3](STRATEGY_ENGINE_V3_SUMMARY.md)
- [Risk Engine](core/risk_engine_v2.py)
- [Trade Guardian](TRADE_GUARDIAN_SUMMARY.md)
