"""
Integration module for ExecutionEngine V3 with existing paper engines.

This module provides helper functions to integrate ExecutionEngine V3
with paper_engine.py, options_paper_engine.py, and equity_paper_engine.py
in a minimal, non-breaking way.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def create_execution_engine_v3(
    config: Dict[str, Any],
    market_data_engine: Any = None,
    trade_recorder: Any = None,
    state_store: Any = None,
) -> Optional[Any]:
    """
    Create ExecutionEngine V3 if enabled in config.
    
    Args:
        config: Configuration dictionary
        market_data_engine: Market data engine instance (used as broker_feed)
        trade_recorder: Trade recorder instance
        state_store: State store instance
        
    Returns:
        ExecutionEngineV3 instance if enabled, None otherwise
    """
    try:
        exec_config = config.get("execution", {})
        engine_version = exec_config.get("engine", "v2")
        
        if engine_version != "v3":
            logger.info("ExecutionEngine V3 not enabled (engine=%s)", engine_version)
            return None
        
        # Import ExecutionEngineV3
        from execution.engine_v3 import ExecutionEngineV3
        
        logger.info("Creating ExecutionEngine V3 (Step 1 - minimal)")
        
        # Get trading config for default_quantity
        trading_config = config.get("trading", {})
        exec_cfg_with_defaults = {
            **exec_config,
            "default_quantity": trading_config.get("default_quantity", 1),
        }
        
        engine = ExecutionEngineV3(
            cfg=exec_cfg_with_defaults,
            state_store=state_store,
            trade_recorder=trade_recorder,
            broker_feed=market_data_engine,  # BrokerFeed is market_data_engine in this context
            logger_instance=logger,
        )
        
        logger.info("ExecutionEngine V3 initialized successfully")
        return engine
        
    except ImportError as e:
        logger.warning("ExecutionEngine V3 not available: %s", e)
        return None
    except Exception as e:
        logger.error("Failed to create ExecutionEngine V3: %s", e, exc_info=True)
        return None


def convert_to_order_intent(
    symbol: str,
    signal: str,
    qty: int,
    price: float,
    strategy_code: str = "",
    logical_symbol: str = "",
    product: str = "MIS",
    mode: str = "paper",
    timeframe: str = "5m",
    exchange: str = "NFO",
    sl_price: Optional[float] = None,
    tp_price: Optional[float] = None,
    time_stop_bars: Optional[int] = None,
    reason: str = "",
    **kwargs
) -> tuple:
    """
    Convert signal parameters to (OrderIntent, ExecutionContext) tuple for ExecutionEngine V3.
    
    Args:
        symbol: Trading symbol
        signal: Signal action (BUY/SELL/EXIT)
        qty: Order quantity
        price: Current price
        strategy_code: Strategy identifier
        logical_symbol: Logical underlying (e.g., "NIFTY")
        product: Product type (default: "MIS")
        mode: Trading mode (default: "paper")
        timeframe: Timeframe (default: "5m")
        exchange: Exchange (default: "NFO")
        sl_price: Stop loss price (not used in Step 1)
        tp_price: Take profit price (not used in Step 1)
        time_stop_bars: Time stop in bars (not used in Step 1)
        reason: Signal reason
        **kwargs: Additional metadata
        
    Returns:
        Tuple of (OrderIntent, ExecutionContext)
    """
    from types import SimpleNamespace
    from datetime import datetime, timezone
    from execution.engine_v3 import ExecutionContext
    
    # Infer logical_symbol from symbol if not provided
    if not logical_symbol:
        # Simple heuristic: extract from symbol (e.g., "NIFTY24DECFUT" -> "NIFTY")
        if "NIFTY" in symbol.upper():
            logical_symbol = "BANKNIFTY" if "BANK" in symbol.upper() else "FINNIFTY" if "FIN" in symbol.upper() else "NIFTY"
        else:
            logical_symbol = symbol  # Fallback to symbol itself
    
    # Create OrderIntent-like object for signal processing
    intent = SimpleNamespace(
        symbol=symbol,
        signal=signal,
        action=signal,  # Alias
        qty=qty,
        qty_hint=qty,
        price=price,
        strategy_id=strategy_code,
        strategy_code=strategy_code,
        sl_price=sl_price,
        tp_price=tp_price,
        time_stop_bars=time_stop_bars,
        reason=reason,
        metadata=kwargs,
    )
    
    # Create ExecutionContext for the new minimal V3 API
    context = ExecutionContext(
        symbol=symbol,
        logical_symbol=logical_symbol,
        product=product,
        strategy_id=strategy_code,
        mode=mode,
        timestamp=datetime.now(timezone.utc),
        timeframe=timeframe,
        exchange=exchange,
        fixed_qty=qty,  # Pass the qty as fixed_qty so the engine uses it
    )
    
    return (intent, context)


def should_use_v3(config: Dict[str, Any], exec_engine_v3: Any) -> bool:
    """
    Determine if ExecutionEngine V3 should be used.
    
    Args:
        config: Configuration dictionary
        exec_engine_v3: ExecutionEngine V3 instance (or None)
        
    Returns:
        True if V3 should be used
    """
    if exec_engine_v3 is None:
        return False
    
    exec_config = config.get("execution", {})
    engine_version = exec_config.get("engine", "v2")
    
    return engine_version == "v3"


def update_positions_from_tick(exec_engine_v3: Any, tick_data: Dict[str, float]):
    """
    Update positions in ExecutionEngine V3 from tick data.
    
    Args:
        exec_engine_v3: ExecutionEngine V3 instance
        tick_data: Dictionary of symbol -> price
    """
    if exec_engine_v3 is None:
        return
    
    try:
        exec_engine_v3.update_positions(tick_data)
    except Exception as e:
        logger.error("Error updating positions in ExecutionEngine V3: %s", e, exc_info=True)


def on_candle_close(exec_engine_v3: Any):
    """
    Notify ExecutionEngine V3 that a candle has closed.
    
    Args:
        exec_engine_v3: ExecutionEngine V3 instance
    """
    if exec_engine_v3 is None:
        return
    
    try:
        exec_engine_v3.on_candle_close()
    except Exception as e:
        logger.error("Error in ExecutionEngine V3 candle close: %s", e, exc_info=True)


def get_v3_positions(exec_engine_v3: Any) -> list:
    """
    Get positions from ExecutionEngine V3.
    
    Args:
        exec_engine_v3: ExecutionEngine V3 instance
        
    Returns:
        List of Position objects
    """
    if exec_engine_v3 is None:
        return []
    
    try:
        return exec_engine_v3.get_positions()
    except Exception as e:
        logger.error("Error getting positions from ExecutionEngine V3: %s", e, exc_info=True)
        return []


def get_v3_metrics(exec_engine_v3: Any) -> Dict[str, Any]:
    """
    Get metrics from ExecutionEngine V3.
    
    Args:
        exec_engine_v3: ExecutionEngine V3 instance
        
    Returns:
        Metrics dictionary
    """
    if exec_engine_v3 is None:
        return {}
    
    try:
        return exec_engine_v3.get_metrics()
    except Exception as e:
        logger.error("Error getting metrics from ExecutionEngine V3: %s", e, exc_info=True)
        return {}
