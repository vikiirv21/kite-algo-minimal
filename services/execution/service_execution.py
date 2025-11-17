"""
Execution Service - Architecture v3 Phase 4

Executes approved orders with broker APIs.

Topics:
- Publishes: exec.order_submitted.*, exec.fill.*
- Subscribes: risk.order_approved.*, risk.order_rejected.*
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Protocol, Any, Dict

# Initialize logger early
logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from services.common.event_bus import EventBus, Event

from analytics.trade_recorder import TradeRecorder
from broker.paper_broker import PaperBroker

# Lazy imports for live trading dependencies (may not be available in all environments)
KiteBroker = None
LiveBroker = None

try:
    from broker.kite_bridge import KiteBroker
except ImportError:
    logger.warning("KiteBroker not available (kiteconnect module missing)")

try:
    from broker.live_broker import LiveBroker
except ImportError:
    logger.warning("LiveBroker not available")


@dataclass
class ServiceConfig:
    """Configuration for Execution service."""
    name: str = "execution"
    enabled: bool = True
    mode: str = "paper"  # "paper" or "live"
    slippage_bps: float = 5.0  # Paper mode slippage in basis points


class ExecutionBackend(Protocol):
    """Protocol defining the interface for execution backends."""
    
    def submit_order(self, *, symbol: str, side: str, quantity: int, price: float, **kwargs) -> Dict[str, Any]:
        """
        Submit an order to the backend.
        
        Args:
            symbol: Trading symbol
            side: "BUY" or "SELL"
            quantity: Order quantity
            price: Order price
            **kwargs: Additional order parameters
            
        Returns:
            Dict with order_id, symbol, side, quantity, price, status, and optionally fill_price
        """
        ...
    
    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Cancel an order by ID."""
        ...
    
    def sync_open_orders(self) -> list[Dict[str, Any]]:
        """Synchronize and return open orders."""
        ...


class PaperBackend:
    """Paper trading backend wrapping PaperBroker."""
    
    def __init__(self, cfg: Dict[str, Any]):
        """
        Initialize paper backend.
        
        Args:
            cfg: Configuration dict with optional slippage_bps
        """
        self.broker = PaperBroker()
        self.slippage_bps = cfg.get("slippage_bps", 5.0)
        self.order_counter = 0
        logger.info("PaperBackend initialized with slippage_bps=%.2f", self.slippage_bps)
    
    def submit_order(self, *, symbol: str, side: str, quantity: int, price: float, **kwargs) -> Dict[str, Any]:
        """
        Submit a paper order with simulated immediate fill.
        
        Args:
            symbol: Trading symbol
            side: "BUY" or "SELL"
            quantity: Order quantity
            price: Order price
            **kwargs: Additional parameters (ignored)
            
        Returns:
            Dict with order details including synthetic order_id and FILLED status
        """
        try:
            # Generate synthetic order ID
            self.order_counter += 1
            today = datetime.utcnow().strftime("%Y%m%d")
            order_id = f"paper-{today}-{self.order_counter:04d}"
            
            # Apply slippage
            slippage_multiplier = 1.0 + (self.slippage_bps / 10000.0)
            if side.upper() == "BUY":
                fill_price = price * slippage_multiplier
            else:  # SELL
                fill_price = price / slippage_multiplier
            
            # Place order via paper broker
            order = self.broker.place_order(symbol=symbol, side=side, quantity=quantity, price=fill_price)
            
            logger.info(
                "Paper order filled: order_id=%s symbol=%s side=%s qty=%d price=%.2f fill_price=%.2f",
                order_id, symbol, side, quantity, price, fill_price
            )
            
            return {
                "order_id": order_id,
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "price": price,
                "fill_price": fill_price,
                "status": "FILLED",
            }
        except Exception as e:
            logger.error("Paper order failed: %s", e, exc_info=True)
            return {
                "order_id": f"paper-error-{uuid.uuid4().hex[:8]}",
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "price": price,
                "status": "ERROR",
                "error": str(e),
            }
    
    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Cancel not implemented for paper trading."""
        return {"order_id": order_id, "status": "NOT_SUPPORTED"}
    
    def sync_open_orders(self) -> list[Dict[str, Any]]:
        """No open orders in paper mode (immediate fills)."""
        return []


class LiveBackend:
    """Live trading backend wrapping KiteBroker/LiveBroker."""
    
    def __init__(self, cfg: Dict[str, Any]):
        """
        Initialize live backend.
        
        Args:
            cfg: Configuration dict with broker settings
        """
        if KiteBroker is None and LiveBroker is None:
            raise RuntimeError(
                "Live trading dependencies not available. "
                "Install kiteconnect package for live trading."
            )
        
        self.cfg = cfg
        
        # Try to initialize broker - prefer LiveBroker if available, fallback to KiteBroker
        self.broker = None
        try:
            # Attempt to use LiveBroker if it's been configured
            # For now, we'll use KiteBroker as the primary wrapper
            if KiteBroker is not None:
                self.broker = KiteBroker(config=cfg)
                if hasattr(self.broker, 'ensure_logged_in'):
                    self.broker.ensure_logged_in()
                logger.info("LiveBackend initialized with KiteBroker")
            else:
                raise RuntimeError("KiteBroker not available")
        except Exception as e:
            logger.error("Failed to initialize live broker: %s", e)
            raise RuntimeError(f"Cannot initialize live broker: {e}") from e
    
    def submit_order(self, *, symbol: str, side: str, quantity: int, price: float, **kwargs) -> Dict[str, Any]:
        """
        Submit a live order via Kite API.
        
        Args:
            symbol: Trading symbol
            side: "BUY" or "SELL"
            quantity: Order quantity
            price: Order price
            **kwargs: Additional parameters (profile, strategy, etc.)
            
        Returns:
            Dict with order details including broker order_id and status
        """
        try:
            # Build order intent
            intent = {
                "symbol": symbol,
                "side": side.upper(),
                "qty": quantity,
                "order_type": "LIMIT",  # Default to LIMIT orders
                "product": kwargs.get("profile", "MIS"),  # Use profile as product
                "validity": "DAY",
                "price": price,
            }
            
            # Place order
            result = self.broker.place_order(intent)
            
            logger.info(
                "Live order submitted: order_id=%s symbol=%s side=%s qty=%d price=%.2f status=%s",
                result.get("order_id", "unknown"),
                symbol,
                side,
                quantity,
                price,
                result.get("status", "UNKNOWN")
            )
            
            return {
                "order_id": result.get("order_id", f"live-{uuid.uuid4().hex[:8]}"),
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "price": price,
                "status": result.get("status", "SUBMITTED"),
                "message": result.get("message", ""),
            }
        except Exception as e:
            logger.error("Live order failed: %s", e, exc_info=True)
            return {
                "order_id": f"live-error-{uuid.uuid4().hex[:8]}",
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "price": price,
                "status": "ERROR",
                "error": str(e),
            }
    
    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """
        Cancel an order by ID.
        
        Args:
            order_id: Broker order ID
            
        Returns:
            Dict with cancellation status
        """
        try:
            if hasattr(self.broker, 'cancel_order'):
                result = self.broker.cancel_order(order_id)
                return result
            else:
                return {"order_id": order_id, "status": "NOT_SUPPORTED"}
        except Exception as e:
            logger.error("Order cancellation failed: %s", e, exc_info=True)
            return {"order_id": order_id, "status": "ERROR", "error": str(e)}
    
    def sync_open_orders(self) -> list[Dict[str, Any]]:
        """
        Synchronize and return open orders.
        
        Returns:
            List of open orders
        """
        try:
            if hasattr(self.broker, 'get_orders'):
                orders = self.broker.get_orders()
                return [o for o in orders if o.get("status") in ("OPEN", "PENDING", "TRIGGER_PENDING")]
            else:
                return []
        except Exception as e:
            logger.error("Failed to sync open orders: %s", e, exc_info=True)
            return []


class ExecutionService:
    """
    Execution Service - Order placement and management.
    
    Responsibilities:
    - Consume risk-approved order intents
    - Place orders via paper or live backend
    - Log orders and fills via TradeRecorder
    - Publish execution events
    """
    
    def __init__(self, bus: EventBus, cfg: Dict[str, Any], mode: str = "paper"):
        """
        Initialize the Execution service.
        
        Args:
            bus: EventBus instance for pub/sub
            cfg: Configuration dict
            mode: Trading mode - "paper" or "live"
        """
        self.bus = bus
        self.cfg = cfg
        self.mode = mode
        self.recorder = TradeRecorder()
        self.backend = self._select_backend(mode)
        self.running = False
        self._subscribe()
        logger.info("ExecutionService initialized in mode=%s", mode)
    
    def _select_backend(self, mode: str) -> ExecutionBackend:
        """
        Select and initialize the appropriate backend.
        
        Args:
            mode: Trading mode - "paper" or "live"
            
        Returns:
            ExecutionBackend instance
        """
        if mode == "live":
            return LiveBackend(self.cfg)
        return PaperBackend(self.cfg)
    
    def _subscribe(self):
        """Subscribe to risk-approved and risk-rejected events."""
        self.bus.subscribe("risk.order_approved.*", self.on_approved_order)
        self.bus.subscribe("risk.order_rejected.*", self.on_rejected_order)
        logger.info("ExecutionService subscribed to risk.order_approved.* and risk.order_rejected.*")
    
    def on_approved_order(self, event: Event):
        """
        Handle risk-approved order intents.
        
        Expected payload:
        {
          "signal_id": "...",
          "symbol": "...",
          "logical": "...",
          "side": "BUY" | "SELL" | "EXIT",
          "quantity": 50,
          "price": 24500.0,
          "profile": "INTRADAY",
          "mode": "paper" | "live",
          "tf": "5m",
          "reason": "risk_ok",
          "timestamp": "...",
          "strategy": "..."
        }
        
        Args:
            event: Event containing order intent
        """
        payload = event.payload or {}
        
        # 1) Basic validation
        symbol = payload.get("symbol")
        side = payload.get("side")
        quantity = payload.get("quantity")
        price = payload.get("price")
        
        if not symbol or not side or quantity is None or price is None:
            logger.warning(
                "Invalid order intent: symbol=%s side=%s quantity=%s price=%s",
                symbol, side, quantity, price
            )
            return
        
        # Never call float(None) - defensive check
        try:
            price_float = float(price)
        except (TypeError, ValueError) as e:
            logger.warning("Cannot convert price=%r to float: %s", price, e)
            return
        
        # 2) Submit order via backend
        result = self.backend.submit_order(
            symbol=symbol,
            side=side,
            quantity=int(quantity),
            price=price_float,
            profile=payload.get("profile"),
            strategy=payload.get("strategy"),
        )
        
        # 3) Log order via TradeRecorder
        self.recorder.record_order(
            symbol=symbol,
            side=side,
            quantity=int(quantity),
            price=price_float,
            status=result.get("status", "UNKNOWN"),
            tf=payload.get("tf", ""),
            profile=payload.get("profile", ""),
            strategy=payload.get("strategy", ""),
            parent_signal_timestamp=payload.get("timestamp", ""),
            extra={"order_id": result.get("order_id"), "signal_id": payload.get("signal_id")},
        )
        
        # 4) Publish exec.order_submitted event
        topic_suffix = f"{payload.get('profile', 'GENERIC')}.{symbol}"
        self.bus.publish(
            f"exec.order_submitted.{topic_suffix}",
            {
                "order_id": result.get("order_id"),
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "price": price_float,
                "status": result.get("status", "UNKNOWN"),
                "mode": self.mode,
                "timestamp": payload.get("timestamp", datetime.utcnow().isoformat()),
                "signal_id": payload.get("signal_id"),
                "strategy": payload.get("strategy"),
            },
        )
        
        # 5) For paper mode with immediate fill, also log fill and publish exec.fill
        if self.mode == "paper" and result.get("status") == "FILLED":
            fill_price = result.get("fill_price", price_float)
            
            # Log fill via TradeRecorder (using record_order with FILLED status)
            # Note: TradeRecorder doesn't have a separate log_fill method, so we use record_order
            self.recorder.record_order(
                symbol=symbol,
                side=side,
                quantity=int(quantity),
                price=float(fill_price),
                status="FILLED",
                tf=payload.get("tf", ""),
                profile=payload.get("profile", ""),
                strategy=payload.get("strategy", ""),
                parent_signal_timestamp=payload.get("timestamp", ""),
                extra={
                    "order_id": result.get("order_id"),
                    "signal_id": payload.get("signal_id"),
                    "fill_type": "immediate",
                },
            )
            
            # Publish fill event
            self.bus.publish(
                f"exec.fill.{topic_suffix}",
                {
                    "order_id": result.get("order_id"),
                    "symbol": symbol,
                    "logical": payload.get("logical"),
                    "side": side,
                    "fill_qty": quantity,
                    "fill_price": float(fill_price),
                    "status": "FILLED",
                    "mode": self.mode,
                    "profile": payload.get("profile"),
                    "strategy": payload.get("strategy"),
                    "timestamp": payload.get("timestamp", datetime.utcnow().isoformat()),
                },
            )
            
            logger.info(
                "Paper fill published: order_id=%s symbol=%s side=%s qty=%d fill_price=%.2f",
                result.get("order_id"), symbol, side, quantity, fill_price
            )
    
    def on_rejected_order(self, event: Event):
        """
        Handle risk-rejected order intents.
        
        For now: just log structured event for analytics.
        
        Args:
            event: Event containing rejected order intent
        """
        payload = event.payload or {}
        logger.info(
            "Order rejected by risk: signal_id=%s symbol=%s side=%s reason=%s",
            payload.get("signal_id"),
            payload.get("symbol"),
            payload.get("side"),
            payload.get("reason", "unknown"),
        )
        # Future: could log to TradeRecorder as REJECTED_BY_RISK
    
    def run_forever(self) -> None:
        """
        Main service loop with heartbeat.
        
        The actual work is done by event handlers.
        This loop just keeps the service alive.
        """
        logger.info(f"ExecutionService starting in mode={self.mode}...")
        self.running = True
        
        try:
            while self.running:
                logger.debug("ExecutionService heartbeat (mode=%s)", self.mode)
                time.sleep(10)  # Heartbeat every 10 seconds
        except KeyboardInterrupt:
            logger.info("ExecutionService interrupted by user")
        finally:
            self.running = False
            logger.info("ExecutionService stopped")
