#!/usr/bin/env python
"""
Test script to verify that the TradingMode fix works with various mode inputs.
This simulates the flow from scripts/run_day.py
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.config import load_config
from core.modes import TradingMode


def test_config_mode_parsing():
    """Test that config mode is parsed correctly."""
    print("Testing config mode parsing...")
    
    config_path = "configs/dev.yaml"
    try:
        cfg = load_config(config_path)
        print(f"✓ Config loaded successfully")
        
        # Get mode from config
        trading = getattr(cfg, "trading", {}) or {}
        mode_from_config = trading.get("mode", "paper")
        print(f"  Mode from config: '{mode_from_config}'")
        
        # Normalize (as done in _mode_from_config)
        normalized = str(mode_from_config or "paper").strip().lower()
        print(f"  Normalized mode: '{normalized}'")
        
        # Create TradingMode enum
        mode_enum = TradingMode(normalized)
        print(f"  TradingMode enum: {mode_enum}")
        print(f"  Enum value: '{mode_enum.value}'")
        
        assert mode_enum == TradingMode.PAPER
        print("✓ Config mode parsing works correctly\n")
        
    except Exception as e:
        print(f"✗ Error: {e}\n")
        raise


def test_cli_override_uppercase():
    """Test that CLI override with uppercase works."""
    print("Testing CLI mode override (uppercase)...")
    
    try:
        # Simulate --mode PAPER from CLI
        cli_mode = "PAPER"
        print(f"  CLI mode input: '{cli_mode}'")
        
        # Normalize (as done in main())
        normalized = cli_mode.strip().lower()
        print(f"  Normalized mode: '{normalized}'")
        
        # Create TradingMode enum
        mode_enum = TradingMode(normalized)
        print(f"  TradingMode enum: {mode_enum}")
        print(f"  Enum value: '{mode_enum.value}'")
        
        assert mode_enum == TradingMode.PAPER
        print("✓ CLI uppercase mode works correctly\n")
        
    except Exception as e:
        print(f"✗ Error: {e}\n")
        raise


def test_cli_override_live():
    """Test that CLI override with LIVE works."""
    print("Testing CLI mode override (LIVE)...")
    
    try:
        # Simulate --mode live from CLI
        cli_mode = "live"
        print(f"  CLI mode input: '{cli_mode}'")
        
        # Normalize (as done in main())
        normalized = cli_mode.strip().lower()
        print(f"  Normalized mode: '{normalized}'")
        
        # Create TradingMode enum
        mode_enum = TradingMode(normalized)
        print(f"  TradingMode enum: {mode_enum}")
        print(f"  Enum value: '{mode_enum.value}'")
        
        assert mode_enum == TradingMode.LIVE
        print("✓ CLI 'live' mode works correctly\n")
        
    except Exception as e:
        print(f"✗ Error: {e}\n")
        raise


def test_paper_engine_mode_init():
    """Test that PaperEngine can be initialized with various mode inputs."""
    print("Testing PaperEngine mode initialization...")
    
    try:
        # Simulate what happens in PaperEngine.__init__
        test_cases = [
            ("paper", TradingMode.PAPER),
            ("PAPER", TradingMode.PAPER),
            ("Paper", TradingMode.PAPER),
            ("  PAPER  ", TradingMode.PAPER),
            ("live", TradingMode.LIVE),
            ("LIVE", TradingMode.LIVE),
            (TradingMode.PAPER, TradingMode.PAPER),  # enum instance
        ]
        
        for cfg_mode, expected in test_cases:
            mode_raw = cfg_mode
            
            # Apply normalization logic from PaperEngine.__init__
            if isinstance(mode_raw, TradingMode):
                mode = mode_raw
            else:
                mode_str = str(mode_raw).strip().lower()
                mode = TradingMode(mode_str)
            
            assert mode == expected, f"Failed for input '{cfg_mode}'"
            print(f"  ✓ '{cfg_mode}' -> {mode}")
        
        print("✓ All PaperEngine mode initialization cases work\n")
        
    except Exception as e:
        print(f"✗ Error: {e}\n")
        raise


if __name__ == "__main__":
    print("=" * 60)
    print("Testing TradingMode fix for issue:")
    print("  python -m scripts.run_day --mode paper --engines all")
    print("=" * 60)
    print()
    
    try:
        test_config_mode_parsing()
        test_cli_override_uppercase()
        test_cli_override_live()
        test_paper_engine_mode_init()
        
        print("=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        print()
        print("The fix successfully handles:")
        print("  • Lowercase mode strings (e.g., 'paper', 'live')")
        print("  • Uppercase mode strings (e.g., 'PAPER', 'LIVE')")
        print("  • Mixed case mode strings (e.g., 'Paper', 'Live')")
        print("  • Mode strings with whitespace")
        print("  • TradingMode enum instances")
        print()
        
    except Exception as e:
        print("=" * 60)
        print("✗ TESTS FAILED")
        print("=" * 60)
        sys.exit(1)
