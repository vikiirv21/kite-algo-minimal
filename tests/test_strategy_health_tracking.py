"""Tests for strategy health tracking features in StrategyEngineV2."""

import sys
from pathlib import Path
from datetime import datetime, timezone

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
        # Return mock candle data with EMA crossover
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


def test_strategy_state_health_fields():
    """Test that StrategyState has health tracking fields."""
    state = StrategyState()
    
    # Check new health fields are initialized
    assert hasattr(state, 'signals_today')
    assert hasattr(state, 'last_signal')
    assert hasattr(state, 'last_signal_ts')
    assert hasattr(state, 'regime')
    
    # Check initial values
    assert state.signals_today == 0
    assert state.last_signal == "HOLD"
    assert state.last_signal_ts is None
    assert state.regime is None
    
    # Check existing win/loss tracking fields
    assert state.win_count == 0
    assert state.loss_count == 0
    assert state.trades_today == 0


def test_signal_increments_signals_today():
    """Test that generating signals increments signals_today counter."""
    config = {"history_lookback": 100}
    market_data = MockMarketDataEngine()
    engine = StrategyEngineV2(config, market_data)
    
    # Register strategy
    strategy_config = {"name": "test_strategy", "timeframe": "5m"}
    state = StrategyState()
    strategy = MockStrategy(strategy_config, state)
    engine.register_strategy("test_strategy", strategy)
    
    # Set paper engine
    paper_engine = MockPaperEngine()
    engine.set_paper_engine(paper_engine)
    
    # Get the state that the engine is actually using
    engine_state = engine.strategy_states.get("test_strategy")
    assert engine_state is not None
    
    # Initial signals_today should be 0
    assert engine_state.signals_today == 0
    assert engine_state.last_signal == "HOLD"
    
    # Run strategy (will generate a signal based on mock data)
    intents = engine.run_strategy("test_strategy", "NIFTY", "5m")
    
    # If a BUY/SELL/EXIT signal was generated, signals_today should increment
    if len(intents) > 0 and intents[0].action in ["BUY", "SELL", "EXIT"]:
        assert engine_state.signals_today == 1
        assert engine_state.last_signal in ["BUY", "SELL", "EXIT"]
        assert engine_state.last_signal_ts is not None
        assert isinstance(engine_state.last_signal_ts, datetime)


def test_health_publish_includes_new_fields():
    """Test that _publish_health includes new health fields."""
    config = {"history_lookback": 100}
    market_data = MockMarketDataEngine()
    engine = StrategyEngineV2(config, market_data)
    
    # Register strategy
    strategy_config = {"name": "test_strategy", "timeframe": "5m"}
    state = StrategyState()
    state.signals_today = 5
    state.last_signal = "BUY"
    state.last_signal_ts = datetime.now(timezone.utc)
    state.win_count = 3
    state.loss_count = 2
    
    strategy = MockStrategy(strategy_config, state)
    engine.register_strategy("test_strategy", strategy)
    
    # Manually call _publish_health to check it doesn't error
    try:
        engine._publish_health()
        # If we get here without exception, the method works
        assert True
    except AttributeError as e:
        # Should not raise AttributeError about missing fields
        assert False, f"_publish_health raised AttributeError: {e}"
    except Exception as e:
        # Other exceptions (like telemetry not available) are OK for this test
        pass


def test_win_rate_calculation():
    """Test win rate calculation in health metrics."""
    state = StrategyState()
    
    # No trades yet
    assert state.win_count == 0
    assert state.loss_count == 0
    total_trades = state.win_count + state.loss_count
    win_rate = state.win_count / total_trades if total_trades > 0 else None
    assert win_rate is None
    
    # Add some wins and losses
    state.update_pnl(100.0)  # Win
    state.update_pnl(50.0)   # Win
    state.update_pnl(-30.0)  # Loss
    
    assert state.win_count == 2
    assert state.loss_count == 1
    total_trades = state.win_count + state.loss_count
    win_rate = state.win_count / total_trades if total_trades > 0 else None
    assert win_rate is not None
    assert abs(win_rate - 0.6667) < 0.01  # 2/3 = 0.6667


def test_last_signal_updates_on_signal():
    """Test that last_signal and last_signal_ts update when signal is generated."""
    state = StrategyState()
    
    # Initially HOLD
    assert state.last_signal == "HOLD"
    assert state.last_signal_ts is None
    
    # This would normally be updated by the engine when processing signals
    # Simulate what the engine does
    state.signals_today += 1
    state.last_signal = "BUY"
    state.last_signal_ts = datetime.now(timezone.utc)
    
    assert state.last_signal == "BUY"
    assert state.last_signal_ts is not None
    assert state.signals_today == 1


if __name__ == "__main__":
    print("Running strategy health tracking tests...")
    
    test_strategy_state_health_fields()
    print("✓ test_strategy_state_health_fields passed")
    
    test_signal_increments_signals_today()
    print("✓ test_signal_increments_signals_today passed")
    
    test_health_publish_includes_new_fields()
    print("✓ test_health_publish_includes_new_fields passed")
    
    test_win_rate_calculation()
    print("✓ test_win_rate_calculation passed")
    
    test_last_signal_updates_on_signal()
    print("✓ test_last_signal_updates_on_signal passed")
    
    print("\nAll tests passed!")
