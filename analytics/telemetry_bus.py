"""
Real-Time Strategy & Market Telemetry Layer

Provides centralized event publishing and streaming for all engine components.
Supports SSE (Server-Sent Events) streaming for real-time telemetry consumption.

Event Types:
- signal_event: Strategy signals generated
- indicator_event: Indicator calculations
- order_event: Order lifecycle events
- position_event: Position updates
- engine_health: Engine health metrics
- decision_trace: Strategy decision traces
- universe_scan: Universe scanning results
- performance_update: Performance metrics updates
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from datetime import datetime, timezone
from threading import Lock
from typing import Any, AsyncIterator, Dict, List, Optional

logger = logging.getLogger(__name__)


class TelemetryBus:
    """
    Centralized telemetry bus for real-time event publishing and streaming.
    
    Features:
    - Thread-safe event publishing
    - In-memory event buffering (last-N events)
    - SSE/WebSocket streaming support
    - Structured JSON events with timestamps
    """
    
    _instance: Optional[TelemetryBus] = None
    _lock = Lock()
    
    def __new__(cls):
        """Singleton pattern to ensure single telemetry bus instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, buffer_size: int = 5000):
        """
        Initialize TelemetryBus.
        
        Args:
            buffer_size: Maximum number of events to buffer in memory
        """
        # Only initialize once
        if hasattr(self, '_initialized'):
            return
        
        self._initialized = True
        self.buffer: deque = deque(maxlen=buffer_size)
        self._buffer_lock = Lock()
        self._event_types_seen: set = set()
        logger.info("TelemetryBus initialized with buffer_size=%d", buffer_size)
    
    def publish_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        """
        Publish a telemetry event.
        
        Args:
            event_type: Type of event (e.g., 'signal_event', 'order_event')
            payload: Event data as dictionary
        """
        if not isinstance(payload, dict):
            logger.warning("TelemetryBus: payload must be dict, got %s", type(payload))
            payload = {"data": payload}
        
        # Create structured event with timestamp
        event = {
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
        
        with self._buffer_lock:
            self.buffer.append(event)
            self._event_types_seen.add(event_type)
        
        # Log at debug level to avoid log spam
        logger.debug("Published %s event: %s", event_type, payload)
    
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
            List of recent events (newest last)
        """
        with self._buffer_lock:
            events = list(self.buffer)
        
        if event_type:
            events = [e for e in events if e.get("type") == event_type]
        
        return events[-limit:] if events else []
    
    def get_event_types(self) -> List[str]:
        """
        Get list of all event types that have been published.
        
        Returns:
            List of event type strings
        """
        with self._buffer_lock:
            return sorted(self._event_types_seen)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get telemetry bus statistics.
        
        Returns:
            Dictionary with buffer stats
        """
        with self._buffer_lock:
            total_events = len(self.buffer)
            event_counts = {}
            for event in self.buffer:
                event_type = event.get("type", "unknown")
                event_counts[event_type] = event_counts.get(event_type, 0) + 1
        
        return {
            "total_events": total_events,
            "buffer_size": self.buffer.maxlen,
            "event_types": self.get_event_types(),
            "event_counts": event_counts,
        }
    
    def clear_buffer(self) -> None:
        """Clear all buffered events."""
        with self._buffer_lock:
            self.buffer.clear()
            logger.info("TelemetryBus buffer cleared")
    
    async def stream_events(
        self, 
        event_type: Optional[str] = None,
        poll_interval: float = 0.5
    ) -> AsyncIterator[str]:
        """
        Stream events as Server-Sent Events (SSE) format.
        
        Args:
            event_type: Filter by event type (None for all)
            poll_interval: How often to check for new events (seconds)
            
        Yields:
            SSE-formatted event strings
        """
        last_index = 0
        
        # Get current buffer size to start streaming from
        with self._buffer_lock:
            last_index = len(self.buffer)
        
        # Send initial connection message
        yield self._format_sse({
            "type": "connection",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": {"status": "connected", "event_type_filter": event_type}
        })
        
        try:
            while True:
                # Get new events since last check
                new_events = []
                with self._buffer_lock:
                    current_size = len(self.buffer)
                    if current_size > last_index:
                        # Get new events
                        events_to_send = list(self.buffer)[last_index:]
                        if event_type:
                            events_to_send = [e for e in events_to_send if e.get("type") == event_type]
                        new_events = events_to_send
                        last_index = current_size
                    elif current_size < last_index:
                        # Buffer wrapped around, reset
                        last_index = 0
                
                # Send new events
                for event in new_events:
                    yield self._format_sse(event)
                
                # Send heartbeat to keep connection alive
                if not new_events:
                    yield self._format_sse({
                        "type": "heartbeat",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "payload": {}
                    })
                
                await asyncio.sleep(poll_interval)
        
        except asyncio.CancelledError:
            logger.info("SSE stream cancelled for event_type=%s", event_type)
            raise
        except Exception as exc:
            logger.error("Error in SSE stream: %s", exc, exc_info=True)
            raise
    
    def _format_sse(self, event: Dict[str, Any]) -> str:
        """
        Format event as SSE message.
        
        Args:
            event: Event dictionary
            
        Returns:
            SSE-formatted string
        """
        # SSE format: data: <json>\n\n
        event_json = json.dumps(event, default=str)
        return f"data: {event_json}\n\n"


# Global singleton instance
_telemetry_bus: Optional[TelemetryBus] = None


def get_telemetry_bus() -> TelemetryBus:
    """
    Get the global TelemetryBus singleton instance.
    
    Returns:
        TelemetryBus instance
    """
    global _telemetry_bus
    if _telemetry_bus is None:
        _telemetry_bus = TelemetryBus()
    return _telemetry_bus


def publish_event(event_type: str, payload: Dict[str, Any]) -> None:
    """
    Convenience function to publish event to global telemetry bus.
    
    Args:
        event_type: Type of event
        payload: Event data dictionary
    """
    bus = get_telemetry_bus()
    bus.publish_event(event_type, payload)


# Helper functions for specific event types
def publish_signal_event(
    symbol: str,
    strategy_name: str,
    signal: str,
    **kwargs
) -> None:
    """Publish a strategy signal event."""
    payload = {
        "symbol": symbol,
        "strategy_name": strategy_name,
        "signal": signal,
        **kwargs
    }
    publish_event("signal_event", payload)


def publish_indicator_event(
    symbol: str,
    timeframe: str,
    indicators: Dict[str, Any],
    **kwargs
) -> None:
    """Publish an indicator calculation event."""
    payload = {
        "symbol": symbol,
        "timeframe": timeframe,
        "indicators": indicators,
        **kwargs
    }
    publish_event("indicator_event", payload)


def publish_order_event(
    order_id: str,
    symbol: str,
    side: str,
    status: str,
    **kwargs
) -> None:
    """Publish an order lifecycle event."""
    payload = {
        "order_id": order_id,
        "symbol": symbol,
        "side": side,
        "status": status,
        **kwargs
    }
    publish_event("order_event", payload)


def publish_position_event(
    symbol: str,
    position_size: int,
    **kwargs
) -> None:
    """Publish a position update event."""
    payload = {
        "symbol": symbol,
        "position_size": position_size,
        **kwargs
    }
    publish_event("position_event", payload)


def publish_engine_health(
    engine_name: str,
    status: str,
    metrics: Dict[str, Any],
    **kwargs
) -> None:
    """Publish an engine health event."""
    payload = {
        "engine_name": engine_name,
        "status": status,
        "metrics": metrics,
        **kwargs
    }
    publish_event("engine_health", payload)


def publish_decision_trace(
    strategy_name: str,
    symbol: str,
    decision: str,
    trace_data: Dict[str, Any],
    **kwargs
) -> None:
    """Publish a strategy decision trace event."""
    payload = {
        "strategy_name": strategy_name,
        "symbol": symbol,
        "decision": decision,
        "trace_data": trace_data,
        **kwargs
    }
    publish_event("decision_trace", payload)


def publish_universe_scan(
    scan_type: str,
    universe_size: int,
    summary: Dict[str, Any],
    **kwargs
) -> None:
    """Publish a universe scan event."""
    payload = {
        "scan_type": scan_type,
        "universe_size": universe_size,
        "summary": summary,
        **kwargs
    }
    publish_event("universe_scan", payload)


def publish_performance_update(
    metrics: Dict[str, Any],
    **kwargs
) -> None:
    """Publish a performance metrics update event."""
    payload = {
        "metrics": metrics,
        **kwargs
    }
    publish_event("performance_update", payload)
