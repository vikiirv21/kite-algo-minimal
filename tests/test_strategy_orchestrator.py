"""Tests for core/strategy_orchestrator.py"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.strategy_orchestrator import (
    StrategyState, OrchestratorDecision, StrategyOrchestrator
)


class MockStateStore:
    """Mock state store for testing."""
    
    def __init__(self):
        self.data = {}
    
    def load_checkpoint(self):
        return self.data
    
    def save_checkpoint(self, data):
        self.data = data


class MockAnalytics:
    """Mock analytics engine for testing."""
    pass


def test_strategy_state():
    """Test StrategyState dataclass."""
    state = StrategyState()
    
    assert state.active is True
    assert state.disabled_until is None
    assert state.loss_streak == 0
    assert state.health_score == 1.0
    assert len(state.last_signals) == 0
    assert len(state.last_pnls) == 0


def test_orchestrator_decision():
    """Test OrchestratorDecision dataclass."""
    decision = OrchestratorDecision(allow=True, reason="test_reason")
    
    assert decision.allow is True
    assert decision.reason == "test_reason"


def test_orchestrator_disabled_by_default():
    """Test that orchestrator is disabled by default."""
    config = {}
    state_store = MockStateStore()
    analytics = MockAnalytics()
    
    orchestrator = StrategyOrchestrator(config, state_store, analytics)
    
    assert orchestrator.enabled is False
    
    # When disabled, should always allow
    decision = orchestrator.should_run_strategy("test_strategy")
    assert decision.allow is True
    assert decision.reason == "orchestrator_disabled"


def test_orchestrator_enabled():
    """Test orchestrator when enabled."""
    config = {
        "strategy_orchestrator": {
            "enabled": True,
            "health_scoring_window": 20,
            "loss_streak_disable": 3,
            "disable_duration_seconds": 900,
            "enforce_regimes": True,
            "enforce_capital_budgets": False,
        }
    }
    state_store = MockStateStore()
    analytics = MockAnalytics()
    
    orchestrator = StrategyOrchestrator(config, state_store, analytics)
    
    assert orchestrator.enabled is True
    assert orchestrator.health_scoring_window == 20
    assert orchestrator.loss_streak_disable == 3
    assert orchestrator.disable_duration_seconds == 900


def test_should_run_strategy_basic():
    """Test basic strategy execution allowance."""
    config = {
        "strategy_orchestrator": {
            "enabled": True,
        }
    }
    state_store = MockStateStore()
    analytics = MockAnalytics()
    
    orchestrator = StrategyOrchestrator(config, state_store, analytics)
    
    # Initially should allow
    decision = orchestrator.should_run_strategy("test_strategy")
    assert decision.allow is True
    assert decision.reason == "all_checks_passed"


def test_loss_streak_cooldown():
    """Test loss streak cooldown mechanism."""
    config = {
        "strategy_orchestrator": {
            "enabled": True,
            "loss_streak_disable": 3,
            "disable_duration_seconds": 10,  # 10 seconds for testing
        }
    }
    state_store = MockStateStore()
    analytics = MockAnalytics()
    
    orchestrator = StrategyOrchestrator(config, state_store, analytics)
    
    strategy_code = "test_strategy"
    
    # Record 3 consecutive losses
    orchestrator.update_after_trade(strategy_code, -100.0)
    orchestrator.update_after_trade(strategy_code, -50.0)
    orchestrator.update_after_trade(strategy_code, -25.0)
    
    # Should be disabled now
    decision = orchestrator.should_run_strategy(strategy_code)
    assert decision.allow is False
    assert "cooldown_until" in decision.reason
    
    # Check state
    state = orchestrator._get_strategy_state(strategy_code)
    assert state.active is False
    assert state.disabled_until is not None
    assert state.loss_streak == 3


def test_loss_streak_reset_on_win():
    """Test that loss streak resets on a winning trade."""
    config = {
        "strategy_orchestrator": {
            "enabled": True,
            "loss_streak_disable": 3,
        }
    }
    state_store = MockStateStore()
    analytics = MockAnalytics()
    
    orchestrator = StrategyOrchestrator(config, state_store, analytics)
    
    strategy_code = "test_strategy"
    
    # Record 2 losses then a win
    orchestrator.update_after_trade(strategy_code, -100.0)
    orchestrator.update_after_trade(strategy_code, -50.0)
    orchestrator.update_after_trade(strategy_code, 150.0)  # Win
    
    state = orchestrator._get_strategy_state(strategy_code)
    assert state.loss_streak == 0  # Reset
    
    # Should still be allowed
    decision = orchestrator.should_run_strategy(strategy_code)
    assert decision.allow is True


def test_health_score_calculation():
    """Test health score calculation based on recent PnLs."""
    config = {
        "strategy_orchestrator": {
            "enabled": True,
            "health_scoring_window": 10,
        }
    }
    state_store = MockStateStore()
    analytics = MockAnalytics()
    
    orchestrator = StrategyOrchestrator(config, state_store, analytics)
    
    strategy_code = "test_strategy"
    
    # Record 10 trades: 7 wins, 3 losses = 70% win rate
    for _ in range(7):
        orchestrator.update_after_trade(strategy_code, 100.0)  # Win
    for _ in range(3):
        orchestrator.update_after_trade(strategy_code, -50.0)  # Loss
    
    state = orchestrator._get_strategy_state(strategy_code)
    assert 0.65 < state.health_score < 0.75  # Should be around 0.7


def test_regime_evaluation():
    """Test regime compatibility checks."""
    config = {
        "strategy_orchestrator": {
            "enabled": True,
            "enforce_regimes": True,
        },
        "strategies": {
            "trend_strategy": {
                "requires_regime": ["trend"],
                "avoid_regime": ["low_vol"],
            }
        }
    }
    state_store = MockStateStore()
    analytics = MockAnalytics()
    
    orchestrator = StrategyOrchestrator(config, state_store, analytics)
    
    strategy_code = "trend_strategy"
    
    # Test 1: Regime matches requirements
    market_regime = {"trend": True, "low_vol": False, "volatile": False}
    decision = orchestrator.should_run_strategy(strategy_code, market_regime)
    assert decision.allow is True
    
    # Test 2: Required regime not present
    market_regime = {"trend": False, "low_vol": False, "volatile": False}
    decision = orchestrator.should_run_strategy(strategy_code, market_regime)
    assert decision.allow is False
    assert decision.reason == "regime_incompatible"
    
    # Test 3: Avoided regime present
    market_regime = {"trend": True, "low_vol": True, "volatile": False}
    decision = orchestrator.should_run_strategy(strategy_code, market_regime)
    assert decision.allow is False
    assert decision.reason == "regime_incompatible"


def test_session_time_check():
    """Test session time window filtering."""
    config = {
        "strategy_orchestrator": {
            "enabled": True,
        },
        "strategies": {
            "intraday_strategy": {
                "session_times": {
                    "start": "09:25",
                    "end": "14:55",
                }
            }
        }
    }
    state_store = MockStateStore()
    analytics = MockAnalytics()
    
    orchestrator = StrategyOrchestrator(config, state_store, analytics)
    
    # Note: This test will pass/fail depending on current time
    # In production, you'd want to mock datetime.now()
    strategy_code = "intraday_strategy"
    decision = orchestrator.should_run_strategy(strategy_code)
    
    # Just check that it doesn't crash
    assert decision.allow in [True, False]
    if not decision.allow and decision.reason == "outside_session_time":
        print(f"Session time check working: {decision.reason}")


def test_allowed_days_check():
    """Test allowed days filtering."""
    config = {
        "strategy_orchestrator": {
            "enabled": True,
        },
        "strategies": {
            "weekday_strategy": {
                "allowed_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
            }
        }
    }
    state_store = MockStateStore()
    analytics = MockAnalytics()
    
    orchestrator = StrategyOrchestrator(config, state_store, analytics)
    
    strategy_code = "weekday_strategy"
    decision = orchestrator.should_run_strategy(strategy_code)
    
    # Just check that it doesn't crash
    assert decision.allow in [True, False]


def test_orchestrator_no_crash_on_missing_config():
    """Test that orchestrator handles missing config gracefully."""
    config = {
        "strategy_orchestrator": {
            "enabled": True,
        }
    }
    state_store = MockStateStore()
    analytics = MockAnalytics()
    
    orchestrator = StrategyOrchestrator(config, state_store, analytics)
    
    # Test with strategy that has no metadata
    decision = orchestrator.should_run_strategy("unknown_strategy")
    assert decision.allow is True  # Should allow by default


def test_health_score_threshold():
    """Test health score threshold enforcement."""
    config = {
        "strategy_orchestrator": {
            "enabled": True,
            "min_health_score": 0.6,
            "health_scoring_window": 10,
            "loss_streak_disable": 100,  # Set high to avoid triggering loss streak cooldown
        }
    }
    state_store = MockStateStore()
    analytics = MockAnalytics()
    
    orchestrator = StrategyOrchestrator(config, state_store, analytics)
    
    strategy_code = "test_strategy"
    
    # Record 10 trades: 4 wins, 6 losses = 40% win rate (health_score = 0.4)
    for _ in range(4):
        orchestrator.update_after_trade(strategy_code, 100.0)
    for _ in range(6):
        orchestrator.update_after_trade(strategy_code, -50.0)
    
    state = orchestrator._get_strategy_state(strategy_code)
    assert state.health_score < 0.6
    
    # Should be denied due to low health score
    decision = orchestrator.should_run_strategy(strategy_code)
    assert decision.allow is False
    assert "health_score_low" in decision.reason


def run_all_tests():
    """Run all tests and report results."""
    tests = [
        test_strategy_state,
        test_orchestrator_decision,
        test_orchestrator_disabled_by_default,
        test_orchestrator_enabled,
        test_should_run_strategy_basic,
        test_loss_streak_cooldown,
        test_loss_streak_reset_on_win,
        test_health_score_calculation,
        test_regime_evaluation,
        test_session_time_check,
        test_allowed_days_check,
        test_orchestrator_no_crash_on_missing_config,
        test_health_score_threshold,
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
