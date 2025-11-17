"""
Higher Timeframe Trend Strategy for v3 Engine
"""

from typing import Any, Dict, Optional

from core.strategies_v3 import StrategyV3Base, OrderIntent


class HTFTrendStrategy(StrategyV3Base):
    """
    Higher timeframe trend confirmation strategy.
    
    Confirms primary timeframe signals with higher timeframe trend.
    This strategy is used in conjunction with others for multi-timeframe confirmation.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.id = "htf_trend"
    
    def generate(
        self,
        symbol: str,
        ts: str,
        price: float,
        md: Dict[str, Any],
        bundle: Dict[str, Any]
    ) -> Optional[OrderIntent]:
        """Generate signal based on higher timeframe trend."""
        # This strategy evaluates HTF indicators
        # Bundle should contain HTF indicators prefixed with "htf_"
        htf_ema20 = bundle.get("htf_ema20")
        htf_ema50 = bundle.get("htf_ema50")
        htf_trend = bundle.get("htf_trend")  # Can be "up", "down", or "neutral"
        
        if htf_ema20 is None or htf_ema50 is None:
            return None
        
        # HTF bullish trend
        if htf_ema20 > htf_ema50:
            confidence = 0.7
            
            # Check if current price aligns with HTF trend
            if price > htf_ema20:
                confidence = 0.8
            
            return OrderIntent(
                symbol=symbol,
                action="BUY",
                qty=None,
                reason="htf_trend_bullish",
                strategy_code=self.id,
                confidence=confidence,
                metadata={
                    "htf_ema20": htf_ema20,
                    "htf_ema50": htf_ema50,
                    "htf_trend": "up",
                    "setup": "htf_confirm"
                }
            )
        
        # HTF bearish trend
        elif htf_ema20 < htf_ema50:
            confidence = 0.7
            
            # Check if current price aligns with HTF trend
            if price < htf_ema20:
                confidence = 0.8
            
            return OrderIntent(
                symbol=symbol,
                action="SELL",
                qty=None,
                reason="htf_trend_bearish",
                strategy_code=self.id,
                confidence=confidence,
                metadata={
                    "htf_ema20": htf_ema20,
                    "htf_ema50": htf_ema50,
                    "htf_trend": "down",
                    "setup": "htf_confirm"
                }
            )
        
        return None
