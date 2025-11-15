# Market Data Engine v2 (MDE v2)

## Overview

Market Data Engine v2 (MDE v2) is a robust, event-driven market data processing system that serves as the single source of truth for:

- **Real-time ticks** (live or replay)
- **Multi-timeframe candle building**
- **Historical data replay** for backtesting
- **Strategy triggers** via event callbacks

## Key Features

### 1. Event-Driven Architecture

MDE v2 uses callbacks for candle lifecycle events:

- `on_candle_open`: Fired when a new candle starts
- `on_candle_update`: Fired on each tick that updates a candle
- `on_candle_close`: Fired when a candle completes

This decouples market data processing from strategy logic.

### 2. Multi-Timeframe Support

MDE v2 simultaneously builds candles for multiple timeframes:

- **Supported**: 1m, 3m, 5m, 10m, 15m, 30m, 60m (1h)
- **Efficient**: Single tick updates all relevant timeframes
- **Independent**: Each symbol+timeframe tracked separately

### 3. Data Validation

Built-in safeguards:

- **Stale tick detection**: Ignores old data
- **Invalid price filtering**: Rejects null/negative prices
- **Anomaly detection**: Flags >5% price jumps

## Configuration

Enable in `configs/dev.yaml`:

```yaml
data:
  use_mde_v2: true
  feed: "kite"              # "kite", "replay", or "mock"
  timeframes: ["1m", "5m"]
  replay_speed: 1.0
```

## Usage Example

```python
from core.market_data_engine_v2 import MarketDataEngineV2

# Initialize
config = {"data": {"feed": "kite", "timeframes": ["1m", "5m"]}}
mde = MarketDataEngineV2(config=config, broker=kite_broker)

# Subscribe & start
mde.subscribe_symbols(["NIFTY24DECFUT"])
mde.start()

# Register callback
def on_candle_close(symbol, timeframe, candle):
    print(f"Candle closed: {symbol} {timeframe}")
mde.on_candle_close_handlers.append(on_candle_close)
```

## Dashboard API

- `GET /api/market_data/latest_tick?symbol=NIFTY24DECFUT`
- `GET /api/market_data/candles?symbol=...&timeframe=5m&limit=100`
- `GET /api/market_data/v2/stats`

See full documentation for detailed API reference and examples.
