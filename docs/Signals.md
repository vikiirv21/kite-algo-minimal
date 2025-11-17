# Trading Signals

## Overview

Signals are the output of strategy evaluation, indicating desired trading actions.

## Signal Types

### BUY
- Enter a new long position
- Add to existing long position
- Generated when bullish conditions met

### SELL
- Enter a new short position
- Add to existing short position
- Generated when bearish conditions met

### EXIT
- Close existing position
- Can be profit target or stop loss
- Generated when exit conditions met

### HOLD
- No action required
- Default when no setup present
- Maintains current position state

## Signal Structure

### OrderIntent

```python
class OrderIntent:
    symbol: str          # Trading symbol
    action: str          # "BUY", "SELL", "EXIT"
    qty: int            # Order quantity
    reason: str         # Human-readable reason
    strategy_code: str  # Strategy identifier
    confidence: float   # Signal confidence (0-1)
    metadata: dict      # Additional data
```

### Example Signal

```python
signal = OrderIntent(
    symbol="NIFTY",
    action="BUY",
    qty=75,
    reason="EMA 20 crossed above EMA 50",
    strategy_code="EMA_20_50",
    confidence=0.85,
    metadata={{
        "ema_20": 21500.0,
        "ema_50": 21480.0,
        "rsi": 62.5
    }}
)
```

## Signal Generation

### Strategy-Based

```python
def generate_signal(self, symbol, candles, ltp, metadata):
    # Calculate indicators
    ema_20 = indicators.ema(closes, 20)
    ema_50 = indicators.ema(closes, 50)
    
    # Generate signal
    if ema_20 > ema_50 and not self.state.is_position_open(symbol):
        return OrderIntent(
            symbol=symbol,
            action="BUY",
            qty=self.calculate_qty(),
            reason="Bullish EMA crossover",
            strategy_code=self.name,
            confidence=0.8
        )
    
    return None  # HOLD
```

## Signal Quality

Signals are scored on:
- **Confidence**: Strategy's conviction (0-1)
- **Timing**: How fresh the setup is
- **Context**: Market regime alignment
- **Risk/Reward**: Expected profit vs risk

## Signal Filters

### Pattern Filters
- Trend alignment
- Volume confirmation
- Volatility requirements

### Risk Filters
- Position limits
- Capital constraints
- Correlation limits

### Time Filters
- Market hours
- High-volatility periods
- News events

## Signal Flow

```
Strategy.generate_signal()
        ↓
   OrderIntent
        ↓
Signal Quality Check
        ↓
  Risk Validation
        ↓
   Execution
```

## Signal Metadata

Metadata can include:
- Indicator values at signal time
- Support/resistance levels
- Volatility metrics
- Volume profile
- Market regime

## Best Practices

1. **Clear Reasons**: Always provide human-readable reason
2. **Confidence Scoring**: Rate signal quality
3. **Metadata**: Include all relevant context
4. **Validation**: Check data quality before signaling
5. **Filtering**: Apply multiple confirmation layers

---
*Auto-generated on 2025-11-17T19:09:52.566854+00:00*
