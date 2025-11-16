# Backtesting Engine

## Overview

The backtesting engine allows historical testing of strategies using past market data.

## Architecture

### Components

1. **BacktestBroker** (`broker/backtest_broker.py`)
   - Historical fill simulation
   - Slippage modeling
   - Commission tracking

2. **BacktestRunner** (`scripts/run_backtest.py`)
   - Data replay orchestration
   - Performance calculation
   - Report generation

3. **BacktestData** (`data/backtest_data.py`)
   - Historical data loading
   - Candle reconstruction
   - Tick simulation

## Running Backtests

### Basic Backtest

```bash
python scripts/run_backtest.py \
  --strategy EMA_20_50 \
  --symbol NIFTY \
  --start 2024-01-01 \
  --end 2024-03-31 \
  --capital 100000
```

### Multi-Strategy Backtest

```bash
python scripts/run_backtest.py \
  --strategies EMA_20_50,MEAN_REV \
  --symbols NIFTY,BANKNIFTY \
  --start 2024-01-01 \
  --end 2024-12-31
```

## Performance Metrics

### Return Metrics
- **Total Return**: Absolute profit/loss
- **Return %**: Percentage return on capital
- **CAGR**: Annualized return
- **Sharpe Ratio**: Risk-adjusted return

### Risk Metrics
- **Max Drawdown**: Largest peak-to-trough decline
- **Win Rate**: Percentage of winning trades
- **Avg Win/Loss**: Average profit vs loss
- **Profit Factor**: Gross profit / gross loss

### Trade Metrics
- **Total Trades**: Number of round trips
- **Win Trades**: Number of profitable trades
- **Loss Trades**: Number of losing trades
- **Avg Trade Duration**: Average holding period

## Backtest Reports

### Console Output

```
=== Backtest Results ===
Strategy: EMA_20_50
Period: 2024-01-01 to 2024-03-31
Initial Capital: ₹100,000

Total Return: ₹12,500 (12.5%)
Max Drawdown: ₹3,200 (3.2%)
Sharpe Ratio: 1.85
Win Rate: 62.5%

Total Trades: 48
Winning: 30
Losing: 18
Avg Win: ₹850
Avg Loss: ₹420
```

### CSV Report

Detailed trade-by-trade report saved to `artifacts/backtests/`.

### Equity Curve

Visual representation of capital over time.

## Configuration

```yaml
backtest:
  slippage_pct: 0.05
  commission_per_trade: 20
  start_date: "2024-01-01"
  end_date: "2024-03-31"
  capital: 100000
```

## Data Requirements

- Historical OHLCV candles
- Sufficient lookback period for indicators
- Clean, validated data (no gaps)

## Limitations

- **Look-Ahead Bias**: Ensure no future data leakage
- **Overfitting**: Beware of curve-fitting parameters
- **Market Impact**: Assumes no slippage beyond model
- **Regime Changes**: Past ≠ future performance

## Best Practices

1. **Walk-Forward Testing**: Rolling window validation
2. **Out-of-Sample**: Test on unseen data
3. **Multiple Periods**: Test across market regimes
4. **Realistic Costs**: Include slippage and commissions
5. **Robustness**: Test parameter sensitivity

---
*Auto-generated on 2025-11-15T21:51:37.969217+00:00*
