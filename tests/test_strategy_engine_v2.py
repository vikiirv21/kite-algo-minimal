"""Tests for core/strategy_engine_v2.py"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.strategy_engine_v2 import (
    BaseStrategy, OrderIntent, StrategyState, StrategyEngineV2
)
from strategies.base import Decision


class MockStrategy(BaseStrategy):
    """Mock strategy for testing."""
    
    def generate_signal(self, candle, series, indicators):
        close = candle.get("close", 0)
        ema20 = indicators.get("ema20", 0)
        ema50 = indicators.get("ema50", 0)
        
        if ema20 > ema50 and close > ema20:
            return Decision(action="BUY", reason="test_buy", confidence=0.8)
        elif ema20 < ema50 and close < ema20:
            return Decision(action="SELL", reason="test_sell", confidence=0.8)
        return Decision(action="HOLD", reason="test_hold", confidence=0.0)


class MockMarketDataEngine:
    """Mock market data engine for testing."""
    
    def get_window(self, symbol, timeframe, window_size):
        # Return mock candle data
        candles = []
        for i in range(window_size):
            candles.append({
                "open": 100.0 + i,
                "high": 105.0 + i,
                "low": 95.0 + i,
                "close": 100.0 + i,
                "volume": 1000,
                "ts": f"2024-01-01T{i:02d}:00:00Z"
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


class MockPaperEngine:
    """Mock paper engine for testing."""
    
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


def test_strategy_state():
    """Test StrategyState class."""
    state = StrategyState()
    
    # Initially no positions
    assert not state.is_position_open("NIFTY")
    assert not state.is_long("NIFTY")
    assert not state.is_short("NIFTY")
    
    # Open long position
    state.update_position("NIFTY", 1, 100.0)
    assert state.is_position_open("NIFTY")
    assert state.is_long("NIFTY")
    assert not state.is_short("NIFTY")
    
    # Open short position
    state.update_position("BANKNIFTY", -1, 200.0)
    assert state.is_position_open("BANKNIFTY")
    assert state.is_short("BANKNIFTY")
    assert not state.is_long("BANKNIFTY")
    
    # Close position
    state.update_position("NIFTY", 0)
    assert not state.is_position_open("NIFTY")


def test_order_intent():
    """Test OrderIntent class."""
    intent = OrderIntent(
        symbol="NIFTY",
        action="BUY",
        qty=1,
        reason="test_reason",
        strategy_code="test_strategy",
        confidence=0.8
    )
    
    assert intent.symbol == "NIFTY"
    assert intent.action == "BUY"
    assert intent.qty == 1
    assert intent.confidence == 0.8
    
    # Test to_dict
    d = intent.to_dict()
    assert d["symbol"] == "NIFTY"
    assert d["action"] == "BUY"


def test_base_strategy_methods():
    """Test BaseStrategy helper methods."""
    config = {"name": "test_strategy", "timeframe": "5m"}
    state = StrategyState()
    strategy = MockStrategy(config, state)
    
    # Test long()
    intent = strategy.long("NIFTY", qty=1, reason="test_long")
    assert intent.action == "BUY"
    assert intent.symbol == "NIFTY"
    
    # Test short()
    intent = strategy.short("BANKNIFTY", qty=1, reason="test_short")
    assert intent.action == "SELL"
    assert intent.symbol == "BANKNIFTY"
    
    # Test exit()
    state.update_position("NIFTY", 1, 100.0)
    intent = strategy.exit("NIFTY", reason="test_exit")
    assert intent.action == "EXIT"
    
    # Test position checks
    state.update_position("NIFTY", 1, 100.0)
    assert strategy.position_is_long("NIFTY")
    assert not strategy.position_is_short("NIFTY")
    
    state.update_position("NIFTY", -1, 100.0)
    assert strategy.position_is_short("NIFTY")
    assert not strategy.position_is_long("NIFTY")


def test_strategy_engine_v2_init():
    """Test StrategyEngineV2 initialization."""
    config = {
        "history_lookback": 100,
        "strategies": ["test_strategy"],
        "timeframe": "5m"
    }
    market_data = MockMarketDataEngine()
    
    engine = StrategyEngineV2(config, market_data)
    
    assert engine.window_size == 100
    assert len(engine.enabled_strategies) == 1


def test_strategy_engine_v2_register():
    """Test strategy registration."""
    config = {"history_lookback": 100}
    market_data = MockMarketDataEngine()
    engine = StrategyEngineV2(config, market_data)
    
    strategy_config = {"name": "test_strategy", "timeframe": "5m"}
    state = StrategyState()
    strategy = MockStrategy(strategy_config, state)
    
    engine.register_strategy("test_strategy", strategy)
    
    assert "test_strategy" in engine.strategies
    assert "test_strategy" in engine.strategy_states


def test_strategy_engine_v2_compute_indicators():
    """Test indicator computation."""
    config = {"history_lookback": 100}
    market_data = MockMarketDataEngine()
    engine = StrategyEngineV2(config, market_data)
    
    # Create mock series
    series = {
        "close": [100.0 + i * 0.5 for i in range(100)],
        "high": [105.0 + i * 0.5 for i in range(100)],
        "low": [95.0 + i * 0.5 for i in range(100)],
        "volume": [1000] * 100,
    }
    
    indicators = engine.compute_indicators(series)
    
    # Check that indicators were computed
    assert "ema20" in indicators
    assert "ema50" in indicators
    assert "sma20" in indicators
    assert "rsi14" in indicators
    assert "atr14" in indicators
    assert "trend" in indicators


def test_strategy_engine_v2_run_strategy():
    """Test running a single strategy."""
    config = {"history_lookback": 100, "timeframe": "5m"}
    market_data = MockMarketDataEngine()
    engine = StrategyEngineV2(config, market_data)
    
    # Register strategy
    strategy_config = {"name": "test_strategy", "timeframe": "5m"}
    state = StrategyState()
    strategy = MockStrategy(strategy_config, state)
    engine.register_strategy("test_strategy", strategy)
    
    # Set mock paper engine
    paper_engine = MockPaperEngine()
    engine.set_paper_engine(paper_engine)
    
    # Run strategy
    intents = engine.run_strategy("test_strategy", "NIFTY", "5m")
    
    # Should generate some intent based on mock strategy logic
    assert isinstance(intents, list)


def run_all_tests():
    """Run all tests and report results."""
    tests = [
        test_strategy_state,
        test_order_intent,
        test_base_strategy_methods,
        test_strategy_engine_v2_init,
        test_strategy_engine_v2_register,
        test_strategy_engine_v2_compute_indicators,
        test_strategy_engine_v2_run_strategy,
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
    
    print(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
