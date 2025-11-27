"""
Price Action Strategy - Version 1

A placeholder/template strategy that demonstrates HTF (Higher Timeframe)
filter integration. This strategy can be extended with actual price action
logic in the future.

Currently implements basic price action concepts:
- Swing high/low detection
- Support/resistance levels
- Candlestick pattern recognition (simplified)
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional

from core.strategy_engine_v2 import BaseStrategy, StrategyState
from strategies.base import Decision


class PriceActionV1(BaseStrategy):
    """
    Price Action Strategy - Version 1
    
    Strategy Logic:
    - Detects price action patterns (swing highs/lows, breakouts)
    - Uses candlestick analysis for entry signals
    - Supports HTF (Higher Timeframe) trend filter for improved accuracy
    
    Uses pre-computed indicators from Strategy Engine v2.
    """
    
    def __init__(self, config: Dict[str, Any], strategy_state: StrategyState):
        super().__init__(config, strategy_state)
        self.name = "price_action_v1"
        
        # Strategy parameters
        self.lookback_bars = config.get("lookback_bars", 10)
        self.breakout_threshold = config.get("breakout_threshold", 0.002)  # 0.2%
        self.use_regime_filter = config.get("use_regime_filter", True)
        self.min_confidence = config.get("min_confidence", 0.5)
        
        # HTF filter parameters
        self.use_htf_filter = config.get("use_htf_filter", False)
        self.htf_min_score = config.get("htf_min_score", 0.6)
        self.htf_conflict_action = config.get("htf_conflict_action", "suppress")
        self.htf_confidence_reduction = config.get("htf_confidence_reduction", 0.3)
        
        # Track swing points
        self._swing_highs: Dict[str, List[float]] = {}
        self._swing_lows: Dict[str, List[float]] = {}
    
    def generate_signal(
        self,
        candle: Dict[str, float],
        series: Dict[str, List[float]],
        indicators: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Optional[Decision]:
        """
        Generate trading signal based on price action analysis.
        
        Args:
            candle: Current candle with open, high, low, close, volume
            series: Historical series (close, high, low, etc.)
            indicators: Pre-computed indicators
            context: Optional context dict with expiry info, session time, htf_trend etc.
        
        Returns:
            Decision object (BUY, SELL, EXIT, or HOLD)
        """
        context = context or {}
        
        close = candle.get("close", 0.0)
        high = candle.get("high", 0.0)
        low = candle.get("low", 0.0)
        open_price = candle.get("open", 0.0)
        
        if close <= 0:
            return Decision(action="HOLD", reason="invalid_price", confidence=0.0)
        
        # Get symbol from config
        symbol = self.config.get("current_symbol", "UNKNOWN")
        
        # Get historical prices
        close_series = series.get("close", [])
        high_series = series.get("high", [])
        low_series = series.get("low", [])
        
        if len(close_series) < self.lookback_bars:
            return Decision(action="HOLD", reason="insufficient_data", confidence=0.0)
        
        # Detect basic price action patterns
        signal = None
        confidence = 0.0
        reason = ""
        
        # Check for bullish breakout
        recent_high = max(high_series[-self.lookback_bars:-1]) if len(high_series) > self.lookback_bars else 0
        if recent_high > 0 and close > recent_high * (1 + self.breakout_threshold):
            signal = "BUY"
            confidence = 0.65
            reason = "bullish_breakout"
        
        # Check for bearish breakdown
        recent_low = min(low_series[-self.lookback_bars:-1]) if len(low_series) > self.lookback_bars else float('inf')
        if recent_low < float('inf') and close < recent_low * (1 - self.breakout_threshold):
            signal = "SELL"
            confidence = 0.65
            reason = "bearish_breakdown"
        
        # Check for bullish engulfing candle pattern
        if signal is None and len(close_series) >= 2:
            prev_close = close_series[-2]
            prev_open = close_series[-2]  # Simplified - would need actual open series
            
            # Bullish engulfing: current close > current open, current body > previous body
            if close > open_price and (close - open_price) > abs(prev_close - prev_open) * 1.5:
                ema20 = indicators.get("ema20")
                if ema20 and close > ema20:
                    signal = "BUY"
                    confidence = 0.55
                    reason = "bullish_engulfing"
        
        # Check for bearish engulfing candle pattern
        if signal is None and len(close_series) >= 2:
            prev_close = close_series[-2]
            prev_open = close_series[-2]
            
            # Bearish engulfing: current close < current open, current body > previous body
            if close < open_price and (open_price - close) > abs(prev_close - prev_open) * 1.5:
                ema20 = indicators.get("ema20")
                if ema20 and close < ema20:
                    signal = "SELL"
                    confidence = 0.55
                    reason = "bearish_engulfing"
        
        # Apply regime filter if enabled
        if signal and self.use_regime_filter:
            trend = indicators.get("trend", "unknown")
            if signal == "BUY" and trend == "down":
                confidence *= 0.7  # Reduce confidence for counter-trend
                reason = f"{reason}|counter_trend"
            elif signal == "SELL" and trend == "up":
                confidence *= 0.7
                reason = f"{reason}|counter_trend"
        
        # Check minimum confidence
        if confidence < self.min_confidence:
            signal = None
        
        # Apply HTF filter if enabled and we have a signal
        if signal in ["BUY", "SELL"] and self.use_htf_filter:
            htf_context = context.get("htf_trend")
            if htf_context:
                htf_filter_result = self._apply_htf_filter(signal, confidence, htf_context)
                if htf_filter_result:
                    if htf_filter_result.action == "HOLD":
                        return htf_filter_result
                    else:
                        confidence = htf_filter_result.confidence
                        reason = f"{reason}|{htf_filter_result.reason}"
        
        # Return final decision
        if signal:
            return Decision(action=signal, reason=reason, confidence=confidence)
        else:
            return Decision(action="HOLD", reason="no_pattern", confidence=0.0)
    
    def _apply_htf_filter(
        self,
        signal: str,
        confidence: float,
        htf_context: Dict[str, Any],
    ) -> Optional[Decision]:
        """
        Apply Higher Timeframe (HTF) trend filter to proposed entry signal.
        
        Args:
            signal: "BUY" or "SELL"
            confidence: Signal confidence (0-1)
            htf_context: HTF trend context dict
        
        Returns:
            Decision to modify/block entry or None to allow
        """
        if not htf_context:
            return None
        
        htf_bias = htf_context.get("htf_bias", "sideways")
        htf_score = htf_context.get("score", 0.0)
        htf_aligned = htf_context.get("aligned", False)
        
        # Check for conflict
        is_conflicting = False
        conflict_reason = ""
        
        if signal in ["BUY", "LONG"]:
            if htf_bias == "bearish":
                is_conflicting = True
                conflict_reason = "htf_bearish_conflicts_long"
        elif signal in ["SELL", "SHORT"]:
            if htf_bias == "bullish":
                is_conflicting = True
                conflict_reason = "htf_bullish_conflicts_short"
        
        if is_conflicting:
            if self.htf_conflict_action == "suppress":
                return Decision(action="HOLD", reason=conflict_reason, confidence=0.0)
            else:
                reduced_confidence = confidence * (1.0 - self.htf_confidence_reduction)
                return Decision(
                    action=signal,
                    reason=f"htf_conflict_reduced|{conflict_reason}",
                    confidence=reduced_confidence
                )
        
        # Sideways - slight reduction
        if htf_bias == "sideways":
            reduced_confidence = confidence * 0.9
            return Decision(
                action=signal,
                reason="htf_sideways_caution",
                confidence=reduced_confidence
            )
        
        # Aligned - boost confidence
        if htf_aligned and htf_score >= self.htf_min_score:
            boosted_confidence = min(1.0, confidence * 1.05)
            return Decision(
                action=signal,
                reason="htf_aligned_boost",
                confidence=boosted_confidence
            )
        
        return None


# Factory function for easy instantiation
def create_price_action_v1(config: Dict[str, Any], state: StrategyState) -> PriceActionV1:
    """Create an instance of Price Action Strategy v1."""
    return PriceActionV1(config, state)
