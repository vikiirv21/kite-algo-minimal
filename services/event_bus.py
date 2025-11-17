"""
Event Bus Service

Minimal in-process event bus for HFT Architecture v3.
Provides publish/subscribe pattern with async queue readiness.

Features:
- publish(event_type, payload)
- subscribe(event_type, callback)
- Safe no-op if no subscribers
- Thread-safe operation
- Works in both sync and async contexts
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class EventBus:
    """
    Minimal in-process event bus for service communication.
    
    This is a simpler, synchronous version suitable for service-layer
    communication. For async execution context, use core.execution_engine_v3.EventBus.
    """
    
    def __init__(self, buffer_size: int = 1000):
        """
        Initialize EventBus.
        
        Args:
            buffer_size: Maximum number of events to buffer for history
        """
        self.buffer: deque = deque(maxlen=buffer_size)
        self.subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._lock = Lock()
        
    def publish(self, event_type: str, payload: Dict[str, Any]) -> None:
        """
        Publish an event to all subscribers.
        
        Args:
            event_type: Type/name of the event (e.g., "signals.raw", "order.filled")
            payload: Event data dictionary
        """
        if not isinstance(payload, dict):
            logger.warning("EventBus.publish expects dict payload, got %s", type(payload))
            payload = {"data": payload}
        
        event = {
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
        
        with self._lock:
            # Add to buffer for history
            self.buffer.append(event)
            
            # Notify subscribers - safe no-op if none exist
            subscribers = self.subscribers.get(event_type, [])
            for callback in subscribers:
                try:
                    callback(event)
                except Exception as exc:
                    logger.error(
                        "Error in event subscriber for %s: %s",
                        event_type,
                        exc,
                        exc_info=True
                    )
    
    def subscribe(self, event_type: str, callback: Callable) -> None:
        """
        Subscribe to an event type.
        
        Args:
            event_type: Type/name of event to subscribe to
            callback: Function to call when event is published (receives event dict)
        """
        with self._lock:
            self.subscribers[event_type].append(callback)
            logger.debug("Subscribed to event type: %s", event_type)
    
    def get_recent_events(
        self, 
        event_type: Optional[str] = None, 
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get recent events from buffer.
        
        Args:
            event_type: Filter by event type (None for all)
            limit: Maximum number of events to return
            
        Returns:
            List of recent events
        """
        with self._lock:
            events = list(self.buffer)
        
        if event_type:
            events = [e for e in events if e.get("type") == event_type]
        
        return events[-limit:] if events else []
    
    def clear_buffer(self) -> None:
        """Clear the event buffer."""
        with self._lock:
            self.buffer.clear()
    
    def subscriber_count(self, event_type: Optional[str] = None) -> int:
        """
        Get count of subscribers.
        
        Args:
            event_type: Specific event type, or None for total across all types
            
        Returns:
            Number of subscribers
        """
        with self._lock:
            if event_type:
                return len(self.subscribers.get(event_type, []))
            return sum(len(subs) for subs in self.subscribers.values())
