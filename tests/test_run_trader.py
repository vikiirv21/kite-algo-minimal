"""
Tests for scripts/run_trader.py

These tests verify the behavior of the run_trader entrypoint script.
"""

import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]


def test_run_trader_help():
    """Test that run_trader help works."""
    result = subprocess.run(
        [sys.executable, "-m", "scripts.run_trader", "--help"],
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "paper" in result.stdout
    assert "live" in result.stdout
    assert "--login" in result.stdout
    assert "--config" in result.stdout


def test_run_trader_paper_mode_help():
    """Test that paper mode is a valid command."""
    result = subprocess.run(
        [sys.executable, "-m", "scripts.run_trader", "--help"],
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "paper" in result.stdout.lower()


def test_run_trader_live_requires_config():
    """Test that live mode requires explicit config."""
    result = subprocess.run(
        [sys.executable, "-m", "scripts.run_trader", "live"],
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
        timeout=5,
    )
    # Should exit with error code 1
    assert result.returncode == 1
    assert "requires explicit --config" in result.stderr.lower() or "requires explicit --config" in result.stdout.lower()


def test_run_day_backward_compatibility():
    """Test that run_day still works with existing flags."""
    result = subprocess.run(
        [sys.executable, "-m", "scripts.run_day", "--help"],
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "--mode" in result.stdout
    assert "--engines" in result.stdout
    assert "--login" in result.stdout
    assert "--config" in result.stdout


if __name__ == "__main__":
    # Run basic tests
    print("Running test_run_trader_help...")
    test_run_trader_help()
    print("✓ PASSED")
    
    print("Running test_run_trader_paper_mode_help...")
    test_run_trader_paper_mode_help()
    print("✓ PASSED")
    
    print("Running test_run_trader_live_requires_config...")
    test_run_trader_live_requires_config()
    print("✓ PASSED")
    
    print("Running test_run_day_backward_compatibility...")
    test_run_day_backward_compatibility()
    print("✓ PASSED")
    
    print("\nAll tests passed!")
