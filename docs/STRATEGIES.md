# Strategies Documentation – kite-algo-minimal

> **Status**: CURRENT – Last updated: 2025-11-19  
> **Purpose**: Complete strategy enumeration and development guide

---

## Overview

This document maps all existing strategies, engines, and risk components in the kite-algo-minimal repository, explaining how they are wired together and how to extend them with market context awareness.

## Strategy Modules and Classes

### Strategy Engine Architecture

The repository supports two strategy engine architectures:

1. **Strategy Engine v1**: Legacy bar-based strategies (`strategies/fno_intraday_trend.py`, etc.)
2. **Strategy Engine v2**: Modern indicator-based strategies (`core/strategy_engine_v2.py`)

### Available Strategies

#### 1. EMA2050IntradayV2 (Strategy Engine v2)
- **Location**: `strategies/ema20_50_intraday_v2.py`
- **Class**: `EMA2050IntradayV2`
- **Strategy ID**: `EMA_20_50`
- **Description**: EMA 20/50 crossover strategy for intraday trading
- **Logic**:
  - BUY when EMA20 crosses above EMA50 and trend is up
  - SELL when EMA20 crosses below EMA50 and trend is down
  - Exit on opposite signal
  - Optional RSI overbought/oversold exits
- **Configuration**: `configs/dev.yaml` under `strategy_engine.strategies_v2`

#### 2. FnoIntradayTrendStrategy (Strategy Engine v1)
- **Location**: `strategies/fno_intraday_trend.py`
- **Class**: `FnoIntradayTrendStrategy`
- **Strategy ID**: `EMA_TREND`
- **Description**: Multi-timeframe EMA trend strategy for FnO
- **Logic**:
  - Uses dual EMAs for short and higher timeframe trend detection
  - Short TF: EMA9/EMA21
  - Higher TF: EMA21/EMA55
  - Signals on trend alignment transitions
- **Mode**: `SCALP`

#### 3. EquityIntradaySimpleStrategy (Strategy Engine v1)
- **Location**: `strategies/equity_intraday_simple.py`
- **Class**: `EquityIntradaySimpleStrategy`
- **Strategy ID**: `EQ_SIMPLE`
- **Description**: Placeholder equity strategy (currently returns HOLD)
- **Mode**: `INTRADAY`

#### 4. Mean Reversion Strategy
- **Location**: `strategies/mean_reversion_intraday.py`
- **Description**: Additional intraday strategy (implementation details in file)

### Strategy Engine v3 Strategies

Located in `core/strategies_v3/`, these are modern, composable strategies designed for the v3 multi-strategy fusion engine.

#### 1. EMA2050Strategy (v3)
- **File**: `core/strategies_v3/ema20_50.py`
- **Class**: `EMA2050Strategy`
- **Strategy ID**: `ema20_50`
- **Description**: EMA 20/50 crossover with trend alignment
- **Logic**:
  - BUY when: EMA20 > EMA50 AND price > EMA20 (bullish alignment)
  - SELL when: EMA20 < EMA50 AND price < EMA20 (bearish alignment)
- **Confidence**: 0.7 (base)
- **Timeframes**: Works on any timeframe (typically 5m or 15m)
- **Best For**: Trending markets

#### 2. TrendStrategy (v3)
- **File**: `core/strategies_v3/trend_strategy.py`
- **Class**: `TrendStrategy`
- **Strategy ID**: `trend`
- **Description**: Generic trend following using slope and moving averages
- **Logic**:
  - Identifies trend direction using EMA slope
  - Confirms with price position relative to EMA
  - Filters out choppy ranges
- **Confidence**: Variable (0.5-0.9 based on trend strength)
- **Best For**: Strong directional moves

#### 3. RSIPullbackStrategy (v3)
- **File**: `core/strategies_v3/rsi_pullback.py`
- **Class**: `RSIPullbackStrategy`
- **Strategy ID**: `rsi_pullback`
- **Description**: Counter-trend pullback entries using RSI
- **Logic**:
  - BUY when: Uptrend detected AND RSI < 40 (pullback in uptrend)
  - SELL when: Downtrend detected AND RSI > 60 (pullback in downtrend)
- **Confidence**: 0.65
- **Best For**: Trend + pullback setups

#### 4. VWAPFilterStrategy (v3)
- **File**: `core/strategies_v3/vwap_filter.py`
- **Class**: `VWAPFilterStrategy`
- **Strategy ID**: `vwap_filter`
- **Description**: VWAP-based entry filter
- **Logic**:
  - BUY only if price above VWAP (institutional buying)
  - SELL only if price below VWAP (institutional selling)
  - Acts as filter for other strategies
- **Confidence**: 0.6
- **Best For**: Institutional flow alignment

#### 5. VolRegimeStrategy (v3)
- **File**: `core/strategies_v3/vol_regime.py`
- **Class**: `VolRegimeStrategy`
- **Strategy ID**: `vol_regime`
- **Description**: Volatility regime classification
- **Logic**:
  - Measures ATR% (ATR / price)
  - Classifies as: LOW_VOL, NORMAL_VOL, HIGH_VOL
  - Adjusts strategy behavior based on regime
- **Confidence**: N/A (filter only)
- **Best For**: Risk management

#### 6. HTFTrendStrategy (v3)
- **File**: `core/strategies_v3/htf_trend.py`
- **Class**: `HTFTrendStrategy`
- **Strategy ID**: `htf_trend`
- **Description**: Higher timeframe trend filter
- **Logic**:
  - Checks trend on 15m or 1h timeframe
  - Only allows trades aligned with HTF trend
  - Prevents counter-trend trades
- **Confidence**: 0.8
- **Best For**: Multi-timeframe confirmation

### Strategy Engine v3 Configuration

**Example** (`configs/strategy_engine_v3.yaml`):
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

### Strategy Fusion

When multiple v3 strategies agree:
1. Signals are aggregated by action (BUY/SELL)
2. Confidence is weighted average of agreeing strategies
3. Setup is classified using playbooks
4. Final OrderIntent has combined confidence

**Example**:
```
ema20_50: BUY, confidence=0.7
htf_trend: BUY, confidence=0.8
vwap_filter: BUY, confidence=0.6

→ Fused: BUY, confidence=0.7, setup="trend_follow"
```

## Strategy Engine V2 Architecture

### Location
`core/strategy_engine_v2.py`

### Key Components

#### StrategyEngineV2 Class
The orchestrator for v2 strategies with:
- Unified indicator calculation
- Strategy registration and lifecycle management
- Conflict resolution when multiple strategies signal
- Integration with PortfolioEngine, RiskEngine, RegimeEngine
- Telemetry and health monitoring

#### BaseStrategy Class
Abstract base class for v2 strategies requiring:
- `generate_signal()` method: Takes candle, series, indicators → returns Decision
- Helper methods: `long()`, `short()`, `exit()`, `position_is_long()`, `position_is_short()`

#### OrderIntent Dataclass
Standardized format for trading decisions:
```python
@dataclass
class OrderIntent:
    symbol: str
    signal: str  # "BUY", "SELL", "EXIT", "HOLD"
    side: str  # "LONG", "SHORT", "FLAT"
    logical: str  # Logical symbol (e.g., "NIFTY")
    timeframe: str
    strategy_id: str
    confidence: float  # 0.0 to 1.0
    qty_hint: Optional[int]
    reason: str
    extra: Dict[str, Any]
```

### Strategy Registration

Strategies are loaded via `from_config()` class method:

1. Reads `config["strategy_engine"]["strategies_v2"]` list
2. For each strategy config:
   - Imports module: `importlib.import_module(module_name)`
   - Gets class: `getattr(mod, class_name)`
   - Creates StrategyState instance
   - Instantiates strategy: `strategy_class(config, state)`
   - Registers: `engine.register_strategy(strategy_id, strategy)`

**Example config entry** (`configs/dev.yaml`):
```yaml
strategy_engine:
  engine: v2
  version: 2
  enabled: true
  primary_strategy_id: EMA_20_50
  
  strategies_v2:
    - id: EMA_20_50
      module: strategies.ema20_50_intraday_v2
      class: EMA2050IntradayV2
      enabled: true
      params:
        timeframe: "5m"
        min_rr: 1.5
        max_risk_per_trade_pct: 0.01
        min_trend_strength: 0.4
        min_confidence: 0.55
```

### Evaluation Flow

`StrategyEngineV2.evaluate()` is the main entry point:
1. Receives: logical symbol, actual symbol, timeframe, candle, indicators
2. Gets primary strategy from config
3. Calls `strategy.generate_signal(candle, series, indicators)`
4. Converts Decision → OrderIntent
5. Returns (OrderIntent, debug_payload)

## Portfolio Engine V1

### Location
`core/portfolio_engine.py`

### Purpose
Position sizing and capital management:
- Per-strategy capital budgets
- Exposure limits (total and per-symbol)
- Position sizing modes:
  - `fixed_qty`: Fixed quantity per trade
  - `fixed_risk_atr`: ATR-based volatility sizing

### Configuration
```yaml
portfolio:
  max_leverage: 2.0
  max_exposure_pct: 0.8
  max_risk_per_trade_pct: 0.01
  max_risk_per_strategy_pct: 0.2
  position_sizing_mode: "fixed_qty"
  default_fixed_qty: 1
  lot_size_fallback: 25
  atr_stop_multiplier: 2.0
  
  strategy_budgets:
    ema20_50_intraday:
      capital_pct: 0.3
      fixed_qty: 1
```

### Key Methods
- `get_equity()`: Current equity from state store
- `compute_strategy_budget(strategy_code)`: Max capital for strategy
- `compute_position_size(intent, last_price, atr_value)`: Calculate quantity
- `_apply_exposure_limits()`: Enforce max exposure rules

### Adaptive Risk Logic
The repository includes adaptive risk management in:
- `risk/adaptive_risk_manager.py`: Dynamic risk scaling based on market conditions
- `risk/position_sizer.py`: Position sizing with `risk_scale` and `lot_scale` parameters
- `core/atr_risk.py`: ATR-based stop loss and take profit computation

## Trade Throttler

### Location
`core/trade_throttler.py`

### Purpose
Pre-execution trade limits and circuit breakers:
- Max trades per symbol per day
- Max trades per strategy per day
- Max total trades per day
- Daily drawdown limits
- Loss streak protection
- Minimum edge requirements

### Configuration
```yaml
# Embedded in throttler initialization
max_trades_per_symbol_per_day: 20
max_trades_per_strategy_per_day: 80
max_total_trades_per_day: 300
max_daily_drawdown_pct: 0.02  # 2%
max_loss_streak: 5
min_edge_vs_cost_rupees: 50.0
```

### Key Methods
- `should_allow_entry()`: Check if trade is allowed
- `register_fill()`: Record executed trade
- `quality_summary()`: Dashboard metrics

## Trade Guardian

### Location
`core/trade_guardian.py`

### Purpose
Pre-execution safety gate validating:
- Stale price detection
- Quantity validation (max lot size)
- Trade rate limiting (orders per second)
- Slippage sanity checks
- PnL-based circuit breakers

### Configuration
```yaml
guardian:
  enabled: false  # DISABLED by default
  max_order_per_second: 5
  max_lot_size: 50
  reject_if_price_stale_secs: 3
  reject_if_slippage_pct: 2.0
  max_daily_drawdown_pct: 3.0
  halt_on_pnl_drop_pct: 5.0
```

### Key Methods
- `validate_pre_trade(intent, market_snapshot)`: Returns GuardianDecision

## Regime Engine V2

### Location
`core/regime_engine.py`

### Purpose
Real-time market regime detection:
- Trend classification (up/down/chop)
- Volatility detection (low/normal/high)
- Market structure (breakout/range/compression)

### Integration
- Used by StrategyEngineV2 for regime-aware indicator enrichment
- Used by PortfolioEngine for regime-based position sizing adjustments
- Used by TradeGuardian for regime-specific validation rules

## Paper Engines (FnO, Equity, Options)

### Locations
- `engine/paper_engine.py`: Base PaperEngine class
- `engine/equity_paper_engine.py`: Equity-specific implementation
- `apps/run_fno_paper.py`: FnO standalone process
- `apps/run_equity_paper.py`: Equity standalone process
- `apps/run_options_paper.py`: Options standalone process

### Configuration Wiring

Each engine type is configured in `configs/dev.yaml`:

#### FnO Universe
```yaml
trading:
  fno_universe:
    - "NIFTY"
    - "BANKNIFTY"
    - "FINNIFTY"
```

#### Equity Universe
```yaml
trading:
  equity_universe: []  # Managed via config/universe_equity.csv
  
  equity_universe_config:
    mode: "nifty_lists"
    include_indices: ["NIFTY50", "NIFTY100"]
    max_symbols: 120
    min_price: 100
```

#### Options Underlyings
```yaml
trading:
  options_underlyings:
    - "NIFTY"
    - "BANKNIFTY"
    - "FINNIFTY"
```

### Engine Flow
1. Load config and build universe
2. Initialize components:
   - StateStore, JournalStateStore
   - MarketDataEngine
   - StrategyEngineV2 (if enabled)
   - PortfolioEngine
   - RiskEngine
   - RegimeEngine
   - TradeThrottler
   - TradeGuardian
3. Main loop:
   - Fetch market data
   - Update regime
   - For each symbol:
     - Get candles and indicators
     - Call StrategyEngineV2.evaluate()
     - Apply risk checks
     - Size position via PortfolioEngine
     - Validate via TradeGuardian
     - Execute via PaperBroker

## Market Context Integration (NEW)

### Overview
The MarketContext layer adds broad market awareness to trading decisions:
- India VIX regime classification
- Market breadth (advances/declines, % above EMAs)
- Symbol relative volume

### Implementation Location
`core/market_context.py` (✅ implemented)

### Design Principles
1. **Conservative**: Only adds filters, never loosens entry rules
2. **Configurable**: All features can be enabled/disabled in config
3. **Robust**: Graceful fallback when data is unavailable
4. **Non-breaking**: Existing strategies work without modification

### Quick Start

#### 1. Enable MarketContext
Edit `configs/dev.yaml`:
```yaml
market_context:
  enabled: true  # Activate the feature
```

#### 2. Run Paper Trading
```bash
python -m apps.run_fno_paper --config configs/dev.yaml --mode paper
```

MarketContext will:
- Fetch India VIX every 60 seconds (cached)
- Compute breadth from NIFTY50 universe
- Calculate relative volume for each symbol
- Apply filters to entry signals

#### 3. Monitor Impact
Check logs for filtered signals:
```
[INFO] Signal: NIFTY BUY blocked - market_context_weak_breadth_25.3%_low_confidence_0.65
[INFO] Signal: BANKNIFTY SELL blocked - market_context_vix_panic_no_shorts
[INFO] Signal: FINNIFTY BUY blocked - market_context_low_rvol_0.55
```

### MarketContext Dataclass
```python
@dataclass
class MarketContext:
    # VIX metrics
    vix_value: float
    vix_regime: str  # "low", "normal", "high", "panic"
    
    # Breadth metrics
    advances: int
    declines: int
    unchanged: int
    pct_above_20ema: float
    pct_above_50ema: float
    
    # Relative volume (per symbol)
    symbol_rvol: Dict[str, float]
    
    # Timestamp
    timestamp: datetime
```

### Usage in Strategies

Strategies receive MarketContext via indicators dict:
```python
def generate_signal(self, candle, series, indicators):
    context = indicators.get("market_context")
    if context:
        # Apply VIX filters
        if context.vix_regime == "panic" and signal == "SELL":
            return Decision("HOLD", reason="vix_panic_no_shorts")
        
        # Apply breadth filters
        if context.pct_above_20ema < 0.3 and signal == "BUY":
            # Require stronger edge when breadth is weak
            if confidence < 0.7:
                return Decision("HOLD", reason="weak_breadth_low_confidence")
        
        # Apply RVOL filters
        rvol = context.symbol_rvol.get(symbol, 1.0)
        if rvol < 0.7:
            return Decision("HOLD", reason="low_relative_volume")
    
    # ... rest of strategy logic
```

### Configuration
```yaml
market_context:
  enabled: true
  
  vix:
    enabled: true
    symbol: "INDIA VIX"  # Kite instrument token
    low_threshold: 12.0
    normal_threshold: 18.0
    high_threshold: 25.0
    panic_threshold: 35.0
  
  breadth:
    enabled: true
    universe: "NIFTY50"  # Which universe to compute breadth for
    ema_periods: [20, 50]
  
  relative_volume:
    enabled: true
    lookback_periods: 20  # Average volume over N periods
    min_rvol: 0.7  # Minimum relative volume to enter
  
  filters:
    block_shorts_on_panic: true
    require_stronger_edge_on_weak_breadth: true
    skip_low_rvol: true
```

## Running Backtests

### Location
`scripts/run_backtest.py` (primary)
`scripts/run_backtest_v3.py` (v3 engine)
`backtest/engine_v3.py` (backtest engine implementation)

### Running Backtests

#### Basic Backtest (v3 Engine)
```bash
python -m scripts.run_backtest_v3 \
    --config configs/dev.yaml \
    --symbols NIFTY,BANKNIFTY \
    --start 2025-01-01 \
    --end 2025-01-31 \
    --timeframe 5m
```

#### With MarketContext Enabled
MarketContext works automatically in backtests if enabled in config:

1. **Enable in config** (`configs/dev.yaml`):
```yaml
market_context:
  enabled: true  # Enable for both live and backtest
```

2. **Run backtest normally**:
```bash
python -m scripts.run_backtest_v3 \
    --config configs/dev.yaml \
    --symbols NIFTY,BANKNIFTY \
    --start 2025-01-01 \
    --end 2025-01-31
```

The backtest engine will:
- Build MarketContext for each bar
- Pass to StrategyEngineV2
- Apply filters (VIX, breadth, RVOL)
- Record filtered signals in results

#### Strict Mode (No Parameter Loosening)
All MarketContext filters are conservative by default:
```yaml
market_context:
  enabled: true
  filters:
    block_shorts_on_panic: true  # Only blocks, never loosens
    require_stronger_edge_on_weak_breadth: true
    skip_low_rvol: true
```

No additional "strict mode" flag needed - filters are already conservative.

### Backtest Outputs

Results are written to `artifacts/analytics/backtests/`:
```
artifacts/analytics/backtests/
├── backtest_20250101_20250131.json      # Trade log
├── backtest_20250101_20250131_summary.json  # Metrics summary
└── backtest_20250101_20250131_equity.csv    # Equity curve
```

**Metrics Included**:
- Total trades (with and without MarketContext filters)
- Win rate
- Profit factor
- Max drawdown
- Sharpe ratio
- Total PnL
- Average trade PnL
- Max consecutive wins/losses
- Filter statistics (how many trades blocked by each filter)

### Analyzing MarketContext Impact

To see how MarketContext affects results:

1. **Run without MarketContext**:
```bash
# Disable in config
market_context:
  enabled: false

python -m scripts.run_backtest_v3 --config configs/dev.yaml ...
# Save results as baseline
```

2. **Run with MarketContext**:
```bash
# Enable in config
market_context:
  enabled: true

python -m scripts.run_backtest_v3 --config configs/dev.yaml ...
# Compare results
```

3. **Compare metrics**:
   - Trade count (how many filtered)
   - Win rate (quality improvement)
   - Max drawdown (risk reduction)
   - Profit factor (efficiency)

### Backtest Configuration
```yaml
# configs/backtest.dev.yaml (optional - overrides dev.yaml)
backtest:
  data_source: "csv"  # or "kite_historical"
  data_directory: "data/historical"
  
  replay_speed: 1.0  # 1.0 = real-time, 10.0 = 10x faster
  
  # Use same strategy config as live/paper
  strategy_engine:
    # ... same as dev.yaml
  
  # MarketContext (uses same config as live)
  market_context:
    enabled: true
    # ... same settings as dev.yaml
  
  # Backtest-specific settings
  initial_capital: 500000
  commission_per_trade: 40  # Round-trip brokerage
  
  # Write detailed logs
  verbose_logging: true
  log_filtered_signals: true  # Log signals blocked by MarketContext
```

### Example: Testing MarketContext VIX Filter

```bash
# 1. Baseline: No MarketContext
python -m scripts.run_backtest_v3 \
    --config configs/dev.yaml \
    --symbols NIFTY,BANKNIFTY \
    --start 2020-03-01 \
    --end 2020-05-31 \
    --timeframe 5m
# Note: March 2020 had COVID volatility spike

# 2. With VIX filter
# Edit config to enable market_context
python -m scripts.run_backtest_v3 \
    --config configs/dev.yaml \
    --symbols NIFTY,BANKNIFTY \
    --start 2020-03-01 \
    --end 2020-05-31 \
    --timeframe 5m

# Expected result: Fewer short entries during panic period
# Better risk-adjusted returns
```

## Analytics and Monitoring

### Trade Journal
- Location: `artifacts/journal/trades_YYYYMMDD.csv`
- Fields: See `analytics/trade_journal.py` for schema
- Auto-finalized trades with entry/exit details

### Telemetry
- Real-time metrics published via `analytics/telemetry_bus.py`
- Dashboard access at `http://localhost:9000`
- Metrics include:
  - Engine health
  - Strategy signals
  - Order events
  - Position updates
  - Decision traces

### Learning Engine
- Location: `analytics/learning_engine.py`
- Auto-adjusts strategy parameters based on performance
- Disabled by default: `learning_engine.enabled: false`

## Extending Strategies

### Adding a New Strategy (v2)

1. **Create strategy file**: `strategies/my_strategy.py`
```python
from core.strategy_engine_v2 import BaseStrategy, StrategyState
from strategies.base import Decision

class MyStrategy(BaseStrategy):
    def __init__(self, config, strategy_state):
        super().__init__(config, strategy_state)
        self.name = "my_strategy"
        # ... load params from config
    
    def generate_signal(self, candle, series, indicators):
        # ... strategy logic
        return Decision(action="BUY", reason="my_logic", confidence=0.8)
```

2. **Register in config**: Add to `configs/dev.yaml`
```yaml
strategy_engine:
  strategies_v2:
    - id: MY_STRATEGY
      module: strategies.my_strategy
      class: MyStrategy
      enabled: true
      params:
        my_param: 123
```

3. **Set as primary** (optional):
```yaml
strategy_engine:
  primary_strategy_id: MY_STRATEGY
```

### Adding MarketContext Awareness

Update `generate_signal()` to check context:
```python
def generate_signal(self, candle, series, indicators):
    context = indicators.get("market_context")
    
    # ... compute base signal
    
    if context and context.vix_regime == "panic":
        # Adjust logic for high VIX
        pass
    
    return decision
```

## Future Enhancements

Potential additions to the strategy framework:
- [ ] Multi-leg options strategies (spreads, straddles)
- [ ] Machine learning signal ensemble
- [ ] Order book imbalance signals
- [ ] Cross-asset correlation filters
- [ ] Sentiment analysis integration
- [ ] News event filters
- [ ] Sector rotation signals

## References

- **Strategy Engine v2**: `docs/STRATEGY_ENGINE_V2.md`
- **Portfolio Engine**: `docs/PORTFOLIO_ENGINE_V1.md`
- **Backtest Engine**: `docs/BACKTEST_ENGINE_V3.md`
- **Multi-Process Architecture**: `docs/MULTIPROCESS_ARCHITECTURE.md`
- **Trade Guardian**: `docs/TRADE_GUARDIAN_SUMMARY.md`
- **Regime Engine**: `docs/PR_SUMMARY_REGIME_ENGINE_V2.md`

## Support

For questions or issues, refer to:
- Repository: https://github.com/vikiirv21/kite-algo-minimal
- Documentation: `docs/` directory
- Config examples: `configs/` directory
