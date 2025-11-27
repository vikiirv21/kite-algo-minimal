"""
Price Action Strategy V1

Technical analysis strategy using candlestick patterns and volume analysis.
Implements pattern detection for hammer, engulfing, pinbar, and momentum candles.
Designed for intraday trading on index options (NIFTY, BANKNIFTY, FINNIFTY).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from core.strategy_engine_v2 import BaseStrategy, StrategyState
from strategies.base import Decision

logger = logging.getLogger(__name__)


class PriceActionV1(BaseStrategy):
    """
    Price Action Strategy - Version 1
    
    Strategy Logic:
    - Detects candlestick patterns (hammer, engulfing, pinbar)
    - Confirms with volume spikes
    - Uses HTF trend filter for direction alignment
    - Integrates ATR volatility mode for risk adjustment
    
    Designed for use with StrategyEngineV2 in options trading.
    """
    
    def __init__(self, config: Dict[str, Any], strategy_state: StrategyState):
        super().__init__(config, strategy_state)
        self.name = config.get("strategy_id", "PRICE_ACTION_V1")
        self.role = config.get("role", "intraday")
        self.timeframe = config.get("timeframe", "5m")
        
        # Strategy parameters
        self.min_confidence = config.get("min_confidence", 0.55)
        self.use_htf_filter = config.get("use_htf_filter", True)
        self.use_volume_filter = config.get("use_volume_filter", True)
        self.min_rr = config.get("min_rr", 1.5)
        
        # Pattern detection parameters (tuned for index options)
        self.body_ratio_threshold = config.get("body_ratio_threshold", 0.30)
        self.wick_ratio_threshold = config.get("wick_ratio_threshold", 2.0)
        self.volume_spike_factor = config.get("volume_spike_factor", 1.5)
        self.volume_window = config.get("volume_window", 20)
        
        # ATR volatility parameters
        self.atr_expand_factor = config.get("atr_expand_factor", 1.2)
        self.atr_compress_factor = config.get("atr_compress_factor", 0.8)
        
        # HTF suppression logging (track last logged symbol to avoid spam)
        self._htf_blocked_symbols: Dict[str, str] = {}
        
        # Internal state for tracking pattern history
        self._candle_history: Dict[str, List[Dict[str, float]]] = {}
    
    def generate_signal(
        self,
        candle: Dict[str, float],
        series: Dict[str, List[float]],
        indicators: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Optional[Decision]:
        """
        Generate trading signal based on price action patterns.
        
        Args:
            candle: Current candle with open, high, low, close, volume
            series: Historical series (close, high, low, etc.)
            indicators: Pre-computed indicators (ema20, ema50, htf_ema20, htf_trend, etc.)
            context: Optional context dict with expiry info, session time, etc.
        
        Returns:
            Decision object (BUY, SELL, EXIT, or HOLD)
        """
        context = context or {}
        
        close = candle.get("close", 0.0)
        open_price = candle.get("open", 0.0)
        high = candle.get("high", 0.0)
        low = candle.get("low", 0.0)
        volume = candle.get("volume", 0.0)
        
        if close <= 0 or open_price <= 0:
            return Decision(action="HOLD", reason="invalid_price", confidence=0.0)
        
        # Get symbol from config or context
        symbol = self.config.get("current_symbol", context.get("symbol", "UNKNOWN"))
        
        # Build candle history for pattern detection
        self._update_candle_history(symbol, candle, series)
        
        # Detect patterns
        patterns = self._detect_patterns(symbol, candle, series)
        
        if not patterns:
            return Decision(action="HOLD", reason="no_pattern", confidence=0.0)
        
        # Determine signal direction from patterns
        bullish_patterns = [p for p in patterns if p.get("direction") == "bullish"]
        bearish_patterns = [p for p in patterns if p.get("direction") == "bearish"]
        
        signal = None
        base_confidence = 0.0
        pattern_reason = ""
        
        if bullish_patterns:
            signal = "BUY"
            base_confidence = max(p.get("strength", 0.5) for p in bullish_patterns)
            pattern_reason = "+".join(p["name"] for p in bullish_patterns)
        elif bearish_patterns:
            signal = "SELL"
            base_confidence = max(p.get("strength", 0.5) for p in bearish_patterns)
            pattern_reason = "+".join(p["name"] for p in bearish_patterns)
        
        if not signal:
            return Decision(action="HOLD", reason="no_directional_pattern", confidence=0.0)
        
        # Apply HTF trend filter
        if self.use_htf_filter:
            htf_result = self._apply_htf_filter(signal, symbol, indicators, context)
            if htf_result:
                # Log HTF filter suppression
                self._log_htf_suppression(symbol, signal, htf_result.reason)
                return htf_result
        
        # Apply volume filter
        volume_confirmed = True
        if self.use_volume_filter:
            volume_confirmed = self._check_volume_spike(volume, series.get("volume", []))
            if volume_confirmed:
                base_confidence += 0.15
                pattern_reason += "|vol_spike"
            else:
                base_confidence -= 0.1
                pattern_reason += "|low_vol"
                # Log volume suppression if confidence drops too low
                if base_confidence < self.min_confidence:
                    logger.debug(
                        "[PRICE_ACTION_V1] Volume filter suppressed %s for %s (vol=%.0f, conf=%.2f)",
                        signal, symbol, volume, base_confidence
                    )
        
        # Apply volatility mode adjustment
        atr_val = indicators.get("atr14") or indicators.get("atr")
        if atr_val:
            vol_mode = self._classify_volatility(atr_val, indicators)
            if vol_mode == "expanding":
                base_confidence -= 0.1
                pattern_reason += "|vol_expanding"
            elif vol_mode == "compressing":
                base_confidence += 0.05
                pattern_reason += "|vol_compressing"
        
        # Add EMA alignment bonus
        ema20 = indicators.get("ema20")
        ema50 = indicators.get("ema50")
        if ema20 and ema50:
            if signal == "BUY" and ema20 > ema50:
                base_confidence += 0.1
                pattern_reason += "|ema_aligned_bull"
            elif signal == "SELL" and ema20 < ema50:
                base_confidence += 0.1
                pattern_reason += "|ema_aligned_bear"
        
        # Check confidence threshold
        if base_confidence < self.min_confidence:
            return Decision(
                action="HOLD",
                reason=f"low_conf:{pattern_reason}",
                confidence=base_confidence
            )
        
        # Check existing position
        has_long = self.position_is_long(symbol)
        has_short = self.position_is_short(symbol)
        
        # Handle position conflicts
        if signal == "BUY" and has_short:
            signal = "EXIT"
            pattern_reason = f"exit_short|{pattern_reason}"
        elif signal == "SELL" and has_long:
            signal = "EXIT"
            pattern_reason = f"exit_long|{pattern_reason}"
        elif signal == "BUY" and has_long:
            return Decision(action="HOLD", reason="already_long", confidence=base_confidence)
        elif signal == "SELL" and has_short:
            return Decision(action="HOLD", reason="already_short", confidence=base_confidence)
        
        # Apply expiry-aware adjustments
        if context:
            is_expiry_day = context.get("is_expiry_day", False)
            time_to_expiry_minutes = context.get("time_to_expiry_minutes")
            
            if is_expiry_day and time_to_expiry_minutes is not None and time_to_expiry_minutes < 60:
                base_confidence *= 0.85
                pattern_reason += "|expiry_caution"
        
        return Decision(
            action=signal,
            reason=pattern_reason,
            confidence=min(base_confidence, 1.0)
        )
    
    def _update_candle_history(
        self,
        symbol: str,
        candle: Dict[str, float],
        series: Dict[str, List[float]]
    ) -> None:
        """Update internal candle history for pattern detection."""
        if symbol not in self._candle_history:
            self._candle_history[symbol] = []
        
        # Add current candle
        self._candle_history[symbol].append(candle.copy())
        
        # Keep only last 50 candles
        if len(self._candle_history[symbol]) > 50:
            self._candle_history[symbol] = self._candle_history[symbol][-50:]
    
    def _detect_patterns(
        self,
        symbol: str,
        candle: Dict[str, float],
        series: Dict[str, List[float]]
    ) -> List[Dict[str, Any]]:
        """
        Detect candlestick patterns in current candle.
        
        Returns list of detected patterns with direction and strength.
        """
        patterns = []
        
        open_price = candle.get("open", 0.0)
        close = candle.get("close", 0.0)
        high = candle.get("high", 0.0)
        low = candle.get("low", 0.0)
        
        if high <= low or close <= 0 or open_price <= 0:
            return patterns
        
        # Calculate candle metrics
        body = abs(close - open_price)
        candle_range = high - low
        body_top = max(close, open_price)
        body_bottom = min(close, open_price)
        upper_shadow = high - body_top
        lower_shadow = body_bottom - low
        is_bullish = close > open_price
        is_bearish = close < open_price
        
        body_ratio = body / candle_range if candle_range > 0 else 0
        
        # Detect Hammer (bullish reversal)
        if body_ratio <= self.body_ratio_threshold:
            if body > 0 and lower_shadow >= self.wick_ratio_threshold * body:
                if upper_shadow <= body:
                    patterns.append({
                        "name": "hammer",
                        "direction": "bullish",
                        "strength": 0.65
                    })
        
        # Detect Inverted Hammer (potential bullish reversal)
        if body_ratio <= self.body_ratio_threshold:
            if body > 0 and upper_shadow >= self.wick_ratio_threshold * body:
                if lower_shadow <= body:
                    patterns.append({
                        "name": "inv_hammer",
                        "direction": "bullish",
                        "strength": 0.55
                    })
        
        # Detect Shooting Star (bearish reversal - inverted hammer at top)
        if body_ratio <= self.body_ratio_threshold:
            if body > 0 and upper_shadow >= self.wick_ratio_threshold * body:
                if lower_shadow <= body and is_bearish:
                    patterns.append({
                        "name": "shooting_star",
                        "direction": "bearish",
                        "strength": 0.60
                    })
        
        # Detect Engulfing patterns (requires previous candle)
        history = self._candle_history.get(symbol, [])
        if len(history) >= 2:
            prev_candle = history[-2]
            prev_open = prev_candle.get("open", 0.0)
            prev_close = prev_candle.get("close", 0.0)
            prev_body_top = max(prev_close, prev_open)
            prev_body_bottom = min(prev_close, prev_open)
            prev_is_bullish = prev_close > prev_open
            prev_is_bearish = prev_close < prev_open
            
            # Bullish engulfing: current green engulfs previous red
            if is_bullish and prev_is_bearish:
                if body_top >= prev_body_top and body_bottom <= prev_body_bottom:
                    patterns.append({
                        "name": "bull_engulf",
                        "direction": "bullish",
                        "strength": 0.70
                    })
            
            # Bearish engulfing: current red engulfs previous green
            if is_bearish and prev_is_bullish:
                if body_top >= prev_body_top and body_bottom <= prev_body_bottom:
                    patterns.append({
                        "name": "bear_engulf",
                        "direction": "bearish",
                        "strength": 0.70
                    })
        
        # Detect strong momentum candles
        if body_ratio >= 0.6:  # Body is 60%+ of candle range
            if is_bullish:
                patterns.append({
                    "name": "bull_momentum",
                    "direction": "bullish",
                    "strength": 0.55
                })
            elif is_bearish:
                patterns.append({
                    "name": "bear_momentum",
                    "direction": "bearish",
                    "strength": 0.55
                })
        
        return patterns
    
    def _apply_htf_filter(
        self,
        signal: str,
        symbol: str,
        indicators: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Optional[Decision]:
        """
        Apply Higher Timeframe trend filter.
        
        Blocks trades that go against HTF trend.
        
        Returns Decision to block (HOLD) or None to allow.
        """
        # Get HTF indicators (if available)
        htf_ema20 = indicators.get("htf_ema20")
        htf_ema50 = indicators.get("htf_ema50")
        htf_trend = indicators.get("htf_trend")
        
        # Try context as fallback
        if context and htf_trend is None:
            htf_trend = context.get("htf_trend")
        
        # If no HTF data, allow the trade
        if htf_ema20 is None and htf_ema50 is None and htf_trend is None:
            return None
        
        # Determine HTF trend direction
        htf_bullish = False
        htf_bearish = False
        
        if htf_trend:
            htf_bullish = str(htf_trend).lower() in ("up", "bullish", "bull", "1")
            htf_bearish = str(htf_trend).lower() in ("down", "bearish", "bear", "-1")
        elif htf_ema20 is not None and htf_ema50 is not None:
            htf_bullish = htf_ema20 > htf_ema50
            htf_bearish = htf_ema20 < htf_ema50
        
        # Block trades against HTF trend
        if signal == "BUY" and htf_bearish:
            return Decision(
                action="HOLD",
                reason="htf_filter_blocked_BUY|htf_bearish",
                confidence=0.0
            )
        
        if signal == "SELL" and htf_bullish:
            return Decision(
                action="HOLD",
                reason="htf_filter_blocked_SELL|htf_bullish",
                confidence=0.0
            )
        
        return None
    
    def _log_htf_suppression(self, symbol: str, signal: str, reason: str) -> None:
        """Log when HTF filter suppresses a trade (avoid spam)."""
        key = f"{symbol}:{signal}"
        if self._htf_blocked_symbols.get(key) != reason:
            self._htf_blocked_symbols[key] = reason
            logger.info(
                "[PRICE_ACTION_V1] HTF filter blocked %s for %s: %s",
                signal, symbol, reason
            )
    
    def _check_volume_spike(
        self,
        current_volume: float,
        volume_series: List[float]
    ) -> bool:
        """Check if current volume is a spike above rolling average."""
        if not volume_series or len(volume_series) < self.volume_window:
            return True  # Insufficient data, don't block
        
        # Calculate rolling average
        recent_volumes = volume_series[-self.volume_window:]
        avg_volume = sum(recent_volumes) / len(recent_volumes)
        
        if avg_volume <= 0:
            return True
        
        return current_volume >= avg_volume * self.volume_spike_factor
    
    def _classify_volatility(
        self,
        current_atr: float,
        indicators: Dict[str, Any]
    ) -> str:
        """
        Classify current volatility mode based on ATR.
        
        Returns: "expanding", "normal", or "compressing"
        """
        # Try to get ATR average from indicators
        atr_avg = indicators.get("atr_avg") or indicators.get("atr14_avg")
        
        if atr_avg is None or atr_avg <= 0:
            return "normal"
        
        ratio = current_atr / atr_avg
        
        if ratio >= self.atr_expand_factor:
            return "expanding"
        elif ratio <= self.atr_compress_factor:
            return "compressing"
        else:
            return "normal"


# Factory function for easy instantiation
def create_price_action_v1(config: Dict[str, Any], state: StrategyState) -> PriceActionV1:
    """Create an instance of Price Action Strategy v1."""
    return PriceActionV1(config, state)
