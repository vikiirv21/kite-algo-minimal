"""
Integration test for SRDE (Strategy Real-Time Diagnostics Engine)

Tests the complete flow from strategy engine to diagnostics storage.
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from analytics.diagnostics import load_diagnostics, DIAGNOSTICS_DIR


def test_strategy_engine_v2_diagnostics_emission():
    """
    Test that StrategyEngineV2 emits diagnostics when evaluating strategies.
    """
    # Import after path setup
    from core.strategy_engine_v2 import StrategyEngineV2, BaseStrategy, StrategyState
    from strategies.base import Decision
    
    # Create a mock strategy
    class TestStrategy(BaseStrategy):
        def generate_signal(self, candle, series, indicators, context=None):
            ema20 = indicators.get("ema20", 0)
            ema50 = indicators.get("ema50", 0)
            close = candle.get("close", 0)
            
            if ema20 > ema50 and close > ema20:
                return Decision(action="BUY", reason="EMA crossover", confidence=0.8)
            return Decision(action="HOLD", reason="No signal", confidence=0.0)
    
    # Create strategy engine
    config = {
        "primary_strategy_id": "test_strategy",
        "window_size": 50,
    }
    engine = StrategyEngineV2(config=config)
    
    # Register test strategy
    state = StrategyState()
    strategy_config = {"strategy_id": "test_strategy", "timeframe": "5m"}
    strategy = TestStrategy(config=strategy_config, strategy_state=state)
    engine.register_strategy("test_strategy", strategy)
    
    # Prepare test data
    candle = {
        "open": 100.0,
        "high": 102.0,
        "low": 99.0,
        "close": 101.5,
        "volume": 1000,
    }
    
    indicators = {
        "ema20": 100.0,
        "ema50": 98.0,
        "rsi14": 65.0,
        "atr14": 2.5,
    }
    
    # Use a temporary directory for testing
    with tempfile.TemporaryDirectory() as tmpdir:
        test_diag_dir = Path(tmpdir) / "diagnostics"
        
        with patch('analytics.diagnostics.DIAGNOSTICS_DIR', test_diag_dir):
            # Evaluate strategy (this should emit diagnostics)
            intent, debug = engine.evaluate(
                logical="NIFTY",
                symbol="NIFTY24JANFUT",
                timeframe="5m",
                candle=candle,
                indicators=indicators,
                mode="paper",
                profile="intraday",
            )
            
            # Check that intent was created
            assert intent is not None
            assert intent.signal in ["BUY", "SELL", "HOLD"]
            
            # Load diagnostics (should have been written)
            diagnostics = load_diagnostics("NIFTY24JANFUT", "test_strategy", limit=10)
            
            # Verify diagnostics were emitted
            assert len(diagnostics) > 0, "Diagnostics should have been emitted"
            
            record = diagnostics[0]
            assert record["price"] == 101.5
            assert record["decision"] in ["BUY", "SELL", "HOLD"]
            assert "reason" in record
            assert "confidence" in record
            assert record.get("ema20") == 100.0
            assert record.get("ema50") == 98.0
            
            print("✓ Strategy engine emitted diagnostics successfully")


def test_diagnostics_non_blocking():
    """
    Test that diagnostics failures don't crash the strategy engine.
    """
    from core.strategy_engine_v2 import StrategyEngineV2, BaseStrategy, StrategyState
    from strategies.base import Decision
    
    class SimpleStrategy(BaseStrategy):
        def generate_signal(self, candle, series, indicators, context=None):
            return Decision(action="HOLD", reason="Test", confidence=0.5)
    
    config = {"primary_strategy_id": "simple"}
    engine = StrategyEngineV2(config=config)
    
    state = StrategyState()
    strategy = SimpleStrategy(config={"strategy_id": "simple"}, strategy_state=state)
    engine.register_strategy("simple", strategy)
    
    candle = {"close": 100.0}
    indicators = {}
    
    # Patch append_diagnostic to raise an exception
    with patch('analytics.diagnostics.append_diagnostic', side_effect=Exception("Simulated error")):
        # This should NOT crash even though diagnostics fails
        try:
            intent, debug = engine.evaluate(
                logical="TEST",
                symbol="TEST",
                timeframe="5m",
                candle=candle,
                indicators=indicators,
                mode="paper",
                profile="intraday",
            )
            
            # Engine should continue working
            assert intent is not None
            assert intent.signal == "HOLD"
            
            print("✓ Diagnostics failure handled gracefully (non-blocking)")
        except Exception as exc:
            raise AssertionError(f"Strategy engine crashed due to diagnostics error: {exc}")


def test_diagnostics_with_regime_and_risk():
    """
    Test that diagnostics capture regime and risk block information.
    """
    from core.strategy_engine_v2 import StrategyEngineV2, BaseStrategy, StrategyState
    from strategies.base import Decision
    
    class RiskAwareStrategy(BaseStrategy):
        def generate_signal(self, candle, series, indicators, context=None):
            # Simulate a risk-blocked HOLD
            return Decision(action="HOLD", reason="max_loss_reached", confidence=0.0)
    
    config = {"primary_strategy_id": "risk_aware"}
    engine = StrategyEngineV2(config=config)
    
    state = StrategyState()
    strategy = RiskAwareStrategy(config={"strategy_id": "risk_aware"}, strategy_state=state)
    engine.register_strategy("risk_aware", strategy)
    
    candle = {"close": 100.0}
    indicators = {"ema20": 99.0, "ema50": 98.0}
    context = {"regime": "low_vol"}
    
    with tempfile.TemporaryDirectory() as tmpdir:
        test_diag_dir = Path(tmpdir) / "diagnostics"
        
        with patch('analytics.diagnostics.DIAGNOSTICS_DIR', test_diag_dir):
            intent, debug = engine.evaluate(
                logical="TEST",
                symbol="TEST",
                timeframe="5m",
                candle=candle,
                indicators=indicators,
                mode="paper",
                profile="intraday",
                context=context,
            )
            
            diagnostics = load_diagnostics("TEST", "risk_aware", limit=1)
            
            assert len(diagnostics) > 0
            record = diagnostics[0]
            
            # Check for regime
            assert record.get("regime") == "low_vol"
            
            # Check for risk block detection
            assert record.get("risk_block") in ["max_loss", "none"]
            
            print("✓ Diagnostics captured regime and risk information")


if __name__ == "__main__":
    print("Running SRDE integration tests...\n")
    
    try:
        test_strategy_engine_v2_diagnostics_emission()
        test_diagnostics_non_blocking()
        test_diagnostics_with_regime_and_risk()
        
        print("\n✓ All SRDE integration tests passed!")
    except Exception as exc:
        print(f"\n✗ Test failed: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
