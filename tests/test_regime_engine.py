"""
Tests for Market Regime Engine v2
"""

import time
from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock

import pytest

from core.regime_engine import RegimeEngine, RegimeSnapshot


class TestRegimeSnapshot:
    """Test RegimeSnapshot dataclass."""
    
    def test_snapshot_creation(self):
        """Test creating a RegimeSnapshot."""
        snapshot = RegimeSnapshot(
            trend="up",
            volatility="high",
            structure="breakout",
            velocity=0.5,
            atr=10.0,
            slope=0.2,
            timestamp=datetime.now(timezone.utc)
        )
        
        assert snapshot.trend == "up"
        assert snapshot.volatility == "high"
        assert snapshot.structure == "breakout"
        assert snapshot.velocity == 0.5
        assert snapshot.atr == 10.0
        assert snapshot.slope == 0.2
        assert isinstance(snapshot.timestamp, datetime)


class TestRegimeEngineBasic:
    """Test basic RegimeEngine functionality."""
    
    def test_engine_disabled(self):
        """Test engine behavior when disabled."""
        config = {"regime_engine": {"enabled": False}}
        mde = Mock()
        
        engine = RegimeEngine(config, mde)
        
        # Should return neutral regime
        snapshot = engine.snapshot("NIFTY")
        assert snapshot.trend == "flat"
        assert snapshot.volatility == "medium"
        assert snapshot.structure == "none"
        assert snapshot.velocity == 0.0
        assert snapshot.atr == 0.0
        assert snapshot.slope == 0.0
    
    def test_engine_enabled_with_defaults(self):
        """Test engine with default configuration."""
        config = {"regime_engine": {"enabled": True}}
        mde = Mock()
        
        # Mock insufficient data
        mde.get_candles = Mock(return_value=[])
        mde.get_historical_data = Mock(return_value=None)
        
        engine = RegimeEngine(config, mde)
        
        assert engine.enabled is True
        assert engine.bar_period == "1m"
        assert engine.slope_period == 20
        assert engine.atr_period == 14
        assert engine.volatility_high_pct == 1.0
        assert engine.volatility_low_pct == 0.35
        assert engine.compression_pct == 0.25
    
    def test_engine_with_custom_config(self):
        """Test engine with custom configuration."""
        config = {
            "regime_engine": {
                "enabled": True,
                "bar_period": "5m",
                "slope_period": 30,
                "atr_period": 21,
                "volatility_high_pct": 1.5,
                "volatility_low_pct": 0.5,
                "compression_pct": 0.3,
            }
        }
        mde = Mock()
        
        engine = RegimeEngine(config, mde)
        
        assert engine.bar_period == "5m"
        assert engine.slope_period == 30
        assert engine.atr_period == 21
        assert engine.volatility_high_pct == 1.5
        assert engine.volatility_low_pct == 0.5
        assert engine.compression_pct == 0.3


class TestRegimeEngineComputation:
    """Test RegimeEngine computation logic."""
    
    def _create_mock_candles(self, num_candles=100, base_price=100.0, trend="flat"):
        """Helper to create mock candle data."""
        candles = []
        price = base_price
        
        for i in range(num_candles):
            if trend == "up":
                price += 0.5
            elif trend == "down":
                price -= 0.5
            
            # Add some noise
            high = price + 1.0
            low = price - 1.0
            
            candle = Mock()
            candle.open = price - 0.2
            candle.high = high
            candle.low = low
            candle.close = price
            candles.append(candle)
        
        return candles
    
    def test_uptrend_detection(self):
        """Test detection of uptrend."""
        config = {"regime_engine": {"enabled": True}}
        mde = Mock()
        
        # Create uptrending data
        candles = self._create_mock_candles(100, base_price=100.0, trend="up")
        mde.get_candles = Mock(return_value=candles)
        
        engine = RegimeEngine(config, mde)
        snapshot = engine.compute_snapshot("NIFTY")
        
        # Should detect uptrend
        assert snapshot.trend == "up"
        assert snapshot.velocity > 0
        assert snapshot.slope > 0
    
    def test_downtrend_detection(self):
        """Test detection of downtrend."""
        config = {"regime_engine": {"enabled": True}}
        mde = Mock()
        
        # Create downtrending data
        candles = self._create_mock_candles(100, base_price=100.0, trend="down")
        mde.get_candles = Mock(return_value=candles)
        
        engine = RegimeEngine(config, mde)
        snapshot = engine.compute_snapshot("NIFTY")
        
        # Should detect downtrend
        assert snapshot.trend == "down"
        assert snapshot.velocity < 0
        assert snapshot.slope < 0
    
    def test_flat_trend_detection(self):
        """Test detection of flat/ranging market."""
        config = {"regime_engine": {"enabled": True}}
        mde = Mock()
        
        # Create flat data
        candles = self._create_mock_candles(100, base_price=100.0, trend="flat")
        mde.get_candles = Mock(return_value=candles)
        
        engine = RegimeEngine(config, mde)
        snapshot = engine.compute_snapshot("NIFTY")
        
        # Should detect flat trend
        assert snapshot.trend == "flat"
    
    def test_high_volatility_detection(self):
        """Test detection of high volatility."""
        config = {
            "regime_engine": {
                "enabled": True,
                "volatility_high_pct": 1.0,
            }
        }
        mde = Mock()
        
        # Create high volatility data (wide price swings)
        candles = []
        for i in range(100):
            price = 100.0 + (10.0 if i % 2 == 0 else -10.0)
            candle = Mock()
            candle.open = price
            candle.high = price + 5.0
            candle.low = price - 5.0
            candle.close = price
            candles.append(candle)
        
        mde.get_candles = Mock(return_value=candles)
        
        engine = RegimeEngine(config, mde)
        snapshot = engine.compute_snapshot("NIFTY")
        
        # Should detect high volatility
        assert snapshot.volatility == "high"
        assert snapshot.atr > 0
    
    def test_low_volatility_detection(self):
        """Test detection of low volatility."""
        config = {
            "regime_engine": {
                "enabled": True,
                "volatility_low_pct": 0.35,
            }
        }
        mde = Mock()
        
        # Create low volatility data (tight price range)
        candles = []
        for i in range(100):
            price = 100.0 + (0.1 if i % 2 == 0 else -0.1)
            candle = Mock()
            candle.open = price
            candle.high = price + 0.05
            candle.low = price - 0.05
            candle.close = price
            candles.append(candle)
        
        mde.get_candles = Mock(return_value=candles)
        
        engine = RegimeEngine(config, mde)
        snapshot = engine.compute_snapshot("NIFTY")
        
        # Should detect low volatility
        assert snapshot.volatility == "low"
    
    def test_insufficient_data(self):
        """Test behavior with insufficient data."""
        config = {"regime_engine": {"enabled": True}}
        mde = Mock()
        
        # Return only a few candles (insufficient)
        candles = self._create_mock_candles(5)
        mde.get_candles = Mock(return_value=candles)
        
        engine = RegimeEngine(config, mde)
        snapshot = engine.compute_snapshot("NIFTY")
        
        # Should return neutral regime
        assert snapshot.trend == "flat"
        assert snapshot.volatility == "medium"
        assert snapshot.structure == "none"


class TestRegimeEngineCaching:
    """Test RegimeEngine caching mechanism."""
    
    def test_cache_hit(self):
        """Test that cached snapshots are returned."""
        config = {"regime_engine": {"enabled": True}}
        mde = Mock()
        mde.get_candles = Mock(return_value=[])
        
        engine = RegimeEngine(config, mde)
        
        # First call - cache miss
        snapshot1 = engine.snapshot("NIFTY")
        call_count_1 = mde.get_candles.call_count
        
        # Second call immediately - cache hit
        snapshot2 = engine.snapshot("NIFTY")
        call_count_2 = mde.get_candles.call_count
        
        # Should not have called get_candles again
        assert call_count_2 == call_count_1
        assert snapshot2.timestamp == snapshot1.timestamp
    
    def test_cache_expiry(self):
        """Test that cache expires after TTL."""
        config = {"regime_engine": {"enabled": True}}
        mde = Mock()
        mde.get_candles = Mock(return_value=[])
        
        engine = RegimeEngine(config, mde)
        engine._cache_ttl = 0.1  # 100ms TTL for testing
        
        # First call
        snapshot1 = engine.snapshot("NIFTY")
        
        # Wait for cache to expire
        time.sleep(0.15)
        
        # Second call - cache should be expired
        snapshot2 = engine.snapshot("NIFTY")
        
        # Timestamps should be different
        assert snapshot2.timestamp > snapshot1.timestamp
    
    def test_cache_per_symbol(self):
        """Test that cache is maintained per symbol."""
        config = {"regime_engine": {"enabled": True}}
        mde = Mock()
        mde.get_candles = Mock(return_value=[])
        
        engine = RegimeEngine(config, mde)
        
        # Get snapshots for different symbols
        snapshot1 = engine.snapshot("NIFTY")
        snapshot2 = engine.snapshot("BANKNIFTY")
        
        # Should have cached both
        assert "NIFTY" in engine._cache
        assert "BANKNIFTY" in engine._cache
        
        # Should be able to retrieve from cache
        snapshot1_again = engine.snapshot("NIFTY")
        assert snapshot1_again.timestamp == snapshot1.timestamp
    
    def test_clear_cache(self):
        """Test cache clearing."""
        config = {"regime_engine": {"enabled": True}}
        mde = Mock()
        mde.get_candles = Mock(return_value=[])
        
        engine = RegimeEngine(config, mde)
        
        # Get snapshot
        engine.snapshot("NIFTY")
        assert "NIFTY" in engine._cache
        
        # Clear specific symbol
        engine.clear_cache("NIFTY")
        assert "NIFTY" not in engine._cache
        
        # Get multiple snapshots
        engine.snapshot("NIFTY")
        engine.snapshot("BANKNIFTY")
        assert len(engine._cache) == 2
        
        # Clear all
        engine.clear_cache()
        assert len(engine._cache) == 0


class TestRegimeEngineErrorHandling:
    """Test RegimeEngine error handling."""
    
    def test_no_exceptions_on_mde_error(self):
        """Test that engine never throws exceptions even when MDE fails."""
        config = {"regime_engine": {"enabled": True}}
        mde = Mock()
        
        # Make MDE throw exception
        mde.get_candles = Mock(side_effect=Exception("MDE error"))
        mde.get_historical_data = Mock(side_effect=Exception("MDE error"))
        
        engine = RegimeEngine(config, mde)
        
        # Should not throw
        snapshot = engine.snapshot("NIFTY")
        
        # Should return neutral regime
        assert snapshot.trend == "flat"
        assert snapshot.volatility == "medium"
        assert snapshot.structure == "none"
    
    def test_no_exceptions_on_computation_error(self):
        """Test that computation errors are handled gracefully."""
        config = {"regime_engine": {"enabled": True}}
        mde = Mock()
        
        # Return invalid data
        candles = [Mock(close=None, high=None, low=None, open=None)]
        mde.get_candles = Mock(return_value=candles)
        
        engine = RegimeEngine(config, mde)
        
        # Should not throw
        snapshot = engine.snapshot("NIFTY")
        
        # Should return neutral regime
        assert snapshot.trend == "flat"
        assert snapshot.volatility == "medium"
        assert snapshot.structure == "none"
    
    def test_no_exceptions_on_cache_error(self):
        """Test that cache errors don't break the engine."""
        config = {"regime_engine": {"enabled": True}}
        mde = Mock()
        mde.get_candles = Mock(return_value=[])
        
        engine = RegimeEngine(config, mde)
        
        # Corrupt cache
        engine._cache = None
        
        # Should not throw
        snapshot = engine.snapshot("NIFTY")
        
        # Should return neutral regime
        assert isinstance(snapshot, RegimeSnapshot)


class TestRegimeEngineIntegration:
    """Test RegimeEngine integration scenarios."""
    
    def test_mde_v2_integration(self):
        """Test integration with MarketDataEngine v2."""
        config = {"regime_engine": {"enabled": True}}
        mde = Mock()
        
        # Simulate MDE v2 API
        candles = []
        for i in range(100):
            candle = Mock()
            candle.open = 100.0
            candle.high = 101.0
            candle.low = 99.0
            candle.close = 100.0
            candles.append(candle)
        
        mde.get_candles = Mock(return_value=candles)
        
        engine = RegimeEngine(config, mde)
        snapshot = engine.snapshot("NIFTY")
        
        # Should successfully compute
        assert isinstance(snapshot, RegimeSnapshot)
        assert mde.get_candles.called
    
    def test_mde_v1_fallback(self):
        """Test fallback to MarketDataEngine v1 API."""
        import pandas as pd
        
        config = {"regime_engine": {"enabled": True}}
        mde = Mock()
        
        # MDE v2 not available
        mde.get_candles = None
        
        # Simulate MDE v1 API with pandas DataFrame
        df = pd.DataFrame({
            'open': [100.0] * 100,
            'high': [101.0] * 100,
            'low': [99.0] * 100,
            'close': [100.0] * 100,
        })
        mde.get_historical_data = Mock(return_value=df)
        
        engine = RegimeEngine(config, mde)
        snapshot = engine.snapshot("NIFTY")
        
        # Should successfully compute
        assert isinstance(snapshot, RegimeSnapshot)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
