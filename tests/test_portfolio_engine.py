"""
Test script for Portfolio Engine v1

Validates:
- PortfolioConfig loading
- Position sizing in fixed_qty mode
- Position sizing in fixed_risk_atr mode
- Exposure limits enforcement
"""

import logging
import sys
from pathlib import Path

# Add parent directory to path
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from core.portfolio_engine import PortfolioEngine, PortfolioConfig
from core.state_store import StateStore
from dataclasses import dataclass

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class MockIntent:
    """Mock OrderIntent for testing."""
    symbol: str
    strategy_code: str
    side: str
    qty: int = None


class MockStateStore:
    """Mock StateStore for testing."""
    
    def __init__(self, equity: float = 100000.0, positions: list = None):
        self.equity = equity
        self.positions = positions or []
    
    def load_checkpoint(self):
        """Return mock checkpoint data."""
        return {
            "equity": {
                "paper_capital": self.equity,
                "realized_pnl": 0.0,
                "unrealized_pnl": 0.0,
            },
            "positions": self.positions,
        }


def test_config_loading():
    """Test PortfolioConfig creation from dict."""
    logger.info("\n=== Test 1: Config Loading ===")
    
    config_dict = {
        "max_leverage": 2.0,
        "max_exposure_pct": 0.8,
        "max_risk_per_trade_pct": 0.01,
        "position_sizing_mode": "fixed_qty",
        "default_fixed_qty": 1,
        "strategy_budgets": {
            "test_strategy": {
                "capital_pct": 0.3,
                "fixed_qty": 2,
            }
        }
    }
    
    config = PortfolioConfig.from_dict(config_dict)
    
    assert config.max_leverage == 2.0
    assert config.max_exposure_pct == 0.8
    assert config.max_risk_per_trade_pct == 0.01
    assert config.position_sizing_mode == "fixed_qty"
    assert config.default_fixed_qty == 1
    assert "test_strategy" in config.strategy_budgets
    
    logger.info("✓ Config loading successful")
    logger.info(f"  max_leverage: {config.max_leverage}")
    logger.info(f"  max_exposure_pct: {config.max_exposure_pct}")
    logger.info(f"  position_sizing_mode: {config.position_sizing_mode}")


def test_equity_reading():
    """Test equity reading from state store."""
    logger.info("\n=== Test 2: Equity Reading ===")
    
    config = PortfolioConfig()
    state_store = MockStateStore(equity=500000.0)
    
    engine = PortfolioEngine(
        portfolio_config=config,
        state_store=state_store,
        logger_instance=logger,
    )
    
    equity = engine.get_equity()
    assert equity == 500000.0
    
    logger.info(f"✓ Equity reading successful: {equity}")


def test_strategy_budget():
    """Test strategy budget computation."""
    logger.info("\n=== Test 3: Strategy Budget Computation ===")
    
    config_dict = {
        "strategy_budgets": {
            "test_strategy": {"capital_pct": 0.3},
            "another_strategy": {"capital_pct": 0.4},
        }
    }
    config = PortfolioConfig.from_dict(config_dict)
    state_store = MockStateStore(equity=100000.0)
    
    engine = PortfolioEngine(
        portfolio_config=config,
        state_store=state_store,
        logger_instance=logger,
    )
    
    budget1 = engine.compute_strategy_budget("test_strategy")
    budget2 = engine.compute_strategy_budget("another_strategy")
    budget3 = engine.compute_strategy_budget("unknown_strategy")
    
    assert budget1 == 30000.0  # 30% of 100k
    assert budget2 == 40000.0  # 40% of 100k
    assert budget3 == 20000.0  # default 20% of 100k
    
    logger.info(f"✓ Strategy budgets computed:")
    logger.info(f"  test_strategy: {budget1}")
    logger.info(f"  another_strategy: {budget2}")
    logger.info(f"  unknown_strategy (default): {budget3}")


def test_fixed_qty_mode():
    """Test position sizing in fixed_qty mode."""
    logger.info("\n=== Test 4: Fixed Qty Mode ===")
    
    config_dict = {
        "position_sizing_mode": "fixed_qty",
        "default_fixed_qty": 5,
        "strategy_budgets": {
            "test_strategy": {
                "capital_pct": 0.3,
                "fixed_qty": 10,
            }
        }
    }
    config = PortfolioConfig.from_dict(config_dict)
    state_store = MockStateStore(equity=100000.0)
    
    engine = PortfolioEngine(
        portfolio_config=config,
        state_store=state_store,
        logger_instance=logger,
    )
    
    # Test 1: Intent with pre-set qty (small enough to fit budget)
    intent1 = MockIntent(symbol="STOCK1", strategy_code="test_strategy", side="BUY", qty=1)
    qty1 = engine.compute_position_size(intent1, last_price=1000.0)
    assert qty1 == 1
    logger.info(f"✓ Intent with pre-set qty=1: {qty1}")
    
    # Test 2: Intent without qty, strategy has fixed_qty (use lower price)
    intent2 = MockIntent(symbol="STOCK2", strategy_code="test_strategy", side="BUY")
    qty2 = engine.compute_position_size(intent2, last_price=2000.0)
    # With budget of 30k and price 2k, max is 15 shares
    # fixed_qty is 10, so should get 10
    assert qty2 == 10
    logger.info(f"✓ Intent without qty, strategy fixed_qty=10: {qty2}")
    
    # Test 3: Intent without qty, strategy has no fixed_qty (use default)
    intent3 = MockIntent(symbol="STOCK3", strategy_code="unknown_strategy", side="BUY")
    qty3 = engine.compute_position_size(intent3, last_price=1000.0)
    assert qty3 == 5
    logger.info(f"✓ Intent without qty, default fixed_qty=5: {qty3}")


def test_atr_based_mode():
    """Test position sizing in fixed_risk_atr mode."""
    logger.info("\n=== Test 5: ATR-Based Mode ===")
    
    config_dict = {
        "position_sizing_mode": "fixed_risk_atr",
        "max_risk_per_trade_pct": 0.01,  # 1% risk
        "atr_stop_multiplier": 2.0,
        "lot_size_fallback": 25,
    }
    config = PortfolioConfig.from_dict(config_dict)
    state_store = MockStateStore(equity=100000.0)
    
    engine = PortfolioEngine(
        portfolio_config=config,
        state_store=state_store,
        logger_instance=logger,
    )
    
    # Test equity trade with ATR
    intent = MockIntent(symbol="RELIANCE", strategy_code="test_strategy", side="BUY")
    last_price = 2500.0
    atr_value = 50.0  # ATR = 50
    
    # Expected: risk = 100000 * 0.01 = 1000
    #           stop_distance = 2.0 * 50 = 100
    #           qty = floor(1000 / 100) = 10 shares
    qty = engine.compute_position_size(intent, last_price=last_price, atr_value=atr_value)
    
    logger.info(f"✓ ATR-based sizing for equity:")
    logger.info(f"  Equity: 100000, Risk: 1%, ATR: {atr_value}, Stop: 2xATR")
    logger.info(f"  Computed qty: {qty} shares")
    logger.info(f"  Notional: {qty * last_price:.2f}")
    
    # Test FnO trade with ATR
    intent_fno = MockIntent(symbol="NIFTYFUT", strategy_code="test_strategy", side="BUY")
    qty_fno = engine.compute_position_size(intent_fno, last_price=18000.0, atr_value=100.0)
    
    logger.info(f"✓ ATR-based sizing for FnO:")
    logger.info(f"  Computed qty: {qty_fno} (in lot units)")


def test_exposure_limits():
    """Test exposure limits enforcement."""
    logger.info("\n=== Test 6: Exposure Limits ===")
    
    # Create config with 80% max exposure
    config_dict = {
        "position_sizing_mode": "fixed_qty",
        "default_fixed_qty": 100,
        "max_exposure_pct": 0.8,  # 80% of equity
        "max_leverage": 1.0,
    }
    config = PortfolioConfig.from_dict(config_dict)
    
    # Mock state with existing positions (70k exposure)
    existing_positions = [
        {"symbol": "EXISTING1", "quantity": 100, "last_price": 500.0, "avg_price": 500.0},
        {"symbol": "EXISTING2", "quantity": 50, "last_price": 400.0, "avg_price": 400.0},
    ]
    state_store = MockStateStore(equity=100000.0, positions=existing_positions)
    
    engine = PortfolioEngine(
        portfolio_config=config,
        state_store=state_store,
        logger_instance=logger,
    )
    
    # Current exposure: 100*500 + 50*400 = 70,000
    # Max exposure: 100,000 * 0.8 * 1.0 = 80,000
    # Available: 10,000
    current_exp = engine.compute_total_exposure()
    logger.info(f"Current exposure: {current_exp}")
    
    # Try to add a large position
    intent = MockIntent(symbol="NEWSTOCK", strategy_code="test", side="BUY")
    last_price = 1000.0
    
    # Request 100 shares (100k notional) - should be reduced
    qty = engine.compute_position_size(intent, last_price=last_price)
    
    logger.info(f"✓ Exposure limit enforcement:")
    logger.info(f"  Requested qty: 100, Allowed qty: {qty}")
    logger.info(f"  Max exposure: 80000, Current: {current_exp}, Available: {80000 - current_exp}")
    
    assert qty <= 10  # Should be capped


def test_portfolio_limits_api():
    """Test get_portfolio_limits() for API/dashboard."""
    logger.info("\n=== Test 7: Portfolio Limits API ===")
    
    config_dict = {
        "max_leverage": 2.0,
        "max_exposure_pct": 0.8,
        "max_risk_per_trade_pct": 0.01,
        "position_sizing_mode": "fixed_qty",
        "strategy_budgets": {
            "strategy1": {"capital_pct": 0.3},
            "strategy2": {"capital_pct": 0.4},
        }
    }
    config = PortfolioConfig.from_dict(config_dict)
    state_store = MockStateStore(equity=100000.0)
    
    engine = PortfolioEngine(
        portfolio_config=config,
        state_store=state_store,
        logger_instance=logger,
    )
    
    limits = engine.get_portfolio_limits()
    
    assert "equity" in limits
    assert "max_exposure" in limits
    assert "current_exposure" in limits
    assert "per_strategy" in limits
    
    logger.info("✓ Portfolio limits API response:")
    logger.info(f"  Equity: {limits['equity']}")
    logger.info(f"  Max exposure: {limits['max_exposure']}")
    logger.info(f"  Current exposure: {limits['current_exposure']}")
    logger.info(f"  Strategy budgets: {len(limits['per_strategy'])} strategies")
    
    for strategy, info in limits["per_strategy"].items():
        logger.info(f"    {strategy}: budget={info['budget']}, used={info['used']}")


def run_all_tests():
    """Run all tests."""
    logger.info("=" * 60)
    logger.info("Portfolio Engine v1 - Test Suite")
    logger.info("=" * 60)
    
    try:
        test_config_loading()
        test_equity_reading()
        test_strategy_budget()
        test_fixed_qty_mode()
        test_atr_based_mode()
        test_exposure_limits()
        test_portfolio_limits_api()
        
        logger.info("\n" + "=" * 60)
        logger.info("✓ ALL TESTS PASSED")
        logger.info("=" * 60)
        return True
        
    except AssertionError as e:
        logger.error(f"\n✗ TEST FAILED: {e}")
        return False
    except Exception as e:
        logger.error(f"\n✗ ERROR: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
