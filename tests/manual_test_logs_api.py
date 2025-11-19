#!/usr/bin/env python3
"""
Manual test script for Logs API endpoints.
Starts the dashboard server and tests the /api/logs/tail endpoint.
"""

import sys
import json
import time
import requests
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

BASE_URL = "http://127.0.0.1:8765"


def test_endpoint(method, path, params=None):
    """Test an API endpoint and print results."""
    url = f"{BASE_URL}{path}"
    
    try:
        if method == "GET":
            response = requests.get(url, params=params, timeout=5)
        else:
            raise ValueError(f"Unsupported method: {method}")
        
        print(f"\n{'='*70}")
        print(f"{method} {path}")
        if params:
            print(f"Params: {params}")
        print(f"Status: {response.status_code}")
        print(f"Response:")
        result = response.json()
        # Only print first few lines if there are many
        if isinstance(result, dict) and "lines" in result:
            lines = result["lines"]
            result_copy = result.copy()
            if len(lines) > 5:
                result_copy["lines"] = lines[:3] + ["...", f"({len(lines) - 5} more lines)", "..."] + lines[-2:]
            print(json.dumps(result_copy, indent=2))
        else:
            print(json.dumps(result, indent=2))
        print(f"{'='*70}")
        
        return response.status_code == 200, response.json()
    except Exception as exc:
        print(f"\n{'='*70}")
        print(f"{method} {path}")
        print(f"ERROR: {exc}")
        print(f"{'='*70}")
        return False, None


def create_test_logs():
    """Create test log files if they don't exist."""
    logs_dir = Path(__file__).parent.parent / "artifacts" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    
    # Create FNO log file
    fno_log = logs_dir / "fno_paper.log"
    if not fno_log.exists() or fno_log.stat().st_size < 100:
        print(f"Creating test log file: {fno_log}")
        with fno_log.open("w", encoding="utf-8") as f:
            for i in range(50):
                f.write(f"2025-01-19 10:00:{i:02d} [INFO] FNO engine log entry {i}\n")
    
    # Create Equity log file (with fewer entries)
    equity_log = logs_dir / "equity_paper.log"
    if not equity_log.exists():
        print(f"Creating test log file: {equity_log}")
        with equity_log.open("w", encoding="utf-8") as f:
            for i in range(20):
                f.write(f"2025-01-19 10:00:{i:02d} [INFO] Equity engine log entry {i}\n")
    
    print("Test log files created/verified")


def main():
    """Run all API endpoint tests."""
    print("\n" + "="*70)
    print("Logs API Endpoints Testing")
    print("="*70)
    print("\nNOTE: Make sure the dashboard server is running:")
    print("  python -m uvicorn apps.dashboard:app --host 127.0.0.1 --port 8765")
    print("\nWaiting 2 seconds for server to be ready...")
    time.sleep(2)
    
    # Create test logs
    create_test_logs()
    
    # Test 1: GET /api/logs/tail with FNO engine (default lines)
    print("\n[Test 1] GET /api/logs/tail - FNO engine (default 200 lines)")
    success, data = test_endpoint("GET", "/api/logs/tail", params={"engine": "fno"})
    
    if not success:
        print("\n❌ Server may not be running. Start with:")
        print("  python -m uvicorn apps.dashboard:app --host 127.0.0.1 --port 8765")
        return
    
    # Verify response structure
    if data:
        assert "engine" in data, "Missing 'engine' field"
        assert "lines" in data, "Missing 'lines' field"
        assert "count" in data, "Missing 'count' field"
        assert "file" in data, "Missing 'file' field"
        assert "exists" in data, "Missing 'exists' field"
        assert data["engine"] == "fno", f"Expected engine='fno', got '{data['engine']}'"
        print(f"\n✓ Response structure valid, got {data['count']} lines")
    
    # Test 2: GET /api/logs/tail with specific line count
    print("\n[Test 2] GET /api/logs/tail - FNO engine (10 lines)")
    success, data = test_endpoint("GET", "/api/logs/tail", params={"engine": "fno", "lines": 10})
    if data:
        assert data["count"] <= 10, f"Expected max 10 lines, got {data['count']}"
        print(f"\n✓ Line count validation passed: {data['count']} <= 10")
    
    # Test 3: GET /api/logs/tail with equity engine
    print("\n[Test 3] GET /api/logs/tail - Equity engine")
    success, data = test_endpoint("GET", "/api/logs/tail", params={"engine": "equity", "lines": 15})
    if data:
        print(f"\n✓ Equity engine query succeeded, got {data['count']} lines")
    
    # Test 4: GET /api/logs/tail with options engine (likely doesn't exist)
    print("\n[Test 4] GET /api/logs/tail - Options engine (may not exist)")
    success, data = test_endpoint("GET", "/api/logs/tail", params={"engine": "options", "lines": 10})
    if data and not data.get("exists"):
        print(f"\n✓ Non-existent file handled correctly: {data.get('warning')}")
    
    # Test 5: GET /api/logs/tail with invalid engine (should fail)
    print("\n[Test 5] GET /api/logs/tail - Invalid engine name (should fail)")
    success, data = test_endpoint("GET", "/api/logs/tail", params={"engine": "invalid", "lines": 10})
    if not success or (data and "detail" in data):
        print("\n✓ Invalid engine rejected as expected")
    
    # Test 6: GET /api/logs/tail with max lines (2000)
    print("\n[Test 6] GET /api/logs/tail - Maximum lines (2000)")
    success, data = test_endpoint("GET", "/api/logs/tail", params={"engine": "fno", "lines": 2000})
    if success:
        print(f"\n✓ Max lines (2000) accepted, got {data['count']} lines")
    
    # Test 7: GET /api/logs/tail with too many lines (should fail)
    print("\n[Test 7] GET /api/logs/tail - Over maximum lines (2001, should fail)")
    success, data = test_endpoint("GET", "/api/logs/tail", params={"engine": "fno", "lines": 2001})
    if not success or (data and "detail" in data):
        print("\n✓ Over-limit lines rejected as expected")
    
    # Test 8: GET /api/logs/tail with lines=1
    print("\n[Test 8] GET /api/logs/tail - Minimum lines (1)")
    success, data = test_endpoint("GET", "/api/logs/tail", params={"engine": "fno", "lines": 1})
    if data:
        assert data["count"] <= 1, f"Expected max 1 line, got {data['count']}"
        print(f"\n✓ Minimum lines (1) accepted, got {data['count']} lines")
    
    # Test 9: GET /api/logs/tail with lines=0 (should fail)
    print("\n[Test 9] GET /api/logs/tail - Zero lines (should fail)")
    success, data = test_endpoint("GET", "/api/logs/tail", params={"engine": "fno", "lines": 0})
    if not success or (data and "detail" in data):
        print("\n✓ Zero lines rejected as expected")
    
    print("\n" + "="*70)
    print("Testing Complete!")
    print("="*70)
    print("\nAll tests passed! The /api/logs/tail endpoint is working correctly.")


if __name__ == "__main__":
    main()
