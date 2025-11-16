"""
PaperExecutionEngine - Standalone paper trading execution engine.

This module provides a safe, realistic paper trading execution engine with
configurable simulation features. All simulation features default to OFF for
maximum safety and deterministic behavior.

Features:
- Fill simulation based on last trade price from market data
- Optional slippage simulation (default: OFF)
- Optional spread simulation (default: OFF)  
- Optional partial fill simulation (default: OFF)
- Optional latency simulation (default: OFF)
- Order lifecycle tracking with events
- Position state management
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.execution_engine_v3 import (
    EventBus,
    EventType,
    ExecutionEngine,
    Order,
    OrderStatus,
)

logger = logging.getLogger(__name__)


class PaperExecutionEngine(ExecutionEngine):
    """
    Safe paper execution engine with realistic market simulation.
    
    All simulation features default to OFF for deterministic, safe behavior.
    Features can be enabled individually via configuration.
    
    Example config:
    {
        "execution": {
            "paper": {
                "slippage_enabled": false,  # Default OFF
                "slippage_bps": 5.0,
                "spread_enabled": false,     # Default OFF
                "spread_bps": 2.0,
                "partial_fill_enabled": false,  # Default OFF
                "latency_enabled": false     # Default OFF
            }
        }
    }
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
        
        # Extract paper execution config with safe defaults
        paper_config = config.get("execution", {}).get("paper", {})
        
        # All simulation features default to OFF for safety
        self.slippage_enabled = paper_config.get("slippage_enabled", False)
        self.slippage_bps = paper_config.get("slippage_bps", 5.0)
        
        self.spread_enabled = paper_config.get("spread_enabled", False)
        self.spread_bps = paper_config.get("spread_bps", 2.0)
        
        self.partial_fill_enabled = paper_config.get("partial_fill_enabled", False)
        self.partial_fill_probability = paper_config.get("partial_fill_probability", 0.1)
        self.partial_fill_ratio = paper_config.get("partial_fill_ratio", 0.5)
        
        self.latency_enabled = paper_config.get("latency_enabled", False)
        self.latency_ms = paper_config.get("latency_ms", 50)
        
        # Order tracking
        self.orders: Dict[str, Order] = {}
        self.fill_counter = 0
        
        self.logger.info(
            "PaperExecutionEngine initialized: slippage=%s, spread=%s, partial_fill=%s, latency=%s",
            "ON" if self.slippage_enabled else "OFF",
            "ON" if self.spread_enabled else "OFF",
            "ON" if self.partial_fill_enabled else "OFF",
            "ON" if self.latency_enabled else "OFF"
        )
    
    async def place_order(self, order: Order) -> Order:
        """
        Place a paper order with optional realistic simulation.
        
        Pipeline:
        1. Set order status to SUBMITTED
        2. Simulate latency (if enabled)
        3. Get market price from MDE
        4. Check if order is marketable (for LIMIT orders)
        5. Calculate fill price with slippage/spread (if enabled)
        6. Simulate partial fills (if enabled)
        7. Update order object with fill details
        8. Update state_store for positions
        9. Publish order_filled or order_open event
        
        Args:
            order: Order to place
            
        Returns:
            Updated order with execution details
        """
        # Set status to submitted
        order.status = OrderStatus.SUBMITTED
        order.updated_at = datetime.now(timezone.utc)
        order.events.append({
            "timestamp": order.updated_at.isoformat(),
            "status": order.status,
            "message": "Order submitted to paper engine"
        })
        
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
                return order
            
            # Check if LIMIT order is marketable
            if order.order_type == "LIMIT":
                if not self._is_limit_marketable(order.price, ltp, order.side):
                    # LIMIT order not marketable - leave as OPEN
                    order.status = OrderStatus.OPEN
                    order.remaining_qty = order.qty
                    order.message = f"LIMIT order placed (price={order.price}, LTP={ltp})"
                    order.updated_at = datetime.now(timezone.utc)
                    order.events.append({
                        "timestamp": order.updated_at.isoformat(),
                        "status": order.status,
                        "message": order.message
                    })
                    await self.event_bus.publish(EventType.ORDER_PLACED, {
                        "order_id": order.order_id,
                        "symbol": order.symbol,
                        "reason": order.message
                    })
                    self.logger.info(
                        "PAPER LIMIT order placed: %s %d x %s @ %.2f (LTP=%.2f, not marketable)",
                        order.side, order.qty, order.symbol, order.price, ltp
                    )
                    return order
            
            # Calculate fill price with optional slippage and spread
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
                "ltp": ltp,
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
            
            self.logger.info(
                "✅ PAPER FILL: %s %d x %s @ %.2f (LTP=%.2f, slippage=%s, spread=%s)",
                order.side, filled_qty, order.symbol, fill_price, ltp,
                "ON" if self.slippage_enabled else "OFF",
                "ON" if self.spread_enabled else "OFF"
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
        Calculate fill price with optional slippage and spread.
        
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
