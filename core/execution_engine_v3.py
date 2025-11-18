"""
ExecutionEngine V3 - Unified execution layer for PAPER and LIVE modes.

This module provides:
- Clean abstract interface for execution engines
- Enhanced paper execution with realistic simulation
- Production-ready live execution with retry logic and reconciliation
- Lightweight EventBus for real-time monitoring
- 100% backward compatibility with existing paper trading
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field

from analytics.telemetry_bus import publish_order_event

logger = logging.getLogger(__name__)


# ============================================================================
# Models
# ============================================================================

class OrderStatus(str, Enum):
    """
    Unified order status enumeration for execution lifecycle.
    
    Status Flow:
    - new: Order created but not yet submitted
    - submitted: Order submitted to broker/paper engine  
    - open: Order accepted and waiting for fill
    - partially_filled: Order partially executed
    - filled: Order completely executed
    - cancelled: Order cancelled before complete fill
    - rejected: Order rejected by broker/validation
    - error: Order failed due to technical error
    """
    NEW = "new"
    SUBMITTED = "submitted"
    OPEN = "open"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    ERROR = "error"


class Order(BaseModel):
    """
    Unified order model for both PAPER and LIVE modes.
    
    This model is used across the execution engine to represent orders
    in a normalized format with full lifecycle tracking.
    """
    order_id: str = Field(..., description="Unique order identifier")
    symbol: str = Field(..., description="Trading symbol")
    side: str = Field(..., description="BUY or SELL")
    qty: int = Field(..., description="Order quantity", gt=0)
    order_type: str = Field(..., description="MARKET or LIMIT")
    price: Optional[float] = Field(None, description="Limit price (for LIMIT orders)")
    status: str = Field(default=OrderStatus.NEW, description="Order status")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    strategy: str = Field(..., description="Strategy identifier")
    tags: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    
    # Execution details (filled when order is executed)
    filled_qty: int = Field(default=0, description="Quantity filled")
    remaining_qty: Optional[int] = Field(None, description="Quantity remaining to be filled")
    avg_fill_price: Optional[float] = Field(None, description="Average fill price")
    message: Optional[str] = Field(None, description="Status message or error")
    events: List[Dict[str, Any]] = Field(default_factory=list, description="Detailed fill history")
    
    # Legacy field alias for backward compatibility
    @property
    def avg_price(self) -> Optional[float]:
        """Alias for backward compatibility."""
        return self.avg_fill_price
    
    def model_post_init(self, __context: Any) -> None:
        """Initialize derived fields after model creation."""
        if self.remaining_qty is None:
            self.remaining_qty = self.qty
    
    class Config:
        use_enum_values = True


# ============================================================================
# EventBus
# ============================================================================

class EventType(str, Enum):
    """Event types for the EventBus."""
    ORDER_PLACED = "order_placed"
    ORDER_FILLED = "order_filled"
    ORDER_REJECTED = "order_rejected"
    ORDER_CANCELLED = "order_cancelled"
    ORDER_UPDATED = "order_updated"
    POSITION_UPDATED = "position_updated"
    POSITION_SYNCED = "position_synced"
    RECONCILIATION_DISCREPANCY = "reconciliation_discrepancy"


@dataclass
class Event:
    """Event data structure."""
    type: EventType
    timestamp: datetime
    data: Dict[str, Any]


class EventBus:
    """
    Lightweight event bus for execution events.
    
    Features:
    - Publish/subscribe pattern
    - Event buffering for dashboard/API consumption
    - Thread-safe operation
    """
    
    def __init__(self, buffer_size: int = 1000):
        """
        Initialize EventBus.
        
        Args:
            buffer_size: Maximum number of events to buffer
        """
        self.buffer: deque = deque(maxlen=buffer_size)
        self.subscribers: Dict[EventType, List[Callable]] = {}
        self._lock = asyncio.Lock()
        
    async def publish(self, event_type: EventType, data: Dict[str, Any]):
        """
        Publish an event to all subscribers.
        
        Args:
            event_type: Type of event
            data: Event data
        """
        event = Event(
            type=event_type,
            timestamp=datetime.now(timezone.utc),
            data=data
        )
        
        async with self._lock:
            # Add to buffer
            self.buffer.append(event)
            
            # Notify subscribers
            subscribers = self.subscribers.get(event_type, [])
            for callback in subscribers:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(event)
                    else:
                        callback(event)
                except Exception as exc:
                    logger.error(f"Error in event subscriber: {exc}", exc_info=True)
    
    def subscribe(self, event_type: EventType, callback: Callable):
        """
        Subscribe to an event type.
        
        Args:
            event_type: Type of event to subscribe to
            callback: Callback function to invoke when event occurs
        """
        if event_type not in self.subscribers:
            self.subscribers[event_type] = []
        self.subscribers[event_type].append(callback)
    
    def get_recent_events(self, event_type: Optional[EventType] = None, limit: int = 100) -> List[Event]:
        """
        Get recent events from buffer.
        
        Args:
            event_type: Filter by event type (None for all)
            limit: Maximum number of events to return
            
        Returns:
            List of recent events
        """
        events = list(self.buffer)
        
        if event_type:
            events = [e for e in events if e.type == event_type]
        
        return events[-limit:]


# ============================================================================
# Abstract ExecutionEngine Interface
# ============================================================================

class ExecutionEngine(ABC):
    """
    Abstract base class for execution engines.
    
    This defines the interface that all execution engines (Paper, Live)
    must implement.
    """
    
    def __init__(self, event_bus: Optional[EventBus] = None):
        """
        Initialize the execution engine.
        
        Args:
            event_bus: Optional EventBus for event publishing
        """
        self.event_bus = event_bus or EventBus()
    
    @abstractmethod
    async def place_order(self, order: Order) -> Order:
        """
        Place an order.
        
        Args:
            order: Order to place
            
        Returns:
            Updated order with execution details
        """
        pass
    
    @abstractmethod
    async def cancel_order(self, order_id: str) -> Order:
        """
        Cancel an existing order.
        
        Args:
            order_id: ID of order to cancel
            
        Returns:
            Updated order with cancellation details
        """
        pass
    
    @abstractmethod
    async def poll_orders(self) -> List[Order]:
        """
        Poll for order updates.
        
        Returns:
            List of all active orders with latest status
        """
        pass


# ============================================================================
# Paper Execution Engine
# ============================================================================

class PaperExecutionEngine(ExecutionEngine):
    """
    Enhanced paper execution engine with realistic market simulation.
    
    Features:
    - Simulated fills based on last tick from MDE
    - Configurable slippage
    - Spread simulation
    - Partial fill simulation
    - Latency simulation
    - Deterministic behavior when simulations are disabled
    """
    
    def __init__(
        self,
        market_data_engine: Any,
        state_store: Any,
        config: Dict[str, Any],
        event_bus: Optional[EventBus] = None,
        logger_instance: Optional[logging.Logger] = None
    ):
        """
        Initialize PaperExecutionEngine.
        
        Args:
            market_data_engine: Market data engine for price data
            state_store: State store for persistence
            config: Configuration dict
            event_bus: Optional EventBus instance
            logger_instance: Optional logger instance
        """
        super().__init__(event_bus)
        self.mde = market_data_engine
        self.state_store = state_store
        self.config = config
        self.logger = logger_instance or logger
        
        # Extract paper execution config
        paper_config = config.get("execution", {}).get("paper", {})
        
        # Slippage configuration
        self.slippage_bps = paper_config.get("slippage_bps", 5.0)
        self.slippage_enabled = paper_config.get("slippage_enabled", True)
        
        # Spread simulation
        self.spread_bps = paper_config.get("spread_bps", 2.0)
        self.spread_enabled = paper_config.get("spread_enabled", False)
        
        # Partial fill simulation
        self.partial_fill_enabled = paper_config.get("partial_fill_enabled", False)
        self.partial_fill_probability = paper_config.get("partial_fill_probability", 0.1)
        self.partial_fill_ratio = paper_config.get("partial_fill_ratio", 0.5)
        
        # Latency simulation
        self.latency_enabled = paper_config.get("latency_enabled", False)
        self.latency_ms = paper_config.get("latency_ms", 50)
        
        # Order tracking
        self.orders: Dict[str, Order] = {}
        self.fill_counter = 0
        
        self.logger.info(
            "PaperExecutionEngine initialized: slippage=%s bps, spread=%s bps, "
            "partial_fill=%s, latency=%sms",
            self.slippage_bps if self.slippage_enabled else "disabled",
            self.spread_bps if self.spread_enabled else "disabled",
            "enabled" if self.partial_fill_enabled else "disabled",
            self.latency_ms if self.latency_enabled else "disabled"
        )
    
    async def place_order(self, order: Order) -> Order:
        """
        Place a paper order with realistic simulation.
        
        Args:
            order: Order to place
            
        Returns:
            Updated order with execution details
        """
        # Simulate latency if enabled
        if self.latency_enabled:
            await asyncio.sleep(self.latency_ms / 1000.0)
        
        # Generate order ID if not present
        if not order.order_id or order.order_id == "":
            self.fill_counter += 1
            timestamp = datetime.now(timezone.utc)
            order.order_id = f"PAPER-{timestamp.strftime('%Y%m%d%H%M%S')}-{self.fill_counter:04d}"
        
        # Store order
        self.orders[order.order_id] = order
        
        # Get market price
        try:
            ltp = await self._get_market_price(order.symbol)
            
            if ltp is None or ltp <= 0:
                order.status = OrderStatus.REJECTED
                order.remaining_qty = order.qty
                order.message = f"No market data available for {order.symbol}"
                order.updated_at = datetime.now(timezone.utc)
                order.events.append({
                    "timestamp": order.updated_at.isoformat(),
                    "status": order.status,
                    "message": order.message
                })
                await self.event_bus.publish(EventType.ORDER_REJECTED, {
                    "order_id": order.order_id,
                    "symbol": order.symbol,
                    "reason": order.message
                })
                
                # Publish to telemetry bus
                publish_order_event(
                    order_id=order.order_id,
                    symbol=order.symbol,
                    side=order.side,
                    status=OrderStatus.REJECTED,
                    reason=order.message,
                    strategy=order.strategy,
                )
                
                return order
            
            # Check if LIMIT order is marketable
            if order.order_type == "LIMIT":
                if not self._is_limit_marketable(order.price, ltp, order.side):
                    order.status = OrderStatus.REJECTED
                    order.remaining_qty = order.qty
                    order.message = f"LIMIT price {order.price} not marketable (LTP={ltp})"
                    order.updated_at = datetime.now(timezone.utc)
                    order.events.append({
                        "timestamp": order.updated_at.isoformat(),
                        "status": order.status,
                        "message": order.message
                    })
                    await self.event_bus.publish(EventType.ORDER_REJECTED, {
                        "order_id": order.order_id,
                        "symbol": order.symbol,
                        "reason": order.message
                    })
                    
                    # Publish to telemetry bus
                    publish_order_event(
                        order_id=order.order_id,
                        symbol=order.symbol,
                        side=order.side,
                        status=OrderStatus.REJECTED,
                        reason=order.message,
                        strategy=order.strategy,
                    )
                    
                    return order
            
            # Calculate fill price with slippage and spread
            fill_price = self._calculate_fill_price(ltp, order.side, order.order_type, order.price)
            
            # Simulate partial fills if enabled
            filled_qty = order.qty
            if self.partial_fill_enabled:
                import random
                if random.random() < self.partial_fill_probability:
                    filled_qty = int(order.qty * self.partial_fill_ratio)
                    if filled_qty < 1:
                        filled_qty = 1
            
            # Update order
            order.status = OrderStatus.FILLED if filled_qty == order.qty else OrderStatus.PARTIALLY_FILLED
            order.filled_qty = filled_qty
            order.remaining_qty = order.qty - filled_qty
            order.avg_fill_price = fill_price
            order.message = "Paper order filled successfully"
            order.updated_at = datetime.now(timezone.utc)
            order.events.append({
                "timestamp": order.updated_at.isoformat(),
                "status": order.status,
                "filled_qty": filled_qty,
                "fill_price": fill_price,
                "message": order.message
            })
            
            # Update state store with position
            self._update_position(order)
            
            # Publish event
            await self.event_bus.publish(
                EventType.ORDER_FILLED if order.status == OrderStatus.FILLED else EventType.ORDER_PLACED,
                {
                    "order_id": order.order_id,
                    "symbol": order.symbol,
                    "side": order.side,
                    "qty": filled_qty,
                    "price": fill_price,
                    "status": order.status,
                    "remaining_qty": order.remaining_qty
                }
            )
            
            # Also publish to telemetry bus
            publish_order_event(
                order_id=order.order_id,
                symbol=order.symbol,
                side=order.side,
                status=order.status,
                qty=filled_qty,
                price=fill_price,
                remaining_qty=order.remaining_qty,
                strategy=order.strategy,
                order_type=order.order_type,
            )
            
            self.logger.info(
                "✅ PAPER FILL: %s %d x %s @ %.2f (LTP=%.2f)",
                order.side, filled_qty, order.symbol, fill_price, ltp
            )
            
        except Exception as exc:
            self.logger.error(f"Paper order execution failed: {exc}", exc_info=True)
            order.status = OrderStatus.ERROR
            order.remaining_qty = order.qty
            order.message = f"Execution error: {exc}"
            order.updated_at = datetime.now(timezone.utc)
            order.events.append({
                "timestamp": order.updated_at.isoformat(),
                "status": order.status,
                "message": order.message
            })
            await self.event_bus.publish(EventType.ORDER_REJECTED, {
                "order_id": order.order_id,
                "symbol": order.symbol,
                "reason": order.message
            })
        
        return order
    
    async def cancel_order(self, order_id: str) -> Order:
        """
        Cancel a paper order.
        
        Args:
            order_id: ID of order to cancel
            
        Returns:
            Updated order with cancellation status
        """
        if order_id not in self.orders:
            raise ValueError(f"Order {order_id} not found")
        
        order = self.orders[order_id]
        
        if order.status in [OrderStatus.FILLED, OrderStatus.CANCELLED]:
            return order
        
        order.status = OrderStatus.CANCELLED
        order.remaining_qty = order.qty - order.filled_qty
        order.message = "Order cancelled"
        order.updated_at = datetime.now(timezone.utc)
        order.events.append({
            "timestamp": order.updated_at.isoformat(),
            "status": order.status,
            "message": order.message
        })
        
        await self.event_bus.publish(EventType.ORDER_CANCELLED, {
            "order_id": order.order_id,
            "symbol": order.symbol
        })
        
        self.logger.info(f"Paper order {order_id} cancelled")
        
        return order
    
    async def poll_orders(self) -> List[Order]:
        """
        Get all paper orders.
        
        Returns:
            List of all orders
        """
        return list(self.orders.values())
    
    async def _get_market_price(self, symbol: str) -> Optional[float]:
        """
        Get current market price from MDE.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Last traded price or None
        """
        try:
            timeframe = self.config.get("data", {}).get("timeframe", "5m")
            candle = self.mde.get_latest_candle(symbol, timeframe)
            
            if not candle:
                return None
            
            return float(candle.get("close", 0))
        except Exception as exc:
            self.logger.error(f"Error getting market price for {symbol}: {exc}")
            return None
    
    def _calculate_fill_price(
        self,
        ltp: float,
        side: str,
        order_type: str,
        limit_price: Optional[float]
    ) -> float:
        """
        Calculate fill price with slippage and spread.
        
        Args:
            ltp: Last traded price
            side: BUY or SELL
            order_type: MARKET or LIMIT
            limit_price: Limit price (for LIMIT orders)
            
        Returns:
            Fill price
        """
        if order_type == "LIMIT" and limit_price is not None:
            # LIMIT orders fill at limit price
            return limit_price
        
        # Start with LTP
        fill_price = ltp
        
        # Apply spread if enabled
        if self.spread_enabled:
            spread_multiplier = self.spread_bps / 10000.0
            if side == "BUY":
                fill_price *= (1 + spread_multiplier / 2)
            else:  # SELL
                fill_price *= (1 - spread_multiplier / 2)
        
        # Apply slippage if enabled
        if self.slippage_enabled:
            slippage_multiplier = self.slippage_bps / 10000.0
            if side == "BUY":
                fill_price *= (1 + slippage_multiplier)
            else:  # SELL
                fill_price *= (1 - slippage_multiplier)
        
        return fill_price
    
    def _is_limit_marketable(
        self,
        limit_price: Optional[float],
        ltp: float,
        side: str
    ) -> bool:
        """
        Check if LIMIT order is marketable.
        
        Args:
            limit_price: Limit price
            ltp: Last traded price
            side: BUY or SELL
            
        Returns:
            True if marketable
        """
        if limit_price is None:
            return False
        
        if side == "BUY":
            return limit_price >= ltp
        else:  # SELL
            return limit_price <= ltp
    
    def _update_position(self, order: Order):
        """
        Update position in state store.
        
        Args:
            order: Filled order
        """
        try:
            state = self.state_store.load()
            if not state:
                return
            
            positions = state.get("positions", [])
            
            # Find existing position
            position = None
            for pos in positions:
                if pos.get("symbol") == order.symbol:
                    position = pos
                    break
            
            # Calculate position change
            qty_change = order.filled_qty if order.side == "BUY" else -order.filled_qty
            
            if position:
                current_qty = position.get("qty", 0)
                new_qty = current_qty + qty_change
                
                if new_qty == 0:
                    positions.remove(position)
                else:
                    position["qty"] = new_qty
                    position["avg_price"] = order.avg_fill_price
            else:
                positions.append({
                    "symbol": order.symbol,
                    "qty": qty_change,
                    "avg_price": order.avg_fill_price,
                    "entry_time": order.created_at.isoformat(),
                })
            
            state["positions"] = positions
            self.state_store.save(state)
            
            # Publish position update event
            asyncio.create_task(self.event_bus.publish(EventType.POSITION_UPDATED, {
                "symbol": order.symbol,
                "qty": qty_change,
                "price": order.avg_fill_price
            }))
            
        except Exception as exc:
            self.logger.error(f"Error updating position: {exc}", exc_info=True)


# ============================================================================
# Live Execution Engine
# ============================================================================

class LiveExecutionEngine(ExecutionEngine):
    """
    Production-ready live execution engine with Zerodha integration.
    
    Features:
    - Retry logic for API calls
    - Reconciliation loop (every 2-5 seconds)
    - Status normalization
    - Guardian safety validation
    - Fallback handling for REJECTED/CANCELLED
    - JournalStateStore integration
    """
    
    def __init__(
        self,
        broker: Any,
        guardian: Any,
        state_store: Any,
        journal_store: Any,
        config: Dict[str, Any],
        event_bus: Optional[EventBus] = None,
        logger_instance: Optional[logging.Logger] = None
    ):
        """
        Initialize LiveExecutionEngine.
        
        Args:
            broker: Broker instance (KiteBroker)
            guardian: TradeGuardian instance for safety checks
            state_store: State store for persistence
            journal_store: Journal store for order/fill logs
            config: Configuration dict
            event_bus: Optional EventBus instance
            logger_instance: Optional logger instance
        """
        super().__init__(event_bus)
        self.broker = broker
        self.guardian = guardian
        self.state_store = state_store
        self.journal_store = journal_store
        self.config = config
        self.logger = logger_instance or logger
        
        # Extract live execution config
        live_config = config.get("execution", {}).get("live", {})
        
        # Retry configuration
        self.retry_enabled = live_config.get("retry_enabled", True)
        self.max_retries = live_config.get("max_retries", 3)
        self.retry_delay = live_config.get("retry_delay", 1.0)
        
        # Reconciliation configuration
        self.reconciliation_enabled = live_config.get("reconciliation_enabled", True)
        self.reconciliation_interval = live_config.get("reconciliation_interval", 3.0)
        
        # Guardian validation
        self.guardian_enabled = live_config.get("guardian_enabled", True)
        
        # Order tracking
        self.orders: Dict[str, Order] = {}
        self._reconciliation_task = None
        
        # Start reconciliation loop if enabled
        if self.reconciliation_enabled:
            self._reconciliation_task = asyncio.create_task(self._reconciliation_loop())
        
        self.logger.info(
            "LiveExecutionEngine initialized: retry=%s (max=%d), reconciliation=%s (interval=%.1fs), guardian=%s",
            "enabled" if self.retry_enabled else "disabled",
            self.max_retries,
            "enabled" if self.reconciliation_enabled else "disabled",
            self.reconciliation_interval,
            "enabled" if self.guardian_enabled else "disabled"
        )
    
    async def place_order(self, order: Order) -> Order:
        """
        Place a live order with safety checks and retry logic.
        
        Args:
            order: Order to place
            
        Returns:
            Updated order with execution details
        """
        # Guardian safety validation
        if self.guardian_enabled:
            # Convert order to intent format for guardian
            intent = {
                "symbol": order.symbol,
                "side": order.side,
                "qty": order.qty,
                "strategy_code": order.strategy,
            }
            
            guardian_decision = self.guardian.validate_pre_trade(intent, None)
            if not guardian_decision.allow:
                order.status = OrderStatus.REJECTED
                order.remaining_qty = order.qty
                order.message = f"Guardian blocked: {guardian_decision.reason}"
                order.updated_at = datetime.now(timezone.utc)
                order.events.append({
                    "timestamp": order.updated_at.isoformat(),
                    "status": order.status,
                    "message": order.message
                })
                
                await self.event_bus.publish(EventType.ORDER_REJECTED, {
                    "order_id": order.order_id,
                    "symbol": order.symbol,
                    "reason": order.message
                })
                
                self.logger.warning(
                    f"🛡️ Guardian BLOCKED: {order.side} {order.qty} x {order.symbol} - {guardian_decision.reason}"
                )
                
                return order
        
        # Place order with retry logic
        for attempt in range(self.max_retries if self.retry_enabled else 1):
            try:
                # Map Order to broker format
                broker_intent = {
                    "symbol": order.symbol,
                    "side": order.side,
                    "qty": order.qty,
                    "order_type": order.order_type,
                    "price": order.price,
                    "exchange": order.tags.get("exchange", "NFO"),
                    "product": order.tags.get("product", "MIS"),
                }
                
                # Place order via broker
                result = self.broker.place_order(broker_intent)
                
                # Update order with broker response
                order.order_id = result.get("order_id", order.order_id)
                order.status = self._normalize_status(result.get("status", "SUBMITTED"))
                order.remaining_qty = order.qty - order.filled_qty
                order.message = result.get("message", "Order placed")
                order.updated_at = datetime.now(timezone.utc)
                order.events.append({
                    "timestamp": order.updated_at.isoformat(),
                    "status": order.status,
                    "message": order.message,
                    "broker_response": result
                })
                
                # Store order
                self.orders[order.order_id] = order
                
                # Append to journal
                self._append_to_journal(order)
                
                # Publish event
                await self.event_bus.publish(EventType.ORDER_PLACED, {
                    "order_id": order.order_id,
                    "symbol": order.symbol,
                    "side": order.side,
                    "qty": order.qty,
                    "status": order.status
                })
                
                self.logger.info(
                    f"🔴 LIVE ORDER PLACED: {order.side} {order.qty} x {order.symbol} (order_id={order.order_id})"
                )
                
                return order
                
            except Exception as exc:
                self.logger.error(f"Order placement attempt {attempt + 1} failed: {exc}", exc_info=True)
                
                if attempt < self.max_retries - 1 and self.retry_enabled:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                else:
                    # Final failure
                    order.status = OrderStatus.ERROR
                    order.remaining_qty = order.qty
                    order.message = f"Broker error after {attempt + 1} attempts: {exc}"
                    order.updated_at = datetime.now(timezone.utc)
                    order.events.append({
                        "timestamp": order.updated_at.isoformat(),
                        "status": order.status,
                        "message": order.message
                    })
                    
                    await self.event_bus.publish(EventType.ORDER_REJECTED, {
                        "order_id": order.order_id,
                        "symbol": order.symbol,
                        "reason": order.message
                    })
        
        return order
    
    async def cancel_order(self, order_id: str) -> Order:
        """
        Cancel a live order.
        
        Args:
            order_id: ID of order to cancel
            
        Returns:
            Updated order with cancellation status
        """
        if order_id not in self.orders:
            raise ValueError(f"Order {order_id} not found")
        
        order = self.orders[order_id]
        
        try:
            # Cancel via broker
            result = self.broker.cancel_order(order_id)
            
            order.status = OrderStatus.CANCELLED
            order.message = "Order cancelled"
            order.updated_at = datetime.now(timezone.utc)
            
            # Append to journal
            self._append_to_journal(order)
            
            await self.event_bus.publish(EventType.ORDER_CANCELLED, {
                "order_id": order.order_id,
                "symbol": order.symbol
            })
            
            self.logger.info(f"Live order {order_id} cancelled")
            
        except Exception as exc:
            self.logger.error(f"Failed to cancel order {order_id}: {exc}", exc_info=True)
            order.message = f"Cancel failed: {exc}"
        
        return order
    
    async def poll_orders(self) -> List[Order]:
        """
        Poll for order updates from broker.
        
        Returns:
            List of all orders with latest status
        """
        try:
            # Get orders from broker
            broker_orders = self.broker.get_orders()
            
            # Update tracked orders
            for broker_order in broker_orders:
                order_id = broker_order.get("order_id")
                if order_id in self.orders:
                    self._update_order_from_broker(self.orders[order_id], broker_order)
            
        except Exception as exc:
            self.logger.error(f"Failed to poll orders: {exc}", exc_info=True)
        
        return list(self.orders.values())
    
    async def _reconciliation_loop(self):
        """
        Background reconciliation loop to sync order status.
        """
        self.logger.info("Starting reconciliation loop")
        
        while True:
            try:
                await asyncio.sleep(self.reconciliation_interval)
                await self.poll_orders()
            except Exception as exc:
                self.logger.error(f"Reconciliation loop error: {exc}", exc_info=True)
    
    def _normalize_status(self, broker_status: str) -> str:
        """
        Normalize broker status to standard OrderStatus.
        
        Args:
            broker_status: Status from broker
            
        Returns:
            Normalized status
        """
        status_map = {
            "PENDING": OrderStatus.NEW,
            "NEW": OrderStatus.NEW,
            "SUBMITTED": OrderStatus.SUBMITTED,
            "OPEN": OrderStatus.OPEN,
            "COMPLETE": OrderStatus.FILLED,
            "FILLED": OrderStatus.FILLED,
            "REJECTED": OrderStatus.REJECTED,
            "CANCELLED": OrderStatus.CANCELLED,
            "PARTIAL": OrderStatus.PARTIALLY_FILLED,
            "PARTIALLY_FILLED": OrderStatus.PARTIALLY_FILLED,
        }
        
        return status_map.get(broker_status.upper(), OrderStatus.NEW)
    
    def _update_order_from_broker(self, order: Order, broker_order: Dict[str, Any]):
        """
        Update order with broker data.
        
        Args:
            order: Order to update
            broker_order: Broker order data
        """
        old_status = order.status
        new_status = self._normalize_status(broker_order.get("status", ""))
        
        if old_status != new_status:
            order.status = new_status
            order.updated_at = datetime.now(timezone.utc)
            
            # Update fill details if filled
            if new_status in [OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED]:
                order.filled_qty = broker_order.get("filled_quantity", order.filled_qty)
                order.remaining_qty = order.qty - order.filled_qty
                order.avg_fill_price = broker_order.get("average_price", order.avg_fill_price)
                order.events.append({
                    "timestamp": order.updated_at.isoformat(),
                    "status": new_status,
                    "filled_qty": order.filled_qty,
                    "avg_fill_price": order.avg_fill_price,
                    "broker_update": broker_order
                })
                
                # Publish fill event
                asyncio.create_task(self.event_bus.publish(EventType.ORDER_FILLED, {
                    "order_id": order.order_id,
                    "symbol": order.symbol,
                    "side": order.side,
                    "qty": order.filled_qty,
                    "price": order.avg_fill_price
                }))
                
                # Update position
                self._update_position(order)
                
                # Append to journal
                self._append_to_journal(order)
                
                self.logger.info(
                    f"✅ LIVE FILL: {order.side} {order.filled_qty} x {order.symbol} @ {order.avg_fill_price}"
                )
    
    def _update_position(self, order: Order):
        """
        Update position in state store.
        
        Args:
            order: Filled order
        """
        try:
            state = self.state_store.load()
            if not state:
                return
            
            positions = state.get("positions", [])
            
            # Find existing position
            position = None
            for pos in positions:
                if pos.get("symbol") == order.symbol:
                    position = pos
                    break
            
            # Calculate position change
            qty_change = order.filled_qty if order.side == "BUY" else -order.filled_qty
            
            if position:
                current_qty = position.get("qty", 0)
                new_qty = current_qty + qty_change
                
                if new_qty == 0:
                    positions.remove(position)
                else:
                    position["qty"] = new_qty
                    position["avg_price"] = order.avg_fill_price
            else:
                positions.append({
                    "symbol": order.symbol,
                    "qty": qty_change,
                    "avg_price": order.avg_fill_price,
                    "entry_time": order.created_at.isoformat(),
                })
            
            state["positions"] = positions
            self.state_store.save(state)
            
            # Publish position update event
            asyncio.create_task(self.event_bus.publish(EventType.POSITION_UPDATED, {
                "symbol": order.symbol,
                "qty": qty_change,
                "price": order.avg_fill_price
            }))
            
        except Exception as exc:
            self.logger.error(f"Error updating position: {exc}", exc_info=True)
    
    def _append_to_journal(self, order: Order):
        """
        Append order to journal.
        
        Args:
            order: Order to log
        """
        try:
            journal_row = {
                "order_id": order.order_id,
                "timestamp": order.updated_at.isoformat(),
                "symbol": order.symbol,
                "strategy": order.strategy,
                "side": order.side,
                "qty": order.qty,
                "filled_qty": order.filled_qty,
                "order_type": order.order_type,
                "status": order.status,
                "avg_price": order.avg_fill_price,
                "message": order.message,
                "mode": "live",
            }
            
            self.journal_store.append_orders([journal_row])
            
        except Exception as exc:
            self.logger.error(f"Failed to append to journal: {exc}", exc_info=True)
