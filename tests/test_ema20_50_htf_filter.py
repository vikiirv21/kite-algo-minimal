"""
Tests for EMA 20/50 Intraday Strategy v2 with HTF (Higher-Timeframe) filter.
"""

import unittest
from datetime import datetime, timezone
from unittest.mock import Mock

from core.strategy_engine_v2 import StrategyState
from strategies.ema20_50_intraday_v2 import EMA2050IntradayV2
from strategies.base import Decision


class TestEMA2050IntradayV2HTFFilter(unittest.TestCase):
    """Test EMA 20/50 strategy with HTF filter."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            "ema_fast": 20,
            "ema_slow": 50,
            "use_regime_filter": True,
            "min_confidence": 0.0,
            "use_htf_filter": True,
            "htf_min_score": 0.6,
            "htf_conflict_action": "suppress",
            "htf_confidence_reduction": 0.3,
        }
        self.state = StrategyState()
        self.strategy = EMA2050IntradayV2(config=self.config, strategy_state=self.state)
        self.strategy.config["current_symbol"] = "NIFTY"
    
    def _create_candle(self, close: float = 24500.0) -> dict:
        """Create a test candle."""
        return {
            "open": close - 10.0,
            "high": close + 20.0,
            "low": close - 20.0,
            "close": close,
            "volume": 100000,
        }
    
    def _create_bullish_indicators(self) -> dict:
        """Create bullish indicators (EMA20 > EMA50)."""
        return {
            "ema20": 24600.0,
            "ema50": 24400.0,
            "ema200": 24000.0,
            "rsi14": 55.0,
            "trend": "up",
        }
    
    def _create_bearish_indicators(self) -> dict:
        """Create bearish indicators (EMA20 < EMA50)."""
        return {
            "ema20": 24400.0,
            "ema50": 24600.0,
            "ema200": 25000.0,
            "rsi14": 45.0,
            "trend": "down",
        }
    
    def test_htf_filter_disabled_by_default(self):
        """Test that HTF filter is disabled by default."""
        config_no_htf = {
            "ema_fast": 20,
            "ema_slow": 50,
        }
        state = StrategyState()
        strategy = EMA2050IntradayV2(config=config_no_htf, strategy_state=state)
        
        self.assertFalse(strategy.use_htf_filter)
    
    def test_htf_filter_enabled_via_config(self):
        """Test that HTF filter can be enabled via config."""
        self.assertTrue(self.strategy.use_htf_filter)
        self.assertEqual(self.strategy.htf_min_score, 0.6)
        self.assertEqual(self.strategy.htf_conflict_action, "suppress")
    
    def test_long_signal_blocked_when_htf_bearish(self):
        """Test that long signal is blocked when HTF bias is bearish."""
        candle = self._create_candle()
        indicators = self._create_bullish_indicators()
        
        # Simulate bullish crossover
        self.strategy._prev_state["NIFTY"] = {"fast_above_slow": False}
        
        # HTF context shows bearish bias
        context = {
            "htf_trend": {
                "htf_bias": "bearish",
                "aligned": True,
                "score": 0.8,
            }
        }
        
        decision = self.strategy.generate_signal(candle, {}, indicators, context)
        
        self.assertEqual(decision.action, "HOLD")
        self.assertIn("htf_bearish_conflicts_long", decision.reason)
    
    def test_short_signal_blocked_when_htf_bullish(self):
        """Test that short signal is blocked when HTF bias is bullish."""
        candle = self._create_candle()
        indicators = self._create_bearish_indicators()
        
        # Simulate bearish crossover
        self.strategy._prev_state["NIFTY"] = {"fast_above_slow": True}
        
        # HTF context shows bullish bias
        context = {
            "htf_trend": {
                "htf_bias": "bullish",
                "aligned": True,
                "score": 0.8,
            }
        }
        
        decision = self.strategy.generate_signal(candle, {}, indicators, context)
        
        self.assertEqual(decision.action, "HOLD")
        self.assertIn("htf_bullish_conflicts_short", decision.reason)
    
    def test_long_signal_allowed_when_htf_bullish(self):
        """Test that long signal is allowed when HTF bias is bullish."""
        candle = self._create_candle()
        indicators = self._create_bullish_indicators()
        
        # Simulate bullish crossover
        self.strategy._prev_state["NIFTY"] = {"fast_above_slow": False}
        
        # HTF context shows bullish bias
        context = {
            "htf_trend": {
                "htf_bias": "bullish",
                "aligned": True,
                "score": 0.8,
            }
        }
        
        decision = self.strategy.generate_signal(candle, {}, indicators, context)
        
        # Signal should be BUY (allowed) since HTF aligns
        self.assertEqual(decision.action, "BUY")
    
    def test_short_signal_allowed_when_htf_bearish(self):
        """Test that short signal is allowed when HTF bias is bearish."""
        candle = self._create_candle()
        indicators = self._create_bearish_indicators()
        
        # Simulate bearish crossover
        self.strategy._prev_state["NIFTY"] = {"fast_above_slow": True}
        
        # HTF context shows bearish bias
        context = {
            "htf_trend": {
                "htf_bias": "bearish",
                "aligned": True,
                "score": 0.8,
            }
        }
        
        decision = self.strategy.generate_signal(candle, {}, indicators, context)
        
        # Signal should be SELL (allowed) since HTF aligns
        self.assertEqual(decision.action, "SELL")
    
    def test_signal_allowed_when_htf_sideways(self):
        """Test that signal is allowed with slight reduction when HTF is sideways."""
        candle = self._create_candle()
        indicators = self._create_bullish_indicators()
        
        # Simulate bullish crossover
        self.strategy._prev_state["NIFTY"] = {"fast_above_slow": False}
        
        # HTF context shows sideways bias
        context = {
            "htf_trend": {
                "htf_bias": "sideways",
                "aligned": False,
                "score": 0.3,
            }
        }
        
        decision = self.strategy.generate_signal(candle, {}, indicators, context)
        
        # Signal should be BUY (allowed) since sideways doesn't block
        self.assertEqual(decision.action, "BUY")
        self.assertIn("htf_sideways_caution", decision.reason)
    
    def test_reduce_confidence_mode(self):
        """Test that htf_conflict_action='reduce_confidence' reduces confidence instead of blocking."""
        config = {
            "ema_fast": 20,
            "ema_slow": 50,
            "use_regime_filter": True,
            "min_confidence": 0.0,
            "use_htf_filter": True,
            "htf_min_score": 0.6,
            "htf_conflict_action": "reduce_confidence",
            "htf_confidence_reduction": 0.3,
        }
        state = StrategyState()
        strategy = EMA2050IntradayV2(config=config, strategy_state=state)
        strategy.config["current_symbol"] = "NIFTY"
        
        candle = self._create_candle()
        indicators = self._create_bullish_indicators()
        
        # Simulate bullish crossover
        strategy._prev_state["NIFTY"] = {"fast_above_slow": False}
        
        # HTF context shows bearish bias (conflict)
        context = {
            "htf_trend": {
                "htf_bias": "bearish",
                "aligned": True,
                "score": 0.8,
            }
        }
        
        decision = strategy.generate_signal(candle, {}, indicators, context)
        
        # Signal should be BUY (not blocked) but with reduced confidence
        self.assertEqual(decision.action, "BUY")
        self.assertIn("htf_conflict_reduced", decision.reason)
        # Confidence should be reduced
        self.assertLess(decision.confidence, 1.0)
    
    def test_htf_filter_disabled_no_impact(self):
        """Test that when HTF filter is disabled, signals are not affected by HTF context."""
        config = {
            "ema_fast": 20,
            "ema_slow": 50,
            "use_htf_filter": False,  # Disabled
        }
        state = StrategyState()
        strategy = EMA2050IntradayV2(config=config, strategy_state=state)
        strategy.config["current_symbol"] = "NIFTY"
        
        candle = self._create_candle()
        indicators = self._create_bullish_indicators()
        
        # Simulate bullish crossover
        strategy._prev_state["NIFTY"] = {"fast_above_slow": False}
        
        # HTF context shows bearish bias (would conflict if enabled)
        context = {
            "htf_trend": {
                "htf_bias": "bearish",
                "aligned": True,
                "score": 0.8,
            }
        }
        
        decision = strategy.generate_signal(candle, {}, indicators, context)
        
        # Signal should still be BUY since HTF filter is disabled
        self.assertEqual(decision.action, "BUY")
        self.assertNotIn("htf", decision.reason.lower())
    
    def test_no_htf_context_no_impact(self):
        """Test that when no HTF context is provided, signals are not affected."""
        candle = self._create_candle()
        indicators = self._create_bullish_indicators()
        
        # Simulate bullish crossover
        self.strategy._prev_state["NIFTY"] = {"fast_above_slow": False}
        
        # No HTF context
        context = {}
        
        decision = self.strategy.generate_signal(candle, {}, indicators, context)
        
        # Signal should be BUY since no HTF context to filter
        self.assertEqual(decision.action, "BUY")
    
    def test_htf_aligned_boosts_confidence(self):
        """Test that aligned HTF with high score boosts confidence."""
        candle = self._create_candle()
        indicators = self._create_bullish_indicators()
        
        # Simulate bullish crossover
        self.strategy._prev_state["NIFTY"] = {"fast_above_slow": False}
        
        # HTF context shows strong bullish alignment
        context = {
            "htf_trend": {
                "htf_bias": "bullish",
                "aligned": True,
                "score": 0.9,  # High score
            }
        }
        
        decision = self.strategy.generate_signal(candle, {}, indicators, context)
        
        self.assertEqual(decision.action, "BUY")
        self.assertIn("htf_aligned_boost", decision.reason)


if __name__ == "__main__":
    unittest.main()
