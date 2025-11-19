# Operational Runbook – kite-algo-minimal

> **Status**: CURRENT – Last updated: 2025-11-19  
> **Purpose**: Day-to-day operational guide for traders and operators

---

## Table of Contents

1. [Daily Routine](#daily-routine)
2. [Pre-Market Checklist](#pre-market-checklist)
3. [Starting the System](#starting-the-system)
4. [Monitoring During Trading](#monitoring-during-trading)
5. [Post-Market Shutdown](#post-market-shutdown)
6. [Common Operations](#common-operations)
7. [Troubleshooting](#troubleshooting)
8. [Emergency Procedures](#emergency-procedures)

---

## Daily Routine

### Overview

A typical trading day involves:

1. **8:45 AM**: Pre-market checks (login, universe build)
2. **9:00 AM**: Start engines
3. **9:15 AM - 3:30 PM**: Monitor trading, intervene if needed
4. **3:30 PM**: Engines auto-stop (market close)
5. **4:00 PM**: Review analytics, generate reports

---

## Pre-Market Checklist

### 1. Kite Login (8:45 AM)

**Purpose**: Generate fresh access token for the day

**Command**:
```bash
python -m scripts.login_kite
```

**Steps**:
1. Script opens browser to Kite login page
2. Enter Kite credentials (user ID, password, 2FA)
3. Authorize app
4. Script saves access token to `secrets/kite_tokens.env`

**Verify**:
```bash
# Check token file exists
cat secrets/kite_tokens.env

# Expected output:
# ACCESS_TOKEN=xyz789...
# EXPIRY=2025-11-19 23:59:59
```

**Troubleshooting**:
- If browser doesn't open: Copy URL from terminal and paste in browser
- If login fails: Check credentials in `secrets/kite.env`
- If token invalid: Delete `secrets/kite_tokens.env` and re-run login

### 2. Build Universe (8:50 AM)

**Purpose**: Generate daily tradeable universe for equity engine

**Command**:
```bash
python -m scripts.run_indicator_scanner --config configs/dev.yaml
```

**Output**:
```
artifacts/scanner/2025-11-19/universe.json
```

**What It Does**:
1. Fetches NIFTY 50 and NIFTY 100 constituents
2. Filters by price (min: ₹100)
3. Filters by liquidity (optional)
4. Saves to universe.json

**Verify**:
```bash
cat artifacts/scanner/$(date +%Y-%m-%d)/universe.json | jq '.count'
# Expected: 80-120 symbols
```

**Troubleshooting**:
- If file not created: Check token validity
- If count is 0: Check filter parameters in config
- If missing symbols: Update NIFTY lists in data/universe/

### 3. Check System Health (8:55 AM)

**Command**:
```bash
# Check artifacts directory
ls -la artifacts/checkpoints/

# Check logs directory
ls -la artifacts/logs/

# Check disk space
df -h artifacts/
```

**What to Check**:
- ✅ Artifacts directory writable
- ✅ Enough disk space (> 1 GB free)
- ✅ No stale lock files
- ✅ Previous day's logs archived

**Clean Up** (if needed):
```bash
# Archive old logs
gzip artifacts/logs/*.log.1

# Remove old snapshots (> 7 days)
find artifacts/snapshots/ -name "*.json" -mtime +7 -delete

# Remove old orders CSV (> 30 days)
find artifacts/ -name "orders_*.csv" -mtime +30 -delete
```

---

## Starting the System

### Option 1: Complete Session (Recommended)

**Command**:
```bash
python -m scripts.run_session --mode paper --config configs/dev.yaml
```

**What It Does**:
1. Validates token
2. Builds universe (if not exists)
3. Starts all engines (equity, FnO, options)
4. Monitors market hours
5. Auto-stops at market close
6. Generates analytics report

**Best For**: Full automated trading day

### Option 2: Individual Engines

**Equity Engine Only**:
```bash
python -m apps.run_equity_paper --config configs/dev.yaml --mode paper
```

**FnO Engine Only**:
```bash
python -m apps.run_fno_paper --config configs/dev.yaml --mode paper
```

**Options Engine Only**:
```bash
python -m apps.run_options_paper --config configs/dev.yaml --mode paper
```

**Best For**: Testing specific asset class

### Option 3: Multi-Process Mode

**Command**:
```bash
python -m scripts.run_session --mode paper --config configs/dev.yaml --layout multi
```

**What It Does**:
- Each engine runs as separate Python process
- Better isolation and performance
- Slightly more complex to monitor

**Best For**: Production, high-frequency trading

### Start Dashboard

**Command** (in separate terminal):
```bash
python -m uvicorn apps.server:app --host 0.0.0.0 --port 9000
```

**Access**: http://localhost:9000

**Best Practice**: Start dashboard before engines for full monitoring

---

## Monitoring During Trading

### 1. Dashboard Monitoring (Primary)

**URL**: http://localhost:9000

**What to Watch**:

**Overview Page** (every 5 minutes):
- ✅ Total P&L positive or within acceptable drawdown
- ✅ Portfolio equity not declining too fast
- ✅ Positions count within limits

**Trading Page** (every 10 minutes):
- ✅ Open positions have reasonable P&L
- ✅ No positions with excessive losses
- ✅ Positions spread across symbols (not concentrated)

**Signals Page** (if needed):
- ✅ Strategies generating reasonable signals
- ✅ Not too many HOLD signals (indicates indicator issue)
- ✅ Confidence scores reasonable (> 0.5 for entries)

**Logs Page** (if issues):
- ❌ No ERROR level logs
- ⚠️ Few WARNING logs acceptable
- ✅ INFO logs show normal activity

### 2. Command Line Monitoring

**Check Engine Status**:
```bash
# Check if engines running
ps aux | grep python | grep -E "run_equity|run_fno|run_options"

# Expected output:
# python -m apps.run_equity_paper ...
# python -m apps.run_fno_paper ...
```

**Check Recent Orders**:
```bash
# View today's orders
tail -20 artifacts/orders_equity_paper_$(date +%Y-%m-%d).csv

# Count orders
wc -l artifacts/orders_equity_paper_$(date +%Y-%m-%d).csv
```

**Check Current State**:
```bash
# View checkpoint
cat artifacts/checkpoints/runtime_state_latest.json | jq '.portfolio'

# Output:
# {
#   "equity": 500000.0,
#   "realized_pnl": 1250.50,
#   "unrealized_pnl": -320.00,
#   "total_pnl": 930.50
# }
```

**Check Logs**:
```bash
# Follow equity engine log
tail -f artifacts/logs/equity_paper_engine.log

# Check for errors
grep ERROR artifacts/logs/*.log

# Check for warnings
grep WARN artifacts/logs/*.log
```

### 3. Key Metrics to Watch

**Portfolio Metrics**:
- Total P&L: Should be positive or < -3000
- Unrealized P&L: Watch for large negative values (> -1500 per position)
- Exposure: Should be < 80% of capital
- Position count: Should be ≤ 5 (configurable)

**Risk Metrics**:
- Daily loss: If approaching max_daily_loss (₹3000), be ready to stop
- Per-symbol loss: If any symbol approaching per_symbol_max_loss (₹1500), check strategy
- Drawdown: If > 3%, investigate issue

**Performance Metrics**:
- Win rate: Should be > 50% (ideally 55-65%)
- Profit factor: Should be > 1.5
- Average win > average loss

### 4. When to Intervene

**Stop Trading If**:
- ❌ Daily loss > ₹2500 (approaching max_daily_loss)
- ❌ Drawdown > 2.5%
- ❌ 3+ consecutive losing trades
- ❌ Token expired or auth issue
- ❌ Engine crashed and not auto-restarting

**Investigate If**:
- ⚠️ No trades for > 1 hour (during market hours)
- ⚠️ Win rate < 45%
- ⚠️ Positions stuck (not exiting on signals)
- ⚠️ Excessive slippage (> 0.5% average)
- ⚠️ Log showing repeated errors

---

## Post-Market Shutdown

### 1. Verify Engines Stopped

**Check**:
```bash
ps aux | grep python | grep -E "run_equity|run_fno|run_options"

# If still running, kill:
pkill -f "run_equity_paper"
pkill -f "run_fno_paper"
pkill -f "run_options_paper"
```

**Note**: Session orchestrator auto-stops engines at 3:30 PM

### 2. Review Orders

**Command**:
```bash
# Count orders
echo "Equity orders: $(wc -l < artifacts/orders_equity_paper_$(date +%Y-%m-%d).csv)"
echo "FnO orders: $(wc -l < artifacts/orders_fno_paper_$(date +%Y-%m-%d).csv)"
echo "Options orders: $(wc -l < artifacts/orders_options_paper_$(date +%Y-%m-%d).csv)"
```

**Verify**:
- ✅ All orders have status FILLED or CANCELLED (no PENDING)
- ✅ Order count matches expected (10-50 typical)
- ✅ No duplicate orders

### 3. Generate Analytics Report

**Command**:
```bash
python -m scripts.run_analytics --config configs/dev.yaml
```

**Output**:
```
artifacts/reports/daily/2025-11-19.json
artifacts/reports/daily/2025-11-19.md
```

**Review**:
```bash
# View markdown report
cat artifacts/reports/daily/$(date +%Y-%m-%d).md

# View JSON metrics
cat artifacts/reports/daily/$(date +%Y-%m-%d).json | jq '.performance'
```

### 4. Save Checkpoint

**Command**:
```bash
# Copy final checkpoint
cp artifacts/checkpoints/runtime_state_latest.json \
   artifacts/checkpoints/runtime_state_$(date +%Y-%m-%d).json
```

### 5. Backup Important Files

**Command**:
```bash
# Create daily backup
mkdir -p backups/$(date +%Y-%m-%d)

cp artifacts/orders_*.csv backups/$(date +%Y-%m-%d)/
cp artifacts/checkpoints/runtime_state_*.json backups/$(date +%Y-%m-%d)/
cp artifacts/reports/daily/$(date +%Y-%m-%d).* backups/$(date +%Y-%m-%d)/
```

---

## Common Operations

### Check Token Status

```bash
# Read token expiry
grep EXPIRY secrets/kite_tokens.env

# Test token
python -c "
from core.kite_env import make_kite_client_from_files, token_is_valid
kite = make_kite_client_from_files()
print('Token valid:', token_is_valid(kite))
"
```

### Manually Place Order (Paper Mode)

```bash
python -c "
from broker.paper_broker import PaperBroker
broker = PaperBroker()
order = broker.place_order('RELIANCE', 'BUY', 10, 'MARKET', None)
print('Order:', order)
"
```

### View Current Positions

```bash
# From checkpoint
cat artifacts/checkpoints/runtime_state_latest.json | jq '.positions'

# From dashboard API
curl http://localhost:9000/api/positions | jq '.positions'
```

### Check Universe

```bash
# View universe
cat artifacts/scanner/$(date +%Y-%m-%d)/universe.json | jq '.equity_universe[].symbol'

# Count symbols
cat artifacts/scanner/$(date +%Y-%m-%d)/universe.json | jq '.count'
```

### Manually Run Analytics

```bash
# Generate report
python -m scripts.run_analytics --config configs/dev.yaml

# View equity curve
python -m scripts.analyze_paper_results
```

### Switch Mode (Paper ↔ Live)

**CAUTION**: Switching to live mode requires careful preparation

```bash
# Check current mode
grep "mode:" configs/dev.yaml

# Edit config
vim configs/dev.yaml
# Change: mode: "paper" → mode: "live"

# Restart engines with new config
python -m scripts.run_session --mode live --config configs/dev.yaml
```

**Pre-Live Checklist**:
- ✅ Tested thoroughly in paper mode (> 5 days)
- ✅ Win rate > 55%
- ✅ Max drawdown < 5%
- ✅ Token valid
- ✅ Sufficient margin in Kite account
- ✅ Risk limits configured conservatively
- ✅ Monitoring in place (dashboard, alerts)

---

## Troubleshooting

### Issue: Engine Won't Start

**Symptoms**: Engine exits immediately

**Solutions**:
1. Check token:
   ```bash
   python -m scripts.login_kite
   ```
2. Check config file:
   ```bash
   cat configs/dev.yaml
   ```
3. Check logs:
   ```bash
   tail -50 artifacts/logs/equity_paper_engine.log
   ```

### Issue: No Trades Happening

**Symptoms**: Engine runs but no orders placed

**Possible Causes**:
1. **Indicators not ready**: Insufficient history
   - Solution: Increase `history_lookback` to 200+
2. **Risk limits hit**: Daily loss or position limit
   - Solution: Check `max_daily_loss`, `max_open_positions`
3. **Strategy disabled**: Not enabled in config
   - Solution: Check `strategies_v2` section, set `enabled: true`
4. **Regime mismatch**: Strategy requires specific regime
   - Solution: Check regime logs, adjust regime thresholds

**Debug**:
```bash
# Check signals
cat artifacts/signals.csv | tail -20

# Check if only HOLD signals
cat artifacts/signals.csv | grep -v HOLD | tail -10

# Check strategy evaluation logs
grep "strategy.*evaluate" artifacts/logs/equity_paper_engine.log | tail -20
```

### Issue: Orders Not Filling (Live Mode)

**Symptoms**: Orders placed but not filled

**Possible Causes**:
1. **Invalid price**: Limit price too far from LTP
2. **Insufficient margin**: Not enough capital
3. **Symbol suspended**: Circuit filter or halt

**Debug**:
```bash
# Check order status via Kite
# https://kite.zerodha.com/orders

# Check reconciliation logs
grep "reconciliation" artifacts/logs/live_engine.log | tail -20
```

### Issue: High Slippage

**Symptoms**: Fill prices far from expected

**Solutions**:
1. Use LIMIT orders instead of MARKET
2. Trade more liquid symbols
3. Reduce position size
4. Avoid trading at open/close

**Check Slippage**:
```bash
# Calculate average slippage from orders CSV
python -c "
import pandas as pd
df = pd.read_csv('artifacts/orders_equity_paper_$(date +%Y-%m-%d).csv')
df['slippage_pct'] = abs(df['avg_fill_price'] - df['price']) / df['price'] * 100
print(f'Avg slippage: {df[\"slippage_pct\"].mean():.2f}%')
"
```

### Issue: Dashboard Not Loading

**Symptoms**: Blank page or 404 errors

**Solutions**:
1. Rebuild frontend:
   ```bash
   ./build-dashboard.sh
   ```
2. Check static files:
   ```bash
   ls -la static/index.html
   ```
3. Restart server:
   ```bash
   pkill -f "uvicorn.*server"
   python -m uvicorn apps.server:app --host 0.0.0.0 --port 9000
   ```

### Issue: Token Expired Mid-Day

**Symptoms**: Engines stop with "Token invalid" error

**Solution**:
```bash
# Kite tokens are valid for entire day
# If expired mid-day, it's a bug

# Workaround: Re-login
python -m scripts.login_kite

# Restart engines
python -m scripts.run_session --mode paper --config configs/dev.yaml
```

**Prevention**: Always login before market open

---

## Emergency Procedures

### Stop All Engines Immediately

```bash
# Kill all engine processes
pkill -9 -f "run_equity_paper"
pkill -9 -f "run_fno_paper"
pkill -9 -f "run_options_paper"
pkill -9 -f "run_session"

# Verify stopped
ps aux | grep python | grep -E "run_equity|run_fno|run_options"
```

### Exit All Positions (Paper Mode)

```bash
# This closes all positions in paper mode
python -c "
from core.portfolio_engine import PortfolioEngine
from broker.paper_broker import PaperBroker

broker = PaperBroker()
portfolio = PortfolioEngine()

for position in portfolio.get_all_positions():
    if position.qty != 0:
        side = 'SELL' if position.qty > 0 else 'BUY'
        qty = abs(position.qty)
        order = broker.place_order(position.symbol, side, qty, 'MARKET', None)
        print(f'Closed {position.symbol}: {order}')
"
```

### Exit All Positions (Live Mode)

**CAUTION**: This places real orders!

```bash
# Manual exit via Kite web
# https://kite.zerodha.com/positions
# Click "Exit all" button
```

### Check Live Positions

```bash
# Fetch from broker (live mode only)
python -c "
from core.kite_env import make_kite_client_from_files
kite = make_kite_client_from_files()
positions = kite.positions()
print('Net positions:', positions.get('net', []))
"
```

### Roll Back to Previous State

```bash
# Restore checkpoint from backup
cp backups/$(date +%Y-%m-%d --date="yesterday")/runtime_state_*.json \
   artifacts/checkpoints/runtime_state_latest.json

# Restart engines
python -m scripts.run_session --mode paper --config configs/dev.yaml
```

---

## Best Practices

### Before Going Live

1. **Test in paper mode**: Minimum 5-7 trading days
2. **Review performance**: Win rate > 55%, profit factor > 1.5
3. **Check drawdown**: Max drawdown < 5%
4. **Start small**: Use 10-20% of capital initially
5. **Monitor closely**: Watch first 1-2 hours, then hourly

### During Trading

1. **Monitor dashboard**: Check every 15-30 minutes
2. **Watch risk limits**: Daily loss, drawdown, position count
3. **Be ready to intervene**: Have emergency stop ready
4. **Log issues**: Note any anomalies for post-market review

### After Trading

1. **Review analytics**: Check daily report
2. **Update strategy**: Adjust parameters if needed
3. **Backup data**: Save orders, checkpoints, reports
4. **Plan improvements**: Note issues to fix

---

## Related Documentation

- **[REPO_OVERVIEW.md](./REPO_OVERVIEW.md)**: Repository overview
- **[ARCHITECTURE.md](./ARCHITECTURE.md)**: System architecture
- **[MODULES.md](./MODULES.md)**: Module reference
- **[ENGINES.md](./ENGINES.md)**: Engine documentation
- **[STRATEGIES.md](./STRATEGIES.md)**: Strategy guide
- **[DASHBOARD.md](./DASHBOARD.md)**: Dashboard docs

---

**Last Updated**: 2025-11-19  
**Version**: 1.0
