# kite-algo-minimal

Skeleton for a Zerodha Kite algo trading project (FnO + equity, paper + live).

Real content will be added later.

## Features

### React Dashboard (NEW!)

Modern web-based control panel built with React, TypeScript, and Tailwind CSS:

- **7 Pages**: Overview, Trading, Portfolio, Signals, Analytics, System, Logs
- **Real-time Updates**: Auto-polling with React Query (1-5s intervals)
- **Dark Theme**: Professional futuristic design
- **Live Metrics**: P&L, positions, orders, signals with color coding
- **Log Viewer**: Filterable engine logs with auto-scroll
- **Charts**: Equity curve visualization with Recharts

**Quick Start:**
```bash
# Build the dashboard
./build-dashboard.sh

# Start the server
python -m uvicorn apps.server:app --host 0.0.0.0 --port 9000

# Open http://localhost:9000
```

See [docs/dashboard_new_ui.md](docs/dashboard_new_ui.md) for complete documentation.

### Backtest Engine v3
Offline backtesting framework that reuses live/paper components:
- Runs completely offline on historical data
- Reuses StrategyEngine, PortfolioEngine, RiskEngine, RegimeEngine
- No broker connections or authentication required
- Structured outputs for analytics

Quick start:
```bash
python -m scripts.run_backtest_v3 \
    --config configs/dev.yaml \
    --symbols NIFTY,BANKNIFTY \
    --start 2025-01-01 \
    --end 2025-01-05 \
    --data-source csv
```

See [BACKTEST_ENGINE_V3.md](docs/BACKTEST_ENGINE_V3.md) for complete documentation.

### Multi-Process Architecture (v3 Phase 1)
Run each engine (FnO, Equity, Options) as a separate Python process for better isolation and scalability:

```bash
# Default: single-process mode (all engines in one process)
python -m scripts.run_session --mode paper --config configs/dev.yaml

# New: multi-process mode (one process per engine)
python -m scripts.run_session --mode paper --config configs/dev.yaml --layout multi

# Run individual engines directly
python -m apps.run_fno_paper --config configs/dev.yaml --mode paper
python -m apps.run_equity_paper --config configs/dev.yaml --mode paper
python -m apps.run_options_paper --config configs/dev.yaml --mode paper
```

Features:
- **Backward Compatible**: Default behavior unchanged
- **Process Isolation**: Each engine runs independently
- **Graceful Shutdown**: Handles Ctrl+C and SIGTERM properly
- **Shared Artifacts**: All engines use same config and state files

See [docs/MULTIPROCESS_ARCHITECTURE.md](docs/MULTIPROCESS_ARCHITECTURE.md) for complete documentation.

## Git Hooks & Documentation

Auto-generated docs ensure REST and architecture notes stay current. Before committing, enable the local hook once:

```bash
git config core.hooksPath .githooks
```

The pre-commit hook runs `python -m tools.docsync` and automatically stages `docs/` and `CHANGELOG.md` whenever they change. If the sync fails, the commit aborts so you can fix the issue first.
