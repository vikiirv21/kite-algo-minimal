# kite-algo-minimal

Skeleton for a Zerodha Kite algo trading project (FnO + equity, paper + live).

Real content will be added later.

## Features

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

See [BACKTEST_ENGINE_V3.md](BACKTEST_ENGINE_V3.md) for complete documentation.

## Git Hooks & Documentation

Auto-generated docs ensure REST and architecture notes stay current. Before committing, enable the local hook once:

```bash
git config core.hooksPath .githooks
```

The pre-commit hook runs `python -m tools.docsync` and automatically stages `docs/` and `CHANGELOG.md` whenever they change. If the sync fails, the commit aborts so you can fix the issue first.
