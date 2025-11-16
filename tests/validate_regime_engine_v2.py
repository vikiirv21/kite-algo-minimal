#!/usr/bin/env python3
"""
Manual validation script for RegimeEngine v2 implementation.
Tests the complete integration end-to-end.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime, timezone
from unittest.mock import Mock
import yaml

from core.regime_engine import RegimeEngine, RegimeSnapshot
from core.strategy_engine_v2 import StrategyEngineV2
from core.portfolio_engine import PortfolioEngine, PortfolioConfig
from core.trade_guardian import TradeGuardian
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_config_loading():
    """Test that config loads correctly."""
    logger.info("TEST 1: Config Loading")
    
    with open("configs/dev.yaml") as f:
        config = yaml.safe_load(f)
    
    assert "regime_engine" in config, "regime_engine section missing from config"
    
    regime_config = config["regime_engine"]
    assert regime_config["enabled"] is True, "regime_engine should be enabled"
    assert regime_config["bar_period"] == "1m", "bar_period should be 1m"
    assert regime_config["slope_period"] == 20, "slope_period should be 20"
    assert regime_config["atr_period"] == 14, "atr_period should be 14"
    
    logger.info("✅ Config loads correctly with regime_engine section")


def test_regime_engine_standalone():
    """Test RegimeEngine standalone functionality."""
    logger.info("\nTEST 2: RegimeEngine Standalone")
    
    config = {
        "regime_engine": {
            "enabled": True,
            "bar_period": "1m",
            "slope_period": 20,
            "atr_period": 14,
        }
    }
    
    # Mock MDE with trending data
    mde = Mock()
    candles = []
    for i in range(100):
        candle = Mock()
        candle.open = 100.0 + i * 0.5
        candle.high = 101.0 + i * 0.5
        candle.low = 99.0 + i * 0.5
        candle.close = 100.0 + i * 0.5
        candles.append(candle)
    
    mde.get_candles = Mock(return_value=candles)
    
    # Create engine
    engine = RegimeEngine(config, mde, logger)
    
    # Get snapshot
    snapshot = engine.snapshot("NIFTY")
    
    assert isinstance(snapshot, RegimeSnapshot), "Should return RegimeSnapshot"
    assert snapshot.trend in ["up", "down", "flat"], f"Invalid trend: {snapshot.trend}"
    assert snapshot.volatility in ["high", "medium", "low"], f"Invalid volatility: {snapshot.volatility}"
    assert snapshot.structure in ["breakout", "range", "reversal", "none"], f"Invalid structure: {snapshot.structure}"
    assert isinstance(snapshot.atr, float), "ATR should be float"
    assert isinstance(snapshot.velocity, float), "Velocity should be float"
    
    logger.info(f"✅ RegimeEngine works: trend={snapshot.trend}, volatility={snapshot.volatility}, structure={snapshot.structure}")


def test_regime_engine_disabled():
    """Test that disabled regime engine returns neutral regime."""
    logger.info("\nTEST 3: RegimeEngine Disabled")
    
    config = {"regime_engine": {"enabled": False}}
    mde = Mock()
    
    engine = RegimeEngine(config, mde, logger)
    snapshot = engine.snapshot("NIFTY")
    
    assert snapshot.trend == "flat", "Disabled engine should return flat trend"
    assert snapshot.volatility == "medium", "Disabled engine should return medium volatility"
    assert snapshot.structure == "none", "Disabled engine should return none structure"
    
    logger.info("✅ Disabled regime engine returns neutral regime")


def test_strategy_engine_integration():
    """Test StrategyEngineV2 integration with RegimeEngine."""
    logger.info("\nTEST 4: StrategyEngineV2 Integration")
    
    config = {
        "history_lookback": 200,
        "strategies": [],
        "regime_engine": {"enabled": True}
    }
    
    # Mock MDE
    mde = Mock()
    mde.get_window = Mock(return_value=[
        {"open": 100, "high": 101, "low": 99, "close": 100, "volume": 1000}
        for _ in range(100)
    ])
    
    # Mock RegimeEngine
    regime_engine = Mock()
    regime_engine.snapshot = Mock(return_value=RegimeSnapshot(
        trend="up",
        volatility="high",
        structure="breakout",
        velocity=0.5,
        atr=2.0,
        slope=0.3,
        timestamp=datetime.now(timezone.utc)
    ))
    
    # Create StrategyEngineV2 with RegimeEngine
    engine = StrategyEngineV2(
        config=config,
        market_data_engine=mde,
        regime_engine=regime_engine
    )
    
    assert engine.regime_engine is not None, "RegimeEngine should be set"
    
    logger.info("✅ StrategyEngineV2 accepts regime_engine parameter")


def test_portfolio_engine_integration():
    """Test PortfolioEngine integration with RegimeEngine."""
    logger.info("\nTEST 5: PortfolioEngine Integration")
    
    config_dict = {
        "position_sizing_mode": "fixed_qty",
        "default_fixed_qty": 10
    }
    
    portfolio_config = PortfolioConfig.from_dict(config_dict)
    state_store = Mock()
    state_store.load_checkpoint = Mock(return_value={
        "equity": {"paper_capital": 100000, "realized_pnl": 0, "unrealized_pnl": 0}
    })
    
    # Mock RegimeEngine with high volatility
    regime_engine = Mock()
    regime_engine.snapshot = Mock(return_value=RegimeSnapshot(
        trend="up",
        volatility="high",
        structure="none",
        velocity=0.5,
        atr=5.0,
        slope=0.3,
        timestamp=datetime.now(timezone.utc)
    ))
    
    # Create PortfolioEngine with RegimeEngine
    engine = PortfolioEngine(
        portfolio_config=portfolio_config,
        state_store=state_store,
        regime_engine=regime_engine
    )
    
    # Mock intent
    intent = Mock()
    intent.symbol = "NIFTY"
    intent.strategy_code = "test_strategy"
    intent.qty = None
    
    # Compute position size
    qty = engine.compute_position_size(intent, last_price=100.0)
    
    assert qty == 6, f"Expected qty=6 (10 * 0.6), got {qty}"
    
    logger.info(f"✅ PortfolioEngine applies regime adjustments: 10 -> {qty} (high vol reduction)")


def test_guardian_integration():
    """Test TradeGuardian integration with RegimeEngine."""
    logger.info("\nTEST 6: TradeGuardian Integration")
    
    config = {
        "guardian": {
            "enabled": True,
            "max_order_per_second": 5,
            "max_lot_size": 50
        }
    }
    
    state_store = Mock()
    state_store.load_checkpoint = Mock(return_value={})
    
    # Mock RegimeEngine
    regime_engine = Mock()
    regime_engine.snapshot = Mock(return_value=RegimeSnapshot(
        trend="up",
        volatility="high",
        structure="none",
        velocity=0.5,
        atr=5.0,
        slope=0.3,
        timestamp=datetime.now(timezone.utc)
    ))
    
    # Create TradeGuardian with RegimeEngine
    guardian = TradeGuardian(
        config=config,
        state_store=state_store,
        logger_instance=logger,
        regime_engine=regime_engine
    )
    
    # Mock intent
    intent = Mock()
    intent.symbol = "NIFTY"
    intent.qty = 10
    intent.price = 100.0
    
    # Validate trade
    decision = guardian.validate_pre_trade(intent)
    
    assert decision.allow is True, "Guardian should allow valid trade"
    
    logger.info("✅ TradeGuardian works with regime_engine parameter")


def test_backward_compatibility():
    """Test that all components work without regime_engine."""
    logger.info("\nTEST 7: Backward Compatibility")
    
    # Test StrategyEngineV2 without regime_engine
    config = {"history_lookback": 200, "strategies": []}
    mde = Mock()
    mde.get_window = Mock(return_value=[
        {"open": 100, "high": 101, "low": 99, "close": 100, "volume": 1000}
        for _ in range(100)
    ])
    
    engine = StrategyEngineV2(config=config, market_data_engine=mde, regime_engine=None)
    assert engine.regime_engine is None, "Should work without regime_engine"
    
    # Test PortfolioEngine without regime_engine
    portfolio_config = PortfolioConfig.from_dict({"default_fixed_qty": 10})
    state_store = Mock()
    state_store.load_checkpoint = Mock(return_value={
        "equity": {"paper_capital": 100000, "realized_pnl": 0, "unrealized_pnl": 0}
    })
    
    portfolio = PortfolioEngine(
        portfolio_config=portfolio_config,
        state_store=state_store,
        regime_engine=None
    )
    
    intent = Mock()
    intent.symbol = "NIFTY"
    intent.strategy_code = "test"
    intent.qty = None
    
    qty = portfolio.compute_position_size(intent, last_price=100.0)
    assert qty == 10, f"Should return base qty without adjustments, got {qty}"
    
    # Test TradeGuardian without regime_engine
    config = {"guardian": {"enabled": True, "max_lot_size": 50}}
    state_store = Mock()
    state_store.load_checkpoint = Mock(return_value={})
    
    guardian = TradeGuardian(config, state_store, logger, regime_engine=None)
    
    intent = Mock()
    intent.symbol = "NIFTY"
    intent.qty = 10
    
    decision = guardian.validate_pre_trade(intent)
    assert decision.allow is True, "Should work without regime_engine"
    
    logger.info("✅ All components work without regime_engine (backward compatible)")


def main():
    """Run all validation tests."""
    logger.info("=" * 60)
    logger.info("REGIME ENGINE V2 - MANUAL VALIDATION")
    logger.info("=" * 60)
    
    try:
        test_config_loading()
        test_regime_engine_standalone()
        test_regime_engine_disabled()
        test_strategy_engine_integration()
        test_portfolio_engine_integration()
        test_guardian_integration()
        test_backward_compatibility()
        
        logger.info("\n" + "=" * 60)
        logger.info("✅ ALL VALIDATION TESTS PASSED")
        logger.info("=" * 60)
        logger.info("\nRegimeEngine v2 is ready for deployment!")
        logger.info("Recommendation: Start with enabled=false for Monday paper trading")
        
        return 0
    
    except Exception as e:
        logger.error("\n" + "=" * 60)
        logger.error(f"❌ VALIDATION FAILED: {e}")
        logger.error("=" * 60)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
