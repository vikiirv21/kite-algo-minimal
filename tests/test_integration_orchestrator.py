"""Integration test for StrategyEngine v2 with Orchestrator v3"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.strategy_engine_v2 import (
    BaseStrategy, OrderIntent, StrategyState, StrategyEngineV2
)
from strategies.base import Decision


class TestStrategy(BaseStrategy):
    """Test strategy for integration testing."""
    
    def generate_signal(self, candle, series, indicators):
        close = candle.get("close", 0)
        ema20 = indicators.get("ema20", 0)
        ema50 = indicators.get("ema50", 0)
        
        if ema20 > ema50 and close > ema20:
            return Decision(action="BUY", reason="test_buy", confidence=0.8)
        return Decision(action="HOLD", reason="test_hold", confidence=0.0)


class MockMarketDataEngine:
    """Mock market data engine."""
    
    def get_window(self, symbol, timeframe, window_size):
        candles = []
        for i in range(window_size):
            candles.append({
                "open": 100.0 + i,
                "high": 105.0 + i,
                "low": 95.0 + i,
                "close": 100.0 + i,
                "volume": 1000,
            })
        return candles
    
    def get_latest_candle(self, symbol, timeframe):
        return {
            "open": 100.0,
            "high": 105.0,
            "low": 95.0,
            "close": 100.0,
            "volume": 1000,
        }


class MockStateStore:
    """Mock state store."""
    
    def __init__(self):
        self.data = {}
    
    def load_checkpoint(self):
        return self.data


class MockPaperEngine:
    """Mock paper engine."""
    
    def __init__(self):
        self.signals = []
        self.logical_alias = {}
    
    def _handle_signal(self, symbol, action, price, logical, tf, strategy_name, strategy_code, confidence, reason):
        self.signals.append({
            "symbol": symbol,
            "action": action,
            "price": price,
            "strategy_code": strategy_code,
            "confidence": confidence,
            "reason": reason,
        })


def test_integration_orchestrator_disabled():
    """Test that everything works with orchestrator disabled (default)."""
    config = {
        "history_lookback": 100,
        "strategies": ["test_strategy"],
        "timeframe": "5m",
        # orchestrator disabled by default
    }
    market_data = MockMarketDataEngine()
    state_store = MockStateStore()
    
    # Create engine
    engine = StrategyEngineV2(
        config,
        market_data,
        state_store=state_store,
        analytics=None
    )
    
    # Register strategy
    strategy_config = {"name": "test_strategy", "timeframe": "5m"}
    state = StrategyState()
    strategy = TestStrategy(strategy_config, state)
    engine.register_strategy("test_strategy", strategy)
    
    # Set mock paper engine
    paper_engine = MockPaperEngine()
    engine.set_paper_engine(paper_engine)
    
    # Run strategy
    symbols = ["NIFTY"]
    engine.run(symbols)
    
    # Should have generated signals (orchestrator disabled, so no blocking)
    assert len(paper_engine.signals) > 0
    print(f"✓ Generated {len(paper_engine.signals)} signals with orchestrator disabled")


def test_integration_orchestrator_enabled():
    """Test that orchestrator works when enabled."""
    config = {
        "history_lookback": 100,
        "strategies": ["test_strategy"],
        "timeframe": "5m",
        "strategy_orchestrator": {
            "enabled": True,
            "health_scoring_window": 20,
            "loss_streak_disable": 3,
            "enforce_regimes": False,  # Disable regime checks for simple test
        }
    }
    market_data = MockMarketDataEngine()
    state_store = MockStateStore()
    
    # Create engine
    engine = StrategyEngineV2(
        config,
        market_data,
        state_store=state_store,
        analytics=None
    )
    
    # Verify orchestrator was created
    assert engine.orchestrator is not None
    assert engine.orchestrator.enabled is True
    
    # Register strategy
    strategy_config = {"name": "test_strategy", "timeframe": "5m"}
    state = StrategyState()
    strategy = TestStrategy(strategy_config, state)
    engine.register_strategy("test_strategy", strategy)
    
    # Set mock paper engine
    paper_engine = MockPaperEngine()
    engine.set_paper_engine(paper_engine)
    
    # Run strategy
    symbols = ["NIFTY"]
    engine.run(symbols)
    
    # Should have generated signals (orchestrator allows by default)
    assert len(paper_engine.signals) > 0
    print(f"✓ Generated {len(paper_engine.signals)} signals with orchestrator enabled")


def test_integration_orchestrator_blocks_strategy():
    """Test that orchestrator can block a strategy."""
    config = {
        "history_lookback": 100,
        "strategies": ["test_strategy"],
        "timeframe": "5m",
        "strategy_orchestrator": {
            "enabled": True,
            "loss_streak_disable": 2,  # Block after 2 losses
            "enforce_regimes": False,
        }
    }
    market_data = MockMarketDataEngine()
    state_store = MockStateStore()
    
    # Create engine
    engine = StrategyEngineV2(
        config,
        market_data,
        state_store=state_store,
        analytics=None
    )
    
    # Register strategy
    strategy_config = {"name": "test_strategy", "timeframe": "5m"}
    state = StrategyState()
    strategy = TestStrategy(strategy_config, state)
    engine.register_strategy("test_strategy", strategy)
    
    # Set mock paper engine
    paper_engine = MockPaperEngine()
    engine.set_paper_engine(paper_engine)
    
    # Simulate 2 consecutive losses
    engine.orchestrator.update_after_trade("test_strategy", -100.0)
    engine.orchestrator.update_after_trade("test_strategy", -50.0)
    
    # Clear previous signals
    paper_engine.signals.clear()
    
    # Run strategy - should be blocked
    symbols = ["NIFTY"]
    engine.run(symbols)
    
    # Should NOT have generated signals (orchestrator blocked it)
    assert len(paper_engine.signals) == 0
    print("✓ Orchestrator successfully blocked strategy after loss streak")


def test_backward_compatibility():
    """Test that old code without state_store still works."""
    config = {
        "history_lookback": 100,
        "strategies": ["test_strategy"],
        "timeframe": "5m",
    }
    market_data = MockMarketDataEngine()
    
    # Create engine WITHOUT state_store (old way)
    engine = StrategyEngineV2(config, market_data)
    
    # Should not have orchestrator
    assert engine.orchestrator is None
    
    # Register strategy
    strategy_config = {"name": "test_strategy", "timeframe": "5m"}
    state = StrategyState()
    strategy = TestStrategy(strategy_config, state)
    engine.register_strategy("test_strategy", strategy)
    
    # Set mock paper engine
    paper_engine = MockPaperEngine()
    engine.set_paper_engine(paper_engine)
    
    # Run strategy
    symbols = ["NIFTY"]
    engine.run(symbols)
    
    # Should work normally without orchestrator
    assert len(paper_engine.signals) > 0
    print("✓ Backward compatibility maintained - works without state_store")


def run_all_tests():
    """Run all integration tests."""
    tests = [
        test_integration_orchestrator_disabled,
        test_integration_orchestrator_enabled,
        test_integration_orchestrator_blocks_strategy,
        test_backward_compatibility,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            print(f"✓ {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print(f"\nIntegration Test Results: {passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
