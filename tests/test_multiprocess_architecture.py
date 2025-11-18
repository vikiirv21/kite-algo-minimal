"""
Simple validation tests for multi-process architecture components.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_imports():
    """Test that all new modules can be imported."""
    print("Testing imports...")
    
    try:
        import core.engine_bootstrap
        print("✓ core.engine_bootstrap imported")
    except ImportError as e:
        print(f"✗ Failed to import core.engine_bootstrap: {e}")
        return False
    
    try:
        import apps.run_fno_paper
        print("✓ apps.run_fno_paper imported")
    except ImportError as e:
        print(f"✗ Failed to import apps.run_fno_paper: {e}")
        return False
    
    try:
        import apps.run_equity_paper
        print("✓ apps.run_equity_paper imported")
    except ImportError as e:
        print(f"✗ Failed to import apps.run_equity_paper: {e}")
        return False
    
    try:
        import apps.run_options_paper
        print("✓ apps.run_options_paper imported")
    except ImportError as e:
        print(f"✗ Failed to import apps.run_options_paper: {e}")
        return False
    
    return True


def test_bootstrap_functions():
    """Test that bootstrap helper functions exist."""
    print("\nTesting bootstrap functions...")
    
    from core.engine_bootstrap import (
        setup_engine_logging,
        build_kite_client,
        build_fno_universe,
        build_equity_universe,
        build_options_universe,
        resolve_fno_universe,
        resolve_equity_universe,
        resolve_options_universe,
        load_scanner_universe,
    )
    
    functions = [
        setup_engine_logging,
        build_kite_client,
        build_fno_universe,
        build_equity_universe,
        build_options_universe,
        resolve_fno_universe,
        resolve_equity_universe,
        resolve_options_universe,
        load_scanner_universe,
    ]
    
    for func in functions:
        if callable(func):
            print(f"✓ {func.__name__} is callable")
        else:
            print(f"✗ {func.__name__} is not callable")
            return False
    
    return True


def test_run_session_layout_support():
    """Test that run_session.py supports --layout flag."""
    print("\nTesting run_session layout support...")
    
    import subprocess
    
    result = subprocess.run(
        [sys.executable, "-m", "scripts.run_session", "--help"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
    )
    
    if "--layout" in result.stdout:
        print("✓ --layout flag found in run_session help")
        return True
    else:
        print("✗ --layout flag not found in run_session help")
        return False


def main():
    """Run all validation tests."""
    print("=" * 60)
    print("Multi-Process Architecture Validation Tests")
    print("=" * 60)
    
    tests = [
        test_imports,
        test_bootstrap_functions,
        test_run_session_layout_support,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"✗ Test {test.__name__} failed with exception: {e}")
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
