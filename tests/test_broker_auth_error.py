"""Tests for BrokerAuthError handling in broker_feed."""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from data.broker_feed import BrokerFeed, BrokerAuthError


def test_broker_auth_error_exception_exists():
    """Test that BrokerAuthError is a proper exception class."""
    assert issubclass(BrokerAuthError, Exception)
    
    # Test it can be raised and caught
    try:
        raise BrokerAuthError("Test auth error")
    except BrokerAuthError as exc:
        assert "Test auth error" in str(exc)
    
    print("✓ test_broker_auth_error_exception_exists")


def test_broker_feed_raises_auth_error_after_multiple_failures():
    """Test that BrokerFeed raises BrokerAuthError after multiple consecutive auth failures."""
    from kiteconnect import exceptions as kite_exceptions
    
    mock_kite = Mock()
    
    with patch('data.broker_feed.kite_request') as mock_kite_request:
        # Simulate Kite TokenException with auth error message
        token_exc = kite_exceptions.TokenException("Incorrect `api_key` or `access_token`.")
        mock_kite_request.side_effect = token_exc
        
        feed = BrokerFeed(mock_kite)
        # Lower threshold for testing
        feed._max_auth_errors_before_raise = 3
        
        # First two calls should return None
        result1 = feed.get_ltp("NIFTY", exchange="NSE")
        assert result1 is None
        assert feed._consecutive_auth_errors == 1
        
        result2 = feed.get_ltp("NIFTY", exchange="NSE")
        assert result2 is None
        assert feed._consecutive_auth_errors == 2
        
        # Third call should raise BrokerAuthError
        try:
            feed.get_ltp("NIFTY", exchange="NSE")
            assert False, "Should have raised BrokerAuthError"
        except BrokerAuthError as exc:
            assert "Broker authentication failed" in str(exc)
            assert "re-login" in str(exc)
        
        print("✓ test_broker_feed_raises_auth_error_after_multiple_failures")


def test_broker_feed_resets_auth_error_count_on_success():
    """Test that successful LTP fetch resets the auth error counter."""
    mock_kite = Mock()
    
    with patch('data.broker_feed.kite_request') as mock_kite_request:
        feed = BrokerFeed(mock_kite)
        feed._consecutive_auth_errors = 2  # Simulate previous failures
        
        # Return valid data
        mock_kite_request.return_value = {"NSE:NIFTY": {"last_price": 25000.0}}
        
        result = feed.get_ltp("NIFTY", exchange="NSE")
        
        assert result == 25000.0
        assert feed._consecutive_auth_errors == 0  # Should be reset
        
        print("✓ test_broker_feed_resets_auth_error_count_on_success")


def test_broker_feed_handles_non_auth_token_exception():
    """Test that non-auth TokenExceptions don't trigger BrokerAuthError."""
    from kiteconnect import exceptions as kite_exceptions
    
    mock_kite = Mock()
    
    with patch('data.broker_feed.kite_request') as mock_kite_request:
        # Simulate TokenException with different message (not auth error)
        token_exc = kite_exceptions.TokenException("Session expired")
        mock_kite_request.side_effect = token_exc
        
        feed = BrokerFeed(mock_kite)
        feed._max_auth_errors_before_raise = 2
        
        # Multiple calls should return None but not raise BrokerAuthError
        result1 = feed.get_ltp("NIFTY", exchange="NSE")
        result2 = feed.get_ltp("NIFTY", exchange="NSE")
        result3 = feed.get_ltp("NIFTY", exchange="NSE")
        
        # All should return None
        assert result1 is None
        assert result2 is None
        assert result3 is None
        
        print("✓ test_broker_feed_handles_non_auth_token_exception")


def run_all_tests():
    """Run all tests and report results."""
    tests = [
        test_broker_auth_error_exception_exists,
        test_broker_feed_raises_auth_error_after_multiple_failures,
        test_broker_feed_resets_auth_error_count_on_success,
        test_broker_feed_handles_non_auth_token_exception,
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
