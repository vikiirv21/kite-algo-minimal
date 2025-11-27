"""Tests for options ATM resolution robustness against None spot prices."""

import sys
from pathlib import Path
from unittest.mock import Mock, patch
from datetime import date

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from data.options_instruments import OptionUniverse


def create_test_universe(by_name_data):
    """Helper to create an OptionUniverse instance with test data without Kite API calls."""
    with patch.object(OptionUniverse, '__init__', lambda x, y=None: None):
        universe = OptionUniverse.__new__(OptionUniverse)
        universe._by_name = by_name_data
        return universe


def test_resolve_atm_for_underlying_handles_none_spot():
    """Test that resolve_atm_for_underlying returns None when spot is None."""
    universe = create_test_universe({
        "NIFTY": [
            {"tradingsymbol": "NIFTY25NOV25000CE", "strike": 25000, "instrument_type": "CE", "expiry": None},
            {"tradingsymbol": "NIFTY25NOV25000PE", "strike": 25000, "instrument_type": "PE", "expiry": None},
        ]
    })
    
    result = universe.resolve_atm_for_underlying("NIFTY", None)
    
    assert result is None, "Should return None when spot is None"
    print("✓ test_resolve_atm_for_underlying_handles_none_spot")


def test_resolve_atm_for_underlying_works_with_valid_spot():
    """Test that resolve_atm_for_underlying works normally when spot is valid."""
    today = date.today()
    
    universe = create_test_universe({
        "NIFTY": [
            {"tradingsymbol": "NIFTY25NOV25000CE", "strike": 25000, "instrument_type": "CE", "expiry": today},
            {"tradingsymbol": "NIFTY25NOV25000PE", "strike": 25000, "instrument_type": "PE", "expiry": today},
        ]
    })
    
    result = universe.resolve_atm_for_underlying("NIFTY", 25050.0)
    
    assert result is not None
    assert result.get("CE") == "NIFTY25NOV25000CE"
    assert result.get("PE") == "NIFTY25NOV25000PE"
    print("✓ test_resolve_atm_for_underlying_works_with_valid_spot")


def test_resolve_atm_for_many_skips_none_spots():
    """Test that resolve_atm_for_many skips underlyings with None spot prices."""
    today = date.today()
    
    universe = create_test_universe({
        "NIFTY": [
            {"tradingsymbol": "NIFTY25NOV25000CE", "strike": 25000, "instrument_type": "CE", "expiry": today},
            {"tradingsymbol": "NIFTY25NOV25000PE", "strike": 25000, "instrument_type": "PE", "expiry": today},
        ],
        "BANKNIFTY": [
            {"tradingsymbol": "BANKNIFTY25NOV55000CE", "strike": 55000, "instrument_type": "CE", "expiry": today},
            {"tradingsymbol": "BANKNIFTY25NOV55000PE", "strike": 55000, "instrument_type": "PE", "expiry": today},
        ],
    })
    
    # NIFTY has valid spot, BANKNIFTY has None spot
    spots = {"NIFTY": 25050.0, "BANKNIFTY": None}
    
    result = universe.resolve_atm_for_many(spots)
    
    # Should include NIFTY but not BANKNIFTY
    assert "NIFTY" in result
    assert "BANKNIFTY" not in result
    assert result["NIFTY"]["CE"] == "NIFTY25NOV25000CE"
    print("✓ test_resolve_atm_for_many_skips_none_spots")


def test_resolve_atm_for_many_returns_empty_when_all_none():
    """Test that resolve_atm_for_many returns empty dict when all spots are None."""
    today = date.today()
    
    universe = create_test_universe({
        "NIFTY": [
            {"tradingsymbol": "NIFTY25NOV25000CE", "strike": 25000, "instrument_type": "CE", "expiry": today},
        ],
        "BANKNIFTY": [
            {"tradingsymbol": "BANKNIFTY25NOV55000CE", "strike": 55000, "instrument_type": "CE", "expiry": today},
        ],
    })
    
    # All spots are None
    spots = {"NIFTY": None, "BANKNIFTY": None}
    
    result = universe.resolve_atm_for_many(spots)
    
    # Should be empty
    assert result == {}
    print("✓ test_resolve_atm_for_many_returns_empty_when_all_none")


def run_all_tests():
    """Run all tests and report results."""
    tests = [
        test_resolve_atm_for_underlying_handles_none_spot,
        test_resolve_atm_for_underlying_works_with_valid_spot,
        test_resolve_atm_for_many_skips_none_spots,
        test_resolve_atm_for_many_returns_empty_when_all_none,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
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
