"""
ExecutionEngine V3 Integration Adapter

This module provides adapters and wrappers to integrate ExecutionEngine V3
with existing code (ExecutionEngine V2) while maintaining 100% backward compatibility.

Usage:
    # Use V3 with existing V2 interface (backward compatible)
    from engine.execution_engine_v3_adapter import ExecutionEngineV2ToV3Adapter
    
    # Or use V3 directly
    from core.execution_engine_v3 import PaperExecutionEngine, LiveExecutionEngine
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from core.execution_engine_v3 import (
    EventBus,
    LiveExecutionEngine,
    Order,
    OrderStatus,
    PaperExecutionEngine,
)
from engine.execution_engine import ExecutionResult, OrderIntent

logger = logging.getLogger(__name__)


class ExecutionEngineV2ToV3Adapter:
    """
    Adapter that wraps ExecutionEngine V3 to provide ExecutionEngine V2 interface.
    
    This allows existing code using V2 to seamlessly use V3 under the hood.
    """
    
    def __init__(
        self,
        mode: str,
        broker: Any,
        state_store: Any,
        journal_store: Any,
        trade_throttler: Any,
        logger_instance: logging.Logger,
        config: Dict[str, Any],
        mde: Optional[Any] = None,
        guardian: Optional[Any] = None,
    ):
        """
        Initialize adapter with V2-compatible parameters.
        
        Args:
            mode: 'paper' or 'live'
            broker: Broker instance (for live mode)
            state_store: StateStore instance
            journal_store: JournalStateStore instance
            trade_throttler: TradeThrottler instance (unused in V3)
            logger_instance: Logger instance
            config: Configuration dict
            mde: MarketDataEngine (for paper mode)
            guardian: TradeGuardian instance (for live mode)
        """
        self.mode = mode.lower()
        self.broker = broker
        self.state_store = state_store
        self.journal = journal_store
        self.throttler = trade_throttler
        self.logger = logger_instance or logger
        self.config = config
        self.mde = mde
        self.guardian_instance = guardian
        
        # Create V3 engine
        self.event_bus = EventBus()
        
        if self.mode == "paper":
            # Import TradeGuardian if not provided
            if self.guardian_instance is None:
                from core.trade_guardian import TradeGuardian
                self.guardian_instance = TradeGuardian(config, state_store, logger_instance)
            
            self.v3_engine = PaperExecutionEngine(
                market_data_engine=mde,
                state_store=state_store,
                config=config,
                event_bus=self.event_bus,
                logger_instance=logger_instance
            )
            self.logger.info("ExecutionEngineV2ToV3Adapter initialized in PAPER mode")
        else:
            # Import TradeGuardian if not provided
            if self.guardian_instance is None:
                from core.trade_guardian import TradeGuardian
                self.guardian_instance = TradeGuardian(config, state_store, logger_instance)
            
            self.v3_engine = LiveExecutionEngine(
                broker=broker,
                guardian=self.guardian_instance,
                state_store=state_store,
                journal_store=journal_store,
                config=config,
                event_bus=self.event_bus,
                logger_instance=logger_instance
            )
            self.logger.info("ExecutionEngineV2ToV3Adapter initialized in LIVE mode")
    
    def execute_intent(self, intent: OrderIntent) -> ExecutionResult:
        """
        Execute an order intent using V3 engine (V2 interface).
        
        Args:
            intent: OrderIntent from V2
            
        Returns:
            ExecutionResult in V2 format
        """
        # Apply throttler if available (V2 compatibility)
        if self.throttler:
            can_trade, reason = self.throttler.can_trade(
                symbol=intent.symbol,
                strategy=intent.strategy_code,
                expected_edge=100.0,
            )
            if not can_trade:
                self.logger.warning(f"TradeThrottler blocked order: {reason}")
                return ExecutionResult(
                    order_id=None,
                    status="REJECTED",
                    symbol=intent.symbol,
                    side=intent.side,
                    qty=intent.qty,
                    message=f"Throttler blocked: {reason}",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
        
        # Convert V2 OrderIntent to V3 Order
        v3_order = self._convert_intent_to_order(intent)
        
        # Execute using V3 engine (run async in sync context)
        try:
            # Get or create event loop
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            # Run async operation
            result_order = loop.run_until_complete(self.v3_engine.place_order(v3_order))
            
            # Convert V3 Order back to V2 ExecutionResult
            return self._convert_order_to_result(result_order)
            
        except Exception as exc:
            self.logger.error(f"V3 execution failed: {exc}", exc_info=True)
            return ExecutionResult(
                order_id=None,
                status="REJECTED",
                symbol=intent.symbol,
                side=intent.side,
                qty=intent.qty,
                message=f"Execution error: {exc}",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
    
    def apply_circuit_breakers(self, intent: OrderIntent) -> bool:
        """
        Apply circuit breakers (V2 compatibility).
        
        Note: V3 engines handle circuit breakers internally via Guardian.
        This method maintains V2 interface for backward compatibility.
        
        Args:
            intent: Order intent to check
            
        Returns:
            True if trading allowed
        """
        # Check state-based circuit breakers
        state = self.state_store.load()
        if not state:
            return True
        
        # Check if risk halted
        risk_info = state.get("risk", {})
        if risk_info.get("trading_halted", False):
            halt_reason = risk_info.get("halt_reason", "Unknown")
            self.logger.warning(f"Circuit breaker: Trading halted by risk engine ({halt_reason})")
            return False
        
        return True
    
    def on_order_update(self, update: Dict[str, Any]):
        """
        Handle broker order updates (V2 compatibility).
        
        Args:
            update: Order update dict from broker
        """
        if self.mode != "live":
            self.logger.warning(f"on_order_update called in {self.mode} mode - ignoring")
            return
        
        self.logger.info(f"Order update received: {update}")
        
        # V3 handles updates via reconciliation loop
        # This method is maintained for backward compatibility
    
    def _convert_intent_to_order(self, intent: OrderIntent) -> Order:
        """
        Convert V2 OrderIntent to V3 Order.
        
        Args:
            intent: V2 OrderIntent
            
        Returns:
            V3 Order
        """
        return Order(
            order_id="",  # Will be generated by V3 engine
            symbol=intent.symbol,
            side=intent.side,
            qty=intent.qty,
            order_type=intent.order_type,
            price=intent.price,
            strategy=intent.strategy_code,
            tags={
                "product": intent.product,
                "validity": intent.validity,
                "trigger_price": intent.trigger_price,
                "tag": intent.tag,
                "reason": intent.reason,
                "confidence": intent.confidence,
                **intent.metadata
            }
        )
    
    def _map_status(self, status):
        """Map V3 OrderStatus to V2 status string."""
        STATUS_MAP = {
            OrderStatus.OPEN: "PLACED",
            OrderStatus.FILLED: "FILLED",
            OrderStatus.CANCELLED: "CANCELLED",
            OrderStatus.REJECTED: "REJECTED",
            OrderStatus.SUBMITTED: "PLACED",
            OrderStatus.NEW: "PLACED",
            OrderStatus.PARTIALLY_FILLED: "PARTIAL",
            OrderStatus.ERROR: "REJECTED",
        }
        return STATUS_MAP.get(status, str(status).upper())
    
    def _convert_order_to_result(self, order: Order) -> ExecutionResult:
        """
        Convert V3 Order to V2 ExecutionResult.
        
        Args:
            order: V3 Order
            
        Returns:
            V2 ExecutionResult
        """
        # Use helper method to map status
        status = self._map_status(order.status)
        
        return ExecutionResult(
            order_id=order.order_id,
            status=status,
            symbol=order.symbol,
            side=order.side,
            qty=order.qty,
            avg_price=order.avg_price,
            message=order.message,
            raw={
                "v3_order": order.dict() if hasattr(order, 'dict') else order.model_dump(),
                "filled_qty": order.filled_qty,
                "tags": order.tags,
            },
            timestamp=order.updated_at.isoformat(),
        )


def create_execution_engine(
    mode: str,
    config: Dict[str, Any],
    state_store: Any,
    journal_store: Any,
    mde: Optional[Any] = None,
    broker: Optional[Any] = None,
    guardian: Optional[Any] = None,
    throttler: Optional[Any] = None,
    logger_instance: Optional[logging.Logger] = None,
    use_v3: bool = True,
) -> Any:
    """
    Factory function to create execution engine (V2 or V3).
    
    Args:
        mode: 'paper' or 'live'
        config: Configuration dict
        state_store: StateStore instance
        journal_store: JournalStateStore instance
        mde: MarketDataEngine (for paper mode)
        broker: Broker instance (for live mode)
        guardian: TradeGuardian instance
        throttler: TradeThrottler instance
        logger_instance: Logger instance
        use_v3: If True, use V3 engine with V2 adapter (default True)
        
    Returns:
        Execution engine instance
    """
    log = logger_instance or logger
    
    if use_v3:
        log.info("Creating ExecutionEngine V3 (with V2 adapter)")
        return ExecutionEngineV2ToV3Adapter(
            mode=mode,
            broker=broker,
            state_store=state_store,
            journal_store=journal_store,
            trade_throttler=throttler,
            logger_instance=log,
            config=config,
            mde=mde,
            guardian=guardian,
        )
    else:
        # Fall back to V2
        log.info("Creating ExecutionEngine V2 (legacy)")
        from engine.execution_engine import ExecutionEngineV2
        
        return ExecutionEngineV2(
            mode=mode,
            broker=broker,
            state_store=state_store,
            journal_store=journal_store,
            trade_throttler=throttler,
            logger_instance=log,
            config=config,
            mde=mde,
        )
