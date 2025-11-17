"""
Options Trading Service

Manages options trading strategies (iron condors, straddles, etc.).

Topics:
- Publishes: strategy.eval_request.options.<symbol>
- Subscribes: bars.options.*
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.common.event_bus import EventBus, Event

logger = logging.getLogger(__name__)


@dataclass
class ServiceConfig:
    """Configuration for Options Trader service."""
    name: str = "trader_options"
    enabled: bool = True
    symbols: list = None
    
    def __post_init__(self):
        if self.symbols is None:
            self.symbols = ["NIFTY", "BANKNIFTY"]


class TraderOptionsService:
    """
    Options Trading Service.
    
    Responsibilities:
    - Monitor options market data
    - Publish strategy evaluation requests for options
    - Manage complex options strategies
    """
    
    def __init__(self, event_bus: EventBus, config: ServiceConfig):
        """
        Initialize the Options Trader service.
        
        Args:
            event_bus: EventBus instance for pub/sub
            config: Service configuration
        """
        self.event_bus = event_bus
        self.config = config
        self.running = False
    
    def on_bar_event(self, event: Event) -> None:
        """
        Handle incoming bar data from market data service.
        
        Args:
            event: Event containing bar data
        """
        try:
            payload = event.payload
            symbol = payload.get("symbol", "")
            
            # Extract bar data
            bar = {
                "open": payload.get("open", 0.0),
                "high": payload.get("high", 0.0),
                "low": payload.get("low", 0.0),
                "close": payload.get("close", 0.0),
                "volume": payload.get("volume", 0),
                "timestamp": payload.get("timestamp", datetime.utcnow().isoformat())
            }
            
            # Create strategy evaluation request
            eval_request = {
                "symbol": symbol,
                "logical": symbol,
                "asset_class": "options",
                "tf": "5m",  # Default timeframe
                "price": bar["close"],
                "mode": "live",
                "timestamp": bar["timestamp"],
                "bar": bar,
            }
            
            # Publish to strategy service
            topic = f"strategy.eval_request.options.{symbol}"
            self.event_bus.publish(topic, eval_request)
            logger.debug(f"Published eval request to {topic}")
            
        except Exception as e:
            logger.exception(f"Error processing bar event: {e}")
    
    def _publish_fake_bars(self):
        """
        Publish fake bar data for testing.
        
        This simulates receiving bar data from market data service.
        In production, this would come from actual market data.
        """
        for symbol in self.config.symbols:
            # Create fake bar for underlying
            fake_price = 18000.0 if symbol == "NIFTY" else 42000.0
            bar_payload = {
                "symbol": symbol,
                "open": fake_price,
                "high": fake_price + 10,
                "low": fake_price - 10,
                "close": fake_price + 5,
                "volume": 2000,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Publish to bars.options.<symbol>
            topic = f"bars.options.{symbol}"
            self.event_bus.publish(topic, bar_payload)
            logger.debug(f"Published fake bar to {topic}")
    
    def run_forever(self) -> None:
        """
        Main service loop.
        
        Subscribes to bar events and publishes strategy evaluation requests.
        """
        logger.info(f"Service {self.config.name} starting...")
        self.running = True
        
        # Subscribe to bar events with wildcard
        self.event_bus.subscribe("bars.options.*", self.on_bar_event)
        logger.info("Subscribed to bars.options.*")
        
        try:
            iteration = 0
            while self.running:
                # Publish fake bars every 5 seconds for testing
                if iteration % 5 == 0:
                    self._publish_fake_bars()
                
                time.sleep(1)
                iteration += 1
                
                if iteration % 60 == 0:  # Log every minute
                    logger.info(f"Service {self.config.name} heartbeat")
                    
        except KeyboardInterrupt:
            logger.info(f"Service {self.config.name} interrupted")
        finally:
            self.running = False
            logger.info(f"Service {self.config.name} stopped")
