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

### Canonical Commands (Recommended)

The **run_trader** script is the primary entrypoint for starting PAPER and LIVE trading engines. It provides a simple, unified interface with sensible defaults.

#### PAPER Trading (Sandbox/Dev Mode)

```bash
# Simple, recommended usage (uses configs/dev.yaml, reuses tokens)
python -m scripts.run_trader paper

# With explicit config
python -m scripts.run_trader paper --config configs/dev.yaml

# Force Kite re-login and refresh tokens
python -m scripts.run_trader paper --login

# Run specific engines only
python -m scripts.run_trader paper --engines fno
python -m scripts.run_trader paper --engines options
```

#### LIVE Trading

⚠️ **WARNING: Real money at risk! LIVE mode requires explicit config.**

```bash
# Run LIVE trading (requires explicit config for safety)
python -m scripts.run_trader live --config configs/dev.yaml

# Force Kite re-login before starting
python -m scripts.run_trader live --login --config configs/dev.yaml

# Run specific engines only
python -m scripts.run_trader live --engines fno --config configs/dev.yaml
```

#### Token Reuse vs. Forced Login

By default, `run_trader` reuses existing Kite tokens from `secrets/kite_tokens.env` for fast startup:
- **No `--login` flag**: Reuses existing tokens (validates they're still valid)
- **With `--login` flag**: Forces interactive browser login and refreshes tokens

When to use `--login`:
- First time setup
- When tokens have expired (you'll see an error message)
- After extended downtime
- When you want to ensure fresh authentication

#### Command Hierarchy

The system has three layers of commands:

1. **`run_session`** (highest level): Full day orchestration with pre-market checks, monitoring, and analytics
2. **`run_trader`** (recommended): Canonical entrypoint for starting engines (PAPER or LIVE)
3. **`run_day`** (low-level): Direct engine wiring and management (advanced usage)

Most users should use `run_trader` or `run_session`. The `run_day` script is still available for advanced scenarios.

### Session Orchestrator (Full Day Lifecycle)

The Session Orchestrator manages the complete daily trading lifecycle including pre-market checks, engine startup, monitoring, and end-of-day analytics. It uses `run_trader` internally.

```bash
# Run full session with paper trading
python -m scripts.run_session --mode paper --config configs/dev.yaml

# Pre-market checks only (dry run)
python -m scripts.run_session --mode paper --config configs/dev.yaml --dry-run

# Run without end-of-day analytics and backtests
python -m scripts.run_session --mode paper --config configs/dev.yaml --no-analytics --no-backtest

# Run with live trading (⚠️ REAL MONEY!)
python -m scripts.run_session --mode live --config configs/dev.yaml
```

The Session Orchestrator:
- Performs pre-market checks (time, secrets, config, authentication)
- Starts all engines via `run_trader` or `run_day`
- Monitors engine execution
- Runs end-of-day analytics
- Generates daily reports in `artifacts/reports/daily/`

### Advanced: Direct Engine Control (run_day)

For advanced users who need fine-grained control, `run_day` is still available as a low-level interface:

```bash
# Run all engines in paper mode
python -m scripts.run_day --mode paper --engines all --config configs/dev.yaml

# Run with forced login
python -m scripts.run_day --login --mode paper --engines all --config configs/dev.yaml

# Run live mode
python -m scripts.run_day --mode live --engines all --config configs/dev.yaml

# Login only, don't start engines
python -m scripts.run_day --login --engines none
```

**Note**: Most users should use `run_trader` instead of `run_day` directly. The `run_day` script is considered a low-level tool and is invoked internally by `run_trader`.

### Legacy: Individual Engine Scripts

```bash
# These scripts are legacy and may be deprecated in the future
# Use run_trader instead for a unified experience

# Run paper trading for equities
python scripts/run_paper_equity.py

# Run paper trading for F&O
python scripts/run_paper_fno.py

# Run paper trading for options
python scripts/run_paper_options.py
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

### Morning Routine (Paper Trading)

```bash
# 1. (Optional) Refresh Kite login if tokens expired
python -m scripts.run_trader paper --login --engines none

# 2. Start paper trading with dashboard (recommended)
python -m scripts.run_trader paper

# Or use full session orchestrator
python -m scripts.run_session --mode paper --config configs/dev.yaml
```

### Morning Routine (Live Trading)

⚠️ **WARNING: Real money at risk!**

```bash
# 1. Login to Kite (if needed)
python -m scripts.run_trader live --login --engines none --config configs/dev.yaml

# 2. Refresh market cache
python scripts/refresh_market_cache.py

# 3. Start dashboard (optional, in separate terminal)
python scripts/run_dashboard.py &

# 4. Start live engine (after market open, verify config!)
python -m scripts.run_trader live --config configs/dev.yaml
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
