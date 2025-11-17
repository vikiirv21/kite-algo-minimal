"""Tests for data/broker_feed.py robustness to missing symbols"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from data.broker_feed import BrokerFeed


def test_broker_feed_handles_missing_symbol():
    """Test that broker_feed handles missing symbol gracefully"""
    # Create mock Kite client
    mock_kite = Mock()
    
    # Mock the kite_request to return data without the requested symbol
    with patch('data.broker_feed.kite_request') as mock_kite_request:
        # Return data without the key we're looking for
        mock_kite_request.return_value = {"NSE:SOME_OTHER_SYMBOL": {"last_price": 100.0}}
        
        feed = BrokerFeed(mock_kite)
        
        # Should return None instead of raising KeyError
        result = feed.get_ltp("MCDOWELL-N", exchange="NSE")
        
        assert result is None
        print("✓ test_broker_feed_handles_missing_symbol")


def test_broker_feed_warns_once_per_symbol():
    """Test that broker_feed warns only once per missing symbol"""
    # Create mock Kite client
    mock_kite = Mock()
    
    with patch('data.broker_feed.kite_request') as mock_kite_request:
        # Return data without the requested symbol
        mock_kite_request.return_value = {"NSE:SOME_OTHER_SYMBOL": {"last_price": 100.0}}
        
        feed = BrokerFeed(mock_kite)
        
        # Call get_ltp multiple times for the same symbol
        result1 = feed.get_ltp("MCDOWELL-N", exchange="NSE")
        result2 = feed.get_ltp("MCDOWELL-N", exchange="NSE")
        result3 = feed.get_ltp("MCDOWELL-N", exchange="NSE")
        
        assert result1 is None
        assert result2 is None
        assert result3 is None
        
        # Check that the symbol was tracked
        assert "NSE:MCDOWELL-N" in feed._warned_missing_symbols
        
        print("✓ test_broker_feed_warns_once_per_symbol")


def test_broker_feed_returns_valid_price():
    """Test that broker_feed returns valid price when symbol exists"""
    # Create mock Kite client
    mock_kite = Mock()
    
    with patch('data.broker_feed.kite_request') as mock_kite_request:
        # Return valid data
        mock_kite_request.return_value = {"NSE:NIFTY": {"last_price": 1234.56}}
        
        feed = BrokerFeed(mock_kite)
        
        result = feed.get_ltp("NIFTY", exchange="NSE")
        
        assert result == 1234.56
        print("✓ test_broker_feed_returns_valid_price")


def test_broker_feed_tracks_multiple_missing_symbols():
    """Test that broker_feed tracks multiple different missing symbols"""
    # Create mock Kite client
    mock_kite = Mock()
    
    with patch('data.broker_feed.kite_request') as mock_kite_request:
        # Return data without the requested symbols
        mock_kite_request.return_value = {"NSE:SOME_OTHER_SYMBOL": {"last_price": 100.0}}
        
        feed = BrokerFeed(mock_kite)
        
        # Request multiple different missing symbols
        symbols = ["MCDOWELL-N", "SYMBOL1", "SYMBOL2", "SYMBOL3"]
        
        for symbol in symbols:
            result = feed.get_ltp(symbol, exchange="NSE")
            assert result is None
        
        # All should be tracked
        for symbol in symbols:
            assert f"NSE:{symbol}" in feed._warned_missing_symbols
        
        print("✓ test_broker_feed_tracks_multiple_missing_symbols")


def test_broker_feed_handles_exception():
    """Test that broker_feed handles general exceptions gracefully"""
    # Create mock Kite client
    mock_kite = Mock()
    
    with patch('data.broker_feed.kite_request') as mock_kite_request:
        # Raise an exception
        mock_kite_request.side_effect = ValueError("Network error")
        
        feed = BrokerFeed(mock_kite)
        
        result = feed.get_ltp("TEST", exchange="NSE")
        
        assert result is None
        print("✓ test_broker_feed_handles_exception")


def run_all_tests():
    """Run all tests and report results"""
    tests = [
        test_broker_feed_handles_missing_symbol,
        test_broker_feed_warns_once_per_symbol,
        test_broker_feed_returns_valid_price,
        test_broker_feed_tracks_multiple_missing_symbols,
        test_broker_feed_handles_exception,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
