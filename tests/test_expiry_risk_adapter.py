"""
Unit tests for core/expiry_risk_adapter.py

Tests risk scaling and blocking logic for expiry-aware trading.
"""

import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.expiry_risk_adapter import (
    ExpiryRiskConfig,
    ExpiryRiskAdapter,
    ExpiryRiskDecision,
)
import pytz

IST = pytz.timezone("Asia/Kolkata")


def test_risk_config_from_dict():
    """Test loading ExpiryRiskConfig from configuration dict."""
    print("Testing ExpiryRiskConfig.from_config...")
    
    config = {
        "expiry_risk": {
            "enabled": True,
            "expiry_day_risk_scale": 0.8,
            "expiry_last_hour_risk_scale": 0.6,
            "expiry_week_risk_scale": 0.9,
            "block_new_option_entries_after_ist": "15:00",
        }
    }
    
    risk_config = ExpiryRiskConfig.from_config(config)
    
    assert risk_config.enabled is True
    assert risk_config.expiry_day_risk_scale == 0.8
    assert risk_config.expiry_last_hour_risk_scale == 0.6
    assert risk_config.expiry_week_risk_scale == 0.9
    assert risk_config.block_new_option_entries_after_ist == "15:00"
    
    print("✓ ExpiryRiskConfig loading works correctly")


def test_risk_adapter_disabled():
    """Test that adapter returns no adjustment when disabled."""
    print("Testing disabled risk adapter...")
    
    config = ExpiryRiskConfig(enabled=False)
    adapter = ExpiryRiskAdapter(config)
    
    # On expiry day (should still return 1.0 when disabled)
    thursday = datetime(2025, 11, 20, 14, 0, 0, tzinfo=IST)
    decision = adapter.evaluate(
        symbol="NIFTY",
        dt=thursday,
        is_option=True,
        is_new_entry=True,
    )
    
    assert decision.risk_scale == 1.0
    assert decision.allow_new_entry is True
    assert decision.reason == "expiry_risk_disabled"
    
    print("✓ Disabled adapter returns default values")


def test_risk_adapter_non_expiry_day():
    """Test adapter returns no adjustment on non-expiry day."""
    print("Testing non-expiry day...")
    
    config = ExpiryRiskConfig(enabled=True)
    adapter = ExpiryRiskAdapter(config)
    
    # Monday (not expiry day)
    monday = datetime(2025, 11, 17, 10, 0, 0, tzinfo=IST)
    decision = adapter.evaluate(
        symbol="NIFTY",
        dt=monday,
        is_option=True,
        is_new_entry=True,
    )
    
    # Should be expiry week, so risk_scale = 0.9
    assert decision.risk_scale == 0.9
    assert decision.allow_new_entry is True
    assert "expiry_week_risk_scale" in decision.reason
    
    print("✓ Non-expiry day (but expiry week) returns correct scale")


def test_risk_adapter_expiry_day_morning():
    """Test adapter on expiry day morning."""
    print("Testing expiry day morning...")
    
    config = ExpiryRiskConfig(enabled=True, expiry_day_risk_scale=0.8)
    adapter = ExpiryRiskAdapter(config)
    
    # Thursday 10:00 AM (expiry day, not last hour)
    thursday_morning = datetime(2025, 11, 20, 10, 0, 0, tzinfo=IST)
    decision = adapter.evaluate(
        symbol="NIFTY",
        dt=thursday_morning,
        is_option=True,
        is_new_entry=True,
    )
    
    assert decision.risk_scale == 0.8
    assert decision.allow_new_entry is True
    assert "expiry_day_risk_scale" in decision.reason
    
    print("✓ Expiry day morning returns 0.8 scale")


def test_risk_adapter_expiry_day_last_hour():
    """Test adapter in last hour of expiry day."""
    print("Testing expiry day last hour...")
    
    config = ExpiryRiskConfig(enabled=True, expiry_last_hour_risk_scale=0.6)
    adapter = ExpiryRiskAdapter(config)
    
    # Thursday 2:45 PM (expiry day, last 45 minutes, before 3:00 PM cutoff)
    thursday_afternoon = datetime(2025, 11, 20, 14, 45, 0, tzinfo=IST)
    decision = adapter.evaluate(
        symbol="NIFTY",
        dt=thursday_afternoon,
        is_option=True,
        is_new_entry=True,
    )
    
    assert decision.risk_scale == 0.6
    assert decision.allow_new_entry is True
    assert "last_hour_risk_scale" in decision.reason
    
    print("✓ Expiry day last hour returns 0.6 scale")


def test_risk_adapter_block_after_3pm():
    """Test blocking new option entries after 3:00 PM on expiry day."""
    print("Testing block after 3:00 PM...")
    
    config = ExpiryRiskConfig(
        enabled=True,
        block_new_option_entries_after_ist="15:00"
    )
    adapter = ExpiryRiskAdapter(config)
    
    # Thursday 3:05 PM (after 3:00 PM cutoff)
    thursday_late = datetime(2025, 11, 20, 15, 5, 0, tzinfo=IST)
    decision = adapter.evaluate(
        symbol="NIFTY",
        dt=thursday_late,
        is_option=True,
        is_new_entry=True,
    )
    
    assert decision.risk_scale == 0.0
    assert decision.allow_new_entry is False
    assert "block_new_option_entries" in decision.reason
    
    print("✓ Blocks new option entries after 3:00 PM")


def test_risk_adapter_exit_always_allowed():
    """Test that exits are always allowed regardless of expiry timing."""
    print("Testing exits always allowed...")
    
    config = ExpiryRiskConfig(enabled=True)
    adapter = ExpiryRiskAdapter(config)
    
    # Thursday 3:10 PM (after cutoff, but this is an exit)
    thursday_late = datetime(2025, 11, 20, 15, 10, 0, tzinfo=IST)
    decision = adapter.evaluate(
        symbol="NIFTY",
        dt=thursday_late,
        is_option=True,
        is_new_entry=False,  # This is an exit
    )
    
    assert decision.risk_scale == 1.0
    assert decision.allow_new_entry is True
    assert decision.reason == "exit_always_allowed"
    
    print("✓ Exits are always allowed")


def test_risk_adapter_futures_not_blocked():
    """Test that futures are not blocked after 3:00 PM (only options)."""
    print("Testing futures not blocked...")
    
    config = ExpiryRiskConfig(
        enabled=True,
        block_new_option_entries_after_ist="15:00"
    )
    adapter = ExpiryRiskAdapter(config)
    
    # Thursday 3:05 PM but not an option
    thursday_late = datetime(2025, 11, 20, 15, 5, 0, tzinfo=IST)
    decision = adapter.evaluate(
        symbol="NIFTY",
        dt=thursday_late,
        is_option=False,  # Futures, not options
        is_new_entry=True,
    )
    
    # Should apply last hour risk scale but not block
    assert decision.allow_new_entry is True
    assert decision.risk_scale == config.expiry_last_hour_risk_scale
    
    print("✓ Futures are not blocked after 3:00 PM")


def test_risk_adapter_expiry_week_not_day():
    """Test scaling during expiry week but not on expiry day."""
    print("Testing expiry week (not day)...")
    
    config = ExpiryRiskConfig(enabled=True, expiry_week_risk_scale=0.9)
    adapter = ExpiryRiskAdapter(config)
    
    # Monday in expiry week (not expiry day)
    monday = datetime(2025, 11, 17, 10, 0, 0, tzinfo=IST)
    decision = adapter.evaluate(
        symbol="NIFTY",
        dt=monday,
        is_option=True,
        is_new_entry=True,
    )
    
    assert decision.risk_scale == 0.9
    assert decision.allow_new_entry is True
    assert "expiry_week_risk_scale" in decision.reason
    
    print("✓ Expiry week scaling works correctly")


def run_all_tests():
    """Run all tests."""
    print("\n" + "="*60)
    print("Running Expiry Risk Adapter Tests")
    print("="*60 + "\n")
    
    try:
        test_risk_config_from_dict()
        test_risk_adapter_disabled()
        test_risk_adapter_non_expiry_day()
        test_risk_adapter_expiry_day_morning()
        test_risk_adapter_expiry_day_last_hour()
        test_risk_adapter_block_after_3pm()
        test_risk_adapter_exit_always_allowed()
        test_risk_adapter_futures_not_blocked()
        test_risk_adapter_expiry_week_not_day()
        
        print("\n" + "="*60)
        print("✅ All tests passed!")
        print("="*60)
        return True
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
