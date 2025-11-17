"""
Strategy Service

Generates trading signals based on market data and indicators.

Topics:
- Publishes: signals.<asset_class>.<symbol>
- Subscribes: strategy.eval_request.*
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from services.common.event_bus import EventBus, Event

logger = logging.getLogger(__name__)


@dataclass
class ServiceConfig:
    """Configuration for Strategy service."""
    name: str = "strategy"
    enabled: bool = True
    history_lookback: int = 200
    strategies: list = None
    timeframe: str = "5m"
    
    def __post_init__(self):
        if self.strategies is None:
            self.strategies = []


class StrategyService:
    """
    Strategy Service - Signal generation engine.
    
    Responsibilities:
    - Receive strategy evaluation requests via event bus
    - Use StrategyEngineV2 to compute indicators and generate signals
    - Publish trading signals to signals.<asset_class>.<symbol>
    """
    
    def __init__(self, event_bus: EventBus, config: ServiceConfig):
        """
        Initialize the Strategy service.
        
        Args:
            event_bus: EventBus instance for pub/sub
            config: Service configuration
        """
        self.event_bus = event_bus
        self.config = config
        self.running = False
        
        # For v3 architecture, we don't need a full StrategyEngineV2
        # We'll implement lightweight signal generation here
        # The real StrategyEngineV2 is used by v2 paper engines
        
        logger.info("StrategyService initialized (v3 architecture)")
    
    def on_eval_request(self, event: Event) -> None:
        """
        Handle strategy evaluation request.
        
        Expected payload:
        {
            "symbol": str,
            "logical": str,
            "tf": str,
            "price": float,
            "mode": str,
            "timestamp": str,
            "asset_class": str,
            "bar": dict (optional with OHLCV data)
        }
        
        Args:
            event: Event containing evaluation request
        """
        try:
            payload = event.payload
            symbol = payload.get("symbol", "")
            logical = payload.get("logical", symbol)
            asset_class = payload.get("asset_class", "unknown")
            tf = payload.get("tf", self.config.timeframe)
            price = payload.get("price", 0.0)
            mode = payload.get("mode", "live")
            bar = payload.get("bar", {})
            
            logger.debug(f"Received eval request for {symbol} @ {price}")
            
            # For now, create a simple mock evaluation
            # In real implementation, we would:
            # 1. Fetch historical data window for the symbol
            # 2. Call engine.run_strategy() or engine.generate_decisions()
            # 3. Get signals from registered strategies
            
            # Create a minimal bar if not provided
            if not bar:
                bar = {
                    "open": price,
                    "high": price,
                    "low": price,
                    "close": price,
                    "volume": 0,
                    "timestamp": payload.get("timestamp", datetime.utcnow().isoformat())
                }
            
            # Mock signal generation - replace with real engine call
            # For demonstration, we'll generate a simple signal
            signal = self._generate_mock_signal(symbol, logical, asset_class, bar, mode)
            
            if signal:
                # Publish signal to signals.<asset_class>.<symbol>
                signal_topic = f"signals.{asset_class}.{symbol}"
                self.event_bus.publish(signal_topic, signal)
                logger.info(f"Published signal to {signal_topic}: {signal.get('action', 'HOLD')}")
            
        except Exception as e:
            logger.exception(f"Error processing eval request: {e}")
    
    def _generate_mock_signal(
        self, 
        symbol: str, 
        logical: str, 
        asset_class: str,
        bar: Dict[str, Any],
        mode: str
    ) -> Optional[Dict[str, Any]]:
        """
        Generate a mock signal for testing.
        
        In real implementation, this would call engine.run_strategy()
        or use engine.compute_indicators() + strategy logic.
        
        Returns:
            Signal dict or None
        """
        # For now, return a simple HOLD signal with computed indicators
        close = bar.get("close", 0.0)
        
        return {
            "symbol": symbol,
            "logical": logical,
            "asset_class": asset_class,
            "action": "HOLD",  # BUY, SELL, EXIT, HOLD
            "confidence": 0.0,
            "price": close,
            "reason": "Mock signal from StrategyService",
            "mode": mode,
            "timestamp": datetime.utcnow().isoformat(),
            "strategy": "mock_strategy",
        }
    
    def run_forever(self) -> None:
        """
        Main service loop.
        
        Subscribes to strategy evaluation requests and processes them.
        """
        logger.info(f"Service {self.config.name} starting...")
        self.running = True
        
        # Subscribe to strategy evaluation requests with wildcard
        # This will match "strategy.eval_request.fno.NIFTY", etc.
        self.event_bus.subscribe("strategy.eval_request.*", self.on_eval_request)
        logger.info("Subscribed to strategy.eval_request.*")
        
        try:
            heartbeat_counter = 0
            while self.running:
                time.sleep(5)  # Heartbeat interval
                heartbeat_counter += 1
                if heartbeat_counter % 12 == 0:  # Log every minute
                    logger.info(f"Service {self.config.name} heartbeat")
        except KeyboardInterrupt:
            logger.info(f"Service {self.config.name} interrupted")
        finally:
            self.running = False
            logger.info(f"Service {self.config.name} stopped")
