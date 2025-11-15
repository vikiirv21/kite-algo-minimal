# Repository Map

## Directory Structure

```
kite-algo-minimal/
│
├── engine/              # Trading engines
│   ├── paper_engine.py      # Paper trading orchestrator
│   ├── live_engine.py       # Live trading orchestrator  
│   ├── equity_paper_engine.py
│   ├── options_paper_engine.py
│   ├── meta_strategy_engine.py
│   └── bootstrap.py         # Engine initialization
│
├── core/                # Core system components
│   ├── strategy_engine_v2.py    # Modern strategy framework
│   ├── market_data_engine.py    # Market data management
│   ├── risk_engine.py           # Risk validation
│   ├── risk_engine_v2.py        # Enhanced risk engine
│   ├── indicators.py            # Technical indicators
│   ├── state_store.py           # State management
│   ├── strategy_registry.py    # Strategy catalog
│   ├── config.py                # Configuration management
│   └── ...
│
├── strategies/          # Trading strategies
│   ├── base.py                  # Base strategy class
│   ├── ema20_50_intraday_v2.py  # EMA crossover strategy
│   ├── fno_intraday_trend.py    # F&O trend following
│   ├── mean_reversion_intraday.py
│   └── equity_intraday_simple.py
│
├── broker/              # Broker integrations
│   ├── execution_router.py      # Mode-aware routing
│   ├── paper_broker.py          # Paper trading broker
│   ├── live_broker.py           # Live trading broker
│   ├── backtest_broker.py       # Backtest broker
│   ├── kite_bridge.py           # Kite API wrapper
│   └── auth.py                  # Authentication
│
├── ui/                  # Web dashboard
│   ├── dashboard.py             # FastAPI dashboard
│   ├── services.py              # Dashboard services
│   ├── static/                  # Static assets
│   └── templates/               # HTML templates
│
├── scripts/             # Utility scripts
│   ├── generate_docs.py         # Documentation generator
│   ├── run_paper_equity.py      # Run paper equity mode
│   ├── run_backtest.py          # Run backtests
│   ├── login_kite.py            # Kite authentication
│   └── ...
│
├── analytics/           # Performance analytics
│   ├── trade_recorder.py        # Trade journaling
│   ├── strategy_performance.py  # Strategy metrics
│   └── ...
│
├── risk/                # Risk management
│   ├── adaptive_risk_manager.py
│   ├── position_sizer.py
│   └── cost_model.py
│
├── data/                # Data management
│   ├── broker_feed.py
│   ├── instruments.py
│   └── backtest_data.py
│
├── docs/                # Documentation (auto-generated)
│   └── *.md
│
├── artifacts/           # Runtime artifacts
│   ├── checkpoints/
│   ├── logs/
│   └── market_data/
│
├── configs/             # Configuration files
├── secrets/             # API credentials (gitignored)
└── tests/               # Test suite

```

## Key Files

### Engine Layer
- `engine/paper_engine.py`: Main paper trading orchestrator with simulated fills
- `engine/live_engine.py`: Live trading with real Kite orders

### Core Layer
- `core/strategy_engine_v2.py`: Strategy execution framework
- `core/market_data_engine.py`: Candle fetching and caching
- `core/risk_engine.py`: Risk checks and position sizing
- `core/indicators.py`: Technical indicator library
- `core/state_store.py`: State persistence

### Strategy Layer
- `strategies/base.py`: Base strategy interface
- `strategies/*.py`: Individual strategy implementations

### Broker Layer
- `broker/execution_router.py`: Routes orders based on mode
- `broker/paper_broker.py`: In-memory position tracking
- `broker/kite_bridge.py`: Kite API integration

### UI Layer
- `ui/dashboard.py`: FastAPI web dashboard
- `ui/templates/`: Dashboard HTML templates

---
*Auto-generated on 2025-11-15T21:49:59.697142+00:00*
