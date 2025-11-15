# Technical Indicators

## Overview

The `core/indicators.py` module provides a unified indicator library with vectorized, efficient calculations for technical analysis.

## Features

- **Vectorized**: Efficient numpy-based calculations
- **Flexible**: Returns single values or full series
- **Dependency-Light**: No pandas required
- **Well-Tested**: Comprehensive test coverage

## Available Indicators

### `ema()`

Calculates EMA indicator.

### `sma()`

Calculates SMA indicator.

### `rsi()`

Calculates RSI indicator.

### `atr()`

Calculates ATR indicator.

### `supertrend()`

Calculates SUPERTREND indicator.

### `bollinger()`

Calculates BOLLINGER indicator.

### `vwap()`

Calculates VWAP indicator.

### `slope()`

Calculates SLOPE indicator.

### `hl2()`

Calculates HL2 indicator.

### `hl3()`

Calculates HL3 indicator.


## Usage Examples

### EMA (Exponential Moving Average)

```python
from core import indicators

# Get latest EMA value
ema_20 = indicators.ema(close_prices, period=20)

# Get full EMA series
ema_series = indicators.ema(close_prices, period=20, return_series=True)
```

### RSI (Relative Strength Index)

```python
# Get current RSI
rsi_14 = indicators.rsi(close_prices, period=14)

# Overbought/oversold check
if rsi_14 > 70:
    # Overbought
elif rsi_14 < 30:
    # Oversold
```

### SMA (Simple Moving Average)

```python
sma_50 = indicators.sma(close_prices, period=50)
sma_200 = indicators.sma(close_prices, period=200)

# Golden cross
if sma_50 > sma_200:
    # Bullish
```

### MACD (Moving Average Convergence Divergence)

```python
macd, signal, histogram = indicators.macd(close_prices)

if macd > signal:
    # Bullish crossover
```

### Bollinger Bands

```python
upper, middle, lower = indicators.bollinger_bands(close_prices, period=20, std_dev=2)

# Price breakout
if price > upper:
    # Upper band breakout
```

### ATR (Average True Range)

```python
atr_14 = indicators.atr(high_prices, low_prices, close_prices, period=14)

# Position sizing based on volatility
position_size = capital * risk_pct / atr_14
```

## Implementation Details

- **Input Validation**: Checks for sufficient data points
- **Type Flexibility**: Accepts lists or numpy arrays
- **NaN Handling**: Graceful handling of missing data
- **Performance**: Optimized for real-time tick processing

## Adding New Indicators

To add a new indicator:

1. Add function to `core/indicators.py`
2. Follow naming convention (lowercase, descriptive)
3. Include docstring with parameters and returns
4. Add unit tests in `tests/test_indicators.py`
5. Update this documentation (auto-generated)

---
*Auto-generated on 2025-11-15T21:51:37.963247+00:00*
