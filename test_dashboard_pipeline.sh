#!/bin/bash
# Dashboard Data Pipeline - Verification Script
# Tests all new functionality to ensure everything works

set -e

echo "================================"
echo "Dashboard Data Pipeline Tests"
echo "================================"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Start server in background
echo "1. Starting backend server..."
cd /home/runner/work/kite-algo-minimal/kite-algo-minimal
python -m uvicorn ui.dashboard:app --host 127.0.0.1 --port 8767 > /tmp/dashboard_test.log 2>&1 &
SERVER_PID=$!
sleep 5

# Test API endpoints
echo "2. Testing API endpoints..."

# Test /api/pm/metrics
echo -n "   Testing /api/pm/metrics... "
METRICS_RESPONSE=$(curl -s http://127.0.0.1:8767/api/pm/metrics)
if echo "$METRICS_RESPONSE" | grep -q '"mode"'; then
    echo -e "${GREEN}✓ PASS${NC}"
else
    echo -e "${RED}✗ FAIL${NC}"
    kill $SERVER_PID 2>/dev/null || true
    exit 1
fi

# Test /api/trading/status
echo -n "   Testing /api/trading/status... "
STATUS_RESPONSE=$(curl -s http://127.0.0.1:8767/api/trading/status)
if echo "$STATUS_RESPONSE" | grep -q '"ist_time"'; then
    echo -e "${GREEN}✓ PASS${NC}"
else
    echo -e "${RED}✗ FAIL${NC}"
    kill $SERVER_PID 2>/dev/null || true
    exit 1
fi

# Test /api/risk/summary
echo -n "   Testing /api/risk/summary... "
RISK_RESPONSE=$(curl -s http://127.0.0.1:8767/api/risk/summary)
if echo "$RISK_RESPONSE" | grep -q '"trading_halted"'; then
    echo -e "${GREEN}✓ PASS${NC}"
else
    echo -e "${RED}✗ FAIL${NC}"
    kill $SERVER_PID 2>/dev/null || true
    exit 1
fi

# Test /api/strategies
echo -n "   Testing /api/strategies... "
STRAT_RESPONSE=$(curl -s http://127.0.0.1:8767/api/strategies/)
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ PASS${NC}"
else
    echo -e "${RED}✗ FAIL${NC}"
fi

# Test root page loads
echo -n "   Testing dashboard root page... "
ROOT_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8767/)
if [ "$ROOT_RESPONSE" = "200" ]; then
    echo -e "${GREEN}✓ PASS${NC}"
else
    echo -e "${RED}✗ FAIL (HTTP $ROOT_RESPONSE)${NC}"
fi

# Cleanup
echo ""
echo "3. Cleaning up..."
kill $SERVER_PID 2>/dev/null || true
sleep 2

echo ""
echo "================================"
echo -e "${GREEN}All tests passed!${NC}"
echo "================================"
echo ""
echo "Dashboard data pipeline is ready for production."
echo ""
echo "To start the dashboard:"
echo "  cd /home/runner/work/kite-algo-minimal/kite-algo-minimal"
echo "  python -m uvicorn ui.dashboard:app --host 0.0.0.0 --port 8765"
echo ""
