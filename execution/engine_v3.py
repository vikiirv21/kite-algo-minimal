"""
Execution Engine V3 - Minimal Step 1 implementation.

This is a minimal working implementation that provides:
- Simple "market at LTP" order fills
- Basic position tracking and PnL calculation
- State updates via state_store
- Trade journaling via trade_recorder
- No SL/TP, trailing stops, or partial exits (those come in later steps)

This module provides the foundation for future enhancements in subsequent steps.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ============================================================================
# Data Models - Minimal Step 1
# ============================================================================

@dataclass
class ExecutionContext:
    """
    Context information for executing a signal.
    
    Attributes:
        symbol: Trading symbol (e.g., "NIFTY24DECFUT")
        logical_symbol: Logical underlying (e.g., "NIFTY")
        product: Product type ("MIS", "NRML", etc.)
        strategy_id: Strategy identifier
        mode: Trading mode ("paper", "live")
        timestamp: Current timestamp
        timeframe: Timeframe for the signal
        exchange: Exchange ("NFO", "NSE", etc.)
        fixed_qty: Optional fixed quantity override
    """
    symbol: str
    logical_symbol: str
    product: str
    strategy_id: str
    mode: str
    timestamp: datetime
    timeframe: str
    exchange: str = "NFO"
    fixed_qty: Optional[int] = None


@dataclass
class ExecutionResult:
    """
    Result of order execution.
    
    Attributes:
        order_id: Unique order identifier
        symbol: Trading symbol
        side: Order side ("BUY" or "SELL")
        qty: Order quantity
        price: Fill price
        status: Order status ("FILLED", "REJECTED", etc.)
        reason: Reason for status (e.g., "ltp_missing")
        timestamp: Execution timestamp
    """
    order_id: str
    symbol: str
    side: str
    qty: int
    price: float
    status: str
    reason: str = ""
    timestamp: Optional[datetime] = None


# ============================================================================
# ExecutionEngineV3 - Minimal Step 1 Implementation
# ============================================================================

class ExecutionEngineV3:
    """
    Minimal Execution Engine V3 for Step 1.
    
    Provides simple "market at LTP" fills with basic state and journal updates.
    No SL/TP, trailing stops, or partial exits (those come in later steps).
    
    Responsibilities:
    - Process signals (BUY/SELL/HOLD)
    - Fill orders at LTP
    - Update state_store with positions and PnL
    - Log orders to trade_recorder
    """
    
    def __init__(
        self,
        cfg: Dict[str, Any],
        state_store: Any,
        trade_recorder: Any,
        broker_feed: Any,
        logger_instance: Optional[logging.Logger] = None
    ):
        """
        Initialize ExecutionEngineV3.
        
        Args:
            cfg: Execution config section from dev.yaml
            state_store: StateStore instance for state management
            trade_recorder: TradeRecorder instance for journaling
            broker_feed: BrokerFeed instance for LTP lookup
            logger_instance: Optional logger instance
        """
        self.cfg = cfg
        self.state_store = state_store
        self.trade_recorder = trade_recorder
        self.broker_feed = broker_feed
        self.logger = logger_instance or logger
        
        # Get default quantity from config
        self.default_quantity = int(cfg.get("default_quantity", 1))
        
        # Track order sequence for unique IDs
        self._order_sequence = 0
        
        self.logger.info("ExecutionEngineV3 (Step 1) initialized - simple market fills only")
    
    def process_signal(
        self,
        symbol: str,
        signal_obj: Any,
        context: ExecutionContext
    ) -> Optional[ExecutionResult]:
        """
        Process a signal from the strategy engine.
        
        Args:
            symbol: Trading symbol
            signal_obj: Signal object (with .signal or .action attribute)
            context: Execution context
            
        Returns:
            ExecutionResult if order was placed, None if HOLD or error
        """
        # Extract signal action
        if hasattr(signal_obj, 'signal'):
            action = signal_obj.signal
        elif hasattr(signal_obj, 'action'):
            action = signal_obj.action
        else:
            action = str(signal_obj).upper() if signal_obj else "HOLD"
        
        # Normalize action
        action = str(action).upper().strip()
        
        # Log the signal
        self.logger.debug(f"Processing signal for {symbol}: {action}")
        
        # Handle HOLD - just log and return None
        if action == "HOLD" or action not in ("BUY", "SELL", "LONG", "SHORT"):
            self.logger.debug(f"Signal is HOLD for {symbol}, no action taken")
            return None
        
        # Normalize LONG/SHORT to BUY/SELL
        if action == "LONG":
            action = "BUY"
        elif action == "SHORT":
            action = "SELL"
        
        # Determine quantity
        qty = context.fixed_qty if context.fixed_qty else self.default_quantity
        
        # Fill the order
        return self._fill_market_order(symbol, action, qty, context)
    
    def _fill_market_order(
        self,
        symbol: str,
        side: str,
        qty: int,
        context: ExecutionContext
    ) -> ExecutionResult:
        """
        Fill a market order at LTP.
        
        Args:
            symbol: Trading symbol
            side: Order side ("BUY" or "SELL")
            qty: Order quantity
            context: Execution context
            
        Returns:
            ExecutionResult with fill details
        """
        # Get LTP from broker feed
        exchange = context.exchange or "NFO"
        ltp = None
        
        try:
            if hasattr(self.broker_feed, 'get_ltp'):
                ltp = self.broker_feed.get_ltp(symbol, exchange=exchange)
            elif hasattr(self.broker_feed, 'get_last_price'):
                ltp = self.broker_feed.get_last_price(symbol)
        except Exception as e:
            self.logger.warning(f"Error fetching LTP for {symbol}: {e}")
        
        # Handle missing LTP
        if ltp is None or ltp <= 0:
            self.logger.warning(f"LTP missing for {symbol}, rejecting order")
            result = ExecutionResult(
                order_id=self._generate_order_id(),
                symbol=symbol,
                side=side,
                qty=qty,
                price=0.0,
                status="REJECTED",
                reason="ltp_missing",
                timestamp=datetime.now(timezone.utc)
            )
            return result
        
        # Use LTP as fill price (simple market fill)
        fill_price = float(ltp)
        order_id = self._generate_order_id()
        
        self.logger.info(
            f"Filling market order: {side} {qty} {symbol} @ {fill_price:.2f}"
        )
        
        # Update state_store with position and PnL
        try:
            self._update_state_store(symbol, side, qty, fill_price, context)
        except Exception as e:
            self.logger.error(f"Error updating state store: {e}", exc_info=True)
        
        # Log order to trade_recorder
        try:
            self._log_order(
                order_id=order_id,
                symbol=symbol,
                side=side,
                qty=qty,
                price=fill_price,
                context=context
            )
        except Exception as e:
            self.logger.error(f"Error logging order: {e}", exc_info=True)
        
        # Return execution result
        result = ExecutionResult(
            order_id=order_id,
            symbol=symbol,
            side=side,
            qty=qty,
            price=fill_price,
            status="FILLED",
            reason="",
            timestamp=datetime.now(timezone.utc)
        )
        
        return result
    
    def _update_state_store(
        self,
        symbol: str,
        side: str,
        qty: int,
        price: float,
        context: ExecutionContext
    ) -> None:
        """
        Update state_store with position and PnL.
        
        This follows the existing paper engine logic for state management.
        
        Args:
            symbol: Trading symbol
            side: Order side
            qty: Order quantity
            price: Fill price
            context: Execution context
        """
        # Load current state
        state = self.state_store.load_checkpoint() or {}
        
        # Get or create positions dict
        positions = state.setdefault("positions", {})
        
        # Get current position for symbol
        position = positions.get(symbol, {
            "quantity": 0,
            "avg_price": 0.0,
            "realized_pnl": 0.0,
            "unrealized_pnl": 0.0
        })
        
        current_qty = int(position.get("quantity", 0))
        current_avg = float(position.get("avg_price", 0.0))
        realized_pnl = float(position.get("realized_pnl", 0.0))
        
        # Calculate new position based on side
        if side == "BUY":
            new_qty = current_qty + qty
        else:  # SELL
            new_qty = current_qty - qty
        
        # Calculate realized PnL for position changes
        pnl_delta = 0.0
        
        # If closing or reducing position
        if (current_qty > 0 and side == "SELL") or (current_qty < 0 and side == "BUY"):
            close_qty = min(abs(current_qty), qty)
            if current_qty > 0:  # Closing long
                pnl_delta = (price - current_avg) * close_qty
            else:  # Closing short
                pnl_delta = (current_avg - price) * close_qty
            realized_pnl += pnl_delta
        
        # Calculate new average price
        if new_qty == 0:
            new_avg = 0.0
        elif (current_qty >= 0 and side == "BUY") or (current_qty <= 0 and side == "SELL"):
            # Adding to position
            total_cost = (current_avg * abs(current_qty)) + (price * qty)
            new_avg = total_cost / abs(new_qty) if new_qty != 0 else 0.0
        else:
            # Position reversed, use new price
            new_avg = price
        
        # Update position
        position["quantity"] = new_qty
        position["avg_price"] = new_avg
        position["realized_pnl"] = realized_pnl
        position["unrealized_pnl"] = 0.0  # Will be calculated when price updates
        
        positions[symbol] = position
        
        # Save state
        self.state_store.save_checkpoint(state)
        
        self.logger.debug(
            f"State updated for {symbol}: qty={new_qty}, avg={new_avg:.2f}, "
            f"realized_pnl={realized_pnl:.2f}"
        )
    
    def _log_order(
        self,
        order_id: str,
        symbol: str,
        side: str,
        qty: int,
        price: float,
        context: ExecutionContext
    ) -> None:
        """
        Log order to trade_recorder.
        
        Uses the same schema as existing TradeRecorder to maintain compatibility.
        
        Args:
            order_id: Order ID
            symbol: Trading symbol
            side: Order side
            qty: Order quantity
            price: Fill price
            context: Execution context
        """
        timestamp = context.timestamp or datetime.now(timezone.utc)
        
        # Build order record matching existing schema
        order_record = {
            "timestamp": timestamp.isoformat(),
            "order_id": order_id,
            "symbol": symbol,
            "tradingsymbol": symbol,
            "side": side,
            "transaction_type": side,
            "quantity": qty,
            "filled_quantity": qty,
            "price": price,
            "average_price": price,
            "status": "FILLED",
            "exchange": context.exchange,
            "product": context.product,
            "variety": "REGULAR",
            "strategy": context.strategy_id,
            "tf": context.timeframe,
            "mode": context.mode,
            "underlying": context.logical_symbol,
            "tag": context.strategy_id,
        }
        
        # Log using trade_recorder.log_order if available
        if hasattr(self.trade_recorder, 'log_order'):
            try:
                self.trade_recorder.log_order(
                    timestamp=timestamp,
                    symbol=symbol,
                    side=side,
                    quantity=qty,
                    price=price,
                    status="FILLED",
                    strategy=context.strategy_id,
                    tf=context.timeframe,
                    mode=context.mode,
                    underlying=context.logical_symbol
                )
            except Exception as e:
                self.logger.warning(f"log_order method failed: {e}")
        
        # Fallback: record_order method (if available)
        elif hasattr(self.trade_recorder, 'record_order'):
            try:
                self.trade_recorder.record_order(
                    symbol=symbol,
                    side=side,
                    quantity=qty,
                    price=price,
                    status="FILLED",
                    tf=context.timeframe,
                    profile="",
                    strategy=context.strategy_id,
                    parent_signal_timestamp="",
                    extra=order_record
                )
            except Exception as e:
                self.logger.warning(f"record_order method failed: {e}")
        
        self.logger.debug(f"Order logged: {order_id}")
    
    def _generate_order_id(self) -> str:
        """Generate a unique order ID."""
        self._order_sequence += 1
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        return f"V3-{timestamp}-{self._order_sequence:04d}"
    
    def update_positions(self, tick_prices: Dict[str, float]) -> None:
        """
        Update unrealized PnL for open positions based on current prices.
        
        Args:
            tick_prices: Dict of symbol -> current_price
        """
        try:
            state = self.state_store.load_checkpoint() or {}
            positions = state.get("positions", {})
            
            updated = False
            for symbol, position in positions.items():
                qty = int(position.get("quantity", 0))
                if qty == 0:
                    continue
                
                current_price = tick_prices.get(symbol)
                if current_price is None or current_price <= 0:
                    continue
                
                avg_price = float(position.get("avg_price", 0.0))
                if avg_price <= 0:
                    continue
                
                # Calculate unrealized PnL
                if qty > 0:  # Long position
                    unrealized = (current_price - avg_price) * qty
                else:  # Short position
                    unrealized = (avg_price - current_price) * abs(qty)
                
                position["unrealized_pnl"] = unrealized
                updated = True
            
            if updated:
                self.state_store.save_checkpoint(state)
                
        except Exception as e:
            self.logger.error(f"Error updating positions: {e}", exc_info=True)
