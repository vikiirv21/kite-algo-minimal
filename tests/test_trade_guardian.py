"""
Test script for Trade Guardian v1

Validates:
- Guardian disabled mode (always allows)
- Guardian enabled with various validation scenarios
- Quantity validation
- Rate limiting
- Stale price detection
- Slippage checks
- PnL-based circuit breakers
- Exception handling (guardian never crashes)
"""

import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# Add parent directory to path
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from core.trade_guardian import TradeGuardian, GuardianDecision

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class MockIntent:
    """Mock OrderIntent for testing."""
    symbol: str
    qty: int
    side: str = "BUY"
    price: float = None
    strategy_code: str = "test_strategy"


class MockStateStore:
    """Mock StateStore for testing."""
    
    def __init__(self, realized_pnl: float = 0.0, paper_capital: float = 100000.0):
        self.realized_pnl = realized_pnl
        self.paper_capital = paper_capital
    
    def load_checkpoint(self):
        """Return mock checkpoint data."""
        return {
            "equity": {
                "paper_capital": self.paper_capital,
                "realized_pnl": self.realized_pnl,
                "unrealized_pnl": 0.0,
            },
        }


def test_guardian_disabled():
    """Test that disabled guardian always allows trades."""
    logger.info("\n=== Test 1: Guardian Disabled ===")
    
    config = {
        "guardian": {
            "enabled": False,
        }
    }
    
    state_store = MockStateStore()
    guardian = TradeGuardian(config, state_store, logger)
    
    # Create an intent that would fail multiple checks if guardian was enabled
    intent = MockIntent(symbol="NIFTY", qty=1000, side="BUY")
    
    decision = guardian.validate_pre_trade(intent, None)
    
    assert decision.allow is True, "Disabled guardian should always allow trades"
    logger.info("✅ Test passed: Disabled guardian allows all trades")


def test_guardian_qty_validation():
    """Test quantity validation."""
    logger.info("\n=== Test 2: Quantity Validation ===")
    
    config = {
        "guardian": {
            "enabled": True,
            "max_lot_size": 50,
            "max_order_per_second": 10,
        }
    }
    
    state_store = MockStateStore()
    guardian = TradeGuardian(config, state_store, logger)
    
    # Test within limit
    intent_ok = MockIntent(symbol="NIFTY", qty=50, side="BUY")
    decision_ok = guardian.validate_pre_trade(intent_ok, None)
    assert decision_ok.allow is True, "Should allow qty=50 when max_lot_size=50"
    logger.info("✅ Allowed qty=50 (within limit)")
    
    # Test exceeding limit
    intent_too_big = MockIntent(symbol="NIFTY", qty=51, side="BUY")
    decision_blocked = guardian.validate_pre_trade(intent_too_big, None)
    assert decision_blocked.allow is False, "Should block qty=51 when max_lot_size=50"
    assert "max_lot_size" in decision_blocked.reason.lower()
    logger.info(f"✅ Blocked qty=51: {decision_blocked.reason}")


def test_guardian_rate_limiting():
    """Test trade rate limiting."""
    logger.info("\n=== Test 3: Rate Limiting ===")
    
    config = {
        "guardian": {
            "enabled": True,
            "max_lot_size": 100,
            "max_order_per_second": 3,
        }
    }
    
    state_store = MockStateStore()
    guardian = TradeGuardian(config, state_store, logger)
    
    # Place 3 orders (should all pass)
    for i in range(3):
        intent = MockIntent(symbol="NIFTY", qty=10, side="BUY")
        decision = guardian.validate_pre_trade(intent, None)
        assert decision.allow is True, f"Order {i+1}/3 should be allowed"
        logger.info(f"✅ Order {i+1}/3 allowed")
    
    # 4th order should be blocked
    intent_4th = MockIntent(symbol="NIFTY", qty=10, side="BUY")
    decision_blocked = guardian.validate_pre_trade(intent_4th, None)
    assert decision_blocked.allow is False, "4th order should be blocked (rate limit)"
    assert "rate limit" in decision_blocked.reason.lower()
    logger.info(f"✅ 4th order blocked: {decision_blocked.reason}")
    
    # Wait 1 second and try again (should pass)
    time.sleep(1.1)
    intent_after_wait = MockIntent(symbol="NIFTY", qty=10, side="BUY")
    decision_after = guardian.validate_pre_trade(intent_after_wait, None)
    assert decision_after.allow is True, "Order should be allowed after 1 second wait"
    logger.info("✅ Order allowed after 1 second wait")


def test_guardian_stale_price():
    """Test stale price detection."""
    logger.info("\n=== Test 4: Stale Price Detection ===")
    
    config = {
        "guardian": {
            "enabled": True,
            "max_lot_size": 100,
            "max_order_per_second": 10,
            "reject_if_price_stale_secs": 2,
        }
    }
    
    state_store = MockStateStore()
    guardian = TradeGuardian(config, state_store, logger)
    
    # Test with fresh price
    current_time = time.time()
    market_snapshot_fresh = {
        "last_price": 100.0,
        "timestamp": current_time,
    }
    intent = MockIntent(symbol="NIFTY", qty=10, side="BUY")
    decision_fresh = guardian.validate_pre_trade(intent, market_snapshot_fresh)
    assert decision_fresh.allow is True, "Should allow trade with fresh price"
    logger.info("✅ Allowed with fresh price")
    
    # Test with stale price (5 seconds old)
    market_snapshot_stale = {
        "last_price": 100.0,
        "timestamp": current_time - 5.0,
    }
    decision_stale = guardian.validate_pre_trade(intent, market_snapshot_stale)
    assert decision_stale.allow is False, "Should block trade with stale price"
    assert "stale" in decision_stale.reason.lower()
    logger.info(f"✅ Blocked with stale price: {decision_stale.reason}")


def test_guardian_slippage_check():
    """Test slippage validation."""
    logger.info("\n=== Test 5: Slippage Check ===")
    
    config = {
        "guardian": {
            "enabled": True,
            "max_lot_size": 100,
            "max_order_per_second": 10,
            "reject_if_slippage_pct": 2.0,
        }
    }
    
    state_store = MockStateStore()
    guardian = TradeGuardian(config, state_store, logger)
    
    # Test with acceptable slippage (1%)
    market_snapshot = {
        "last_price": 100.0,
        "timestamp": time.time(),
    }
    intent_ok = MockIntent(symbol="NIFTY", qty=10, side="BUY", price=101.0)
    decision_ok = guardian.validate_pre_trade(intent_ok, market_snapshot)
    assert decision_ok.allow is True, "Should allow 1% slippage when limit is 2%"
    logger.info("✅ Allowed with 1% slippage")
    
    # Test with excessive slippage (3%)
    intent_high_slip = MockIntent(symbol="NIFTY", qty=10, side="BUY", price=103.0)
    decision_blocked = guardian.validate_pre_trade(intent_high_slip, market_snapshot)
    assert decision_blocked.allow is False, "Should block 3% slippage when limit is 2%"
    assert "slippage" in decision_blocked.reason.lower()
    logger.info(f"✅ Blocked with 3% slippage: {decision_blocked.reason}")


def test_guardian_pnl_drawdown():
    """Test PnL-based circuit breakers."""
    logger.info("\n=== Test 6: PnL Drawdown Check ===")
    
    config = {
        "guardian": {
            "enabled": True,
            "max_lot_size": 100,
            "max_order_per_second": 10,
            "max_daily_drawdown_pct": 3.0,
            "halt_on_pnl_drop_pct": 5.0,
        }
    }
    
    # Test with small loss (allowed)
    state_store_ok = MockStateStore(realized_pnl=-1000.0, paper_capital=100000.0)
    guardian_ok = TradeGuardian(config, state_store_ok, logger)
    intent = MockIntent(symbol="NIFTY", qty=10, side="BUY")
    decision_ok = guardian_ok.validate_pre_trade(intent, None)
    assert decision_ok.allow is True, "Should allow with 1% drawdown (limit=3%)"
    logger.info("✅ Allowed with 1% drawdown")
    
    # Test with excessive drawdown (blocked) - just above 3% but below 5%
    state_store_dd = MockStateStore(realized_pnl=-3500.0, paper_capital=100000.0)
    guardian_dd = TradeGuardian(config, state_store_dd, logger)
    decision_dd = guardian_dd.validate_pre_trade(intent, None)
    assert decision_dd.allow is False, "Should block with 3.5% drawdown (limit=3%)"
    assert "drawdown" in decision_dd.reason.lower()
    logger.info(f"✅ Blocked with 3.5% drawdown: {decision_dd.reason}")
    
    # Test with PnL drop halt (above both thresholds, should catch drawdown first)
    state_store_halt = MockStateStore(realized_pnl=-6000.0, paper_capital=100000.0)
    guardian_halt = TradeGuardian(config, state_store_halt, logger)
    decision_halt = guardian_halt.validate_pre_trade(intent, None)
    assert decision_halt.allow is False, "Should block with 6% loss (exceeds both limits)"
    # Will be caught by drawdown check first
    assert "drawdown" in decision_halt.reason.lower() or "pnl" in decision_halt.reason.lower()
    logger.info(f"✅ Blocked with 6% loss: {decision_halt.reason}")


def test_guardian_exception_handling():
    """Test that guardian never crashes (always catches exceptions)."""
    logger.info("\n=== Test 7: Exception Handling ===")
    
    config = {
        "guardian": {
            "enabled": True,
            "max_lot_size": 100,
        }
    }
    
    # Create a state store that will raise exception
    class BrokenStateStore:
        def load_checkpoint(self):
            raise RuntimeError("Simulated state store failure")
    
    state_store = BrokenStateStore()
    guardian = TradeGuardian(config, state_store, logger)
    
    # Guardian should still allow trade despite exception
    intent = MockIntent(symbol="NIFTY", qty=10, side="BUY")
    decision = guardian.validate_pre_trade(intent, None)
    assert decision.allow is True, "Guardian should allow trade on exception"
    logger.info("✅ Guardian allowed trade despite internal exception")


def test_guardian_no_config():
    """Test guardian with missing config (should disable)."""
    logger.info("\n=== Test 8: Missing Config ===")
    
    # Config with no guardian section
    config = {
        "trading": {
            "mode": "paper",
        }
    }
    
    state_store = MockStateStore()
    guardian = TradeGuardian(config, state_store, logger)
    
    # Should be disabled and allow all trades
    intent = MockIntent(symbol="NIFTY", qty=1000, side="BUY")
    decision = guardian.validate_pre_trade(intent, None)
    assert decision.allow is True, "Guardian with no config should allow all trades"
    logger.info("✅ Guardian without config section allows all trades")


def run_all_tests():
    """Run all test cases."""
    logger.info("=" * 60)
    logger.info("Trade Guardian v1 - Test Suite")
    logger.info("=" * 60)
    
    tests = [
        test_guardian_disabled,
        test_guardian_qty_validation,
        test_guardian_rate_limiting,
        test_guardian_stale_price,
        test_guardian_slippage_check,
        test_guardian_pnl_drawdown,
        test_guardian_exception_handling,
        test_guardian_no_config,
    ]
    
    passed = 0
    failed = 0
    
    for test_func in tests:
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            logger.error(f"❌ Test failed: {test_func.__name__} - {e}")
            failed += 1
        except Exception as e:
            logger.error(f"❌ Test error: {test_func.__name__} - {e}", exc_info=True)
            failed += 1
    
    logger.info("\n" + "=" * 60)
    logger.info(f"Test Results: {passed} passed, {failed} failed")
    logger.info("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
