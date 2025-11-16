"""
Test TradingMode enum handling with case-insensitive string inputs.
"""

import pytest
from core.modes import TradingMode


def test_trading_mode_enum_values():
    """Test that TradingMode enum has lowercase values."""
    assert TradingMode.PAPER.value == "paper"
    assert TradingMode.LIVE.value == "live"
    assert TradingMode.REPLAY.value == "replay"


def test_trading_mode_from_lowercase_string():
    """Test creating TradingMode from lowercase string."""
    assert TradingMode("paper") == TradingMode.PAPER
    assert TradingMode("live") == TradingMode.LIVE
    assert TradingMode("replay") == TradingMode.REPLAY


def test_trading_mode_from_uppercase_string_fails():
    """Test that uppercase strings fail without normalization."""
    with pytest.raises(ValueError, match="is not a valid TradingMode"):
        TradingMode("PAPER")
    with pytest.raises(ValueError, match="is not a valid TradingMode"):
        TradingMode("LIVE")
    with pytest.raises(ValueError, match="is not a valid TradingMode"):
        TradingMode("REPLAY")


def test_trading_mode_normalization():
    """Test the normalization pattern used in engines."""
    # This pattern is used in paper_engine.py, options_paper_engine.py, equity_paper_engine.py
    test_cases = [
        ("paper", TradingMode.PAPER),
        ("PAPER", TradingMode.PAPER),
        ("Paper", TradingMode.PAPER),
        ("live", TradingMode.LIVE),
        ("LIVE", TradingMode.LIVE),
        ("Live", TradingMode.LIVE),
        ("replay", TradingMode.REPLAY),
        ("REPLAY", TradingMode.REPLAY),
        ("Replay", TradingMode.REPLAY),
        ("  paper  ", TradingMode.PAPER),  # with whitespace
        ("  LIVE  ", TradingMode.LIVE),
    ]
    
    for input_str, expected_enum in test_cases:
        # Simulate the normalization pattern from engines
        mode_str = str(input_str).strip().lower()
        result = TradingMode(mode_str)
        assert result == expected_enum, f"Failed for input '{input_str}'"


def test_trading_mode_from_enum_instance():
    """Test that passing an enum instance works."""
    # This pattern is also used in engines
    mode_raw = TradingMode.PAPER
    
    if isinstance(mode_raw, TradingMode):
        result = mode_raw
    else:
        mode_str = str(mode_raw).strip().lower()
        result = TradingMode(mode_str)
    
    assert result == TradingMode.PAPER


def test_mixed_mode_inputs():
    """Test the full normalization logic used in engines."""
    def normalize_mode(mode_raw):
        """Simulate the pattern from paper_engine.py"""
        if isinstance(mode_raw, TradingMode):
            return mode_raw
        else:
            mode_str = str(mode_raw).strip().lower()
            return TradingMode(mode_str)
    
    # Test with enum instances
    assert normalize_mode(TradingMode.PAPER) == TradingMode.PAPER
    assert normalize_mode(TradingMode.LIVE) == TradingMode.LIVE
    
    # Test with strings
    assert normalize_mode("paper") == TradingMode.PAPER
    assert normalize_mode("PAPER") == TradingMode.PAPER
    assert normalize_mode("live") == TradingMode.LIVE
    assert normalize_mode("LIVE") == TradingMode.LIVE
    assert normalize_mode("replay") == TradingMode.REPLAY
    assert normalize_mode("REPLAY") == TradingMode.REPLAY
    
    # Test with whitespace
    assert normalize_mode("  paper  ") == TradingMode.PAPER
    assert normalize_mode("  LIVE  ") == TradingMode.LIVE


def test_invalid_mode_string():
    """Test that invalid mode strings still raise ValueError."""
    def normalize_mode(mode_raw):
        if isinstance(mode_raw, TradingMode):
            return mode_raw
        else:
            mode_str = str(mode_raw).strip().lower()
            return TradingMode(mode_str)
    
    with pytest.raises(ValueError):
        normalize_mode("invalid")
    
    with pytest.raises(ValueError):
        normalize_mode("INVALID")
    
    with pytest.raises(ValueError):
        normalize_mode("")
