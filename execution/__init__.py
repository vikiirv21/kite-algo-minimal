"""
Execution Engine V3 - Step 1 minimal implementation.

This package provides:
- Simple "market at LTP" order fills
- Basic position tracking and PnL calculation
- State updates via state_store
- Trade journaling via trade_recorder
- No SL/TP, trailing stops, or partial exits (deferred to later steps)
"""

from execution.engine_v3 import (
    ExecutionEngineV3,
    ExecutionContext,
    ExecutionResult,
)

__all__ = [
    "ExecutionEngineV3",
    "ExecutionContext",
    "ExecutionResult",
]
