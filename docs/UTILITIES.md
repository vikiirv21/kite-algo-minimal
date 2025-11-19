# Utilities & Tools

## Overview

This document describes helper scripts and tools for managing the trading system.

## Scripts (`scripts/`)

### Trading & Execution

| Script | Description |
|--------|-------------|
| `analyze_paper_results.py` | Basic end-of-day analysis for paper trading results. |
| `dry_run_strategy_v2.py` | Dry run test for StrategyEngineV2. |
| `live_quotes.py` | Script: live_quotes.py |
| `run_all.py` | Script: run_all.py |
| `run_analytics.py` | Run Strategy Analytics Engine v1 |
| `run_backtest.py` | Script: run_backtest.py |
| `run_backtest_v1.py` | Backtest Runner v1 - Clean implementation using MarketDataEngine.replay() |
| `run_backtest_v3.py` | Backtest Runner v3 - CLI for running offline backtests. |
| `run_dashboard.py` | Run the FastAPI dashboard showing live-ish paper trading state. |
| `run_day.py` | Unified runbook for daily trading. |
| `run_indicator_scanner.py` | Script: run_indicator_scanner.py |
| `run_learning_engine.py` | Script: run_learning_engine.py |
| `run_paper_equity.py` | Run NSE equity intraday paper trading engine using configs/dev.yaml. |
| `run_paper_fno.py` | Script: run_paper_fno.py |
| `run_paper_options.py` | Run index options paper trading engine using configs/dev.yaml. |
| `run_session.py` | Market Session Orchestrator v1 |
| `run_trader.py` | Unified high-level entrypoint for PAPER and LIVE trading. |
| `show_paper_state.py` | Inspect paper broker state. |

### Analysis & Reporting

| Script | Description |
|--------|-------------|
| `analyze_and_learn.py` | End-of-day analyzer that proposes strategy overrides based on recent trades. |
| `analyze_paper_results.py` | Basic end-of-day analysis for paper trading results. |
| `analyze_performance.py` | Analyze paper trading performance based on artifacts. |
| `analyze_strategy_performance.py` | Analyze strategy-level performance based on orders.csv. |
| `replay_from_historical.py` | Script: replay_from_historical.py |
| `show_paper_state.py` | Inspect paper broker state. |

### Development & Utilities

| Script | Description |
|--------|-------------|
| `backfill_history.py` | Script: backfill_history.py |
| `demo_scanner.py` | Demonstration script showing the enhanced MarketScanner in action. |
| `demo_v3_trader_strategy.py` | End-to-End Demo: Trader -> Strategy Flow |
| `diag_kite_ws.py` | Diagnose Kite WebSocket connection health. |
| `generate_docs.py` | Auto-generate comprehensive documentation for the HFT trading system. |
| `login_kite.py` | Script: login_kite.py |
| `refresh_market_cache.py` | Refresh Market Data Cache Script |
| `test_v3_exec_flow.py` | Test script for Phase 4 Architecture v3 Execution Flow |
| `test_v3_strategy_flow.py` | Test script for Phase 2 Architecture v3 Strategy Flow |


## Tools (`tools/`)

| Tool | Description |
|------|-------------|
| `tools/docsync.py` | docsync.py |
| `tools/docs/repo_audit.py` | Tool: repo_audit.py |
| `tools/docs/generate_docs.py` | Auto-generate curated documentation for the HFT trading system. |


## Common Usage Examples

### Running Engines

```bash
# Paper trading (equity)
python scripts/run_paper_equity.py

# Paper trading (F&O)
python scripts/run_paper_fno.py

# Full day trading with login
python scripts/run_day.py --login --engines all
```

### Analysis & Monitoring

```bash
# Analyze paper trading results
python scripts/analyze_paper_results.py

# Show current paper state
python scripts/show_paper_state.py

# Analyze overall performance
python scripts/analyze_performance.py
```

### Development

```bash
# Generate documentation
python scripts/generate_docs.py

# Run tests
python scripts/test_v3_exec_flow.py
python scripts/test_v3_strategy_flow.py

# Demo/testing
python scripts/demo_scanner.py
python scripts/demo_v3_trader_strategy.py
```

### Authentication

```bash
# Login to Kite (interactive browser login)
python scripts/login_kite.py

# Test WebSocket connection
python scripts/diag_kite_ws.py
```

### Data Management

```bash
# Refresh market data cache
python scripts/refresh_market_cache.py

# Backfill historical data
python scripts/backfill_history.py

# Replay from historical data
python scripts/replay_from_historical.py
```

### Backtesting

```bash
# Run backtest v1
python scripts/run_backtest_v1.py

# Run backtest v3
python scripts/run_backtest_v3.py

# Run strategy-specific backtest
python scripts/run_backtest.py
```

## Helper Modules

### Risk Management
- `risk/adaptive_risk_manager.py` - Dynamic risk adjustment
- `risk/position_sizer.py` - Position sizing algorithms
- `risk/cost_model.py` - Trading cost models

### Data Management
- `data/broker_feed.py` - Broker data integration
- `data/instruments.py` - Instrument management
- `data/backtest_data.py` - Historical data for backtesting

### Configuration
- `config/` - Environment-specific configurations
- `configs/` - YAML configuration files

## Artifacts Directory

Runtime artifacts are stored in `artifacts/`:

```
artifacts/
├── checkpoints/     # State checkpoints
├── logs/            # System and trade logs
├── market_data/     # Cached market data
├── analytics/       # Performance reports
└── backtests/       # Backtest results
```

## Environment Variables

Key environment variables:
- `HFT_CONFIG` - Path to configuration file
- `KITE_DASHBOARD_CONFIG` - Dashboard-specific config
- Additional variables in `.env` file

## Development Tools

### Linting & Formatting
```bash
# (If configured in the project)
# ruff check .
# black .
```

### Testing
```bash
# Run tests (if pytest is configured)
python -m pytest tests/
```

---
*Auto-generated from repository structure*
