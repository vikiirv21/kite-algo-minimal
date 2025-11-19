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
                       May also include market_context for broad market awareness
        
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
        
        # Generate base signals
        signal = None
        reason = ""
        
        if bullish_cross:
            if has_short:
                # Exit short and go long
                signal = "EXIT"
                reason = "bearish_to_bullish_cross"
            elif not has_long:
                # Enter long
                signal = "BUY"
                reason = self._build_reason("bullish_cross", indicators)
        
        elif bearish_cross:
            if has_long:
                # Exit long and go short
                signal = "EXIT"
                reason = "bullish_to_bearish_cross"
            elif not has_short:
                # Enter short
                signal = "SELL"
                reason = self._build_reason("bearish_cross", indicators)
        
        # Check exit conditions (RSI extremes)
        rsi = indicators.get("rsi14")
        if rsi and not signal:
            if has_long and rsi > 75:
                signal = "EXIT"
                reason = "rsi_overbought"
            elif has_short and rsi < 25:
                signal = "EXIT"
                reason = "rsi_oversold"
        
        # Apply MarketContext filters if available (conservative - only blocks entries)
        if signal in ["BUY", "SELL"]:
            market_context = indicators.get("market_context")
            if market_context:
                filter_result = self._apply_market_context_filters(
                    signal, confidence, symbol, market_context
                )
                if filter_result:
                    # Filter blocked the entry
                    return filter_result
        
        # Return final decision
        if signal:
            return Decision(action=signal, reason=reason, confidence=confidence)
        else:
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
    
    def _apply_market_context_filters(
        self,
        signal: str,
        confidence: float,
        symbol: str,
        market_context: Any,
    ) -> Optional[Decision]:
        """
        Apply MarketContext filters to proposed entry signal.
        
        Conservative approach: Only blocks entries, never loosens rules.
        
        Args:
            signal: "BUY" or "SELL"
            confidence: Signal confidence (0-1)
            symbol: Trading symbol
            market_context: MarketContextSnapshot instance
        
        Returns:
            Decision to block entry (HOLD) or None to allow
        """
        # Determine index alias for symbol (NIFTY or BANKNIFTY)
        index_alias = self._determine_index_alias(symbol)
        
        # Get index trend if available
        index_trend_state = None
        if hasattr(market_context, "index_trend") and index_alias in market_context.index_trend:
            index_trend_state = market_context.index_trend[index_alias]
        
        # BUY signal gating: Require BULL or RANGE_UP regime
        if signal in ["BUY", "LONG"]:
            if index_trend_state:
                regime = getattr(index_trend_state, "regime", "UNKNOWN")
                if regime not in ["BULL", "RANGE_UP"]:
                    return Decision(
                        action="HOLD",
                        reason=f"market_context_{index_alias}_{regime}_no_longs",
                        confidence=0.0
                    )
        
        # SELL signal gating: Require BEAR or RANGE_DOWN regime
        if signal in ["SELL", "SHORT"]:
            if index_trend_state:
                regime = getattr(index_trend_state, "regime", "UNKNOWN")
                if regime not in ["BEAR", "RANGE_DOWN"]:
                    return Decision(
                        action="HOLD",
                        reason=f"market_context_{index_alias}_{regime}_no_shorts",
                        confidence=0.0
                    )
        
        # Volatility Filter: Block ALL new entries in PANIC regime
        volatility_state = getattr(market_context, "volatility", None)
        if volatility_state:
            vol_regime = getattr(volatility_state, "regime", "UNKNOWN")
            if vol_regime == "PANIC":
                return Decision(
                    action="HOLD",
                    reason=f"market_context_vol_{vol_regime}_block_entries",
                    confidence=0.0
                )
        
        # Relative Volume Filter: Block when rvol < 0.5
        rvol_index = getattr(market_context, "rvol_index", {})
        if index_alias and index_alias in rvol_index:
            rvol = rvol_index[index_alias]
            if rvol < 0.5:
                return Decision(
                    action="HOLD",
                    reason=f"market_context_{index_alias}_low_rvol_{rvol:.2f}",
                    confidence=0.0
                )
        
        # All filters passed
        return None
    
    def _determine_index_alias(self, symbol: str) -> str:
        """
        Determine which index (NIFTY/BANKNIFTY) a symbol belongs to.
        
        Args:
            symbol: Trading symbol
        
        Returns:
            "NIFTY" or "BANKNIFTY" (defaults to NIFTY)
        """
        symbol_upper = symbol.upper()
        
        if "BANKNIFTY" in symbol_upper or "BANKNFT" in symbol_upper:
            return "BANKNIFTY"
        else:
            # Default to NIFTY for most symbols
            return "NIFTY"


# Factory function for easy instantiation
def create_ema20_50_intraday_v2(config: Dict[str, Any], state: StrategyState) -> EMA2050IntradayV2:
    """Create an instance of EMA 20/50 Intraday Strategy v2."""
    return EMA2050IntradayV2(config, state)
