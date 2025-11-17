"""
EMA 20/50 Crossover Strategy for v3 Engine
"""

from typing import Any, Dict, Optional

from core.strategies_v3 import StrategyV3Base, OrderIntent


class EMA2050Strategy(StrategyV3Base):
    """
    EMA 20/50 crossover strategy.
    
    Generates:
    - BUY when EMA20 > EMA50 and price above EMA20
    - SELL when EMA20 < EMA50 and price below EMA20
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.id = "ema20_50"
    
    def generate(
        self,
        symbol: str,
        ts: str,
        price: float,
        md: Dict[str, Any],
        bundle: Dict[str, Any]
    ) -> Optional[OrderIntent]:
        """Generate signal based on EMA crossover."""
        # Extract indicators from bundle
        ema20 = bundle.get("ema20")
        ema50 = bundle.get("ema50")
        
        if ema20 is None or ema50 is None:
            return None
        
        # Check for bullish alignment
        if ema20 > ema50 and price > ema20:
            return OrderIntent(
                symbol=symbol,
                action="BUY",
                qty=None,
                reason="ema20_above_ema50_price_above_ema20",
                strategy_code=self.id,
                confidence=0.7,
                metadata={
                    "ema20": ema20,
                    "ema50": ema50,
                    "price": price,
                    "setup": "ema_bullish"
                }
            )
        
        # Check for bearish alignment
        elif ema20 < ema50 and price < ema20:
            return OrderIntent(
                symbol=symbol,
                action="SELL",
                qty=None,
                reason="ema20_below_ema50_price_below_ema20",
                strategy_code=self.id,
                confidence=0.7,
                metadata={
                    "ema20": ema20,
                    "ema50": ema50,
                    "price": price,
                    "setup": "ema_bearish"
                }
            )
        
        return None
