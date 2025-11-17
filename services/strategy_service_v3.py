"""
Strategy Service v3

Integrates StrategyEngineV3 with market data and event publishing.
Provides high-level interface for running multi-strategy evaluation.

Features:
- run_symbol(symbol, ts) - Fetch data, run strategies, publish signals
- Multi-timeframe evaluation (primary + secondary)
- Signal fusion and confidence scoring
- EventBus integration for raw and fused signals
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from core.strategy_engine_v2 import OrderIntent
from core.strategy_engine_v3 import StrategyEngineV3
from services.event_bus import EventBus
from services.market_data_service import MarketDataService

logger = logging.getLogger(__name__)


class StrategyService:
    """
    Strategy Service integrating StrategyEngineV3 with data fetching.
    
    Handles:
    - Market data fetching for primary and secondary timeframes
    - Strategy evaluation and signal fusion
    - Event publishing for monitoring
    """
    
    def __init__(
        self,
        strategy_engine: StrategyEngineV3,
        market_data_service: MarketDataService,
        event_bus: Optional[EventBus] = None,
        primary_tf: str = "5m",
        secondary_tf: str = "15m",
    ):
        """
        Initialize Strategy Service.
        
        Args:
            strategy_engine: StrategyEngineV3 instance
            market_data_service: MarketDataService for data fetching
            event_bus: EventBus for signal publishing
            primary_tf: Primary timeframe for signals
            secondary_tf: Secondary timeframe for confirmation
        """
        self.engine = strategy_engine
        self.mds = market_data_service
        self.bus = event_bus
        self.primary_tf = primary_tf
        self.secondary_tf = secondary_tf
        
        logger.info(
            "StrategyService initialized (primary=%s, secondary=%s)",
            primary_tf,
            secondary_tf
        )
    
    def run_symbol(
        self,
        symbol: str,
        ts: Optional[str] = None,
    ) -> OrderIntent:
        """
        Run strategy evaluation for a symbol.
        
        Steps:
        1. Fetch current price (LTP)
        2. Fetch indicator bundles for primary and secondary timeframes
        3. Run strategies via StrategyEngineV3
        4. Publish raw and fused signals to EventBus
        5. Return final fused OrderIntent
        
        Args:
            symbol: Trading symbol
            ts: Timestamp (ISO format, defaults to now)
            
        Returns:
            OrderIntent with action (BUY/SELL/HOLD) and metadata
        """
        # Default timestamp to now
        if ts is None:
            ts = datetime.now(timezone.utc).isoformat()
        
        # Step 1: Fetch current price
        price = self.mds.get_ltp(symbol)
        if price is None:
            logger.debug("No LTP available for %s, returning HOLD", symbol)
            return self._hold_intent(symbol, "No price data", ts)
        
        # Step 2: Fetch indicator bundles
        try:
            primary_bundle = self.mds.get_bundle(symbol, self.primary_tf)
            secondary_bundle = self.mds.get_bundle(symbol, self.secondary_tf)
        except Exception as exc:
            logger.warning(
                "Error fetching bundles for %s: %s",
                symbol, exc,
                exc_info=True
            )
            return self._hold_intent(symbol, f"Data fetch error: {exc}", ts)
        
        if not primary_bundle:
            logger.debug(
                "No primary bundle available for %s/%s, returning HOLD",
                symbol, self.primary_tf
            )
            return self._hold_intent(symbol, "No primary timeframe data", ts)
        
        # Step 3: Build market data dict for StrategyEngineV3
        md = self._build_market_data(primary_bundle, secondary_bundle)
        
        # Step 4: Run strategy evaluation
        try:
            intent = self.engine.evaluate(symbol, ts, price, md)
        except Exception as exc:
            logger.error(
                "Strategy evaluation failed for %s: %s",
                symbol, exc,
                exc_info=True
            )
            return self._hold_intent(symbol, f"Strategy error: {exc}", ts)
        
        # Step 5: Publish signals to EventBus
        if self.bus:
            try:
                # Publish raw signals (candidates before fusion)
                self.bus.publish("signals.raw", {
                    "symbol": symbol,
                    "ts": ts,
                    "price": price,
                    "primary_tf": self.primary_tf,
                    "secondary_tf": self.secondary_tf,
                })
                
                # Publish fused signal
                self.bus.publish("signals.fused", {
                    "symbol": symbol,
                    "ts": ts,
                    "price": price,
                    "action": intent.action,
                    "confidence": intent.confidence,
                    "reason": intent.reason,
                    "strategy_code": intent.strategy_code,
                })
            except Exception as exc:
                logger.debug("Error publishing signals: %s", exc)
        
        return intent
    
    def _build_market_data(
        self,
        primary_bundle: Optional[Dict[str, Any]],
        secondary_bundle: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Build market data dictionary for StrategyEngineV3.
        
        Args:
            primary_bundle: Primary timeframe indicator bundle
            secondary_bundle: Secondary timeframe indicator bundle
            
        Returns:
            Market data dict with series for both timeframes
        """
        md: Dict[str, Any] = {}
        
        # Add primary series
        if primary_bundle:
            last_candle = primary_bundle.get("last_candle", {})
            md["primary_series"] = {
                "close": [float(last_candle.get("close", 0))],
                "high": [float(last_candle.get("high", 0))],
                "low": [float(last_candle.get("low", 0))],
                "open": [float(last_candle.get("open", 0))],
                "volume": [float(last_candle.get("volume", 0))],
            }
            
            # Copy indicators to bundle
            md["primary_bundle"] = primary_bundle
        
        # Add secondary series
        if secondary_bundle:
            last_candle = secondary_bundle.get("last_candle", {})
            md["secondary_series"] = {
                "close": [float(last_candle.get("close", 0))],
                "high": [float(last_candle.get("high", 0))],
                "low": [float(last_candle.get("low", 0))],
                "open": [float(last_candle.get("open", 0))],
                "volume": [float(last_candle.get("volume", 0))],
            }
            
            # Copy indicators to bundle
            md["secondary_bundle"] = secondary_bundle
        
        return md
    
    def _hold_intent(self, symbol: str, reason: str, ts: str) -> OrderIntent:
        """
        Create a HOLD OrderIntent with reason.
        
        Args:
            symbol: Trading symbol
            reason: Reason for holding
            ts: Timestamp
            
        Returns:
            OrderIntent with HOLD action
        """
        return OrderIntent(
            symbol=symbol,
            action="HOLD",
            qty=0,
            reason=reason,
            strategy_code="strategy_service_v3",
            confidence=0.0,
            metadata={"ts": ts}
        )
