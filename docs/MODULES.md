# Module Reference – kite-algo-minimal

> **Status**: CURRENT – Last updated: 2025-11-19  
> **Purpose**: Detailed module-by-module developer reference

---

## Table of Contents

1. [Core Modules (core/)](#core-modules)
2. [Engine Modules (engine/)](#engine-modules)
3. [Analytics Modules (analytics/)](#analytics-modules)
4. [Strategy Modules (strategies/ & core/strategies_v3/)](#strategy-modules)
5. [Broker Modules (broker/)](#broker-modules)
6. [Data Modules (data/)](#data-modules)
7. [Risk Modules (risk/)](#risk-modules)
8. [Service Modules (services/)](#service-modules)
9. [Application Modules (apps/)](#application-modules)
10. [Script Modules (scripts/)](#script-modules)
11. [UI Modules (ui/)](#ui-modules)
12. [Backtest Modules (backtest/)](#backtest-modules)

---

## Core Modules

The `core/` directory contains the fundamental trading logic and engines.

### core/strategy_engine_v3.py (525 lines)

**Purpose**: Multi-strategy fusion engine with multi-timeframe confirmation

**Key Classes**:
- `StrategyEngineV3`: Main orchestrator for v3 strategies
  - `__init__(cfg, bus)`: Initialize with config and event bus
  - `evaluate(symbol, candles_5m, candles_15m, position, regime)`: Evaluate all strategies and fuse signals
  - `_compute_indicators(candles, tf)`: Calculate unified indicator bundle
  - `_fuse_signals(signals)`: Aggregate signals by confidence weighting
  - `_classify_setup(signals)`: Classify setup using playbooks

**Strategy Registry**:
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

**Dependencies**: `core.indicators`, `core.strategies_v3`, telemetry bus

### core/strategy_engine_v2.py (1547 lines)

**Purpose**: Modern indicator-based strategy architecture with conflict resolution

**Key Classes**:
- `StrategyEngineV2`: Main engine for v2 strategies
  - `evaluate(symbol, df, position, regime)`: Evaluate all enabled strategies
  - `_resolve_conflicts(intents)`: Resolve conflicts when multiple strategies signal
  - `_compute_unified_indicators(df)`: Calculate indicators once for all strategies
  - `register_strategy(strategy_id, strategy_instance)`: Add strategy to registry
- `BaseStrategy`: Abstract base class for v2 strategies
  - `generate_signal(candle, series, indicators, position)`: Must be implemented by subclasses
- `OrderIntent`: Dataclass for strategy signals with confidence scoring

**Conflict Resolution Modes**:
- `highest_confidence`: Choose signal with highest confidence
- `priority`: Use pre-defined strategy priorities
- `net_out`: Cancel opposing signals, keep strongest side

**Dependencies**: `core.indicators`, `core.portfolio_engine`, `core.risk_engine`, `core.regime_engine`

### core/execution_engine_v3.py (1121 lines)

**Purpose**: Unified paper/live execution layer with order lifecycle tracking

**Key Classes**:
- `Order`: Pydantic model for unified order representation
  - Fields: `order_id`, `symbol`, `side`, `qty`, `order_type`, `price`, `status`, `filled_qty`, `avg_fill_price`
  - Lifecycle: NEW → SUBMITTED → OPEN → FILLED/CANCELLED/REJECTED
- `ExecutionEngineV3`: Abstract base class defining execution interface
  - `place_order(order)`: Submit order for execution
  - `cancel_order(order_id)`: Cancel pending order
  - `get_order_status(order_id)`: Query order status
  - `list_orders(filters)`: List orders with filtering
- `PaperExecutionEngineV3`: Paper execution with realistic simulation
  - `_simulate_fill(order, ltp)`: Fill logic with configurable slippage
  - `_save_to_csv(order)`: Persist order to CSV
- `LiveExecutionEngineV3`: Live execution with retry logic (placeholder)

**Configuration**:
```yaml
execution:
  use_execution_engine_v2: false
  dry_run: false
  slippage_bps: 5.0
  circuit_breakers:
    max_daily_loss_rupees: 5000.0
    max_daily_drawdown_pct: 0.02
```

**Dependencies**: `analytics.telemetry_bus`, `broker` layer

### core/portfolio_engine.py (619 lines)

**Purpose**: Position tracking and capital allocation across strategies

**Key Classes**:
- `PortfolioEngine`: Track positions, calculate P&L, enforce limits
  - `get_position(symbol)`: Get current position for symbol
  - `update_position(order)`: Update position after fill
  - `calculate_pnl(ltp_map)`: Calculate realized and unrealized P&L
  - `check_exposure_limits()`: Verify exposure within limits
  - `allocate_capital(strategy_id)`: Allocate capital budget to strategy
- `Position`: Dataclass representing an open position
  - Fields: `symbol`, `qty`, `avg_price`, `ltp`, `unrealized_pnl`, `realized_pnl`

**Position Sizing**:
- Fixed quantity mode: Use configured lot size
- ATR-based risk mode: `qty = risk_amount / (atr_stop_distance * price)`

**Dependencies**: State store for persistence

### core/risk_engine_v2.py (366 lines)

**Purpose**: Circuit breakers, stop-loss, take-profit, trailing stops

**Key Classes**:
- `RiskEngineV2`: Enforce risk limits and exit logic
  - `check_entry_allowed(symbol, portfolio)`: Pre-trade risk check
  - `check_stop_loss(position, ltp)`: Check if position hit stop-loss
  - `check_take_profit(position, ltp)`: Check if position hit take-profit
  - `update_trailing_stop(position, ltp)`: Update trailing stop price
  - `get_partial_exit_qty(position)`: Calculate partial exit quantity

**Risk Controls**:
- Max daily loss (absolute rupees)
- Max drawdown percentage
- Max loss streak (consecutive losing trades)
- Time-based stops (exit after N bars)
- Partial exits (scale out at profit targets)

**Configuration**:
```yaml
risk_engine:
  enabled: false
  max_loss_per_trade_pct: 0.01
  soft_stop_pct: -0.7
  hard_stop_pct: -1.2
  take_profit_r: 2.0
  enable_trailing: true
```

### core/regime_engine.py (426 lines)

**Purpose**: Market regime detection (trend, volatility, structure)

**Key Classes**:
- `RegimeEngine`: Classify market state for each symbol
  - `update_regime(symbol, df)`: Update regime based on latest data
  - `get_regime(symbol)`: Get current regime classification
  - `is_regime_compatible(regime, strategy)`: Check strategy-regime compatibility

**Regimes Detected**:
1. **Trend**: UP_TREND, DOWN_TREND, RANGE (based on EMA slope)
2. **Volatility**: HIGH_VOL, NORMAL_VOL, LOW_VOL (based on ATR%)
3. **Structure**: COMPRESSION, EXPANSION, NEUTRAL (based on Bollinger Band width)

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

### core/indicators.py (608 lines)

**Purpose**: Technical indicator calculations (EMA, RSI, ATR, VWAP, Bollinger Bands, etc.)

**Key Functions**:
- `ema(series, period)`: Exponential moving average
- `sma(series, period)`: Simple moving average
- `rsi(series, period)`: Relative strength index
- `atr(df, period)`: Average true range
- `vwap(df)`: Volume-weighted average price
- `bollinger_bands(series, period, std_dev)`: Bollinger bands (upper, middle, lower)
- `macd(series, fast, slow, signal)`: MACD indicator
- `stochastic(df, period)`: Stochastic oscillator
- `adx(df, period)`: Average directional index (trend strength)

**Usage**:
```python
from core.indicators import ema, rsi, atr

df['ema_20'] = ema(df['close'], 20)
df['ema_50'] = ema(df['close'], 50)
df['rsi'] = rsi(df['close'], 14)
df['atr'] = atr(df, 14)
```

### core/market_data_engine.py (394 lines)

**Purpose**: Real-time tick processing and candle building

**Key Classes**:
- `MarketDataEngine`: Process ticks and build multi-timeframe candles
  - `on_tick(tick)`: Process incoming tick
  - `build_candle(symbol, timeframe)`: Aggregate ticks into candle
  - `get_candles(symbol, timeframe, count)`: Get recent candles
  - `subscribe(symbol, timeframes)`: Subscribe to symbol for given timeframes

**Supported Timeframes**: 1m, 5m, 15m, 1h, 1d

**Configuration**:
```yaml
data:
  use_mde_v2: false
  feed: "kite"
  timeframes: ["1m", "5m"]
  replay_speed: 1.0
```

### core/trade_guardian.py (248 lines)

**Purpose**: Pre-execution safety gate with rate limiting and sanity checks

**Key Classes**:
- `TradeGuardian`: Validate orders before submission
  - `validate_order(order, ltp, portfolio)`: Run all validation checks
  - `check_rate_limit()`: Enforce max orders per second
  - `check_lot_size(order)`: Verify lot size within limits
  - `check_slippage(order, ltp)`: Reject if expected slippage too high
  - `check_stale_price(ltp_timestamp)`: Reject if price data stale
  - `check_drawdown(portfolio)`: Halt trading if drawdown exceeded

**Safety Checks**:
1. Rate limiting (e.g., max 5 orders/second)
2. Lot size limits (e.g., max 50 lots)
3. Stale price rejection (e.g., > 3 seconds old)
4. Slippage threshold (e.g., > 2%)
5. Drawdown circuit breaker (e.g., > 3% daily drawdown)

**Configuration**:
```yaml
guardian:
  enabled: false
  max_order_per_second: 5
  max_lot_size: 50
  reject_if_price_stale_secs: 3
  reject_if_slippage_pct: 2.0
```

### core/universe_builder.py (169 lines)

**Purpose**: Build daily tradeable universe with filtering

**Key Functions**:
- `build_equity_universe(config)`: Build equity universe from NIFTY lists
- `filter_by_price(symbols, min_price)`: Filter out low-priced stocks
- `filter_by_liquidity(symbols, min_volume)`: Filter by volume
- `save_universe(universe, date)`: Save to artifacts/scanner/

**Configuration**:
```yaml
equity_universe_config:
  mode: "nifty_lists"
  include_indices: ["NIFTY50", "NIFTY100"]
  max_symbols: 120
  min_price: 100
```

**Output**: `artifacts/scanner/YYYY-MM-DD/universe.json`

### core/state_store.py (712 lines)

**Purpose**: Checkpoint management and state persistence

**Key Functions**:
- `save_checkpoint(state, checkpoint_name)`: Save state to JSON
- `load_checkpoint(checkpoint_name)`: Load state from JSON
- `record_strategy_signal(signal)`: Log strategy signal to JSONL
- `record_order(order)`: Log order to CSV
- `create_position_snapshot(positions)`: Save position snapshot

**File Locations**:
- Checkpoints: `artifacts/checkpoints/runtime_state_latest.json`
- Orders: `artifacts/orders_<engine>_<date>.csv`
- Signals: `artifacts/signals_<date>.csv`
- Snapshots: `artifacts/snapshots/positions_<timestamp>.json`

### core/kite_auth.py (127 lines)

**Purpose**: Kite Connect authentication helper

**Key Functions**:
- `login_kite()`: Interactive login flow to get access token
- `load_kite_credentials()`: Load API key and secret from secrets/
- `is_token_valid(token)`: Check if access token is still valid
- `refresh_token()`: Refresh expired token (not supported by Kite)

**Usage**:
```bash
python -m scripts.login_kite
# Opens browser, user logs in, token saved to secrets/kite_tokens.env
```

### Other Core Modules

| Module | Lines | Purpose |
|--------|-------|---------|
| **engine_bootstrap.py** | 516 | Initialize engines with config, universe, state |
| **market_context.py** | 684 | Market context filters (VIX, breadth, relative volume) |
| **reconciliation_engine.py** | 670 | Reconcile paper state with broker (for live mode) |
| **signal_quality.py** | 330 | Signal quality scoring and filtering |
| **strategy_orchestrator.py** | 332 | Strategy health monitoring and auto-disable |
| **trade_throttler.py** | 314 | Rate limiting and throttling for order placement |
| **scanner.py** | 410 | Technical scanner for pre-market filtering |
| **backtest_registry.py** | 286 | Backtest configuration registry |
| **atr_risk.py** | 220 | ATR-based stop-loss and position sizing |

---

## Engine Modules

The `engine/` directory contains the trading engines that orchestrate all components.

### engine/equity_paper_engine.py (1304 lines)

**Purpose**: Paper trading engine for equity stocks

**Key Class**: `EquityPaperEngine`

**Main Loop**:
```python
while is_market_open():
    for symbol in universe:
        # 1. Fetch historical candles
        df = fetch_historical(symbol, "5m", lookback=200)
        
        # 2. Calculate indicators
        indicators = strategy_engine.compute_indicators(df)
        
        # 3. Get current position
        position = portfolio_engine.get_position(symbol)
        
        # 4. Evaluate strategy
        intent = strategy_engine.evaluate(symbol, df, position)
        
        # 5. Check risk limits
        if risk_engine.check_entry_allowed(symbol, portfolio):
            # 6. Place order
            order = execution_engine.place_order(intent)
            
            # 7. Update position
            portfolio_engine.update_position(order)
        
    sleep(tick_interval)
```

**Responsibilities**:
- Load equity universe from scanner output
- Fetch 5-minute candles for each symbol
- Evaluate strategies via StrategyEngine v2
- Place orders via ExecutionEngine v3
- Track positions via PortfolioEngine
- Save state and orders to artifacts/

**Configuration**: Uses `configs/dev.yaml` under `equity_universe_config` section

### engine/paper_engine.py (3021 lines)

**Purpose**: Legacy paper trading engine for FnO futures (still actively used)

**Key Class**: `PaperEngine`

**Features**:
- Multi-timeframe strategy support
- FnO contract resolution (logical → actual contract)
- Multi-strategy orchestration
- Trade recorder integration
- Telemetry and health monitoring

**Responsibilities**:
- Resolve logical symbols (NIFTY) to contracts (NIFTY25DECFUT)
- Fetch candles for multiple timeframes
- Evaluate strategies (v1 bar-based strategies)
- Simulate fills via paper broker
- Update portfolio and state

**Note**: This is the original engine. New engines use ExecutionEngine v3, but this is still production-ready.

### engine/options_paper_engine.py (1203 lines)

**Purpose**: Paper trading engine for index options

**Key Class**: `OptionsPaperEngine`

**Features**:
- Strike selection logic (ATM, 1 OTM, 2 OTM, etc.)
- Option type selection (CE/PE) based on signal
- Options-specific risk parameters
- Greeks tracking (optional)

**Strike Selection**:
```python
# Example: NIFTY at 21,500, strike interval = 50
atm_strike = round(ltp / 50) * 50  # 21,500
otm_call_1 = atm_strike + 50       # 21,550
otm_put_1 = atm_strike - 50        # 21,450
```

**Responsibilities**:
- Fetch underlying LTP (e.g., NIFTY index)
- Calculate ATM strike
- Select strike based on strategy signal
- Construct option symbol (e.g., NIFTY25DEC21500CE)
- Place option orders via paper broker

**Configuration**: Uses `options_underlyings` from `configs/dev.yaml`

### engine/live_engine.py (820 lines)

**Purpose**: Live trading engine (unified for all asset classes)

**Key Class**: `LiveEngine`

**Features**:
- Real broker orders via Kite Connect
- Order status polling and reconciliation
- Error handling and retry logic
- Production-ready safety checks

**Differences from Paper**:
- Uses `LiveExecutionEngineV3` instead of paper broker
- Requires valid access token
- Reconciles with broker state every N seconds
- Circuit breakers enforced strictly

**Note**: Use with caution. Test thoroughly in paper mode first.

### Other Engine Modules

| Module | Lines | Purpose |
|--------|-------|---------|
| **execution_engine_v3_adapter.py** | 345 | Adapter to use ExecutionEngine v3 in legacy engines |
| **meta_strategy_engine.py** | 200 | Meta-strategy orchestration (swing vs intraday) |
| **execution_bridge.py** | 168 | Bridge between engines and execution layer |
| **bootstrap.py** | 133 | Engine initialization and setup |

---

## Analytics Modules

The `analytics/` directory contains performance tracking, telemetry, and learning engines.

### analytics/telemetry_bus.py (508 lines)

**Purpose**: Event-driven telemetry for orders, signals, positions

**Key Functions**:
- `publish_order_event(order)`: Log order to events.jsonl
- `publish_signal_event(signal)`: Log strategy signal
- `publish_position_event(position)`: Log position update
- `publish_engine_health(health)`: Log engine health metrics
- `get_telemetry_bus()`: Get singleton telemetry bus instance

**Event Format** (JSONL):
```json
{"event_type": "order", "timestamp": "2025-11-19T09:30:00", "order_id": "uuid", "symbol": "RELIANCE", "side": "BUY", "qty": 10, "status": "FILLED"}
{"event_type": "signal", "timestamp": "2025-11-19T09:30:00", "symbol": "RELIANCE", "signal": "BUY", "confidence": 0.75, "strategy": "EMA_20_50"}
```

**Output**: `artifacts/logs/events.jsonl`

### analytics/trade_journal.py (126 lines)

**Purpose**: Per-trade logging and analysis

**Key Functions**:
- `record_entry(order, position)`: Log trade entry
- `record_exit(order, position, pnl)`: Log trade exit with P&L
- `get_trade_history(symbol)`: Get all trades for a symbol

**Output**: `artifacts/journal/YYYY-MM-DD/trades.jsonl`

**Trade Entry Format**:
```json
{
  "trade_id": "uuid",
  "symbol": "RELIANCE",
  "entry_time": "2025-11-19T09:30:00",
  "entry_price": 2451.47,
  "qty": 80,
  "strategy": "EMA_20_50",
  "reason": "EMA crossover up"
}
```

### analytics/performance_v2.py (428 lines)

**Purpose**: Performance metrics calculation (Sharpe, drawdown, win rate)

**Key Functions**:
- `calculate_sharpe_ratio(returns, risk_free_rate)`: Sharpe ratio
- `calculate_max_drawdown(equity_curve)`: Maximum drawdown
- `calculate_win_rate(trades)`: Win rate percentage
- `calculate_profit_factor(trades)`: Profit factor (gross profit / gross loss)
- `generate_daily_report(portfolio, trades)`: Daily analytics summary

**Metrics Calculated**:
- Total P&L (realized + unrealized)
- Win rate (% of winning trades)
- Average win / average loss
- Profit factor
- Sharpe ratio
- Max drawdown (absolute and %)
- Calmar ratio (return / max drawdown)
- Recovery factor
- Trade count

**Output**: `artifacts/reports/daily/YYYY-MM-DD.json`

### analytics/trade_recorder.py (532 lines)

**Purpose**: CSV-based trade logging with detailed fill information

**Key Functions**:
- `record_order(order)`: Write order to CSV
- `record_fill(order, fill_details)`: Write fill event to CSV
- `get_orders_for_date(date)`: Load orders from CSV

**CSV Format**:
```csv
timestamp,order_id,symbol,side,qty,order_type,price,status,filled_qty,avg_fill_price,strategy,reason
2025-11-19 09:30:08,uuid-123,RELIANCE,BUY,80,MARKET,,FILLED,80,2451.47,EMA_20_50,EMA crossover up
```

### analytics/learning_engine.py (231 lines)

**Purpose**: Strategy parameter optimization (experimental)

**Key Features**:
- Analyze recent trade performance
- Suggest parameter adjustments (risk multipliers, thresholds)
- Save learned parameters to `configs/learned_overrides.yaml`

**Note**: Experimental feature, use with caution

### Other Analytics Modules

| Module | Lines | Purpose |
|--------|-------|---------|
| **strategy_analytics.py** | 517 | Per-strategy performance tracking |
| **risk_service.py** | 442 | Risk metrics calculation and monitoring |
| **multi_timeframe_engine.py** | 252 | Multi-timeframe indicator calculation |
| **multi_timeframe_scanner.py** | 222 | Multi-timeframe technical scanning |
| **strategy_performance.py** | 109 | Strategy-specific performance metrics |

---

## Strategy Modules

Strategies are organized across two directories:

### Legacy Strategies (strategies/)

| Module | Class | Strategy ID | Purpose |
|--------|-------|-------------|---------|
| **ema20_50_intraday_v2.py** | `EMA2050IntradayV2` | EMA_20_50 | EMA 20/50 crossover for intraday trading (v2) |
| **fno_intraday_trend.py** | `FnoIntradayTrendStrategy` | EMA_TREND | Multi-timeframe EMA trend for FnO (v1) |
| **equity_intraday_simple.py** | `EquityIntradaySimpleStrategy` | EQ_SIMPLE | Simple equity strategy (placeholder) |
| **mean_reversion_intraday.py** | `MeanReversionStrategy` | MEAN_REV | Mean reversion strategy (v1) |
| **base.py** | `BaseStrategy` | N/A | Base class for v1 strategies |

### Strategy v3 Modules (core/strategies_v3/)

| Module | Class | Strategy ID | Purpose |
|--------|-------|-------------|---------|
| **ema20_50.py** | `EMA2050Strategy` | ema20_50 | EMA crossover with trend strength |
| **trend_strategy.py** | `TrendStrategy` | trend | Generic trend following |
| **rsi_pullback.py** | `RSIPullbackStrategy` | rsi_pullback | RSI-based pullback entries |
| **vwap_filter.py** | `VWAPFilterStrategy` | vwap_filter | VWAP-based filter |
| **vol_regime.py** | `VolRegimeStrategy` | vol_regime | Volatility regime filter |
| **htf_trend.py** | `HTFTrendStrategy` | htf_trend | Higher timeframe trend filter |

**Configuration** (v3):
```yaml
strategies:
  - id: "ema20_50"
    enabled: true
  - id: "vwap_filter"
    enabled: true
```

---

## Broker Modules

The `broker/` directory contains broker adapters and execution routers.

| Module | Lines | Purpose |
|--------|-------|---------|
| **paper_broker.py** | ~500 | Paper broker with simulated fills |
| **live_broker.py** | ~400 | Live broker via Kite Connect |
| **backtest_broker.py** | ~300 | Backtest broker for historical simulation |
| **kite_client.py** | ~600 | Kite Connect API wrapper |
| **execution_router.py** | ~200 | Route orders to appropriate broker |
| **kite_bridge.py** | ~150 | Bridge between engines and Kite API |
| **auth.py** | ~100 | Authentication helpers |

---

## Data Modules

The `data/` directory contains data loaders and universe definitions.

| Module | Lines | Purpose |
|--------|-------|---------|
| **broker_feed.py** | ~400 | Fetch data from broker API |
| **instruments.py** | ~300 | Instrument list management |
| **options_instruments.py** | ~250 | Options chain data |
| **backtest_data.py** | ~200 | Historical data loader for backtests |
| **universe/nifty_lists.py** | ~150 | NIFTY 50/100 constituent lists |

---

## Risk Modules

The `risk/` directory contains risk management components.

| Module | Lines | Purpose |
|--------|-------|---------|
| **position_sizer.py** | ~300 | Dynamic position sizing (fixed qty, ATR-based) |
| **cost_model.py** | ~250 | Trading cost estimation (brokerage, STT, etc.) |
| **adaptive_risk_manager.py** | ~200 | Adaptive risk based on market conditions |
| **factory.py** | ~100 | Factory for creating risk components |

---

## Service Modules

The `services/` directory contains service layer for dashboard and IPC.

| Module | Lines | Purpose |
|--------|-------|---------|
| **portfolio_service.py** | ~400 | Portfolio state API |
| **execution_service.py** | ~300 | Execution API |
| **strategy_service_v3.py** | ~250 | Strategy management API |
| **dashboard_feed.py** | ~200 | Dashboard real-time feed |
| **event_bus.py** | ~150 | Event bus for IPC |
| **state/service_state.py** | ~200 | State management service |
| **risk_portfolio/service_risk_portfolio.py** | ~180 | Risk and portfolio service |

---

## Application Modules

The `apps/` directory contains application entry points.

| Module | Lines | Purpose |
|--------|-------|---------|
| **server.py** | ~700 | FastAPI server (dashboard backend) |
| **dashboard.py** | ~400 | Dashboard API routes |
| **dashboard_logs.py** | ~200 | Log streaming API |
| **run_equity_paper.py** | ~150 | Equity engine launcher |
| **run_fno_paper.py** | ~180 | FnO engine launcher |
| **run_options_paper.py** | ~160 | Options engine launcher |
| **run_service.py** | ~200 | Service launcher |

---

## Script Modules

The `scripts/` directory contains CLI scripts for various tasks.

| Script | Lines | Purpose |
|--------|-------|---------|
| **run_session.py** | ~900 | Market session orchestrator |
| **run_day.py** | ~600 | Start engines with config |
| **login_kite.py** | ~200 | Kite authentication |
| **run_analytics.py** | ~300 | Generate analytics report |
| **run_backtest_v3.py** | ~500 | Run backtest v3 |
| **run_indicator_scanner.py** | ~250 | Run market scanner |
| **analyze_paper_results.py** | ~200 | Analyze paper trading results |
| **show_paper_state.py** | ~100 | Display current paper state |

---

## UI Modules

The `ui/` directory contains dashboard frontend and backend.

| Module | Lines | Purpose |
|--------|-------|---------|
| **dashboard.py** | ~4000 | Dashboard backend (legacy routes) |
| **frontend/** | N/A | React + TypeScript frontend |
| **static-react/** | N/A | Built React app (static files) |

**Frontend Structure** (`ui/frontend/`):
```
src/
├── pages/          # 7 pages (Overview, Trading, Portfolio, Signals, Analytics, System, Logs)
├── components/     # Reusable UI components
├── services/       # API client (React Query)
├── hooks/          # Custom React hooks
├── utils/          # Utility functions
└── App.tsx         # Main app component
```

---

## Backtest Modules

The `backtest/` directory contains offline backtesting framework.

| Module | Lines | Purpose |
|--------|-------|---------|
| **engine_v3.py** | ~800 | Backtest engine v3 (reuses live components) |
| **runner.py** | ~400 | Backtest runner with reporting |
| **data_loader.py** | ~300 | Historical data loader |

**Features**:
- Runs completely offline on historical data
- Reuses StrategyEngine, PortfolioEngine, RiskEngine
- No broker connections required
- Structured outputs for analytics

---

## Module Dependencies

### Key Dependency Chains

```
Trading Engines (equity, FnO, options)
  ↓
Strategy Engine (v2 or v3)
  ↓
Indicators (EMA, RSI, ATR, VWAP, etc.)
  ↓
Execution Engine v3
  ↓
Broker (Paper or Live)
  ↓
Portfolio Engine
  ↓
State Store + Analytics
```

### Cross-Module Communication

```
Telemetry Bus (analytics/telemetry_bus.py)
  ← Orders (from ExecutionEngine)
  ← Signals (from StrategyEngine)
  ← Positions (from PortfolioEngine)
  ← Health (from Engines)
  → Events.jsonl (for analytics)
```

---

## Related Documentation

For more information, see:

- **[REPO_OVERVIEW.md](./REPO_OVERVIEW.md)**: High-level repository summary
- **[ARCHITECTURE.md](./ARCHITECTURE.md)**: Architecture and processes
- **[ENGINES.md](./ENGINES.md)**: Trading engine deep-dive
- **[STRATEGIES.md](./STRATEGIES.md)**: Strategy development guide
- **[DASHBOARD.md](./DASHBOARD.md)**: Dashboard and API docs
- **[RUNBOOKS.md](./RUNBOOKS.md)**: Operational runbook

---

**Last Updated**: 2025-11-19  
**Version**: 1.0
