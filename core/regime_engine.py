"""
Market Regime Engine v2

Unified module that computes TREND, VOLATILITY, and MARKET STRUCTURE signals
from recent price data and exposes them as RegimeSnapshot objects.

Features:
- Lightweight computation using existing indicator library
- Caching mechanism for performance (< 1s cache)
- Graceful degradation when disabled
- Thread-safe operations
- NEVER throws exceptions
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from core import indicators

logger = logging.getLogger(__name__)


@dataclass
class RegimeSnapshot:
    """
    Snapshot of current market regime for a symbol.
    
    Attributes:
        trend: Trend direction - "up", "down", or "flat"
        volatility: Volatility level - "high", "medium", or "low"
        structure: Market structure - "breakout", "range", "reversal", or "none"
        velocity: Rate of price change (EMA slope)
        atr: Average True Range value
        slope: Normalized slope of trend indicator
        timestamp: When this snapshot was computed
    """
    trend: str
    volatility: str
    structure: str
    velocity: float
    atr: float
    slope: float
    timestamp: datetime


class RegimeEngine:
    """
    Market Regime Engine v2
    
    Computes regime signals from MarketDataEngine price bars and provides
    cached snapshots for strategy consumption.
    
    The engine computes:
    - VOLATILITY: Based on ATR% thresholds (high/medium/low)
    - TREND: Based on EMA slope and price vs EMA (up/down/flat)
    - STRUCTURE: Based on Bollinger Band width and breakouts (breakout/range/reversal/none)
    """
    
    def __init__(
        self,
        config: Dict[str, Any],
        mde: Any,
        logger_instance: Optional[logging.Logger] = None
    ):
        """
        Initialize RegimeEngine.
        
        Args:
            config: Full application config dict
            mde: MarketDataEngine instance (v1 or v2)
            logger_instance: Optional logger instance
        """
        self.logger = logger_instance or logger
        self.mde = mde
        
        # Load regime_engine config with defaults
        regime_config = config.get("regime_engine", {})
        self.enabled = regime_config.get("enabled", True)
        
        if not self.enabled:
            self.logger.info("RegimeEngine: DISABLED (enabled=false in config)")
            return
        
        # Configuration parameters with safe defaults
        self.bar_period = regime_config.get("bar_period", "1m")
        self.slope_period = regime_config.get("slope_period", 20)
        self.atr_period = regime_config.get("atr_period", 14)
        self.volatility_high_pct = regime_config.get("volatility_high_pct", 1.0)
        self.volatility_low_pct = regime_config.get("volatility_low_pct", 0.35)
        self.compression_pct = regime_config.get("compression_pct", 0.25)
        
        # Cache for performance (symbol -> (snapshot, timestamp))
        self._cache: Dict[str, tuple[RegimeSnapshot, float]] = {}
        self._cache_ttl = 1.0  # 1 second cache TTL
        
        self.logger.info(
            "RegimeEngine: ENABLED - bar_period=%s, slope_period=%d, atr_period=%d, "
            "volatility_high_pct=%.2f%%, volatility_low_pct=%.2f%%, compression_pct=%.2f%%",
            self.bar_period,
            self.slope_period,
            self.atr_period,
            self.volatility_high_pct,
            self.volatility_low_pct,
            self.compression_pct,
        )
    
    def _get_price_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Fetch recent price bars from MarketDataEngine.
        
        Args:
            symbol: Symbol to fetch data for
            
        Returns:
            Dict with 'close', 'high', 'low', 'open' lists or None
        """
        try:
            # Try MDE v2 first if available
            if hasattr(self.mde, 'get_candles'):
                candles = self.mde.get_candles(symbol, self.bar_period, limit=100)
                if candles and len(candles) > 0:
                    return {
                        'close': [c.close for c in candles],
                        'high': [c.high for c in candles],
                        'low': [c.low for c in candles],
                        'open': [c.open for c in candles],
                    }
            
            # Fall back to MDE v1 API
            if hasattr(self.mde, 'get_historical_data'):
                df = self.mde.get_historical_data(symbol, interval=self.bar_period)
                if df is not None and len(df) > 0:
                    return {
                        'close': df['close'].tolist(),
                        'high': df['high'].tolist(),
                        'low': df['low'].tolist(),
                        'open': df['open'].tolist(),
                    }
            
            return None
        except Exception as e:
            self.logger.warning("RegimeEngine: Failed to fetch data for %s: %s", symbol, e)
            return None
    
    def _compute_volatility(self, close: list[float], high: list[float], low: list[float]) -> tuple[str, float]:
        """
        Compute volatility regime based on ATR%.
        
        Args:
            close: Close prices
            high: High prices
            low: Low prices
            
        Returns:
            Tuple of (volatility_level, atr_value)
        """
        try:
            if len(close) < self.atr_period + 1:
                return "medium", 0.0
            
            # Calculate ATR
            atr_val = indicators.atr(high, low, close, period=self.atr_period)
            if atr_val <= 0 or close[-1] <= 0:
                return "medium", 0.0
            
            # Calculate ATR as percentage of price
            atr_pct = (atr_val / close[-1]) * 100.0
            
            # Classify volatility
            if atr_pct >= self.volatility_high_pct:
                return "high", atr_val
            elif atr_pct <= self.volatility_low_pct:
                return "low", atr_val
            else:
                return "medium", atr_val
                
        except Exception as e:
            self.logger.debug("RegimeEngine: Volatility computation error: %s", e)
            return "medium", 0.0
    
    def _compute_trend(self, close: list[float]) -> tuple[str, float, float]:
        """
        Compute trend regime based on EMA slope.
        
        Args:
            close: Close prices
            
        Returns:
            Tuple of (trend_direction, velocity, slope)
        """
        try:
            if len(close) < self.slope_period + 5:
                return "flat", 0.0, 0.0
            
            # Calculate EMA for trend following
            ema_values = indicators.ema(close, period=self.slope_period, return_series=True)
            if not ema_values or len(ema_values) < 2:
                return "flat", 0.0, 0.0
            
            # Calculate slope (rate of change) of EMA
            current_ema = ema_values[-1]
            prev_ema = ema_values[-2]
            slope_val = current_ema - prev_ema
            
            # Calculate velocity (normalized slope relative to price)
            velocity = (slope_val / close[-1]) * 100.0 if close[-1] > 0 else 0.0
            
            # Determine trend direction
            # Also check if price is above/below EMA for confirmation
            price_vs_ema = close[-1] - current_ema
            
            if slope_val > 0 and price_vs_ema > 0:
                return "up", velocity, slope_val
            elif slope_val < 0 and price_vs_ema < 0:
                return "down", velocity, slope_val
            else:
                return "flat", velocity, slope_val
                
        except Exception as e:
            self.logger.debug("RegimeEngine: Trend computation error: %s", e)
            return "flat", 0.0, 0.0
    
    def _compute_structure(
        self,
        close: list[float],
        high: list[float],
        low: list[float],
        atr: float
    ) -> str:
        """
        Compute market structure based on Bollinger Bands and price action.
        
        Args:
            close: Close prices
            high: High prices
            low: Low prices
            atr: ATR value for context
            
        Returns:
            Structure type: "breakout", "range", "reversal", or "none"
        """
        try:
            if len(close) < 20:
                return "none"
            
            # Calculate Bollinger Bands
            bb_result = indicators.bollinger_bands(close, period=20, std_dev=2.0)
            if not bb_result or len(bb_result) != 3:
                return "none"
            
            upper, middle, lower = bb_result
            
            # Calculate band width as percentage
            if middle <= 0:
                return "none"
            band_width_pct = ((upper - lower) / middle) * 100.0
            
            # Detect compression (tight bands = potential breakout setup)
            is_compressed = band_width_pct < self.compression_pct
            
            # Check price position relative to bands
            price = close[-1]
            near_upper = (upper - price) < (atr * 0.5) if atr > 0 else False
            near_lower = (price - lower) < (atr * 0.5) if atr > 0 else False
            above_upper = price > upper
            below_lower = price < lower
            
            # Classify structure
            if above_upper or below_lower:
                return "breakout"
            elif is_compressed:
                return "range"
            elif near_upper or near_lower:
                # Price testing bands but not breaking = potential reversal
                return "reversal"
            else:
                return "none"
                
        except Exception as e:
            self.logger.debug("RegimeEngine: Structure computation error: %s", e)
            return "none"
    
    def compute_snapshot(self, symbol: str) -> RegimeSnapshot:
        """
        Compute fresh regime snapshot for symbol.
        
        This method performs the actual computation and is called by snapshot()
        when cache is stale or missing.
        
        Args:
            symbol: Symbol to compute regime for
            
        Returns:
            RegimeSnapshot with current regime data
            
        Note:
            This method NEVER throws exceptions. Returns neutral regime on any error.
        """
        try:
            # If disabled, return neutral regime
            if not self.enabled:
                return RegimeSnapshot(
                    trend="flat",
                    volatility="medium",
                    structure="none",
                    velocity=0.0,
                    atr=0.0,
                    slope=0.0,
                    timestamp=datetime.now(timezone.utc)
                )
            
            # Fetch price data
            data = self._get_price_data(symbol)
            if not data or len(data['close']) < max(self.slope_period, self.atr_period) + 5:
                self.logger.debug("RegimeEngine: Insufficient data for %s, returning neutral regime", symbol)
                return RegimeSnapshot(
                    trend="flat",
                    volatility="medium",
                    structure="none",
                    velocity=0.0,
                    atr=0.0,
                    slope=0.0,
                    timestamp=datetime.now(timezone.utc)
                )
            
            # Compute regime components
            volatility, atr_val = self._compute_volatility(data['close'], data['high'], data['low'])
            trend, velocity, slope_val = self._compute_trend(data['close'])
            structure = self._compute_structure(data['close'], data['high'], data['low'], atr_val)
            
            # Create snapshot
            snapshot = RegimeSnapshot(
                trend=trend,
                volatility=volatility,
                structure=structure,
                velocity=velocity,
                atr=atr_val,
                slope=slope_val,
                timestamp=datetime.now(timezone.utc)
            )
            
            self.logger.debug(
                "RegimeEngine: Computed snapshot for %s: trend=%s, volatility=%s, structure=%s",
                symbol, trend, volatility, structure
            )
            
            return snapshot
            
        except Exception as e:
            # NEVER throw - return neutral regime
            self.logger.error("RegimeEngine: Unexpected error computing snapshot for %s: %s", symbol, e)
            return RegimeSnapshot(
                trend="flat",
                volatility="medium",
                structure="none",
                velocity=0.0,
                atr=0.0,
                slope=0.0,
                timestamp=datetime.now(timezone.utc)
            )
    
    def snapshot(self, symbol: str) -> RegimeSnapshot:
        """
        Get regime snapshot for symbol (cached if recent).
        
        Returns cached snapshot if computed within last 1 second,
        otherwise computes fresh snapshot.
        
        Args:
            symbol: Symbol to get regime snapshot for
            
        Returns:
            RegimeSnapshot with current regime data
            
        Note:
            This method NEVER throws exceptions.
        """
        try:
            current_time = time.time()
            
            # Check cache
            if symbol in self._cache:
                cached_snapshot, cached_time = self._cache[symbol]
                if current_time - cached_time < self._cache_ttl:
                    return cached_snapshot
            
            # Compute fresh snapshot
            snapshot = self.compute_snapshot(symbol)
            
            # Update cache
            self._cache[symbol] = (snapshot, current_time)
            
            return snapshot
            
        except Exception as e:
            # NEVER throw - return neutral regime
            self.logger.error("RegimeEngine: Unexpected error in snapshot() for %s: %s", symbol, e)
            return RegimeSnapshot(
                trend="flat",
                volatility="medium",
                structure="none",
                velocity=0.0,
                atr=0.0,
                slope=0.0,
                timestamp=datetime.now(timezone.utc)
            )
    
    def clear_cache(self, symbol: Optional[str] = None) -> None:
        """
        Clear cached snapshots.
        
        Args:
            symbol: Optional symbol to clear. If None, clears all.
        """
        try:
            if symbol:
                self._cache.pop(symbol, None)
            else:
                self._cache.clear()
        except Exception as e:
            self.logger.warning("RegimeEngine: Error clearing cache: %s", e)
