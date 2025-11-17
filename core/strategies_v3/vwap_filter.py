"""
VWAP Filter Strategy for v3 Engine
"""

from typing import Any, Dict, Optional

from core.strategies_v3 import StrategyV3Base, OrderIntent


class VWAPFilterStrategy(StrategyV3Base):
    """
    VWAP-based filter strategy.
    
    Uses VWAP as a trend filter:
    - BUY when price above VWAP (bullish)
    - SELL when price below VWAP (bearish)
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.id = "vwap_filter"
    
    def generate(
        self,
        symbol: str,
        ts: str,
        price: float,
        md: Dict[str, Any],
        bundle: Dict[str, Any]
    ) -> Optional[OrderIntent]:
        """Generate signal based on VWAP position."""
        # Extract VWAP from bundle
        vwap = bundle.get("vwap")
        
        if vwap is None or vwap <= 0:
            return None
        
        # Price above VWAP - bullish
        if price > vwap:
            distance_pct = ((price - vwap) / vwap) * 100
            
            # Only signal if price is not too far from VWAP
            if distance_pct < 2.0:  # Within 2% of VWAP
                confidence = 0.6 + min(0.3, distance_pct / 10)
                
                return OrderIntent(
                    symbol=symbol,
                    action="BUY",
                    qty=None,
                    reason="price_above_vwap",
                    strategy_code=self.id,
                    confidence=confidence,
                    metadata={
                        "vwap": vwap,
                        "price": price,
                        "distance_pct": distance_pct,
                        "setup": "vwap_bullish"
                    }
                )
        
        # Price below VWAP - bearish
        elif price < vwap:
            distance_pct = ((vwap - price) / vwap) * 100
            
            # Only signal if price is not too far from VWAP
            if distance_pct < 2.0:  # Within 2% of VWAP
                confidence = 0.6 + min(0.3, distance_pct / 10)
                
                return OrderIntent(
                    symbol=symbol,
                    action="SELL",
                    qty=None,
                    reason="price_below_vwap",
                    strategy_code=self.id,
                    confidence=confidence,
                    metadata={
                        "vwap": vwap,
                        "price": price,
                        "distance_pct": distance_pct,
                        "setup": "vwap_bearish"
                    }
                )
        
        return None
