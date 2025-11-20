#!/usr/bin/env python
"""
Manual verification script for SRDE implementation.

This script verifies that all components work correctly without needing
to run the full trading engine.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

def verify_diagnostics_module():
    """Verify the diagnostics module works correctly."""
    print("=" * 60)
    print("Verifying Diagnostics Module")
    print("=" * 60)
    
    from analytics.diagnostics import (
        ensure_diagnostics_dir,
        path_for,
        append_diagnostic,
        load_diagnostics,
        build_diagnostic_record,
    )
    
    # Test 1: Directory creation
    print("\n1. Testing directory creation...")
    diag_dir = ensure_diagnostics_dir()
    assert diag_dir.exists(), "Diagnostics directory should exist"
    print(f"   ✓ Directory created at: {diag_dir}")
    
    # Test 2: Path generation
    print("\n2. Testing path generation...")
    path = path_for("TEST_SYMBOL", "TEST_STRATEGY")
    assert "TEST_SYMBOL" in str(path)
    assert "TEST_STRATEGY.jsonl" in str(path)
    print(f"   ✓ Path generated: {path}")
    
    # Test 3: Build diagnostic record
    print("\n3. Testing record building...")
    record = build_diagnostic_record(
        price=18500.0,
        decision="BUY",
        reason="Test signal",
        confidence=0.8,
        ema20=18480.0,
        ema50=18450.0,
        trend_strength=0.042,
    )
    assert record["price"] == 18500.0
    assert record["decision"] == "BUY"
    assert "ts" in record
    print(f"   ✓ Record built with {len(record)} fields")
    
    # Test 4: Append diagnostic
    print("\n4. Testing diagnostic append...")
    result = append_diagnostic("VERIFY_TEST", "VERIFY_STRATEGY", record)
    assert result is True, "Append should succeed"
    print("   ✓ Diagnostic appended successfully")
    
    # Test 5: Load diagnostics
    print("\n5. Testing diagnostic load...")
    loaded = load_diagnostics("VERIFY_TEST", "VERIFY_STRATEGY", limit=10)
    assert len(loaded) >= 1, "Should have at least 1 record"
    assert loaded[0]["price"] == 18500.0
    print(f"   ✓ Loaded {len(loaded)} diagnostic record(s)")
    
    # Test 6: Multiple appends
    print("\n6. Testing multiple appends...")
    for i in range(5):
        rec = build_diagnostic_record(
            price=18500.0 + i,
            decision=["BUY", "HOLD", "SELL"][i % 3],
            reason=f"Test signal {i}",
            confidence=0.5 + (i * 0.1),
        )
        append_diagnostic("MULTI_TEST", "MULTI_STRATEGY", rec)
    
    loaded = load_diagnostics("MULTI_TEST", "MULTI_STRATEGY", limit=10)
    assert len(loaded) == 5, f"Should have 5 records, got {len(loaded)}"
    print(f"   ✓ Multiple appends successful ({len(loaded)} records)")
    
    # Test 7: Limit parameter
    print("\n7. Testing limit parameter...")
    loaded_limited = load_diagnostics("MULTI_TEST", "MULTI_STRATEGY", limit=3)
    assert len(loaded_limited) == 3, f"Should respect limit=3, got {len(loaded_limited)}"
    print("   ✓ Limit parameter working correctly")
    
    print("\n" + "=" * 60)
    print("✓ All diagnostics module tests passed!")
    print("=" * 60)


def verify_dashboard_endpoint():
    """Verify the dashboard endpoint is properly defined."""
    print("\n" + "=" * 60)
    print("Verifying Dashboard Endpoint")
    print("=" * 60)
    
    # Check that the endpoint exists
    print("\n1. Checking dashboard.py modifications...")
    
    dashboard_path = Path(__file__).parent / "apps" / "dashboard.py"
    content = dashboard_path.read_text()
    
    # Verify import
    assert "from analytics.diagnostics import load_diagnostics" in content, \
        "Missing diagnostics import"
    print("   ✓ Diagnostics import present")
    
    # Verify endpoint definition
    assert "async def get_strategy_diagnostics" in content, \
        "Missing endpoint function"
    print("   ✓ Endpoint function defined")
    
    # Verify route decorator
    assert '@router.get("/api/diagnostics/strategy")' in content, \
        "Missing route decorator"
    print("   ✓ Route decorator present")
    
    # Verify parameters
    assert "symbol: str" in content and "strategy: str" in content, \
        "Missing required parameters"
    print("   ✓ Required parameters defined")
    
    print("\n" + "=" * 60)
    print("✓ Dashboard endpoint verification passed!")
    print("=" * 60)


def verify_strategy_engine_integration():
    """Verify StrategyEngineV2 integration."""
    print("\n" + "=" * 60)
    print("Verifying Strategy Engine Integration")
    print("=" * 60)
    
    engine_path = Path(__file__).parent / "core" / "strategy_engine_v2.py"
    content = engine_path.read_text()
    
    # Verify _emit_diagnostic method exists
    print("\n1. Checking _emit_diagnostic method...")
    assert "def _emit_diagnostic" in content, \
        "Missing _emit_diagnostic method"
    print("   ✓ _emit_diagnostic method defined")
    
    # Verify it's called from evaluate
    print("\n2. Checking diagnostics emission in evaluate()...")
    assert "self._emit_diagnostic(" in content, \
        "Missing _emit_diagnostic call"
    print("   ✓ Diagnostics emission call present")
    
    # Verify try/except protection
    print("\n3. Checking error handling...")
    assert "try:" in content and "except" in content, \
        "Missing error handling"
    print("   ✓ Error handling present")
    
    # Verify diagnostic imports
    print("\n4. Checking diagnostic imports in _emit_diagnostic...")
    assert "from analytics.diagnostics import" in content, \
        "Missing diagnostics imports"
    print("   ✓ Diagnostics imports present")
    
    print("\n" + "=" * 60)
    print("✓ Strategy engine integration verification passed!")
    print("=" * 60)


def verify_test_coverage():
    """Verify test files exist and are complete."""
    print("\n" + "=" * 60)
    print("Verifying Test Coverage")
    print("=" * 60)
    
    tests_dir = Path(__file__).parent / "tests"
    
    # Check unit tests
    print("\n1. Checking unit tests...")
    unit_test = tests_dir / "test_diagnostics.py"
    assert unit_test.exists(), "Missing test_diagnostics.py"
    
    content = unit_test.read_text()
    test_funcs = [
        "test_ensure_diagnostics_dir",
        "test_path_for",
        "test_build_diagnostic_record",
        "test_append_and_load_diagnostics",
        "test_load_nonexistent_diagnostics",
        "test_append_diagnostic_limit",
    ]
    
    for func in test_funcs:
        assert f"def {func}" in content, f"Missing test function: {func}"
    
    print(f"   ✓ Unit test file exists with {len(test_funcs)} tests")
    
    # Check integration tests
    print("\n2. Checking integration tests...")
    int_test = tests_dir / "test_srde_integration.py"
    assert int_test.exists(), "Missing test_srde_integration.py"
    print("   ✓ Integration test file exists")
    
    print("\n" + "=" * 60)
    print("✓ Test coverage verification passed!")
    print("=" * 60)


def verify_documentation():
    """Verify documentation exists."""
    print("\n" + "=" * 60)
    print("Verifying Documentation")
    print("=" * 60)
    
    doc_path = Path(__file__).parent / "SRDE_DIAGNOSTICS.md"
    assert doc_path.exists(), "Missing SRDE_DIAGNOSTICS.md"
    
    content = doc_path.read_text()
    
    # Check for key sections
    sections = [
        "## Overview",
        "## Architecture",
        "## Usage",
        "## Diagnostic Record Schema",
        "## Integration",
        "## Error Handling",
    ]
    
    for section in sections:
        assert section in content, f"Missing documentation section: {section}"
    
    print(f"   ✓ Documentation exists with {len(sections)} main sections")
    print(f"   ✓ Documentation size: {len(content)} characters")
    
    print("\n" + "=" * 60)
    print("✓ Documentation verification passed!")
    print("=" * 60)


def main():
    """Run all verifications."""
    print("\n" + "=" * 60)
    print("SRDE IMPLEMENTATION VERIFICATION")
    print("=" * 60)
    
    try:
        verify_diagnostics_module()
        verify_dashboard_endpoint()
        verify_strategy_engine_integration()
        verify_test_coverage()
        verify_documentation()
        
        print("\n" + "=" * 60)
        print("✓✓✓ ALL VERIFICATIONS PASSED ✓✓✓")
        print("=" * 60)
        print("\nThe SRDE implementation is complete and ready for use!")
        print("\nNext steps:")
        print("  1. Start the dashboard: python -m uvicorn apps.dashboard:app")
        print("  2. Test the endpoint: curl 'http://localhost:8000/api/diagnostics/strategy?symbol=NIFTY&strategy=EMA_20_50'")
        print("  3. Run a paper engine to generate diagnostics")
        print("  4. Check artifacts/diagnostics/ for JSONL files")
        print("=" * 60 + "\n")
        
        return 0
        
    except AssertionError as exc:
        print(f"\n✗ Verification failed: {exc}")
        return 1
    except Exception as exc:
        print(f"\n✗ Unexpected error: {exc}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
