# Strategy Engine v2 Documentation

## Overview

Strategy Engine v2 is a modern, modular trading strategy framework with unified indicator calculations. It provides clean separation between strategy logic, market data, and execution while maintaining 100% backward compatibility with the legacy v1 system.

## Quick Start

### Using Legacy v1 (Default)

No changes required. The system continues to use Strategy Engine v1 by default.

### Enabling Strategy Engine v2

Update `configs/dev.yaml`:

```yaml
strategy_engine:
  version: 2                    # Use Strategy Engine v2
  strategies_v2:
    - ema20_50_intraday_v2      # List of v2 strategies to enable
  window_size: 200              # Historical candle window for indicators
  use_unified_indicators: true
```

## Architecture

### Core Components

1. **Indicator Library** (`core/indicators.py`)
   - Unified technical indicator calculations
   - Vectorized for performance
   - No pandas dependency
   - Supports both scalar and series outputs

2. **Strategy Engine v2** (`core/strategy_engine_v2.py`)
   - Orchestrates strategy execution
   - Computes indicators centrally
   - Manages strategy state
   - Routes orders through risk engine

3. **Base Strategy** (`core/strategy_engine_v2.BaseStrategy`)
   - Abstract base class for all v2 strategies
   - Provides helper methods for order generation
   - Receives pre-computed indicators

## Creating a v2 Strategy

### Basic Template

```python
from core.strategy_engine_v2 import BaseStrategy, StrategyState
from strategies.base import Decision
from typing import Dict, List, Any, Optional

class MyStrategyV2(BaseStrategy):
    def __init__(self, config: Dict[str, Any], strategy_state: StrategyState):
        super().__init__(config, strategy_state)
        self.name = "my_strategy_v2"
        
        # Strategy parameters
        self.param1 = config.get("param1", default_value)
    
    def generate_signal(
        self,
        candle: Dict[str, float],
        series: Dict[str, List[float]],
        indicators: Dict[str, Any]
    ) -> Optional[Decision]:
        """
        Generate trading signal.
        
        Args:
            candle: Current candle {open, high, low, close, volume}
            series: Historical series {open, high, low, close, volume}
            indicators: Pre-computed indicators {ema20, ema50, rsi14, ...}
        
        Returns:
            Decision(action="BUY"|"SELL"|"EXIT"|"HOLD", reason="...", confidence=0.0-1.0)
        """
        close = candle["close"]
        
        # Access indicators
        ema20 = indicators.get("ema20")
        ema50 = indicators.get("ema50")
        rsi = indicators.get("rsi14")
        
        # Check position state
        if self.position_is_long("SYMBOL"):
            # Handle exit logic
            pass
        
        # Generate signal
        if ema20 > ema50 and rsi < 70:
            return Decision(action="BUY", reason="bullish_cross", confidence=0.8)
        
        return Decision(action="HOLD", reason="no_signal", confidence=0.0)
```

### Available Indicators

The Strategy Engine v2 automatically computes these indicators and passes them to your strategy:

- `ema9`, `ema20`, `ema50`, `ema100`, `ema200` - Exponential Moving Averages
- `sma20`, `sma50` - Simple Moving Averages
- `rsi14` - Relative Strength Index (14 period)
- `atr14` - Average True Range (14 period)
- `bb_upper`, `bb_middle`, `bb_lower` - Bollinger Bands (20 period, 2 stddev)
- `supertrend`, `supertrend_direction` - SuperTrend indicator
- `vwap` - Volume Weighted Average Price
- `slope10` - Linear regression slope (10 period)
- `hl2`, `hl3` - Typical price indicators
- `trend` - "up" or "down" based on EMA20/EMA50

### Helper Methods

**Order Generation:**
```python
# Generate long order
self.long(symbol="NIFTY", qty=1, reason="bullish_signal")

# Generate short order
self.short(symbol="NIFTY", qty=1, reason="bearish_signal")

# Exit position
self.exit(symbol="NIFTY", reason="take_profit")

# Exit all positions
self.exit(reason="end_of_day")
```

**Position Checks:**
```python
# Check if we have a long position
if self.position_is_long("NIFTY"):
    # Handle long position logic
    pass

# Check if we have a short position
if self.position_is_short("NIFTY"):
    # Handle short position logic
    pass
```

## Using the Indicator Library Directly

You can also use the indicator library independently:

```python
from core import indicators

# Price data
closes = [100.0, 102.0, 104.0, 103.0, 105.0, 107.0]
highs = [105.0, 107.0, 109.0, 108.0, 110.0, 112.0]
lows = [95.0, 97.0, 99.0, 98.0, 100.0, 102.0]

# Calculate EMA (returns latest value)
ema_value = indicators.ema(closes, period=20)

# Calculate EMA series (returns all values)
ema_series = indicators.ema(closes, period=20, return_series=True)

# Calculate RSI
rsi_value = indicators.rsi(closes, period=14)

# Calculate ATR
atr_value = indicators.atr(highs, lows, closes, period=14)

# Calculate Bollinger Bands
bb = indicators.bollinger(closes, period=20, stddev=2.0)
# bb = {"middle": float, "upper": float, "lower": float}

# Calculate SuperTrend
st = indicators.supertrend(highs, lows, closes, period=10, multiplier=3.0)
# st = {"supertrend": float, "direction": 1 or -1, "upper_band": float, "lower_band": float}
```

## Running Backtests with v2 Strategies

Strategy Engine v2 is fully integrated with the backtest runner:

```bash
# Run backtest with v2 strategy
python scripts/run_backtest_v1.py \
    --strategy ema20_50_intraday_v2 \
    --symbol NIFTY \
    --from-date 2024-01-01 \
    --to-date 2024-03-31
```

The backtest runner automatically detects v2 strategies (by `_v2` suffix) and uses the appropriate engine.

## Testing

### Run All Tests

```bash
# Test indicator library
python tests/test_indicators.py

# Test strategy engine v2
python tests/test_strategy_engine_v2.py
```

### Writing Strategy Tests

```python
from core.strategy_engine_v2 import StrategyState
from strategies.my_strategy_v2 import MyStrategyV2

def test_my_strategy():
    config = {"name": "test", "timeframe": "5m"}
    state = StrategyState()
    strategy = MyStrategyV2(config, state)
    
    # Test data
    candle = {"open": 100, "high": 105, "low": 95, "close": 102, "volume": 1000}
    series = {"close": [100, 101, 102], "high": [105, 106, 107], "low": [95, 96, 97]}
    indicators = {"ema20": 100.5, "ema50": 99.5, "rsi14": 55.0}
    
    # Generate signal
    decision = strategy.generate_signal(candle, series, indicators)
    
    assert decision.action in ["BUY", "SELL", "EXIT", "HOLD"]
    assert 0.0 <= decision.confidence <= 1.0
```

## Migration Guide: v1 to v2

### Key Differences

| Feature | v1 | v2 |
|---------|----|----|
| State Management | Internal to strategy | Managed by StrategyEngine |
| Indicators | Computed by strategy | Pre-computed and passed in |
| Market Data | Strategy fetches directly | Provided via parameters |
| Order Generation | Direct broker calls | OrderIntent objects |
| Position Tracking | Manual | Built-in helpers |

### Migration Steps

1. **Create new v2 strategy file**: `strategies/my_strategy_v2.py`

2. **Inherit from BaseStrategy**:
   ```python
   from core.strategy_engine_v2 import BaseStrategy
   ```

3. **Update `generate_signal` signature**:
   ```python
   # v1
   def on_bar(self, symbol: str, bar: Dict[str, float]) -> Decision:
   
   # v2
   def generate_signal(
       self, candle: Dict[str, float], 
       series: Dict[str, List[float]], 
       indicators: Dict[str, Any]
   ) -> Optional[Decision]:
   ```

4. **Use pre-computed indicators**:
   ```python
   # v1 - compute yourself
   ema20 = self._ema(self.prices, 20)
   
   # v2 - use pre-computed
   ema20 = indicators["ema20"]
   ```

5. **Use helper methods for orders**:
   ```python
   # v1 - return Decision
   return Decision(action="BUY", reason="signal")
   
   # v2 - same, or use helpers
   return Decision(action="BUY", reason="signal")
   # OR
   self.long(symbol, qty=1, reason="signal")
   return Decision(action="HOLD")
   ```

6. **Update config**:
   ```yaml
   strategy_engine:
     version: 2
     strategies_v2:
       - my_strategy_v2
   ```

## Performance Considerations

### Indicator Calculation

- Indicators are calculated once per symbol per tick
- Vectorized implementations for better performance
- Results cached within strategy execution cycle
- No pandas overhead for core calculations

### Memory Usage

- `window_size` controls historical data retention (default: 200 candles)
- Adjust based on your indicators' lookback requirements
- Minimum recommended: 200 candles for reliable indicators

### Optimization Tips

1. Use appropriate `window_size` - larger isn't always better
2. Minimize custom indicator calculations in strategies
3. Leverage pre-computed indicators when possible
4. Use `return_series=False` (default) when only latest value needed

## Troubleshooting

### Strategy Not Running

**Problem**: v2 strategy configured but not executing

**Solutions**:
- Check `strategy_engine.version` is set to `2` in config
- Verify strategy name ends with `_v2`
- Check strategy is registered in engine initialization
- Review logs for import errors

### Missing Indicators

**Problem**: `indicators.get("ema20")` returns `None`

**Solutions**:
- Ensure sufficient historical data (check `window_size`)
- Verify symbol has market data available
- Check indicator requires minimum candles (e.g., EMA200 needs 200+ candles)
- Review MarketDataEngine logs

### Backward Compatibility Issues

**Problem**: v1 strategies stopped working

**Solutions**:
- v1 should work by default - check config hasn't changed
- Verify `strategy_engine.version` is `1` or not set
- Check no import errors in v2 code affecting v1
- Review error logs for specific issues

## Best Practices

1. **Start with v2 for new strategies** - cleaner architecture
2. **Keep v1 strategies as-is** - no need to migrate working code
3. **Test thoroughly** - use backtest runner before live trading
4. **Use meaningful reasons** - helps with debugging and analysis
5. **Set realistic confidence** - reflects signal quality
6. **Handle edge cases** - check for None/missing indicators
7. **Log important decisions** - use strategy logger when needed

## Support

For issues or questions:
- Check logs in `logs/` directory
- Review test files for usage examples
- Consult existing v2 strategies in `strategies/` directory

## Future Enhancements

Planned improvements for Strategy Engine v2:
- Additional technical indicators
- Strategy parameter optimization framework
- Multi-timeframe analysis helpers
- Performance analytics dashboard
- Strategy backtesting metrics
- Real-time strategy monitoring
