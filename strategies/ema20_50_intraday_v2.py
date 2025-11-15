"""
EMA 20/50 Intraday Strategy - Version 2

Modern implementation using Strategy Engine v2 architecture.
Uses pre-computed indicators instead of maintaining internal state.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional

from core.strategy_engine_v2 import BaseStrategy, StrategyState
from strategies.base import Decision


class EMA2050IntradayV2(BaseStrategy):
    """
    EMA Crossover Strategy for Intraday Trading - Version 2
    
    Strategy Logic:
    - BUY when EMA20 crosses above EMA50 and trend is up
    - SELL when EMA20 crosses below EMA50 and trend is down
    - Exit on opposite signal
    
    Uses pre-computed indicators from Strategy Engine v2.
    """
    
    def __init__(self, config: Dict[str, Any], strategy_state: StrategyState):
        super().__init__(config, strategy_state)
        self.name = "ema20_50_intraday_v2"
        
        # Strategy parameters
        self.ema_fast = config.get("ema_fast", 20)
        self.ema_slow = config.get("ema_slow", 50)
        self.use_regime_filter = config.get("use_regime_filter", True)
        self.min_confidence = config.get("min_confidence", 0.0)
        
        # Track previous state for crossover detection
        self._prev_state: Dict[str, Dict[str, Any]] = {}
    
    def generate_signal(
        self,
        candle: Dict[str, float],
        series: Dict[str, List[float]],
        indicators: Dict[str, Any]
    ) -> Optional[Decision]:
        """
        Generate trading signal based on EMA crossover.
        
        Args:
            candle: Current candle with open, high, low, close, volume
            series: Historical series (close, high, low, etc.)
            indicators: Pre-computed indicators (ema20, ema50, trend, rsi14, etc.)
        
        Returns:
            Decision object (BUY, SELL, EXIT, or HOLD)
        """
        close = candle.get("close", 0.0)
        if close <= 0:
            return Decision(action="HOLD", reason="invalid_price", confidence=0.0)
        
        # Check if we have required indicators
        ema_fast_val = indicators.get(f"ema{self.ema_fast}")
        ema_slow_val = indicators.get(f"ema{self.ema_slow}")
        
        if ema_fast_val is None or ema_slow_val is None:
            return Decision(action="HOLD", reason="missing_indicators", confidence=0.0)
        
        # Get symbol from metadata if available
        symbol = self.config.get("current_symbol", "UNKNOWN")
        
        # Determine current state
        fast_above_slow = ema_fast_val > ema_slow_val
        fast_below_slow = ema_fast_val < ema_slow_val
        
        # Get previous state for crossover detection
        prev_state = self._prev_state.get(symbol, {})
        prev_fast_above = prev_state.get("fast_above_slow", fast_above_slow)
        
        # Update state
        self._prev_state[symbol] = {
            "fast_above_slow": fast_above_slow,
            "ema_fast": ema_fast_val,
            "ema_slow": ema_slow_val,
        }
        
        # Check for regime filter
        if self.use_regime_filter:
            trend = indicators.get("trend", "unknown")
            ema200 = indicators.get("ema200")
            
            # Only trade in direction of higher timeframe trend
            if ema200 and close < ema200 * 0.995:
                # Below 200 EMA, only consider shorts
                if fast_above_slow:
                    return Decision(action="HOLD", reason="below_200ema_no_longs", confidence=0.0)
            elif ema200 and close > ema200 * 1.005:
                # Above 200 EMA, only consider longs
                if fast_below_slow:
                    return Decision(action="HOLD", reason="above_200ema_no_shorts", confidence=0.0)
        
        # Detect crossovers
        bullish_cross = not prev_fast_above and fast_above_slow
        bearish_cross = prev_fast_above and fast_below_slow
        
        # Calculate confidence based on separation
        confidence = self._calculate_confidence(ema_fast_val, ema_slow_val, indicators)
        
        if confidence < self.min_confidence:
            return Decision(action="HOLD", reason="low_confidence", confidence=confidence)
        
        # Check current position
        has_long = self.position_is_long(symbol)
        has_short = self.position_is_short(symbol)
        
        # Generate signals
        if bullish_cross:
            if has_short:
                # Exit short and go long
                return Decision(action="EXIT", reason="bearish_to_bullish_cross", confidence=confidence)
            elif not has_long:
                # Enter long
                reason = self._build_reason("bullish_cross", indicators)
                return Decision(action="BUY", reason=reason, confidence=confidence)
        
        elif bearish_cross:
            if has_long:
                # Exit long and go short
                return Decision(action="EXIT", reason="bullish_to_bearish_cross", confidence=confidence)
            elif not has_short:
                # Enter short
                reason = self._build_reason("bearish_cross", indicators)
                return Decision(action="SELL", reason=reason, confidence=confidence)
        
        # Check exit conditions (RSI extremes)
        rsi = indicators.get("rsi14")
        if rsi:
            if has_long and rsi > 75:
                return Decision(action="EXIT", reason="rsi_overbought", confidence=confidence)
            if has_short and rsi < 25:
                return Decision(action="EXIT", reason="rsi_oversold", confidence=confidence)
        
        return Decision(action="HOLD", reason="no_signal", confidence=confidence)
    
    def _calculate_confidence(
        self,
        ema_fast: float,
        ema_slow: float,
        indicators: Dict[str, Any]
    ) -> float:
        """
        Calculate confidence score based on indicator alignment.
        
        Returns:
            Confidence score between 0.0 and 1.0
        """
        # Base confidence from EMA separation
        if ema_slow > 0:
            separation = abs(ema_fast - ema_slow) / ema_slow
        else:
            separation = 0.0
        
        base_confidence = min(separation * 20, 0.5)  # Max 0.5 from separation
        
        # Boost if other indicators align
        boost = 0.0
        
        # RSI alignment
        rsi = indicators.get("rsi14")
        if rsi:
            if ema_fast > ema_slow and 40 < rsi < 70:
                boost += 0.15
            elif ema_fast < ema_slow and 30 < rsi < 60:
                boost += 0.15
        
        # Trend alignment
        trend = indicators.get("trend")
        if trend:
            if (ema_fast > ema_slow and trend == "up") or (ema_fast < ema_slow and trend == "down"):
                boost += 0.15
        
        # SuperTrend alignment
        st_direction = indicators.get("supertrend_direction")
        if st_direction:
            if (ema_fast > ema_slow and st_direction == 1) or (ema_fast < ema_slow and st_direction == -1):
                boost += 0.20
        
        return min(base_confidence + boost, 1.0)
    
    def _build_reason(self, signal_type: str, indicators: Dict[str, Any]) -> str:
        """Build descriptive reason string for the signal."""
        parts = [signal_type]
        
        # Add trend info
        trend = indicators.get("trend")
        if trend:
            parts.append(f"trend:{trend}")
        
        # Add RSI info
        rsi = indicators.get("rsi14")
        if rsi:
            if rsi > 70:
                parts.append("rsi:overbought")
            elif rsi < 30:
                parts.append("rsi:oversold")
            else:
                parts.append(f"rsi:{int(rsi)}")
        
        # Add volatility info
        atr = indicators.get("atr14")
        if atr:
            parts.append(f"atr:{atr:.2f}")
        
        return "|".join(parts)


# Factory function for easy instantiation
def create_ema20_50_intraday_v2(config: Dict[str, Any], state: StrategyState) -> EMA2050IntradayV2:
    """Create an instance of EMA 20/50 Intraday Strategy v2."""
    return EMA2050IntradayV2(config, state)
