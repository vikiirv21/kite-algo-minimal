# System Architecture – kite-algo-minimal

> **Status**: CURRENT – Last updated: 2025-11-19  
> **Purpose**: Detailed architecture, processes, and component interactions

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Component Diagram](#component-diagram)
3. [Trading Engines](#trading-engines)
4. [Strategy Engine](#strategy-engine)
5. [Execution Engine](#execution-engine)
6. [Market Data Flow](#market-data-flow)
7. [Risk & Portfolio Management](#risk--portfolio-management)
8. [State & Persistence](#state--persistence)
9. [Market Scanner & Universe](#market-scanner--universe)
10. [Dashboard & API](#dashboard--api)
11. [Process & Concurrency Model](#process--concurrency-model)
12. [Signal → Order → Fill → PnL Flow](#signal--order--fill--pnl-flow)
13. [Related Documentation](#related-documentation)

---

## Architecture Overview

The kite-algo-minimal system is built on a **modular, event-driven architecture** with clean separation between:

1. **Data Layer**: Market data ingestion, universe building, historical data
2. **Strategy Layer**: Signal generation, indicator calculation, multi-strategy fusion
3. **Execution Layer**: Order routing, paper simulation, live broker integration
4. **Risk Layer**: Position sizing, circuit breakers, drawdown limits
5. **Analytics Layer**: Performance tracking, trade journal, telemetry
6. **Dashboard Layer**: Real-time UI, REST API, log streaming

### Design Principles

- **Modularity**: Each component has a single responsibility
- **Testability**: Core logic isolated from external dependencies
- **Observability**: Comprehensive logging and telemetry at all layers
- **Safety**: Multiple layers of risk checks before execution
- **Extensibility**: Easy to add new strategies, indicators, and engines

---

## Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         Dashboard (React + FastAPI)              │
│  Portfolio | Trading | Signals | Analytics | System | Logs      │
└────────────────────────────┬────────────────────────────────────┘
                             │ REST API
                             │
┌────────────────────────────┴────────────────────────────────────┐
│                      Session Orchestrator                        │
│                    (scripts/run_session.py)                      │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Pre-market: Login, Universe Build, State Bootstrap      │  │
│  │  Trading: Start Engines, Monitor Health                  │  │
│  │  Post-market: Analytics, Reports, Shutdown               │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────────┬────────────────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│ Equity Engine │    │  FnO Engine   │    │Options Engine │
│   (Stocks)    │    │  (Futures)    │    │  (Options)    │
└───────┬───────┘    └───────┬───────┘    └───────┬───────┘
        │                    │                    │
        └────────────────────┼────────────────────┘
                             │
          ┌──────────────────┴──────────────────┐
          │                                     │
          ▼                                     ▼
  ┌───────────────┐                   ┌───────────────┐
  │Strategy Engine│                   │Execution Engine│
  │   (v2/v3)     │────signals───────▶│   (v3)         │
  └───────┬───────┘                   └───────┬───────┘
          │                                   │
          │ indicators                        │ orders
          │                                   │
          ▼                                   ▼
  ┌───────────────┐                   ┌───────────────┐
  │  Indicators   │                   │ Broker Layer  │
  │  (EMA, RSI,   │                   │ Paper | Live  │
  │   ATR, etc)   │                   └───────┬───────┘
  └───────────────┘                           │
                                              │ fills
          ┌───────────────────────────────────┘
          │
          ▼
  ┌───────────────┐     ┌───────────────┐     ┌───────────────┐
  │Portfolio Eng  │     │  Risk Engine  │     │  Regime Eng   │
  │  (Positions)  │     │ (Limits,SL,TP)│     │ (Market State)│
  └───────┬───────┘     └───────┬───────┘     └───────────────┘
          │                     │
          └──────────┬──────────┘
                     │
                     ▼
          ┌─────────────────────┐
          │   State & Storage   │
          │  artifacts/         │
          │  - checkpoints/     │
          │  - orders.csv       │
          │  - logs/            │
          │  - reports/         │
          └─────────────────────┘
```

---

## Trading Engines

The system has **three specialized trading engines**, each handling a different asset class:

### 1. Equity Paper Engine

**File**: `engine/equity_paper_engine.py`

**Responsibilities**:
- Trades equity stocks from NIFTY 50 / NIFTY 100
- Fetches universe from `artifacts/scanner/YYYY-MM-DD/universe.json`
- Loops over each symbol, fetches 5-minute candles
- Evaluates strategies via StrategyEngine v2/v3
- Places orders via ExecutionEngine v3 (paper broker)
- Records orders to `artifacts/orders_equity_paper_YYYY-MM-DD.csv`

**Configuration** (from `configs/dev.yaml`):
```yaml
equity_universe_config:
  mode: "nifty_lists"
  include_indices: ["NIFTY50", "NIFTY100"]
  max_symbols: 120
  min_price: 100
```

**Main Loop**:
```
For each symbol in universe:
  1. Fetch 5m candles (lookback = 200)
  2. Calculate indicators (EMA, RSI, ATR)
  3. Call StrategyEngine.evaluate()
  4. Get OrderIntent (BUY/SELL/EXIT/HOLD)
  5. Check risk limits (portfolio, regime)
  6. Place order via ExecutionEngine
  7. Update positions and state
  8. Sleep for tick interval (default: 10s)
```

### 2. FnO Paper Engine

**File**: `engine/paper_engine.py` (legacy, but still used for FnO futures)

**Responsibilities**:
- Trades index futures (NIFTY, BANKNIFTY, FINNIFTY)
- Resolves logical symbols to current month contracts (e.g., NIFTY → NIFTY25DECFUT)
- Uses multi-timeframe strategy engine
- Places orders via paper broker
- Records orders to `artifacts/orders_fno_paper_YYYY-MM-DD.csv`

**Configuration**:
```yaml
fno_universe:
  - "NIFTY"
  - "BANKNIFTY"
  - "FINNIFTY"
```

**Key Differences from Equity**:
- Uses lot sizes (e.g., NIFTY = 75, BANKNIFTY = 30)
- Higher leverage and volatility
- Different risk parameters (ATR multipliers, stop-loss %)

### 3. Options Paper Engine

**File**: `engine/options_paper_engine.py`

**Responsibilities**:
- Trades index options (NIFTY, BANKNIFTY, FINNIFTY)
- Selects strikes based on ATM/OTM distance (e.g., 1 strike OTM)
- Chooses CE (call) or PE (put) based on signal
- Places orders via paper broker
- Records orders to `artifacts/orders_options_paper_YYYY-MM-DD.csv`

**Strike Selection Logic**:
```python
# Example: NIFTY at 21,500
# ATM = 21,500 (nearest strike)
# 1 strike OTM call = 21,550 (if strike interval = 50)
# 1 strike OTM put = 21,450
```

**Configuration**:
```yaml
options_underlyings:
  - "NIFTY"
  - "BANKNIFTY"
  - "FINNIFTY"
```

### Engine Startup Modes

**Single-Process Mode** (default):
```bash
python -m scripts.run_session --mode paper --config configs/dev.yaml
```
All engines run as threads in a single Python process.

**Multi-Process Mode**:
```bash
python -m scripts.run_session --mode paper --config configs/dev.yaml --layout multi
```
Each engine runs as a separate Python process, started via subprocess.

**Individual Engine Mode**:
```bash
python -m apps.run_equity_paper --config configs/dev.yaml --mode paper
python -m apps.run_fno_paper --config configs/dev.yaml --mode paper
python -m apps.run_options_paper --config configs/dev.yaml --mode paper
```

---

## Strategy Engine

The strategy engine has evolved through three major versions:

### Strategy Engine v1 (Legacy)

**Location**: `strategies/` directory

**Characteristics**:
- Bar-based strategies (receive full candle DataFrame)
- Manual indicator calculation
- Returns `Decision` objects (BUY/SELL/EXIT/HOLD)

**Examples**:
- `fno_intraday_trend.py`: Multi-timeframe EMA trend strategy
- `equity_intraday_simple.py`: Simple equity strategy

### Strategy Engine v2

**File**: `core/strategy_engine_v2.py`

**Key Features**:
- **Unified indicator calculation**: All strategies share the same indicator bundle
- **OrderIntent model**: Standardized signal format with confidence scoring
- **Conflict resolution**: When multiple strategies signal, resolve by confidence or priority
- **Integration with PortfolioEngine, RiskEngine, RegimeEngine**

**OrderIntent Model**:
```python
@dataclass
class OrderIntent:
    symbol: str
    signal: str          # "BUY", "SELL", "EXIT", "HOLD"
    side: str            # "LONG", "SHORT", "FLAT"
    logical: str         # Logical symbol (e.g., "NIFTY")
    timeframe: str       # "5m", "15m", etc.
    strategy_id: str     # "EMA_20_50", "RSI_PULLBACK", etc.
    confidence: float    # 0.0 to 1.0
    qty_hint: Optional[int]
    reason: str          # Human-readable explanation
    extra: Dict[str, Any]  # Additional metadata
```

**Strategy Registration**:
```yaml
strategy_engine:
  strategies_v2:
    - id: EMA_20_50
      module: strategies.ema20_50_intraday_v2
      class: EMA2050IntradayV2
      enabled: true
      params:
        timeframe: "5m"
        min_rr: 1.5
        min_confidence: 0.55
```

### Strategy Engine v3

**File**: `core/strategy_engine_v3.py`

**Key Features**:
- **Multi-strategy fusion**: Combine signals from multiple strategies
- **Multi-timeframe confirmation**: Primary (5m) + secondary (15m) timeframe alignment
- **Playbook-based setup classification**: Categorize setups (trend follow, pullback, breakout)
- **EventBus integration**: Publish signals to telemetry bus

**Strategy Registry** (v3):
```python
STRATEGY_REGISTRY_V3 = {
    "ema20_50": EMA2050Strategy,
    "trend": TrendStrategy,
    "rsi_pullback": RSIPullbackStrategy,
    "vwap_filter": VWAPFilterStrategy,
    "vol_regime": VolRegimeStrategy,
    "htf_trend": HTFTrendStrategy,
}
```

**Configuration Example** (`configs/strategy_engine_v3.yaml`):
```yaml
primary_tf: "5m"
secondary_tf: "15m"

strategies:
  - id: "ema20_50"
    enabled: true
  - id: "vwap_filter"
    enabled: true
  - id: "htf_trend"
    enabled: true

playbooks:
  trend_follow:
    description: "Strong trend with HTF alignment"
    rules:
      - "ema20_50 signal == BUY"
      - "htf_trend signal == BUY"
  pullback:
    description: "Pullback in trend"
    rules:
      - "rsi_pullback signal == BUY"
      - "trend signal == BUY"
```

**Signal Fusion Logic**:
1. Each strategy outputs a signal with confidence (0.0 to 1.0)
2. Aggregate signals by side (LONG/SHORT)
3. Calculate weighted confidence (average of all agreeing strategies)
4. Classify setup using playbooks
5. Return fused OrderIntent with combined confidence

---

## Execution Engine

### Execution Engine v3

**File**: `core/execution_engine_v3.py`

**Key Features**:
- **Unified interface**: Same API for paper and live execution
- **Order lifecycle tracking**: NEW → SUBMITTED → OPEN → FILLED/CANCELLED/REJECTED
- **EventBus integration**: Publish order events to telemetry bus
- **Backward compatible**: Drop-in replacement for older execution code

### Order Model

```python
class Order(BaseModel):
    order_id: str               # Unique UUID
    symbol: str                 # Trading symbol
    side: str                   # "BUY" or "SELL"
    qty: int                    # Quantity
    order_type: str             # "MARKET" or "LIMIT"
    price: Optional[float]      # Limit price (for LIMIT orders)
    status: str                 # OrderStatus enum
    created_at: datetime
    updated_at: datetime
    strategy: str               # Strategy identifier
    tags: Dict[str, Any]        # Additional metadata
    
    # Execution details
    filled_qty: int
    remaining_qty: int
    avg_fill_price: Optional[float]
    message: Optional[str]
    events: List[Dict[str, Any]]  # Fill history
```

### Paper Execution

**Class**: `PaperExecutionEngineV3`

**Features**:
- Realistic fill simulation with configurable slippage
- Instant fills for MARKET orders (next tick)
- Limit order fills only if price crosses limit
- Partial fills supported
- CSV order logging

**Slippage Simulation**:
```python
# Default: 5 bps = 0.05%
slippage_bps = 5.0

# For BUY orders
fill_price = ltp * (1 + slippage_bps / 10000)

# For SELL orders
fill_price = ltp * (1 - slippage_bps / 10000)
```

### Live Execution

**Class**: `LiveExecutionEngineV3`

**Features**:
- Real broker orders via Kite Connect
- Retry logic for transient errors
- Order status polling
- Reconciliation with broker state
- Production-ready error handling

**Safety Checks**:
1. Token validity check
2. Rate limiting (max orders per second)
3. Position limit checks
4. Circuit breaker checks (daily loss, drawdown)
5. Duplicate order prevention

---

## Market Data Flow

### Data Sources

1. **Live Data**: Kite Connect REST API + WebSocket (planned)
2. **Historical Data**: Kite historical API (for indicators, backtesting)
3. **Cached Data**: Local CSV files (for offline backtesting)

### Market Data Engine

**File**: `core/market_data_engine.py`

**Features**:
- Real-time tick processing
- Multi-timeframe candle building (1m, 5m, 15m, 1h, 1d)
- WebSocket integration (planned)
- Tick-to-candle aggregation

**Configuration**:
```yaml
data:
  source: "broker"
  timeframe: "5minute"
  history_lookback: 50
  use_mde_v2: false     # Enable Market Data Engine v2
  feed: "kite"          # "kite" or "replay"
  timeframes:
    - "1m"
    - "5m"
  replay_speed: 1.0     # For backtesting
```

### Data Flow Diagram

```
Kite Connect API
      │
      ▼
BrokerFeed.fetch_historical()
      │
      ▼
DataFrame (OHLCV)
      │
      ├──▶ Indicators.calculate() ──▶ EMA, RSI, ATR, etc.
      │
      └──▶ StrategyEngine.evaluate() ──▶ OrderIntent
```

---

## Risk & Portfolio Management

### Portfolio Engine

**File**: `core/portfolio_engine.py`

**Responsibilities**:
- Track all open positions across engines
- Calculate total exposure and margin usage
- Enforce capital limits per strategy
- Position sizing based on risk parameters

**Configuration**:
```yaml
portfolio:
  max_leverage: 2.0
  max_exposure_pct: 0.8
  max_risk_per_trade_pct: 0.01
  position_sizing_mode: "fixed_qty"  # or "fixed_risk_atr"
  lot_size_fallback: 25
  default_fixed_qty: 1
  atr_stop_multiplier: 2.0
  
  strategy_budgets:
    ema20_50_intraday:
      capital_pct: 0.3
      fixed_qty: 1
```

**Position Sizing Modes**:

1. **fixed_qty**: Fixed quantity per trade
   ```python
   qty = default_fixed_qty  # e.g., 1 lot
   ```

2. **fixed_risk_atr**: Risk-based sizing using ATR
   ```python
   risk_amount = equity * max_risk_per_trade_pct
   stop_distance = atr * atr_stop_multiplier
   qty = risk_amount / (stop_distance * lot_size)
   ```

### Risk Engine v2

**File**: `core/risk_engine_v2.py`

**Features**:
- **Circuit breakers**: Max daily loss, max drawdown, max loss streak
- **Position limits**: Max open positions, max positions per strategy
- **Time-based filters**: Only trade during specified sessions
- **Stop-loss and take-profit**: ATR-based or percentage-based
- **Trailing stops**: Start trailing after profit target reached

**Configuration**:
```yaml
risk_engine:
  enabled: false
  max_loss_per_trade_pct: 0.01
  soft_stop_pct: -0.7
  hard_stop_pct: -1.2
  take_profit_r: 2.0
  trail_start_r: 1.0
  trail_step_r: 0.5
  time_stop_bars: 25
  partial_exit_fraction: 0.5
  enable_partial_exits: true
  enable_trailing: true
  enable_time_stop: true
```

### Trade Guardian

**File**: `core/trade_guardian.py`

**Purpose**: Pre-execution safety gate

**Checks**:
1. Rate limiting (max orders per second)
2. Lot size limits
3. Stale price check (reject if LTP older than N seconds)
4. Slippage check (reject if expected slippage > threshold)
5. Drawdown check (halt if drawdown exceeds limit)

**Configuration**:
```yaml
guardian:
  enabled: false
  max_order_per_second: 5
  max_lot_size: 50
  reject_if_price_stale_secs: 3
  reject_if_slippage_pct: 2.0
  max_daily_drawdown_pct: 3.0
  halt_on_pnl_drop_pct: 5.0
```

### Regime Engine

**File**: `core/regime_engine.py`

**Purpose**: Classify market state (trend, volatility, structure)

**Regimes Detected**:
1. **Trend**: UP_TREND, DOWN_TREND, RANGE
2. **Volatility**: HIGH_VOL, NORMAL_VOL, LOW_VOL
3. **Structure**: COMPRESSION, EXPANSION, NEUTRAL

**Configuration**:
```yaml
regime_engine:
  enabled: true
  bar_period: "1m"
  slope_period: 20
  atr_period: 14
  volatility_high_pct: 1.0
  volatility_low_pct: 0.35
  compression_pct: 0.25
```

**Usage**:
```python
regime = regime_engine.get_regime(symbol)
if regime["trend"] == "DOWN_TREND":
    # Skip long entries
    pass
```

---

## State & Persistence

All runtime state is persisted to `artifacts/` directory:

### Directory Structure

```
artifacts/
├── checkpoints/
│   ├── runtime_state_latest.json    # Current session state
│   └── paper_state_latest.json      # Paper broker state
├── orders_equity_paper_2025-11-19.csv   # Equity orders
├── orders_fno_paper_2025-11-19.csv      # FnO orders
├── orders_options_paper_2025-11-19.csv  # Options orders
├── snapshots/
│   └── positions_20251119_143000.json   # Position snapshots
├── logs/
│   ├── equity_paper_engine.log      # Engine logs
│   ├── server.log                   # Dashboard logs
│   └── events.jsonl                 # Event logs (telemetry)
├── reports/
│   └── daily/
│       └── 2025-11-19.json          # Daily analytics report
├── scanner/
│   └── 2025-11-19/
│       └── universe.json            # Daily universe
└── journal/
    └── 2025-11-19/
        └── trades.jsonl             # Trade journal
```

### Checkpoint Format

**runtime_state_latest.json**:
```json
{
  "mode": "paper",
  "session_id": "2025-11-19-equity-paper",
  "start_time": "2025-11-19T09:15:00+05:30",
  "portfolio": {
    "equity": 500000.0,
    "realized_pnl": 1250.50,
    "unrealized_pnl": -320.00,
    "total_pnl": 930.50
  },
  "positions": [
    {
      "symbol": "RELIANCE",
      "qty": 10,
      "avg_price": 2450.25,
      "ltp": 2462.00,
      "pnl": 117.50
    }
  ],
  "orders_count": 25,
  "last_updated": "2025-11-19T14:30:00+05:30"
}
```

### Orders CSV Format

**orders_equity_paper_2025-11-19.csv**:
```csv
timestamp,order_id,symbol,side,qty,order_type,price,status,filled_qty,avg_fill_price,strategy,reason
2025-11-19 09:30:15,abc123,RELIANCE,BUY,10,MARKET,,FILLED,10,2450.25,EMA_20_50,EMA crossover up
2025-11-19 10:15:30,def456,RELIANCE,SELL,10,MARKET,,FILLED,10,2462.00,EMA_20_50,EMA crossover down
```

---

## Market Scanner & Universe

### Universe Builder

**File**: `core/universe_builder.py`

**Purpose**: Build daily tradeable universe

**Process**:
1. Fetch NIFTY 50 / NIFTY 100 constituents from data layer
2. Filter by min price (e.g., > ₹100 to exclude penny stocks)
3. Filter by liquidity (optional, using volume)
4. Apply max symbols limit (e.g., 120 stocks)
5. Save to `artifacts/scanner/YYYY-MM-DD/universe.json`

**Configuration**:
```yaml
equity_universe_config:
  mode: "nifty_lists"
  include_indices: ["NIFTY50", "NIFTY100"]
  max_symbols: 120
  min_price: 100
```

**Output Format**:
```json
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

### Market Scanner

**Script**: `scripts/run_indicator_scanner.py`

**Purpose**: Pre-market technical scanning

**Scans For**:
- Strong trends (EMA alignment)
- Overbought/oversold (RSI extremes)
- Volatility expansion (ATR breakout)
- Volume surges

**Output**: Enhanced universe with scanner flags

---

## Dashboard & API

### Backend: FastAPI Server

**File**: `apps/server.py`

**Main Endpoints**:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | GET | Serve React app (static build) |
| `/api/state` | GET | Current session state (portfolio, equity, PnL) |
| `/api/engines/status` | GET | Engine health and status |
| `/api/positions` | GET | All open positions |
| `/api/orders` | GET | All orders (with filtering) |
| `/api/logs` | GET | Engine logs (paginated) |
| `/api/logs/tail` | GET | Recent log lines (streaming) |
| `/api/pm/log` | GET | Portfolio manager logs |
| `/api/analytics/daily` | GET | Daily analytics report |
| `/api/analytics/equity_curve` | GET | Equity curve data for charting |
| `/api/health` | GET | System health check |

### Frontend: React App

**Directory**: `ui/frontend/`

**Pages**:
1. **Overview**: Portfolio summary, equity, P&L, positions count
2. **Trading**: Active positions with real-time P&L
3. **Portfolio**: Position details, allocation, risk metrics
4. **Signals**: Recent strategy signals with confidence scores
5. **Analytics**: Performance charts, equity curve, drawdown
6. **System**: Engine status, health metrics, runtime mode
7. **Logs**: Filterable log viewer with auto-refresh

**Tech Stack**:
- React 18 + TypeScript
- Tailwind CSS (dark theme)
- React Query (data fetching, auto-polling)
- Recharts (charting)
- React Router (navigation)

**Build Process**:
```bash
./build-dashboard.sh
# Builds frontend and copies to static/
```

### Real-Time Updates

**Polling Strategy**:
- Portfolio data: 1 second
- Positions/orders: 2 seconds
- Logs: 5 seconds
- Analytics: 10 seconds

**Future**: WebSocket for true real-time push updates

---

## Process & Concurrency Model

### Current: Single-Process Multi-Threaded

**Default behavior** (when using `scripts.run_session`):
- All engines run as threads in one Python process
- Dashboard runs as separate uvicorn process (port 9000)
- Shared memory for state (thread-safe data structures)

**Advantages**:
- Simple debugging (single process)
- Fast inter-engine communication
- Easy state sharing

**Limitations**:
- Python GIL limits CPU parallelism
- One engine crash can affect others
- Memory isolation not guaranteed

### Future: Multi-Process Architecture

**New behavior** (with `--layout multi`):
- Each engine runs as separate Python process
- Inter-process communication via files or message queue (future: Redis)
- Dashboard as separate process

**Advantages**:
- True parallelism (no GIL)
- Process isolation (crash in one engine doesn't affect others)
- Scales to high-frequency workloads

**Challenges**:
- More complex IPC
- State synchronization overhead
- Harder debugging

---

## Signal → Order → Fill → PnL Flow

### Complete Flow Diagram

```
1. Market Data Fetch
   ├─▶ BrokerFeed.fetch_historical(symbol, "5m", lookback=200)
   └─▶ DataFrame(OHLCV)
         │
2. Indicator Calculation
   ├─▶ Indicators.calculate(df)
   └─▶ df with [ema_20, ema_50, rsi, atr, vwap, bb_upper, bb_lower]
         │
3. Strategy Evaluation
   ├─▶ StrategyEngine.evaluate(symbol, df, indicators, position)
   └─▶ OrderIntent(signal="BUY", confidence=0.75, reason="EMA crossover")
         │
4. Risk Checks
   ├─▶ RiskEngine.check_limits(intent, portfolio)
   ├─▶ RegimeEngine.check_regime(symbol, intent)
   ├─▶ TradeGuardian.validate(intent)
   └─▶ Approved OrderIntent
         │
5. Position Sizing
   ├─▶ PortfolioEngine.calculate_qty(intent, risk_params)
   └─▶ OrderIntent with qty
         │
6. Order Placement
   ├─▶ ExecutionEngine.place_order(intent)
   └─▶ Order(order_id, symbol, side, qty, status="SUBMITTED")
         │
7. Order Execution (Paper)
   ├─▶ PaperBroker.simulate_fill(order, ltp)
   └─▶ Order(status="FILLED", avg_fill_price, filled_qty)
         │
8. Position Update
   ├─▶ PortfolioEngine.update_position(order)
   └─▶ Position(symbol, qty, avg_price, unrealized_pnl)
         │
9. State Persistence
   ├─▶ StateStore.save_checkpoint(state)
   ├─▶ Write to orders.csv
   └─▶ Write to events.jsonl
         │
10. Telemetry & Analytics
    ├─▶ TelemetryBus.publish_order_event(order)
    ├─▶ TradeJournal.record_trade(order, position)
    └─▶ PerformanceEngine.update_metrics(portfolio)
```

### Example: End-to-End Flow

**Scenario**: EMA 20/50 crossover on RELIANCE

```
09:30:00 - Fetch RELIANCE 5m data (last 200 candles)
09:30:01 - Calculate EMA(20) = 2450, EMA(50) = 2430
09:30:02 - Detect crossover: EMA(20) crossed above EMA(50)
09:30:03 - StrategyEngine outputs:
           OrderIntent(
             symbol="RELIANCE",
             signal="BUY",
             confidence=0.75,
             reason="EMA 20 crossed above EMA 50, trend strength 0.8"
           )
09:30:04 - RiskEngine checks:
           ✓ Portfolio exposure: 65% (< 80% limit)
           ✓ Daily loss: -₹500 (< ₹3000 limit)
           ✓ Max positions: 4 open (< 5 limit)
09:30:05 - PortfolioEngine calculates qty:
           Risk per trade: ₹5000 (1% of ₹500K)
           ATR stop: 2.5% (2 * ATR / price)
           Qty = 5000 / (2450 * 0.025) = 81 shares
           Rounded to 80 shares
09:30:06 - ExecutionEngine places order:
           Order(
             order_id="uuid-123",
             symbol="RELIANCE",
             side="BUY",
             qty=80,
             order_type="MARKET",
             status="SUBMITTED"
           )
09:30:07 - PaperBroker simulates fill:
           LTP = 2450.25
           Slippage = 5 bps = 0.05% = 1.22
           Fill price = 2450.25 + 1.22 = 2451.47
           Order status = "FILLED"
09:30:08 - PortfolioEngine updates position:
           Position(
             symbol="RELIANCE",
             qty=80,
             avg_price=2451.47,
             ltp=2450.25,
             unrealized_pnl=-97.60  # (2450.25 - 2451.47) * 80
           )
09:30:09 - Write to orders.csv:
           2025-11-19 09:30:08,uuid-123,RELIANCE,BUY,80,MARKET,,FILLED,80,2451.47,EMA_20_50,EMA crossover up
09:30:10 - Save checkpoint to runtime_state_latest.json
09:30:11 - Publish to telemetry bus:
           TelemetryBus.publish_order_event(order)
           TelemetryBus.publish_position_event(position)

10:15:00 - RELIANCE LTP = 2462.00
10:15:01 - Position P&L = (2462.00 - 2451.47) * 80 = +₹842.40
10:15:02 - StrategyEngine evaluates exit:
           EMA(20) crossed below EMA(50)
           OrderIntent(signal="EXIT", reason="EMA crossover down")
10:15:03 - ExecutionEngine places SELL order:
           Order(symbol="RELIANCE", side="SELL", qty=80, status="SUBMITTED")
10:15:04 - PaperBroker simulates fill:
           Fill price = 2462.00 - 1.23 = 2460.77
           Order status = "FILLED"
10:15:05 - PortfolioEngine closes position:
           Realized P&L = (2460.77 - 2451.47) * 80 = +₹744.00
10:15:06 - Update portfolio:
           Total equity = 500744.00
           Realized P&L today = +₹744.00
10:15:07 - Write to orders.csv and checkpoint
```

---

## Related Documentation

For more details, see:

- **[REPO_OVERVIEW.md](./REPO_OVERVIEW.md)**: High-level repository summary
- **[MODULES.md](./MODULES.md)**: Module-by-module reference
- **[ENGINES.md](./ENGINES.md)**: Trading engine deep-dive
- **[STRATEGIES.md](./STRATEGIES.md)**: Strategy development guide
- **[DASHBOARD.md](./DASHBOARD.md)**: Dashboard and API docs
- **[RUNBOOKS.md](./RUNBOOKS.md)**: Operational runbook

---

**Last Updated**: 2025-11-19  
**Version**: 1.0
