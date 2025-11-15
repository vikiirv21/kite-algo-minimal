# Trading Strategies

## Overview

This document lists all implemented trading strategies in the system.

## Strategy List

### MeanReversionIntradayStrategy

**File**: `strategies/mean_reversion_intraday.py`

---

### FnoIntradayTrendStrategy

**File**: `strategies/fno_intraday_trend.py`

---


## Strategy Structure

All strategies inherit from `BaseStrategy` and implement:

```python
class MyStrategy(BaseStrategy):
    def generate_signal(self, symbol, candles, ltp, metadata):
        # Strategy logic here
        return OrderIntent(...) or None
```

## Strategy Types

### Trend Following
- EMA crossover strategies
- Momentum-based entries
- Trend confirmation filters

### Mean Reversion
- Bollinger Band reversions
- RSI oversold/overbought
- Support/resistance bounces

### Breakout
- Range breakouts
- Volume-confirmed breakouts
- Volatility-based entries

## Strategy Configuration

Strategies are configured in `configs/config.yaml`:

```yaml
strategies:
  EMA_20_50:
    enabled: true
    timeframe: "5m"
    symbols: ["NIFTY", "BANKNIFTY"]
    params:
      fast_period: 20
      slow_period: 50
```

## Adding New Strategies

1. Create new file in `strategies/` directory
2. Inherit from `BaseStrategy`
3. Implement `generate_signal()` method
4. Register in `core/strategy_registry.py`
5. Add configuration in `configs/config.yaml`
6. Test in paper mode first

---
*Auto-generated on 2025-11-15T21:49:59.737608+00:00*
