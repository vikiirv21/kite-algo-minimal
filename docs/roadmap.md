# Kite-Algo-Minimal Roadmap

**Last Updated:** 2025-11-26  
**Repository:** kite-algo-minimal

---

## Overview

This roadmap outlines the planned evolution of the trading system, with a focus on building a richer signal stack for NIFTY/BANKNIFTY/FINNIFTY index options trading. The current system uses EMA 20/50 crossover strategies; this document describes the phased approach to add more sophisticated signal generation, filtering, and market structure awareness.

---

## Current State

### Engines
| Engine | Script | Status | Mode |
|--------|--------|--------|------|
| Paper Equity | `scripts/run_paper_equity.py` | ✅ Active | Paper |
| Paper FnO | `scripts/run_paper_fno.py` | ✅ Active | Paper |
| Paper Options | `scripts/run_paper_options.py` | ✅ Active | Paper |
| Live Equity | `scripts/run_live_equity.py` | ✅ Active | Live (dry_run=true default) |
| Live Options | `scripts/run_paper_options.py` + `configs/live.yaml` | ✅ Active | Live (dry_run=true) |

### Strategy Stack
| Strategy | Timeframe | Status |
|----------|-----------|--------|
| EMA_20_50 Intraday | 5m | ✅ Active |
| EMA_20_50_SCALP | 1m | ✅ Active |

### What's Missing
- ❌ Candle pattern recognition (hammer, engulfing, pinbar, etc.)
- ❌ Volume spike detection
- ❌ VWAP-based signals (bands, reversion, breakout)
- ❌ Higher timeframe (HTF) trend confirmation (15m, 1h)
- ❌ Market structure detection (BoS/CHoCH)
- ❌ Options-specific filters (OI, IV regimes)

---

## Signal Stack v2 Roadmap

### Phase 1: Core Signal Enhancements (Short Term, Options Focus)

**Target:** Dry-run live mode for NIFTY/BANKNIFTY/FINNIFTY options

**Scope:**

- [ ] **Candle Pattern Module** (`core/candle_patterns.py`)
  - Hammer / Inverted Hammer detection
  - Pinbar (rejection wick) identification
  - Engulfing pattern (bullish/bearish)
  - Pattern scoring/confidence calculation
  - Integration with StrategyEngineV2

- [ ] **Volume Spike Detector** (`core/volume_detector.py`)
  - Rolling average volume calculation
  - Relative volume (RVOL) ratio computation
  - Spike threshold configuration
  - Per-symbol volume normalization

- [ ] **ATR-Based Volatility Filter** (`core/volatility_filter.py`)
  - ATR calculation with configurable lookback
  - Low volatility regime detection (avoid chop)
  - High volatility regime detection (reduce size or skip)
  - Integration with signal gating

- [ ] **Strategy Integration**
  - Hook candle patterns into StrategyEngineV2
  - Combine volume + pattern signals for confluence
  - Add pattern-based entry/exit rules to options engine
  - Enable signal filtering for NIFTY/BANKNIFTY/FINNIFTY

**Constraints:**
- Live mode will remain `execution.dry_run = true`
- Only options engine will be considered "active" in live mode for now
- Equity/FnO live engines will be wired later, mirroring paper design
- All new modules must respect central risk limits (see Risk and Controls)

**Success Criteria:**
- Candle patterns detected with >80% accuracy on historical data
- Volume spike detection with configurable sensitivity
- ATR filter blocks signals during low-volatility chop
- No runtime code changes to live execution path (dry_run remains true)

---

### Phase 2: Higher Timeframe & Market Structure

**Target:** Add HTF confirmation and market structure awareness

**Scope:**

- [ ] **HTF Trend Filter** (`core/htf_trend_filter.py`)
  - 15-minute EMA 20/50 bias calculation
  - 1-hour EMA 20/50 bias calculation
  - HTF trend alignment scoring
  - Trade direction gating based on HTF trend

- [ ] **VWAP Engine** (`core/vwap_engine.py`)
  - Standard VWAP calculation
  - VWAP band computation (±1σ, ±2σ)
  - Reversion signals (price return to VWAP)
  - Breakout signals (VWAP band breakout)
  - Anchored VWAP support (session start, swing points)

- [ ] **Market Structure Detection** (`core/market_structure.py`)
  - Swing high/low identification
  - Break of Structure (BoS) detection
  - Change of Character (CHoCH) detection
  - Structure-based bias determination

**Integration:**
- HTF filter as optional gate for EMA signals
- VWAP as entry/exit refinement layer
- Structure detection for trend/range regime classification

**Success Criteria:**
- HTF filter correctly aligns trades with higher timeframe trend
- VWAP signals generate actionable reversion/breakout alerts
- BoS/CHoCH detection matches manual chart analysis

---

### Phase 3: Options-Specific & Advanced Filters

**Target:** Enhance options trading with market-specific intelligence

**Scope:**

- [ ] **Open Interest (OI) Filters** (`core/oi_filter.py`)
  - OI change (ΔOI) tracking
  - Put-Call ratio computation
  - OI buildup/unwinding detection
  - Strike-level OI analysis

- [ ] **Implied Volatility (IV) Regime** (`core/iv_regime.py`)
  - IV percentile calculation
  - IV crush/expansion detection
  - Volatility regime classification (low/normal/high/panic)
  - IV-adjusted position sizing

- [ ] **Advanced Orderflow Filters** (`core/orderflow_filters.py`)
  - Liquidity sweep detection
  - Absorption pattern identification
  - Imbalance detection
  - Order block mapping (optional)

**Integration:**
- OI filters for options strike selection
- IV regime for entry timing and position sizing
- Orderflow filters as confluence signals

**Success Criteria:**
- OI analysis provides actionable strike recommendations
- IV regime correctly identifies optimal entry windows
- Orderflow patterns align with price action

---

## Risk and Controls

All new strategies and signal modules **must** respect the central risk limits defined in `configs/live.yaml` and enforced by the risk engine.

### Trade Throttling
| Control | Config Key | Default |
|---------|------------|---------|
| Max orders per second | `guardian.max_order_per_second` | 5 |
| Max lot size | `guardian.max_lot_size` | 50 |
| Reject on stale price | `guardian.reject_if_price_stale_secs` | 3s |
| Reject on slippage | `guardian.reject_if_slippage_pct` | 2% |

### Per-Trade Risk
| Control | Config Key | Default |
|---------|------------|---------|
| Max loss per trade | `risk_engine.max_loss_per_trade_pct` | 1% |
| Scalping risk per trade | `risk.scalping_risk_pct_per_trade` | 0.25% |
| Intraday risk per trade | `risk.intraday_risk_pct_per_trade` | 0.75% |
| Hard SL cap | `risk_engine.hard_sl_pct_cap` | 3% |
| Hard TP cap | `risk_engine.hard_tp_pct_cap` | 6% |

### Trade Limits
| Control | Config Key | Default |
|---------|------------|---------|
| Max trades per symbol (scalping) | `risk.max_scalping_trades_per_symbol` | 10 |
| Max trades per symbol (intraday) | `risk.max_intraday_trades_per_symbol` | 3 |
| Max trades per day | `risk.max_total_trades_per_day` | 200 |
| Max trades per strategy per day | `circuit_breakers.max_trades_per_strategy_per_day` | 50 |

### Daily Drawdown & Kill Switch
| Control | Config Key | Default |
|---------|------------|---------|
| Max daily drawdown | `guardian.max_daily_drawdown_pct` | 3% |
| Halt on PnL drop | `guardian.halt_on_pnl_drop_pct` | 5% |
| Max daily loss (rupees) | `circuit_breakers.max_daily_loss_rupees` | ₹5,000 |
| Max loss streak | `circuit_breakers.max_loss_streak` | 5 |

### Risk Policy for New Strategies
1. **Inheritance:** All new strategies must inherit from `BaseStrategy` and use `StrategyEngineV2`
2. **Risk Engine Integration:** Signal generation must pass through `RiskEngineV2` validation
3. **Guardian Validation:** All entries must pass `TradeGuardian` pre-execution checks
4. **ATR-Based Sizing:** Use ATR-based stop loss/take profit where available
5. **Position Limits:** Respect `portfolio.max_exposure_pct` and `portfolio.max_risk_per_trade_pct`

---

## Dashboard Alignment

The dashboard should evolve to display the richer signal stack. Planned enhancements:

### Signal Visualization
- [ ] **Signal Type Breakdown**
  - EMA crossover signals
  - Candle pattern signals
  - Volume spike signals
  - VWAP signals
  - HTF confirmation status

### Regime Display
- [ ] **Market Regime Panel**
  - Trending vs. Choppy classification
  - High vs. Low volatility indicator
  - VIX regime (if available)
  - HTF trend bias (bullish/bearish/neutral)

### Strategy Performance
- [ ] **Per-Strategy Metrics**
  - Realized P&L by strategy
  - Win rate / hit rate
  - Average R-multiple
  - Sharpe ratio
  - Max drawdown

### Options-Specific Dashboard
- [ ] **Options Intelligence Panel** (Phase 3)
  - OI heatmap by strike
  - IV percentile display
  - Put-Call ratio trend
  - Greeks snapshot (optional)

---

## Timeline Summary

| Phase | Focus | Duration | Live Mode |
|-------|-------|----------|-----------|
| Phase 1 | Candle patterns, volume, ATR filter | 2-4 weeks | dry_run=true (options only) |
| Phase 2 | HTF trend, VWAP, market structure | 4-6 weeks | dry_run=true |
| Phase 3 | OI, IV regimes, orderflow | 6-8 weeks | Gradual live enablement |

---

## Next Concrete Coding Steps

After this planning phase is complete, the first coding tasks will be:

1. **Create `core/candle_patterns.py`**
   - Implement `detect_hammer()`, `detect_engulfing()`, `detect_pinbar()`
   - Add unit tests in `tests/test_candle_patterns.py`
   - Integration test with historical NIFTY data

2. **Create `core/volume_detector.py`**
   - Implement `calculate_rvol()` with rolling window
   - Add spike threshold configuration
   - Add unit tests

3. **Create `core/volatility_filter.py`**
   - Implement ATR-based low/high volatility detection
   - Add integration with signal gating
   - Add unit tests

4. **Update `strategies/ema20_50_intraday_v2.py`**
   - Add optional candle pattern filter
   - Add optional volume confirmation
   - Add optional volatility gate

5. **Update Dashboard**
   - Add signal type column to signals table
   - Add regime indicator to header

---

*This roadmap is a living document. Update as phases complete and priorities shift.*
