"""
Higher Timeframe (HTF) Trend Filter Module

Provides trend analysis across multiple timeframes (15m, 1h) to filter
trading signals from primary timeframe strategies.

This module computes:
- EMA20/50 trend on higher timeframes
- Alignment score across timeframes
- Trend bias (bullish, bearish, sideways)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core import indicators

logger = logging.getLogger(__name__)


@dataclass
class HTFTrendResult:
    """
    Result of higher timeframe trend analysis.
    
    Attributes:
        htf_bias: Overall trend bias ("bullish", "bearish", "sideways")
        aligned: Whether all HTF timeframes agree on direction
        score: Alignment score (0.0 to 1.0) indicating trend strength
        trend_15m: Trend on 15m timeframe ("up", "down", "flat")
        trend_1h: Trend on 1h timeframe ("up", "down", "flat")
        ema20_15m: EMA20 value on 15m timeframe
        ema50_15m: EMA50 value on 15m timeframe
        ema20_1h: EMA20 value on 1h timeframe
        ema50_1h: EMA50 value on 1h timeframe
        timestamp: When this analysis was performed
    """
    htf_bias: str
    aligned: bool
    score: float
    trend_15m: str
    trend_1h: str
    ema20_15m: Optional[float] = None
    ema50_15m: Optional[float] = None
    ema20_1h: Optional[float] = None
    ema50_1h: Optional[float] = None
    timestamp: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "htf_bias": self.htf_bias,
            "aligned": self.aligned,
            "score": self.score,
            "trend_15m": self.trend_15m,
            "trend_1h": self.trend_1h,
            "ema20_15m": self.ema20_15m,
            "ema50_15m": self.ema50_15m,
            "ema20_1h": self.ema20_1h,
            "ema50_1h": self.ema50_1h,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


def compute_ema_trend(close_prices: List[float], ema_fast_period: int = 20, ema_slow_period: int = 50) -> Dict[str, Any]:
    """
    Compute EMA-based trend from close prices.
    
    Args:
        close_prices: List of close prices (oldest first)
        ema_fast_period: Period for fast EMA (default: 20)
        ema_slow_period: Period for slow EMA (default: 50)
    
    Returns:
        Dict with trend info: trend, ema_fast, ema_slow, separation
    """
    if not close_prices or len(close_prices) < ema_slow_period:
        return {
            "trend": "flat",
            "ema_fast": None,
            "ema_slow": None,
            "separation": 0.0,
        }
    
    try:
        ema_fast = indicators.ema(close_prices, ema_fast_period)
        ema_slow = indicators.ema(close_prices, ema_slow_period)
        
        if ema_fast is None or ema_slow is None:
            return {
                "trend": "flat",
                "ema_fast": None,
                "ema_slow": None,
                "separation": 0.0,
            }
        
        # Calculate separation as percentage
        separation = 0.0
        if ema_slow > 0:
            separation = (ema_fast - ema_slow) / ema_slow
        
        # Determine trend
        if ema_fast > ema_slow:
            trend = "up"
        elif ema_fast < ema_slow:
            trend = "down"
        else:
            trend = "flat"
        
        return {
            "trend": trend,
            "ema_fast": ema_fast,
            "ema_slow": ema_slow,
            "separation": separation,
        }
    except Exception as e:
        logger.debug("Error computing EMA trend: %s", e)
        return {
            "trend": "flat",
            "ema_fast": None,
            "ema_slow": None,
            "separation": 0.0,
        }


def compute_htf_trend(
    symbol: str,
    primary_df: Optional[Dict[str, List[float]]] = None,
    htf_df_15m: Optional[Dict[str, List[float]]] = None,
    htf_df_1h: Optional[Dict[str, List[float]]] = None,
    ema_fast_period: int = 20,
    ema_slow_period: int = 50,
) -> HTFTrendResult:
    """
    Compute higher timeframe trend for a symbol.
    
    This function analyzes EMA20/50 crossovers on 15m and 1h timeframes
    to determine the overall higher timeframe bias.
    
    Args:
        symbol: Trading symbol (for logging purposes)
        primary_df: Optional primary timeframe data (not used in current implementation)
        htf_df_15m: Dict with 'close' list for 15m timeframe
        htf_df_1h: Dict with 'close' list for 1h timeframe
        ema_fast_period: Period for fast EMA (default: 20)
        ema_slow_period: Period for slow EMA (default: 50)
    
    Returns:
        HTFTrendResult with trend analysis
    """
    timestamp = datetime.now(timezone.utc)
    
    # Compute 15m trend
    trend_15m_result = {"trend": "flat", "ema_fast": None, "ema_slow": None, "separation": 0.0}
    if htf_df_15m and "close" in htf_df_15m and htf_df_15m["close"]:
        trend_15m_result = compute_ema_trend(
            htf_df_15m["close"],
            ema_fast_period,
            ema_slow_period
        )
    
    # Compute 1h trend
    trend_1h_result = {"trend": "flat", "ema_fast": None, "ema_slow": None, "separation": 0.0}
    if htf_df_1h and "close" in htf_df_1h and htf_df_1h["close"]:
        trend_1h_result = compute_ema_trend(
            htf_df_1h["close"],
            ema_fast_period,
            ema_slow_period
        )
    
    trend_15m = trend_15m_result["trend"]
    trend_1h = trend_1h_result["trend"]
    
    # Determine alignment and bias
    aligned = False
    htf_bias = "sideways"
    score = 0.0
    
    # Both uptrends
    if trend_15m == "up" and trend_1h == "up":
        htf_bias = "bullish"
        aligned = True
        # Score based on separation strength
        sep_15m = abs(trend_15m_result.get("separation", 0.0))
        sep_1h = abs(trend_1h_result.get("separation", 0.0))
        score = min(1.0, (sep_15m + sep_1h) * 10)  # Scale separation to 0-1
    
    # Both downtrends
    elif trend_15m == "down" and trend_1h == "down":
        htf_bias = "bearish"
        aligned = True
        sep_15m = abs(trend_15m_result.get("separation", 0.0))
        sep_1h = abs(trend_1h_result.get("separation", 0.0))
        score = min(1.0, (sep_15m + sep_1h) * 10)
    
    # Mixed or sideways
    else:
        aligned = False
        htf_bias = "sideways"
        # Partial score if at least one timeframe has direction
        if trend_15m != "flat" or trend_1h != "flat":
            score = 0.3
        else:
            score = 0.0
    
    result = HTFTrendResult(
        htf_bias=htf_bias,
        aligned=aligned,
        score=score,
        trend_15m=trend_15m,
        trend_1h=trend_1h,
        ema20_15m=trend_15m_result.get("ema_fast"),
        ema50_15m=trend_15m_result.get("ema_slow"),
        ema20_1h=trend_1h_result.get("ema_fast"),
        ema50_1h=trend_1h_result.get("ema_slow"),
        timestamp=timestamp,
    )
    
    logger.debug(
        "HTF trend for %s: bias=%s, aligned=%s, score=%.2f, 15m=%s, 1h=%s",
        symbol,
        htf_bias,
        aligned,
        score,
        trend_15m,
        trend_1h,
    )
    
    return result


def compute_htf_trend_from_series(
    symbol: str,
    close_15m: Optional[List[float]] = None,
    close_1h: Optional[List[float]] = None,
    ema_fast_period: int = 20,
    ema_slow_period: int = 50,
) -> HTFTrendResult:
    """
    Convenience function to compute HTF trend from close price lists.
    
    Args:
        symbol: Trading symbol
        close_15m: List of close prices for 15m timeframe
        close_1h: List of close prices for 1h timeframe
        ema_fast_period: Period for fast EMA (default: 20)
        ema_slow_period: Period for slow EMA (default: 50)
    
    Returns:
        HTFTrendResult with trend analysis
    """
    htf_df_15m = {"close": close_15m} if close_15m else None
    htf_df_1h = {"close": close_1h} if close_1h else None
    
    return compute_htf_trend(
        symbol=symbol,
        htf_df_15m=htf_df_15m,
        htf_df_1h=htf_df_1h,
        ema_fast_period=ema_fast_period,
        ema_slow_period=ema_slow_period,
    )


def should_allow_signal(
    signal_direction: str,
    htf_result: HTFTrendResult,
    min_score: float = 0.6,
    allow_sideways: bool = True,
) -> tuple[bool, str]:
    """
    Check if a signal should be allowed based on HTF trend.
    
    Args:
        signal_direction: "long" or "short"
        htf_result: HTF trend analysis result
        min_score: Minimum alignment score required (default: 0.6)
        allow_sideways: Whether to allow signals when HTF bias is sideways
    
    Returns:
        Tuple of (allowed, reason)
    """
    signal_direction = signal_direction.lower()
    
    # If HTF bias is sideways
    if htf_result.htf_bias == "sideways":
        if allow_sideways:
            return True, "htf_sideways_allowed"
        else:
            return False, "htf_sideways_blocked"
    
    # Long signals need bullish HTF
    if signal_direction in ["long", "buy"]:
        if htf_result.htf_bias == "bullish":
            if htf_result.score >= min_score:
                return True, "htf_bullish_aligned"
            else:
                return True, "htf_bullish_weak"
        elif htf_result.htf_bias == "bearish":
            return False, "htf_bearish_conflicts_long"
    
    # Short signals need bearish HTF
    if signal_direction in ["short", "sell"]:
        if htf_result.htf_bias == "bearish":
            if htf_result.score >= min_score:
                return True, "htf_bearish_aligned"
            else:
                return True, "htf_bearish_weak"
        elif htf_result.htf_bias == "bullish":
            return False, "htf_bullish_conflicts_short"
    
    # Default allow
    return True, "htf_no_conflict"


def adjust_confidence_for_htf(
    confidence: float,
    htf_result: HTFTrendResult,
    signal_direction: str,
    reduction_factor: float = 0.3,
) -> float:
    """
    Adjust signal confidence based on HTF alignment.
    
    If HTF bias conflicts with signal direction, reduce confidence.
    If HTF is sideways, slightly reduce confidence.
    If HTF aligns, maintain or slightly boost confidence.
    
    Args:
        confidence: Original confidence score (0.0 to 1.0)
        htf_result: HTF trend analysis result
        signal_direction: "long" or "short"
        reduction_factor: How much to reduce confidence on conflict (default: 0.3)
    
    Returns:
        Adjusted confidence score
    """
    signal_direction = signal_direction.lower()
    
    # Sideways - slight reduction
    if htf_result.htf_bias == "sideways":
        return confidence * (1.0 - reduction_factor * 0.5)
    
    # Check alignment
    is_aligned = (
        (signal_direction in ["long", "buy"] and htf_result.htf_bias == "bullish") or
        (signal_direction in ["short", "sell"] and htf_result.htf_bias == "bearish")
    )
    
    if is_aligned:
        # Aligned - boost based on HTF score
        boost = htf_result.score * 0.1  # Up to 10% boost
        return min(1.0, confidence * (1.0 + boost))
    else:
        # Conflicting - reduce confidence
        return confidence * (1.0 - reduction_factor)
