"""
Tests for analytics/htf_trend.py - Higher Timeframe Trend Filter
"""

import pytest
from datetime import datetime, timezone

from analytics.htf_trend import (
    HTFTrendResult,
    compute_ema_trend,
    compute_htf_trend,
    compute_htf_trend_from_series,
    should_allow_signal,
    adjust_confidence_for_htf,
)


class TestHTFTrendResult:
    """Test HTFTrendResult dataclass."""
    
    def test_create_result(self):
        """Test creating an HTFTrendResult."""
        result = HTFTrendResult(
            htf_bias="bullish",
            aligned=True,
            score=0.8,
            trend_15m="up",
            trend_1h="up",
            ema20_15m=100.0,
            ema50_15m=95.0,
            ema20_1h=105.0,
            ema50_1h=100.0,
            timestamp=datetime.now(timezone.utc),
        )
        
        assert result.htf_bias == "bullish"
        assert result.aligned is True
        assert result.score == 0.8
        assert result.trend_15m == "up"
        assert result.trend_1h == "up"
    
    def test_to_dict(self):
        """Test converting HTFTrendResult to dict."""
        ts = datetime.now(timezone.utc)
        result = HTFTrendResult(
            htf_bias="bearish",
            aligned=True,
            score=0.7,
            trend_15m="down",
            trend_1h="down",
            timestamp=ts,
        )
        
        d = result.to_dict()
        
        assert d["htf_bias"] == "bearish"
        assert d["aligned"] is True
        assert d["score"] == 0.7
        assert d["timestamp"] == ts.isoformat()


class TestComputeEmaTrend:
    """Test compute_ema_trend function."""
    
    def test_uptrend(self):
        """Test detection of uptrend."""
        # Create uptrending prices
        close_prices = [100.0 + i for i in range(60)]
        
        result = compute_ema_trend(close_prices)
        
        assert result["trend"] == "up"
        assert result["ema_fast"] is not None
        assert result["ema_slow"] is not None
        assert result["ema_fast"] > result["ema_slow"]
        assert result["separation"] > 0
    
    def test_downtrend(self):
        """Test detection of downtrend."""
        # Create downtrending prices
        close_prices = [200.0 - i for i in range(60)]
        
        result = compute_ema_trend(close_prices)
        
        assert result["trend"] == "down"
        assert result["ema_fast"] is not None
        assert result["ema_slow"] is not None
        assert result["ema_fast"] < result["ema_slow"]
        assert result["separation"] < 0
    
    def test_insufficient_data(self):
        """Test behavior with insufficient data."""
        close_prices = [100.0] * 10  # Less than 50 (ema_slow_period)
        
        result = compute_ema_trend(close_prices)
        
        assert result["trend"] == "flat"
        assert result["ema_fast"] is None
        assert result["ema_slow"] is None
    
    def test_empty_data(self):
        """Test behavior with empty data."""
        result = compute_ema_trend([])
        
        assert result["trend"] == "flat"
        assert result["ema_fast"] is None
        assert result["ema_slow"] is None
    
    def test_none_data(self):
        """Test behavior with None data."""
        result = compute_ema_trend(None)
        
        assert result["trend"] == "flat"


class TestComputeHtfTrend:
    """Test compute_htf_trend function."""
    
    def test_bullish_alignment(self):
        """Test bullish alignment when both timeframes are up."""
        # Create uptrending data for both timeframes
        close_15m = [100.0 + i for i in range(60)]
        close_1h = [100.0 + i * 2 for i in range(60)]  # Stronger uptrend
        
        result = compute_htf_trend(
            symbol="NIFTY",
            htf_df_15m={"close": close_15m},
            htf_df_1h={"close": close_1h},
        )
        
        assert result.htf_bias == "bullish"
        assert result.aligned is True
        assert result.score > 0
        assert result.trend_15m == "up"
        assert result.trend_1h == "up"
    
    def test_bearish_alignment(self):
        """Test bearish alignment when both timeframes are down."""
        # Create downtrending data for both timeframes
        close_15m = [200.0 - i for i in range(60)]
        close_1h = [200.0 - i * 2 for i in range(60)]  # Stronger downtrend
        
        result = compute_htf_trend(
            symbol="NIFTY",
            htf_df_15m={"close": close_15m},
            htf_df_1h={"close": close_1h},
        )
        
        assert result.htf_bias == "bearish"
        assert result.aligned is True
        assert result.score > 0
        assert result.trend_15m == "down"
        assert result.trend_1h == "down"
    
    def test_sideways_mixed_trends(self):
        """Test sideways when timeframes have mixed trends."""
        # 15m uptrend, 1h downtrend
        close_15m = [100.0 + i for i in range(60)]
        close_1h = [200.0 - i for i in range(60)]
        
        result = compute_htf_trend(
            symbol="NIFTY",
            htf_df_15m={"close": close_15m},
            htf_df_1h={"close": close_1h},
        )
        
        assert result.htf_bias == "sideways"
        assert result.aligned is False
    
    def test_sideways_flat_trends(self):
        """Test sideways when both timeframes are flat."""
        # Flat data
        close_15m = [100.0] * 60
        close_1h = [100.0] * 60
        
        result = compute_htf_trend(
            symbol="NIFTY",
            htf_df_15m={"close": close_15m},
            htf_df_1h={"close": close_1h},
        )
        
        assert result.htf_bias == "sideways"
        assert result.aligned is False
    
    def test_missing_15m_data(self):
        """Test with missing 15m data."""
        close_1h = [100.0 + i for i in range(60)]
        
        result = compute_htf_trend(
            symbol="NIFTY",
            htf_df_15m=None,
            htf_df_1h={"close": close_1h},
        )
        
        # Should be sideways since 15m is flat
        assert result.htf_bias == "sideways"
        assert result.trend_15m == "flat"
        assert result.trend_1h == "up"
    
    def test_missing_1h_data(self):
        """Test with missing 1h data."""
        close_15m = [100.0 + i for i in range(60)]
        
        result = compute_htf_trend(
            symbol="NIFTY",
            htf_df_15m={"close": close_15m},
            htf_df_1h=None,
        )
        
        # Should be sideways since 1h is flat
        assert result.htf_bias == "sideways"
        assert result.trend_15m == "up"
        assert result.trend_1h == "flat"
    
    def test_both_missing_data(self):
        """Test with both timeframes missing data."""
        result = compute_htf_trend(
            symbol="NIFTY",
            htf_df_15m=None,
            htf_df_1h=None,
        )
        
        assert result.htf_bias == "sideways"
        assert result.aligned is False
        assert result.score == 0.0


class TestComputeHtfTrendFromSeries:
    """Test compute_htf_trend_from_series convenience function."""
    
    def test_bullish_from_series(self):
        """Test bullish detection from close price series."""
        close_15m = [100.0 + i for i in range(60)]
        close_1h = [100.0 + i for i in range(60)]
        
        result = compute_htf_trend_from_series(
            symbol="BANKNIFTY",
            close_15m=close_15m,
            close_1h=close_1h,
        )
        
        assert result.htf_bias == "bullish"
        assert result.aligned is True


class TestShouldAllowSignal:
    """Test should_allow_signal function."""
    
    def test_long_with_bullish_htf(self):
        """Test long signal with bullish HTF - should allow."""
        htf_result = HTFTrendResult(
            htf_bias="bullish",
            aligned=True,
            score=0.8,
            trend_15m="up",
            trend_1h="up",
        )
        
        allowed, reason = should_allow_signal("long", htf_result)
        
        assert allowed is True
        assert "aligned" in reason or "bullish" in reason
    
    def test_long_with_bearish_htf(self):
        """Test long signal with bearish HTF - should block."""
        htf_result = HTFTrendResult(
            htf_bias="bearish",
            aligned=True,
            score=0.8,
            trend_15m="down",
            trend_1h="down",
        )
        
        allowed, reason = should_allow_signal("long", htf_result)
        
        assert allowed is False
        assert "conflicts" in reason
    
    def test_short_with_bearish_htf(self):
        """Test short signal with bearish HTF - should allow."""
        htf_result = HTFTrendResult(
            htf_bias="bearish",
            aligned=True,
            score=0.8,
            trend_15m="down",
            trend_1h="down",
        )
        
        allowed, reason = should_allow_signal("short", htf_result)
        
        assert allowed is True
        assert "aligned" in reason or "bearish" in reason
    
    def test_short_with_bullish_htf(self):
        """Test short signal with bullish HTF - should block."""
        htf_result = HTFTrendResult(
            htf_bias="bullish",
            aligned=True,
            score=0.8,
            trend_15m="up",
            trend_1h="up",
        )
        
        allowed, reason = should_allow_signal("short", htf_result)
        
        assert allowed is False
        assert "conflicts" in reason
    
    def test_sideways_allows_by_default(self):
        """Test sideways HTF allows signals by default."""
        htf_result = HTFTrendResult(
            htf_bias="sideways",
            aligned=False,
            score=0.3,
            trend_15m="flat",
            trend_1h="flat",
        )
        
        allowed, reason = should_allow_signal("long", htf_result)
        
        assert allowed is True
        assert "sideways_allowed" in reason
    
    def test_sideways_blocks_when_configured(self):
        """Test sideways HTF blocks when allow_sideways is False."""
        htf_result = HTFTrendResult(
            htf_bias="sideways",
            aligned=False,
            score=0.3,
            trend_15m="flat",
            trend_1h="flat",
        )
        
        allowed, reason = should_allow_signal("long", htf_result, allow_sideways=False)
        
        assert allowed is False
        assert "sideways_blocked" in reason
    
    def test_buy_alias_for_long(self):
        """Test 'buy' works same as 'long'."""
        htf_result = HTFTrendResult(
            htf_bias="bullish",
            aligned=True,
            score=0.8,
            trend_15m="up",
            trend_1h="up",
        )
        
        allowed, reason = should_allow_signal("buy", htf_result)
        
        assert allowed is True
    
    def test_sell_alias_for_short(self):
        """Test 'sell' works same as 'short'."""
        htf_result = HTFTrendResult(
            htf_bias="bearish",
            aligned=True,
            score=0.8,
            trend_15m="down",
            trend_1h="down",
        )
        
        allowed, reason = should_allow_signal("sell", htf_result)
        
        assert allowed is True


class TestAdjustConfidenceForHtf:
    """Test adjust_confidence_for_htf function."""
    
    def test_aligned_boosts_confidence(self):
        """Test that aligned HTF boosts confidence."""
        htf_result = HTFTrendResult(
            htf_bias="bullish",
            aligned=True,
            score=0.9,
            trend_15m="up",
            trend_1h="up",
        )
        
        original = 0.7
        adjusted = adjust_confidence_for_htf(original, htf_result, "long")
        
        # Should be boosted
        assert adjusted >= original
    
    def test_conflicting_reduces_confidence(self):
        """Test that conflicting HTF reduces confidence."""
        htf_result = HTFTrendResult(
            htf_bias="bearish",
            aligned=True,
            score=0.8,
            trend_15m="down",
            trend_1h="down",
        )
        
        original = 0.8
        adjusted = adjust_confidence_for_htf(original, htf_result, "long")
        
        # Should be reduced
        assert adjusted < original
    
    def test_sideways_slight_reduction(self):
        """Test that sideways HTF slightly reduces confidence."""
        htf_result = HTFTrendResult(
            htf_bias="sideways",
            aligned=False,
            score=0.3,
            trend_15m="flat",
            trend_1h="flat",
        )
        
        original = 0.8
        adjusted = adjust_confidence_for_htf(original, htf_result, "long")
        
        # Should be slightly reduced (less than full reduction)
        assert adjusted < original
        assert adjusted > original * 0.5  # Not reduced by more than half
    
    def test_custom_reduction_factor(self):
        """Test custom reduction factor."""
        htf_result = HTFTrendResult(
            htf_bias="bearish",
            aligned=True,
            score=0.8,
            trend_15m="down",
            trend_1h="down",
        )
        
        original = 1.0
        adjusted = adjust_confidence_for_htf(
            original, htf_result, "long", reduction_factor=0.5
        )
        
        # Should be reduced by 50%
        assert adjusted == 0.5
    
    def test_confidence_capped_at_1(self):
        """Test that boosted confidence doesn't exceed 1.0."""
        htf_result = HTFTrendResult(
            htf_bias="bullish",
            aligned=True,
            score=1.0,
            trend_15m="up",
            trend_1h="up",
        )
        
        original = 0.99
        adjusted = adjust_confidence_for_htf(original, htf_result, "long")
        
        assert adjusted <= 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
