"""
Execution Engine V3 - Unified execution layer with comprehensive order lifecycle management.

This package provides:
- Order lifecycle management (CREATED → SUBMITTED → FILLED → ACTIVE → CLOSED)
- Fill simulation with bid/ask spread and slippage
- Stop Loss management with partial exit support
- Take Profit management
- Trailing Stop Loss
- Time-based stops
- Unified position tracking and PnL calculation
"""

from execution.engine_v3 import (
    ExecutionEngineV3,
    OrderBuilder,
    FillEngine,
    StopLossManager,
    TakeProfitManager,
    TrailingStopManager,
    TimeStopManager,
    TradeLifecycleManager,
    OrderState,
    Order,
    Position,
)

__all__ = [
    "ExecutionEngineV3",
    "OrderBuilder",
    "FillEngine",
    "StopLossManager",
    "TakeProfitManager",
    "TrailingStopManager",
    "TimeStopManager",
    "TradeLifecycleManager",
    "OrderState",
    "Order",
    "Position",
]
