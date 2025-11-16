# Common Commands

## Overview

This document lists common CLI commands for running and managing the trading system.

## Authentication

### Login to Kite

```bash
# Interactive login (opens browser)
python scripts/login_kite.py
```

## Trading Modes

### Paper Trading

```bash
# Run paper trading for equities
python scripts/run_paper_equity.py

# Run paper trading for F&O
python scripts/run_paper_fno.py

# Run paper trading for options
python scripts/run_paper_options.py
```

### Live Trading

⚠️ **WARNING: Real money at risk!**

```bash
# Run live trading
python scripts/run_live.py

# Or use specific engine
python -m engine.live_engine
```

### Backtesting

```bash
# Run backtest
python scripts/run_backtest.py --strategy EMA_20_50 --symbol NIFTY

# Run backtest v1
python scripts/run_backtest_v1.py
```

## Analysis & Reporting

### Performance Analysis

```bash
# Analyze paper trading results
python scripts/analyze_paper_results.py

# Analyze overall performance
python scripts/analyze_performance.py

# Show paper state
python scripts/show_paper_state.py
```

### Strategy Analysis

```bash
# Run indicator scanner
python scripts/run_indicator_scanner.py

# Analyze and learn
python scripts/analyze_and_learn.py
```

## Dashboard

### Start Dashboard

```bash
# Run dashboard
python scripts/run_dashboard.py

# Or use uvicorn directly
uvicorn ui.dashboard:app --host 0.0.0.0 --port 8000
```

## Data Management

### Refresh Market Cache

```bash
# Refresh cached market data
python scripts/refresh_market_cache.py
```

### Historical Replay

```bash
# Replay from historical data
python scripts/replay_from_historical.py
```

## Diagnostics

### WebSocket Diagnostics

```bash
# Test Kite WebSocket connection
python scripts/diag_kite_ws.py
```

### State Inspection

```bash
# Show current state
python scripts/show_paper_state.py
```

## Development

### Run Tests

```bash
# Run all tests
python -m pytest tests/

# Run specific test
python -m pytest tests/test_strategy_engine_v2.py

# Run with coverage
python -m pytest --cov=. tests/
```

### Generate Documentation

```bash
# Regenerate all documentation
python scripts/generate_docs.py
```

## Configuration

### Edit Configuration

```bash
# Edit main config
nano configs/config.yaml

# Edit environment variables
nano .env
```

### View Configuration

```bash
# View current config
cat configs/config.yaml
```

## Logs

### View Logs

```bash
# View engine logs
tail -f artifacts/logs/engine.log

# View JSON logs
tail -f artifacts/logs/events.jsonl

# View all logs
tail -f artifacts/logs/*.log
```

### Clear Logs

```bash
# Clear old logs (careful!)
rm artifacts/logs/*.log
```

## Artifacts

### View Artifacts

```bash
# List checkpoints
ls -lah artifacts/checkpoints/

# List market data cache
ls -lah artifacts/market_data/

# List backtest results
ls -lah artifacts/backtests/
```

## Common Workflows

### Morning Routine (Live Trading)

```bash
# 1. Login to Kite
python scripts/login_kite.py

# 2. Refresh market cache
python scripts/refresh_market_cache.py

# 3. Start dashboard
python scripts/run_dashboard.py &

# 4. Start live engine (after market open)
python scripts/run_live.py
```

### Evening Routine

```bash
# 1. Analyze day's performance
python scripts/analyze_performance.py

# 2. Review logs
tail -100 artifacts/logs/engine.log

# 3. Backup state
cp artifacts/checkpoints/runtime_state_latest.json backups/
```

### Strategy Development

```bash
# 1. Test in paper mode
python scripts/run_paper_equity.py

# 2. Analyze results
python scripts/analyze_paper_results.py

# 3. Backtest on historical data
python scripts/run_backtest.py --strategy NEW_STRATEGY

# 4. Review metrics
# 5. Refine and repeat
```

---
*Auto-generated on 2025-11-15T21:51:37.969522+00:00*
