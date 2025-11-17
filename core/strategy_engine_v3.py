"""
Strategy Engine v3

Multi-strategy fusion engine with multi-timeframe confirmation,
unified indicator bundles, and playbook setup classification.

Features:
- Dynamic strategy loading from registry
- Multi-timeframe (5m + 15m) confirmation
- Signal fusion with confidence scoring
- Setup classification (trend follow, pullback, breakout)
- EventBus integration for signal logging
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core import indicators
from core.strategy_engine_v2 import OrderIntent
from core.strategies_v3 import StrategyV3Base

# Import strategy implementations
from core.strategies_v3.ema20_50 import EMA2050Strategy
from core.strategies_v3.trend_strategy import TrendStrategy
from core.strategies_v3.rsi_pullback import RSIPullbackStrategy
from core.strategies_v3.vwap_filter import VWAPFilterStrategy
from core.strategies_v3.vol_regime import VolRegimeStrategy
from core.strategies_v3.htf_trend import HTFTrendStrategy

logger = logging.getLogger(__name__)

# Strategy registry mapping IDs to classes
STRATEGY_REGISTRY_V3 = {
    "ema20_50": EMA2050Strategy,
    "trend": TrendStrategy,
    "rsi_pullback": RSIPullbackStrategy,
    "vwap_filter": VWAPFilterStrategy,
    "vol_regime": VolRegimeStrategy,
    "htf_trend": HTFTrendStrategy,
}


class StrategyEngineV3:
    """
    Strategy Engine v3 with multi-strategy fusion and multi-timeframe confirmation.
    
    Key features:
    - Loads strategies dynamically from configuration
    - Computes unified indicator bundle
    - Evaluates multiple strategies and fuses their signals
    - Multi-timeframe confirmation (primary + secondary)
    - Playbook-based setup classification
    - EventBus integration for signal logging
    """
    
    def __init__(self, cfg: Dict[str, Any], bus: Optional[Any] = None):
        """
        Initialize Strategy Engine v3.
        
        Args:
            cfg: Configuration dictionary with strategy_engine_v3 section
            bus: Optional EventBus instance for signal publishing
        """
        self.cfg = cfg
        self.bus = bus
        
        # Load timeframe configuration
        self.primary_tf = cfg.get("primary_tf", "5m")
        self.secondary_tf = cfg.get("secondary_tf", "15m")
        
        # Load playbook definitions
        self.playbooks = cfg.get("playbooks", {})
        
        # Load strategy registry
        self.strategies: List[StrategyV3Base] = []
        strategy_configs = cfg.get("strategies", [])
        
        for strat_cfg in strategy_configs:
            if isinstance(strat_cfg, dict):
                strategy_id = strat_cfg.get("id")
                enabled = strat_cfg.get("enabled", True)
            elif isinstance(strat_cfg, str):
                strategy_id = strat_cfg
                enabled = True
                strat_cfg = {"id": strategy_id}
            else:
                logger.warning("Invalid strategy config: %s", strat_cfg)
                continue
            
            if not enabled:
                logger.info("Strategy %s is disabled, skipping", strategy_id)
                continue
            
            # Get strategy class from registry
            strategy_class = STRATEGY_REGISTRY_V3.get(strategy_id)
            if strategy_class is None:
                logger.warning("Unknown strategy ID: %s", strategy_id)
                continue
            
            # Instantiate strategy
            try:
                strategy = strategy_class(strat_cfg)
                self.strategies.append(strategy)
                logger.info("Loaded strategy: %s", strategy_id)
            except Exception as e:
                logger.error("Failed to load strategy %s: %s", strategy_id, e)
        
        logger.info(
            "StrategyEngineV3 initialized with %d strategies (primary=%s, secondary=%s)",
            len(self.strategies),
            self.primary_tf,
            self.secondary_tf
        )
    
    def evaluate(
        self,
        symbol: str,
        ts: str,
        price: float,
        md: Dict[str, Any]
    ) -> OrderIntent:
        """
        Evaluate all strategies and fuse signals.
        
        Args:
            symbol: Trading symbol
            ts: Timestamp (ISO format)
            price: Current price
            md: Market data dictionary with series for primary and secondary timeframes
        
        Returns:
            Final fused OrderIntent (may be HOLD with reason)
        """
        # Compute indicator bundle for primary timeframe
        primary_series = md.get("primary_series", {})
        primary_bundle = self._compute_bundle(primary_series)
        
        # Compute indicator bundle for secondary timeframe (if available)
        secondary_series = md.get("secondary_series", {})
        secondary_bundle = self._compute_bundle(secondary_series) if secondary_series else {}
        
        # Add HTF indicators to primary bundle with "htf_" prefix
        for key, value in secondary_bundle.items():
            primary_bundle[f"htf_{key}"] = value
        
        # Run each strategy to get candidate OrderIntents
        candidates: List[OrderIntent] = []
        
        for strategy in self.strategies:
            try:
                intent = strategy.generate(symbol, ts, price, md, primary_bundle)
                if intent is not None:
                    candidates.append(intent)
                    logger.debug(
                        "Strategy %s generated: %s (confidence=%.2f)",
                        strategy.id,
                        intent.action,
                        intent.confidence
                    )
            except Exception as e:
                logger.error("Strategy %s failed: %s", strategy.id, e, exc_info=True)
        
        # Publish raw signals event
        if self.bus:
            try:
                self.bus.publish("signals.raw", {
                    "symbol": symbol,
                    "ts": ts,
                    "price": price,
                    "candidates": [c.to_dict() for c in candidates]
                })
            except Exception as e:
                logger.debug("Failed to publish raw signals: %s", e)
        
        # Apply filters
        filtered_candidates = self._apply_filters(
            candidates,
            symbol,
            price,
            primary_bundle,
            secondary_bundle
        )
        
        # Fuse signals
        final_intent = self._fuse_signals(
            filtered_candidates,
            symbol,
            ts,
            price,
            primary_bundle,
            secondary_bundle
        )
        
        # Add indicator bundle to metadata
        final_intent.metadata["indicators"] = primary_bundle
        
        # Publish fused signal event
        if self.bus:
            try:
                self.bus.publish("signals.fused", {
                    "symbol": symbol,
                    "ts": ts,
                    "price": price,
                    "intent": final_intent.to_dict()
                })
            except Exception as e:
                logger.debug("Failed to publish fused signal: %s", e)
        
        return final_intent
    
    def _compute_bundle(self, series: Dict[str, List[float]]) -> Dict[str, Any]:
        """
        Compute unified indicator bundle.
        
        Args:
            series: Price series dictionary (open, high, low, close, volume)
        
        Returns:
            Dictionary of computed indicators
        """
        return indicators.compute_bundle(series)
    
    def _apply_filters(
        self,
        candidates: List[OrderIntent],
        symbol: str,
        price: float,
        primary_bundle: Dict[str, Any],
        secondary_bundle: Dict[str, Any]
    ) -> List[OrderIntent]:
        """
        Apply filters to candidate signals.
        
        Filters:
        - Remove None/HOLD signals
        - Volatility regime checks
        - Trend alignment checks
        - Time filters (TODO: implement if needed)
        
        Args:
            candidates: List of candidate OrderIntents
            symbol: Trading symbol
            price: Current price
            primary_bundle: Primary timeframe indicators
            secondary_bundle: Secondary timeframe indicators
        
        Returns:
            Filtered list of OrderIntents
        """
        filtered = []
        
        for intent in candidates:
            if intent is None or intent.action == "HOLD":
                continue
            
            # Volume regime filter: check if volatility is too low/high
            atr = primary_bundle.get("atr14")
            if atr is not None and price > 0:
                atr_pct = (atr / price) * 100
                
                # Skip if volatility is extremely low (market may be stagnant)
                if atr_pct < 0.5:
                    logger.debug(
                        "Filtered %s: volatility too low (ATR=%.2f%%)",
                        intent.strategy_code,
                        atr_pct
                    )
                    continue
                
                # Skip if volatility is extremely high (may be news/event)
                if atr_pct > 10.0:
                    logger.debug(
                        "Filtered %s: volatility too high (ATR=%.2f%%)",
                        intent.strategy_code,
                        atr_pct
                    )
                    continue
            
            # Trend alignment filter: primary trend should align with signal
            trend = primary_bundle.get("trend")
            if trend:
                if intent.action == "BUY" and trend == "down":
                    logger.debug(
                        "Filtered %s: BUY signal in downtrend",
                        intent.strategy_code
                    )
                    continue
                elif intent.action == "SELL" and trend == "up":
                    logger.debug(
                        "Filtered %s: SELL signal in uptrend",
                        intent.strategy_code
                    )
                    continue
            
            filtered.append(intent)
        
        return filtered
    
    def _fuse_signals(
        self,
        candidates: List[OrderIntent],
        symbol: str,
        ts: str,
        price: float,
        primary_bundle: Dict[str, Any],
        secondary_bundle: Dict[str, Any]
    ) -> OrderIntent:
        """
        Fuse multiple candidate signals into a single OrderIntent.
        
        Fusion logic:
        1. If no candidates → HOLD with reason "no_signal_candidates"
        2. Check direction alignment across strategies
        3. Require secondary timeframe alignment
        4. Compute weighted confidence score
        5. Classify setup type
        
        Args:
            candidates: Filtered candidate OrderIntents
            symbol: Trading symbol
            ts: Timestamp
            price: Current price
            primary_bundle: Primary timeframe indicators
            secondary_bundle: Secondary timeframe indicators
        
        Returns:
            Final fused OrderIntent
        """
        # No candidates - return HOLD
        if not candidates:
            return OrderIntent(
                symbol=symbol,
                action="HOLD",
                qty=None,
                reason="no_signal_candidates",
                strategy_code="engine_v3",
                confidence=0.0,
                metadata={"fuse_reason": "no_candidates"}
            )
        
        # Separate by action
        buy_signals = [c for c in candidates if c.action == "BUY"]
        sell_signals = [c for c in candidates if c.action == "SELL"]
        
        # Check for conflicting signals
        if buy_signals and sell_signals:
            # Calculate weighted confidence for each side
            buy_weight = sum(c.confidence for c in buy_signals)
            sell_weight = sum(c.confidence for c in sell_signals)
            
            # If conflict is too close, skip trade
            if abs(buy_weight - sell_weight) < 0.3:
                return OrderIntent(
                    symbol=symbol,
                    action="HOLD",
                    qty=None,
                    reason="conflicting_signals_equal_weight",
                    strategy_code="engine_v3",
                    confidence=0.0,
                    metadata={
                        "fuse_reason": "conflict",
                        "buy_weight": buy_weight,
                        "sell_weight": sell_weight
                    }
                )
            
            # Use dominant direction
            if buy_weight > sell_weight:
                selected_signals = buy_signals
                action = "BUY"
            else:
                selected_signals = sell_signals
                action = "SELL"
        elif buy_signals:
            selected_signals = buy_signals
            action = "BUY"
        elif sell_signals:
            selected_signals = sell_signals
            action = "SELL"
        else:
            return OrderIntent(
                symbol=symbol,
                action="HOLD",
                qty=None,
                reason="no_directional_signals",
                strategy_code="engine_v3",
                confidence=0.0,
                metadata={"fuse_reason": "no_direction"}
            )
        
        # Check secondary timeframe alignment
        if secondary_bundle:
            htf_ema20 = secondary_bundle.get("ema20")
            htf_ema50 = secondary_bundle.get("ema50")
            
            if htf_ema20 is not None and htf_ema50 is not None:
                htf_trend = "up" if htf_ema20 > htf_ema50 else "down"
                
                # If HTF trend contradicts signal, reduce confidence or block
                if action == "BUY" and htf_trend == "down":
                    return OrderIntent(
                        symbol=symbol,
                        action="HOLD",
                        qty=None,
                        reason="htf_mismatch_buy_in_htf_downtrend",
                        strategy_code="engine_v3",
                        confidence=0.0,
                        metadata={
                            "fuse_reason": "htf_mismatch",
                            "htf_trend": htf_trend,
                            "signal_action": action
                        }
                    )
                elif action == "SELL" and htf_trend == "up":
                    return OrderIntent(
                        symbol=symbol,
                        action="HOLD",
                        qty=None,
                        reason="htf_mismatch_sell_in_htf_uptrend",
                        strategy_code="engine_v3",
                        confidence=0.0,
                        metadata={
                            "fuse_reason": "htf_mismatch",
                            "htf_trend": htf_trend,
                            "signal_action": action
                        }
                    )
        
        # Compute weighted average confidence
        total_confidence = sum(s.confidence for s in selected_signals)
        avg_confidence = total_confidence / len(selected_signals)
        
        # Classify setup type
        setup = self._classify_setup(selected_signals, primary_bundle)
        
        # Build reason string
        strategy_codes = [s.strategy_code for s in selected_signals]
        reason = f"fused_{action.lower()}_from_{','.join(strategy_codes)}"
        
        # Create final fused intent
        final_intent = OrderIntent(
            symbol=symbol,
            action=action,
            qty=None,  # Will be determined by position sizer
            reason=reason,
            strategy_code="engine_v3",
            confidence=avg_confidence,
            metadata={
                "setup": setup,
                "fuse_reason": "aligned",
                "num_strategies": len(selected_signals),
                "strategy_codes": strategy_codes,
                "multi_tf_status": "aligned" if secondary_bundle else "single_tf"
            }
        )
        
        logger.info(
            "Fused signal: %s %s (setup=%s, confidence=%.2f, strategies=%s)",
            symbol,
            action,
            setup,
            avg_confidence,
            strategy_codes
        )
        
        return final_intent
    
    def _classify_setup(
        self,
        signals: List[OrderIntent],
        bundle: Dict[str, Any]
    ) -> str:
        """
        Classify the setup type based on signals and indicators.
        
        Setup types:
        - TREND_FOLLOW_BREAKOUT: Strong trend + momentum + breakout
        - PULLBACK_BUY/SELL: Mean reversion in trending market
        - VOLATILITY_SQUEEZE_BREAK: Low vol followed by expansion
        - MOMENTUM: General momentum play
        
        Args:
            signals: List of selected signals
            bundle: Indicator bundle
        
        Returns:
            Setup classification string
        """
        # Check signal metadata for setup hints
        setups = [s.metadata.get("setup") for s in signals if "setup" in s.metadata]
        
        # If signals indicate pullback
        if "pullback_buy" in setups or "pullback_sell" in setups:
            return "PULLBACK_BUY" if signals[0].action == "BUY" else "PULLBACK_SELL"
        
        # If signals indicate volatility squeeze
        if "vol_squeeze_break" in setups:
            return "VOLATILITY_SQUEEZE_BREAK"
        
        # Check for trend + strong momentum
        ema9 = bundle.get("ema9")
        ema20 = bundle.get("ema20")
        ema50 = bundle.get("ema50")
        slope = bundle.get("slope10")
        
        # Trend follow breakout criteria
        if ema9 and ema20 and ema50 and slope:
            # Strong uptrend
            if ema9 > ema20 > ema50 and slope > 0:
                # Check if we have trend strategy in signals
                if any("trend" in s.strategy_code for s in signals):
                    return "TREND_FOLLOW_BREAKOUT"
            # Strong downtrend
            elif ema9 < ema20 < ema50 and slope < 0:
                if any("trend" in s.strategy_code for s in signals):
                    return "TREND_FOLLOW_BREAKOUT"
        
        # Default to momentum
        return "MOMENTUM"


__all__ = ["StrategyEngineV3"]
