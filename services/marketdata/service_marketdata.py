"""
Market Data Service

Fetches and distributes real-time market data (LTP, OHLC, order book).

Topics:
- Publishes: marketdata.tick, marketdata.quote, marketdata.ohlc
- Subscribes: control.start, control.stop
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
    """Configuration for Market Data service."""
    name: str = "marketdata"
    enabled: bool = True


class MarketDataService:
    """
    Market Data Service - Real-time price feed distribution.
    
    Responsibilities:
    - Connect to Kite WebSocket or REST APIs
    - Normalize and validate incoming data
    - Broadcast market updates to subscribers
    """
    
    def __init__(self, event_bus: EventBus, config: ServiceConfig):
        """
        Initialize the Market Data service.
        
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
        TODO: Implement actual market data fetching and publishing.
        """
        logger.info(f"Service {self.config.name} starting...")
        self.running = True
        
        try:
            while self.running:
                # TODO: Fetch market data from Kite API
                # TODO: Publish events to event_bus
                # Example:
                # self.event_bus.publish("marketdata.tick", {
                #     "symbol": "NIFTY",
                #     "ltp": 18000.0,
                #     "timestamp": datetime.utcnow().isoformat()
                # })
                
                time.sleep(1)  # Placeholder sleep
        except KeyboardInterrupt:
            logger.info(f"Service {self.config.name} interrupted")
        finally:
            self.running = False
            logger.info(f"Service {self.config.name} stopped")
