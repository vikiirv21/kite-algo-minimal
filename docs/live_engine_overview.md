# Live Engine Overview

**Repository:** kite-algo-minimal  
**Target Mode:** LIVE equity trading via Zerodha Kite  
**Generated:** 2025-11-26

---

## Process Architecture: run_session vs live_smoke_test

### Understanding "Multi-Process Layout"

When you run:
```bash
python -m scripts.run_session --mode live --config configs/live.yaml --layout multi
```

The `--layout multi` option means **"one process per engine"**, not "many engines for live". In LIVE mode, the orchestrator deliberately starts **only the `live_equity` engine**.

**Why only one engine in LIVE mode?**

From `scripts/run_session.py`:
```python
if mode == "live":
    engines_to_start = ["live_equity"]  # only this one
    logger.info("LIVE mode: Starting live equity engine only (paper engines skipped)")
```

This is intentional:
- Paper engines don't support live mode
- Only `live_equity` is designed for real trading
- Having paper + live engines would cause conflicts

### Where Multi-Timeframe/Multi-Strategy Lives

All the "multi" behavior happens **inside the single `live_equity` engine**:

1. **Multi-timeframe:** `MarketDataEngineV2` subscribes to `["1m", "5m"]` when `trading.strategy_mode: "multi"`
2. **Multi-strategy:** `StrategyEngineV2` can register both scalping and intraday variants
3. **Single execution pipeline:** `ExecutionEngineV3` + Guardian handle all orders

So even though you see **one process**, inside that process you get:
- Multiple timeframes (1m + 5m)
- Multiple strategy variants (scalp + intraday)
- One unified risk + execution pipeline

### Engine Processes Summary

| Command | Engines Started | Real Orders? |
|---------|-----------------|--------------|
| `run_session --mode live --layout multi` | `live_equity` only | Yes (if `dry_run: false`) |
| `run_session --mode paper --layout multi` | `fno`, `equity`, `options` | No (paper trading) |
| `live_smoke_test` | `live_equity` | **No** (forces `dry_run: true`) |

---

## Trading Sessions & Schedules

### Config: `configs/live.yaml`

```yaml
session:
  market_open_ist: "09:15"
  market_close_ist: "15:30"

trading:
  sessions:
    - { start: "09:15", end: "15:30" }
```

### Session Determination

The engine determines "inside session" vs "outside market hours" in two ways:

1. **`scripts/live_smoke_test.py`** uses `_is_within_trading_session()`:
   - Parses `trading.sessions` from config
   - Compares current IST time against start/end for each session
   - Falls back to `True` if no sessions are configured

2. **`core/market_session.py`** provides `is_market_open()`:
   - Used by `LiveEquityEngine.run_forever()` and `run_smoke_test()`
   - Returns whether the NSE equity market is currently open

### Warmup-Only Mode

When running outside market hours, `live_smoke_test.py`:
- Creates `LiveEquityEngine(cfg, warmup_only=True)`
- Validates Kite session/authentication
- Logs warmup summary (capital, artifacts dir)
- Exits cleanly without starting ticks or strategies

---

## Data & Timeframes

### MarketDataEngineV2 Subscription

From `configs/live.yaml`:

```yaml
data:
  use_mde_v2: true
  feed: "kite"
  timeframes:
    - "1m"
    - "5m"
```

The `LiveEquityEngine.__init__` determines timeframes based on `trading_style`:

| Trading Style | Timeframes Subscribed |
|---------------|----------------------|
| `multi` | `["1m", "5m"]` (scalping + intraday) |
| `scalp` | `["1m"]` (scalping only) |
| `intraday` (default) | `["5m"]` (intraday only) |

### Window Size for Strategies

From `configs/live.yaml`:

```yaml
strategy_engine:
  window_size: 200
  history_lookback: 200
```

`StrategyEngineV2` uses `get_window()` from `MarketDataEngineV2` to retrieve historical candles for indicator computation. Both scalping (1m) and intraday (5m) horizons are supported when `strategy_mode: "multi"`.

---

## Strategies

### Configured Strategies

From `configs/live.yaml`:

```yaml
strategy_engine:
  primary_strategy_id: EMA_20_50
  strategies_v2:
    - id: EMA_20_50
      module: strategies.ema20_50_intraday_v2
      class: EMA2050IntradayV2
      enabled: true
      params:
        timeframe: "5m"
        scalping_timeframe: "1m"
        min_rr: 1.5
        max_risk_per_trade_pct: 0.01
        min_trend_strength: 0.4
        min_confidence: 0.55
```

### Strategy Details

| Strategy ID | Timeframe(s) | Role | Per-Strategy Limits |
|-------------|-------------|------|---------------------|
| `EMA_20_50` | 5m (primary), 1m (scalping) | Dual-mode intraday | `max_trades_per_day: 10`, `max_loss_streak: 3` |

### Conflict Resolution

```yaml
conflict_resolution: "highest_confidence"  # Options: "highest_confidence", "priority", "net_out"
```

---

## Execution & Risk Controls

### ExecutionEngineV3 Configuration

From `configs/live.yaml`:

```yaml
execution:
  engine: v3
  dry_run: true  # Set to false for real orders in LIVE mode
  
  # Trailing stop
  enable_trailing: true
  trail_step_r: 0.5  # Trail step as multiple of initial risk (0.5R)
  
  # Partial exits
  enable_partial_exit: true
  partial_exit_pct: 0.5  # Exit 50% of position on SL breach
  
  # Time-based exit
  enable_time_stop: true
  time_stop_bars: 20  # Close position after N bars if no SL/TP hit
  
  # Hard SL/TP
  # Defined in risk_engine section
```

### Order Placement

`ExecutionEngineV3` places orders via `KiteBroker`:

1. Intent created with strategy signal
2. Position sizer calculates quantity
3. Guardian validates pre-execution (if enabled)
4. `broker.place_order()` → Kite API
5. Order status tracked and reconciled

### TradeGuardian Controls

From `configs/live.yaml`:

```yaml
guardian:
  enabled: true
  max_order_per_second: 5        # Rate limiting
  max_lot_size: 50               # Max quantity per order
  max_daily_drawdown_pct: 3.0    # Block trades if drawdown exceeds 3%
  halt_on_pnl_drop_pct: 5.0      # Halt trading if PnL drops below -5%
  reject_if_price_stale_secs: 3  # Reject if market data older than 3s
  reject_if_slippage_pct: 2.0    # Reject if slippage exceeds 2%
```

### Risk Engine Settings

From `configs/live.yaml`:

```yaml
risk_engine:
  enabled: true
  max_loss_per_trade_pct: 0.01   # 1% max loss per trade
  hard_sl_pct_cap: 0.03          # 3% hard stop loss cap
  hard_tp_pct_cap: 0.06          # 6% hard take profit cap
  trail_start_r: 1.0
  trail_step_r: 0.5
  time_stop_bars: 25
  partial_exit_fraction: 0.5
  enable_partial_exits: true
  enable_trailing: true
  enable_time_stop: true
```

### Circuit Breakers

```yaml
circuit_breakers:
  max_daily_loss_rupees: 5000.0
  max_daily_drawdown_pct: 0.02
  max_trades_per_day: 100
  max_trades_per_strategy_per_day: 50
  max_loss_streak: 5
```

---

## Capital & Limits

### LiveCapitalProvider

**Location:** `core/capital_provider.py`

**How it works:**

1. **Fetches live margins** from Kite API via `kite.margins("equity")`
2. **Returns available cash** from `available.cash` field
3. **Fallback capital** used if broker API fails (from `trading.live_capital` or `paper_capital`)
4. **Cache TTL:** 30 seconds (refreshes at least every 30s)
5. **Forced refresh** on order placement to ensure accurate sizing

### Capital Refresh Timing

- Initial refresh on engine startup
- Every 20 loop iterations (~100 seconds in normal mode)
- After every successful fill
- On-demand before position sizing

### Per-Trade Position Sizing

**Location:** `risk/position_sizer.py` (`DynamicPositionSizer`)

```yaml
portfolio:
  max_exposure_pct: 0.8           # Max 80% of equity in open positions
  max_risk_per_trade_pct: 0.01    # Risk 1% of equity per trade
  position_sizing_mode: "fixed_qty"  # "fixed_qty" or "fixed_risk_atr"
  default_fixed_qty: 1
```

**Sizing logic:**

1. Get current live capital from `LiveCapitalProvider`
2. Calculate equity = capital + unrealized PnL
3. Apply `max_exposure_pct` constraint
4. Apply `max_risk_per_trade_pct` for risk-based sizing
5. Return final quantity (respects `min_order_notional`, `max_order_notional_pct`)

---

## State, Reconciliation & Safety

### StateStore Persistence

**Location:** `core/state_store.py`

**What is persisted:**

| Artifact | Path | Purpose |
|----------|------|---------|
| Checkpoint | `artifacts/checkpoints/live_state_latest.json` | Engine state snapshot |
| Journal | `artifacts/journal/{date}/orders.csv` | Order history |
| Snapshots | `artifacts/snapshots/` | Point-in-time state |
| Runtime Metrics | `artifacts/analytics/runtime_metrics.json` | PnL, equity curve |

### ReconciliationEngine

**Location:** `core/reconciliation_engine.py`

**Configuration:**

```yaml
reconciliation:
  enabled: true
  interval_seconds: 5  # Reconciliation interval
```

**What it does:**

1. **Order reconciliation:** Polls broker orders, syncs status with local state
2. **Position reconciliation:** Compares broker positions vs local tracking
3. **On mismatch:** Currently logs discrepancies (no auto-corrective actions in dry run)

**Integration in `LiveEquityEngine`:**

```python
self.reconciler = ReconciliationEngine(
    execution_engine=recon_exec,
    state_store=self.execution_engine.state_store,
    event_bus=recon_bus,
    kite_broker=self.broker,
    config=cfg.raw,
    mode="LIVE",
    logger_instance=logger,
    capital_provider=self.capital_provider,
)
```

---

## Kite Session & Credentials

### REST Client & WebSocket Ticker

**Credentials source:**

1. Environment variables: `KITE_API_KEY`, `KITE_API_SECRET`, `KITE_ACCESS_TOKEN`
2. Fallback files:
   - `secrets/kite.env` (API key/secret)
   - `secrets/kite_tokens.env` (access token)

**Shared client creation:**

- `LiveCapitalProvider` creates the Kite client via `broker/auth.py`
- Same client reused by `LiveEquityEngine` for session validation
- `KiteTicker` WebSocket created by `KiteBroker.subscribe_ticks()`

### Daily Login

**Command:**

```bash
python -m scripts.run_day --login --engines none
```

This:
1. Opens Kite login URL in browser
2. Completes 2FA authentication
3. Saves access token to `secrets/kite_tokens.env`
4. Tokens expire daily at ~6:00 AM IST

---

## Smoke-Test Behaviour

### Inside Market Hours

When `live_smoke_test.py` runs during trading session:

1. Loads config with safety overrides:
   - `execution.dry_run = True` (forced)
   - `guardian.enabled = True` (forced)
   - `risk_engine.enabled = True` (forced)
2. Creates full `LiveEquityEngine(cfg, warmup_only=False)`
3. Starts `MarketDataEngineV2` and tick subscription
4. Runs `engine.run_smoke_test(max_loops, sleep_seconds)`
5. Strategies generate signals, execution simulated (dry run)
6. Exits after `max_loops` iterations

### Outside Market Hours (Warmup-Only Mode)

When running outside trading session:

1. Detects outside-hours via `_is_within_trading_session()`
2. Creates `LiveEquityEngine(cfg, warmup_only=True)`
3. **Skips:** Universe loading, MDE, strategies, execution wiring
4. **Validates:** Kite session, capital provider
5. Logs warmup summary
6. Exits cleanly (return 0)

---

## Is Tomorrow's Live Dry Run Safe?

### ✅ Recommended Command for Tomorrow (Guaranteed Dry-Run)

**Use the live smoke test** - this is the safest option:

```bash
# Step 1: Login to Kite (once in the morning)
python -m scripts.run_day --login --engines none

# Step 2: Run the smoke test (forces dry_run=True automatically)
python -m scripts.live_smoke_test --config configs/live.yaml --max-loops 60 --sleep-seconds 1.0
```

This will:
- Start the full `LiveEquityEngine`
- Force `execution.dry_run=True` regardless of config
- Run multi-timeframe strategies (1m + 5m)
- Generate signals and log them
- **Never place real orders**

### ⚠️ Do NOT Use This Tomorrow (Unless You Want Real Orders)

```bash
# WARNING: This can place REAL orders if dry_run is false in config!
python -m scripts.run_session --mode live --config configs/live.yaml --layout multi
```

The `run_session` command does NOT force `dry_run=True`. If your config has `execution.dry_run: false`, it **will place real orders**.

### ✅ Order Paths Guarded in Smoke Test

**YES** - All order paths are guarded by `execution.dry_run`:

1. `scripts/live_smoke_test.py` forces `dry_run=True` regardless of config:
   ```python
   cfg.raw["execution"]["dry_run"] = True
   logger.warning("[LIVE-SMOKE] Forcing execution.dry_run=True for safety")
   ```

2. `ExecutionEngineV3` respects `dry_run` flag:
   - When `True`: Orders are simulated, not sent to broker
   - All signals logged but no real Kite API calls

### ⚠️ Code Paths That Could Place Real Orders

**Only if `dry_run=False`:**

- `scripts/run_live_equity.py` - Main production runner
- `scripts/run_session.py --mode live` - Session orchestrator  
- Direct `LiveEquityEngine` instantiation without safety overrides

**The smoke test is safe** because it explicitly forces `dry_run=True`.

### What Would Need to Change for Real Live Trading

1. **Verify capital limits:** Ensure `live_capital` in config matches actual account
2. **Enable all safety gates:**
   - `guardian.enabled: true` ✅ (already in live.yaml)
   - `risk_engine.enabled: true` ✅ (already in live.yaml)
3. **Set `execution.dry_run: false`** in `configs/live.yaml`
4. **Test order cancellation:** Verify cancel orders work correctly
5. **Test position exit:** Verify emergency exit paths
6. **Monitor first session manually:** Watch dashboard and logs closely
7. **Start with minimal quantity:** `default_quantity: 1`

---

## Known Gaps / TODOs

| File | Function/Area | Status |
|------|---------------|--------|
| `engine/live_engine.py` | `_tick_once()` | ✅ Implemented - runs strategy tick, reconciliation, and metrics |
| `engine/live_engine.py` | `_load_learning_tuning()` | ✅ Implemented - loads tuning from learning engine path |
| `engine/live_engine.py` | `_on_tick()` | ✅ Implemented - handles WebSocket ticks, updates last_prices |
| `engine/live_engine.py` | `_apply_learning_adjustments()` | ✅ Implemented - applies learning engine risk multipliers |
| `engine/live_engine.py` | `_save_live_state()` | ✅ Implemented - saves live state checkpoints |
| `core/reconciliation_engine.py` | Mismatch handling | Currently log-only; consider auto-corrective actions |
| `configs/live.yaml` | `execution.dry_run` | Set to `true` by default - must change for real trading |

---

*End of Live Engine Overview*
