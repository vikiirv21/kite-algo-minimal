"""
Live Trading Engine

Parallel to PaperEngine but places REAL orders via Kite.

Shares:
- StrategyEngine v2
- RiskEngine
- MarketDataEngine
- StateStore concepts

Diverges at:
- Execution layer (real Kite orders vs simulated)
- Fill handling (WebSocket order updates vs immediate fills)
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, time as dt_time, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from kiteconnect import KiteConnect

from broker.kite_bridge import KiteBroker
from core.config import AppConfig
from core.market_data_engine import MarketDataEngine
from core.market_session import is_market_open
from core.modes import TradingMode
from core.risk_engine import RiskAction, RiskDecision, RiskEngine
from core.state_store import JournalStateStore, StateStore
from core.strategy_engine_v2 import StrategyEngineV2
from core.event_logging import log_event
from core.portfolio_engine import PortfolioEngine, PortfolioConfig

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = BASE_DIR / "artifacts"

# IST market hours (approx) - 9:15 AM to 3:30 PM IST
MARKET_OPEN_TIME = dt_time(9, 15)
MARKET_CLOSE_TIME = dt_time(15, 30)


class LiveEngine:
    """
    LIVE trading engine that places real orders via Kite.
    
    Key features:
    - WebSocket-based tick processing
    - Real order placement through KiteBroker
    - Shared strategy and risk engines with paper mode
    - Safety guardrails (login checks, market hours, risk engine)
    """
    
    def __init__(
        self,
        cfg: AppConfig,
        broker: KiteBroker,
        market_data_engine: MarketDataEngine,
        strategy_engine: StrategyEngineV2,
        risk_engine: RiskEngine,
        state_store: StateStore,
        journal_store: Optional[JournalStateStore] = None,
        *,
        artifacts_dir: Optional[Path] = None,
        execution_engine_v2: Any = None,
    ):
        """
        Initialize LiveEngine.
        
        Args:
            cfg: Application config
            broker: KiteBroker instance
            market_data_engine: Market data engine
            strategy_engine: Strategy engine v2
            risk_engine: Risk engine
            state_store: State checkpoint store
            journal_store: Journal store for orders/fills
            artifacts_dir: Artifacts directory override
            execution_engine_v2: Optional ExecutionEngine v2 instance
        """
        self.cfg = cfg
        self.broker = broker
        self.market_data_engine = market_data_engine
        self.strategy_engine = strategy_engine
        self.risk_engine = risk_engine
        self.state_store = state_store
        
        self.artifacts_dir = Path(artifacts_dir).resolve() if artifacts_dir else ARTIFACTS_DIR
        
        if journal_store is None:
            journal_store = JournalStateStore(mode="live", artifacts_dir=self.artifacts_dir)
        self.journal = journal_store
        
        self.running = True
        self.universe: List[str] = []
        self.instrument_tokens: Dict[str, int] = {}
        
        # Pending orders tracking
        self.pending_orders: Dict[str, Dict[str, Any]] = {}  # order_id -> order_info
        
        # Last known prices for each symbol
        self.last_prices: Dict[str, float] = {}
        
        # Initialize ExecutionEngine v2 (optional)
        self.execution_engine_v2 = execution_engine_v2
        if self.execution_engine_v2 is None:
            exec_config = self.cfg.raw.get("execution", {})
            use_exec_v2 = exec_config.get("use_execution_engine_v2", False)
            if use_exec_v2:
                try:
                    from engine.execution_bridge import create_execution_engine_v2
                    from core.trade_throttler import TradeThrottler, build_throttler_config
                    
                    logger.info("Initializing ExecutionEngine v2 for live mode")
                    
                    # Create throttler if not exists
                    throttler_config = build_throttler_config(cfg.raw.get("trading", {}).get("trade_throttler"))
                    throttler = TradeThrottler(config=throttler_config, capital=100000.0)
                    
                    self.execution_engine_v2 = create_execution_engine_v2(
                        mode="live",
                        broker=self.broker,
                        state_store=self.state_store,
                        journal_store=self.journal,
                        trade_throttler=throttler,
                        config=self.cfg.raw,
                        mde=None,  # Live mode doesn't need MDE for fills
                    )
                except Exception as exc:
                    logger.warning("Failed to initialize ExecutionEngine v2: %s", exc)
                    self.execution_engine_v2 = None
        
        # Initialize Trade Guardian v1 (optional, for legacy path when ExecutionEngine v2 not used)
        self.guardian = None
        try:
            from core.trade_guardian import TradeGuardian
            self.guardian = TradeGuardian(self.cfg.raw, self.state_store, logger)
        except Exception as exc:
            logger.warning("Failed to initialize TradeGuardian: %s", exc)
        
        # Initialize PortfolioEngine v1 (optional)
        self.portfolio_engine = None
        portfolio_config_raw = self.cfg.raw.get("portfolio")
        if portfolio_config_raw:
            try:
                logger.info("Initializing PortfolioEngine v1 for live mode")
                portfolio_config = PortfolioConfig.from_dict(portfolio_config_raw)
                self.portfolio_engine = PortfolioEngine(
                    portfolio_config=portfolio_config,
                    state_store=self.state_store,
                    journal_store=self.journal,
                    logger_instance=logger,
                    mde=None,  # Live mode can use MDE if available
                )
                logger.info(
                    "PortfolioEngine v1 initialized for LIVE: mode=%s, max_exposure_pct=%.2f",
                    portfolio_config.position_sizing_mode,
                    portfolio_config.max_exposure_pct,
                )
            except Exception as exc:
                logger.warning("Failed to initialize PortfolioEngine v1: %s", exc, exc_info=True)
                self.portfolio_engine = None
        
        logger.info("✅ LiveEngine initialized (mode=LIVE)")
        logger.warning("⚠️ LIVE TRADING MODE ACTIVE - REAL ORDERS WILL BE PLACED ⚠️")
    
    def start(self) -> None:
        """
        Start the live trading engine.
        
        - Validates login
        - Subscribes to WebSocket ticks
        - Runs main event loop
        """
        # Ensure logged in
        if not self.broker.ensure_logged_in():
            logger.error("❌ Cannot start LiveEngine: not logged in to Kite")
            self.running = False
            return
        
        # Load universe from config
        trading = getattr(self.cfg, "trading", {}) or {}
        logical_universe = trading.get("logical_universe") or trading.get("fno_universe") or []
        if isinstance(logical_universe, str):
            logical_universe = [logical_universe]
        self.universe = [str(s).strip().upper() for s in logical_universe if s]
        
        if not self.universe:
            logger.error("❌ No symbols configured for LIVE trading - cannot start")
            self.running = False
            return
        
        logger.info("📊 LIVE universe: %s", self.universe)
        
        # Resolve instrument tokens for WebSocket subscription
        self._resolve_instrument_tokens()
        
        if not self.instrument_tokens:
            logger.error("❌ Could not resolve any instrument tokens - cannot subscribe to ticks")
            self.running = False
            return
        
        # Subscribe to WebSocket ticks
        tokens = list(self.instrument_tokens.values())
        if not self.broker.subscribe_ticks(tokens, self.on_tick):
            logger.error("❌ Failed to subscribe to WebSocket ticks")
            self.running = False
            return
        
        logger.info("✅ LiveEngine started - processing ticks")
        
        # Main event loop (keeps engine alive)
        self._run_event_loop()
    
    def _run_event_loop(self) -> None:
        """
        Main event loop - keeps engine alive and performs periodic checks.
        """
        snapshot_interval = 60  # seconds
        last_snapshot = time.time()
        
        while self.running:
            try:
                # Check if market is open
                if not is_market_open():
                    logger.info("Market closed - engine sleeping")
                    time.sleep(60)
                    continue
                
                # Periodic snapshot
                now = time.time()
                if now - last_snapshot >= snapshot_interval:
                    self._snapshot_state("periodic")
                    last_snapshot = now
                
                # Sleep to avoid tight loop
                time.sleep(5)
                
            except KeyboardInterrupt:
                logger.info("Keyboard interrupt - stopping LiveEngine")
                self.running = False
                break
            except Exception as exc:
                logger.error("Error in event loop: %s", exc, exc_info=True)
                time.sleep(10)
    
    def on_tick(self, tick: Dict[str, Any]) -> None:
        """
        Handle incoming tick from WebSocket.
        
        - Updates market data engine
        - Runs strategy engine
        - Processes signals through risk engine
        - Places orders via broker
        
        Args:
            tick: Normalized tick dict from KiteBroker
        """
        try:
            symbol = tick.get("tradingsymbol")
            price = tick.get("last_price")
            
            if not symbol or not price:
                return
            
            # Update last known price
            self.last_prices[symbol] = float(price)
            
            # Update market data engine (if needed for strategy)
            # This would typically update candle windows
            # For now, strategies will use the tick price directly
            
            # Run strategy engine for this symbol
            # StrategyEngineV2.run() expects a list of symbols
            # It will internally fetch data and generate signals
            signals = self.strategy_engine.run([symbol])
            
            # Process each signal
            for signal in signals:
                self._process_signal(signal, price)
                
        except Exception as exc:
            logger.error("Error processing tick for %s: %s", tick.get("tradingsymbol"), exc)
    
    def _process_signal(self, signal: Dict[str, Any], current_price: float) -> None:
        """
        Process a strategy signal through risk engine and place order if approved.
        
        Args:
            signal: Signal dict from strategy engine
            current_price: Current market price
        """
        symbol = signal.get("symbol")
        action = signal.get("action", "HOLD").upper()
        
        if action == "HOLD":
            return
        
        # Check if we're still logged in
        if not self.broker.ensure_logged_in():
            logger.error("❌ Lost Kite session - cannot place order")
            self.running = False
            return
        
        # Check market hours
        if not self._is_market_hours():
            logger.warning("Market closed - cannot place order for %s", symbol)
            return
        
        # Build order intent
        order_intent = self._build_order_intent(signal, current_price)
        
        # Pass through risk engine
        portfolio_state = self._get_portfolio_state()
        strategy_snapshot = self._get_strategy_snapshot()
        
        risk_decision = self.risk_engine.check_order(
            order_intent,
            portfolio_state,
            strategy_snapshot,
        )
        
        # Handle risk decision
        if risk_decision.action == RiskAction.BLOCK:
            logger.info(
                "❌ Risk engine BLOCKED order: %s %s - %s",
                action, symbol, risk_decision.reason
            )
            log_event(
                "RISK_BLOCK",
                risk_decision.reason,
                symbol=symbol,
                extra=order_intent,
            )
            return
        elif risk_decision.action == RiskAction.REDUCE:
            logger.info(
                "⚠️ Risk engine REDUCED order: %s %s - %s (qty: %s -> %s)",
                action, symbol, risk_decision.reason,
                order_intent.get("qty"), risk_decision.adjusted_qty
            )
            order_intent["qty"] = risk_decision.adjusted_qty
        elif risk_decision.action == RiskAction.HALT_SESSION:
            logger.warning(
                "🛑 Risk engine HALT_SESSION: %s - stopping engine",
                risk_decision.reason
            )
            log_event(
                "HALT_SESSION",
                risk_decision.reason,
                symbol=symbol,
                level=logging.WARNING,
            )
            self.running = False
            return
        
        # Exits always allowed (but still logged)
        if action in ("EXIT", "CLOSE"):
            logger.info("✅ EXIT signal approved for %s", symbol)
        
        # Place the order
        self.place_order(order_intent)
    
    def place_order(self, intent: Dict[str, Any]) -> None:
        """
        Place a LIVE order via broker.
        
        Args:
            intent: Order intent dict
        """
        try:
            # Use ExecutionEngine v2 if available
            if self.execution_engine_v2 is not None:
                try:
                    from engine.execution_engine import OrderIntent
                    # Convert to ExecutionEngine v2 OrderIntent
                    exec_intent = OrderIntent(
                        symbol=intent.get("symbol", ""),
                        strategy_code=intent.get("strategy", "unknown"),
                        side=intent.get("side", "BUY"),
                        qty=intent.get("qty", 0),
                        order_type=intent.get("order_type", "MARKET"),
                        product=intent.get("product", "MIS"),
                        validity=intent.get("validity", "DAY"),
                        price=intent.get("price"),
                        trigger_price=intent.get("trigger_price"),
                        tag=intent.get("tag"),
                        reason=intent.get("reason", ""),
                    )
                    
                    # Execute via ExecutionEngine v2
                    result = self.execution_engine_v2.execute_intent(exec_intent)
                    
                    order_id = result.order_id
                    status = result.status
                    message = result.message or ""
                    
                    if order_id:
                        # Track pending order
                        self.pending_orders[order_id] = {
                            "intent": intent,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "status": status,
                        }
                        logger.info(
                            "✅ Order placed via ExecutionEngine v2: ID=%s status=%s symbol=%s side=%s qty=%s",
                            order_id, status, intent.get("symbol"), intent.get("side"), intent.get("qty")
                        )
                        
                        # Journal handled by ExecutionEngine v2
                    else:
                        logger.error(
                            "❌ Order placement failed via ExecutionEngine v2: %s (symbol=%s side=%s)",
                            message, intent.get("symbol"), intent.get("side")
                        )
                        log_event(
                            "ORDER_ERROR",
                            f"Order placement failed: {message}",
                            symbol=intent.get("symbol"),
                            extra=intent,
                            level=logging.ERROR,
                        )
                    return
                except Exception as exc:
                    logger.warning("ExecutionEngine v2 failed, falling back to legacy: %s", exc)
                    # Guardian check for legacy fallback path
                    if self.guardian:
                        from engine.execution_engine import OrderIntent
                        exec_intent = OrderIntent(
                            symbol=intent.get("symbol", ""),
                            strategy_code=intent.get("strategy", "unknown"),
                            side=intent.get("side", "BUY"),
                            qty=intent.get("qty", 0),
                            order_type=intent.get("order_type", "MARKET"),
                            product=intent.get("product", "MIS"),
                            price=intent.get("price"),
                        )
                        guardian_decision = self.guardian.validate_pre_trade(exec_intent, None)
                        if not guardian_decision.allow:
                            logger.warning(
                                "[guardian-block] %s - skipping order", guardian_decision.reason
                            )
                            return
                    # Fall through to legacy path
            
            # Legacy execution path - check guardian before placing order
            if self.guardian:
                from engine.execution_engine import OrderIntent
                exec_intent = OrderIntent(
                    symbol=intent.get("symbol", ""),
                    strategy_code=intent.get("strategy", "unknown"),
                    side=intent.get("side", "BUY"),
                    qty=intent.get("qty", 0),
                    order_type=intent.get("order_type", "MARKET"),
                    product=intent.get("product", "MIS"),
                    price=intent.get("price"),
                )
                guardian_decision = self.guardian.validate_pre_trade(exec_intent, None)
                if not guardian_decision.allow:
                    logger.warning(
                        "[guardian-block] %s - skipping order", guardian_decision.reason
                    )
                    log_event(
                        "GUARDIAN_BLOCK",
                        f"Trade guardian blocked order: {guardian_decision.reason}",
                        symbol=intent.get("symbol"),
                        extra=intent,
                        level=logging.WARNING,
                    )
                    return
            
            result = self.broker.place_order(intent)
            
            order_id = result.get("order_id")
            status = result.get("status")
            message = result.get("message", "")
            
            if order_id:
                # Track pending order
                self.pending_orders[order_id] = {
                    "intent": intent,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "status": status,
                }
                logger.info(
                    "✅ Order placed: ID=%s status=%s symbol=%s side=%s qty=%s",
                    order_id, status, intent.get("symbol"), intent.get("side"), intent.get("qty")
                )
                
                # Journal the order
                self._journal_order(order_id, intent, status)
            else:
                logger.error(
                    "❌ Order placement failed: %s (symbol=%s side=%s)",
                    message, intent.get("symbol"), intent.get("side")
                )
                log_event(
                    "ORDER_ERROR",
                    f"Order placement failed: {message}",
                    symbol=intent.get("symbol"),
                    extra=intent,
                    level=logging.ERROR,
                )
                
        except Exception as exc:
            logger.error("❌ Exception placing order: %s", exc, exc_info=True)
            log_event(
                "ORDER_ERROR",
                f"Exception placing order: {exc}",
                symbol=intent.get("symbol"),
                extra=intent,
                level=logging.ERROR,
            )
    
    def handle_order_update(self, order_update: Dict[str, Any]) -> None:
        """
        Handle order update from WebSocket or polling.
        
        Updates:
        - Pending orders tracking
        - Position state
        - PnL calculations
        - Journal/checkpoint
        
        Args:
            order_update: Order update dict from Kite
        """
        order_id = order_update.get("order_id")
        status = order_update.get("status", "").upper()
        
        if not order_id:
            return
        
        logger.info(
            "📝 Order update: ID=%s status=%s symbol=%s",
            order_id, status, order_update.get("tradingsymbol")
        )
        
        # Update pending orders
        if order_id in self.pending_orders:
            self.pending_orders[order_id]["status"] = status
            
            # If filled or rejected, remove from pending
            if status in ("COMPLETE", "REJECTED", "CANCELLED"):
                self.pending_orders.pop(order_id, None)
        
        # Journal the update
        self._journal_order_update(order_update)
        
        # Update state checkpoint
        self._snapshot_state("order_update")
    
    def _build_order_intent(self, signal: Dict[str, Any], current_price: float) -> Dict[str, Any]:
        """
        Build order intent from strategy signal.
        
        Args:
            signal: Signal dict from strategy
            current_price: Current market price
            
        Returns:
            Order intent dict for broker
        """
        symbol = signal.get("symbol")
        action = signal.get("action", "HOLD").upper()
        qty = signal.get("qty", 1)
        
        # Map action to side
        if action in ("BUY", "LONG"):
            side = "BUY"
        elif action in ("SELL", "SHORT"):
            side = "SELL"
        elif action in ("EXIT", "CLOSE"):
            # Determine exit side based on current position
            # For now, default to SELL (close long)
            side = "SELL"
        else:
            side = "BUY"
        
        # Default to MIS (intraday) product
        product = signal.get("product", "MIS")
        order_type = signal.get("order_type", "MARKET")
        
        return {
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "price": current_price if order_type == "LIMIT" else None,
            "order_type": order_type,
            "product": product,
            "validity": "DAY",
            "exchange": signal.get("exchange", "NFO"),
            "strategy": signal.get("strategy", "unknown"),
            "reason": signal.get("reason", ""),
        }
    
    def _resolve_instrument_tokens(self) -> None:
        """
        Resolve instrument tokens for WebSocket subscription.
        
        Uses Kite instruments() API to map trading symbols to tokens.
        """
        if not self.broker.kite:
            logger.error("No Kite client - cannot resolve instrument tokens")
            return
        
        try:
            instruments = self.broker.kite.instruments("NFO")
            
            for symbol in self.universe:
                # Find matching instrument
                for inst in instruments:
                    if inst.get("tradingsymbol") == symbol:
                        token = inst.get("instrument_token")
                        if token:
                            self.instrument_tokens[symbol] = token
                            logger.info("✅ Resolved %s -> token %s", symbol, token)
                        break
                        
            logger.info("Resolved %d/%d instrument tokens", len(self.instrument_tokens), len(self.universe))
            
        except Exception as exc:
            logger.error("Failed to resolve instrument tokens: %s", exc)
    
    def _is_market_hours(self) -> bool:
        """
        Check if current time is within market hours (IST).
        
        Returns:
            True if within market hours, False otherwise
        """
        # Use the shared market session checker
        return is_market_open()
    
    def _get_portfolio_state(self) -> Dict[str, Any]:
        """
        Get current portfolio state for risk engine.
        
        Returns:
            Portfolio state dict
        """
        # Load latest checkpoint
        state = self.state_store.load_checkpoint() or {}
        
        # Get positions from broker
        positions = self.broker.fetch_positions()
        
        # Compute portfolio metrics
        total_pnl = sum(p.get("pnl", 0.0) for p in positions)
        total_notional = sum(abs(p.get("quantity", 0) * p.get("last_price", 0)) for p in positions)
        
        return {
            "equity": state.get("equity", {}),
            "positions": positions,
            "total_pnl": total_pnl,
            "total_notional": total_notional,
            "free_notional": 0.0,  # Would need margin data
        }
    
    def _get_strategy_snapshot(self) -> Dict[str, Any]:
        """
        Get current strategy state snapshot for risk engine.
        
        Returns:
            Strategy state dict
        """
        state = self.state_store.load_checkpoint() or {}
        return state.get("strategies", {})
    
    def _journal_order(self, order_id: str, intent: Dict[str, Any], status: str) -> None:
        """
        Journal an order to the orders.csv file.
        
        Args:
            order_id: Kite order ID
            intent: Order intent
            status: Order status
        """
        try:
            order_record = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "order_id": order_id,
                "symbol": intent.get("symbol"),
                "side": intent.get("side"),
                "quantity": intent.get("qty"),
                "price": intent.get("price", ""),
                "order_type": intent.get("order_type", "MARKET"),
                "product": intent.get("product", "MIS"),
                "status": status,
                "exchange": intent.get("exchange", "NFO"),
                "strategy": intent.get("strategy", ""),
                "reason": intent.get("reason", ""),
            }
            
            self.journal.append_orders([order_record])
            
        except Exception as exc:
            logger.error("Failed to journal order: %s", exc)
    
    def _journal_order_update(self, order_update: Dict[str, Any]) -> None:
        """
        Journal an order update/fill.
        
        Args:
            order_update: Order update dict from Kite
        """
        try:
            # Normalize the order update
            normalized = JournalStateStore.normalize_order(order_update)
            self.journal.append_orders([normalized])
            
        except Exception as exc:
            logger.error("Failed to journal order update: %s", exc)
    
    def _snapshot_state(self, reason: str = "") -> None:
        """
        Save a checkpoint of current state.
        
        Args:
            reason: Reason for snapshot (for logging)
        """
        try:
            # Fetch current positions
            positions = self.broker.fetch_positions()
            
            # Build state payload
            state = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "mode": "LIVE",
                "positions": positions,
                "pending_orders": list(self.pending_orders.values()),
                "last_prices": self.last_prices,
                "reason": reason,
            }
            
            # Save checkpoint
            self.state_store.save_checkpoint(state)
            
            logger.info(
                "💾 State snapshot saved (reason=%s, positions=%d, pending=%d)",
                reason, len(positions), len(self.pending_orders)
            )
            
        except Exception as exc:
            logger.error("Failed to save state snapshot: %s", exc)
    
    def stop(self) -> None:
        """
        Stop the live engine gracefully.
        """
        logger.info("Stopping LiveEngine...")
        self.running = False
        
        # Stop WebSocket
        if self.broker.ticker:
            self.broker.stop_ticker()
        
        # Final snapshot
        self._snapshot_state("engine_stop")
        
        logger.info("✅ LiveEngine stopped")
