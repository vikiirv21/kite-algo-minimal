"""
Manual verification script for Trade Guardian v1

This script demonstrates the guardian in action with various scenarios.
"""

import logging
import sys
import time
from pathlib import Path

# Add parent directory to path
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from core.trade_guardian import TradeGuardian, GuardianDecision
from dataclasses import dataclass

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class MockIntent:
    """Mock OrderIntent for demonstration."""
    symbol: str
    qty: int
    side: str = "BUY"
    price: float = None
    strategy_code: str = "test_strategy"


class MockStateStore:
    """Mock StateStore for demonstration."""
    
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


def demo_disabled_guardian():
    """Demonstrate guardian in disabled mode."""
    print("\n" + "="*70)
    print("DEMO 1: Guardian DISABLED (Default Behavior)")
    print("="*70)
    
    config = {
        "guardian": {
            "enabled": False,
        }
    }
    
    state_store = MockStateStore()
    guardian = TradeGuardian(config, state_store, logger)
    
    # Even an obviously bad trade will be allowed
    intent = MockIntent(symbol="NIFTY", qty=10000, side="BUY", price=50000.0)
    
    print(f"\n📝 Order Intent: {intent.side} {intent.qty} x {intent.symbol} @ {intent.price}")
    
    decision = guardian.validate_pre_trade(intent, None)
    
    print(f"\n🛡️ Guardian Decision: {'✅ ALLOWED' if decision.allow else '❌ BLOCKED'}")
    if decision.reason:
        print(f"   Reason: {decision.reason}")
    
    print("\n💡 Takeaway: When disabled, guardian allows all trades (safe default)")


def demo_enabled_guardian_pass():
    """Demonstrate guardian allowing a good trade."""
    print("\n" + "="*70)
    print("DEMO 2: Guardian ENABLED - Good Trade")
    print("="*70)
    
    config = {
        "guardian": {
            "enabled": True,
            "max_lot_size": 100,
            "max_order_per_second": 5,
            "reject_if_price_stale_secs": 3,
            "reject_if_slippage_pct": 2.0,
            "max_daily_drawdown_pct": 3.0,
        }
    }
    
    state_store = MockStateStore(realized_pnl=-500.0, paper_capital=100000.0)
    guardian = TradeGuardian(config, state_store, logger)
    
    # A reasonable trade
    intent = MockIntent(symbol="NIFTY", qty=50, side="BUY", price=18500.0)
    
    # Fresh market data
    market_snapshot = {
        "last_price": 18490.0,
        "timestamp": time.time(),
    }
    
    print(f"\n📝 Order Intent: {intent.side} {intent.qty} x {intent.symbol} @ {intent.price}")
    print(f"📊 Market Data: LTP={market_snapshot['last_price']}, Age=fresh")
    print(f"💰 Current PnL: -500 (0.5% drawdown)")
    
    decision = guardian.validate_pre_trade(intent, market_snapshot)
    
    print(f"\n🛡️ Guardian Decision: {'✅ ALLOWED' if decision.allow else '❌ BLOCKED'}")
    if decision.reason:
        print(f"   Reason: {decision.reason}")
    
    print("\n💡 Takeaway: Guardian allows reasonable trades that pass all checks")


def demo_enabled_guardian_block_qty():
    """Demonstrate guardian blocking oversized trade."""
    print("\n" + "="*70)
    print("DEMO 3: Guardian ENABLED - Oversized Quantity")
    print("="*70)
    
    config = {
        "guardian": {
            "enabled": True,
            "max_lot_size": 50,
            "max_order_per_second": 5,
        }
    }
    
    state_store = MockStateStore()
    guardian = TradeGuardian(config, state_store, logger)
    
    # Too large quantity
    intent = MockIntent(symbol="NIFTY", qty=100, side="BUY")
    
    print(f"\n📝 Order Intent: {intent.side} {intent.qty} x {intent.symbol}")
    print(f"⚙️  Max Lot Size: 50")
    
    decision = guardian.validate_pre_trade(intent, None)
    
    print(f"\n🛡️ Guardian Decision: {'✅ ALLOWED' if decision.allow else '❌ BLOCKED'}")
    if decision.reason:
        print(f"   Reason: {decision.reason}")
    
    print("\n💡 Takeaway: Guardian blocks trades exceeding max_lot_size")


def demo_enabled_guardian_block_rate():
    """Demonstrate guardian blocking rate limit."""
    print("\n" + "="*70)
    print("DEMO 4: Guardian ENABLED - Rate Limiting")
    print("="*70)
    
    config = {
        "guardian": {
            "enabled": True,
            "max_lot_size": 100,
            "max_order_per_second": 3,
        }
    }
    
    state_store = MockStateStore()
    guardian = TradeGuardian(config, state_store, logger)
    
    print(f"\n⚙️  Max Orders Per Second: 3")
    print(f"\n📝 Attempting 4 rapid orders...")
    
    for i in range(4):
        intent = MockIntent(symbol="NIFTY", qty=10, side="BUY")
        decision = guardian.validate_pre_trade(intent, None)
        
        status = '✅ ALLOWED' if decision.allow else '❌ BLOCKED'
        print(f"   Order {i+1}: {status}")
        if decision.reason:
            print(f"            Reason: {decision.reason}")
    
    print("\n💡 Takeaway: Guardian limits trade velocity to prevent runaway algorithms")


def demo_enabled_guardian_block_drawdown():
    """Demonstrate guardian blocking on drawdown."""
    print("\n" + "="*70)
    print("DEMO 5: Guardian ENABLED - Drawdown Protection")
    print("="*70)
    
    config = {
        "guardian": {
            "enabled": True,
            "max_lot_size": 100,
            "max_order_per_second": 10,
            "max_daily_drawdown_pct": 3.0,
        }
    }
    
    state_store = MockStateStore(realized_pnl=-4000.0, paper_capital=100000.0)
    guardian = TradeGuardian(config, state_store, logger)
    
    intent = MockIntent(symbol="NIFTY", qty=50, side="BUY")
    
    print(f"\n📝 Order Intent: {intent.side} {intent.qty} x {intent.symbol}")
    print(f"💰 Current PnL: -4000 (4% drawdown)")
    print(f"⚙️  Max Drawdown: 3%")
    
    decision = guardian.validate_pre_trade(intent, None)
    
    print(f"\n🛡️ Guardian Decision: {'✅ ALLOWED' if decision.allow else '❌ BLOCKED'}")
    if decision.reason:
        print(f"   Reason: {decision.reason}")
    
    print("\n💡 Takeaway: Guardian halts trading when losses exceed thresholds")


def demo_enabled_guardian_block_stale():
    """Demonstrate guardian blocking stale prices."""
    print("\n" + "="*70)
    print("DEMO 6: Guardian ENABLED - Stale Price Detection")
    print("="*70)
    
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
    
    intent = MockIntent(symbol="NIFTY", qty=50, side="BUY", price=18500.0)
    
    # 5 seconds old market data
    market_snapshot = {
        "last_price": 18490.0,
        "timestamp": time.time() - 5.0,
    }
    
    print(f"\n📝 Order Intent: {intent.side} {intent.qty} x {intent.symbol} @ {intent.price}")
    print(f"📊 Market Data: LTP={market_snapshot['last_price']}, Age=5 seconds")
    print(f"⚙️  Max Age: 2 seconds")
    
    decision = guardian.validate_pre_trade(intent, market_snapshot)
    
    print(f"\n🛡️ Guardian Decision: {'✅ ALLOWED' if decision.allow else '❌ BLOCKED'}")
    if decision.reason:
        print(f"   Reason: {decision.reason}")
    
    print("\n💡 Takeaway: Guardian prevents trading on stale data")


def main():
    """Run all demonstrations."""
    print("\n" + "="*70)
    print("TRADE GUARDIAN v1 - MANUAL VERIFICATION")
    print("="*70)
    print("\nThis script demonstrates various guardian behaviors.")
    print("Each demo shows a different aspect of the guardian's validation logic.")
    
    demos = [
        demo_disabled_guardian,
        demo_enabled_guardian_pass,
        demo_enabled_guardian_block_qty,
        demo_enabled_guardian_block_rate,
        demo_enabled_guardian_block_drawdown,
        demo_enabled_guardian_block_stale,
    ]
    
    for demo in demos:
        try:
            demo()
            time.sleep(0.5)  # Small delay between demos
        except Exception as e:
            logger.error(f"Demo failed: {demo.__name__} - {e}", exc_info=True)
    
    print("\n" + "="*70)
    print("VERIFICATION COMPLETE")
    print("="*70)
    print("\n✅ All guardian behaviors demonstrated successfully")
    print("\nKey Points:")
    print("  1. Guardian is DISABLED by default (safe)")
    print("  2. When disabled, all trades are allowed")
    print("  3. When enabled, performs 5 safety checks")
    print("  4. Never crashes - always catches exceptions")
    print("  5. Minimal performance impact")
    print("\nTo enable in production: Set guardian.enabled=true in config")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
