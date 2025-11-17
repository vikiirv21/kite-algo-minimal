"""Tests for core/strategy_engine_v2.py"""

import sys
from pathlib import Path
from datetime import datetime, timezone

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.strategy_engine_v2 import (
    BaseStrategy, OrderIntent, StrategyState, StrategyEngineV2, StrategySignal
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


def test_strategy_state_pnl_tracking():
    """Test StrategyState PnL tracking and streak management."""
    state = StrategyState()
    
    # Test win streak
    state.update_pnl(100.0)
    assert state.win_streak == 1
    assert state.loss_streak == 0
    assert state.recent_pnl == 100.0
    
    state.update_pnl(50.0)
    assert state.win_streak == 2
    assert state.loss_streak == 0
    assert state.recent_pnl == 150.0
    
    # Test loss streak
    state.update_pnl(-30.0)
    assert state.win_streak == 0
    assert state.loss_streak == 1
    assert state.recent_pnl == 120.0
    
    state.update_pnl(-40.0)
    assert state.win_streak == 0
    assert state.loss_streak == 2
    assert state.recent_pnl == 80.0


def test_strategy_state_decision_recording():
    """Test StrategyState decision recording."""
    state = StrategyState()
    
    # Record some decisions
    state.record_decision("NIFTY", "long", 0.8, "test_reason")
    state.record_decision("BANKNIFTY", "short", 0.7, "test_reason2")
    
    assert len(state.recent_decisions) == 2
    assert state.recent_decisions[0]["symbol"] == "NIFTY"
    assert state.recent_decisions[0]["decision"] == "long"
    assert state.recent_decisions[1]["symbol"] == "BANKNIFTY"
    
    # Test max retention (20 decisions)
    for i in range(25):
        state.record_decision(f"SYM{i}", "long", 0.5, "test")
    
    assert len(state.recent_decisions) == 20


def test_strategy_signal():
    """Test StrategySignal class."""
    signal = StrategySignal(
        timestamp=datetime.utcnow().replace(tzinfo=timezone.utc),
        symbol="NIFTY",
        strategy_name="test_strategy",
        direction="long",
        strength=0.8,
        tags={"reason": "test_reason"}
    )
    
    assert signal.symbol == "NIFTY"
    assert signal.direction == "long"
    assert signal.strength == 0.8
    assert signal.tags["reason"] == "test_reason"
    
    # Test to_dict
    d = signal.to_dict()
    assert d["symbol"] == "NIFTY"
    assert d["direction"] == "long"
    
    # Test strength clamping
    signal2 = StrategySignal(
        timestamp=datetime.utcnow().replace(tzinfo=timezone.utc),
        symbol="NIFTY",
        strategy_name="test",
        direction="long",
        strength=1.5  # Should be clamped to 1.0
    )
    assert signal2.strength == 1.0
    
    signal3 = StrategySignal(
        timestamp=datetime.utcnow().replace(tzinfo=timezone.utc),
        symbol="NIFTY",
        strategy_name="test",
        direction="long",
        strength=-0.5  # Should be clamped to 0.0
    )
    assert signal3.strength == 0.0


def test_normalize_signal():
    """Test signal normalization."""
    config = {"history_lookback": 100}
    market_data = MockMarketDataEngine()
    engine = StrategyEngineV2(config, market_data)
    
    # Test BUY signal
    decision = Decision(action="BUY", reason="test_buy", confidence=0.8)
    signal = engine.normalize_signal(decision, "test_strategy", "NIFTY")
    
    assert signal is not None
    assert signal.direction == "long"
    assert signal.symbol == "NIFTY"
    assert signal.strategy_name == "test_strategy"
    assert signal.strength == 0.8
    
    # Test SELL signal
    decision = Decision(action="SELL", reason="test_sell", confidence=0.7)
    signal = engine.normalize_signal(decision, "test_strategy", "BANKNIFTY")
    
    assert signal is not None
    assert signal.direction == "short"
    
    # Test EXIT signal
    decision = Decision(action="EXIT", reason="test_exit", confidence=0.5)
    signal = engine.normalize_signal(decision, "test_strategy", "FINNIFTY")
    
    assert signal is not None
    assert signal.direction == "flat"
    
    # Test HOLD signal (should return None)
    decision = Decision(action="HOLD", reason="test_hold", confidence=0.0)
    signal = engine.normalize_signal(decision, "test_strategy", "NIFTY")
    
    assert signal is None


def test_filter_signal_basic():
    """Test basic signal filtering."""
    config = {"history_lookback": 100}
    market_data = MockMarketDataEngine()
    engine = StrategyEngineV2(config, market_data)
    
    # Valid signal
    signal = StrategySignal(
        timestamp=datetime.utcnow().replace(tzinfo=timezone.utc),
        symbol="NIFTY",
        strategy_name="test_strategy",
        direction="long",
        strength=0.8
    )
    
    allowed, reason = engine.filter_signal_basic(signal)
    assert allowed or reason == "market_closed"  # Market might be closed in test
    
    # Invalid symbol
    signal2 = StrategySignal(
        timestamp=datetime.utcnow().replace(tzinfo=timezone.utc),
        symbol="",
        strategy_name="test_strategy",
        direction="long",
        strength=0.8
    )
    
    allowed, reason = engine.filter_signal_basic(signal2)
    assert not allowed
    assert reason == "invalid_symbol"
    
    # Invalid direction
    signal3 = StrategySignal(
        timestamp=datetime.utcnow().replace(tzinfo=timezone.utc),
        symbol="NIFTY",
        strategy_name="test_strategy",
        direction="invalid",
        strength=0.8
    )
    
    allowed, reason = engine.filter_signal_basic(signal3)
    assert not allowed
    assert reason == "invalid_direction"


def test_filter_signal_risk():
    """Test risk-based signal filtering."""
    config = {
        "history_lookback": 100,
        "max_trades_per_day": 5,
        "max_loss_streak": 3
    }
    market_data = MockMarketDataEngine()
    engine = StrategyEngineV2(config, market_data)
    
    state = StrategyState()
    
    # Test max trades per day
    signal = StrategySignal(
        timestamp=datetime.utcnow().replace(tzinfo=timezone.utc),
        symbol="NIFTY",
        strategy_name="test_strategy",
        direction="long",
        strength=0.8
    )
    
    # Should pass when trades_today < max
    state.trades_today = 4
    allowed, reason = engine.filter_signal_risk(signal, state)
    assert allowed
    assert reason == "passed_risk"
    
    # Should fail when trades_today >= max
    state.trades_today = 5
    allowed, reason = engine.filter_signal_risk(signal, state)
    assert not allowed
    assert "max_trades_per_day" in reason
    
    # Test loss streak
    state.trades_today = 0
    state.loss_streak = 2
    allowed, reason = engine.filter_signal_risk(signal, state)
    assert allowed
    
    state.loss_streak = 3
    allowed, reason = engine.filter_signal_risk(signal, state)
    assert not allowed
    assert "loss_streak" in reason


def test_conflict_resolution_highest_confidence():
    """Test conflict resolution with highest confidence mode."""
    config = {
        "history_lookback": 100,
        "conflict_resolution": "highest_confidence"
    }
    market_data = MockMarketDataEngine()
    engine = StrategyEngineV2(config, market_data)
    
    # Create conflicting signals for same symbol
    signal1 = StrategySignal(
        timestamp=datetime.utcnow().replace(tzinfo=timezone.utc),
        symbol="NIFTY",
        strategy_name="strategy_a",
        direction="long",
        strength=0.7
    )
    
    signal2 = StrategySignal(
        timestamp=datetime.utcnow().replace(tzinfo=timezone.utc),
        symbol="NIFTY",
        strategy_name="strategy_b",
        direction="short",
        strength=0.9  # Higher confidence
    )
    
    resolved = engine.resolve_conflicts([signal1, signal2])
    
    # Should pick signal2 (highest confidence)
    assert len(resolved) == 1
    assert resolved[0].strategy_name == "strategy_b"
    assert resolved[0].strength == 0.9


def test_conflict_resolution_priority():
    """Test conflict resolution with priority mode."""
    config = {
        "history_lookback": 100,
        "conflict_resolution": "priority",
        "strategy_priorities": {
            "strategy_a": 100,
            "strategy_b": 50
        }
    }
    market_data = MockMarketDataEngine()
    engine = StrategyEngineV2(config, market_data)
    
    # Create conflicting signals
    signal1 = StrategySignal(
        timestamp=datetime.utcnow().replace(tzinfo=timezone.utc),
        symbol="NIFTY",
        strategy_name="strategy_a",  # Higher priority
        direction="long",
        strength=0.7
    )
    
    signal2 = StrategySignal(
        timestamp=datetime.utcnow().replace(tzinfo=timezone.utc),
        symbol="NIFTY",
        strategy_name="strategy_b",  # Lower priority
        direction="short",
        strength=0.9  # Even though confidence is higher
    )
    
    resolved = engine.resolve_conflicts([signal1, signal2])
    
    # Should pick signal1 (higher priority)
    assert len(resolved) == 1
    assert resolved[0].strategy_name == "strategy_a"


def test_conflict_resolution_no_conflict():
    """Test conflict resolution when strategies agree."""
    config = {
        "history_lookback": 100,
        "conflict_resolution": "highest_confidence"
    }
    market_data = MockMarketDataEngine()
    engine = StrategyEngineV2(config, market_data)
    
    # Create agreeing signals for same symbol
    signal1 = StrategySignal(
        timestamp=datetime.utcnow().replace(tzinfo=timezone.utc),
        symbol="NIFTY",
        strategy_name="strategy_a",
        direction="long",
        strength=0.7
    )
    
    signal2 = StrategySignal(
        timestamp=datetime.utcnow().replace(tzinfo=timezone.utc),
        symbol="NIFTY",
        strategy_name="strategy_b",
        direction="long",  # Same direction
        strength=0.9
    )
    
    resolved = engine.resolve_conflicts([signal1, signal2])
    
    # Should pick signal with highest confidence
    assert len(resolved) == 1
    assert resolved[0].strategy_name == "strategy_b"
    assert resolved[0].strength == 0.9


def test_conflict_resolution_different_symbols():
    """Test conflict resolution for different symbols."""
    config = {
        "history_lookback": 100,
        "conflict_resolution": "highest_confidence"
    }
    market_data = MockMarketDataEngine()
    engine = StrategyEngineV2(config, market_data)
    
    # Create signals for different symbols
    signal1 = StrategySignal(
        timestamp=datetime.utcnow().replace(tzinfo=timezone.utc),
        symbol="NIFTY",
        strategy_name="strategy_a",
        direction="long",
        strength=0.7
    )
    
    signal2 = StrategySignal(
        timestamp=datetime.utcnow().replace(tzinfo=timezone.utc),
        symbol="BANKNIFTY",  # Different symbol
        strategy_name="strategy_b",
        direction="short",
        strength=0.9
    )
    
    resolved = engine.resolve_conflicts([signal1, signal2])
    
    # Should keep both signals (no conflict)
    assert len(resolved) == 2


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
        # New tests
        test_strategy_state_pnl_tracking,
        test_strategy_state_decision_recording,
        test_strategy_signal,
        test_normalize_signal,
        test_filter_signal_basic,
        test_filter_signal_risk,
        test_conflict_resolution_highest_confidence,
        test_conflict_resolution_priority,
        test_conflict_resolution_no_conflict,
        test_conflict_resolution_different_symbols,
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
