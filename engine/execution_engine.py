"""
ExecutionEngine v2 - Unified execution layer for paper and live trading.

This module provides:
- Normalized execution interface for both paper and live modes
- Circuit breaker logic for risk management
- Smart fill simulation for paper mode
- Position and journal tracking
- Order routing to paper simulator or live broker
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.market_data_engine_v2 import MarketDataEngineV2
from core.state_store import JournalStateStore, StateStore
from core.trade_throttler import TradeThrottler

logger = logging.getLogger(__name__)


@dataclass
class OrderIntent:
    """
    Normalized order intent structure for execution.
    Extended from strategy_engine_v2.OrderIntent with execution-specific fields.
    """
    symbol: str
    strategy_code: str
    side: str  # 'BUY' / 'SELL'
    qty: int
    order_type: str = "MARKET"  # 'MARKET' / 'LIMIT'
    product: str = "MIS"  # 'MIS' / 'NRML' / 'CNC'
    validity: str = "DAY"  # 'DAY' / 'IOC'
    price: Optional[float] = None
    trigger_price: Optional[float] = None
    tag: Optional[str] = None  # strategy / run identifier
    reason: str = ""
    confidence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "symbol": self.symbol,
            "strategy_code": self.strategy_code,
            "side": self.side,
            "qty": self.qty,
            "order_type": self.order_type,
            "product": self.product,
            "validity": self.validity,
            "price": self.price,
            "trigger_price": self.trigger_price,
            "tag": self.tag,
            "reason": self.reason,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }


@dataclass
class ExecutionResult:
    """
    Normalized execution result returned by ExecutionEngine.
    """
    order_id: Optional[str]
    status: str  # 'PLACED', 'REJECTED', 'FILLED', 'PARTIAL', 'CANCELLED'
    symbol: str
    side: str
    qty: int
    avg_price: Optional[float] = None
    message: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None  # broker raw payload or paper sim details
    timestamp: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "order_id": self.order_id,
            "status": self.status,
            "symbol": self.symbol,
            "side": self.side,
            "qty": self.qty,
            "avg_price": self.avg_price,
            "message": self.message,
            "raw": self.raw,
            "timestamp": self.timestamp,
        }


class SmartFillSimulator:
    """
    Smart fill simulator for paper trading.
    
    Simulates order fills using market data with configurable slippage.
    """

    def __init__(
        self,
        mde: MarketDataEngineV2,
        logger_instance: logging.Logger,
        config: Dict[str, Any]
    ):
        """
        Initialize SmartFillSimulator.
        
        Args:
            mde: MarketDataEngine v2 for price data
            logger_instance: Logger instance
            config: Execution config with slippage settings
        """
        self.mde = mde
        self.logger = logger_instance
        self.config = config
        self.fill_counter = 0
        
        # Extract slippage config
        exec_config = config.get("execution", {})
        self.slippage_bps = exec_config.get("slippage_bps", 5.0)  # 5 basis points default
        self.use_bid_ask = exec_config.get("use_bid_ask_spread", False)
        
    def execute(self, intent: OrderIntent) -> ExecutionResult:
        """
        Simulate a fill for a paper order.
        
        Args:
            intent: Order intent to execute
            
        Returns:
            ExecutionResult with fill details
        """
        symbol = intent.symbol
        side = intent.side.upper()
        qty = intent.qty
        order_type = intent.order_type.upper()
        
        # Generate synthetic order ID
        self.fill_counter += 1
        timestamp = datetime.now(timezone.utc)
        order_id = f"PAPER-{timestamp.strftime('%Y%m%d%H%M%S')}-{self.fill_counter:04d}"
        
        # Get latest price from market data engine
        try:
            # Try to get latest candle from default timeframe
            timeframe = self.config.get("data", {}).get("timeframe", "5m")
            candle = self.mde.get_latest_candle(symbol, timeframe)
            
            if not candle:
                self.logger.warning(
                    "No market data for %s - rejecting paper order",
                    symbol
                )
                return ExecutionResult(
                    order_id=None,
                    status="REJECTED",
                    symbol=symbol,
                    side=side,
                    qty=qty,
                    message=f"No market data available for {symbol}",
                    timestamp=timestamp.isoformat(),
                )
            
            ltp = float(candle.get("close", 0))
            
            if ltp <= 0:
                self.logger.warning(
                    "Invalid LTP (%.2f) for %s - rejecting paper order",
                    ltp, symbol
                )
                return ExecutionResult(
                    order_id=None,
                    status="REJECTED",
                    symbol=symbol,
                    side=side,
                    qty=qty,
                    message=f"Invalid price data for {symbol}",
                    timestamp=timestamp.isoformat(),
                )
            
            # Calculate fill price with slippage
            fill_price = self._apply_slippage(ltp, side, order_type, intent.price)
            
            if order_type == "LIMIT" and not self._is_limit_marketable(
                intent.price, ltp, side
            ):
                # LIMIT order not marketable - treat as rejected/pending
                self.logger.info(
                    "PAPER LIMIT order not marketable: %s %d x %s @ %.2f (LTP=%.2f)",
                    side, qty, symbol, intent.price, ltp
                )
                return ExecutionResult(
                    order_id=order_id,
                    status="REJECTED",
                    symbol=symbol,
                    side=side,
                    qty=qty,
                    avg_price=None,
                    message=f"LIMIT price {intent.price} not marketable (LTP={ltp})",
                    raw={"ltp": ltp, "limit_price": intent.price},
                    timestamp=timestamp.isoformat(),
                )
            
            # Fill the order
            self.logger.info(
                "✅ PAPER FILL: %s %d x %s @ %.2f (LTP=%.2f, slippage=%.1f bps)",
                side, qty, symbol, fill_price, ltp, self.slippage_bps
            )
            
            return ExecutionResult(
                order_id=order_id,
                status="FILLED",
                symbol=symbol,
                side=side,
                qty=qty,
                avg_price=fill_price,
                message="Paper order filled successfully",
                raw={
                    "ltp": ltp,
                    "fill_price": fill_price,
                    "slippage_bps": self.slippage_bps,
                    "candle": candle,
                },
                timestamp=timestamp.isoformat(),
            )
            
        except Exception as exc:
            self.logger.error(
                "Paper fill simulation failed for %s: %s",
                symbol, exc, exc_info=True
            )
            return ExecutionResult(
                order_id=None,
                status="REJECTED",
                symbol=symbol,
                side=side,
                qty=qty,
                message=f"Simulation error: {exc}",
                timestamp=timestamp.isoformat(),
            )
    
    def _apply_slippage(
        self,
        ltp: float,
        side: str,
        order_type: str,
        limit_price: Optional[float]
    ) -> float:
        """
        Apply slippage to LTP based on side and order type.
        
        Args:
            ltp: Last traded price
            side: BUY or SELL
            order_type: MARKET or LIMIT
            limit_price: Limit price if applicable
            
        Returns:
            Fill price with slippage applied
        """
        if order_type == "LIMIT" and limit_price is not None:
            # For LIMIT orders, fill at limit price (if marketable)
            return limit_price
        
        # For MARKET orders, apply slippage
        slippage_multiplier = self.slippage_bps / 10000.0  # Convert bps to decimal
        
        if side == "BUY":
            # Buy at slightly higher price
            return ltp * (1 + slippage_multiplier)
        else:  # SELL
            # Sell at slightly lower price
            return ltp * (1 - slippage_multiplier)
    
    def _is_limit_marketable(
        self,
        limit_price: Optional[float],
        ltp: float,
        side: str
    ) -> bool:
        """
        Check if a LIMIT order is marketable given current LTP.
        
        Args:
            limit_price: Limit price
            ltp: Last traded price
            side: BUY or SELL
            
        Returns:
            True if order would be filled immediately
        """
        if limit_price is None:
            return False
        
        if side == "BUY":
            # BUY limit is marketable if limit >= LTP
            return limit_price >= ltp
        else:  # SELL
            # SELL limit is marketable if limit <= LTP
            return limit_price <= ltp


class ExecutionEngineV2:
    """
    Unified execution engine for paper and live trading.
    
    Features:
    - Mode-aware routing (paper vs live)
    - Circuit breaker logic
    - Position and journal tracking
    - Normalized execution results
    """

    def __init__(
        self,
        mode: str,
        broker: Any,
        state_store: StateStore,
        journal_store: JournalStateStore,
        trade_throttler: Optional[TradeThrottler],
        logger_instance: logging.Logger,
        config: Dict[str, Any],
        mde: Optional[MarketDataEngineV2] = None,
    ):
        """
        Initialize ExecutionEngineV2.
        
        Args:
            mode: 'paper' or 'live'
            broker: KiteBroker instance (or None for paper)
            state_store: StateStore for persistent state
            journal_store: JournalStateStore for orders/fills CSVs
            trade_throttler: TradeThrottler instance
            logger_instance: Logger instance
            config: Full config for risk/execution settings
            mde: MarketDataEngine v2 (required for paper mode)
        """
        self.mode = mode.lower()
        self.broker = broker
        self.state_store = state_store
        self.journal = journal_store
        self.throttler = trade_throttler
        self.logger = logger_instance
        self.config = config
        self.mde = mde
        
        # Initialize smart fill simulator for paper mode
        if self.mode == "paper":
            if mde is None:
                raise ValueError("MarketDataEngine required for paper mode")
            self.smart_fill = SmartFillSimulator(mde, logger_instance, config)
            self.logger.info("ExecutionEngineV2 initialized in PAPER mode")
        else:
            self.smart_fill = None
            if broker is None:
                raise ValueError("Broker required for live mode")
            self.logger.info("ExecutionEngineV2 initialized in LIVE mode")
        
        # Circuit breaker config
        cb_config = config.get("execution", {}).get("circuit_breakers", {})
        self.max_daily_loss_rupees = cb_config.get("max_daily_loss_rupees", 5000.0)
        self.max_daily_drawdown_pct = cb_config.get("max_daily_drawdown_pct", 0.02)
        self.max_trades_per_day = cb_config.get("max_trades_per_day", 100)
        self.max_trades_per_strategy_per_day = cb_config.get(
            "max_trades_per_strategy_per_day", 50
        )
        self.max_loss_streak = cb_config.get("max_loss_streak", 5)
        
    def execute_intent(self, intent: OrderIntent) -> ExecutionResult:
        """
        Main entrypoint: apply checks, route to paper/live execution.
        
        Args:
            intent: Order intent to execute
            
        Returns:
            ExecutionResult with execution details
        """
        # Apply circuit breakers
        if not self.apply_circuit_breakers(intent):
            self.logger.warning(
                "🚫 Circuit breaker BLOCKED order: %s %d x %s",
                intent.side, intent.qty, intent.symbol
            )
            return ExecutionResult(
                order_id=None,
                status="REJECTED",
                symbol=intent.symbol,
                side=intent.side,
                qty=intent.qty,
                message="Circuit breaker blocked execution",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        
        # Route based on mode
        if self.mode == "paper":
            result = self.route_paper(intent)
        else:  # live
            result = self.route_live(intent)
        
        # Update journals if order was placed/filled
        if result.status in ("PLACED", "FILLED", "PARTIAL"):
            self._update_journals(intent, result)
        
        return result
    
    def apply_circuit_breakers(self, intent: OrderIntent) -> bool:
        """
        Check if circuit breakers allow this trade.
        
        Args:
            intent: Order intent to check
            
        Returns:
            False if trading should be blocked, True otherwise
        """
        # Use throttler if available
        if self.throttler:
            can_trade, reason = self.throttler.can_trade(
                symbol=intent.symbol,
                strategy=intent.strategy_code,
                expected_edge=100.0,  # Default edge value
            )
            if not can_trade:
                self.logger.warning(
                    "TradeThrottler blocked order: %s", reason
                )
                return False
        
        # Additional circuit breaker checks from state
        state = self.state_store.load()
        if not state:
            # No state available, allow trade
            return True
        
        # Check total realized PnL
        equity = state.get("equity", {})
        realized_pnl = equity.get("realized_pnl", 0.0)
        
        if realized_pnl < -self.max_daily_loss_rupees:
            self.logger.warning(
                "Circuit breaker: Max daily loss exceeded (%.2f < %.2f)",
                realized_pnl, -self.max_daily_loss_rupees
            )
            return False
        
        # Check drawdown
        paper_capital = equity.get("paper_capital", 100000.0)
        drawdown_pct = abs(realized_pnl) / paper_capital if paper_capital > 0 else 0.0
        
        if drawdown_pct > self.max_daily_drawdown_pct:
            self.logger.warning(
                "Circuit breaker: Max drawdown exceeded (%.2f%% > %.2f%%)",
                drawdown_pct * 100, self.max_daily_drawdown_pct * 100
            )
            return False
        
        # Check if risk halted
        risk_info = state.get("risk", {})
        if risk_info.get("trading_halted", False):
            halt_reason = risk_info.get("halt_reason", "Unknown")
            self.logger.warning(
                "Circuit breaker: Trading halted by risk engine (%s)",
                halt_reason
            )
            return False
        
        return True
    
    def route_paper(self, intent: OrderIntent) -> ExecutionResult:
        """
        Execute via paper smart fill simulator.
        
        Args:
            intent: Order intent to execute
            
        Returns:
            ExecutionResult from paper simulation
        """
        self.logger.info(
            "📝 PAPER ROUTE: %s %d x %s @ %s",
            intent.side, intent.qty, intent.symbol, intent.order_type
        )
        
        if self.smart_fill is None:
            return ExecutionResult(
                order_id=None,
                status="REJECTED",
                symbol=intent.symbol,
                side=intent.side,
                qty=intent.qty,
                message="SmartFillSimulator not initialized",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        
        return self.smart_fill.execute(intent)
    
    def route_live(self, intent: OrderIntent) -> ExecutionResult:
        """
        Execute via broker (Kite) for LIVE mode.
        
        Args:
            intent: Order intent to execute
            
        Returns:
            ExecutionResult from broker
        """
        self.logger.info(
            "🔴 LIVE ROUTE: %s %d x %s @ %s",
            intent.side, intent.qty, intent.symbol, intent.order_type
        )
        
        if self.broker is None:
            return ExecutionResult(
                order_id=None,
                status="REJECTED",
                symbol=intent.symbol,
                side=intent.side,
                qty=intent.qty,
                message="Broker not initialized for live mode",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        
        # Check if dry_run mode
        exec_config = self.config.get("execution", {})
        dry_run = exec_config.get("dry_run", False)
        
        if dry_run:
            self.logger.info(
                "DRY RUN MODE: Would place LIVE order: %s %d x %s @ %s",
                intent.side, intent.qty, intent.symbol, intent.price or "MARKET"
            )
            return ExecutionResult(
                order_id=f"DRY-RUN-{int(time.time())}",
                status="PLACED",
                symbol=intent.symbol,
                side=intent.side,
                qty=intent.qty,
                message="Dry run - order not actually placed",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        
        # Map OrderIntent to broker format
        broker_intent = {
            "symbol": intent.symbol,
            "side": intent.side,
            "qty": intent.qty,
            "order_type": intent.order_type,
            "product": intent.product,
            "validity": intent.validity,
            "price": intent.price,
            "trigger_price": intent.trigger_price,
            "exchange": "NFO",  # Default to NFO, can be overridden in metadata
        }
        
        # Override exchange if specified in metadata
        if "exchange" in intent.metadata:
            broker_intent["exchange"] = intent.metadata["exchange"]
        
        try:
            # Place order via broker
            result = self.broker.place_order(broker_intent)
            
            # Normalize broker response to ExecutionResult
            return ExecutionResult(
                order_id=result.get("order_id"),
                status="PLACED" if result.get("status") == "SUBMITTED" else result.get("status", "REJECTED"),
                symbol=intent.symbol,
                side=intent.side,
                qty=intent.qty,
                message=result.get("message"),
                raw=result,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            
        except Exception as exc:
            self.logger.error(
                "Broker order placement failed: %s",
                exc, exc_info=True
            )
            return ExecutionResult(
                order_id=None,
                status="REJECTED",
                symbol=intent.symbol,
                side=intent.side,
                qty=intent.qty,
                message=f"Broker error: {exc}",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
    
    def on_order_update(self, update: Dict[str, Any]):
        """
        Handle broker order updates (LIVE mode).
        
        Updates positions state and journals.
        
        Args:
            update: Order update dict from broker
        """
        if self.mode != "live":
            self.logger.warning(
                "on_order_update called in %s mode - ignoring",
                self.mode
            )
            return
        
        self.logger.info("Order update received: %s", update)
        
        # Extract key fields from update
        order_id = update.get("order_id")
        status = update.get("status", "").upper()
        
        if status in ("COMPLETE", "FILLED"):
            # Order filled - update positions and journals
            symbol = update.get("tradingsymbol") or update.get("symbol")
            side = update.get("transaction_type", "").upper()
            qty = update.get("filled_quantity") or update.get("quantity", 0)
            avg_price = update.get("average_price", 0.0)
            
            self.logger.info(
                "✅ LIVE FILL: %s %d x %s @ %.2f (order_id=%s)",
                side, qty, symbol, avg_price, order_id
            )
            
            # Update position in state
            self._update_position(symbol, side, qty, avg_price)
            
            # Append to journal
            journal_row = {
                "order_id": order_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "price": avg_price,
                "status": "FILLED",
                "mode": "live",
                "raw": update,
            }
            self.journal.append_orders([journal_row])
    
    def _update_journals(self, intent: OrderIntent, result: ExecutionResult):
        """
        Append order/fill to journal.
        
        Args:
            intent: Original order intent
            result: Execution result
        """
        journal_row = {
            "order_id": result.order_id,
            "timestamp": result.timestamp or datetime.now(timezone.utc).isoformat(),
            "symbol": intent.symbol,
            "strategy": intent.strategy_code,
            "side": intent.side,
            "qty": intent.qty,
            "order_type": intent.order_type,
            "status": result.status,
            "avg_price": result.avg_price,
            "message": result.message,
            "mode": self.mode,
            "reason": intent.reason,
        }
        
        try:
            self.journal.append_orders([journal_row])
        except Exception as exc:
            self.logger.error(
                "Failed to append to journal: %s",
                exc, exc_info=True
            )
    
    def _update_position(
        self,
        symbol: str,
        side: str,
        qty: int,
        avg_price: float
    ):
        """
        Update position state after fill.
        
        Args:
            symbol: Trading symbol
            side: BUY or SELL
            qty: Filled quantity
            avg_price: Average fill price
        """
        state = self.state_store.load()
        if not state:
            self.logger.warning("No state to update position")
            return
        
        positions = state.get("positions", [])
        
        # Find existing position
        position = None
        for pos in positions:
            if pos.get("symbol") == symbol:
                position = pos
                break
        
        # Update or create position
        if position:
            current_qty = position.get("qty", 0)
            if side == "BUY":
                new_qty = current_qty + qty
            else:  # SELL
                new_qty = current_qty - qty
            
            if new_qty == 0:
                # Position closed
                positions.remove(position)
            else:
                position["qty"] = new_qty
                # Update average price (simplified - should use weighted average)
                position["avg_price"] = avg_price
        else:
            # New position
            positions.append({
                "symbol": symbol,
                "qty": qty if side == "BUY" else -qty,
                "avg_price": avg_price,
                "entry_time": datetime.now(timezone.utc).isoformat(),
            })
        
        state["positions"] = positions
        self.state_store.save(state)
