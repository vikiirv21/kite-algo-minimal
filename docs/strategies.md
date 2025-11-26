# Strategy Documentation

**Last Updated:** 2025-11-26  
**Repository:** kite-algo-minimal

---

## Overview

This document describes the trading strategies implemented in the kite-algo-minimal system, including the current state, planned evolution, and integration details.

---

## Strategy Architecture

### Engine Hierarchy

```
StrategyEngineV2 (core/strategy_engine_v2.py)
    │
    ├── Manages strategy lifecycle
    ├── Computes indicators (EMA, RSI, ATR, SuperTrend)
    ├── Routes signals through RiskEngineV2
    │
    └── BaseStrategy (strategies/base.py)
            │
            ├── EMA2050IntradayV2 (strategies/ema20_50_intraday_v2.py)
            ├── EquityIntradaySimple (strategies/equity_intraday_simple.py)
            ├── FnOIntradayTrend (strategies/fno_intraday_trend.py)
            └── MeanReversionIntraday (strategies/mean_reversion_intraday.py)
```

### Signal Flow

```
Market Data (ticks)
    │
    ▼
MarketDataEngineV2 (candle building)
    │
    ▼
StrategyEngineV2 (indicator computation)
    │
    ▼
Strategy.generate_signal()
    │
    ▼
RiskEngineV2 (validation)
    │
    ▼
TradeGuardian (pre-execution checks)
    │
    ▼
ExecutionEngineV3 (order placement)
```

---

## Current Strategies

### EMA 20/50 Intraday v2

**File:** `strategies/ema20_50_intraday_v2.py`  
**Class:** `EMA2050IntradayV2`  
**Status:** ✅ Active (Primary Strategy)

#### Logic
- **Entry (BUY):** EMA 20 crosses above EMA 50, trend is up
- **Entry (SELL):** EMA 20 crosses below EMA 50, trend is down
- **Exit:** Opposite crossover signal, RSI extremes (>75 or <25)

#### Filters
- **Regime Filter:** Uses EMA 200 as trend filter
  - Below 200 EMA: Only shorts allowed
  - Above 200 EMA: Only longs allowed
- **Market Context Filter:** (when enabled)
  - Requires BULL/RANGE_UP for longs
  - Requires BEAR/RANGE_DOWN for shorts
  - Blocks entries during PANIC volatility regime
  - Skips low relative volume (RVOL < 0.5)

#### Confidence Calculation
- Base confidence from EMA separation (max 0.5)
- RSI alignment boost (+0.15)
- Trend alignment boost (+0.15)
- SuperTrend alignment boost (+0.20)

#### Configuration
```yaml
strategy_engine:
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

#### Scalping Mode
When `trading.strategy_mode: "multi"`, the strategy operates on both:
- **5m timeframe:** Intraday signals
- **1m timeframe:** Scalping signals

---

### Equity Intraday Simple

**File:** `strategies/equity_intraday_simple.py`  
**Status:** ✅ Available

Basic equity intraday strategy for testing and development.

---

### FnO Intraday Trend

**File:** `strategies/fno_intraday_trend.py`  
**Status:** ✅ Available

Trend-following strategy for Futures & Options.

---

### Mean Reversion Intraday

**File:** `strategies/mean_reversion_intraday.py`  
**Status:** ✅ Available

Mean reversion strategy for range-bound markets.

---

## Strategy Evolution: Signal Stack v2

The planned evolution adds multiple signal layers to improve entry quality and confluence.

### Current Signal Stack (v1)

```
EMA Crossover (20/50)
    │
    ▼
EMA 200 Regime Filter
    │
    ▼
RSI Extreme Exit
    │
    ▼
Market Context (optional)
    │
    ▼
SIGNAL
```

### Planned Signal Stack (v2)

```
┌─────────────────────────────────────────────────────────────┐
│                    SIGNAL GENERATION                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  EMA Crossover (20/50)                                      │
│       +                                                     │
│  Candle Patterns (hammer, engulfing, pinbar)                │
│       +                                                     │
│  Volume Spike Detection (RVOL)                              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    SIGNAL FILTERING                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ATR Volatility Filter (skip low-vol chop)                  │
│       +                                                     │
│  HTF Trend Filter (15m + 1h EMA alignment)                  │
│       +                                                     │
│  VWAP Position Filter (above/below VWAP)                    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    STRUCTURE CONFIRMATION                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Market Structure (BoS/CHoCH detection)                     │
│       +                                                     │
│  EMA 200 Regime Filter                                      │
│       +                                                     │
│  Market Context (VIX, breadth, relative volume)             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    OPTIONS-SPECIFIC (Phase 3)               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  OI/ΔOI Filter (buildup/unwinding)                          │
│       +                                                     │
│  IV Regime Filter (crush/expansion)                         │
│       +                                                     │
│  Orderflow Confirmation (optional)                          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
                      SIGNAL
```

---

## Phase 1: Entry Enhancement Modules

### Candle Pattern Module

**Planned File:** `core/candle_patterns.py`

#### Patterns to Detect

| Pattern | Description | Signal |
|---------|-------------|--------|
| Hammer | Small body, long lower wick, at support | Bullish reversal |
| Inverted Hammer | Small body, long upper wick, at support | Bullish reversal |
| Bullish Engulfing | Green candle engulfs previous red | Bullish continuation |
| Bearish Engulfing | Red candle engulfs previous green | Bearish continuation |
| Pinbar | Long rejection wick, small body | Reversal at key level |

#### Integration

```python
# Example usage in strategy
def generate_signal(self, candle, series, indicators, context):
    # Existing EMA logic
    ema_signal = self._check_ema_crossover(indicators)
    
    # NEW: Candle pattern confirmation
    pattern = detect_candle_pattern(candle, series[-3:])
    if pattern and pattern.direction == ema_signal.direction:
        confidence_boost = 0.15
    
    # Combine signals
    ...
```

### Volume Spike Detector

**Planned File:** `core/volume_detector.py`

#### Calculation

```python
def calculate_rvol(volumes: List[float], lookback: int = 20) -> float:
    """
    Calculate Relative Volume (RVOL).
    
    RVOL = current_volume / rolling_average_volume
    
    - RVOL > 1.5: Volume spike (bullish confirmation)
    - RVOL < 0.5: Low volume (weak signal)
    - RVOL 0.8-1.2: Normal volume
    """
    if len(volumes) < lookback:
        return 1.0  # Default to neutral
    
    avg_volume = sum(volumes[-lookback:]) / lookback
    current_volume = volumes[-1]
    
    return current_volume / avg_volume if avg_volume > 0 else 1.0
```

#### Integration

```yaml
# Config
volume_detector:
  enabled: true
  lookback: 20
  spike_threshold: 1.5
  low_volume_threshold: 0.5
```

### ATR Volatility Filter

**Planned File:** `core/volatility_filter.py`

#### Logic

| ATR % | Regime | Action |
|-------|--------|--------|
| < 0.3% | Low volatility | Skip signals (chop) |
| 0.3% - 1.0% | Normal | Trade normally |
| > 1.0% | High volatility | Reduce size or require extra confirmation |

#### Integration

```python
def should_trade(atr_pct: float, config: dict) -> bool:
    """
    Determine if volatility is suitable for trading.
    """
    if atr_pct < config.get("min_atr_pct", 0.003):
        return False  # Too choppy
    if atr_pct > config.get("max_atr_pct", 0.01):
        return config.get("allow_high_vol_trades", False)
    return True
```

---

## Phase 2: Higher Timeframe Filters

### HTF Trend Filter

**Planned File:** `core/htf_trend_filter.py`

#### Logic

1. Calculate EMA 20/50 on 15-minute chart
2. Calculate EMA 20/50 on 1-hour chart
3. Determine bias:
   - **BULLISH:** EMA 20 > EMA 50 on both timeframes
   - **BEARISH:** EMA 20 < EMA 50 on both timeframes
   - **MIXED:** Conflicting signals

#### Integration

```python
def get_htf_bias(symbol: str, htf_data: Dict[str, List[dict]]) -> str:
    """
    Get higher timeframe bias.
    
    Returns: "BULLISH", "BEARISH", or "MIXED"
    """
    # 15m analysis
    ema20_15m, ema50_15m = compute_ema(htf_data["15m"])
    bias_15m = "up" if ema20_15m > ema50_15m else "down"
    
    # 1h analysis
    ema20_1h, ema50_1h = compute_ema(htf_data["1h"])
    bias_1h = "up" if ema20_1h > ema50_1h else "down"
    
    if bias_15m == bias_1h == "up":
        return "BULLISH"
    elif bias_15m == bias_1h == "down":
        return "BEARISH"
    else:
        return "MIXED"
```

### VWAP Engine

**Planned File:** `core/vwap_engine.py`

#### Features

- Standard VWAP calculation
- VWAP bands (±1σ, ±2σ)
- Reversion signals (price returns to VWAP after deviation)
- Breakout signals (price breaks above/below VWAP with volume)

#### Calculation

```python
def calculate_vwap(candles: List[dict]) -> Tuple[float, float, float]:
    """
    Calculate VWAP and standard deviation bands.
    
    Returns: (vwap, upper_band_1sd, lower_band_1sd)
    """
    cum_volume = 0
    cum_tp_volume = 0  # Typical Price * Volume
    
    for candle in candles:
        tp = (candle["high"] + candle["low"] + candle["close"]) / 3
        vol = candle["volume"]
        cum_volume += vol
        cum_tp_volume += tp * vol
    
    vwap = cum_tp_volume / cum_volume if cum_volume > 0 else 0
    
    # Calculate standard deviation
    variance_sum = sum(
        ((c["high"] + c["low"] + c["close"]) / 3 - vwap) ** 2 * c["volume"]
        for c in candles
    )
    std_dev = (variance_sum / cum_volume) ** 0.5 if cum_volume > 0 else 0
    
    return vwap, vwap + std_dev, vwap - std_dev
```

### Market Structure Detection

**Planned File:** `core/market_structure.py`

#### Concepts

- **Swing High:** Local maximum where price reverses down
- **Swing Low:** Local minimum where price reverses up
- **Break of Structure (BoS):** Price breaks previous swing high/low in trend direction
- **Change of Character (CHoCH):** Price breaks previous swing opposite to current trend

#### Integration

Structure detection provides context for trade direction:
- In uptrend (higher highs, higher lows): Look for longs
- In downtrend (lower highs, lower lows): Look for shorts
- CHoCH signals potential trend reversal

---

## Phase 3: Options-Specific Intelligence

### OI Filters

**Planned File:** `core/oi_filter.py`

#### Metrics

| Metric | Calculation | Interpretation |
|--------|-------------|----------------|
| ΔOI | Current OI - Previous OI | Buildup vs. unwinding |
| PCR | Put OI / Call OI | Market sentiment |
| Max Pain | Strike with highest total OI | Likely expiry settlement |

#### Integration

```python
def should_trade_strike(strike: int, oi_data: dict) -> bool:
    """
    Determine if a strike is suitable for trading based on OI.
    """
    delta_oi = oi_data.get("delta_oi", 0)
    total_oi = oi_data.get("total_oi", 0)
    
    # Require meaningful OI
    if total_oi < config.get("min_oi", 10000):
        return False
    
    # Prefer strikes with OI buildup
    if delta_oi > 0:
        return True
    
    return False
```

### IV Regime

**Planned File:** `core/iv_regime.py`

#### Regime Classification

| IV Percentile | Regime | Trading Implication |
|---------------|--------|---------------------|
| < 20% | Very Low | Buy options (cheap premium) |
| 20-50% | Normal Low | Normal trading |
| 50-80% | Normal High | Normal trading |
| > 80% | Very High | Sell options (expensive premium) |

#### IV Crush Detection

```python
def detect_iv_crush_risk(iv_current: float, iv_30d_avg: float, days_to_expiry: int) -> bool:
    """
    Detect if IV crush is likely (e.g., before earnings or expiry).
    """
    iv_premium = iv_current / iv_30d_avg if iv_30d_avg > 0 else 1.0
    
    # High IV premium near expiry = crush risk
    if iv_premium > 1.3 and days_to_expiry <= 2:
        return True
    
    return False
```

---

## Adding a New Strategy

### Step 1: Create Strategy File

```python
# strategies/my_new_strategy.py
from strategies.base import BaseStrategy, Decision
from core.strategy_engine_v2 import StrategyState

class MyNewStrategy(BaseStrategy):
    def __init__(self, config: dict, strategy_state: StrategyState):
        super().__init__(config, strategy_state)
        self.name = "my_new_strategy"
    
    def generate_signal(self, candle, series, indicators, context):
        # Your logic here
        return Decision(action="HOLD", reason="no_signal", confidence=0.0)
```

### Step 2: Register in Config

```yaml
strategy_engine:
  strategies_v2:
    - id: MY_NEW_STRATEGY
      module: strategies.my_new_strategy
      class: MyNewStrategy
      enabled: true
      params:
        timeframe: "5m"
        # strategy-specific params
```

### Step 3: Add Tests

```python
# tests/test_my_new_strategy.py
def test_signal_generation():
    # Test your strategy logic
    pass
```

### Step 4: Respect Risk Limits

Ensure your strategy:
- Uses ATR-based stops when available
- Respects max trades per day/symbol
- Integrates with TradeGuardian validation
- Reports confidence scores for signal quality filtering

---

## Strategy Performance Tracking

### Metrics Collected

| Metric | Source | Dashboard Location |
|--------|--------|-------------------|
| Realized P&L | TradeRecorder | Overview tab |
| Win Rate | StrategyPerformance | Strategies tab |
| Average R | RiskMetrics | Analytics tab |
| Sharpe Ratio | PerformanceV2 | Analytics tab |
| Max Drawdown | RuntimeMetrics | Overview tab |

### Configuration

```yaml
analytics:
  enabled: true
  strategy_performance:
    enabled: true
    window: 50  # Rolling window for metrics
```

---

*See [roadmap.md](./roadmap.md) for the full implementation timeline.*
