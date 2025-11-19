# HFT System Architecture – kite-algo-minimal

> **Status**: PARTIALLY STALE – Last validated: 2025-11-17  
> **Superseded by**: [docs/ARCHITECTURE.md](./ARCHITECTURE.md) for canonical architecture documentation  
> **Note**: This document is detailed but some information may be outdated. ARCHITECTURE.md is the current canonical reference.

**High-Level Trading System for Equity, FnO Futures, and Options**

This document describes the architecture of the kite-algo-minimal algorithmic trading system, covering both paper trading (simulation) and live trading modes. The system is designed to handle multiple asset classes (Equity, FnO Futures, Options) with a modular, extensible architecture.

---

## Changelog (Latest Refinements)

**2025-11-17 – Architecture refinement v2 - All requested improvements completed:**

- **✅ Added "Component Status" section** to clarify which components exist vs. planned/WIP
  - Verified all major components exist: scripts, engines, core modules, and docs
  - Explicitly marked live options/equity trading and multi-process architecture as WIP/planned
- **✅ Added "Current vs Future" subsection** in "Process & Concurrency Model"
  - CURRENT: All engines run as threads in single process, dashboard as separate uvicorn
  - FUTURE: Multi-process with message queue/Redis for IPC
  - Added performance considerations explaining I/O-bound workload and GIL implications
- **✅ Verified "Data Validation & Fault Tolerance" section** (already complete)
  - Documents behavior when LTP fetch fails or returns None
  - Documents behavior when indicators are not ready (insufficient history)
  - Shows implementation patterns with code examples
  - References specific TypeError runtime errors now prevented
  - Confirms analytics layer guardrails (only log signals with valid numeric price)
- **✅ Verified "Debugging & Observability" section** (already complete)
  - Documents debugging no-trade scenarios (only HOLD signals)
  - Documents debugging per-symbol errors
  - Explains using signals.csv, orders.csv, JSON event logs, and engine logs
  - Documents optional LOG_REASON_FOR_HOLD flag for deep debugging
- **✅ Verified "Universe and Instruments" equity section** (already accurate)
  - Explicitly mentions NIFTY 50 and NIFTY 100 restriction with min_price filter
  - Documents scanner output structure with equity_universe key
  - Explains equity engine only loops over filtered universe
  - Shows actual file naming: artifacts/scanner/YYYY-MM-DD/universe.json

**Previous Updates (2025-11-17):**

- **Step 1**: Validated module existence. All referenced modules exist and are operational.
- **Step 2**: Added **"Data Validation & Fault Tolerance"** section explaining how system handles None/missing LTP and indicator values.
- **Step 3**: Clarified **Process & Concurrency Model** – dashboard runs as separate uvicorn process on port 8765, not in-process.
- **Step 4**: Tightened **"Universe and Instruments"** section with explicit NIFTY 50/100 filtering logic and scanner output structure.
- **Step 5**: Added **"Debugging & Observability"** section with guidance on using signals.csv, orders.csv, and logs for troubleshooting.
- **Step 6**: Removed speculative "Planned / Future Work" items that were not explicitly requested; kept only validated, existing architecture.

---

## Component Status

All components, scripts, and documentation files referenced in this architecture document are **currently implemented and operational** in the codebase:

**✅ Existing Scripts:**
- `scripts/run_trader.py` - Main entry point for paper/live trading
- `scripts/run_day.py` - Engine orchestration and management
- `scripts/run_all.py` - Convenience script to start all services

**✅ Existing Applications:**
- `apps/dashboard.py` - Dashboard backend (also `ui/dashboard.py`)
- All trading engines: `engine/paper_engine.py`, `engine/equity_paper_engine.py`, `engine/options_paper_engine.py`, `engine/live_engine.py`

**✅ Existing Core Modules:**
- `backtest/engine_v3.py` - Backtest engine v3 (integration into daily workflow is ongoing)
- All strategy, risk, portfolio, and market data engines

**✅ Existing Documentation:**
- `docs/Commands.md` - Command reference
- `docs/Dashboard.md` - Dashboard features and API
- `docs/Strategies.md` - Strategy development guide
- `docs/RiskEngine.md` - Risk configuration and guardrails

**⚠️ Partially Implemented / WIP:**
- **Live Options Trading**: Options engine exists in paper mode only (`engine/options_paper_engine.py`). Live options engine not yet implemented.
- **Live Equity Trading**: Equity engine exists in paper mode only (`engine/equity_paper_engine.py`). Live equity engine not yet implemented.
- **Multi-Process Architecture**: Currently single-process with threads. Multi-process separation is planned for future.
- **Backtest Integration**: `backtest/engine_v3.py` exists but not yet integrated into `run_trader.py` workflow.

**Note**: The "Future Extensions" section at the end of this document describes enhancements that are planned but not yet implemented.

---

## Table of Contents

1. [Component Status](#component-status)
2. [High-Level Overview](#high-level-overview)
3. [Process & Concurrency Model](#process--concurrency-model)
4. [Engines and Responsibilities](#engines-and-responsibilities)
5. [Data Validation & Fault Tolerance](#data-validation--fault-tolerance)
6. [Strategy, Risk, and Portfolio Engines](#strategy-risk-and-portfolio-engines)
7. [Paper vs Live Modes](#paper-vs-live-modes)
8. [State, Journals, and Analytics](#state-journals-and-analytics)
9. [Dashboard Integration](#dashboard-integration)
10. [Universe and Instruments](#universe-and-instruments)
11. [Entry Points and Commands](#entry-points-and-commands)
12. [Debugging & Observability](#debugging--observability)
13. [Future Extensions](#future-extensions)

---

## High-Level Overview

The kite-algo-minimal system is a modular HFT/algo-trading platform that:

- **Trades multiple asset classes**: NSE Equity, FnO Futures (NIFTY, BANKNIFTY, FINNIFTY), Index Options
- **Supports paper and live modes**: Paper mode simulates fills with live market data; live mode places real orders via Zerodha Kite API
- **Runs in a multi-threaded architecture**: Each engine (Equity, FnO, Options) runs in its own thread within a single orchestrator process
- **Uses a shared state store**: All engines share checkpoints, journals, and runtime state for coordination
- **Provides a web dashboard**: FastAPI-based dashboard for monitoring positions, PnL, signals, and orders
- **Enforces risk guardrails**: Max daily loss, per-symbol loss limits, position sizing, trade throttling

**Key Components:**
- **Entry Scripts**: `scripts/run_trader.py`, `scripts/run_day.py`, `scripts/run_all.py`
- **Trading Engines**: `engine/paper_engine.py`, `engine/equity_paper_engine.py`, `engine/options_paper_engine.py`, `engine/live_engine.py`
- **Core Modules**: `core/strategy_engine_v2.py`, `core/risk_engine.py`, `core/portfolio_engine.py`, `core/market_data_engine.py`, `core/state_store.py`
- **Broker Integration**: `broker/paper_broker.py`, `broker/live_broker.py`, `broker/kite_bridge.py`
- **Analytics**: `analytics/trade_recorder.py`, `analytics/trade_journal.py`, `analytics/performance.py`
- **Dashboard**: `apps/dashboard.py`, `ui/dashboard.py`

---

## Process & Concurrency Model

### Current Model (Multi-Threaded)

The system currently runs as a **single main process** with **multiple daemon threads**, one per engine.

```
┌─────────────────────────────────────────────────────────────────┐
│                      Main Process (Python)                       │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │              scripts/run_trader.py (Entrypoint)            │ │
│  │                          ↓                                  │ │
│  │              scripts/run_day.py (Engine Manager)           │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │  FnO Engine     │  │  Options Engine │  │  Equity Engine  │ │
│  │  (Thread)       │  │  (Thread)       │  │  (Thread)       │ │
│  │                 │  │                 │  │                 │ │
│  │ PaperEngine     │  │ OptionsPaper    │  │ EquityPaper     │ │
│  │ or LiveEngine   │  │ Engine          │  │ Engine          │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │         Reconciliation Engine (Thread, if enabled)       │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │         Shared State Store (checkpoints, journals)       │   │
│  └──────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│              Dashboard Process (Separate uvicorn)                │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │          FastAPI App (ui/dashboard.py)                   │   │
│  │  Started via: uvicorn ui.dashboard:app --port 8765      │   │
│  │  Reads: checkpoints, journals, logs                      │   │
│  │  Serves: Web UI on http://localhost:8765                 │   │
│  └──────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────────┘
```

**Today's Architecture:**
- **All trading engines (FnO, Options, Equity)** run as threads inside a single process started by `scripts/run_day.py` or `scripts/run_trader.py`.
- **The dashboard runs as a separate uvicorn process** using `uvicorn ui.dashboard:app --port 8765`.
- Engines communicate via shared in-memory state and file-based journals/checkpoints.

### Current vs Future Architecture

**CURRENT (Multi-Threaded, Single Process):**
- All trading engines (FnO, Options, Equity) run as threads inside a single process (`scripts/run_trader.py` / `scripts/run_day.py`)
- Dashboard runs as a separate uvicorn process using `uvicorn ui.dashboard:app --port 8765`
- Engines communicate via shared in-memory state and file-based journals/checkpoints

**FUTURE (Multi-Process with IPC):**
- Separate processes per engine (FnO, Options, Equity)
- Message queue or Redis for inter-process communication (IPC)
- Each engine can run independently on same or different machines
- Improved isolation and fault tolerance

### Performance Considerations

**For now, most work is IO-bound** on broker API calls and data fetches, so multi-threading is sufficient:
- Threads wait on network I/O (Kite API, WebSocket) without blocking each other
- Python's GIL (Global Interpreter Lock) is not a bottleneck for I/O-heavy workloads
- Shared memory allows fast access to checkpoints, state, and configuration

**Multi-process separation is planned mainly for:**
- **Live vs paper isolation**: Run live and paper engines in separate processes to prevent accidental interference
- **Heavy backtests**: CPU-intensive backtests can run in parallel using multiple cores
- **Resilience**: One engine crash doesn't kill others
- **Resource limits**: Set per-engine memory/CPU caps

---

## Engines and Responsibilities

The system is organized into three primary trading engines, each handling a specific asset class.

### 1. FnO Futures Engine

**Module**: `engine/paper_engine.py` (paper mode), `engine/live_engine.py` (live mode)

**Responsibilities:**
- Trade FnO futures contracts (NIFTY, BANKNIFTY, FINNIFTY current month/next month)
- Fetch LTP (Last Traded Price) from Kite for futures contracts
- Resolve logical symbols (e.g., "NIFTY") to actual trading symbols (e.g., "NIFTY25JANFUT")
- Run strategies (e.g., `FnoIntradayTrendStrategy`, `EMA2050IntradayV2`) on futures prices
- Place orders via `PaperBroker` (paper mode) or `KiteBroker` (live mode)
- Enforce per-symbol loss limits (kill switch)
- Record signals and orders to journals

**Key Modules:**
- Market data: `data/broker_feed.py`, `core/market_data_engine.py`
- Strategy: `strategies/fno_intraday_trend.py`, `core/strategy_engine_v2.py`
- Execution: `broker/execution_router.py`, `broker/paper_broker.py`, `broker/kite_bridge.py`
- Journaling: `analytics/trade_recorder.py`

**Data Flow:**
```
Kite API → BrokerFeed → FnO Engine → StrategyEngine → RiskEngine → 
PortfolioEngine → ExecutionRouter → PaperBroker/LiveBroker → 
TradeRecorder → orders.csv, signals.csv
```

---

### 2. Options Engine

**Module**: `engine/options_paper_engine.py`

**Responsibilities:**
- Trade index options (NIFTY, BANKNIFTY, FINNIFTY)
- Use underlying futures LTP as a proxy for spot price
- Resolve ATM (At-The-Money) Call and Put options on nearest expiry
- Run strategies on option prices (reusing `FnoIntradayTrendStrategy` or custom option strategies)
- Place paper orders via `PaperBroker`
- Enforce per-symbol loss limits
- Record signals and orders to journals

**Key Modules:**
- Options universe: `data/options_instruments.py`
- Market data: `data/broker_feed.py`
- Strategy: `strategies/fno_intraday_trend.py`
- Execution: `broker/execution_router.py`, `broker/paper_broker.py`

**Data Flow:**
```
Kite API → Futures LTP (spot proxy) → OptionUniverse → Resolve ATM CE/PE → 
OptionsEngine → StrategyEngine → RiskEngine → PaperBroker → TradeRecorder
```

**Note**: Live options trading is not yet implemented. The options engine currently only runs in paper mode.

---

### 3. Equity Engine

**Module**: `engine/equity_paper_engine.py`

**Responsibilities:**
- Trade NSE equity stocks (constrained to NIFTY 50/100 for quality)
- Fetch LTP from NSE via Kite for equity symbols (e.g., RELIANCE, TCS, INFY)
- Run strategies (e.g., `FnoIntradayTrendStrategy`) on equity prices
- Place paper orders via `PaperBroker`
- Enforce per-symbol loss limits (kill switch)
- Record signals and orders to journals
- Tag trades as "EQ_<SYMBOL>|<STRATEGY_ID>" for analytics

**Key Modules:**
- Universe: `core/universe.py`, `core/universe_builder.py`
- Market data: `data/broker_feed.py`
- Strategy: `strategies/fno_intraday_trend.py`
- Execution: `broker/execution_router.py`, `broker/paper_broker.py`

**Data Flow:**
```
Kite API → BrokerFeed → Equity symbols → EquityEngine → StrategyEngine → 
RiskEngine → PaperBroker → TradeRecorder → orders.csv, signals.csv
```

**Note**: Live equity trading is not yet implemented. The equity engine currently only runs in paper mode.

---

## Data Validation & Fault Tolerance

The system is designed to handle missing or invalid market data gracefully without crashing. This is critical for production reliability.

### Common Runtime Issues (Now Prevented)

Previously, the system encountered runtime errors like:
- `TypeError: float() argument must be a string or a real number, not 'NoneType'`
- `TypeError: '>' not supported between instances of 'NoneType' and 'NoneType'`

These occurred when:
1. **LTP fetch fails or returns None** (e.g., `KeyError` in `data.broker_feed`, symbol not found in Kite response)
2. **Indicators like ema20, ema50 are not ready yet** (insufficient historical data for calculation)

### Design Principles

**Engines must skip processing for a symbol/timeframe when:**
- `price is None` (LTP fetch failed)
- Required indicators are `None` (not enough history)

**Instead of crashing, the system must:**
1. **Log the reason** (structured event: `ltp_missing`, `indicators_not_ready`)
2. **Skip the symbol for this tick** (continue processing other symbols)
3. **Return early** from the strategy evaluation loop

### Implementation Pattern

**In Market Data Layer (`data/broker_feed.py`):**
- `get_ltp()` returns `None` when symbol not found or API fails
- Logs warning once per symbol to avoid log spam
- Does not raise exceptions (graceful degradation)

**In Engine Layer (e.g., `engine/equity_paper_engine.py`):**
```python
ltp = self.broker_feed.get_ltp(symbol, exchange="NSE")
if ltp is None:
    logger.warning("Skipping %s: LTP not available (ltp_missing)", symbol)
    continue  # Skip to next symbol
```

**In Strategy Layer (`core/strategy_engine_v2.py`):**
```python
indicators = self.get_indicators(symbol, timeframe)
if indicators.get("ema20") is None or indicators.get("ema50") is None:
    logger.debug("Skipping %s: Indicators not ready (indicators_not_ready)", symbol)
    return OrderIntent(signal="HOLD", reason="indicators_not_ready")
```

### Analytics Layer Guardrails

**`analytics/trade_recorder.log_signal()` and `log_order()` must only be called with valid numeric price:**

```python
# Before logging signal
if price is None:
    logger.warning("Cannot log signal for %s: price is None", symbol)
    return  # Do not log

# Log signal
recorder.log_signal(
    symbol=symbol,
    price=float(price),  # Guaranteed non-None here
    signal="LONG",
    # ... other fields
)
```

### Structured Event Logging

The system uses structured JSON event logging (`core/json_log.py`, `core/event_logging.py`) to record:
- `ltp_fetch_error`: When LTP fetch fails for a symbol
- `indicators_not_ready`: When indicators are insufficient
- `risk_blocked`: When risk engine rejects a trade
- `hold_decision`: When strategy decides to HOLD with reason

**Example JSON event:**
```json
{
  "timestamp": "2025-11-17T09:30:00Z",
  "event": "ltp_fetch_error",
  "symbol": "RELIANCE",
  "exchange": "NSE",
  "reason": "symbol_not_found_in_kite_response"
}
```

These events are written to `artifacts/logs/events.jsonl` and can be queried for debugging.

---

## Strategy, Risk, and Portfolio Engines

These core engines are **shared across all asset classes** and handle strategy logic, risk checks, and position sizing.

### Strategy Engine v2

**Module**: `core/strategy_engine_v2.py`

**Responsibilities:**
- Execute trading strategies on market data
- Generate signals: `OrderIntent` objects (BUY, SELL, EXIT)
- Maintain per-strategy state (`StrategyState`)
- Support multiple strategies per symbol (conflict resolution via highest confidence, priority, or net-out)
- Integrate with unified indicators (`core/indicators.py`)

**Example Strategies:**
- `strategies/fno_intraday_trend.py`: Trend-following on 5-min bars
- `strategies/ema20_50_intraday_v2.py`: EMA crossover strategy

**Config**: `configs/dev.yaml` → `strategy_engine` section

---

### Risk Engine

**Module**: `core/risk_engine.py`

**Responsibilities:**
- Enforce risk guardrails on every trade
- Check max daily loss, max positions, per-symbol limits
- Return `RiskDecision`: `ALLOW`, `BLOCK`, `REDUCE`, or `HALT_SESSION`
- Integrate with state store for daily PnL tracking

**Key Rules:**
- `max_daily_loss`: Stop trading when daily PnL <= threshold
- `max_positions_total`: Limit total open positions
- `max_trades_per_symbol_per_day`: Prevent over-trading a single symbol
- `per_symbol_max_loss`: Kill switch for individual symbols

**Config**: `configs/dev.yaml` → `risk` section

---

### Portfolio Engine

**Module**: `core/portfolio_engine.py`

**Responsibilities:**
- Calculate position sizes based on:
  - Account equity
  - Per-strategy capital budgets
  - Risk per trade (e.g., 1% of equity)
  - ATR-based volatility sizing (optional)
- Enforce leverage limits (`max_leverage: 2.0`)
- Enforce exposure limits (`max_exposure_pct: 0.8`)

**Config**: `configs/dev.yaml` → `portfolio` section

---

### Market Data Engine

**Module**: `core/market_data_engine.py`, `core/market_data_engine_v2.py`

**Responsibilities:**
- Fetch live LTP (Last Traded Price) from Kite
- Build intraday candles (1m, 5m, 15m, etc.) from ticks
- Provide historical data for indicator calculation
- Cache market data to `artifacts/market_data/`

**Data Sources:**
- Live: Kite WebSocket or REST API
- Replay: Historical CSV data for backtesting

**Config**: `configs/dev.yaml` → `data` section

---

## Paper vs Live Modes

The system supports two trading modes: **paper** (simulation) and **live** (real orders).

### Paper Mode

**Purpose**: Simulate trading with live market data but **no real orders**

**How it works:**
1. Uses live market data from Kite (LTP, quotes, candles)
2. Simulates fills immediately at market price (with optional slippage)
3. Tracks paper positions and PnL in `broker/paper_broker.py`
4. Records orders and fills to journals (`artifacts/orders.csv`, `artifacts/signals.csv`)
5. Checkpoints state to `artifacts/checkpoints/paper_state_latest.json`

**Entry Command:**
```bash
python -m scripts.run_trader paper
```

**Config**: `configs/dev.yaml` → `trading.mode: "paper"`

**Advantages:**
- Risk-free testing of strategies
- Fast iteration without real money
- Realistic market data (not historical replay)

---

### Live Mode

**Purpose**: Place **real orders** via Zerodha Kite API

**How it works:**
1. Uses live market data from Kite
2. Places real orders via `broker/kite_bridge.py` → Kite API
3. Waits for order fills from Kite (via WebSocket or polling)
4. Tracks real positions and PnL from broker
5. Enforces additional guardrails (max daily loss, kill switch, preflight checks)

**Entry Command:**
```bash
python -m scripts.run_trader live --config configs/live.yaml
```

**Config**: `configs/live.yaml` → `trading.mode: "live"` (requires explicit config for safety)

**Safety Features:**
- Preflight token check before starting engines
- Max daily loss circuit breaker
- Per-symbol loss kill switch
- Position reconciliation with broker (every 5 seconds)

**Shared Components:**
Both paper and live modes use the **same**:
- Strategy Engine (`core/strategy_engine_v2.py`)
- Risk Engine (`core/risk_engine.py`)
- Portfolio Engine (`core/portfolio_engine.py`)
- Market Data Engine (`core/market_data_engine.py`)

**Divergence Point:**
- **Paper**: `broker/paper_broker.py` → simulated fills
- **Live**: `broker/kite_bridge.py` → real Kite API calls

---

### How run_trader.py and run_day.py Decide Between Paper and Live

**scripts/run_trader.py** (Canonical Entrypoint):
- Accepts `mode` argument: `paper` or `live`
- Defaults to `configs/dev.yaml` for paper mode
- **Requires explicit `--config`** for live mode (safety)
- Delegates to `scripts/run_day.py` for actual engine orchestration

**scripts/run_day.py** (Engine Manager):
- Reads `trading.mode` from config file (`configs/dev.yaml` or `configs/live.yaml`)
- CLI `--mode` flag can override config
- Instantiates engines based on mode:
  - Paper: `PaperEngine`, `EquityPaperEngine`, `OptionsPaperEngine`
  - Live: `LiveEngine` (only FnO futures currently)
- Starts engines in daemon threads
- Monitors engines with heartbeat loop

---

## State, Journals, and Analytics

The system maintains persistent state across runs using **checkpoints** and **journals**.

### Checkpoints

**Module**: `core/state_store.py`

**Purpose**: Snapshot of runtime state (positions, equity, PnL, universe)

**Files:**
- `artifacts/checkpoints/paper_state_latest.json` (paper mode)
- `artifacts/checkpoints/live_state_latest.json` (live mode)
- `artifacts/checkpoints/runtime_state_latest.json` (shared runtime state)

**Structure:**
```json
{
  "mode": "paper",
  "equity": {
    "paper_capital": 500000,
    "cash": 498500,
    "realized_pnl": -1500,
    "unrealized_pnl": 200,
    "day_pnl": -1300
  },
  "positions": [
    {
      "symbol": "NIFTY25JANFUT",
      "quantity": 50,
      "avg_price": 24500,
      "realized_pnl": -200
    }
  ],
  "open_orders": [],
  "strategies": {
    "ema20_50_intraday": {
      "day_pnl": -500,
      "open_trades": 1,
      "win_trades": 0,
      "loss_trades": 1
    }
  },
  "universe": {
    "date": "2025-11-17",
    "fno": ["NIFTY", "BANKNIFTY", "FINNIFTY"]
  },
  "last_heartbeat_ts": "2025-11-17T09:30:00Z"
}
```

**Recovery**: On startup, engines load the checkpoint to restore positions and state from previous runs.

---

### Journals

**Modules**: `analytics/trade_recorder.py`, `analytics/trade_journal.py`

**Purpose**: Append-only logs of signals, orders, and fills

**Files:**
- `artifacts/orders.csv`: All orders (paper or live)
- `artifacts/signals.csv`: All strategy signals
- `artifacts/pnl.csv`: Trade PnL summaries (if enabled)

**orders.csv Schema:**
```csv
timestamp,symbol,side,quantity,price,status,tf,profile,strategy,parent_signal_timestamp,underlying,extra
2025-11-17T09:30:00Z,NIFTY25JANFUT,BUY,50,24500,FILLED,5m,INTRADAY,ema20_50_intraday,2025-11-17T09:29:00Z,NIFTY,{}
```

**signals.csv Schema:**
```csv
timestamp,signal_id,logical,symbol,price,signal,tf,reason,profile,mode,confidence,trend_context,vol_regime,htf_trend,playbook,setup_type,ema20,ema50,ema100,ema200,rsi14,atr,adx14,adx,vwap,rel_volume,vol_spike,strategy
2025-11-17T09:29:00Z,abc123,NIFTY,NIFTY25JANFUT,24500,LONG,5m,EMA20>EMA50,INTRADAY,paper,0.85,UPTREND,NORMAL,BULLISH,TREND_FOLLOW,BREAKOUT,24450,24400,24300,24200,65,50,25,25,24450,1.2,false,ema20_50_intraday
```

**Replay**: The `JournalStateStore` can rebuild paper state from journal entries (`rebuild_from_journal()`).

---

### Scanner Outputs

**Module**: `core/scanner.py`

**Purpose**: Pre-market universe selection based on indicators

**Files:**
- `artifacts/scanner/YYYY-MM-DD/universe.json`

**Example:**
```json
{
  "date": "2025-11-17",
  "asof": "2025-11-17T08:00:00Z",
  "fno": ["NIFTY", "BANKNIFTY", "FINNIFTY"],
  "meta": {
    "NIFTY": {
      "tradingsymbol": "NIFTY25JANFUT",
      "instrument_token": 12345678,
      "lot_size": 50
    },
    "BANKNIFTY": {
      "tradingsymbol": "BANKNIFTY25JANFUT",
      "instrument_token": 87654321,
      "lot_size": 15
    }
  }
}
```

**Usage**: Engines load the daily scanner output on startup to determine which symbols to trade.

---

## Dashboard Integration

The dashboard provides real-time monitoring of the trading system via a web UI.

### Dashboard Backend

**Module**: `apps/dashboard.py`, `ui/dashboard.py`

**Framework**: FastAPI

**Data Sources:**
- Checkpoints: `artifacts/checkpoints/runtime_state_latest.json`
- Journals: `artifacts/orders.csv`, `artifacts/signals.csv`
- Engine logs: `artifacts/logs/events.jsonl`

**Key Endpoints:**

| Endpoint | Purpose |
|----------|---------|
| `GET /` | Dashboard home page (HTML) |
| `GET /api/portfolio` | Current positions, PnL, equity |
| `GET /api/orders` | Recent orders (paginated) |
| `GET /api/signals` | Recent signals (paginated) |
| `GET /api/performance` | Strategy performance metrics |
| `GET /api/health` | Engine status, heartbeat |
| `GET /api/config` | Current config (mode, universe, risk) |

**Start Command:**
```bash
uvicorn ui.dashboard:app --reload --port 8765
```

Or, using the convenience script:
```bash
python -m scripts.run_dashboard
```

**Note**: The dashboard runs as a **separate process** from trading engines. It does not need engines to be running; it reads from checkpoints and journals on disk.

---

### Dashboard UI

**Location**: `ui/templates/dashboard.html`, `ui/static/`

**Features:**
- **Portfolio Tab**: Positions, realized/unrealized PnL, equity curve
- **Orders Tab**: Recent orders with status (pending, filled, cancelled)
- **Signals Tab**: Recent strategy signals with reason, confidence, indicators
- **Performance Tab**: Per-strategy win rate, PnL, largest win/loss
- **Health Tab**: Engine status (running, stopped, error), heartbeat

**Technology**:
- Frontend: HTML + JavaScript (Vanilla JS or lightweight framework)
- Styling: Tailwind CSS or custom CSS
- Charts: Chart.js or Plotly for PnL curves and performance graphs

**Data Refresh**: JavaScript polls the `/api/portfolio`, `/api/orders`, `/api/signals` endpoints every 3-5 seconds to update the UI.

---

## Universe and Instruments

The system trades a **constrained universe** to ensure quality and liquidity.

### Equity Universe

**Config**: `configs/dev.yaml` → `trading.equity_universe_config`

**Default Configuration**: NIFTY 50 and NIFTY 100 stocks (excluding penny stocks)

```yaml
equity_universe_config:
  mode: "nifty_lists"              # "nifty_lists" or "all" (fallback to CSV)
  include_indices: ["NIFTY50", "NIFTY100"]
  max_symbols: 120                 # soft cap
  min_price: 100                   # exclude stocks below 100 rupees
```

**Filtering Process:**

1. **Scanner / Universe Builder** (`core/scanner.py`, `core/universe_builder.py`):
   - Loads NSE instruments from Kite
   - Filters by index membership (NIFTY 50 or NIFTY 100)
   - Applies `min_price` filter (≥ 100 rupees) using batch LTP fetch
   - Applies `max_symbols` cap if configured

2. **Scanner Output**:
   - Writes final filtered list to `artifacts/scanner/YYYY-MM-DD/universe.json`
   - File structure:
   ```json
   {
     "date": "2025-11-17",
     "asof": "2025-11-17T08:00:00Z",
     "fno": ["NIFTY", "BANKNIFTY"],
     "equity_universe": ["RELIANCE", "TCS", "INFY", ...],
     "meta": {
       "RELIANCE": {
         "tradingsymbol": "RELIANCE",
         "instrument_token": 738561,
         "exchange": "NSE",
         "lot_size": 1,
         "tick_size": 0.05
       }
     }
   }
   ```

3. **Equity Engine** (`engine/equity_paper_engine.py`):
   - On startup, loads universe from scanner output (`equity_universe` key)
   - Falls back to `artifacts/equity_universe.json` or `config/universe_equity.csv` if scanner output unavailable
   - Only loops over this filtered universe during trading

**Why NIFTY 50/100 Only?**
- **Liquidity**: High trading volume ensures tight bid-ask spreads
- **Quality**: Blue-chip stocks with established businesses
- **Volatility**: Sufficient intraday moves for trend-following strategies
- **No penny stocks**: Eliminates illiquid, low-quality stocks (min_price filter)

**Actual File Naming**: `artifacts/scanner/YYYY-MM-DD/universe.json` (date-stamped for each trading day)

---

### FnO Universe

**Config**: `configs/dev.yaml` → `trading.fno_universe`

**Default**: `["NIFTY", "BANKNIFTY", "FINNIFTY"]`

**Resolution**: `data/instruments.py` → `resolve_fno_symbols()` maps logical symbols (e.g., "NIFTY") to current month futures (e.g., "NIFTY25NOVFUT")

---

### Options Universe

**Config**: `configs/dev.yaml` → `trading.options_underlyings`

**Default**: `["NIFTY", "BANKNIFTY", "FINNIFTY"]`

**Resolution**: `data/options_instruments.py` → `OptionUniverse` resolves ATM strikes for nearest expiry

---

### Scanner Outputs

**Module**: `core/scanner.py`

**Purpose**: Pre-market scan to filter universe based on technical indicators (e.g., ATR, volume, trend)

**Output**: `artifacts/scanner/YYYY-MM-DD/universe.json`

**Usage**: Engines load scanner output on startup to constrain universe for the day.

---

## Entry Points and Commands

### Daily Paper Trading (Market Hours)

**Recommended Command:**
```bash
python -m scripts.run_trader paper
```

**What it does:**
1. Uses `configs/dev.yaml` (default paper config)
2. Reuses existing Kite tokens (no login prompt)
3. Starts all engines (FnO, Options, Equity) in daemon threads
4. Runs until Ctrl+C or market close

**Advanced Options:**
```bash
# Specific engines only
python -m scripts.run_trader paper --engines fno

# Force Kite re-login
python -m scripts.run_trader paper --login

# Custom config
python -m scripts.run_trader paper --config configs/my_config.yaml
```

---

### Daily Live Trading (Market Hours) [WIP]

**Recommended Command:**
```bash
python -m scripts.run_trader live --config configs/live.yaml
```

**What it does:**
1. **Requires explicit config** (`--config` flag) for safety
2. Performs preflight token check
3. Reconciles positions with broker
4. Starts live FnO engine (options/equity live engines not yet implemented)
5. Places **real orders** via Kite API

**Warning**: This places real orders with real money. Ensure risk limits are configured correctly.

---

### Start Dashboard Separately

**Command:**
```bash
uvicorn ui.dashboard:app --reload --port 8765
```

**Access**: http://localhost:8765

**Usage**: Dashboard reads from checkpoints and journals; can run independently of engines.

---

### Start All Services in One Process [Convenience]

**Command:**
```bash
python -m scripts.run_all --config configs/dev.yaml
```

**What it does:**
1. Starts all engines (FnO, Options, Equity) in daemon threads
2. Starts dashboard in same process (via uvicorn)
3. Starts live quotes streamer (WebSocket)

**Limitations**: If one component crashes, entire process stops. Prefer separate processes for production.

---

### Token Refresh (Login)

**Command:**
```bash
python -m scripts.run_day --login --engines none
```

**What it does:**
1. Opens interactive browser login to Kite
2. Saves access token to `secrets/kite_tokens.env`
3. Does not start engines (use `--engines all` to start after login)

---

## Debugging & Observability

The system provides comprehensive observability tools for debugging issues where trades are not happening or symbols consistently fail.

### Common Debugging Scenarios

#### 1. No Trades Happening (Only HOLD Signals)

**Symptoms:**
- Dashboard shows no orders
- `artifacts/signals.csv` shows only `HOLD` signals
- No position changes in state

**How to Debug:**

1. **Check signals.csv** (`artifacts/signals.csv` or `artifacts/replay_YYYY-MM-DD/<engine>/signals.csv`):
   ```csv
   timestamp,signal_id,logical,symbol,price,signal,tf,reason,profile,mode,...
   2025-11-17T09:30:00Z,abc123,NIFTY,NIFTY25NOVFUT,24500,HOLD,5m,ema20<ema50,INTRADAY,paper,...
   ```
   - **Look at the `reason` column**: Explains why strategy decided to HOLD
   - Common reasons: `ema20<ema50`, `rsi_neutral`, `no_trend`, `indicators_not_ready`, `ltp_missing`

2. **Check indicator columns** (ema20, ema50, rsi14, atr):
   - If indicators are `null` or `None`, insufficient history exists yet
   - Wait for system to accumulate enough data (typically 50-200 candles depending on strategy)

3. **Check strategy configuration** (`configs/dev.yaml` → `strategy_engine`):
   - Ensure strategies are enabled: `enabled: true`
   - For v2 engine: Check `strategies_v2` list includes desired strategies

4. **Check risk limits** (dashboard "Health" tab or `artifacts/checkpoints/runtime_state_latest.json`):
   - Daily PnL might have hit `max_daily_loss` (circuit breaker triggered)
   - Per-symbol loss might have hit `per_symbol_max_loss` (kill switch)

#### 2. Some Symbols Consistently Produce Errors

**Symptoms:**
- Specific symbols show `ltp_fetch_error` or `KeyError` in logs
- Symbols skipped repeatedly

**How to Debug:**

1. **Check JSON event logs** (`artifacts/logs/events.jsonl`):
   ```bash
   cat artifacts/logs/events.jsonl | grep ltp_fetch_error
   ```
   Example output:
   ```json
   {"timestamp": "2025-11-17T09:30:00Z", "event": "ltp_fetch_error", "symbol": "RELIANCE", "reason": "symbol_not_found"}
   ```

2. **Check symbol resolution**:
   - For FnO: Ensure symbol maps to valid futures contract (e.g., "NIFTY" → "NIFTY25NOVFUT")
   - For Options: Ensure ATM strike resolution works for current expiry
   - For Equity: Ensure symbol exists in Kite instruments and is tradable

3. **Check broker feed logs** (`logs/kite_algo_*.log`):
   - Look for Kite API errors (token expiry, rate limits, invalid symbols)
   - Kite may reject symbols not in your subscription or with corporate actions

### Key Files for Troubleshooting

#### signals.csv

**Location**: `artifacts/signals.csv` or `artifacts/replay_YYYY-MM-DD/<engine>/signals.csv`

**Purpose**: Per-symbol, per-timeframe strategy decisions with reasons and indicator snapshots

**Columns**:
- `timestamp`: When signal was generated
- `signal`: `LONG`, `SHORT`, `EXIT`, or `HOLD`
- `reason`: Human-readable explanation (e.g., "ema20>ema50", "indicators_not_ready")
- `ema20`, `ema50`, `rsi14`, `atr`: Indicator values at signal time
- `confidence`: Strategy confidence score (0.0-1.0)
- `strategy`: Strategy ID (e.g., "ema20_50_intraday")

**How to Use**:
```bash
# See all HOLD signals and their reasons
cat artifacts/signals.csv | grep HOLD | cut -d',' -f1,4,7,8

# Count signals by reason
cat artifacts/signals.csv | cut -d',' -f8 | sort | uniq -c
```

#### orders.csv

**Location**: `artifacts/orders.csv` or `artifacts/replay_YYYY-MM-DD/<engine>/orders.csv`

**Purpose**: Actual trades placed (or attempted) by engines

**Columns**:
- `timestamp`: When order was placed
- `symbol`: Trading symbol (e.g., "NIFTY25NOVFUT", "RELIANCE")
- `side`: `BUY` or `SELL`
- `quantity`: Lot size or share count
- `price`: Order price (LTP at order time)
- `status`: `FILLED`, `PENDING`, `REJECTED`, `CANCELLED`
- `strategy`: Strategy that triggered order
- `parent_signal_timestamp`: Link back to signal in signals.csv

**How to Use**:
```bash
# See all orders with status
cat artifacts/orders.csv | cut -d',' -f1,2,3,6,9

# Count orders by status
cat artifacts/orders.csv | tail -n +2 | cut -d',' -f6 | sort | uniq -c
```

#### JSON Event Logs

**Location**: `artifacts/logs/events.jsonl`

**Purpose**: Structured event log for errors, warnings, and debug events

**Event Types**:
- `ltp_fetch_error`: LTP fetch failed for symbol
- `indicators_not_ready`: Insufficient history for indicators
- `risk_blocked`: Risk engine rejected trade
- `hold_decision`: Strategy decided to HOLD with reason
- `order_placed`: Order submitted to broker
- `order_filled`: Order confirmed filled

**How to Use**:
```bash
# Find all LTP fetch errors
cat artifacts/logs/events.jsonl | jq 'select(.event=="ltp_fetch_error")'

# Count events by type
cat artifacts/logs/events.jsonl | jq -r '.event' | sort | uniq -c
```

#### Engine Logs (Text)

**Location**: `logs/kite_algo_*.log`

**Purpose**: Human-readable log stream from engines (INFO, WARNING, ERROR levels)

**How to Use**:
```bash
# Watch live logs
tail -f logs/kite_algo_*.log

# Find errors
grep ERROR logs/kite_algo_*.log

# Find specific symbol issues
grep "RELIANCE" logs/kite_algo_*.log
```

### Optional: LOG_REASON_FOR_HOLD Flag

For deep debugging, a `LOG_REASON_FOR_HOLD` flag can be enabled in engine code to log structured reasons when engines decide to HOLD or skip a symbol:

```python
# In engine main loop
if price is None:
    logger.info("HOLD: %s (reason=ltp_missing)", symbol)
    continue

if ema20 is None or ema50 is None:
    logger.info("HOLD: %s (reason=indicators_not_ready)", symbol)
    continue
```

This produces log entries like:
```
2025-11-17 09:30:00 INFO HOLD: RELIANCE (reason=ltp_missing)
2025-11-17 09:30:05 INFO HOLD: TCS (reason=indicators_not_ready)
```

---

## Future Extensions

### 1. Multi-Process Architecture

**Goal**: Move from threads to separate processes per engine

**Benefits:**
- Isolation (one engine crash doesn't kill others)
- CPU-bound backtests can run in parallel
- Easier to deploy engines on separate machines or containers

**Proposed Commands:**
```bash
python -m apps.run_fno_paper --config configs/dev.yaml
python -m apps.run_equity_paper --config configs/dev.yaml
python -m apps.run_options_paper --config configs/dev.yaml
```

**IPC Mechanism**: Redis or message queue (RabbitMQ, ZeroMQ) for inter-engine communication

---

### 2. Message Queue / Redis for IPC

**Goal**: Use message queue for event-driven communication between engines and dashboard

**Benefits:**
- Dashboard can subscribe to order/signal events in real-time (no polling)
- Engines can publish events without direct coupling
- Easier to scale to multiple machines

**Options**:
- Redis Pub/Sub
- RabbitMQ
- ZeroMQ

---

### 3. Advanced Analytics / ML-Based Signals

**Goal**: Integrate machine learning models for signal generation or filtering

**Modules to Add:**
- `analytics/learning_engine.py` (already exists, needs integration)
- `analytics/signal_quality.py` (already exists, needs integration)
- `analytics/strategy_performance.py` (already exists)

**Features:**
- Adaptive strategy tuning based on recent performance
- Signal quality scoring (filter low-quality signals)
- Regime-based strategy selection (trend vs mean-reversion)

---

### 4. Live Options and Equity Trading

**Current State**: Only FnO futures have live trading support

**Next Steps:**
- Implement `LiveOptionsEngine` (analog to `OptionsPaperEngine`)
- Implement `LiveEquityEngine` (analog to `EquityPaperEngine`)
- Add additional risk guardrails for options (Greeks-based risk, theta decay)

---

### 5. Backtesting Framework v3 Integration

**Current State**: Backtest Engine v3 exists (`backtest/engine_v3.py`) but not integrated into daily workflow

**Next Steps:**
- Add `--backtest` flag to `run_trader.py` for offline backtests
- Use historical data from `artifacts/history/` or external data sources
- Reuse live strategy/risk/portfolio engines for consistency

---

### 6. Enhanced Dashboard with Real-Time Charts

**Current State**: Dashboard polls for updates every 3-5 seconds

**Next Steps:**
- WebSocket support for real-time updates (no polling)
- Live PnL curve (streaming equity updates)
- Live order book (depth, bid/ask spread)
- Intraday candle charts (with indicators overlaid)

---

## Summary

The kite-algo-minimal system is a modular, extensible algo-trading platform designed for:
- **Multi-asset trading**: Equity, FnO Futures, Options
- **Paper and live modes**: Safe testing and real trading
- **Modular architecture**: Engines, strategies, risk, portfolio, and analytics as separate modules
- **State persistence**: Checkpoints and journals for recovery
- **Web monitoring**: FastAPI dashboard for real-time monitoring

**Current State**: Multi-threaded, single process, paper trading + live FnO futures

**Future State**: Multi-process, message queue IPC, live options/equity, ML-based signals, advanced analytics

---

**For More Information:**
- See `docs/Commands.md` for detailed command reference
- See `docs/Dashboard.md` for dashboard features and API
- See `docs/Strategies.md` for strategy development guide
- See `docs/RiskEngine.md` for risk configuration and guardrails
