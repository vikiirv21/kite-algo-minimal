"""
RSI Pullback Strategy for v3 Engine
"""

from typing import Any, Dict, Optional

from core.strategies_v3 import StrategyV3Base, OrderIntent


class RSIPullbackStrategy(StrategyV3Base):
    """
    RSI-based pullback strategy.
    
    Looks for pullbacks in trends:
    - BUY when in uptrend and RSI oversold
    - SELL when in downtrend and RSI overbought
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.id = "rsi_pullback"
        self.rsi_oversold = self.config.get("rsi_oversold", 35)
        self.rsi_overbought = self.config.get("rsi_overbought", 65)
    
    def generate(
        self,
        symbol: str,
        ts: str,
        price: float,
        md: Dict[str, Any],
        bundle: Dict[str, Any]
    ) -> Optional[OrderIntent]:
        """Generate pullback signal based on RSI."""
        # Extract indicators
        rsi = bundle.get("rsi14")
        ema20 = bundle.get("ema20")
        ema50 = bundle.get("ema50")
        
        if rsi is None or ema20 is None or ema50 is None:
            return None
        
        # Bullish pullback: uptrend + RSI oversold
        if ema20 > ema50 and rsi < self.rsi_oversold:
            confidence = 0.7
            # Higher confidence if RSI is very oversold
            if rsi < 30:
                confidence = 0.85
            
            return OrderIntent(
                symbol=symbol,
                action="BUY",
                qty=None,
                reason="rsi_oversold_in_uptrend",
                strategy_code=self.id,
                confidence=confidence,
                metadata={
                    "rsi": rsi,
                    "ema20": ema20,
                    "ema50": ema50,
                    "setup": "pullback_buy"
                }
            )
        
        # Bearish pullback: downtrend + RSI overbought
        elif ema20 < ema50 and rsi > self.rsi_overbought:
            confidence = 0.7
            # Higher confidence if RSI is very overbought
            if rsi > 70:
                confidence = 0.85
            
            return OrderIntent(
                symbol=symbol,
                action="SELL",
                qty=None,
                reason="rsi_overbought_in_downtrend",
                strategy_code=self.id,
                confidence=confidence,
                metadata={
                    "rsi": rsi,
                    "ema20": ema20,
                    "ema50": ema50,
                    "setup": "pullback_sell"
                }
            )
        
        return None
