# HFT System Architecture – kite-algo-minimal

**High-Level Trading System for Equity, FnO Futures, and Options**

This document describes the architecture of the kite-algo-minimal algorithmic trading system, covering both paper trading (simulation) and live trading modes. The system is designed to handle multiple asset classes (Equity, FnO Futures, Options) with a modular, extensible architecture.

---

## Table of Contents

1. [High-Level Overview](#high-level-overview)
2. [Process & Concurrency Model](#process--concurrency-model)
3. [Engines and Responsibilities](#engines-and-responsibilities)
4. [Strategy, Risk, and Portfolio Engines](#strategy-risk-and-portfolio-engines)
5. [Paper vs Live Modes](#paper-vs-live-modes)
6. [State, Journals, and Analytics](#state-journals-and-analytics)
7. [Dashboard Integration](#dashboard-integration)
8. [Universe and Instruments](#universe-and-instruments)
9. [Entry Points and Commands](#entry-points-and-commands)
10. [Future Extensions](#future-extensions)

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
│  │          FastAPI App (apps/dashboard.py)                 │   │
│  │  Reads: checkpoints, journals, logs                      │   │
│  │  Serves: Web UI on http://localhost:8765                 │   │
│  └──────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────────┘
```

**Why Multi-Threading Today:**
- **IO-bound operations**: Most time is spent waiting on broker API calls, websocket data, and market data fetches
- **Shared memory**: Threads can share runtime state, checkpoints, and configuration easily
- **Simplicity**: Single process is easier to deploy and monitor during development

**Why Multi-Process Later:**
- **Isolation**: Each engine can crash independently without bringing down others
- **CPU-bound backtests**: Multi-process allows parallel backtests using multiple cores
- **Scaling**: Easier to deploy engines across multiple machines or containers
- **Resource limits**: Can set per-engine memory/CPU limits

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

Or, if using the `apps/dashboard.py` wrapper:
```bash
python -m uvicorn apps.dashboard:app --reload --port 8765
```

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

**Default**: NIFTY 50 and NIFTY 100 stocks (no penny stocks)

**Constraints:**
- `min_price: 100` (exclude low-priced stocks)
- `max_symbols: 120` (soft cap)
- `include_indices: ["NIFTY50", "NIFTY100"]`

**Loading**: `core/universe_builder.py` loads equity universe from:
- `config/universe_equity.csv`
- Kite instruments master (filtered)

---

### FnO Universe

**Config**: `configs/dev.yaml` → `trading.fno_universe`

**Default**: `["NIFTY", "BANKNIFTY", "FINNIFTY"]`

**Resolution**: `data/instruments.py` → `resolve_fno_symbols()` maps logical symbols (e.g., "NIFTY") to current month futures (e.g., "NIFTY25JANFUT")

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
