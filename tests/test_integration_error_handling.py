"""
Integration test to verify end-to-end error handling for None/invalid prices.

This test verifies that:
1. BrokerFeed.get_ltp() returns None for missing symbols
2. FnoIntradayTrendStrategy.on_bar() handles None close values gracefully
3. The integration between feed and strategy works without crashes
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from data.broker_feed import BrokerFeed
from strategies.fno_intraday_trend import FnoIntradayTrendStrategy
from strategies.base import Decision


def test_end_to_end_missing_symbol_handling():
    """
    Test that the entire flow from BrokerFeed to Strategy handles missing symbols gracefully.
    
    This simulates the real scenario where:
    1. BrokerFeed.get_ltp() returns None for a missing symbol (e.g., TATAMOTORS, MCDOWELL-N)
    2. The price is passed to strategy.on_bar() as {"close": None}
    3. Strategy returns HOLD decision without crashing
    """
    # Setup mock Kite client
    mock_kite = Mock()
    
    with patch('data.broker_feed.kite_request') as mock_kite_request:
        # Simulate LTP response without the requested symbol
        mock_kite_request.return_value = {"NSE:RELIANCE": {"last_price": 2500.0}}
        
        # Create feed and strategy
        feed = BrokerFeed(mock_kite)
        strategy = FnoIntradayTrendStrategy()
        
        # Simulate the real flow for a missing symbol
        missing_symbols = ["TATAMOTORS", "MCDOWELL-N"]
        
        for symbol in missing_symbols:
            # Step 1: Feed returns None for missing symbol
            price = feed.get_ltp(symbol, exchange="NSE")
            assert price is None, f"Expected None for missing symbol {symbol}"
            
            # Step 2: Engine passes None to strategy
            bar = {"close": price}
            decision = strategy.on_bar(symbol, bar)
            
            # Step 3: Strategy returns HOLD without crashing
            assert isinstance(decision, Decision), f"Expected Decision object for {symbol}"
            assert decision.action == "HOLD", f"Expected HOLD for {symbol}, got {decision.action}"
            assert "invalid_price" in decision.reason, f"Expected invalid_price reason for {symbol}"
    
    print("✓ test_end_to_end_missing_symbol_handling")


def test_end_to_end_with_valid_price():
    """
    Test that valid prices flow through correctly.
    """
    mock_kite = Mock()
    
    with patch('data.broker_feed.kite_request') as mock_kite_request:
        # Simulate valid LTP response
        mock_kite_request.return_value = {"NSE:RELIANCE": {"last_price": 2500.0}}
        
        feed = BrokerFeed(mock_kite)
        strategy = FnoIntradayTrendStrategy()
        
        # Get valid price
        price = feed.get_ltp("RELIANCE", exchange="NSE")
        assert price == 2500.0, "Expected valid price for existing symbol"
        
        # Pass to strategy
        bar = {"close": price}
        decision = strategy.on_bar("RELIANCE", bar)
        
        # Strategy should work normally (warmup phase initially)
        assert isinstance(decision, Decision)
        assert decision.action == "HOLD"
        assert decision.reason == "warmup"  # Not enough data yet
    
    print("✓ test_end_to_end_with_valid_price")


def test_multiple_invalid_scenarios():
    """
    Test various invalid scenarios to ensure robustness.
    """
    mock_kite = Mock()
    
    with patch('data.broker_feed.kite_request') as mock_kite_request:
        # Always return empty response
        mock_kite_request.return_value = {}
        
        feed = BrokerFeed(mock_kite)
        strategy = FnoIntradayTrendStrategy()
        
        # Test various invalid scenarios
        test_cases = [
            ("SYMBOL1", None, "None from feed"),
            ("SYMBOL2", "invalid", "String value"),
            ("SYMBOL3", 0.0, "Zero value"),
            ("SYMBOL4", -100.0, "Negative value"),
        ]
        
        for symbol, test_value, description in test_cases:
            # Get price from feed (should be None for missing symbol)
            price = feed.get_ltp(symbol, exchange="NSE")
            assert price is None, f"Feed should return None for missing {symbol}"
            
            # Test with the test value
            bar = {"close": test_value}
            decision = strategy.on_bar(symbol, bar)
            
            assert isinstance(decision, Decision), f"Failed for {description}"
            assert decision.action == "HOLD", f"Failed for {description}"
            assert "invalid_price" in decision.reason, f"Failed for {description}"
    
    print("✓ test_multiple_invalid_scenarios")


def test_no_repeated_warnings():
    """
    Test that missing symbol warnings are only logged once per symbol.
    """
    mock_kite = Mock()
    
    with patch('data.broker_feed.kite_request') as mock_kite_request:
        mock_kite_request.return_value = {}
        
        feed = BrokerFeed(mock_kite)
        
        # Call get_ltp multiple times for the same symbol
        symbol = "TATAMOTORS"
        for _ in range(5):
            price = feed.get_ltp(symbol, exchange="NSE")
            assert price is None
        
        # Check that symbol is tracked
        assert f"NSE:{symbol}" in feed._warned_missing_symbols
        assert len(feed._warned_missing_symbols) == 1
    
    print("✓ test_no_repeated_warnings")


def run_all_tests():
    """Run all integration tests"""
    tests = [
        test_end_to_end_missing_symbol_handling,
        test_end_to_end_with_valid_price,
        test_multiple_invalid_scenarios,
        test_no_repeated_warnings,
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
