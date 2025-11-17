"""
Volatility Regime Strategy for v3 Engine
"""

from typing import Any, Dict, Optional

from core.strategies_v3 import StrategyV3Base, OrderIntent


class VolRegimeStrategy(StrategyV3Base):
    """
    Volatility regime detection strategy.
    
    Identifies market regime using ATR and Bollinger Bands:
    - High volatility: look for breakout opportunities
    - Low volatility: prepare for potential squeeze break
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.id = "vol_regime"
        self.low_vol_threshold = self.config.get("low_vol_threshold", 0.015)  # 1.5%
    
    def generate(
        self,
        symbol: str,
        ts: str,
        price: float,
        md: Dict[str, Any],
        bundle: Dict[str, Any]
    ) -> Optional[OrderIntent]:
        """Detect volatility regime and generate appropriate signal."""
        # Extract volatility indicators
        atr = bundle.get("atr14")
        bb_upper = bundle.get("bb_upper")
        bb_lower = bundle.get("bb_lower")
        bb_middle = bundle.get("bb_middle")
        
        if atr is None or bb_upper is None or bb_lower is None or price <= 0:
            return None
        
        # Calculate normalized ATR
        atr_pct = (atr / price) * 100
        
        # Low volatility squeeze detected
        if bb_upper is not None and bb_lower is not None and bb_middle is not None:
            bb_width = ((bb_upper - bb_lower) / bb_middle) * 100
            
            # Volatility squeeze: narrow bands + low ATR
            if bb_width < 3.0 and atr_pct < self.low_vol_threshold:
                # Look for direction based on recent price action
                if price > bb_middle:
                    return OrderIntent(
                        symbol=symbol,
                        action="BUY",
                        qty=None,
                        reason="vol_squeeze_bullish_bias",
                        strategy_code=self.id,
                        confidence=0.5,
                        metadata={
                            "atr_pct": atr_pct,
                            "bb_width": bb_width,
                            "regime": "low_vol_squeeze",
                            "setup": "vol_squeeze_break"
                        }
                    )
                elif price < bb_middle:
                    return OrderIntent(
                        symbol=symbol,
                        action="SELL",
                        qty=None,
                        reason="vol_squeeze_bearish_bias",
                        strategy_code=self.id,
                        confidence=0.5,
                        metadata={
                            "atr_pct": atr_pct,
                            "bb_width": bb_width,
                            "regime": "low_vol_squeeze",
                            "setup": "vol_squeeze_break"
                        }
                    )
        
        # High volatility breakout
        if atr_pct > 3.0:  # High ATR
            # Breakout above upper BB
            if bb_upper is not None and price > bb_upper:
                return OrderIntent(
                    symbol=symbol,
                    action="BUY",
                    qty=None,
                    reason="high_vol_breakout_long",
                    strategy_code=self.id,
                    confidence=0.65,
                    metadata={
                        "atr_pct": atr_pct,
                        "regime": "high_vol",
                        "setup": "breakout"
                    }
                )
            
            # Breakdown below lower BB
            elif bb_lower is not None and price < bb_lower:
                return OrderIntent(
                    symbol=symbol,
                    action="SELL",
                    qty=None,
                    reason="high_vol_breakout_short",
                    strategy_code=self.id,
                    confidence=0.65,
                    metadata={
                        "atr_pct": atr_pct,
                        "regime": "high_vol",
                        "setup": "breakdown"
                    }
                )
        
        return None
