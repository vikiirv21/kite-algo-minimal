"""
Event Bus abstraction for service-to-service communication.

Provides Event dataclass, EventBus abstract base class, and concrete implementations:
- InMemoryEventBus: Thread-based, single-process (development)
- RedisEventBus: Distributed, multi-process (production, placeholder)
"""

from __future__ import annotations

import logging
import queue
import threading
import time
import uuid
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List

logger = logging.getLogger(__name__)


@dataclass
class Event:
    """
    Represents a single event in the system.
    
    Attributes:
        event_id: Unique identifier for this event (UUID)
        ts: Timestamp when event was created
        type: Event type/topic (e.g., "marketdata.tick", "strategy.signal")
        source: Service that generated this event
        payload: Event-specific data as a dictionary
    """
    event_id: str
    ts: datetime | str
    type: str
    source: str
    payload: dict = field(default_factory=dict)


class EventBus(ABC):
    """
    Abstract base class for event bus implementations.
    
    An EventBus enables publish-subscribe communication between services.
    Services publish events to topics, and subscribers receive events from topics they subscribe to.
    """
    
    @abstractmethod
    def publish(self, topic: str, payload: dict) -> None:
        """
        Publish an event to a topic.
        
        Args:
            topic: Topic name (e.g., "marketdata.tick")
            payload: Event data as dictionary
        """
        pass
    
    @abstractmethod
    def subscribe(self, topic: str, handler: Callable[[Event], None]) -> None:
        """
        Subscribe a handler function to a topic.
        
        Args:
            topic: Topic name to subscribe to
            handler: Callback function that receives Event objects
        """
        pass
    
    @abstractmethod
    def start(self) -> None:
        """Start the event bus (initialize background threads/connections)."""
        pass
    
    @abstractmethod
    def stop(self) -> None:
        """Stop the event bus and release resources."""
        pass


class InMemoryEventBus(EventBus):
    """
    In-memory event bus using Python threading and queues.
    
    Suitable for:
    - Local development
    - Single-process deployments
    - Testing
    
    Not suitable for:
    - Multi-process deployments
    - Distributed systems
    - High-throughput production use
    """
    
    def __init__(self, max_queue_size: int = 1000):
        """
        Initialize the in-memory event bus.
        
        Args:
            max_queue_size: Maximum size of event queue before blocking
        """
        self._subscribers: Dict[str, List[Callable[[Event], None]]] = defaultdict(list)
        self._queue: queue.Queue = queue.Queue(maxsize=max_queue_size)
        self._running = False
        self._worker_thread: threading.Thread | None = None
        self._lock = threading.Lock()
    
    def publish(self, topic: str, payload: dict) -> None:
        """
        Publish an event to a topic.
        
        Creates an Event object and places it in the queue for processing.
        
        Args:
            topic: Topic name
            payload: Event data
        """
        event = Event(
            event_id=str(uuid.uuid4()),
            ts=datetime.utcnow().isoformat(),
            type=topic,
            source="publisher",  # Can be enhanced to track actual source
            payload=payload
        )
        
        try:
            self._queue.put(event, timeout=1.0)
        except queue.Full:
            logger.warning(f"Event queue full, dropping event: {topic}")
    
    def subscribe(self, topic: str, handler: Callable[[Event], None]) -> None:
        """
        Subscribe a handler to a topic.
        
        Multiple handlers can subscribe to the same topic.
        
        Args:
            topic: Topic to subscribe to
            handler: Callback function
        """
        with self._lock:
            self._subscribers[topic].append(handler)
            logger.debug(f"Subscribed handler to topic: {topic}")
    
    def start(self) -> None:
        """Start the event bus worker thread."""
        if self._running:
            logger.warning("EventBus already running")
            return
        
        self._running = True
        self._worker_thread = threading.Thread(target=self._worker, daemon=True)
        self._worker_thread.start()
        logger.info("InMemoryEventBus started")
    
    def stop(self) -> None:
        """Stop the event bus and worker thread."""
        if not self._running:
            return
        
        self._running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=5.0)
        logger.info("InMemoryEventBus stopped")
    
    def _worker(self) -> None:
        """
        Background worker thread that processes events from the queue.
        
        Continuously dequeues events and dispatches them to subscribed handlers.
        """
        while self._running:
            try:
                event = self._queue.get(timeout=0.1)
                self._dispatch_event(event)
                self._queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error processing event: {e}", exc_info=True)
    
    def _dispatch_event(self, event: Event) -> None:
        """
        Dispatch an event to all subscribed handlers.
        
        Args:
            event: Event to dispatch
        """
        with self._lock:
            handlers = self._subscribers.get(event.type, [])
        
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(
                    f"Handler error for topic {event.type}: {e}",
                    exc_info=True
                )


class RedisEventBus(EventBus):
    """
    Redis-based event bus for distributed deployments.
    
    TODO: Implement using Redis Pub/Sub or Redis Streams.
    
    Features (planned):
    - Multi-process support
    - Persistent event history (with Streams)
    - Horizontal scaling
    - Network resilience
    
    Usage (future):
        redis_bus = RedisEventBus(host="localhost", port=6379)
        redis_bus.start()
        redis_bus.publish("marketdata.tick", {"symbol": "NIFTY", "ltp": 18000})
    """
    
    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0):
        """
        Initialize Redis event bus (not yet implemented).
        
        Args:
            host: Redis host
            port: Redis port
            db: Redis database number
        """
        self.host = host
        self.port = port
        self.db = db
        logger.warning("RedisEventBus is a placeholder and not yet implemented")
    
    def publish(self, topic: str, payload: dict) -> None:
        """Publish event (not implemented)."""
        raise NotImplementedError("RedisEventBus.publish not yet implemented")
    
    def subscribe(self, topic: str, handler: Callable[[Event], None]) -> None:
        """Subscribe to topic (not implemented)."""
        raise NotImplementedError("RedisEventBus.subscribe not yet implemented")
    
    def start(self) -> None:
        """Start event bus (not implemented)."""
        raise NotImplementedError("RedisEventBus.start not yet implemented")
    
    def stop(self) -> None:
        """Stop event bus (not implemented)."""
        raise NotImplementedError("RedisEventBus.stop not yet implemented")
