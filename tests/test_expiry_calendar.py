"""
Unit tests for core/expiry_calendar.py

Tests expiry date calculations for NIFTY, BANKNIFTY, and FINNIFTY.
"""

import sys
from pathlib import Path
from datetime import datetime, date, timedelta

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.expiry_calendar import (
    get_next_expiry,
    is_expiry_day,
    is_expiry_week,
    get_time_to_expiry_minutes,
    get_session_time_ist,
    build_expiry_context,
    _get_last_thursday_of_month,
    IST,
)


def test_get_last_thursday_of_month():
    """Test monthly expiry calculation (last Thursday)."""
    print("Testing _get_last_thursday_of_month...")
    
    # November 2025: Last Thursday should be 27th
    result = _get_last_thursday_of_month(2025, 11)
    assert result == date(2025, 11, 27), f"Expected 2025-11-27, got {result}"
    assert result.weekday() == 3, "Last Thursday should have weekday 3"
    
    # December 2025: Last Thursday should be 25th
    result = _get_last_thursday_of_month(2025, 12)
    assert result == date(2025, 12, 25), f"Expected 2025-12-25, got {result}"
    assert result.weekday() == 3, "Last Thursday should have weekday 3"
    
    print("✓ Monthly expiry calculation works correctly")


def test_get_next_expiry_nifty():
    """Test next expiry for NIFTY (weekly on Thursday)."""
    print("Testing get_next_expiry for NIFTY...")
    
    # Test on a Monday - should get next Thursday
    monday = datetime(2025, 11, 17, 10, 0, 0, tzinfo=IST)  # Monday morning
    result = get_next_expiry("NIFTY", monday)
    assert result == date(2025, 11, 20), f"Expected 2025-11-20 (Thu), got {result}"
    assert result.weekday() == 3, "NIFTY expiry should be Thursday"
    
    # Test on expiry day Thursday morning - should return same day
    thursday_morning = datetime(2025, 11, 20, 10, 0, 0, tzinfo=IST)
    result = get_next_expiry("NIFTY", thursday_morning)
    assert result == date(2025, 11, 20), f"Expected same day 2025-11-20, got {result}"
    
    # Test on expiry day Thursday evening after market close - should return next week
    thursday_evening = datetime(2025, 11, 20, 16, 0, 0, tzinfo=IST)
    result = get_next_expiry("NIFTY", thursday_evening)
    assert result == date(2025, 11, 27), f"Expected next week 2025-11-27, got {result}"
    
    print("✓ NIFTY next expiry calculation works correctly")


def test_get_next_expiry_banknifty():
    """Test next expiry for BANKNIFTY (weekly on Wednesday)."""
    print("Testing get_next_expiry for BANKNIFTY...")
    
    # Test on a Monday - should get next Wednesday
    monday = datetime(2025, 11, 17, 10, 0, 0, tzinfo=IST)
    result = get_next_expiry("BANKNIFTY", monday)
    assert result == date(2025, 11, 19), f"Expected 2025-11-19 (Wed), got {result}"
    assert result.weekday() == 2, "BANKNIFTY expiry should be Wednesday"
    
    # Test on Wednesday morning - should return same day
    wednesday_morning = datetime(2025, 11, 19, 10, 0, 0, tzinfo=IST)
    result = get_next_expiry("BANKNIFTY", wednesday_morning)
    assert result == date(2025, 11, 19), f"Expected same day 2025-11-19, got {result}"
    
    print("✓ BANKNIFTY next expiry calculation works correctly")


def test_get_next_expiry_finnifty():
    """Test next expiry for FINNIFTY (weekly on Tuesday)."""
    print("Testing get_next_expiry for FINNIFTY...")
    
    # Test on a Monday - should get next Tuesday
    monday = datetime(2025, 11, 17, 10, 0, 0, tzinfo=IST)
    result = get_next_expiry("FINNIFTY", monday)
    assert result == date(2025, 11, 18), f"Expected 2025-11-18 (Tue), got {result}"
    assert result.weekday() == 1, "FINNIFTY expiry should be Tuesday"
    
    print("✓ FINNIFTY next expiry calculation works correctly")


def test_is_expiry_day():
    """Test expiry day detection."""
    print("Testing is_expiry_day...")
    
    # NIFTY on Thursday morning (expiry day)
    thursday_morning = datetime(2025, 11, 20, 10, 0, 0, tzinfo=IST)
    assert is_expiry_day("NIFTY", thursday_morning) is True
    
    # NIFTY on Thursday after market close (not expiry day anymore)
    thursday_evening = datetime(2025, 11, 20, 16, 0, 0, tzinfo=IST)
    assert is_expiry_day("NIFTY", thursday_evening) is False
    
    # NIFTY on Monday (not expiry day)
    monday = datetime(2025, 11, 17, 10, 0, 0, tzinfo=IST)
    assert is_expiry_day("NIFTY", monday) is False
    
    # BANKNIFTY on Wednesday morning (expiry day)
    wednesday = datetime(2025, 11, 19, 10, 0, 0, tzinfo=IST)
    assert is_expiry_day("BANKNIFTY", wednesday) is True
    
    # FINNIFTY on Tuesday morning (expiry day)
    tuesday = datetime(2025, 11, 18, 10, 0, 0, tzinfo=IST)
    assert is_expiry_day("FINNIFTY", tuesday) is True
    
    print("✓ Expiry day detection works correctly")


def test_is_expiry_week():
    """Test expiry week detection."""
    print("Testing is_expiry_week...")
    
    # NIFTY: Week of Nov 20, 2025 (Thursday)
    # Should be expiry week from Nov 14-20
    
    # Monday Nov 17 - should be in expiry week
    monday = datetime(2025, 11, 17, 10, 0, 0, tzinfo=IST)
    assert is_expiry_week("NIFTY", monday) is True
    
    # Thursday Nov 20 (expiry day) - should be in expiry week
    thursday = datetime(2025, 11, 20, 10, 0, 0, tzinfo=IST)
    assert is_expiry_week("NIFTY", thursday) is True
    
    # Friday Nov 14 (7 days before) - should be in expiry week
    friday_before = datetime(2025, 11, 14, 10, 0, 0, tzinfo=IST)
    assert is_expiry_week("NIFTY", friday_before) is True
    
    # Previous Thursday Nov 13 (after market close) - should NOT be in current expiry week
    prev_thursday_evening = datetime(2025, 11, 13, 16, 0, 0, tzinfo=IST)
    assert is_expiry_week("NIFTY", prev_thursday_evening) is False
    
    # Way before - Nov 10 (Monday, well before expiry week) - should NOT be in expiry week
    way_before = datetime(2025, 11, 10, 10, 0, 0, tzinfo=IST)
    # Nov 10 would be in the week for Nov 13 expiry
    # But for testing purposes, we can check that a date far enough back is NOT in a future week
    # Let's instead check Nov 21 (Friday after expiry)
    after_expiry = datetime(2025, 11, 21, 10, 0, 0, tzinfo=IST)
    # Nov 21 would be in the next expiry week (for Nov 27)
    assert is_expiry_week("NIFTY", after_expiry) is True  # It's in the next expiry week
    
    print("✓ Expiry week detection works correctly")


def test_get_time_to_expiry_minutes():
    """Test time to expiry calculation."""
    print("Testing get_time_to_expiry_minutes...")
    
    # NIFTY on Thursday 10:00 AM (expiry day) - 5.5 hours to market close
    thursday_morning = datetime(2025, 11, 20, 10, 0, 0, tzinfo=IST)
    result = get_time_to_expiry_minutes("NIFTY", thursday_morning)
    assert result == 330, f"Expected 330 minutes (5.5 hours), got {result}"
    
    # NIFTY on Thursday 3:00 PM (expiry day) - 30 minutes to market close
    thursday_afternoon = datetime(2025, 11, 20, 15, 0, 0, tzinfo=IST)
    result = get_time_to_expiry_minutes("NIFTY", thursday_afternoon)
    assert result == 30, f"Expected 30 minutes, got {result}"
    
    # NIFTY on Monday (not expiry day) - should return None
    monday = datetime(2025, 11, 17, 10, 0, 0, tzinfo=IST)
    result = get_time_to_expiry_minutes("NIFTY", monday)
    assert result is None, f"Expected None for non-expiry day, got {result}"
    
    print("✓ Time to expiry calculation works correctly")


def test_get_session_time_ist():
    """Test IST session time formatting."""
    print("Testing get_session_time_ist...")
    
    dt = datetime(2025, 11, 20, 10, 30, 45, tzinfo=IST)
    result = get_session_time_ist(dt)
    assert result == "10:30", f"Expected '10:30', got '{result}'"
    
    dt = datetime(2025, 11, 20, 15, 5, 0, tzinfo=IST)
    result = get_session_time_ist(dt)
    assert result == "15:05", f"Expected '15:05', got '{result}'"
    
    print("✓ Session time formatting works correctly")


def test_build_expiry_context():
    """Test building complete expiry context."""
    print("Testing build_expiry_context...")
    
    # Test on expiry day
    thursday = datetime(2025, 11, 20, 14, 0, 0, tzinfo=IST)  # 2:00 PM on expiry day
    context = build_expiry_context("NIFTY", thursday)
    
    assert context["is_expiry_day"] is True
    assert context["is_expiry_week"] is True
    assert context["next_expiry_dt"] == "2025-11-20"
    assert context["time_to_expiry_minutes"] == 90  # 1.5 hours to close
    assert context["session_time_ist"] == "14:00"
    
    # Test on non-expiry day
    monday = datetime(2025, 11, 17, 10, 0, 0, tzinfo=IST)
    context = build_expiry_context("NIFTY", monday)
    
    assert context["is_expiry_day"] is False
    assert context["is_expiry_week"] is True  # Still in expiry week
    assert context["next_expiry_dt"] == "2025-11-20"
    assert context["time_to_expiry_minutes"] is None  # Not expiry day
    assert context["session_time_ist"] == "10:00"
    
    print("✓ Expiry context building works correctly")


def run_all_tests():
    """Run all tests."""
    print("\n" + "="*60)
    print("Running Expiry Calendar Tests")
    print("="*60 + "\n")
    
    try:
        test_get_last_thursday_of_month()
        test_get_next_expiry_nifty()
        test_get_next_expiry_banknifty()
        test_get_next_expiry_finnifty()
        test_is_expiry_day()
        test_is_expiry_week()
        test_get_time_to_expiry_minutes()
        test_get_session_time_ist()
        test_build_expiry_context()
        
        print("\n" + "="*60)
        print("✅ All tests passed!")
        print("="*60)
        return True
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
