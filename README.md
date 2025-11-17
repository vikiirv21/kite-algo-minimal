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

## Git Hooks & Documentation

Auto-generated docs ensure REST and architecture notes stay current. Before committing, enable the local hook once:

```bash
git config core.hooksPath .githooks
```

The pre-commit hook runs `python -m tools.docsync` and automatically stages `docs/` and `CHANGELOG.md` whenever they change. If the sync fails, the commit aborts so you can fix the issue first.
