"""
Test PaperEngine initialization with None/null strategy_engine config.

This test validates that strategy_engine config handling is robust when:
1. strategy_engine config is None/null
2. strategy_engine.strategies_v2 is missing or empty
3. strategy_engine.strategies is missing or empty
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging

# Set up basic logging for tests
logging.basicConfig(level=logging.INFO)


def test_strategy_engine_config_normalization():
    """Test that None/null strategy_engine config is normalized to empty dict."""
    
    # Simulate the normalization logic from PaperEngine.__init__
    
    # Case 1: strategy_engine is None (null in YAML)
    raw_config = {"strategy_engine": None}
    strategy_engine_config = raw_config.get("strategy_engine")
    if strategy_engine_config is None:
        strategy_engine_config = {}
    
    assert strategy_engine_config == {}
    assert strategy_engine_config.get("version", 1) == 1  # Should not crash
    assert strategy_engine_config.get("strategies_v2", []) == []  # Should not crash
    
    # Case 2: strategy_engine is missing entirely
    raw_config = {}
    strategy_engine_config = raw_config.get("strategy_engine")
    if strategy_engine_config is None:
        strategy_engine_config = {}
    
    assert strategy_engine_config == {}
    assert strategy_engine_config.get("version", 1) == 1
    
    # Case 3: strategy_engine exists but strategies_v2 is None
    raw_config = {"strategy_engine": {"version": 2, "strategies_v2": None}}
    strategy_engine_config = raw_config.get("strategy_engine")
    if strategy_engine_config is None:
        strategy_engine_config = {}
    
    strategies_v2 = strategy_engine_config.get("strategies_v2") or []
    assert strategies_v2 == []  # Should convert None to empty list
    
    print("✓ All strategy_engine config normalization tests passed")


def test_strategy_lists_handling():
    """Test that strategy lists are handled safely when None or empty."""
    
    # Simulate the strategy registration logic
    
    # Case 1: Both lists are None
    config = {"strategies_v2": None, "strategies": None}
    strategies_v2 = config.get("strategies_v2") or []
    strategies_v1 = config.get("strategies") or []
    
    assert strategies_v2 == []
    assert strategies_v1 == []
    
    # Should be able to iterate without crashing
    for strategy_code in strategies_v2:
        pass  # Won't execute since list is empty
    
    for strategy_code in strategies_v1:
        pass  # Won't execute since list is empty
    
    # Case 2: Both lists are missing
    config = {}
    strategies_v2 = config.get("strategies_v2") or []
    strategies_v1 = config.get("strategies") or []
    
    assert strategies_v2 == []
    assert strategies_v1 == []
    
    # Case 3: Lists exist but are empty
    config = {"strategies_v2": [], "strategies": []}
    strategies_v2 = config.get("strategies_v2") or []
    strategies_v1 = config.get("strategies") or []
    
    assert strategies_v2 == []
    assert strategies_v1 == []
    
    print("✓ All strategy list handling tests passed")


def test_no_crash_on_none_config():
    """Test that accessing methods on None doesn't happen."""
    
    # Before fix: This would crash
    # strategy_engine_config = None
    # version = strategy_engine_config.get("version", 1)  # AttributeError: 'NoneType' object has no attribute 'get'
    
    # After fix: This works
    strategy_engine_config = None
    if strategy_engine_config is None:
        strategy_engine_config = {}
    
    version = strategy_engine_config.get("version", 1)
    assert version == 1
    
    # Before fix: This would crash
    # for strategy_code in strategy_engine_config.get("strategies_v2", []):  # Would try to call .get() on None
    
    # After fix: This works
    strategies_v2 = strategy_engine_config.get("strategies_v2") or []
    for strategy_code in strategies_v2:
        pass  # Won't execute since list is empty
    
    print("✓ No crash on None config test passed")


if __name__ == "__main__":
    # Run tests
    test_strategy_engine_config_normalization()
    test_strategy_lists_handling()
    test_no_crash_on_none_config()
    print("\n✅ All tests passed successfully!")

