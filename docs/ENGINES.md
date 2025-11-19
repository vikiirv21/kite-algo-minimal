# Trading Engines Deep-Dive – kite-algo-minimal

> **Status**: CURRENT – Last updated: 2025-11-19  
> **Purpose**: Comprehensive guide to trading engines, configuration, and runtime behavior

---

## Table of Contents

1. [Engine Overview](#engine-overview)
2. [Equity Paper Engine](#equity-paper-engine)
3. [FnO Paper Engine](#fno-paper-engine)
4. [Options Paper Engine](#options-paper-engine)
5. [Live Engine](#live-engine)
6. [Backtest Engine](#backtest-engine)
7. [Engine Configuration](#engine-configuration)
8. [Multi-Process vs Single-Process](#multi-process-vs-single-process)
9. [State Management](#state-management)
10. [Troubleshooting](#troubleshooting)

---

## Engine Overview

The kite-algo-minimal system has **three specialized paper trading engines** and one **unified live engine**:

| Engine | File | Asset Class | Status |
|--------|------|-------------|--------|
| **Equity Paper Engine** | `engine/equity_paper_engine.py` | Stocks (NIFTY 50/100) | ✅ Production |
| **FnO Paper Engine** | `engine/paper_engine.py` | Index Futures | ✅ Production |
| **Options Paper Engine** | `engine/options_paper_engine.py` | Index Options | ✅ Production |
| **Live Engine** | `engine/live_engine.py` | All (unified) | ⚠️ Use with caution |
| **Backtest Engine** | `backtest/engine_v3.py` | All (offline) | ✅ Production |

### Common Responsibilities

All engines:
1. **Fetch market data** from Kite Connect (historical + LTP)
2. **Evaluate strategies** via StrategyEngine (v2 or v3)
3. **Place orders** via ExecutionEngine v3 (paper or live broker)
4. **Track positions** via PortfolioEngine
5. **Enforce risk limits** via RiskEngine
6. **Persist state** to checkpoints, CSV orders, and snapshots
7. **Publish telemetry** to event bus

---

## Equity Paper Engine

**File**: `engine/equity_paper_engine.py` (1304 lines)

### Purpose

Trades equity stocks from NIFTY 50 and NIFTY 100 indices in paper mode. Simulates realistic fills with configurable slippage.

### Main Loop

```python
while is_market_open():
    # Load universe from scanner output
    universe = load_equity_universe(date.today())
    
    for symbol in universe:
        # 1. Fetch 5-minute candles (last 200)
        df = broker_feed.fetch_historical(symbol, "5minute", lookback=200)
        
        # 2. Calculate indicators
        indicators = strategy_engine.compute_indicators(df)
        
        # 3. Get current position
        position = portfolio_engine.get_position(symbol)
        
        # 4. Evaluate strategy
        intent = strategy_engine.evaluate(symbol, df, position, regime)
        
        if intent.signal != "HOLD":
            # 5. Check risk limits
            if risk_engine.check_entry_allowed(symbol, portfolio):
                # 6. Calculate quantity
                qty = portfolio_engine.calculate_qty(intent, risk_params)
                
                # 7. Place order
                order = execution_engine.place_order(intent, qty)
                
                # 8. Update position (paper fill is instant)
                portfolio_engine.update_position(order)
                
                # 9. Save state
                state_store.save_checkpoint(portfolio_engine.get_state())
    
    # Sleep for tick interval (default: 10 seconds)
    time.sleep(tick_interval)
```

### Configuration

**Universe Configuration** (`configs/dev.yaml`):
```yaml
equity_universe_config:
  mode: "nifty_lists"              # Use NIFTY 50/100 lists
  include_indices: ["NIFTY50", "NIFTY100"]
  max_symbols: 120                 # Soft cap on universe size
  min_price: 100                   # Filter out low-priced stocks
```

**Risk Configuration**:
```yaml
trading:
  paper_capital: 500000            # Starting capital (₹5 lakh)
  max_daily_loss: 3000             # Stop trading if daily loss > ₹3000
  per_symbol_max_loss: 1500        # Stop symbol if loss > ₹1500
  max_loss_pct_per_trade: 0.01     # Max 1% loss per trade
  max_notional_multiplier: 1.0     # Max 1x leverage
  max_open_positions: 5            # Max 5 concurrent positions
```

**Strategy Configuration**:
```yaml
strategy_engine:
  engine: v2                       # Use StrategyEngineV2
  strategies_v2:
    - id: EMA_20_50
      enabled: true
      params:
        timeframe: "5m"
        min_rr: 1.5
        max_risk_per_trade_pct: 0.01
```

### Universe Loading

The engine loads the universe from the scanner output:
```python
universe_path = artifacts/scanner/2025-11-19/universe.json

# Universe JSON format:
{
  "date": "2025-11-19",
  "mode": "nifty_lists",
  "equity_universe": [
    {"symbol": "RELIANCE", "token": 738561, "last_price": 2450.25},
    {"symbol": "TCS", "token": 2953217, "last_price": 3520.50},
    ...
  ],
  "count": 95
}
```

If universe file doesn't exist, engine falls back to hardcoded NIFTY 50 list.

### Orders CSV

Orders are written to:
```
artifacts/orders_equity_paper_2025-11-19.csv
```

CSV format:
```csv
timestamp,order_id,symbol,side,qty,order_type,price,status,filled_qty,avg_fill_price,strategy,reason
2025-11-19 09:30:15,uuid-123,RELIANCE,BUY,10,MARKET,,FILLED,10,2450.25,EMA_20_50,EMA crossover up
```

### Checkpoint

State is saved to:
```
artifacts/checkpoints/runtime_state_latest.json
```

Contains:
- Portfolio equity, realized/unrealized P&L
- Open positions with symbol, qty, avg price, LTP
- Orders count, signals count
- Last updated timestamp

---

## FnO Paper Engine

**File**: `engine/paper_engine.py` (3021 lines)

### Purpose

Trades index futures (NIFTY, BANKNIFTY, FINNIFTY) in paper mode. This is the original engine and is feature-rich but complex.

### Key Features

- **Contract Resolution**: Resolves logical symbols to actual contracts
  - Example: `NIFTY` → `NIFTY25DECFUT` (current month contract)
- **Multi-Timeframe**: Supports multiple timeframes (1m, 5m, 15m)
- **Multi-Strategy**: Can run multiple strategies simultaneously
- **Lot Size Handling**: Uses proper lot sizes (NIFTY=75, BANKNIFTY=30, etc.)

### Configuration

**Universe Configuration**:
```yaml
fno_universe:
  - "NIFTY"
  - "BANKNIFTY"
  - "FINNIFTY"
```

**Lot Sizes** (hardcoded in engine):
```python
LOT_SIZES = {
    "NIFTY": 75,
    "BANKNIFTY": 30,
    "FINNIFTY": 40,
}
```

### Contract Resolution

```python
# Logical symbol → Actual contract
"NIFTY" → "NIFTY25DECFUT"     # Current month
"NIFTY" → "NIFTY25JANFUT"     # Near month (after rollover)

# Resolution logic:
# 1. Fetch NSE FO instruments list
# 2. Filter by underlying (NIFTY)
# 3. Filter by instrument type (FUT)
# 4. Find contract expiring in current/next month
# 5. Return trading symbol
```

### Orders CSV

Orders are written to:
```
artifacts/orders_fno_paper_2025-11-19.csv
```

### Known Issues

- Legacy codebase (3000+ lines)
- Doesn't use ExecutionEngine v3 (uses old paper broker)
- May have different CSV format than equity engine
- Harder to maintain due to complexity

**Note**: Consider migrating to new architecture (ExecutionEngine v3) in future.

---

## Options Paper Engine

**File**: `engine/options_paper_engine.py` (1203 lines)

### Purpose

Trades index options (NIFTY, BANKNIFTY, FINNIFTY) with automatic strike selection.

### Strike Selection Logic

```python
# Example: NIFTY at 21,525, strike interval = 50

# 1. Calculate ATM strike
atm_strike = round(ltp / strike_interval) * strike_interval
# ATM = round(21525 / 50) * 50 = 21,500

# 2. Select strike based on strategy
if signal == "BUY":
    # For bullish trades, buy slightly OTM call
    strike = atm_strike + (strike_interval * otm_distance)
    option_type = "CE"
    # Example: 21,500 + 50 = 21,550 CE
elif signal == "SELL":
    # For bearish trades, buy slightly OTM put
    strike = atm_strike - (strike_interval * otm_distance)
    option_type = "PE"
    # Example: 21,500 - 50 = 21,450 PE

# 3. Construct option symbol
symbol = f"{underlying}{expiry}{strike}{option_type}"
# Example: NIFTY25DEC21550CE
```

### Configuration

**Universe Configuration**:
```yaml
options_underlyings:
  - "NIFTY"
  - "BANKNIFTY"
  - "FINNIFTY"
```

**Options-Specific Risk**:
```yaml
risk:
  atr:
    per_product:
      OPT:
        sl_r_multiple: 1.2         # Tighter stops for options
        tp_r_multiple: 2.2         # Higher profit targets
```

### Strike Intervals

| Underlying | Strike Interval |
|------------|----------------|
| NIFTY | 50 |
| BANKNIFTY | 100 |
| FINNIFTY | 50 |

### Lot Sizes

| Underlying | Lot Size |
|------------|----------|
| NIFTY | 75 |
| BANKNIFTY | 30 |
| FINNIFTY | 40 |

### Orders CSV

Orders are written to:
```
artifacts/orders_options_paper_2025-11-19.csv
```

---

## Live Engine

**File**: `engine/live_engine.py` (820 lines)

### Purpose

Unified live trading engine for all asset classes. Places real orders via Kite Connect.

### Features

- **Real broker integration**: Uses Kite Connect place_order() API
- **Order status polling**: Continuously checks order status until filled
- **Reconciliation**: Matches engine state with broker state every N seconds
- **Error handling**: Retries on transient errors, logs permanent failures
- **Circuit breakers**: Strict enforcement of risk limits

### Safety Checks

**Pre-Trade Checks**:
1. Token validity (fail if token expired)
2. Rate limiting (max orders per second)
3. Position limits (max open positions)
4. Capital limits (max exposure)
5. Circuit breaker (daily loss, drawdown)

**Post-Trade Reconciliation**:
- Every 5 seconds, fetch positions from broker
- Compare with engine state
- Log discrepancies
- Auto-correct if possible

### Configuration

**Execution Configuration**:
```yaml
execution:
  use_execution_engine_v2: true    # Use ExecutionEngine v3
  dry_run: false                   # Set to true for dry-run mode
  circuit_breakers:
    max_daily_loss_rupees: 5000.0
    max_daily_drawdown_pct: 0.02
    max_trades_per_day: 100
    max_loss_streak: 5
```

**Reconciliation**:
```yaml
reconciliation:
  enabled: true
  interval_seconds: 5              # Reconcile every 5 seconds
```

### Usage

```bash
# CAUTION: This places real orders!
python -m scripts.run_session --mode live --config configs/dev.yaml
```

**Important**: Always test thoroughly in paper mode first. Start with small position sizes. Monitor closely during live trading.

---

## Backtest Engine

**File**: `backtest/engine_v3.py` (800 lines)

### Purpose

Offline backtesting on historical data. Reuses live/paper components for consistency.

### Features

- **Completely offline**: No broker connection required
- **Historical data**: Uses CSV or local data files
- **Same components**: Reuses StrategyEngine, PortfolioEngine, RiskEngine
- **Structured output**: JSON reports for analytics
- **Fast execution**: No rate limits, instant "fills"

### Usage

```bash
python -m scripts.run_backtest_v3 \
    --config configs/dev.yaml \
    --symbols NIFTY,BANKNIFTY \
    --start 2025-01-01 \
    --end 2025-01-05 \
    --data-source csv
```

### Output

```
artifacts/backtests/backtest_20251119_143000/
├── config.json          # Backtest configuration
├── summary.json         # Performance summary
├── trades.csv           # All trades
├── equity_curve.csv     # Equity over time
└── logs/                # Detailed logs
```

### Configuration

**Backtest-Specific Config** (`configs/backtest.dev.yaml`):
```yaml
backtest:
  data_source: "csv"               # "csv" or "kite"
  csv_data_dir: "artifacts/history"
  initial_capital: 500000
  commission_per_trade: 20.0
  slippage_bps: 5.0
```

---

## Engine Configuration

### Common Config Parameters

All engines share these configuration sections:

#### Trading Parameters

```yaml
trading:
  mode: "paper"                    # "paper" or "live"
  default_product: "MIS"           # "MIS" or "NRML"
  default_quantity: 1
  paper_capital: 500000
  max_daily_loss: 3000
  per_symbol_max_loss: 1500
  max_open_positions: 5
```

#### Data Parameters

```yaml
data:
  source: "broker"                 # Always "broker" for now
  timeframe: "5minute"             # Base timeframe
  history_lookback: 50             # Candles for indicators
```

#### Strategy Engine

```yaml
strategy_engine:
  engine: v2                       # "v2" or "v3"
  version: 2
  enabled: true
  primary_strategy_id: EMA_20_50
  
  strategies_v2:
    - id: EMA_20_50
      enabled: true
      params:
        timeframe: "5m"
        min_rr: 1.5
```

#### Risk Engine

```yaml
risk_engine:
  enabled: false                   # Usually disabled (Portfolio handles risk)
  max_loss_per_trade_pct: 0.01
  take_profit_r: 2.0
  enable_trailing: true
```

#### Portfolio Engine

```yaml
portfolio:
  max_leverage: 2.0
  max_exposure_pct: 0.8
  max_risk_per_trade_pct: 0.01
  position_sizing_mode: "fixed_qty"
  default_fixed_qty: 1
```

#### Regime Engine

```yaml
regime_engine:
  enabled: true
  bar_period: "1m"
  slope_period: 20
  atr_period: 14
```

#### Trade Guardian

```yaml
guardian:
  enabled: false
  max_order_per_second: 5
  max_lot_size: 50
  reject_if_price_stale_secs: 3
```

---

## Multi-Process vs Single-Process

### Single-Process Mode (Default)

**Command**:
```bash
python -m scripts.run_session --mode paper --config configs/dev.yaml
```

**Architecture**:
- All engines run as threads in one Python process
- Shared memory for state
- Dashboard as separate uvicorn process (port 9000)

**Advantages**:
- Simple debugging
- Fast inter-engine communication
- Easy state sharing

**Disadvantages**:
- Python GIL limits CPU parallelism
- One engine crash affects all
- Memory not isolated

### Multi-Process Mode

**Command**:
```bash
python -m scripts.run_session --mode paper --config configs/dev.yaml --layout multi
```

**Architecture**:
- Each engine runs as separate Python process
- IPC via files (future: Redis/message queue)
- Dashboard as separate process

**Advantages**:
- True parallelism (no GIL)
- Process isolation
- Scales better

**Disadvantages**:
- More complex IPC
- State sync overhead
- Harder debugging

### Individual Engine Mode

**Commands**:
```bash
# Run equity engine only
python -m apps.run_equity_paper --config configs/dev.yaml --mode paper

# Run FnO engine only
python -m apps.run_fno_paper --config configs/dev.yaml --mode paper

# Run options engine only
python -m apps.run_options_paper --config configs/dev.yaml --mode paper
```

**Use Cases**:
- Testing single engine
- Debugging specific issues
- Running only one asset class

---

## State Management

### Checkpoint Files

**Location**: `artifacts/checkpoints/`

**Files**:
- `runtime_state_latest.json`: Current session state (all engines)
- `paper_state_latest.json`: Paper broker state (deprecated)

**Format**:
```json
{
  "session_id": "2025-11-19-equity-paper",
  "mode": "paper",
  "start_time": "2025-11-19T09:15:00+05:30",
  "portfolio": {
    "equity": 500000.0,
    "realized_pnl": 1250.50,
    "unrealized_pnl": -320.00,
    "total_pnl": 930.50,
    "exposure": 245000.00,
    "margin_used": 0.0
  },
  "positions": [
    {
      "symbol": "RELIANCE",
      "qty": 10,
      "avg_price": 2450.25,
      "ltp": 2462.00,
      "unrealized_pnl": 117.50
    }
  ],
  "orders_count": 25,
  "signals_count": 48,
  "last_updated": "2025-11-19T14:30:00+05:30"
}
```

### Orders CSV

**Location**: `artifacts/orders_<engine>_<date>.csv`

**Examples**:
- `orders_equity_paper_2025-11-19.csv`
- `orders_fno_paper_2025-11-19.csv`
- `orders_options_paper_2025-11-19.csv`

**Format**: See "Orders CSV" sections above for each engine

### Snapshots

**Location**: `artifacts/snapshots/positions_<timestamp>.json`

**Purpose**: Periodic position snapshots for analytics

**Frequency**: Every 5 minutes (configurable)

---

## Troubleshooting

### Engine Won't Start

**Symptoms**: Engine exits immediately or logs "Token invalid"

**Solutions**:
1. Check token validity:
   ```bash
   python -m scripts.login_kite
   ```
2. Verify secrets files exist:
   ```bash
   ls -la secrets/kite.env
   ls -la secrets/kite_tokens.env
   ```
3. Check config file path:
   ```bash
   cat configs/dev.yaml
   ```

### No Trades / Only HOLD Signals

**Symptoms**: Engine runs but never places orders

**Possible Causes**:
1. **Indicators not ready**: Insufficient history
   - Check: `history_lookback` in config (should be ≥ 200 for EMA strategies)
2. **Risk limits exceeded**: Daily loss or position limits hit
   - Check: `max_daily_loss`, `max_open_positions` in config
3. **Regime mismatch**: Strategy requires specific regime
   - Check: Regime engine logs for current regime
4. **Strategy disabled**: Strategy not enabled in config
   - Check: `strategies_v2` section, ensure `enabled: true`

**Debugging**:
```bash
# Check logs
tail -f artifacts/logs/equity_paper_engine.log

# Check signals
cat artifacts/signals.csv | grep -v HOLD

# Check orders
cat artifacts/orders_equity_paper_$(date +%Y-%m-%d).csv
```

### Orders Not Filling (Live Mode)

**Symptoms**: Orders placed but never fill

**Possible Causes**:
1. **Invalid order parameters**: Price/qty out of range
2. **Insufficient margin**: Not enough capital
3. **Market closed**: Outside trading hours
4. **Symbol not tradeable**: Suspended or circuit filter

**Debugging**:
```bash
# Check order status via Kite web
# https://kite.zerodha.com/orders

# Check reconciliation logs
grep "reconciliation" artifacts/logs/live_engine.log
```

### High Slippage

**Symptoms**: Fill prices far from expected

**Causes**:
1. **Low liquidity**: Wide bid-ask spread
2. **High volatility**: Price moving fast
3. **Large order size**: Moving the market

**Solutions**:
1. Use LIMIT orders instead of MARKET
2. Trade more liquid symbols
3. Reduce position size
4. Avoid trading at open/close

### Memory Issues

**Symptoms**: Engine slows down or crashes after hours

**Causes**:
1. **Memory leak**: Accumulating data in memory
2. **Large history**: Too many candles cached

**Solutions**:
1. Restart engine periodically
2. Reduce `history_lookback`
3. Use multi-process mode (better isolation)

---

## Related Documentation

- **[REPO_OVERVIEW.md](./REPO_OVERVIEW.md)**: Repository overview
- **[ARCHITECTURE.md](./ARCHITECTURE.md)**: System architecture
- **[MODULES.md](./MODULES.md)**: Module reference
- **[STRATEGIES.md](./STRATEGIES.md)**: Strategy guide
- **[DASHBOARD.md](./DASHBOARD.md)**: Dashboard docs
- **[RUNBOOKS.md](./RUNBOOKS.md)**: Operational runbook

---

**Last Updated**: 2025-11-19  
**Version**: 1.0
