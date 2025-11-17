"""
Execution Service

Validates orders, sizes via portfolio service, routes to broker.
Publishes order.filled events on fills.

Features:
- execute(order_intent) -> OrderResult
- Order validation (symbol, qty, side)
- Position sizing via portfolio service
- Routing to PaperBroker or LiveBroker
- Event publishing for fills
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from core.strategy_engine_v2 import OrderIntent
from services.event_bus import EventBus

logger = logging.getLogger(__name__)


@dataclass
class OrderResult:
    """
    Result of an order execution.
    
    Attributes:
        order_id: Unique order identifier
        status: Order status (PLACED, FILLED, REJECTED, etc.)
        symbol: Trading symbol
        side: BUY or SELL
        qty: Order quantity
        avg_price: Average fill price (if filled)
        message: Status message or error
        timestamp: Order timestamp
    """
    order_id: Optional[str]
    status: str
    symbol: str
    side: str
    qty: int
    avg_price: Optional[float] = None
    message: Optional[str] = None
    timestamp: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "order_id": self.order_id,
            "status": self.status,
            "symbol": self.symbol,
            "side": self.side,
            "qty": self.qty,
            "avg_price": self.avg_price,
            "message": self.message,
            "timestamp": self.timestamp,
            "metadata": self.metadata or {},
        }


class ExecutionService:
    """
    Execution Service for order validation and routing.
    
    Responsibilities:
    - Validate order intents
    - Apply position sizing
    - Route to paper or live broker
    - Publish order.filled events
    """
    
    def __init__(
        self,
        broker: Any,
        portfolio_service: Optional[Any] = None,
        event_bus: Optional[EventBus] = None,
        mode: str = "paper",
        max_position_size: int = 100,
    ):
        """
        Initialize Execution Service.
        
        Args:
            broker: Broker instance (PaperBroker or LiveBroker)
            portfolio_service: PortfolioService for position sizing
            event_bus: EventBus for order events
            mode: Execution mode (paper or live)
            max_position_size: Maximum position size per symbol
        """
        self.broker = broker
        self.portfolio = portfolio_service
        self.bus = event_bus
        self.mode = mode
        self.max_position_size = max_position_size
        
        logger.info(
            "ExecutionService initialized (mode=%s, max_position_size=%d)",
            mode,
            max_position_size
        )
    
    def execute(self, order_intent: OrderIntent) -> OrderResult:
        """
        Execute an order intent.
        
        Steps:
        1. Validate order intent
        2. Apply position sizing
        3. Route to broker
        4. Publish order.filled event on success
        
        Args:
            order_intent: OrderIntent from strategy
            
        Returns:
            OrderResult with execution details
        """
        # Step 1: Validate order
        validation_error = self._validate_order(order_intent)
        if validation_error:
            logger.warning("Order validation failed: %s", validation_error)
            return self._rejected_result(
                order_intent,
                f"Validation failed: {validation_error}"
            )
        
        # Step 2: Apply position sizing
        sized_qty = self._apply_sizing(order_intent)
        if sized_qty == 0:
            logger.debug("Position sizing returned 0 for %s", order_intent.symbol)
            return self._rejected_result(
                order_intent,
                "Position sizing rejected (qty=0)"
            )
        
        # Update quantity
        order_intent.qty = sized_qty
        
        # Step 3: Route to broker
        try:
            result = self._route_to_broker(order_intent)
        except Exception as exc:
            logger.error(
                "Broker execution error for %s: %s",
                order_intent.symbol,
                exc,
                exc_info=True
            )
            return self._rejected_result(
                order_intent,
                f"Broker error: {exc}"
            )
        
        # Step 4: Publish order.filled event if successful
        if result.status == "FILLED" and self.bus:
            try:
                self.bus.publish("order.filled", {
                    "order_id": result.order_id,
                    "symbol": result.symbol,
                    "side": result.side,
                    "qty": result.qty,
                    "avg_price": result.avg_price,
                    "timestamp": result.timestamp,
                    "strategy_code": order_intent.strategy_code,
                })
            except Exception as exc:
                logger.debug("Error publishing order.filled event: %s", exc)
        
        return result
    
    def _validate_order(self, order_intent: OrderIntent) -> Optional[str]:
        """
        Validate order intent.
        
        Args:
            order_intent: OrderIntent to validate
            
        Returns:
            Error message if invalid, None if valid
        """
        # Check symbol
        if not order_intent.symbol:
            return "Missing symbol"
        
        # Check action
        action = order_intent.action.upper()
        if action not in ("BUY", "SELL", "EXIT", "HOLD"):
            return f"Invalid action: {action}"
        
        # Skip HOLD/EXIT for now
        if action in ("HOLD", "EXIT"):
            return "HOLD/EXIT not actionable"
        
        # Check quantity
        if not order_intent.qty or order_intent.qty <= 0:
            return "Invalid quantity"
        
        return None
    
    def _apply_sizing(self, order_intent: OrderIntent) -> int:
        """
        Apply position sizing.
        
        Args:
            order_intent: OrderIntent to size
            
        Returns:
            Sized quantity (0 if rejected)
        """
        # Use portfolio service if available
        if self.portfolio:
            try:
                # Get current position
                current_pos = self.portfolio.get_position(order_intent.symbol)
                current_qty = current_pos.get("qty", 0) if current_pos else 0
                
                # Check if adding this would exceed max
                action = order_intent.action.upper()
                if action == "BUY":
                    new_qty = current_qty + order_intent.qty
                elif action == "SELL":
                    new_qty = current_qty - order_intent.qty
                else:
                    new_qty = current_qty
                
                if abs(new_qty) > self.max_position_size:
                    logger.debug(
                        "Position size limit reached for %s (current=%d, requested=%d)",
                        order_intent.symbol,
                        current_qty,
                        order_intent.qty
                    )
                    return 0
            except Exception as exc:
                logger.warning("Position sizing check failed: %s", exc)
        
        # Default: use order qty, capped at max
        return min(order_intent.qty, self.max_position_size)
    
    def _route_to_broker(self, order_intent: OrderIntent) -> OrderResult:
        """
        Route order to broker.
        
        Args:
            order_intent: OrderIntent to execute
            
        Returns:
            OrderResult from broker
        """
        if not self.broker:
            return self._rejected_result(order_intent, "No broker available")
        
        # Generate order ID
        order_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Map action to side
        side = order_intent.action.upper()
        if side not in ("BUY", "SELL"):
            side = "BUY" if side in ("LONG", "ENTRY") else "SELL"
        
        # For paper mode, simulate immediate fill
        if self.mode == "paper":
            # Simulate fill with order intent metadata
            avg_price = order_intent.metadata.get("price", 0.0)
            
            logger.info(
                "PAPER: %s %d %s @ %.2f (strategy=%s)",
                side,
                order_intent.qty,
                order_intent.symbol,
                avg_price,
                getattr(order_intent, "strategy_code", "unknown")
            )
            
            reason = getattr(order_intent, "reason", "Paper trade")
            
            return OrderResult(
                order_id=order_id,
                status="FILLED",
                symbol=order_intent.symbol,
                side=side,
                qty=order_intent.qty,
                avg_price=avg_price,
                message=f"Paper fill: {reason}",
                timestamp=timestamp,
                metadata={
                    "strategy_code": getattr(order_intent, "strategy_code", "unknown"),
                    "confidence": getattr(order_intent, "confidence", 0.0),
                    "mode": "paper",
                }
            )
        
        # For live mode, route to actual broker
        try:
            # Call broker's place_order method
            broker_result = self.broker.place_order(
                symbol=order_intent.symbol,
                side=side,
                qty=order_intent.qty,
                order_type=getattr(order_intent, "order_type", "MARKET"),
                price=getattr(order_intent, "price", None),
            )
            
            return OrderResult(
                order_id=broker_result.get("order_id", order_id),
                status=broker_result.get("status", "PLACED"),
                symbol=order_intent.symbol,
                side=side,
                qty=order_intent.qty,
                avg_price=broker_result.get("avg_price"),
                message=broker_result.get("message", "Order placed"),
                timestamp=timestamp,
                metadata={
                    "strategy_code": order_intent.strategy_code,
                    "broker_result": broker_result,
                }
            )
        except Exception as exc:
            logger.error("Broker error: %s", exc, exc_info=True)
            return self._rejected_result(
                order_intent,
                f"Broker error: {exc}"
            )
    
    def _rejected_result(
        self,
        order_intent: OrderIntent,
        message: str
    ) -> OrderResult:
        """
        Create a rejected OrderResult.
        
        Args:
            order_intent: Original order intent
            message: Rejection reason
            
        Returns:
            OrderResult with REJECTED status
        """
        return OrderResult(
            order_id=None,
            status="REJECTED",
            symbol=order_intent.symbol,
            side=order_intent.action.upper(),
            qty=order_intent.qty or 0,
            message=message,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
