"""
Execution Engine V3 - Unified execution layer with comprehensive order lifecycle management.

This module provides:
- Order lifecycle management (CREATED → SUBMITTED → FILLED → ACTIVE → SL/TP_PENDING → CLOSED → ARCHIVED)
- Fill simulation with bid/ask spread and slippage
- Stop Loss management with partial exit support
- Take Profit management
- Trailing Stop Loss
- Time-based stops
- Unified position tracking and PnL calculation
- Trade journal integration
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ============================================================================
# Order State Machine
# ============================================================================

class OrderState(str, Enum):
    """Order state in the lifecycle."""
    CREATED = "CREATED"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    ACTIVE = "ACTIVE"
    SL_PENDING = "SL_PENDING"
    TP_PENDING = "TP_PENDING"
    CLOSED = "CLOSED"
    ARCHIVED = "ARCHIVED"


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class Order:
    """Unified order model for execution engine V3."""
    order_id: str
    symbol: str
    qty: int
    side: str  # "BUY" or "SELL"
    sl_price: Optional[float] = None
    tp_price: Optional[float] = None
    time_stop_bars: Optional[int] = None
    tag: str = ""
    strategy_id: str = ""
    state: OrderState = OrderState.CREATED
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Fill information
    fill_price: Optional[float] = None
    fill_timestamp: Optional[datetime] = None
    
    # Position tracking
    entry_price: Optional[float] = None
    current_price: Optional[float] = None
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    
    # Lifecycle tracking
    bars_held: int = 0
    partial_exit_executed: bool = False
    trailing_sl_active: bool = False
    highest_price: Optional[float] = None  # For long positions
    lowest_price: Optional[float] = None   # For short positions
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)
    
    def add_event(self, event_type: str, message: str, **kwargs):
        """Add an event to the order history."""
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            "message": message,
            **kwargs
        }
        self.events.append(event)
        self.updated_at = datetime.now(timezone.utc)


@dataclass
class Position:
    """Position tracking model."""
    symbol: str
    qty: int
    side: str
    entry_price: float
    current_price: float
    order_id: str
    strategy_id: str
    sl_price: Optional[float] = None
    tp_price: Optional[float] = None
    trailing_sl_active: bool = False
    bars_held: int = 0
    unrealized_pnl: float = 0.0
    highest_price: Optional[float] = None
    lowest_price: Optional[float] = None


# ============================================================================
# OrderBuilder - Constructs orders from OrderIntent
# ============================================================================

class OrderBuilder:
    """Build orders from strategy signals."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize OrderBuilder.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.execution_config = config.get("execution", {})
        
    def build_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        sl_price: Optional[float] = None,
        tp_price: Optional[float] = None,
        time_stop_bars: Optional[int] = None,
        tag: str = "",
        strategy_id: str = ""
    ) -> Order:
        """
        Build an order from parameters.
        
        Args:
            symbol: Trading symbol
            qty: Quantity
            side: "BUY" or "SELL"
            sl_price: Stop loss price
            tp_price: Take profit price
            time_stop_bars: Time stop in bars
            tag: Order tag
            strategy_id: Strategy identifier
            
        Returns:
            Order object
        """
        order_id = self._generate_order_id()
        
        order = Order(
            order_id=order_id,
            symbol=symbol,
            qty=qty,
            side=side,
            sl_price=sl_price,
            tp_price=tp_price,
            time_stop_bars=time_stop_bars,
            tag=tag,
            strategy_id=strategy_id,
            state=OrderState.CREATED,
        )
        
        order.add_event("created", f"Order created: {side} {qty} {symbol}")
        
        return order
    
    def _generate_order_id(self) -> str:
        """Generate unique order ID."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        return f"V3-{timestamp}-{unique_id}"


# ============================================================================
# FillEngine - Determines fill prices with slippage and spread
# ============================================================================

class FillEngine:
    """Simulate fills with realistic pricing."""
    
    def __init__(self, config: Dict[str, Any], market_data_engine: Any = None):
        """
        Initialize FillEngine.
        
        Args:
            config: Configuration dictionary
            market_data_engine: Market data engine for price lookup
        """
        self.config = config
        self.mde = market_data_engine
        self.execution_config = config.get("execution", {})
        
        # Fill mode: "mid", "bid_ask", "ltp"
        self.fill_mode = self.execution_config.get("fill_mode", "mid")
        self.slippage_bps = self.execution_config.get("slippage_bps", 5)
        
        logger.info(f"FillEngine initialized: mode={self.fill_mode}, slippage={self.slippage_bps} bps")
    
    def determine_fill_price(self, order: Order, ltp: float, bid: Optional[float] = None, ask: Optional[float] = None) -> float:
        """
        Determine fill price based on configuration.
        
        Args:
            order: Order to fill
            ltp: Last traded price
            bid: Bid price (optional)
            ask: Ask price (optional)
            
        Returns:
            Fill price
        """
        # Determine base price
        if self.fill_mode == "bid_ask" and bid and ask:
            # Use bid for sell, ask for buy
            base_price = ask if order.side == "BUY" else bid
        elif self.fill_mode == "mid" and bid and ask:
            # Use mid price
            base_price = (bid + ask) / 2
        else:
            # Fallback to LTP
            base_price = ltp
        
        # Apply slippage
        fill_price = self._apply_slippage(base_price, order.side)
        
        return fill_price
    
    def _apply_slippage(self, price: float, side: str) -> float:
        """
        Apply slippage to price.
        
        Args:
            price: Base price
            side: "BUY" or "SELL"
            
        Returns:
            Price with slippage applied
        """
        slippage_factor = self.slippage_bps / 10000.0
        
        if side == "BUY":
            # Buy at higher price (unfavorable)
            return price * (1 + slippage_factor)
        else:
            # Sell at lower price (unfavorable)
            return price * (1 - slippage_factor)
    
    def fill_order(self, order: Order, ltp: float, bid: Optional[float] = None, ask: Optional[float] = None) -> Order:
        """
        Fill an order and update its state.
        
        Args:
            order: Order to fill
            ltp: Last traded price
            bid: Bid price
            ask: Ask price
            
        Returns:
            Updated order
        """
        fill_price = self.determine_fill_price(order, ltp, bid, ask)
        
        order.fill_price = fill_price
        order.entry_price = fill_price
        order.current_price = ltp
        order.fill_timestamp = datetime.now(timezone.utc)
        order.state = OrderState.FILLED
        
        # Initialize tracking for position monitoring
        if order.side == "BUY":
            order.highest_price = ltp
        else:
            order.lowest_price = ltp
        
        order.add_event("filled", f"Order filled at {fill_price:.2f}", fill_price=fill_price)
        
        logger.info(f"Order {order.order_id} filled: {order.side} {order.qty} {order.symbol} @ {fill_price:.2f}")
        
        return order


# ============================================================================
# StopLossManager - Monitors and executes stop losses
# ============================================================================

class StopLossManager:
    """Manage stop loss execution with partial exit support."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize StopLossManager.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.execution_config = config.get("execution", {})
        
        self.enable_partial_exit = self.execution_config.get("enable_partial_exit", False)
        self.partial_exit_pct = self.execution_config.get("partial_exit_pct", 0.5)
        
        logger.info(f"StopLossManager initialized: partial_exit={self.enable_partial_exit}, pct={self.partial_exit_pct}")
    
    def check_stop_loss(self, order: Order, current_price: float) -> Tuple[bool, Optional[str]]:
        """
        Check if stop loss is breached.
        
        Args:
            order: Active order
            current_price: Current market price
            
        Returns:
            Tuple of (breached, action) where action is "partial" or "full"
        """
        if not order.sl_price:
            return False, None
        
        # Check if SL is breached
        breached = False
        if order.side == "BUY" and current_price <= order.sl_price:
            breached = True
        elif order.side == "SELL" and current_price >= order.sl_price:
            breached = True
        
        if not breached:
            return False, None
        
        # Determine action: partial or full exit
        if self.enable_partial_exit and not order.partial_exit_executed:
            return True, "partial"
        else:
            return True, "full"
    
    def execute_stop_loss(self, order: Order, current_price: float, action: str) -> Order:
        """
        Execute stop loss.
        
        Args:
            order: Order to exit
            current_price: Current price
            action: "partial" or "full"
            
        Returns:
            Updated order
        """
        if action == "partial":
            # Exit partial position
            exit_qty = int(order.qty * self.partial_exit_pct)
            remaining_qty = order.qty - exit_qty
            
            # Calculate PnL for exited portion
            if order.side == "BUY":
                pnl = (current_price - order.entry_price) * exit_qty
            else:
                pnl = (order.entry_price - current_price) * exit_qty
            
            order.realized_pnl += pnl
            order.qty = remaining_qty
            order.partial_exit_executed = True
            order.state = OrderState.ACTIVE
            
            order.add_event(
                "partial_sl_exit",
                f"Partial SL exit: {exit_qty} @ {current_price:.2f}, PnL: {pnl:.2f}",
                exit_qty=exit_qty,
                exit_price=current_price,
                pnl=pnl
            )
            
            logger.info(f"Partial SL exit on {order.order_id}: {exit_qty} @ {current_price:.2f}, PnL: {pnl:.2f}")
            
        else:
            # Full exit
            if order.side == "BUY":
                pnl = (current_price - order.entry_price) * order.qty
            else:
                pnl = (order.entry_price - current_price) * order.qty
            
            order.realized_pnl += pnl
            order.state = OrderState.CLOSED
            
            order.add_event(
                "sl_exit",
                f"SL exit: {order.qty} @ {current_price:.2f}, PnL: {pnl:.2f}",
                exit_qty=order.qty,
                exit_price=current_price,
                pnl=pnl
            )
            
            logger.info(f"Full SL exit on {order.order_id}: {order.qty} @ {current_price:.2f}, PnL: {pnl:.2f}")
        
        return order


# ============================================================================
# TakeProfitManager - Monitors and executes take profits
# ============================================================================

class TakeProfitManager:
    """Manage take profit execution."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize TakeProfitManager.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        logger.info("TakeProfitManager initialized")
    
    def check_take_profit(self, order: Order, current_price: float) -> bool:
        """
        Check if take profit is hit.
        
        Args:
            order: Active order
            current_price: Current market price
            
        Returns:
            True if TP is hit
        """
        if not order.tp_price:
            return False
        
        # Check if TP is hit
        if order.side == "BUY" and current_price >= order.tp_price:
            return True
        elif order.side == "SELL" and current_price <= order.tp_price:
            return True
        
        return False
    
    def execute_take_profit(self, order: Order, current_price: float) -> Order:
        """
        Execute take profit - close entire position.
        
        Args:
            order: Order to close
            current_price: Current price
            
        Returns:
            Updated order
        """
        # Calculate PnL
        if order.side == "BUY":
            pnl = (current_price - order.entry_price) * order.qty
        else:
            pnl = (order.entry_price - current_price) * order.qty
        
        order.realized_pnl += pnl
        order.state = OrderState.CLOSED
        
        order.add_event(
            "tp_exit",
            f"TP exit: {order.qty} @ {current_price:.2f}, PnL: {pnl:.2f}",
            exit_qty=order.qty,
            exit_price=current_price,
            pnl=pnl
        )
        
        logger.info(f"TP exit on {order.order_id}: {order.qty} @ {current_price:.2f}, PnL: {pnl:.2f}")
        
        return order


# ============================================================================
# TrailingStopManager - Manages trailing stop loss
# ============================================================================

class TrailingStopManager:
    """Manage trailing stop loss."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize TrailingStopManager.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.execution_config = config.get("execution", {})
        
        self.enable_trailing = self.execution_config.get("enable_trailing", False)
        self.trail_step_r = self.execution_config.get("trail_step_r", 0.5)
        
        logger.info(f"TrailingStopManager initialized: enabled={self.enable_trailing}, step_r={self.trail_step_r}")
    
    def update_trailing_stop(self, order: Order, current_price: float) -> Order:
        """
        Update trailing stop if price moves favorably.
        
        Args:
            order: Order to update
            current_price: Current market price
            
        Returns:
            Updated order
        """
        if not self.enable_trailing or not order.sl_price:
            return order
        
        # Only trail after partial exit (if enabled) or if trailing is always active
        if not order.trailing_sl_active and order.partial_exit_executed:
            order.trailing_sl_active = True
        
        if not order.trailing_sl_active and not order.partial_exit_executed:
            # Start trailing immediately if no partial exit
            order.trailing_sl_active = True
        
        if not order.trailing_sl_active:
            return order
        
        # Update extreme prices
        if order.side == "BUY":
            if order.highest_price is None or current_price > order.highest_price:
                order.highest_price = current_price
                
                # Calculate new SL based on trail step
                risk = order.entry_price - order.sl_price
                new_sl = order.highest_price - (risk * self.trail_step_r)
                
                # Only raise SL, never lower
                if new_sl > order.sl_price:
                    old_sl = order.sl_price
                    order.sl_price = new_sl
                    order.add_event(
                        "trailing_sl_update",
                        f"Trailing SL raised: {old_sl:.2f} → {new_sl:.2f}",
                        old_sl=old_sl,
                        new_sl=new_sl
                    )
                    logger.debug(f"Trailing SL updated for {order.order_id}: {old_sl:.2f} → {new_sl:.2f}")
        
        else:  # SELL
            if order.lowest_price is None or current_price < order.lowest_price:
                order.lowest_price = current_price
                
                # Calculate new SL based on trail step
                risk = order.sl_price - order.entry_price
                new_sl = order.lowest_price + (risk * self.trail_step_r)
                
                # Only lower SL, never raise
                if new_sl < order.sl_price:
                    old_sl = order.sl_price
                    order.sl_price = new_sl
                    order.add_event(
                        "trailing_sl_update",
                        f"Trailing SL lowered: {old_sl:.2f} → {new_sl:.2f}",
                        old_sl=old_sl,
                        new_sl=new_sl
                    )
                    logger.debug(f"Trailing SL updated for {order.order_id}: {old_sl:.2f} → {new_sl:.2f}")
        
        return order


# ============================================================================
# TimeStopManager - Manages time-based exits
# ============================================================================

class TimeStopManager:
    """Manage time-based position exits."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize TimeStopManager.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.execution_config = config.get("execution", {})
        
        self.enable_time_stop = self.execution_config.get("enable_time_stop", False)
        self.time_stop_bars = self.execution_config.get("time_stop_bars", 20)
        
        logger.info(f"TimeStopManager initialized: enabled={self.enable_time_stop}, bars={self.time_stop_bars}")
    
    def check_time_stop(self, order: Order) -> bool:
        """
        Check if time stop is reached.
        
        Args:
            order: Order to check
            
        Returns:
            True if time stop is reached
        """
        if not self.enable_time_stop:
            return False
        
        # Use order-specific time stop if set, otherwise use default
        max_bars = order.time_stop_bars if order.time_stop_bars else self.time_stop_bars
        
        return order.bars_held >= max_bars
    
    def execute_time_stop(self, order: Order, current_price: float) -> Order:
        """
        Execute time stop - close position at market.
        
        Args:
            order: Order to close
            current_price: Current market price
            
        Returns:
            Updated order
        """
        # Calculate PnL
        if order.side == "BUY":
            pnl = (current_price - order.entry_price) * order.qty
        else:
            pnl = (order.entry_price - current_price) * order.qty
        
        order.realized_pnl += pnl
        order.state = OrderState.CLOSED
        
        order.add_event(
            "time_stop_exit",
            f"Time stop exit after {order.bars_held} bars: {order.qty} @ {current_price:.2f}, PnL: {pnl:.2f}",
            exit_qty=order.qty,
            exit_price=current_price,
            pnl=pnl,
            bars_held=order.bars_held
        )
        
        logger.info(f"Time stop exit on {order.order_id} after {order.bars_held} bars: {order.qty} @ {current_price:.2f}, PnL: {pnl:.2f}")
        
        return order


# ============================================================================
# TradeLifecycleManager - Manages order state transitions
# ============================================================================

class TradeLifecycleManager:
    """Manage order lifecycle state transitions."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize TradeLifecycleManager.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        logger.info("TradeLifecycleManager initialized")
    
    def transition_state(self, order: Order, new_state: OrderState, reason: str = "") -> Order:
        """
        Transition order to new state.
        
        Args:
            order: Order to transition
            new_state: Target state
            reason: Reason for transition
            
        Returns:
            Updated order
        """
        old_state = order.state
        order.state = new_state
        order.updated_at = datetime.now(timezone.utc)
        
        order.add_event(
            "state_transition",
            f"State: {old_state} → {new_state}" + (f" ({reason})" if reason else ""),
            old_state=old_state,
            new_state=new_state
        )
        
        logger.debug(f"Order {order.order_id} state: {old_state} → {new_state}")
        
        return order
    
    def can_transition(self, order: Order, new_state: OrderState) -> bool:
        """
        Check if transition is valid.
        
        Args:
            order: Order to check
            new_state: Target state
            
        Returns:
            True if transition is valid
        """
        # Define valid transitions
        valid_transitions = {
            OrderState.CREATED: [OrderState.SUBMITTED],
            OrderState.SUBMITTED: [OrderState.FILLED],
            OrderState.FILLED: [OrderState.ACTIVE],
            OrderState.ACTIVE: [OrderState.SL_PENDING, OrderState.TP_PENDING, OrderState.CLOSED],
            OrderState.SL_PENDING: [OrderState.CLOSED],
            OrderState.TP_PENDING: [OrderState.CLOSED],
            OrderState.CLOSED: [OrderState.ARCHIVED],
        }
        
        allowed = valid_transitions.get(order.state, [])
        return new_state in allowed


# ============================================================================
# ExecutionEngineV3 - Main orchestration class
# ============================================================================

class ExecutionEngineV3:
    """
    Unified Execution Engine V3.
    
    Responsibilities:
    - Accept OrderIntent from StrategyEngineV2
    - Build orders with OrderBuilder
    - Submit to FillEngine for execution
    - Monitor positions with SL/TP/Trailing/Time managers
    - Update state with TradeLifecycleManager
    - Persist to TradeRecorder
    - Update runtime metrics
    """
    
    def __init__(
        self,
        config: Dict[str, Any],
        market_data_engine: Any = None,
        trade_recorder: Any = None,
        state_store: Any = None
    ):
        """
        Initialize ExecutionEngineV3.
        
        Args:
            config: Configuration dictionary
            market_data_engine: Market data engine for price lookup
            trade_recorder: Trade recorder for persistence
            state_store: State store for runtime state
        """
        self.config = config
        self.mde = market_data_engine
        self.trade_recorder = trade_recorder
        self.state_store = state_store
        
        # Initialize managers
        self.order_builder = OrderBuilder(config)
        self.fill_engine = FillEngine(config, market_data_engine)
        self.sl_manager = StopLossManager(config)
        self.tp_manager = TakeProfitManager(config)
        self.trailing_manager = TrailingStopManager(config)
        self.time_stop_manager = TimeStopManager(config)
        self.lifecycle_manager = TradeLifecycleManager(config)
        
        # Active orders and positions
        self.active_orders: Dict[str, Order] = {}
        self.closed_orders: List[Order] = []
        
        # Runtime metrics
        self.metrics = {
            "total_orders": 0,
            "active_positions": 0,
            "realized_pnl": 0.0,
            "unrealized_pnl": 0.0,
            "total_pnl": 0.0,
        }
        
        logger.info("ExecutionEngineV3 initialized successfully")
    
    def process_signal(self, symbol: str, signal_obj: Any) -> Optional[Order]:
        """
        Process a signal from StrategyEngineV2.
        
        Args:
            symbol: Trading symbol
            signal_obj: OrderIntent from StrategyEngineV2
            
        Returns:
            Order if processed, None otherwise
        """
        try:
            # Extract signal details
            if hasattr(signal_obj, 'signal'):
                action = signal_obj.signal
            elif hasattr(signal_obj, 'action'):
                action = signal_obj.action
            else:
                logger.warning(f"Unknown signal format for {symbol}")
                return None
            
            # Handle EXIT signals
            if action == "EXIT":
                return self._handle_exit(symbol, signal_obj)
            
            # Handle entry signals (BUY/SELL)
            if action in ["BUY", "SELL"]:
                return self._handle_entry(symbol, signal_obj)
            
            return None
            
        except Exception as e:
            logger.error(f"Error processing signal for {symbol}: {e}", exc_info=True)
            return None
    
    def _handle_entry(self, symbol: str, signal_obj: Any) -> Optional[Order]:
        """Handle entry signal (BUY/SELL)."""
        # Extract parameters
        side = signal_obj.signal if hasattr(signal_obj, 'signal') else signal_obj.action
        qty = getattr(signal_obj, 'qty', getattr(signal_obj, 'qty_hint', 1))
        strategy_id = getattr(signal_obj, 'strategy_id', getattr(signal_obj, 'strategy_code', ''))
        
        # Build order
        order = self.order_builder.build_order(
            symbol=symbol,
            qty=qty,
            side=side,
            sl_price=getattr(signal_obj, 'sl_price', None),
            tp_price=getattr(signal_obj, 'tp_price', None),
            time_stop_bars=getattr(signal_obj, 'time_stop_bars', None),
            tag=getattr(signal_obj, 'reason', ''),
            strategy_id=strategy_id
        )
        
        # Submit order
        return self.submit_order(order)
    
    def _handle_exit(self, symbol: str, signal_obj: Any) -> Optional[Order]:
        """Handle exit signal."""
        # Find active position for symbol
        for order_id, order in self.active_orders.items():
            if order.symbol == symbol and order.state == OrderState.ACTIVE:
                # Get current price
                current_price = self._get_current_price(symbol)
                if current_price:
                    # Close position
                    return self._close_position(order, current_price, "manual_exit")
        
        return None
    
    def submit_order(self, order: Order) -> Order:
        """
        Submit an order for execution.
        
        Args:
            order: Order to submit
            
        Returns:
            Updated order
        """
        try:
            # Transition to SUBMITTED
            self.lifecycle_manager.transition_state(order, OrderState.SUBMITTED, "order submitted")
            
            # Get market price
            current_price = self._get_current_price(order.symbol)
            if not current_price:
                logger.error(f"No price data for {order.symbol}, cannot fill order")
                return order
            
            # Fill the order
            order = self.fill_engine.fill_order(order, current_price)
            
            # Transition to ACTIVE
            self.lifecycle_manager.transition_state(order, OrderState.ACTIVE, "position opened")
            
            # Track order
            self.active_orders[order.order_id] = order
            self.metrics["total_orders"] += 1
            self.metrics["active_positions"] = len(self.active_orders)
            
            # Persist to trade recorder
            if self.trade_recorder:
                self._record_order(order, "entry")
            
            # Update runtime metrics
            self._update_runtime_metrics()
            
            logger.info(f"Order submitted and filled: {order.order_id} - {order.side} {order.qty} {order.symbol} @ {order.fill_price:.2f}")
            
            return order
            
        except Exception as e:
            logger.error(f"Error submitting order {order.order_id}: {e}", exc_info=True)
            return order
    
    def update_positions(self, tick_data: Dict[str, float]):
        """
        Update all active positions with new tick data.
        
        Args:
            tick_data: Dictionary of symbol -> current_price
        """
        orders_to_close = []
        
        for order_id, order in list(self.active_orders.items()):
            if order.state != OrderState.ACTIVE:
                continue
            
            # Get current price
            current_price = tick_data.get(order.symbol)
            if not current_price:
                continue
            
            order.current_price = current_price
            
            # Update unrealized PnL
            if order.side == "BUY":
                order.unrealized_pnl = (current_price - order.entry_price) * order.qty
            else:
                order.unrealized_pnl = (order.entry_price - current_price) * order.qty
            
            # Check Take Profit
            if self.tp_manager.check_take_profit(order, current_price):
                order = self.tp_manager.execute_take_profit(order, current_price)
                orders_to_close.append(order)
                continue
            
            # Check Stop Loss
            breached, action = self.sl_manager.check_stop_loss(order, current_price)
            if breached:
                order = self.sl_manager.execute_stop_loss(order, current_price, action)
                if order.state == OrderState.CLOSED:
                    orders_to_close.append(order)
                continue
            
            # Update Trailing Stop
            if order.partial_exit_executed or self.trailing_manager.enable_trailing:
                order = self.trailing_manager.update_trailing_stop(order, current_price)
            
            # Check Time Stop
            if self.time_stop_manager.check_time_stop(order):
                order = self.time_stop_manager.execute_time_stop(order, current_price)
                orders_to_close.append(order)
                continue
        
        # Close completed orders
        for order in orders_to_close:
            self._finalize_order(order)
        
        # Update metrics
        self._update_runtime_metrics()
    
    def on_candle_close(self):
        """
        Called when a new candle closes. Increment bar counters.
        """
        for order_id, order in self.active_orders.items():
            if order.state == OrderState.ACTIVE:
                order.bars_held += 1
    
    def _close_position(self, order: Order, current_price: float, reason: str) -> Order:
        """Close a position."""
        if order.side == "BUY":
            pnl = (current_price - order.entry_price) * order.qty
        else:
            pnl = (order.entry_price - current_price) * order.qty
        
        order.realized_pnl += pnl
        order.state = OrderState.CLOSED
        
        order.add_event(
            "position_closed",
            f"Position closed ({reason}): {order.qty} @ {current_price:.2f}, PnL: {pnl:.2f}",
            exit_qty=order.qty,
            exit_price=current_price,
            pnl=pnl,
            reason=reason
        )
        
        self._finalize_order(order)
        
        return order
    
    def _finalize_order(self, order: Order):
        """Finalize a closed order."""
        # Move from active to closed
        if order.order_id in self.active_orders:
            del self.active_orders[order.order_id]
        
        self.closed_orders.append(order)
        
        # Update metrics
        self.metrics["realized_pnl"] += order.realized_pnl
        self.metrics["active_positions"] = len(self.active_orders)
        
        # Persist
        if self.trade_recorder:
            self._record_order(order, "exit")
        
        logger.info(f"Order finalized: {order.order_id}, realized PnL: {order.realized_pnl:.2f}")
    
    def _get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price from market data engine."""
        if not self.mde:
            return None
        
        try:
            # Try to get last price from MDE
            if hasattr(self.mde, 'get_last_price'):
                return self.mde.get_last_price(symbol)
            elif hasattr(self.mde, 'get_ltp'):
                return self.mde.get_ltp(symbol)
            else:
                logger.warning(f"Cannot get price for {symbol}: MDE has no price method")
                return None
        except Exception as e:
            logger.error(f"Error getting price for {symbol}: {e}")
            return None
    
    def _record_order(self, order: Order, event_type: str):
        """Record order to trade journal."""
        try:
            if not self.trade_recorder:
                return
            
            # Create journal entry
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "order_id": order.order_id,
                "symbol": order.symbol,
                "side": order.side,
                "qty": order.qty,
                "event_type": event_type,
                "state": order.state,
                "fill_price": order.fill_price,
                "entry_price": order.entry_price,
                "current_price": order.current_price,
                "sl_price": order.sl_price,
                "tp_price": order.tp_price,
                "realized_pnl": order.realized_pnl,
                "unrealized_pnl": order.unrealized_pnl,
                "strategy_id": order.strategy_id,
                "tag": order.tag,
            }
            
            # Record using trade recorder if available
            if hasattr(self.trade_recorder, 'record_execution'):
                self.trade_recorder.record_execution(entry)
            
        except Exception as e:
            logger.error(f"Error recording order {order.order_id}: {e}", exc_info=True)
    
    def _update_runtime_metrics(self):
        """Update runtime metrics JSON file."""
        try:
            # Calculate unrealized PnL
            unrealized_pnl = sum(order.unrealized_pnl for order in self.active_orders.values())
            
            self.metrics["unrealized_pnl"] = unrealized_pnl
            self.metrics["total_pnl"] = self.metrics["realized_pnl"] + unrealized_pnl
            self.metrics["active_positions"] = len(self.active_orders)
            
            # Write to file
            metrics_path = Path("artifacts/analytics/runtime_metrics.json")
            metrics_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(metrics_path, "w") as f:
                json.dump(self.metrics, f, indent=2)
            
        except Exception as e:
            logger.error(f"Error updating runtime metrics: {e}", exc_info=True)
    
    def get_positions(self) -> List[Position]:
        """
        Get all active positions.
        
        Returns:
            List of Position objects
        """
        positions = []
        for order in self.active_orders.values():
            if order.state == OrderState.ACTIVE:
                position = Position(
                    symbol=order.symbol,
                    qty=order.qty,
                    side=order.side,
                    entry_price=order.entry_price,
                    current_price=order.current_price or order.entry_price,
                    order_id=order.order_id,
                    strategy_id=order.strategy_id,
                    sl_price=order.sl_price,
                    tp_price=order.tp_price,
                    trailing_sl_active=order.trailing_sl_active,
                    bars_held=order.bars_held,
                    unrealized_pnl=order.unrealized_pnl,
                    highest_price=order.highest_price,
                    lowest_price=order.lowest_price,
                )
                positions.append(position)
        
        return positions
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        Get current execution metrics.
        
        Returns:
            Metrics dictionary
        """
        return self.metrics.copy()
