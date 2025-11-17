"""
Trend Following Strategy for v3 Engine
"""

from typing import Any, Dict, Optional

from core.strategies_v3 import StrategyV3Base, OrderIntent


class TrendStrategy(StrategyV3Base):
    """
    Trend following strategy using EMA alignment and ADX.
    
    Generates signals when:
    - Strong trend indicated by ADX
    - EMAs are aligned
    - Price momentum confirms direction
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.id = "trend"
        self.adx_threshold = self.config.get("adx_threshold", 20)
    
    def generate(
        self,
        symbol: str,
        ts: str,
        price: float,
        md: Dict[str, Any],
        bundle: Dict[str, Any]
    ) -> Optional[OrderIntent]:
        """Generate trend-following signal."""
        # Extract indicators
        ema9 = bundle.get("ema9")
        ema20 = bundle.get("ema20")
        ema50 = bundle.get("ema50")
        adx = bundle.get("adx")
        slope10 = bundle.get("slope10")
        
        if None in [ema9, ema20, ema50]:
            return None
        
        # Check for strong trend
        has_strong_trend = adx is not None and adx > self.adx_threshold
        
        # Bullish trend: EMAs aligned upward
        if ema9 > ema20 > ema50:
            confidence = 0.6
            if has_strong_trend:
                confidence += 0.2
            if slope10 is not None and slope10 > 0:
                confidence += 0.1
            
            return OrderIntent(
                symbol=symbol,
                action="BUY",
                qty=None,
                reason="trend_bullish_ema_aligned",
                strategy_code=self.id,
                confidence=min(confidence, 1.0),
                metadata={
                    "ema9": ema9,
                    "ema20": ema20,
                    "ema50": ema50,
                    "adx": adx,
                    "slope": slope10,
                    "setup": "trend_follow"
                }
            )
        
        # Bearish trend: EMAs aligned downward
        elif ema9 < ema20 < ema50:
            confidence = 0.6
            if has_strong_trend:
                confidence += 0.2
            if slope10 is not None and slope10 < 0:
                confidence += 0.1
            
            return OrderIntent(
                symbol=symbol,
                action="SELL",
                qty=None,
                reason="trend_bearish_ema_aligned",
                strategy_code=self.id,
                confidence=min(confidence, 1.0),
                metadata={
                    "ema9": ema9,
                    "ema20": ema20,
                    "ema50": ema50,
                    "adx": adx,
                    "slope": slope10,
                    "setup": "trend_follow"
                }
            )
        
        return None
