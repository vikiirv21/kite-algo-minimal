"""
Kite broker adapter for LIVE trading.

Provides a clean interface for:
- Order placement, modification, cancellation
- Position and order fetching
- WebSocket tick subscription with normalized callbacks
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Optional

from kiteconnect import KiteConnect, KiteTicker, exceptions as kite_exceptions

from broker.auth import make_kite_client_from_env, token_is_valid
from core.kite_http import kite_request

logger = logging.getLogger(__name__)


class KiteBroker:
    """
    Broker adapter for live Kite trading.
    
    Handles:
    - Session/login validation
    - Order placement and management
    - Position and order queries
    - WebSocket tick subscriptions
    """
    
    def __init__(self, config: Dict[str, Any], logger_instance: Optional[logging.Logger] = None):
        """
        Initialize KiteBroker.
        
        Args:
            config: Config dict with optional broker credentials
            logger_instance: Optional logger instance
        """
        self.config = config
        self.logger = logger_instance or logger
        self.kite: Optional[KiteConnect] = None
        self.ticker: Optional[KiteTicker] = None
        self._on_tick_callback: Optional[Callable] = None
        self._subscribed_instruments: List[int] = []
        
    def ensure_logged_in(self) -> bool:
        """
        Ensure we have a valid Kite session.
        
        Uses existing token from environment/files.
        Does NOT perform interactive login (use scripts/login_kite.py for that).
        
        Returns:
            True if logged in successfully, False otherwise
        """
        if self.kite is not None and token_is_valid(self.kite):
            return True
            
        try:
            self.kite = make_kite_client_from_env()
            if token_is_valid(self.kite):
                self.logger.info("✅ Kite session validated successfully")
                return True
            else:
                self.logger.error("❌ Kite token validation failed - run scripts/login_kite.py first")
                return False
        except Exception as exc:
            self.logger.error("❌ Failed to create Kite client: %s", exc)
            return False
    
    def place_order(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        """
        Place a LIVE order via Kite.
        
        Args:
            intent: Order intent dict with:
                - symbol: Trading symbol
                - side: "BUY" or "SELL"
                - qty: Quantity
                - order_type: "MARKET", "LIMIT", etc.
                - product: "MIS", "NRML", "CNC"
                - validity: "DAY", "IOC"
                - price: Limit price (for LIMIT orders)
                - trigger_price: Trigger price (for SL orders)
                
        Returns:
            Dict with order_id, status, message
        """
        if not self.ensure_logged_in():
            raise RuntimeError("Not logged in to Kite - cannot place order")
            
        symbol = intent.get("symbol")
        side = intent.get("side", "BUY").upper()
        qty = int(intent.get("qty", 0))
        order_type = intent.get("order_type", "MARKET").upper()
        product = intent.get("product", "MIS").upper()
        validity = intent.get("validity", "DAY").upper()
        price = intent.get("price")
        trigger_price = intent.get("trigger_price")
        exchange = intent.get("exchange", "NFO").upper()
        
        if qty <= 0:
            raise ValueError(f"Invalid quantity: {qty}")
            
        # Map side to transaction_type
        transaction_type = self.kite.TRANSACTION_TYPE_BUY if side == "BUY" else self.kite.TRANSACTION_TYPE_SELL
        
        # Prepare order params
        order_params = {
            "tradingsymbol": symbol,
            "exchange": exchange,
            "transaction_type": transaction_type,
            "quantity": qty,
            "order_type": order_type,
            "product": product,
            "validity": validity,
        }
        
        if price is not None and order_type in ("LIMIT", "SL-M"):
            order_params["price"] = float(price)
            
        if trigger_price is not None and order_type in ("SL", "SL-M"):
            order_params["trigger_price"] = float(trigger_price)
            
        try:
            self.logger.info(
                "🔴 LIVE ORDER: %s %d x %s @ %s (type=%s, product=%s)",
                side, qty, symbol, price or "MARKET", order_type, product
            )
            order_id = kite_request(self.kite.place_order, self.kite.VARIETY_REGULAR, **order_params)
            
            return {
                "order_id": order_id,
                "status": "SUBMITTED",
                "message": f"Order placed successfully: {order_id}",
                "intent": intent,
            }
        except kite_exceptions.InputException as exc:
            self.logger.error("Order placement failed (input error): %s", exc)
            return {
                "order_id": None,
                "status": "REJECTED",
                "message": f"Input error: {exc}",
                "intent": intent,
            }
        except Exception as exc:
            self.logger.error("Order placement failed: %s", exc, exc_info=True)
            return {
                "order_id": None,
                "status": "ERROR",
                "message": f"Error: {exc}",
                "intent": intent,
            }
    
    def modify_order(self, order_id: str, fields: Dict[str, Any]) -> Dict[str, Any]:
        """
        Modify an existing order.
        
        Args:
            order_id: Kite order ID
            fields: Fields to modify (price, quantity, order_type, etc.)
            
        Returns:
            Dict with order_id, status, message
        """
        if not self.ensure_logged_in():
            raise RuntimeError("Not logged in to Kite - cannot modify order")
            
        try:
            self.logger.info("🔄 MODIFY ORDER: %s with %s", order_id, fields)
            kite_request(self.kite.modify_order, self.kite.VARIETY_REGULAR, order_id, **fields)
            return {
                "order_id": order_id,
                "status": "MODIFIED",
                "message": f"Order {order_id} modified successfully",
            }
        except Exception as exc:
            self.logger.error("Order modification failed: %s", exc, exc_info=True)
            return {
                "order_id": order_id,
                "status": "ERROR",
                "message": f"Error: {exc}",
            }
    
    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """
        Cancel an order.
        
        Args:
            order_id: Kite order ID
            
        Returns:
            Dict with order_id, status, message
        """
        if not self.ensure_logged_in():
            raise RuntimeError("Not logged in to Kite - cannot cancel order")
            
        try:
            self.logger.info("❌ CANCEL ORDER: %s", order_id)
            kite_request(self.kite.cancel_order, self.kite.VARIETY_REGULAR, order_id)
            return {
                "order_id": order_id,
                "status": "CANCELLED",
                "message": f"Order {order_id} cancelled successfully",
            }
        except Exception as exc:
            self.logger.error("Order cancellation failed: %s", exc, exc_info=True)
            return {
                "order_id": order_id,
                "status": "ERROR",
                "message": f"Error: {exc}",
            }
    
    def fetch_positions(self) -> List[Dict[str, Any]]:
        """
        Fetch current positions from Kite.
        
        Returns:
            List of position dicts
        """
        if not self.ensure_logged_in():
            self.logger.warning("Not logged in - cannot fetch positions")
            return []
            
        try:
            positions = kite_request(self.kite.positions)
            # positions is typically {"net": [...], "day": [...]}
            if isinstance(positions, dict):
                return positions.get("net", []) or positions.get("day", [])
            return positions or []
        except Exception as exc:
            self.logger.error("Failed to fetch positions: %s", exc)
            return []
    
    def fetch_open_orders(self) -> List[Dict[str, Any]]:
        """
        Fetch open/pending orders from Kite.
        
        Returns:
            List of order dicts
        """
        if not self.ensure_logged_in():
            self.logger.warning("Not logged in - cannot fetch orders")
            return []
            
        try:
            orders = kite_request(self.kite.orders)
            # Filter for open/pending orders
            if isinstance(orders, list):
                return [
                    o for o in orders 
                    if o.get("status") in ("OPEN", "TRIGGER PENDING", "PENDING")
                ]
            return []
        except Exception as exc:
            self.logger.error("Failed to fetch orders: %s", exc)
            return []
    
    def subscribe_ticks(self, instruments: List[int], on_tick_callback: Callable) -> bool:
        """
        Subscribe to WebSocket ticks for given instrument tokens.
        
        Args:
            instruments: List of instrument tokens
            on_tick_callback: Callback function(tick_dict) for each tick
            
        Returns:
            True if subscription successful, False otherwise
        """
        if not self.ensure_logged_in():
            self.logger.error("Not logged in - cannot subscribe to ticks")
            return False
            
        api_key = getattr(self.kite, "api_key", None) or getattr(self.kite, "_api_key", None)
        access_token = getattr(self.kite, "access_token", None) or getattr(self.kite, "_access_token", None)
        
        if not api_key or not access_token:
            self.logger.error("Missing API key or access token for WebSocket")
            return False
            
        try:
            if self.ticker is None:
                self.ticker = KiteTicker(api_key, access_token)
                self.ticker.on_ticks = self._handle_ticks
                self.ticker.on_connect = self._on_connect
                self.ticker.on_close = self._on_close
                self.ticker.on_error = self._on_error
                self.ticker.on_reconnect = self._on_reconnect
                self.ticker.on_noreconnect = self._on_noreconnect
                
            self._on_tick_callback = on_tick_callback
            self._subscribed_instruments = instruments
            
            # Start ticker in background thread
            import threading
            threading.Thread(target=self.ticker.connect, daemon=True).start()
            
            # Give it a moment to connect
            time.sleep(2)
            
            self.logger.info("✅ WebSocket tick subscription initiated for %d instruments", len(instruments))
            return True
            
        except Exception as exc:
            self.logger.error("Failed to subscribe to ticks: %s", exc, exc_info=True)
            return False
    
    def _handle_ticks(self, ws, ticks: List[Dict[str, Any]]) -> None:
        """Internal: Handle incoming ticks from WebSocket."""
        if not self._on_tick_callback:
            return
            
        for tick in ticks:
            try:
                # Normalize tick to consistent format
                normalized = self._normalize_tick(tick)
                self._on_tick_callback(normalized)
            except Exception as exc:
                self.logger.error("Error in tick callback: %s", exc)
    
    def _normalize_tick(self, tick: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize Kite tick to consistent format.
        
        Returns dict with:
            instrument_token, tradingsymbol, last_price, volume, etc.
        """
        return {
            "instrument_token": tick.get("instrument_token"),
            "tradingsymbol": tick.get("tradingsymbol"),
            "last_price": tick.get("last_price"),
            "last_traded_quantity": tick.get("last_traded_quantity"),
            "volume": tick.get("volume"),
            "average_price": tick.get("average_price"),
            "oi": tick.get("oi"),
            "oi_day_high": tick.get("oi_day_high"),
            "oi_day_low": tick.get("oi_day_low"),
            "timestamp": tick.get("timestamp") or tick.get("last_trade_time"),
            "ohlc": tick.get("ohlc", {}),
            "depth": tick.get("depth", {}),
        }
    
    def _on_connect(self, ws, response) -> None:
        """Internal: WebSocket connected callback."""
        self.logger.info("✅ WebSocket connected")
        if self._subscribed_instruments:
            ws.subscribe(self._subscribed_instruments)
            ws.set_mode(ws.MODE_FULL, self._subscribed_instruments)
            self.logger.info("✅ Subscribed to %d instruments", len(self._subscribed_instruments))
    
    def _on_close(self, ws, code, reason) -> None:
        """Internal: WebSocket closed callback."""
        self.logger.warning("⚠️ WebSocket closed: code=%s reason=%s", code, reason)
    
    def _on_error(self, ws, code, reason) -> None:
        """Internal: WebSocket error callback."""
        self.logger.error("❌ WebSocket error: code=%s reason=%s", code, reason)
    
    def _on_reconnect(self, ws, attempts_count) -> None:
        """Internal: WebSocket reconnecting callback."""
        self.logger.info("🔄 WebSocket reconnecting (attempt %d)", attempts_count)
    
    def _on_noreconnect(self, ws) -> None:
        """Internal: WebSocket no reconnect callback."""
        self.logger.error("❌ WebSocket max reconnect attempts reached")
    
    def stop_ticker(self) -> None:
        """Stop the WebSocket ticker."""
        if self.ticker:
            try:
                self.ticker.close()
            except Exception:
                pass
            self.ticker = None
            self.logger.info("WebSocket ticker stopped")
