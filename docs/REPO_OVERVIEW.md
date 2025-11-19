# Repository Overview – kite-algo-minimal

> **Status**: CURRENT – Last updated: 2025-11-19  
> **Purpose**: High-level summary of the entire repository for new developers and AI agents

---

## Table of Contents

1. [Purpose & Scope](#purpose--scope)
2. [High-Level Architecture](#high-level-architecture)
3. [Environments & Modes](#environments--modes)
4. [Main Entry Points & CLIs](#main-entry-points--clis)
5. [Directory Map](#directory-map)
6. [Quick Start](#quick-start)
7. [Related Documentation](#related-documentation)

---

## Purpose & Scope

**kite-algo-minimal** is a high-frequency trading (HFT) system built for the Indian markets using the Zerodha Kite Connect API. It supports:

- **Multi-asset trading**: Equity, FnO Futures, and Index Options
- **Paper and Live trading**: Realistic paper simulation + production-ready live execution
- **Multi-strategy fusion**: Multiple strategies can run simultaneously with confidence-based signal fusion
- **Real-time dashboard**: Modern React-based UI with FastAPI backend
- **Offline backtesting**: Historical simulation using actual live components
- **Analytics & telemetry**: Performance tracking, trade journal, and daily reports

### Key Features

- **Strategy Engine v3**: Multi-timeframe confirmation, unified indicator bundles, playbook-based setup classification
- **Execution Engine v3**: Unified paper/live execution with realistic slippage simulation
- **Market Data Engine**: Real-time tick processing with multi-timeframe candle building
- **Risk Management**: Position sizing, circuit breakers, drawdown limits, trade guardian
- **Regime Detection**: Trend, volatility, and market structure classification
- **Portfolio Engine**: Multi-strategy capital allocation and exposure management
- **Dashboard**: 7-page React app with real-time updates, P&L tracking, log viewer, and analytics
- **Multi-Process Architecture**: Run each engine (Equity, FnO, Options) as a separate process

---

## High-Level Architecture

The system consists of several major components:

### 1. **Engines (Trading Cores)**

Three specialized trading engines handle different asset classes:

- **Equity Paper Engine** (`engine/equity_paper_engine.py`): Trades NIFTY 50/100 stocks in paper mode
- **FnO Paper Engine** (FnO logic in `engine/paper_engine.py`): Trades index futures (NIFTY, BANKNIFTY, FINNIFTY)
- **Options Paper Engine** (`engine/options_paper_engine.py`): Trades index options with strike selection logic

Each engine:
- Fetches market data via Kite Connect
- Evaluates strategies via Strategy Engine
- Executes trades via Execution Engine
- Records state, orders, and fills to artifacts/

### 2. **Strategy Engines**

Three generations of strategy architecture:

- **Strategy Engine v1** (legacy): Bar-based strategies in `strategies/` directory
- **Strategy Engine v2** (`core/strategy_engine_v2.py`): Modern indicator-based architecture
- **Strategy Engine v3** (`core/strategy_engine_v3.py`): Multi-strategy fusion with multi-timeframe confirmation

All strategies output `OrderIntent` objects with signal, confidence, and reasoning.

### 3. **Execution Layer**

- **Execution Engine v3** (`core/execution_engine_v3.py`): Unified interface for paper and live execution
  - **Paper Execution**: Realistic fills with configurable slippage
  - **Live Execution**: Production-ready with retry logic and reconciliation
- **Broker Adapters**: Paper broker, live broker, backtest broker

### 4. **Dashboard & API**

- **Backend**: FastAPI server (`apps/server.py`) serving REST API
- **Frontend**: React + TypeScript + Tailwind CSS (`ui/frontend/`)
- **API Endpoints**: State, positions, orders, logs, analytics, health checks
- **Static Build**: Pre-built React app served from `static/` directory

Dashboard provides:
- Portfolio overview (equity, P&L, margin)
- Real-time positions and orders
- Strategy signals and performance
- Engine logs with filtering
- Analytics and equity curve

### 5. **Market Scanner & Universe Builder**

- **Universe Builder** (`core/universe_builder.py`): Builds daily universe of tradeable symbols
- **Market Scanner**: Filters stocks based on price, volume, and technical criteria
- **Output**: `artifacts/scanner/YYYY-MM-DD/universe.json`

### 6. **State & Persistence**

All runtime state and analytics stored in `artifacts/`:

- **Checkpoints**: `artifacts/checkpoints/runtime_state_latest.json`
- **Orders**: Orders CSV per engine per day
- **Snapshots**: Position snapshots at intervals
- **Logs**: Engine logs, event logs (JSONL format)
- **Reports**: Daily analytics reports (`artifacts/reports/daily/YYYY-MM-DD.json`)
- **Scanner Output**: `artifacts/scanner/YYYY-MM-DD/universe.json`

### 7. **Analytics & Telemetry**

- **Telemetry Bus** (`analytics/telemetry_bus.py`): Event-driven logging of orders, signals, positions
- **Trade Journal** (`analytics/trade_journal.py`): Per-trade analysis with entry/exit tracking
- **Performance Analytics** (`analytics/performance_v2.py`): P&L, Sharpe, win rate, max drawdown
- **Learning Engine** (`analytics/learning_engine.py`): Strategy parameter optimization (experimental)

---

## Environments & Modes

### Trading Modes

1. **Paper Mode** (`mode: paper`):
   - Simulated execution with realistic fills
   - Uses paper capital (default: ₹500,000)
   - No actual broker orders placed
   - Ideal for testing strategies

2. **Live Mode** (`mode: live`):
   - Real broker orders via Kite Connect
   - Requires valid access token
   - Production-ready with reconciliation
   - Use with caution!

### Process Layouts

1. **Single-Process (default)**:
   - All engines run as threads in one Python process
   - Simpler, good for development
   - Command: `python -m scripts.run_session --mode paper --config configs/dev.yaml`

2. **Multi-Process** (new):
   - Each engine runs as a separate Python process
   - Better isolation, scales to high-frequency workloads
   - Command: `python -m scripts.run_session --mode paper --config configs/dev.yaml --layout multi`
   - Or run individual engines: `python -m apps.run_equity_paper --config configs/dev.yaml`

### Configuration Files

- **configs/dev.yaml**: Main development config (paper mode, all features enabled)
- **configs/backtest.dev.yaml**: Backtest-specific config
- **configs/strategy_engine_v3.yaml**: Strategy engine v3 config (strategies, playbooks, timeframes)
- **configs/risk_overrides.yaml**: Runtime risk parameter overrides
- **configs/learned_overrides.yaml**: Learning engine outputs

---

## Main Entry Points & CLIs

### Daily Trading Session

```bash
# Run complete trading session (pre-market checks → trading → analytics)
python -m scripts.run_session --mode paper --config configs/dev.yaml

# Multi-process mode
python -m scripts.run_session --mode paper --config configs/dev.yaml --layout multi

# Dry run (skip actual trading)
python -m scripts.run_session --mode paper --config configs/dev.yaml --dry-run
```

### Individual Engines

```bash
# Run equity engine only
python -m apps.run_equity_paper --config configs/dev.yaml --mode paper

# Run FnO engine only
python -m apps.run_fno_paper --config configs/dev.yaml --mode paper

# Run options engine only
python -m apps.run_options_paper --config configs/dev.yaml --mode paper
```

### Dashboard

```bash
# Build React frontend (first time only)
./build-dashboard.sh

# Start server (backend + static frontend)
python -m uvicorn apps.server:app --host 0.0.0.0 --port 9000

# Access at http://localhost:9000
```

### Backtest

```bash
# Backtest a strategy on historical data
python -m scripts.run_backtest_v3 \
    --config configs/dev.yaml \
    --symbols NIFTY,BANKNIFTY \
    --start 2025-01-01 \
    --end 2025-01-05 \
    --data-source csv
```

### Analytics

```bash
# Generate end-of-day analytics report
python -m scripts.run_analytics --config configs/dev.yaml

# Analyze paper trading results
python -m scripts.analyze_paper_results
```

### Market Scanner

```bash
# Run market scanner to build universe
python -m scripts.run_indicator_scanner --config configs/dev.yaml
```

### Authentication

```bash
# Login to Kite (generate access token)
python -m scripts.login_kite
```

---

## Directory Map

### Top-Level Directories

| Directory | Purpose |
|-----------|---------|
| **analytics/** | Performance tracking, trade journal, telemetry bus, learning engine |
| **apps/** | Application entry points (server.py, dashboard.py, run_*_paper.py) |
| **archive/** | Old/deprecated code (not actively maintained) |
| **artifacts/** | Runtime state, logs, checkpoints, orders, snapshots, reports |
| **backtest/** | Backtest engine v3 and historical data loaders |
| **broker/** | Broker adapters (paper, live, backtest), Kite client wrapper |
| **config/** | Old config files (mostly superseded by configs/) |
| **configs/** | Active configuration files (dev.yaml, backtest.dev.yaml, etc.) |
| **core/** | Core trading logic: strategy engines, execution engine, risk, portfolio, indicators |
| **data/** | Data loaders, universe definitions, instrument lists |
| **docs/** | Documentation (90+ markdown files) |
| **engine/** | Trading engines (equity, FnO, options, paper, live, backtest) |
| **examples/** | Demo scripts and usage examples |
| **risk/** | Risk management: position sizer, cost model, adaptive risk manager |
| **scripts/** | CLI scripts for trading, analytics, backtesting, scanning |
| **secrets/** | API keys and tokens (gitignored, see .env.example) |
| **services/** | Service layer for dashboard API, event bus, portfolio service |
| **strategies/** | Strategy implementations (v1, v2, v3) |
| **tests/** | Unit and integration tests |
| **tools/** | Utility scripts (docsync, repo audit) |
| **ui/** | Dashboard frontend (React) and backend (FastAPI routers) |

### Key Files

| File | Purpose |
|------|---------|
| **README.md** | Quick start guide and feature overview |
| **requirements.txt** | Python dependencies |
| **build-dashboard.sh** | Build React dashboard frontend |
| **.env.example** | Template for environment variables |
| **ARCHITECTURE_V3_PHASE1_SUMMARY.md** | Architecture summary for v3 changes |

### Core Modules (core/)

| Module | Purpose |
|--------|---------|
| **strategy_engine_v3.py** | Multi-strategy fusion engine with multi-timeframe confirmation |
| **execution_engine_v3.py** | Unified paper/live execution layer |
| **portfolio_engine.py** | Position sizing and capital allocation |
| **risk_engine_v2.py** | Circuit breakers, drawdown limits, position limits |
| **regime_engine.py** | Market regime detection (trend, volatility, structure) |
| **market_data_engine.py** | Real-time tick processing and candle building |
| **indicators.py** | Technical indicators (EMA, RSI, ATR, VWAP, Bollinger Bands) |
| **universe_builder.py** | Daily universe construction with filtering |
| **trade_guardian.py** | Pre-execution safety gate (rate limits, slippage checks) |
| **state_store.py** | Checkpoint management and state persistence |
| **kite_auth.py** | Kite Connect authentication helper |

### Engine Modules (engine/)

| Module | Purpose |
|--------|---------|
| **equity_paper_engine.py** | Paper trading for equity stocks |
| **paper_engine.py** | Paper trading for FnO futures (legacy, still used) |
| **options_paper_engine.py** | Paper trading for index options |
| **live_engine.py** | Live trading engine (unified for all asset classes) |
| **backtest_engine.py** | Backtest engine v3 (offline historical simulation) |
| **execution_engine_v3_adapter.py** | Adapter to use ExecutionEngine v3 in engines |
| **meta_strategy_engine.py** | Meta-strategy orchestration (swing vs intraday) |

### Analytics Modules (analytics/)

| Module | Purpose |
|--------|---------|
| **telemetry_bus.py** | Event-driven telemetry (orders, signals, positions) |
| **trade_journal.py** | Per-trade logging and analysis |
| **performance_v2.py** | Performance metrics (Sharpe, drawdown, win rate) |
| **learning_engine.py** | Strategy parameter optimization (experimental) |
| **multi_timeframe_engine.py** | Multi-timeframe indicator calculation |
| **trade_recorder.py** | CSV-based trade logging |

### Strategy Modules (strategies/)

| Module | Purpose |
|--------|---------|
| **base.py** | Base strategy class for v1 strategies |
| **ema20_50_intraday_v2.py** | EMA crossover strategy (v2) |
| **fno_intraday_trend.py** | Multi-timeframe trend strategy (v1) |
| **equity_intraday_simple.py** | Simple equity strategy (v1) |
| **mean_reversion_intraday.py** | Mean reversion strategy (v1) |

### Strategy v3 Modules (core/strategies_v3/)

| Module | Purpose |
|--------|---------|
| **ema20_50.py** | EMA 20/50 crossover strategy (v3) |
| **trend_strategy.py** | Generic trend following (v3) |
| **rsi_pullback.py** | RSI pullback strategy (v3) |
| **vwap_filter.py** | VWAP-based filter (v3) |
| **vol_regime.py** | Volatility regime filter (v3) |
| **htf_trend.py** | Higher timeframe trend filter (v3) |

---

## Quick Start

### 1. Setup Environment

```bash
# Clone repository
git clone https://github.com/vikiirv21/kite-algo-minimal.git
cd kite-algo-minimal

# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example secrets/kite.env

# Edit secrets/kite.env and add your Kite API key
```

### 2. Login to Kite

```bash
# Generate access token (interactive)
python -m scripts.login_kite

# Tokens saved to secrets/kite_tokens.env
```

### 3. Run Paper Trading

```bash
# Run complete trading session
python -m scripts.run_session --mode paper --config configs/dev.yaml

# Or run individual engines
python -m apps.run_equity_paper --config configs/dev.yaml --mode paper
```

### 4. Start Dashboard

```bash
# Build frontend (first time only)
./build-dashboard.sh

# Start server
python -m uvicorn apps.server:app --host 0.0.0.0 --port 9000

# Open http://localhost:9000 in browser
```

### 5. View Results

```bash
# Check logs
tail -f artifacts/logs/equity_paper_engine.log

# View orders
cat artifacts/orders_equity_paper_2025-11-19.csv

# Generate analytics report
python -m scripts.run_analytics --config configs/dev.yaml
```

---

## Related Documentation

For more detailed information, see:

- **[ARCHITECTURE.md](./ARCHITECTURE.md)**: Detailed architecture and component interactions
- **[MODULES.md](./MODULES.md)**: Module-by-module developer reference
- **[ENGINES.md](./ENGINES.md)**: Deep-dive into trading engines
- **[STRATEGIES.md](./STRATEGIES.md)**: Strategy development guide
- **[DASHBOARD.md](./DASHBOARD.md)**: Dashboard API and UI documentation
- **[RUNBOOKS.md](./RUNBOOKS.md)**: Day-to-day operational guide

For legacy/detailed docs, see:
- `docs/HFT-System-Architecture-kite-algo-minimal.md`: Comprehensive architecture v2
- `docs/MULTIPROCESS_ARCHITECTURE.md`: Multi-process architecture guide
- `docs/BACKTEST_ENGINE_V3.md`: Backtest engine documentation
- `docs/EXECUTION_ENGINE_V3.md`: Execution engine v3 documentation
- `docs/STRATEGY_ENGINE_V3.md`: Strategy engine v3 documentation

---

**Last Updated**: 2025-11-19  
**Maintainer**: Auto-generated via documentation system  
**Version**: 1.0
