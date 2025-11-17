"""
Journal Service

Logs all trading events and decisions for auditing and analysis.

Topics:
- Publishes: (none, terminal sink)
- Subscribes: * (all events)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.common.event_bus import EventBus, Event

logger = logging.getLogger(__name__)


@dataclass
class ServiceConfig:
    """Configuration for Journal service."""
    name: str = "journal"
    enabled: bool = True


class JournalService:
    """
    Journal Service - Trading event logging and auditing.
    
    Responsibilities:
    - Write events to CSV, JSON, or database
    - Support real-time querying and debugging
    - Generate daily reports
    """
    
    def __init__(self, event_bus: EventBus, config: ServiceConfig):
        """
        Initialize the Journal service.
        
        Args:
            event_bus: EventBus instance for pub/sub
            config: Service configuration
        """
        self.event_bus = event_bus
        self.config = config
        self.running = False
    
    def run_forever(self) -> None:
        """
        Main service loop.
        
        Placeholder implementation that logs startup and keeps running.
        TODO: Implement event journaling logic.
        """
        logger.info(f"Service {self.config.name} starting...")
        self.running = True
        
        try:
            while self.running:
                # TODO: Subscribe to all events
                # TODO: Write events to persistent storage
                # TODO: Generate periodic reports
                
                time.sleep(1)  # Placeholder sleep
        except KeyboardInterrupt:
            logger.info(f"Service {self.config.name} interrupted")
        finally:
            self.running = False
            logger.info(f"Service {self.config.name} stopped")
