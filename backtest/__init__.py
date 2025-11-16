"""
Backtest Engine v3 - Offline backtesting using core live/paper components.

This package provides:
- BacktestEngineV3: Main backtest orchestrator
- HistoricalDataLoader: Historical data loading from various sources
- BacktestConfig: Configuration for backtest runs
- BacktestResult: Structured backtest results

The backtest engine reuses:
- StrategyEngine v2/v3
- PortfolioEngine v1
- RegimeEngine v2
- RiskEngine v2
- TradeGuardian (optional)
- ExecutionEngine (sim-only mode)
"""

from backtest.engine_v3 import BacktestConfig, BacktestEngineV3, BacktestResult
from backtest.data_loader import HistoricalDataLoader

__all__ = [
    "BacktestConfig",
    "BacktestEngineV3",
    "BacktestResult",
    "HistoricalDataLoader",
]
