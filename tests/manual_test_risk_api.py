#!/usr/bin/env python3
"""
Manual test script for Risk API endpoints.
Starts the dashboard server and tests all risk endpoints.
"""

import sys
import json
import time
import requests
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

BASE_URL = "http://127.0.0.1:8765"

def test_endpoint(method, path, data=None, params=None):
    """Test an API endpoint and print results."""
    url = f"{BASE_URL}{path}"
    
    try:
        if method == "GET":
            response = requests.get(url, params=params, timeout=5)
        elif method == "POST":
            response = requests.post(url, json=data, timeout=5)
        else:
            raise ValueError(f"Unsupported method: {method}")
        
        print(f"\n{'='*70}")
        print(f"{method} {path}")
        if params:
            print(f"Params: {params}")
        if data:
            print(f"Data: {json.dumps(data, indent=2)}")
        print(f"Status: {response.status_code}")
        print(f"Response:")
        print(json.dumps(response.json(), indent=2))
        print(f"{'='*70}")
        
        return response.status_code == 200, response.json()
    except Exception as exc:
        print(f"\n{'='*70}")
        print(f"{method} {path}")
        print(f"ERROR: {exc}")
        print(f"{'='*70}")
        return False, None


def main():
    """Run all API endpoint tests."""
    print("\n" + "="*70)
    print("Risk API Endpoints Testing")
    print("="*70)
    print("\nNOTE: Make sure the dashboard server is running:")
    print("  python ui/dashboard.py")
    print("\nWaiting 2 seconds for server to be ready...")
    time.sleep(2)
    
    # Test 1: GET /api/risk/limits
    print("\n[Test 1] GET /api/risk/limits - Get current risk limits")
    success, limits_data = test_endpoint("GET", "/api/risk/limits")
    
    if not success:
        print("\n❌ Server may not be running. Start with: python ui/dashboard.py")
        return
    
    # Test 2: GET /api/risk/breaches
    print("\n[Test 2] GET /api/risk/breaches - Get risk breaches")
    test_endpoint("GET", "/api/risk/breaches")
    
    # Test 3: GET /api/risk/var (default params)
    print("\n[Test 3] GET /api/risk/var - Calculate VaR (default)")
    test_endpoint("GET", "/api/risk/var")
    
    # Test 4: GET /api/risk/var (custom params)
    print("\n[Test 4] GET /api/risk/var - Calculate VaR (custom params)")
    test_endpoint("GET", "/api/risk/var", params={"days": 60, "confidence": 0.99})
    
    # Test 5: POST /api/risk/limits (valid update)
    print("\n[Test 5] POST /api/risk/limits - Update risk limits (valid)")
    update_data = {
        "max_daily_loss_rupees": 6000.0,
        "max_trades_per_day": 120,
    }
    test_endpoint("POST", "/api/risk/limits", data=update_data)
    
    # Test 6: Verify update worked
    print("\n[Test 6] GET /api/risk/limits - Verify update")
    success, updated_limits = test_endpoint("GET", "/api/risk/limits")
    if success:
        limits = updated_limits.get("limits", {})
        if limits.get("max_daily_loss_rupees") == 6000.0:
            print("\n✓ Update verified: max_daily_loss_rupees = 6000.0")
        else:
            print(f"\n✗ Update failed: expected 6000.0, got {limits.get('max_daily_loss_rupees')}")
    
    # Test 7: POST /api/risk/limits (invalid field)
    print("\n[Test 7] POST /api/risk/limits - Update with invalid field (should fail)")
    invalid_data = {
        "invalid_field": 12345,
    }
    test_endpoint("POST", "/api/risk/limits", data=invalid_data)
    
    # Test 8: POST /api/risk/limits (invalid type)
    print("\n[Test 8] POST /api/risk/limits - Update with invalid type (should fail)")
    invalid_type_data = {
        "max_daily_loss_rupees": "not_a_number",
    }
    test_endpoint("POST", "/api/risk/limits", data=invalid_type_data)
    
    # Test 9: POST /api/risk/limits (negative value)
    print("\n[Test 9] POST /api/risk/limits - Update with negative value (should fail)")
    negative_data = {
        "max_daily_loss_rupees": -5000.0,
    }
    test_endpoint("POST", "/api/risk/limits", data=negative_data)
    
    print("\n" + "="*70)
    print("Testing Complete!")
    print("="*70)


if __name__ == "__main__":
    main()
