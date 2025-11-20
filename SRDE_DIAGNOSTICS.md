# Strategy Real-Time Diagnostics Engine (SRDE)

## Overview

The SRDE provides real-time insight into **WHY** trading strategies make specific decisions (BUY/SELL/HOLD). This helps with:
- Debugging strategy logic
- Understanding signal generation
- Tracking indicator values over time
- Identifying risk blocks and regime changes

## Architecture

### Storage
- **Format**: JSONL (JSON Lines) for crash resilience
- **Location**: `artifacts/diagnostics/<symbol>/<strategy>.jsonl`
- **Organization**: One file per symbol-strategy pair
- **Persistence**: Survives engine crashes and restarts

### Non-Blocking Design
- All diagnostic writes are best-effort
- Failures are logged at DEBUG level
- Never slows down or crashes trading engines
- Uses try/except protection at all levels

## Usage

### 1. Dashboard API

Query diagnostics via the dashboard endpoint:

```bash
GET /api/diagnostics/strategy?symbol=NIFTY&strategy=EMA_20_50&limit=200
```

**Parameters**:
- `symbol`: Trading symbol (e.g., "NIFTY", "BANKNIFTY", "RELIANCE")
- `strategy`: Strategy identifier (e.g., "EMA_20_50", "RSI_MACD")
- `limit`: Maximum records to return (default: 200, most recent first)

**Response**:
```json
{
  "symbol": "NIFTY",
  "strategy": "EMA_20_50",
  "count": 150,
  "data": [
    {
      "ts": "2024-01-15T09:30:00.123456Z",
      "price": 18500.50,
      "ema20": 18480.0,
      "ema50": 18450.0,
      "trend_strength": 0.042,
      "confidence": 0.85,
      "rr": 2.5,
      "regime": "trend",
      "risk_block": "none",
      "decision": "BUY",
      "reason": "Strong uptrend with EMA crossover",
      "rsi14": 65.0,
      "atr14": 50.0,
      "timeframe": "5m",
      "side": "LONG"
    }
  ]
}
```

### 2. Programmatic Access

```python
from analytics.diagnostics import load_diagnostics, append_diagnostic

# Load diagnostics
records = load_diagnostics("NIFTY", "EMA_20_50", limit=100)
for record in records:
    print(f"{record['ts']}: {record['decision']} - {record['reason']}")

# Append diagnostic (typically done by engines)
append_diagnostic(
    symbol="NIFTY",
    strategy="EMA_20_50",
    record={
        "ts": "2024-01-15T09:30:00Z",
        "price": 18500.0,
        "decision": "BUY",
        "reason": "EMA crossover",
        "confidence": 0.8,
        "ema20": 18480.0,
        "ema50": 18450.0,
        "risk_block": "none",
    }
)
```

### 3. Helper Functions

```python
from analytics.diagnostics import build_diagnostic_record

# Build standardized diagnostic record
record = build_diagnostic_record(
    price=18500.0,
    decision="BUY",
    reason="EMA crossover",
    confidence=0.8,
    ema20=18480.0,
    ema50=18450.0,
    trend_strength=0.042,
    rr=2.5,
    regime="trend",
    risk_block="none",
)
```

## Diagnostic Record Schema

### Required Fields
- `ts`: ISO 8601 timestamp (UTC)
- `price`: Current price (float)
- `decision`: Trading decision ("BUY"|"SELL"|"HOLD")
- `reason`: Explanation string
- `confidence`: Confidence score (0.0 to 1.0)
- `risk_block`: Risk block reason ("none"|"max_loss"|"cooldown"|"slippage")

### Optional Fields
- `ema20`, `ema50`, `ema100`, `ema200`: EMA indicator values
- `rsi14`: RSI indicator value
- `atr14`: ATR indicator value
- `trend_strength`: Calculated trend strength (0.0 to 1.0+)
- `rr`: Risk:reward ratio
- `regime`: Market regime ("trend"|"low_vol"|"compression"|null)
- `timeframe`: Candle timeframe (e.g., "5m", "15m")
- `side`: Position side ("LONG"|"SHORT"|"FLAT")

### Custom Fields
You can add any additional fields via the `**extra_fields` parameter in `build_diagnostic_record()`.

## Integration

### Automatic Integration

The SRDE is automatically integrated into:
- **StrategyEngineV2**: Emits diagnostics on every `evaluate()` call
- **PaperEngine**: Uses StrategyEngineV2 for FnO trading
- **EquityPaperEngine**: Uses StrategyEngineV2 for equity trading
- **OptionsPaperEngine**: Uses StrategyEngineV2 for options trading

### Manual Integration

To add diagnostics to custom strategies:

```python
from analytics.diagnostics import append_diagnostic, build_diagnostic_record

# In your strategy evaluation logic
record = build_diagnostic_record(
    price=current_price,
    decision=signal,
    reason=explanation,
    confidence=confidence_score,
    ema20=indicators.get("ema20"),
    ema50=indicators.get("ema50"),
)

append_diagnostic(symbol, strategy_id, record)
```

## File Organization

```
artifacts/diagnostics/
├── NIFTY/
│   ├── EMA_20_50.jsonl
│   ├── RSI_MACD.jsonl
│   └── SUPERTREND.jsonl
├── BANKNIFTY/
│   ├── EMA_20_50.jsonl
│   └── RSI_MACD.jsonl
└── RELIANCE/
    └── EMA_20_50.jsonl
```

Each JSONL file contains one JSON record per line:
```jsonl
{"ts":"2024-01-15T09:30:00Z","price":18500.0,"decision":"BUY","reason":"...","confidence":0.8}
{"ts":"2024-01-15T09:35:00Z","price":18505.0,"decision":"HOLD","reason":"...","confidence":0.5}
{"ts":"2024-01-15T09:40:00Z","price":18510.0,"decision":"SELL","reason":"...","confidence":0.7}
```

## Benefits

### 1. Real-Time Debugging
- See exactly why a strategy made each decision
- Track indicator values at decision time
- Identify patterns in HOLD signals

### 2. Performance Analysis
- Correlate decisions with market conditions (regime)
- Track confidence scores over time
- Identify risk blocks preventing trades

### 3. Strategy Optimization
- Find optimal indicator parameters
- Identify false signals
- Understand strategy behavior in different regimes

### 4. Dashboard Integration
- Powers the real-time strategy debugger UI
- Enables "Why HOLD?" analysis
- Provides indicator timeline visualization

## Error Handling

The SRDE is designed to **never crash or slow down** trading engines:

1. **Best-Effort Writes**: Failures are logged but don't propagate
2. **Try/Except Protection**: All operations wrapped in error handlers
3. **Debug-Level Logging**: Errors logged at DEBUG to avoid noise
4. **Graceful Degradation**: Missing data returns empty arrays
5. **Non-Blocking**: Synchronous writes (no threads/queues needed for this simple case)

## Performance

- **Write Speed**: ~0.1ms per record (JSONL append)
- **Read Speed**: ~1ms per 100 records
- **Memory**: Minimal (streaming JSONL reads)
- **Disk**: ~100 bytes per record (uncompressed)

## Future Enhancements

Potential improvements (not currently implemented):
- Compression for old diagnostic files
- Automatic cleanup of old records
- Aggregated statistics endpoint
- Real-time streaming via WebSocket
- Integration with strategy backtesting

## Testing

Run the test suite:

```bash
# Unit tests
python tests/test_diagnostics.py

# Integration tests (requires dependencies)
python tests/test_srde_integration.py
```

## Support

For issues or questions:
1. Check diagnostic files in `artifacts/diagnostics/`
2. Enable DEBUG logging: `logger.setLevel(logging.DEBUG)`
3. Review dashboard endpoint responses
4. Check strategy engine logs for diagnostic errors
