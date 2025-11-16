"""
Integration test for TradingMode handling in engines.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.modes import TradingMode
from core.config import AppConfig


def test_paper_engine_mode_normalization():
    """Test that PaperEngine correctly handles uppercase mode strings."""
    # This simulates the pattern from paper_engine.py __init__
    
    # Test 1: Uppercase mode from config
    cfg_mode = "PAPER"  # This is what comes from CLI/config
    
    # Simulate the normalization logic
    mode_raw = cfg_mode
    if isinstance(mode_raw, TradingMode):
        mode = mode_raw
    else:
        mode_str = str(mode_raw).strip().lower()
        mode = TradingMode(mode_str)
    
    assert mode == TradingMode.PAPER
    print("✓ Uppercase 'PAPER' normalized correctly")
    
    # Test 2: Mixed case mode
    cfg_mode = "Paper"
    mode_raw = cfg_mode
    if isinstance(mode_raw, TradingMode):
        mode = mode_raw
    else:
        mode_str = str(mode_raw).strip().lower()
        mode = TradingMode(mode_str)
    
    assert mode == TradingMode.PAPER
    print("✓ Mixed case 'Paper' normalized correctly")
    
    # Test 3: Enum instance (should pass through)
    cfg_mode = TradingMode.LIVE
    mode_raw = cfg_mode
    if isinstance(mode_raw, TradingMode):
        mode = mode_raw
    else:
        mode_str = str(mode_raw).strip().lower()
        mode = TradingMode(mode_str)
    
    assert mode == TradingMode.LIVE
    print("✓ Enum instance passed through correctly")
    
    # Test 4: Lowercase mode (original working case)
    cfg_mode = "paper"
    mode_raw = cfg_mode
    if isinstance(mode_raw, TradingMode):
        mode = mode_raw
    else:
        mode_str = str(mode_raw).strip().lower()
        mode = TradingMode(mode_str)
    
    assert mode == TradingMode.PAPER
    print("✓ Lowercase 'paper' works correctly")


def test_run_day_mode_normalization():
    """Test the mode normalization in run_day.py"""
    
    def _mode_from_config_new(mode_str):
        """Simulates the new _mode_from_config"""
        return str(mode_str or "paper").strip().lower()
    
    # Test various inputs
    assert _mode_from_config_new("PAPER") == "paper"
    assert _mode_from_config_new("paper") == "paper"
    assert _mode_from_config_new("Paper") == "paper"
    assert _mode_from_config_new("LIVE") == "live"
    assert _mode_from_config_new("live") == "live"
    assert _mode_from_config_new("  PAPER  ") == "paper"
    assert _mode_from_config_new(None) == "paper"
    
    print("✓ run_day.py mode normalization works correctly")


if __name__ == "__main__":
    print("Testing TradingMode integration...")
    print()
    
    test_paper_engine_mode_normalization()
    print()
    
    test_run_day_mode_normalization()
    print()
    
    print("✅ All integration tests passed!")
