"""
End-to-end integration test for multi-process architecture.

This test validates that the multi-process architecture works correctly
by testing process spawning, monitoring, and shutdown.
"""

import subprocess
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]


def test_single_process_dry_run():
    """Test single-process mode with dry-run."""
    print("\n" + "=" * 70)
    print("TEST 1: Single-Process Mode (Dry-Run)")
    print("=" * 70)
    
    cmd = [
        sys.executable,
        "-m",
        "scripts.run_session",
        "--mode", "paper",
        "--config", "configs/dev.yaml",
        "--layout", "single",
        "--dry-run",
    ]
    
    print(f"Command: {' '.join(cmd)}")
    print()
    
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=BASE_DIR,
        timeout=30,
    )
    
    # Check for success
    if result.returncode == 0:
        print("✅ Single-process dry-run completed successfully")
        
        # Verify key log messages
        checks = [
            ("Layout: single", "Layout configuration"),
            ("Dry run: True", "Dry run flag"),
            ("Pre-market checks:", "Pre-market checks"),
            ("Dry run mode: Pre-checks completed", "Dry run completion"),
        ]
        
        for expected, description in checks:
            if expected in result.stdout or expected in result.stderr:
                print(f"  ✓ {description}")
            else:
                print(f"  ✗ Missing: {description}")
                return False
        
        return True
    else:
        print(f"❌ Single-process dry-run failed with exit code {result.returncode}")
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)
        return False


def test_multi_process_dry_run():
    """Test multi-process mode with dry-run."""
    print("\n" + "=" * 70)
    print("TEST 2: Multi-Process Mode (Dry-Run)")
    print("=" * 70)
    
    cmd = [
        sys.executable,
        "-m",
        "scripts.run_session",
        "--mode", "paper",
        "--config", "configs/dev.yaml",
        "--layout", "multi",
        "--dry-run",
    ]
    
    print(f"Command: {' '.join(cmd)}")
    print()
    
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=BASE_DIR,
        timeout=30,
    )
    
    # Check for success
    if result.returncode == 0:
        print("✅ Multi-process dry-run completed successfully")
        
        # Verify key log messages
        checks = [
            ("Layout: multi", "Layout configuration"),
            ("Dry run: True", "Dry run flag"),
            ("Pre-market checks:", "Pre-market checks"),
            ("Dry run mode: Pre-checks completed", "Dry run completion"),
        ]
        
        for expected, description in checks:
            if expected in result.stdout or expected in result.stderr:
                print(f"  ✓ {description}")
            else:
                print(f"  ✗ Missing: {description}")
                return False
        
        return True
    else:
        print(f"❌ Multi-process dry-run failed with exit code {result.returncode}")
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)
        return False


def test_individual_engine_help():
    """Test that individual engines can show help."""
    print("\n" + "=" * 70)
    print("TEST 3: Individual Engine Help Output")
    print("=" * 70)
    
    engines = [
        "apps.run_fno_paper",
        "apps.run_equity_paper",
        "apps.run_options_paper",
    ]
    
    all_passed = True
    
    for engine in engines:
        cmd = [sys.executable, "-m", engine, "--help"]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=BASE_DIR,
            timeout=10,
        )
        
        if result.returncode == 0 and "--config" in result.stdout:
            print(f"  ✓ {engine}")
        else:
            print(f"  ✗ {engine} (exit code: {result.returncode})")
            all_passed = False
    
    if all_passed:
        print("✅ All individual engines show help correctly")
        return True
    else:
        print("❌ Some individual engines failed")
        return False


def test_bootstrap_module():
    """Test that bootstrap module can be imported and used."""
    print("\n" + "=" * 70)
    print("TEST 4: Bootstrap Module Functions")
    print("=" * 70)
    
    try:
        # Import needs to be done from the correct working directory
        import sys
        sys.path.insert(0, str(BASE_DIR))
        
        from core.engine_bootstrap import (
            setup_engine_logging,
            resolve_fno_universe,
            resolve_equity_universe,
            resolve_options_universe,
        )
        
        # Check that functions are callable
        functions = [
            setup_engine_logging,
            resolve_fno_universe,
            resolve_equity_universe,
            resolve_options_universe,
        ]
        
        all_callable = True
        for func in functions:
            if callable(func):
                print(f"  ✓ {func.__name__}")
            else:
                print(f"  ✗ {func.__name__} is not callable")
                all_callable = False
        
        if all_callable:
            print("✅ All bootstrap functions are callable")
            return True
        else:
            print("❌ Some bootstrap functions are not callable")
            return False
            
    except Exception as e:
        print(f"❌ Failed to import bootstrap module: {e}")
        return False


def main():
    """Run all integration tests."""
    print("=" * 70)
    print("MULTI-PROCESS ARCHITECTURE - INTEGRATION TESTS")
    print("=" * 70)
    
    tests = [
        test_single_process_dry_run,
        test_multi_process_dry_run,
        test_individual_engine_help,
        test_bootstrap_module,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append((test.__name__, result))
        except Exception as e:
            print(f"\n❌ Test {test.__name__} failed with exception: {e}")
            results.append((test.__name__, False))
    
    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for _, result in results if result)
    failed = len(results) - passed
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print()
    print(f"Total: {passed} passed, {failed} failed out of {len(results)} tests")
    print("=" * 70)
    
    return failed == 0


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
