"""
Tests for EMA 20/50 Intraday Strategy v2 with MarketContext gating.
"""

import unittest
from datetime import datetime, timezone
from unittest.mock import Mock

from core.strategy_engine_v2 import StrategyState
from core.market_context import (
    IndexTrendState,
    VolatilityState,
    BreadthState,
    MarketContextSnapshot,
)
from strategies.ema20_50_intraday_v2 import EMA2050IntradayV2
from strategies.base import Decision


class TestEMA2050IntradayV2MarketContext(unittest.TestCase):
    """Test EMA 20/50 strategy with MarketContext gating."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            "ema_fast": 20,
            "ema_slow": 50,
            "use_regime_filter": True,
            "min_confidence": 0.0,
        }
        self.state = StrategyState()
        self.strategy = EMA2050IntradayV2(config=self.config, strategy_state=self.state)
    
    def _create_candle(self, close: float = 24500.0) -> dict:
        """Create a test candle."""
        return {
            "open": close - 10.0,
            "high": close + 20.0,
            "low": close - 20.0,
            "close": close,
            "volume": 100000,
        }
    
    def _create_indicators(self, ema20: float, ema50: float, trend: str = "up") -> dict:
        """Create test indicators."""
        return {
            "ema20": ema20,
            "ema50": ema50,
            "ema200": ema20 - 100.0,  # Below current for bullish bias
            "rsi14": 55.0,
            "trend": trend,
        }
    
    def _create_market_context(
        self,
        nifty_regime: str = "BULL",
        vol_regime: str = "NORMAL",
        nifty_rvol: float = 1.0,
    ) -> MarketContextSnapshot:
        """Create a test MarketContextSnapshot."""
        return MarketContextSnapshot(
            as_of=datetime.now(timezone.utc),
            index_trend={
                "NIFTY": IndexTrendState(
                    symbol="NIFTY",
                    ema_fast=24500.0,
                    ema_slow=24450.0,
                    regime=nifty_regime,
                ),
                "BANKNIFTY": IndexTrendState(
                    symbol="BANKNIFTY",
                    ema_fast=52000.0,
                    ema_slow=51900.0,
                    regime="BULL",
                ),
            },
            volatility=VolatilityState(
                vix_spot=15.5,
                realized_vol_20d=0.12,
                regime=vol_regime,
            ),
            breadth=BreadthState(
                advances=25,
                declines=20,
                unchanged=5,
            ),
            rvol_index={
                "NIFTY": nifty_rvol,
                "BANKNIFTY": 1.0,
            },
            session_phase="OPEN",
            valid=True,
            errors=[],
        )
    
    def test_buy_allowed_in_bull_regime(self):
        """Test that BUY signals are allowed in BULL regime."""
        # Create a bullish signal (EMA20 > EMA50)
        candle = self._create_candle(close=24500.0)
        indicators = self._create_indicators(ema20=24500.0, ema50=24450.0, trend="up")
        
        # Add BULL market context
        market_context = self._create_market_context(nifty_regime="BULL", nifty_rvol=1.2)
        indicators["market_context"] = market_context
        
        # Update previous state to trigger crossover
        self.strategy._prev_state["UNKNOWN"] = {
            "fast_above_slow": False,  # Was below
            "ema_fast": 24440.0,
            "ema_slow": 24450.0,
        }
        
        decision = self.strategy.generate_signal(candle, {}, indicators)
        
        # Should generate BUY signal
        self.assertIsNotNone(decision)
        self.assertEqual(decision.action, "BUY")
        self.assertNotIn("market_context", decision.reason)
    
    def test_buy_blocked_in_bear_regime(self):
        """Test that BUY signals are blocked in BEAR regime."""
        # Create a bullish signal (EMA20 > EMA50)
        candle = self._create_candle(close=24500.0)
        indicators = self._create_indicators(ema20=24500.0, ema50=24450.0, trend="up")
        
        # Add BEAR market context
        market_context = self._create_market_context(nifty_regime="BEAR", nifty_rvol=1.2)
        indicators["market_context"] = market_context
        
        # Update previous state to trigger crossover
        self.strategy._prev_state["UNKNOWN"] = {
            "fast_above_slow": False,  # Was below
            "ema_fast": 24440.0,
            "ema_slow": 24450.0,
        }
        
        decision = self.strategy.generate_signal(candle, {}, indicators)
        
        # Should block BUY signal
        self.assertIsNotNone(decision)
        self.assertEqual(decision.action, "HOLD")
        self.assertIn("market_context", decision.reason)
        self.assertIn("BEAR", decision.reason)
        self.assertIn("no_longs", decision.reason)
    
    def test_buy_allowed_in_range_up_regime(self):
        """Test that BUY signals are allowed in RANGE_UP regime."""
        # Create a bullish signal
        candle = self._create_candle(close=24500.0)
        indicators = self._create_indicators(ema20=24500.0, ema50=24450.0, trend="up")
        
        # Add RANGE_UP market context
        market_context = self._create_market_context(nifty_regime="RANGE_UP", nifty_rvol=1.2)
        indicators["market_context"] = market_context
        
        # Update previous state to trigger crossover
        self.strategy._prev_state["UNKNOWN"] = {
            "fast_above_slow": False,
            "ema_fast": 24440.0,
            "ema_slow": 24450.0,
        }
        
        decision = self.strategy.generate_signal(candle, {}, indicators)
        
        # Should generate BUY signal
        self.assertIsNotNone(decision)
        self.assertEqual(decision.action, "BUY")
    
    def test_sell_allowed_in_bear_regime(self):
        """Test that SELL signals are allowed in BEAR regime."""
        # Create a bearish signal (EMA20 < EMA50)
        candle = self._create_candle(close=24300.0)
        indicators = self._create_indicators(ema20=24300.0, ema50=24350.0, trend="down")
        
        # Add BEAR market context
        market_context = self._create_market_context(nifty_regime="BEAR", nifty_rvol=1.2)
        indicators["market_context"] = market_context
        
        # Update previous state to trigger crossover
        self.strategy._prev_state["UNKNOWN"] = {
            "fast_above_slow": True,  # Was above
            "ema_fast": 24360.0,
            "ema_slow": 24350.0,
        }
        
        decision = self.strategy.generate_signal(candle, {}, indicators)
        
        # Should generate SELL signal
        self.assertIsNotNone(decision)
        self.assertEqual(decision.action, "SELL")
        self.assertNotIn("market_context", decision.reason)
    
    def test_sell_blocked_in_bull_regime(self):
        """Test that SELL signals are blocked in BULL regime."""
        # Create a bearish signal (EMA20 < EMA50)
        candle = self._create_candle(close=24300.0)
        indicators = self._create_indicators(ema20=24300.0, ema50=24350.0, trend="down")
        
        # Add BULL market context
        market_context = self._create_market_context(nifty_regime="BULL", nifty_rvol=1.2)
        indicators["market_context"] = market_context
        
        # Update previous state to trigger crossover
        self.strategy._prev_state["UNKNOWN"] = {
            "fast_above_slow": True,  # Was above
            "ema_fast": 24360.0,
            "ema_slow": 24350.0,
        }
        
        decision = self.strategy.generate_signal(candle, {}, indicators)
        
        # Should block SELL signal
        self.assertIsNotNone(decision)
        self.assertEqual(decision.action, "HOLD")
        self.assertIn("market_context", decision.reason)
        self.assertIn("BULL", decision.reason)
        self.assertIn("no_shorts", decision.reason)
    
    def test_all_entries_blocked_in_panic_regime(self):
        """Test that all entries are blocked in PANIC volatility regime."""
        # Create a bullish signal
        candle = self._create_candle(close=24500.0)
        indicators = self._create_indicators(ema20=24500.0, ema50=24450.0, trend="up")
        
        # Add PANIC volatility market context
        market_context = self._create_market_context(
            nifty_regime="BULL",  # Even in BULL regime
            vol_regime="PANIC",
            nifty_rvol=1.2,
        )
        indicators["market_context"] = market_context
        
        # Update previous state to trigger crossover
        self.strategy._prev_state["UNKNOWN"] = {
            "fast_above_slow": False,
            "ema_fast": 24440.0,
            "ema_slow": 24450.0,
        }
        
        decision = self.strategy.generate_signal(candle, {}, indicators)
        
        # Should block all entries
        self.assertIsNotNone(decision)
        self.assertEqual(decision.action, "HOLD")
        self.assertIn("market_context", decision.reason)
        self.assertIn("PANIC", decision.reason)
        self.assertIn("block_entries", decision.reason)
    
    def test_entries_blocked_low_rvol(self):
        """Test that entries are blocked when rvol < 0.5."""
        # Create a bullish signal
        candle = self._create_candle(close=24500.0)
        indicators = self._create_indicators(ema20=24500.0, ema50=24450.0, trend="up")
        
        # Add low rvol market context
        market_context = self._create_market_context(
            nifty_regime="BULL",
            vol_regime="NORMAL",
            nifty_rvol=0.4,  # Below 0.5 threshold
        )
        indicators["market_context"] = market_context
        
        # Update previous state to trigger crossover
        self.strategy._prev_state["UNKNOWN"] = {
            "fast_above_slow": False,
            "ema_fast": 24440.0,
            "ema_slow": 24450.0,
        }
        
        decision = self.strategy.generate_signal(candle, {}, indicators)
        
        # Should block entry due to low rvol
        self.assertIsNotNone(decision)
        self.assertEqual(decision.action, "HOLD")
        self.assertIn("market_context", decision.reason)
        self.assertIn("low_rvol", decision.reason)
        self.assertIn("0.40", decision.reason)
    
    def test_signal_without_market_context(self):
        """Test that strategy still works without market context (backward compatibility)."""
        # Create a bullish signal
        candle = self._create_candle(close=24500.0)
        indicators = self._create_indicators(ema20=24500.0, ema50=24450.0, trend="up")
        
        # No market context provided
        
        # Update previous state to trigger crossover
        self.strategy._prev_state["UNKNOWN"] = {
            "fast_above_slow": False,
            "ema_fast": 24440.0,
            "ema_slow": 24450.0,
        }
        
        decision = self.strategy.generate_signal(candle, {}, indicators)
        
        # Should still generate BUY signal (no market context filters applied)
        self.assertIsNotNone(decision)
        self.assertEqual(decision.action, "BUY")
    
    def test_determine_index_alias(self):
        """Test index alias determination from symbol."""
        # NIFTY symbols
        self.assertEqual(self.strategy._determine_index_alias("NIFTY"), "NIFTY")
        self.assertEqual(self.strategy._determine_index_alias("NIFTY50"), "NIFTY")
        self.assertEqual(self.strategy._determine_index_alias("RELIANCE"), "NIFTY")
        
        # BANKNIFTY symbols
        self.assertEqual(self.strategy._determine_index_alias("BANKNIFTY"), "BANKNIFTY")
        self.assertEqual(self.strategy._determine_index_alias("BANKNFT"), "BANKNIFTY")
        self.assertEqual(self.strategy._determine_index_alias("BANKNIFTY24DEC52000CE"), "BANKNIFTY")


if __name__ == '__main__':
    unittest.main()
