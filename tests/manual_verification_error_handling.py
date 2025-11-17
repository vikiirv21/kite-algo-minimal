#!/usr/bin/env python
"""
Manual verification script to demonstrate error handling fixes.

This script shows that:
1. BrokerFeed handles missing symbols gracefully (no KeyError)
2. Strategy handles None/invalid close values gracefully (no TypeError)
3. The system continues processing other symbols after encountering errors

Run this script to see the fixes in action:
    python tests/manual_verification_error_handling.py
"""

import sys
import logging
from pathlib import Path
from unittest.mock import Mock, patch

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from data.broker_feed import BrokerFeed
from strategies.fno_intraday_trend import FnoIntradayTrendStrategy


# Configure logging to see the DEBUG and WARNING messages
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)

logger = logging.getLogger(__name__)


def demonstrate_fixes():
    """
    Demonstrate the error handling fixes for:
    - Missing symbols (TATAMOTORS, MCDOWELL-N)
    - None close values
    - Invalid close values
    """
    
    print("=" * 80)
    print("DEMONSTRATION: Error Handling Fixes")
    print("=" * 80)
    print()
    
    # Setup
    mock_kite = Mock()
    
    with patch('data.broker_feed.kite_request') as mock_kite_request:
        # Simulate LTP response with only some symbols
        mock_kite_request.return_value = {
            "NSE:RELIANCE": {"last_price": 2500.0},
            "NSE:TCS": {"last_price": 3450.0},
            # Note: TATAMOTORS and MCDOWELL-N are missing from response
        }
        
        feed = BrokerFeed(mock_kite)
        strategy = FnoIntradayTrendStrategy()
        
        # Test symbols - some exist, some don't
        test_symbols = [
            ("RELIANCE", True),
            ("TATAMOTORS", False),
            ("TCS", True),
            ("MCDOWELL-N", False),
        ]
        
        print("SCENARIO 1: Processing symbols (some missing from LTP data)")
        print("-" * 80)
        
        for symbol, exists in test_symbols:
            print(f"\nProcessing symbol: {symbol}")
            
            # Step 1: Get LTP from broker feed
            price = feed.get_ltp(symbol, exchange="NSE")
            
            if price is None:
                print(f"  → BrokerFeed returned None (symbol missing in LTP data)")
            else:
                print(f"  → BrokerFeed returned price: {price}")
            
            # Step 2: Pass to strategy
            bar = {"close": price}
            decision = strategy.on_bar(symbol, bar)
            
            print(f"  → Strategy decision: {decision.action} (reason: {decision.reason})")
            
            # Verify no crashes occurred
            assert decision.action == "HOLD", "Expected HOLD for warmup or invalid price"
        
        print()
        print("=" * 80)
        print("SCENARIO 2: Strategy handles various invalid close values")
        print("-" * 80)
        
        invalid_cases = [
            (None, "None value"),
            (0.0, "Zero value"),
            (-100.0, "Negative value"),
            ("invalid", "Non-numeric string"),
        ]
        
        for value, description in invalid_cases:
            print(f"\nTesting: {description} (value={value!r})")
            bar = {"close": value}
            decision = strategy.on_bar("TEST_SYMBOL", bar)
            print(f"  → Strategy decision: {decision.action} (reason: {decision.reason})")
            assert decision.action == "HOLD", f"Expected HOLD for {description}"
        
        print()
        print("=" * 80)
        print("SCENARIO 3: Warning deduplication (no log spam)")
        print("-" * 80)
        print("\nRequesting TATAMOTORS LTP 5 times...")
        
        for i in range(5):
            price = feed.get_ltp("TATAMOTORS", exchange="NSE")
            assert price is None
        
        print(f"  → Only ONE warning logged (check logs above)")
        print(f"  → Warned symbols: {feed._warned_missing_symbols}")
        
        print()
        print("=" * 80)
        print("✓ ALL SCENARIOS PASSED - NO CRASHES OR ERRORS!")
        print("=" * 80)
        print()
        print("Summary:")
        print("  • BrokerFeed handles missing symbols gracefully")
        print("  • Returns None instead of raising KeyError")
        print("  • Logs WARNING once per symbol (no spam)")
        print("  • Strategy handles None/invalid close values")
        print("  • Logs at DEBUG and returns HOLD decision")
        print("  • No TypeError or other crashes occur")
        print("  • System continues processing other symbols normally")
        print()


if __name__ == "__main__":
    try:
        demonstrate_fixes()
        sys.exit(0)
    except Exception as e:
        logger.error("Demonstration failed: %s", e, exc_info=True)
        sys.exit(1)
