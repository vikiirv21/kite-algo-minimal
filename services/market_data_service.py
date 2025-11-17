"""
Market Data Service

Wraps broker_feed and market_data_engine with caching and error handling.
Provides clean API for fetching prices, candles, and indicator bundles.

Features:
- get_ltp(symbol) -> float | None
- get_bundle(symbol, tf) -> indicator bundle dict
- get_history(symbol, tf, n) -> list[candles]
- In-memory caching with TTL
- Graceful error handling, zero crashes on None
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from core import indicators
from core.market_data_engine import MarketDataEngine
from data.broker_feed import BrokerFeed

logger = logging.getLogger(__name__)


class MarketDataService:
    """
    Market Data Service providing unified access to prices and candles.
    
    Wraps broker_feed.get_ltp and market_data_engine with caching layer.
    All methods are safe and return None on errors instead of crashing.
    """
    
    def __init__(
        self,
        broker_feed: Optional[BrokerFeed] = None,
        market_data_engine: Optional[MarketDataEngine] = None,
        cache_ttl_seconds: float = 1.0,
    ):
        """
        Initialize Market Data Service.
        
        Args:
            broker_feed: BrokerFeed instance for LTP data
            market_data_engine: MarketDataEngine for historical candles
            cache_ttl_seconds: Time-to-live for cached data in seconds
        """
        self.broker_feed = broker_feed
        self.mde = market_data_engine
        self.cache_ttl = cache_ttl_seconds
        
        # Cache structure: {(symbol, key): (timestamp, value)}
        self._cache: Dict[tuple, tuple[float, Any]] = {}
        
        logger.info(
            "MarketDataService initialized (cache_ttl=%.2fs)",
            cache_ttl_seconds
        )
    
    def get_ltp(self, symbol: str, exchange: str = "NSE") -> Optional[float]:
        """
        Get last traded price for a symbol.
        
        Args:
            symbol: Trading symbol
            exchange: Exchange name (default: NSE)
            
        Returns:
            Last traded price, or None if unavailable
        """
        cache_key = (symbol, f"ltp_{exchange}")
        
        # Check cache first
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached
        
        # Fetch from broker feed
        if not self.broker_feed:
            logger.debug("No broker_feed available for get_ltp(%s)", symbol)
            return None
        
        try:
            ltp = self.broker_feed.get_ltp(symbol, exchange)
            if ltp is not None:
                self._set_cached(cache_key, ltp)
            return ltp
        except Exception as exc:
            logger.warning("Error fetching LTP for %s: %s", symbol, exc)
            return None
    
    def get_bundle(
        self, 
        symbol: str, 
        timeframe: str = "5m"
    ) -> Optional[Dict[str, Any]]:
        """
        Get indicator bundle for a symbol and timeframe.
        
        Returns dict with:
        - ema20, ema50, rsi, atr, vwap
        - last_candle
        - slope, trend_signal
        
        Args:
            symbol: Trading symbol
            timeframe: Timeframe (e.g., "5m", "15m")
            
        Returns:
            Indicator bundle dict, or None if data unavailable
        """
        cache_key = (symbol, f"bundle_{timeframe}")
        
        # Check cache
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached
        
        # Fetch candles and compute indicators
        if not self.mde:
            logger.debug("No market_data_engine available for get_bundle(%s)", symbol)
            return None
        
        try:
            # Get sufficient history for indicators
            candles = self.mde.get_latest_window(symbol, timeframe, window_size=100)
            if not candles or len(candles) < 20:
                logger.debug(
                    "Insufficient candles for %s/%s: got %d",
                    symbol, timeframe, len(candles) if candles else 0
                )
                return None
            
            # Extract close prices and volumes
            closes = [float(c.get("close", 0)) for c in candles]
            highs = [float(c.get("high", 0)) for c in candles]
            lows = [float(c.get("low", 0)) for c in candles]
            volumes = [float(c.get("volume", 0)) for c in candles]
            
            # Compute indicators
            bundle = {
                "symbol": symbol,
                "timeframe": timeframe,
                "last_candle": candles[-1] if candles else None,
                "ema20": indicators.ema(closes, 20)[-1] if len(closes) >= 20 else None,
                "ema50": indicators.ema(closes, 50)[-1] if len(closes) >= 50 else None,
                "rsi": indicators.rsi(closes, 14)[-1] if len(closes) >= 14 else None,
                "atr": indicators.atr(highs, lows, closes, 14)[-1] if len(closes) >= 14 else None,
                "vwap": indicators.vwap(highs, lows, closes, volumes)[-1] if closes else None,
            }
            
            # Add trend signals
            if bundle["ema20"] and bundle["ema50"]:
                bundle["slope"] = bundle["ema20"] - bundle["ema50"]
                bundle["trend_signal"] = "bullish" if bundle["slope"] > 0 else "bearish"
            else:
                bundle["slope"] = None
                bundle["trend_signal"] = "neutral"
            
            self._set_cached(cache_key, bundle)
            return bundle
            
        except Exception as exc:
            logger.warning(
                "Error computing bundle for %s/%s: %s",
                symbol, timeframe, exc,
                exc_info=True
            )
            return None
    
    def get_history(
        self,
        symbol: str,
        timeframe: str = "5m",
        n: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get historical candles for a symbol.
        
        Args:
            symbol: Trading symbol
            timeframe: Timeframe (e.g., "5m", "15m")
            n: Number of candles to return
            
        Returns:
            List of candle dicts (empty list if unavailable)
        """
        if not self.mde:
            logger.debug("No market_data_engine available for get_history(%s)", symbol)
            return []
        
        try:
            candles = self.mde.get_latest_window(symbol, timeframe, window_size=n)
            return candles if candles else []
        except Exception as exc:
            logger.warning(
                "Error fetching history for %s/%s: %s",
                symbol, timeframe, exc
            )
            return []
    
    def get_last_candle(
        self,
        symbol: str,
        timeframe: str = "5m"
    ) -> Optional[Dict[str, Any]]:
        """
        Get the most recent candle for a symbol.
        
        Args:
            symbol: Trading symbol
            timeframe: Timeframe
            
        Returns:
            Last candle dict, or None if unavailable
        """
        if not self.mde:
            return None
        
        try:
            candles = self.mde.get_latest_window(symbol, timeframe, window_size=1)
            return candles[-1] if candles else None
        except Exception as exc:
            logger.warning(
                "Error fetching last candle for %s/%s: %s",
                symbol, timeframe, exc
            )
            return None
    
    def _get_cached(self, key: tuple) -> Optional[Any]:
        """Get value from cache if not expired."""
        if key not in self._cache:
            return None
        
        timestamp, value = self._cache[key]
        if time.time() - timestamp > self.cache_ttl:
            # Expired
            del self._cache[key]
            return None
        
        return value
    
    def _set_cached(self, key: tuple, value: Any) -> None:
        """Set value in cache with current timestamp."""
        self._cache[key] = (time.time(), value)
    
    def clear_cache(self) -> None:
        """Clear all cached data."""
        self._cache.clear()
        logger.debug("MarketDataService cache cleared")
