# System Architecture

## Overview

This is a high-frequency trading (HFT) system built for the Indian stock market via Zerodha Kite API.

### Project Description

- **Real-time Trading**: Supports paper, live, and backtest modes with real-time tick processing
- **Multi-Strategy Framework**: Pluggable strategy architecture with risk management and portfolio tracking
- **Web Dashboard**: FastAPI-based dashboard for monitoring and control

## High-Level Structure

```

apps/
├── __init__.py
├── api_strategies.py
├── dashboard.py
├── dashboard_logs.py
├── run_equity_paper.py
├── run_fno_paper.py
├── run_options_paper.py
├── run_service.py
└── server.py
core/
├── strategies_v3/
│   ├── __init__.py
│   ├── ema20_50.py
│   ├── htf_trend.py
│   ├── rsi_pullback.py
│   ├── trend_strategy.py
│   ├── vol_regime.py
│   └── vwap_filter.py
├── __init__.py
├── atr_risk.py
├── backtest_registry.py
├── broker_sync.py
├── config.py
├── engine_bootstrap.py
├── event_logging.py
├── execution_engine_v3.py
├── expiry_calendar.py
├── expiry_risk_adapter.py
├── history_loader.py
├── indicators.py
├── json_log.py
├── kite_auth.py
├── kite_env.py
├── kite_http.py
├── logging_utils.py
├── market_context.py
├── market_context.py.backup
├── market_data_engine.py
├── market_data_engine_v2.py
├── market_session.py
├── modes.py
├── pattern_filters.py
├── portfolio_engine.py
├── reconciliation_engine.py
├── regime_detector.py
├── regime_engine.py
├── risk_engine.py
├── risk_engine_v2.py
├── runtime_mode.py
├── scanner.py
├── session.py
├── signal_filters.py
├── signal_quality.py
├── state_store.py
├── strategy_engine.py
├── strategy_engine_v2.py
├── strategy_engine_v3.py
├── strategy_metrics.py
├── strategy_orchestrator.py
├── strategy_registry.py
├── strategy_tags.py
├── trade_guardian.py
├── trade_monitor.py
├── trade_throttler.py
├── universe.py
└── universe_builder.py
engine/
├── __init__.py
├── bootstrap.py
├── equity_paper_engine.py
├── execution_bridge.py
├── execution_engine.py
├── execution_engine_v3_adapter.py
├── live_engine.py
├── meta_strategy_engine.py
├── options_paper_engine.py
├── paper_engine.py
└── paper_execution.py
analytics/
├── __init__.py
├── benchmarks.py
├── learning_engine.py
├── multi_timeframe_engine.py
├── multi_timeframe_scanner.py
├── performance.py
├── performance_utils.py
├── performance_v2.py
├── risk_service.py
├── strategy_analytics.py
├── strategy_performance.py
├── telemetry_bus.py
├── trade_journal.py
├── trade_recorder.py
└── trade_scorer.py
strategies/
├── __init__.py
├── base.py
├── ema20_50_intraday_v2.py
├── equity_intraday_simple.py
├── fno_intraday_trend.py
└── mean_reversion_intraday.py
broker/
├── __init__.py
├── auth.py
├── backtest_broker.py
├── execution_router.py
├── kite_bridge.py
├── kite_client.py
├── live_broker.py
└── paper_broker.py
scripts/
├── __init__.py
├── analyze_and_learn.py
├── analyze_paper_results.py
├── analyze_performance.py
├── analyze_strategy_performance.py
├── backfill_history.py
├── demo_scanner.py
├── demo_v3_trader_strategy.py
├── diag_kite_ws.py
├── dry_run_strategy_v2.py
├── generate_docs.py
├── live_quotes.py
├── login_kite.py
├── refresh_market_cache.py
├── replay_from_historical.py
├── run_all.py
├── run_analytics.py
├── run_backtest.py
├── run_backtest_v1.py
├── run_backtest_v3.py
├── run_dashboard.py
├── run_day.py
├── run_indicator_scanner.py
├── run_learning_engine.py
├── run_paper_equity.py
├── run_paper_fno.py
├── run_paper_options.py
├── run_session.py
├── run_trader.py
├── show_paper_state.py
├── test_v3_exec_flow.py
└── test_v3_strategy_flow.py
ui/
├── frontend/
│   ├── public/
│   ├── src/
│   ├── README.md
│   ├── eslint.config.js
│   ├── index.html
│   ├── package-lock.json
│   ├── package.json
│   ├── postcss.config.js
│   ├── tailwind.config.js
│   ├── tsconfig.app.json
│   ├── tsconfig.json
│   ├── tsconfig.node.json
│   └── vite.config.ts
├── static/
│   ├── css/
│   ├── js/
│   ├── dashboard.css
│   ├── dashboard.js
│   ├── dashboard_tabs.js
│   ├── dashboard_v2.js
│   └── ui-polish.js
├── static-react/
│   ├── assets/
│   ├── index.html
│   └── vite.svg
├── templates/
│   ├── layout/
│   ├── pages/
│   ├── base.html
│   ├── dashboard.html
│   ├── index.html
│   ├── index_backup.html
│   ├── index_backup_old.html
│   ├── index_backup_original.html
│   └── index_original.html
├── __init__.py
├── dashboard.py
└── services.py
```

## Major Subsystems

### Dashboard / UI
- **Location**: `apps/dashboard.py`, `ui/` folder
- **Purpose**: Web-based monitoring and control interface
- **Technology**: FastAPI, Jinja2 templates, Server-Sent Events (SSE)
- **Features**: Real-time position tracking, P&L monitoring, strategy control

### Trading Engines
- **Paper Engine** (`engine/paper_engine.py`): Simulated trading with virtual capital
- **Live Engine** (`engine/live_engine.py`): Real order placement via Kite API
- **Execution Bridge** (`engine/execution_bridge.py`): Mode-aware order routing

### Scanner & Signal Generation
- **Scanner** (`core/scanner.py`): Technical pattern detection and signal generation
- **Indicators** (`core/indicators.py`): Technical indicator library (EMA, RSI, MACD, etc.)
- **Signal Filters** (`core/signal_filters.py`, `core/pattern_filters.py`): Multi-stage signal validation

### Strategy Layer
- **Strategy Engine v3** (`core/strategy_engine_v3.py`): Modern strategy execution framework
- **Strategy Registry** (`core/strategy_registry.py`): Strategy catalog and metadata
- **Strategies** (`strategies/`): Individual strategy implementations
  - EMA crossover strategies
  - Mean reversion strategies
  - Trend following strategies

### Risk & Portfolio Management
- **Risk Engine v2** (`core/risk_engine_v2.py`): Position sizing, loss limits, exposure management
- **Portfolio Engine** (`core/portfolio_engine.py`): Portfolio-level P&L and position tracking
- **Trade Guardian** (`core/trade_guardian.py`): Pre-trade validation and safety checks
- **Adaptive Risk Manager** (`risk/adaptive_risk_manager.py`): Dynamic risk adjustment

### Market Data & Execution
- **Market Data Engine v2** (`core/market_data_engine_v2.py`): Candle fetching and caching
- **Execution Engine v3** (`core/execution_engine_v3.py`): Order management and execution
- **Broker Integration** (`broker/`): Kite API integration, auth, and order routing

### Analytics & Monitoring
- **Telemetry** (`analytics/telemetry.py`): System-wide metrics collection
- **Trade Recorder** (`analytics/trade_recorder.py`): Trade journaling and performance tracking
- **Strategy Performance** (`analytics/strategy_performance.py`): Strategy-level metrics

### Utilities / Tools
- **Scripts** (`scripts/`): CLI tools for running engines, analysis, and management
- **Tools** (`tools/`): Development and documentation tools
- **Config Management** (`core/config.py`): YAML-based configuration

## Key Entrypoints

### Main Runners
- `scripts/run_day.py` - Main day trading orchestrator
- `scripts/run_session.py` - Session-based trading runner
- `scripts/run_paper_equity.py` - Paper trading for equities
- `scripts/run_paper_fno.py` - Paper trading for F&O

### Dashboard
- `scripts/run_dashboard.py` - Start the web dashboard
- `apps/dashboard.py` - Dashboard application

### Analysis
- `scripts/analyze_performance.py` - Performance analysis
- `scripts/analyze_paper_results.py` - Paper trading results analysis

## Configuration

- **Main Config**: `configs/dev.yaml` (and other environment configs)
- **Secrets**: `secrets/` (API keys, tokens - gitignored)
- **Artifacts**: `artifacts/` (logs, checkpoints, market data cache)

## Data Flow

```
Kite WebSocket Ticks
        ↓
Market Data Engine
        ↓
Scanner / Strategy Engine
        ↓
Signal Generation
        ↓
Risk Validation (Trade Guardian)
        ↓
Execution Engine
        ↓
Broker (Paper / Live)
        ↓
Portfolio Engine (P&L tracking)
        ↓
Analytics & Telemetry
```

---
*Auto-generated from repository structure*
