"""
Test Strategy Engine v3

Basic tests for v3 engine functionality.
"""

import unittest
from datetime import datetime, timezone

from core.strategy_engine_v3 import StrategyEngineV3
from core.strategy_engine_v2 import OrderIntent


class TestStrategyEngineV3(unittest.TestCase):
    """Test cases for Strategy Engine v3."""
    
    def setUp(self):
        """Set up test configuration."""
        self.config = {
            "primary_tf": "5m",
            "secondary_tf": "15m",
            "strategies": [
                {"id": "ema20_50", "enabled": True},
                {"id": "trend", "enabled": True},
            ],
            "playbooks": {
                "trend_follow_breakout": {
                    "adx_min": 20,
                    "ema_alignment_required": True
                }
            }
        }
    
    def test_engine_initialization(self):
        """Test that engine initializes correctly."""
        engine = StrategyEngineV3(self.config)
        
        # Check basic properties
        self.assertEqual(engine.primary_tf, "5m")
        self.assertEqual(engine.secondary_tf, "15m")
        self.assertEqual(len(engine.strategies), 2)
    
    def test_strategy_loading(self):
        """Test that strategies are loaded from config."""
        engine = StrategyEngineV3(self.config)
        
        # Check strategies were loaded
        strategy_ids = [s.id for s in engine.strategies]
        self.assertIn("ema20_50", strategy_ids)
        self.assertIn("trend", strategy_ids)
    
    def test_evaluate_no_data(self):
        """Test evaluate with no market data."""
        engine = StrategyEngineV3(self.config)
        
        ts = datetime.now(timezone.utc).isoformat()
        md = {
            "primary_series": {},
            "secondary_series": {}
        }
        
        result = engine.evaluate("TEST", ts, 100.0, md)
        
        # Should return HOLD when no data
        self.assertIsInstance(result, OrderIntent)
        self.assertEqual(result.action, "HOLD")
    
    def test_evaluate_with_data(self):
        """Test evaluate with valid market data."""
        engine = StrategyEngineV3(self.config)
        
        ts = datetime.now(timezone.utc).isoformat()
        
        # Create sample data with uptrend
        closes = [100.0 + i * 0.5 for i in range(50)]
        
        md = {
            "primary_series": {
                "open": closes,
                "high": [c + 1 for c in closes],
                "low": [c - 1 for c in closes],
                "close": closes,
                "volume": [1000] * 50,
            },
            "secondary_series": {
                "open": closes,
                "high": [c + 1 for c in closes],
                "low": [c - 1 for c in closes],
                "close": closes,
                "volume": [1000] * 50,
            }
        }
        
        result = engine.evaluate("TEST", ts, closes[-1], md)
        
        # Should return an OrderIntent
        self.assertIsInstance(result, OrderIntent)
        
        # Check result has required fields
        self.assertIsNotNone(result.action)
        self.assertIsNotNone(result.confidence)
        self.assertIn("indicators", result.metadata)
    
    def test_compute_bundle(self):
        """Test indicator bundle computation."""
        engine = StrategyEngineV3(self.config)
        
        # Create sample series
        closes = [100.0 + i * 0.5 for i in range(50)]
        series = {
            "open": closes,
            "high": [c + 1 for c in closes],
            "low": [c - 1 for c in closes],
            "close": closes,
            "volume": [1000] * 50,
        }
        
        bundle = engine._compute_bundle(series)
        
        # Check indicators were computed
        self.assertIn("ema20", bundle)
        self.assertIn("ema50", bundle)
        self.assertIn("rsi14", bundle)
        self.assertIn("trend", bundle)
    
    def test_fuse_no_candidates(self):
        """Test fusion with no candidate signals."""
        engine = StrategyEngineV3(self.config)
        
        result = engine._fuse_signals(
            [],
            "TEST",
            datetime.now(timezone.utc).isoformat(),
            100.0,
            {},
            {}
        )
        
        # Should return HOLD
        self.assertEqual(result.action, "HOLD")
        self.assertEqual(result.reason, "no_signal_candidates")
    
    def test_fuse_single_candidate(self):
        """Test fusion with single candidate."""
        engine = StrategyEngineV3(self.config)
        
        candidate = OrderIntent(
            symbol="TEST",
            action="BUY",
            qty=None,
            reason="test_signal",
            strategy_code="test",
            confidence=0.8,
            metadata={"setup": "test"}
        )
        
        result = engine._fuse_signals(
            [candidate],
            "TEST",
            datetime.now(timezone.utc).isoformat(),
            100.0,
            {"ema20": 100, "ema50": 95},  # Uptrend
            {}
        )
        
        # Should return BUY
        self.assertEqual(result.action, "BUY")
        self.assertGreater(result.confidence, 0)
    
    def test_fuse_conflicting_candidates(self):
        """Test fusion with conflicting signals."""
        engine = StrategyEngineV3(self.config)
        
        buy_signal = OrderIntent(
            symbol="TEST",
            action="BUY",
            qty=None,
            reason="buy_signal",
            strategy_code="test1",
            confidence=0.7,
            metadata={}
        )
        
        sell_signal = OrderIntent(
            symbol="TEST",
            action="SELL",
            qty=None,
            reason="sell_signal",
            strategy_code="test2",
            confidence=0.7,
            metadata={}
        )
        
        result = engine._fuse_signals(
            [buy_signal, sell_signal],
            "TEST",
            datetime.now(timezone.utc).isoformat(),
            100.0,
            {},
            {}
        )
        
        # Should return HOLD when conflict is equal
        self.assertEqual(result.action, "HOLD")
        self.assertIn("conflict", result.reason.lower())
    
    def test_htf_mismatch(self):
        """Test that HTF mismatch blocks signal."""
        engine = StrategyEngineV3(self.config)
        
        buy_signal = OrderIntent(
            symbol="TEST",
            action="BUY",
            qty=None,
            reason="buy_signal",
            strategy_code="test",
            confidence=0.8,
            metadata={}
        )
        
        # HTF downtrend
        secondary_bundle = {
            "ema20": 95,
            "ema50": 100
        }
        
        result = engine._fuse_signals(
            [buy_signal],
            "TEST",
            datetime.now(timezone.utc).isoformat(),
            100.0,
            {"ema20": 100, "ema50": 95},  # Primary uptrend
            secondary_bundle  # HTF downtrend
        )
        
        # Should return HOLD due to HTF mismatch
        self.assertEqual(result.action, "HOLD")
        self.assertIn("htf_mismatch", result.reason)


if __name__ == "__main__":
    unittest.main()
