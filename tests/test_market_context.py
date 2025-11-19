"""
Tests for MarketContext subsystem.
"""

import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from core.market_context import (
    IndexTrendState,
    VolatilityState,
    BreadthState,
    MarketContextSnapshot,
    MarketContext,
)


class TestIndexTrendState(unittest.TestCase):
    """Test IndexTrendState dataclass."""
    
    def test_index_trend_state_creation(self):
        """Test creating an IndexTrendState."""
        state = IndexTrendState(
            symbol="NIFTY",
            ema_fast=24500.0,
            ema_slow=24450.0,
            regime="BULL"
        )
        
        self.assertEqual(state.symbol, "NIFTY")
        self.assertEqual(state.ema_fast, 24500.0)
        self.assertEqual(state.ema_slow, 24450.0)
        self.assertEqual(state.regime, "BULL")
    
    def test_index_trend_state_to_dict(self):
        """Test converting IndexTrendState to dict."""
        state = IndexTrendState(
            symbol="BANKNIFTY",
            ema_fast=52000.0,
            ema_slow=51900.0,
            regime="RANGE_UP"
        )
        
        d = state.to_dict()
        self.assertEqual(d["symbol"], "BANKNIFTY")
        self.assertEqual(d["ema_fast"], 52000.0)
        self.assertEqual(d["ema_slow"], 51900.0)
        self.assertEqual(d["regime"], "RANGE_UP")


class TestVolatilityState(unittest.TestCase):
    """Test VolatilityState dataclass."""
    
    def test_volatility_state_creation(self):
        """Test creating a VolatilityState."""
        state = VolatilityState(
            vix_spot=15.5,
            realized_vol_20d=0.12,
            regime="NORMAL"
        )
        
        self.assertEqual(state.vix_spot, 15.5)
        self.assertAlmostEqual(state.realized_vol_20d, 0.12, places=2)
        self.assertEqual(state.regime, "NORMAL")
    
    def test_volatility_state_to_dict(self):
        """Test converting VolatilityState to dict."""
        state = VolatilityState(
            vix_spot=35.0,
            realized_vol_20d=0.45,
            regime="PANIC"
        )
        
        d = state.to_dict()
        self.assertEqual(d["vix_spot"], 35.0)
        self.assertAlmostEqual(d["realized_vol_20d"], 0.45, places=2)
        self.assertEqual(d["regime"], "PANIC")


class TestBreadthState(unittest.TestCase):
    """Test BreadthState dataclass."""
    
    def test_breadth_state_creation(self):
        """Test creating a BreadthState."""
        state = BreadthState(
            advances=30,
            declines=20,
            unchanged=0
        )
        
        self.assertEqual(state.advances, 30)
        self.assertEqual(state.declines, 20)
        self.assertEqual(state.unchanged, 0)
    
    def test_adv_decl_ratio(self):
        """Test advance/decline ratio calculation."""
        # Normal case
        state = BreadthState(advances=25, declines=25, unchanged=0)
        self.assertAlmostEqual(state.adv_decl_ratio, 1.0, places=2)
        
        # More advances
        state = BreadthState(advances=30, declines=20, unchanged=0)
        self.assertAlmostEqual(state.adv_decl_ratio, 1.5, places=2)
        
        # No declines
        state = BreadthState(advances=10, declines=0, unchanged=0)
        self.assertEqual(state.adv_decl_ratio, 999.0)
        
        # No advances or declines
        state = BreadthState(advances=0, declines=0, unchanged=50)
        self.assertEqual(state.adv_decl_ratio, 1.0)
    
    def test_breadth_state_to_dict(self):
        """Test converting BreadthState to dict."""
        state = BreadthState(advances=28, declines=22, unchanged=0)
        
        d = state.to_dict()
        self.assertEqual(d["advances"], 28)
        self.assertEqual(d["declines"], 22)
        self.assertEqual(d["unchanged"], 0)
        self.assertIn("adv_decl_ratio", d)
        self.assertAlmostEqual(d["adv_decl_ratio"], 1.27, places=1)


class TestMarketContextSnapshot(unittest.TestCase):
    """Test MarketContextSnapshot dataclass."""
    
    def test_snapshot_creation(self):
        """Test creating a MarketContextSnapshot."""
        snapshot = MarketContextSnapshot(
            as_of=datetime.now(timezone.utc),
            session_phase="OPEN"
        )
        
        self.assertEqual(snapshot.session_phase, "OPEN")
        self.assertTrue(snapshot.valid)
        self.assertEqual(len(snapshot.errors), 0)
    
    def test_snapshot_to_dict(self):
        """Test converting snapshot to dict."""
        now = datetime.now(timezone.utc)
        
        snapshot = MarketContextSnapshot(
            as_of=now,
            index_trend={
                "NIFTY": IndexTrendState(symbol="NIFTY", ema_fast=24500.0, ema_slow=24450.0, regime="BULL")
            },
            volatility=VolatilityState(vix_spot=15.5, realized_vol_20d=0.12, regime="NORMAL"),
            breadth=BreadthState(advances=25, declines=20, unchanged=5),
            rvol_index={"NIFTY": 1.2},
            session_phase="OPEN",
            valid=True,
            errors=[]
        )
        
        d = snapshot.to_dict()
        self.assertIn("as_of", d)
        self.assertIn("index_trend", d)
        self.assertIn("volatility", d)
        self.assertIn("breadth", d)
        self.assertIn("rvol_index", d)
        self.assertEqual(d["session_phase"], "OPEN")
        self.assertTrue(d["valid"])
        self.assertEqual(len(d["errors"]), 0)
        
        # Check nested structures
        self.assertIn("NIFTY", d["index_trend"])
        self.assertEqual(d["index_trend"]["NIFTY"]["regime"], "BULL")
        self.assertEqual(d["volatility"]["regime"], "NORMAL")
        self.assertEqual(d["breadth"]["advances"], 25)


class TestMarketContext(unittest.TestCase):
    """Test MarketContext class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            "index_symbols": ["NIFTY", "BANKNIFTY"],
            "ema_fast_period": 20,
            "ema_slow_period": 50,
        }
    
    def test_context_initialization(self):
        """Test MarketContext initialization."""
        context = MarketContext(config=self.config)
        
        self.assertIsNone(context.snapshot)
        self.assertEqual(context.index_symbols, ["NIFTY", "BANKNIFTY"])
        self.assertEqual(context.ema_fast_period, 20)
        self.assertEqual(context.ema_slow_period, 50)
    
    def test_classify_trend_regime(self):
        """Test trend regime classification."""
        context = MarketContext(config=self.config)
        
        # Strong bullish trend
        regime = context._classify_trend_regime(24500.0, 24300.0, 24500.0)
        self.assertEqual(regime, "BULL")
        
        # Weak bullish trend (range)
        regime = context._classify_trend_regime(24500.0, 24490.0, 24500.0)
        self.assertEqual(regime, "RANGE_UP")
        
        # Strong bearish trend
        regime = context._classify_trend_regime(24300.0, 24500.0, 24300.0)
        self.assertEqual(regime, "BEAR")
        
        # Weak bearish trend (range)
        regime = context._classify_trend_regime(24490.0, 24500.0, 24490.0)
        self.assertEqual(regime, "RANGE_DOWN")
        
        # Invalid EMAs
        regime = context._classify_trend_regime(0.0, 0.0, 24500.0)
        self.assertEqual(regime, "UNKNOWN")
    
    def test_classify_volatility_regime_vix(self):
        """Test volatility regime classification using VIX."""
        context = MarketContext(config=self.config)
        
        # CALM
        regime = context._classify_volatility_regime(10.0, 0.0)
        self.assertEqual(regime, "CALM")
        
        # NORMAL
        regime = context._classify_volatility_regime(15.0, 0.0)
        self.assertEqual(regime, "NORMAL")
        
        # HIGH
        regime = context._classify_volatility_regime(22.0, 0.0)
        self.assertEqual(regime, "HIGH")
        
        # PANIC
        regime = context._classify_volatility_regime(40.0, 0.0)
        self.assertEqual(regime, "PANIC")
    
    def test_classify_volatility_regime_realized(self):
        """Test volatility regime classification using realized volatility."""
        context = MarketContext(config=self.config)
        
        # Fallback to realized vol when VIX is unavailable
        # CALM
        regime = context._classify_volatility_regime(0.0, 0.08)
        self.assertEqual(regime, "CALM")
        
        # NORMAL
        regime = context._classify_volatility_regime(0.0, 0.12)
        self.assertEqual(regime, "NORMAL")
        
        # HIGH
        regime = context._classify_volatility_regime(0.0, 0.28)
        self.assertEqual(regime, "HIGH")
        
        # PANIC
        regime = context._classify_volatility_regime(0.0, 0.45)
        self.assertEqual(regime, "PANIC")
    
    def test_compute_session_phase(self):
        """Test session phase computation."""
        context = MarketContext(config=self.config)
        
        # Create test times in UTC (IST = UTC + 5:30)
        # 3:30 AM UTC = 9:00 AM IST (Pre-open)
        pre_open = datetime(2025, 11, 19, 3, 30, 0, tzinfo=timezone.utc)
        phase = context._compute_session_phase(pre_open)
        self.assertEqual(phase, "PRE_OPEN")
        
        # 5:00 AM UTC = 10:30 AM IST (Open)
        open_time = datetime(2025, 11, 19, 5, 0, 0, tzinfo=timezone.utc)
        phase = context._compute_session_phase(open_time)
        self.assertEqual(phase, "OPEN")
        
        # 11:00 AM UTC = 4:30 PM IST (Closed)
        closed_time = datetime(2025, 11, 19, 11, 0, 0, tzinfo=timezone.utc)
        phase = context._compute_session_phase(closed_time)
        self.assertEqual(phase, "CLOSED")
    
    @patch('core.market_context.MarketContext._fetch_bars')
    def test_refresh_without_kite(self, mock_fetch_bars):
        """Test refresh() without Kite client (graceful degradation)."""
        # Mock empty bars
        mock_fetch_bars.return_value = []
        
        context = MarketContext(kite=None, config=self.config)
        snapshot = context.refresh()
        
        # Should still create a snapshot even without data
        self.assertIsNotNone(snapshot)
        self.assertIsInstance(snapshot, MarketContextSnapshot)
        
        # Snapshot might still be valid with default values
        # The system is designed to be robust with graceful fallback
        # Check that regimes are set to UNKNOWN when data is unavailable
        for index_state in snapshot.index_trend.values():
            self.assertEqual(index_state.regime, "UNKNOWN")


if __name__ == '__main__':
    unittest.main()
