"""
Price Action Intraday Strategy - Version 1

Multi-factor strategy using:
- EMA 20/50 trend filter
- Candlestick pattern detection (hammer, pinbar, engulfing)
- Volume spike confirmation
- ATR volatility mode filter

This strategy co-exists with EMA_20_50 and uses the Strategy Engine v2 architecture.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional

from core.strategy_engine_v2 import BaseStrategy, StrategyState
from strategies.base import Decision


class PriceActionIntradayV1(BaseStrategy):
    """
    Price Action Intraday Strategy - Version 1
    
    Strategy Logic:
    - Use EMA 20/50 to determine trend bias:
      - Only LONG entries when EMA20 > EMA50 (uptrend)
      - Only SHORT entries when EMA20 < EMA50 (downtrend)
    - Confirm entries with:
      - Candlestick patterns (hammer, pinbar, engulfing) in direction of trend
      - Volume spike (volume > factor * rolling mean)
      - ATR volatility mode != "compressing" (avoid low-vol chop)
    - Emit signals:
      - signal = "BUY" / "SELL" / "FLAT"
      - confidence (0-1 range) increased when candle + volume + ATR all align
    
    Uses pre-computed indicators from Strategy Engine v2.
    """
    
    def __init__(self, config: Dict[str, Any], strategy_state: StrategyState):
        super().__init__(config, strategy_state)
        self.name = "price_action_intraday_v1"
        
        # Strategy parameters (from config or defaults)
        self.timeframe = config.get("timeframe", "5m")
        self.role = config.get("role", "intraday")
        
        # EMA parameters
        self.ema_fast = config.get("ema_fast", 20)
        self.ema_slow = config.get("ema_slow", 50)
        
        # Volume spike parameters
        self.volume_spike_factor = config.get("volume_spike_factor", 1.5)
        self.volume_window = config.get("volume_window", 20)
        
        # ATR parameters
        self.atr_period = config.get("atr_period", 14)
        self.atr_expand_factor = config.get("atr_expand_factor", 1.2)
        self.atr_compress_factor = config.get("atr_compress_factor", 0.8)
        
        # Pattern parameters
        self.enable_patterns = config.get("enable_patterns", True)
        self.body_ratio_threshold = config.get("body_ratio_threshold", 0.30)
        self.wick_ratio_threshold = config.get("wick_ratio_threshold", 2.0)
        
        # Confidence thresholds
        self.min_confidence_to_trade = config.get("min_confidence_to_trade", 0.6)
        
        # Track previous state for crossover detection
        self._prev_state: Dict[str, Dict[str, Any]] = {}
    
    def generate_signal(
        self,
        candle: Dict[str, float],
        series: Dict[str, List[float]],
        indicators: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Optional[Decision]:
        """
        Generate trading signal based on price action confluence.
        
        Args:
            candle: Current candle with open, high, low, close, volume
            series: Historical series (close, high, low, open, volume lists)
            indicators: Pre-computed indicators (ema20, ema50, atr14, etc.)
            context: Optional context dict with expiry info, session time, etc.
        
        Returns:
            Decision object (BUY, SELL, EXIT, or HOLD)
        """
        context = context or {}
        
        # Validate candle data
        close = candle.get("close", 0.0)
        if close <= 0:
            return Decision(action="HOLD", reason="invalid_price", confidence=0.0)
        
        # Get symbol from metadata
        symbol = self.config.get("current_symbol", "UNKNOWN")
        
        # Check if we have required indicators
        ema_fast_val = indicators.get(f"ema{self.ema_fast}")
        ema_slow_val = indicators.get(f"ema{self.ema_slow}")
        
        if ema_fast_val is None or ema_slow_val is None:
            return Decision(action="HOLD", reason="missing_ema_indicators", confidence=0.0)
        
        # Determine trend direction
        is_uptrend = ema_fast_val > ema_slow_val
        is_downtrend = ema_fast_val < ema_slow_val
        
        # Detect EMA crossover
        prev_state = self._prev_state.get(symbol, {})
        prev_fast_above = prev_state.get("fast_above_slow", is_uptrend)
        
        # Update state
        self._prev_state[symbol] = {
            "fast_above_slow": is_uptrend,
            "ema_fast": ema_fast_val,
            "ema_slow": ema_slow_val,
        }
        
        bullish_cross = not prev_fast_above and is_uptrend
        bearish_cross = prev_fast_above and is_downtrend
        
        # Build signal components
        signal_components = self._analyze_signal_components(
            candle, series, indicators
        )
        
        # Calculate confidence
        confidence = self._calculate_confidence(
            signal_components, indicators, is_uptrend
        )
        
        # Check if confidence meets minimum threshold
        if confidence < self.min_confidence_to_trade:
            return Decision(
                action="HOLD",
                reason=f"low_confidence:{confidence:.2f}",
                confidence=confidence
            )
        
        # Check current position
        has_long = self.position_is_long(symbol)
        has_short = self.position_is_short(symbol)
        
        # Generate signal based on confluence
        signal = None
        reason_parts = []
        
        # Bullish signal conditions
        if is_uptrend and (
            bullish_cross or signal_components["bullish_pattern"]
        ):
            if signal_components["volume_spike"]:
                reason_parts.append("volume_spike")
            if signal_components["bullish_pattern"]:
                reason_parts.append(f"pattern:{signal_components['pattern_type']}")
            if not signal_components["is_compressing"]:
                reason_parts.append("vol_ok")
            
            if has_short:
                signal = "EXIT"
                reason_parts.insert(0, "exit_short")
            elif not has_long:
                signal = "BUY"
                reason_parts.insert(0, "bullish_confluence")
        
        # Bearish signal conditions
        elif is_downtrend and (
            bearish_cross or signal_components["bearish_pattern"]
        ):
            if signal_components["volume_spike"]:
                reason_parts.append("volume_spike")
            if signal_components["bearish_pattern"]:
                reason_parts.append(f"pattern:{signal_components['pattern_type']}")
            if not signal_components["is_compressing"]:
                reason_parts.append("vol_ok")
            
            if has_long:
                signal = "EXIT"
                reason_parts.insert(0, "exit_long")
            elif not has_short:
                signal = "SELL"
                reason_parts.insert(0, "bearish_confluence")
        
        # Check exit conditions (RSI extremes)
        rsi = indicators.get("rsi14")
        if rsi and not signal:
            if has_long and rsi > 75:
                signal = "EXIT"
                reason_parts = ["rsi_overbought"]
            elif has_short and rsi < 25:
                signal = "EXIT"
                reason_parts = ["rsi_oversold"]
        
        # Apply context adjustments
        if signal in ["BUY", "SELL"] and context:
            is_expiry_day = context.get("is_expiry_day", False)
            time_to_expiry_minutes = context.get("time_to_expiry_minutes")
            
            if is_expiry_day and time_to_expiry_minutes is not None:
                if time_to_expiry_minutes < 60:
                    confidence = confidence * 0.9
                    reason_parts.append("expiry_caution")
        
        # Build reason string
        reason = "|".join(reason_parts) if reason_parts else "no_signal"
        
        # Add indicator values to reason for debugging
        if signal:
            reason += f"|ema20:{ema_fast_val:.2f}|ema50:{ema_slow_val:.2f}"
        
        # Return final decision
        if signal:
            return Decision(action=signal, reason=reason, confidence=confidence)
        else:
            return Decision(action="HOLD", reason=reason, confidence=confidence)
    
    def _analyze_signal_components(
        self,
        candle: Dict[str, float],
        series: Dict[str, List[float]],
        indicators: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Analyze individual signal components.
        
        Returns dict with:
        - bullish_pattern: bool
        - bearish_pattern: bool
        - pattern_type: str (hammer/pinbar/engulfing/none)
        - volume_spike: bool
        - is_compressing: bool (ATR volatility mode)
        - volatility_mode: str (expanding/normal/compressing)
        """
        components = {
            "bullish_pattern": False,
            "bearish_pattern": False,
            "pattern_type": "none",
            "volume_spike": False,
            "is_compressing": False,
            "volatility_mode": "normal",
        }
        
        # Detect candle patterns if enabled
        if self.enable_patterns:
            pattern_result = self._detect_patterns(candle, series)
            components.update(pattern_result)
        
        # Detect volume spike
        components["volume_spike"] = self._detect_volume_spike(candle, series)
        
        # Detect ATR volatility mode
        volatility_result = self._detect_volatility_mode(series, indicators)
        components["volatility_mode"] = volatility_result
        components["is_compressing"] = volatility_result == "compressing"
        
        return components
    
    def _detect_patterns(
        self,
        candle: Dict[str, float],
        series: Dict[str, List[float]]
    ) -> Dict[str, Any]:
        """
        Detect candlestick patterns on current candle.
        
        Returns dict with pattern detection results.
        """
        result = {
            "bullish_pattern": False,
            "bearish_pattern": False,
            "pattern_type": "none",
        }
        
        open_price = candle.get("open", 0.0)
        high = candle.get("high", 0.0)
        low = candle.get("low", 0.0)
        close = candle.get("close", 0.0)
        
        if open_price <= 0 or high <= 0 or low <= 0 or close <= 0:
            return result
        
        # Calculate body and wick sizes
        body = abs(close - open_price)
        candle_range = high - low
        
        if candle_range <= 0:
            return result
        
        body_bottom = min(open_price, close)
        body_top = max(open_price, close)
        lower_shadow = body_bottom - low
        upper_shadow = high - body_top
        
        # Body ratio
        body_ratio = body / candle_range
        
        # Detect hammer (bullish reversal) - long lower wick
        if (body_ratio <= self.body_ratio_threshold and
            body > 0 and
            lower_shadow >= self.wick_ratio_threshold * body and
            upper_shadow <= body):
            result["bullish_pattern"] = True
            result["pattern_type"] = "hammer"
            return result
        
        # Detect inverted hammer (potential bullish) - long upper wick
        if (body_ratio <= self.body_ratio_threshold and
            body > 0 and
            upper_shadow >= self.wick_ratio_threshold * body and
            lower_shadow <= body):
            # Can be bullish after downtrend or bearish after uptrend
            # For simplicity, treat as bearish signal
            result["bearish_pattern"] = True
            result["pattern_type"] = "inv_hammer"
            return result
        
        # Detect engulfing patterns (requires previous candle)
        open_list = series.get("open", [])
        close_list = series.get("close", [])
        
        # Verify both lists have at least 2 elements and same length
        if (len(open_list) >= 2 and len(close_list) >= 2 and
            len(open_list) == len(close_list)):
            prev_open = open_list[-2]
            prev_close = close_list[-2]
            
            prev_body_top = max(prev_open, prev_close)
            prev_body_bottom = min(prev_open, prev_close)
            
            # Current candle properties
            is_green = close > open_price
            is_red = close < open_price
            prev_is_green = prev_close > prev_open
            prev_is_red = prev_close < prev_open
            
            # Bullish engulfing
            if (is_green and prev_is_red and
                body_top >= prev_body_top and
                body_bottom <= prev_body_bottom):
                result["bullish_pattern"] = True
                result["pattern_type"] = "bull_engulf"
                return result
            
            # Bearish engulfing
            if (is_red and prev_is_green and
                body_top >= prev_body_top and
                body_bottom <= prev_body_bottom):
                result["bearish_pattern"] = True
                result["pattern_type"] = "bear_engulf"
                return result
        
        return result
    
    def _detect_volume_spike(
        self,
        candle: Dict[str, float],
        series: Dict[str, List[float]]
    ) -> bool:
        """
        Detect if current volume is a spike above rolling average.
        
        Returns True if volume > factor * rolling_mean(window).
        """
        current_volume = candle.get("volume", 0)
        volume_list = series.get("volume", [])
        
        if current_volume <= 0 or len(volume_list) < self.volume_window:
            return False
        
        # Calculate rolling average volume
        window_data = volume_list[-self.volume_window:]
        avg_volume = sum(window_data) / len(window_data)
        
        if avg_volume <= 0:
            return False
        
        return current_volume > (avg_volume * self.volume_spike_factor)
    
    def _detect_volatility_mode(
        self,
        series: Dict[str, List[float]],
        indicators: Dict[str, Any]
    ) -> str:
        """
        Detect ATR volatility mode.
        
        Returns: "expanding", "normal", or "compressing"
        """
        # Try to get ATR from indicators
        atr_val = indicators.get("atr14") or indicators.get(f"atr{self.atr_period}")
        
        if atr_val is None:
            return "normal"
        
        # Calculate rolling ATR average from series if available
        high_list = series.get("high", [])
        low_list = series.get("low", [])
        close_list = series.get("close", [])
        
        # Need at least atr_period * 2 bars and equal length lists
        min_required = self.atr_period * 2
        if (len(high_list) < min_required or
            len(low_list) < min_required or
            len(close_list) < min_required):
            return "normal"
        
        # Calculate simple ATR average over the period
        tr_values = []
        # Ensure we don't go beyond available data
        max_lookback = min(self.atr_period, len(close_list) - 1)
        for i in range(1, max_lookback + 1):
            h = high_list[-i]
            l = low_list[-i]
            # i ranges from 1 to max_lookback, so -i-1 is valid since we have at least 2*atr_period bars
            c_prev = close_list[-i-1]
            tr = max(h - l, abs(h - c_prev), abs(l - c_prev))
            tr_values.append(tr)
        
        if not tr_values:
            return "normal"
        
        avg_atr = sum(tr_values) / len(tr_values)
        
        if avg_atr <= 0:
            return "normal"
        
        ratio = atr_val / avg_atr
        
        if ratio >= self.atr_expand_factor:
            return "expanding"
        elif ratio <= self.atr_compress_factor:
            return "compressing"
        else:
            return "normal"
    
    def _calculate_confidence(
        self,
        components: Dict[str, Any],
        indicators: Dict[str, Any],
        is_uptrend: bool
    ) -> float:
        """
        Calculate confidence score based on signal component alignment.
        
        Score breakdown:
        - Base score: 0.3 for EMA alignment
        - Pattern match: +0.25
        - Volume spike: +0.2
        - ATR not compressing: +0.15
        - RSI alignment: +0.1
        
        Returns:
            Confidence score between 0.0 and 1.0
        """
        confidence = 0.3  # Base score for EMA alignment
        
        # Pattern confirmation
        if is_uptrend and components["bullish_pattern"]:
            confidence += 0.25
        elif not is_uptrend and components["bearish_pattern"]:
            confidence += 0.25
        
        # Volume spike confirmation
        if components["volume_spike"]:
            confidence += 0.2
        
        # ATR volatility mode (avoid compressing)
        if not components["is_compressing"]:
            confidence += 0.15
        
        # RSI alignment
        rsi = indicators.get("rsi14")
        if rsi:
            if is_uptrend and 40 < rsi < 70:
                confidence += 0.1
            elif not is_uptrend and 30 < rsi < 60:
                confidence += 0.1
        
        # Clamp to [0, 1]
        return min(max(confidence, 0.0), 1.0)


# Factory function for easy instantiation
def create_price_action_intraday_v1(
    config: Dict[str, Any],
    state: StrategyState
) -> PriceActionIntradayV1:
    """Create an instance of Price Action Intraday Strategy v1."""
    return PriceActionIntradayV1(config, state)
