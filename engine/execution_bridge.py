"""
Helper utilities to integrate ExecutionEngine v2 with existing PaperEngine and LiveEngine.

This module provides bridge functions that allow gradual migration to ExecutionEngine v2
without breaking existing code.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from core.market_data_engine_v2 import MarketDataEngineV2
from core.state_store import JournalStateStore, StateStore
from core.trade_throttler import TradeThrottler
from engine.execution_engine import ExecutionEngineV2, OrderIntent, ExecutionResult

logger = logging.getLogger(__name__)


def create_execution_engine_v2(
    mode: str,
    broker: Any,
    state_store: StateStore,
    journal_store: JournalStateStore,
    trade_throttler: Optional[TradeThrottler],
    config: Dict[str, Any],
    mde: Optional[MarketDataEngineV2] = None,
) -> Optional[ExecutionEngineV2]:
    """
    Create ExecutionEngineV2 if enabled in config.
    
    Args:
        mode: 'paper' or 'live'
        broker: Broker instance (KiteBroker for live, None for paper)
        state_store: StateStore instance
        journal_store: JournalStateStore instance
        trade_throttler: TradeThrottler instance
        config: Full config dict
        mde: MarketDataEngine v2 (required for paper mode)
    
    Returns:
        ExecutionEngineV2 instance if enabled, None otherwise
    """
    exec_config = config.get("execution", {})
    use_v2 = exec_config.get("use_execution_engine_v2", False)
    
    if not use_v2:
        logger.info("ExecutionEngine v2 disabled in config - using legacy execution path")
        return None
    
    try:
        logger.info("Initializing ExecutionEngine v2 (mode=%s)", mode)
        return ExecutionEngineV2(
            mode=mode,
            broker=broker,
            state_store=state_store,
            journal_store=journal_store,
            trade_throttler=trade_throttler,
            logger_instance=logger,
            config=config,
            mde=mde,
        )
    except Exception as exc:
        logger.error(
            "Failed to initialize ExecutionEngine v2: %s - falling back to legacy execution",
            exc, exc_info=True
        )
        return None


def convert_strategy_intent_to_execution_intent(
    strategy_intent: Any,
    symbol: str,
    strategy_code: str,
    qty: int,
    order_type: str = "MARKET",
    product: str = "MIS",
    price: Optional[float] = None,
) -> OrderIntent:
    """
    Convert a strategy intent to ExecutionEngine v2 OrderIntent.
    
    Args:
        strategy_intent: Intent from strategy engine (OrderIntent from strategy_engine_v2)
        symbol: Trading symbol
        strategy_code: Strategy identifier
        qty: Order quantity
        order_type: Order type (MARKET/LIMIT)
        product: Product type (MIS/NRML/CNC)
        price: Limit price if applicable
    
    Returns:
        OrderIntent for ExecutionEngine v2
    """
    # Extract data from strategy intent if it's an object
    if hasattr(strategy_intent, 'action'):
        action = strategy_intent.action
        reason = getattr(strategy_intent, 'reason', '')
        confidence = getattr(strategy_intent, 'confidence', 0.0)
        metadata = getattr(strategy_intent, 'metadata', {})
    elif isinstance(strategy_intent, dict):
        action = strategy_intent.get('action', 'BUY')
        reason = strategy_intent.get('reason', '')
        confidence = strategy_intent.get('confidence', 0.0)
        metadata = strategy_intent.get('metadata', {})
    else:
        action = 'BUY'
        reason = ''
        confidence = 0.0
        metadata = {}
    
    # Map action to side
    if action.upper() in ('BUY', 'LONG', 'ENTRY_LONG'):
        side = 'BUY'
    elif action.upper() in ('SELL', 'SHORT', 'ENTRY_SHORT'):
        side = 'SELL'
    elif action.upper() in ('EXIT', 'CLOSE'):
        # For exit, we need to determine side based on position
        # For now, default to SELL (assuming most positions are long)
        side = 'SELL'
    else:
        side = action.upper()
    
    return OrderIntent(
        symbol=symbol,
        strategy_code=strategy_code,
        side=side,
        qty=qty,
        order_type=order_type,
        product=product,
        price=price,
        reason=reason,
        confidence=confidence,
        metadata=metadata,
    )


def execute_with_v2_or_fallback(
    execution_engine: Optional[ExecutionEngineV2],
    intent: OrderIntent,
    fallback_fn: Any,
    fallback_args: tuple = (),
    fallback_kwargs: Optional[Dict[str, Any]] = None,
) -> Any:
    """
    Execute order using ExecutionEngine v2 if available, otherwise use fallback.
    
    Args:
        execution_engine: ExecutionEngine v2 instance (or None)
        intent: Order intent
        fallback_fn: Legacy execution function to call if v2 not available
        fallback_args: Args for fallback function
        fallback_kwargs: Kwargs for fallback function
    
    Returns:
        ExecutionResult if using v2, otherwise result from fallback function
    """
    if execution_engine is not None:
        # Use ExecutionEngine v2
        logger.debug("Using ExecutionEngine v2 for order execution")
        return execution_engine.execute_intent(intent)
    else:
        # Use legacy execution path
        logger.debug("Using legacy execution path for order")
        if fallback_kwargs is None:
            fallback_kwargs = {}
        return fallback_fn(*fallback_args, **fallback_kwargs)
