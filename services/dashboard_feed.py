"""
Dashboard Feed Service

Aggregates state from all services for dashboard consumption.
Provides JSON snapshot with signals, orders, positions, and system state.

Features:
- Subscribe to portfolio.updated and order.filled events
- Aggregate signals from strategy service
- Provide get_snapshot() for dashboard polling
- Thread-safe state management
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Dict, List, Optional

from services.event_bus import EventBus

logger = logging.getLogger(__name__)


class DashboardFeed:
    """
    Dashboard Feed for aggregating state across services.
    
    Subscribes to events:
    - signals.raw
    - signals.fused
    - order.filled
    - portfolio.updated
    
    Provides snapshot for dashboard consumption.
    """
    
    def __init__(
        self,
        event_bus: Optional[EventBus] = None,
        max_signals: int = 100,
        max_orders: int = 100,
    ):
        """
        Initialize Dashboard Feed.
        
        Args:
            event_bus: EventBus to subscribe to
            max_signals: Maximum number of signals to buffer
            max_orders: Maximum number of orders to buffer
        """
        self.bus = event_bus
        
        # State buffers
        self.signals: deque = deque(maxlen=max_signals)
        self.orders: deque = deque(maxlen=max_orders)
        self.portfolio_state: Dict[str, Any] = {}
        self.system_state: Dict[str, Any] = {
            "status": "initialized",
            "last_update": datetime.now(timezone.utc).isoformat(),
        }
        
        self._lock = Lock()
        
        # Subscribe to events if bus available
        if self.bus:
            self.bus.subscribe("signals.fused", self._on_signal_fused)
            self.bus.subscribe("order.filled", self._on_order_filled)
            self.bus.subscribe("portfolio.updated", self._on_portfolio_updated)
            logger.info("DashboardFeed subscribed to events")
        else:
            logger.warning("DashboardFeed initialized without EventBus")
    
    def get_snapshot(self) -> Dict[str, Any]:
        """
        Get current dashboard snapshot.
        
        Returns:
            Dict with:
                - signals: Recent signals
                - orders: Recent orders
                - positions: Current positions
                - portfolio: Portfolio summary
                - system: System state
        """
        with self._lock:
            return {
                "signals": list(self.signals),
                "orders": list(self.orders),
                "positions": self.portfolio_state.get("positions", []),
                "portfolio": {
                    "cash": self.portfolio_state.get("cash", 0.0),
                    "equity": self.portfolio_state.get("equity", 0.0),
                    "realized_pnl": self.portfolio_state.get("realized_pnl", 0.0),
                    "unrealized_pnl": self.portfolio_state.get("unrealized_pnl", 0.0),
                    "exposure": self.portfolio_state.get("exposure", 0.0),
                    "position_count": self.portfolio_state.get("position_count", 0),
                },
                "system": self.system_state,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
    
    def update_system_state(self, key: str, value: Any) -> None:
        """
        Update system state field.
        
        Args:
            key: State key
            value: State value
        """
        with self._lock:
            self.system_state[key] = value
            self.system_state["last_update"] = datetime.now(timezone.utc).isoformat()
    
    def _on_signal_fused(self, event: Dict[str, Any]) -> None:
        """
        Handle fused signal event.
        
        Args:
            event: Signal event from EventBus
        """
        try:
            payload = event.get("payload", {})
            with self._lock:
                self.signals.append({
                    "timestamp": event.get("timestamp"),
                    "symbol": payload.get("symbol"),
                    "action": payload.get("action"),
                    "confidence": payload.get("confidence", 0.0),
                    "reason": payload.get("reason", ""),
                    "strategy_code": payload.get("strategy_code", ""),
                })
        except Exception as exc:
            logger.debug("Error handling signal event: %s", exc)
    
    def _on_order_filled(self, event: Dict[str, Any]) -> None:
        """
        Handle order filled event.
        
        Args:
            event: Order event from EventBus
        """
        try:
            payload = event.get("payload", {})
            with self._lock:
                self.orders.append({
                    "timestamp": event.get("timestamp"),
                    "order_id": payload.get("order_id"),
                    "symbol": payload.get("symbol"),
                    "side": payload.get("side"),
                    "qty": payload.get("qty", 0),
                    "avg_price": payload.get("avg_price", 0.0),
                    "strategy_code": payload.get("strategy_code", ""),
                })
        except Exception as exc:
            logger.debug("Error handling order event: %s", exc)
    
    def _on_portfolio_updated(self, event: Dict[str, Any]) -> None:
        """
        Handle portfolio updated event.
        
        Args:
            event: Portfolio event from EventBus
        """
        try:
            payload = event.get("payload", {})
            with self._lock:
                self.portfolio_state = payload
        except Exception as exc:
            logger.debug("Error handling portfolio event: %s", exc)
    
    def get_signals(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get recent signals.
        
        Args:
            limit: Maximum number of signals to return
            
        Returns:
            List of signal dicts
        """
        with self._lock:
            return list(self.signals)[-limit:]
    
    def get_orders(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get recent orders.
        
        Args:
            limit: Maximum number of orders to return
            
        Returns:
            List of order dicts
        """
        with self._lock:
            return list(self.orders)[-limit:]
    
    def get_positions(self) -> List[Dict[str, Any]]:
        """
        Get current positions.
        
        Returns:
            List of position dicts
        """
        with self._lock:
            return self.portfolio_state.get("positions", [])
    
    def clear(self) -> None:
        """Clear all buffers."""
        with self._lock:
            self.signals.clear()
            self.orders.clear()
            self.portfolio_state.clear()
            logger.debug("DashboardFeed cleared")
