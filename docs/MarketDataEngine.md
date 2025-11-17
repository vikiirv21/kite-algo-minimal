# Market Data Engine

## Overview

The **Market Data Engine** manages candle data fetching, caching, and real-time updates via the Kite API.

## Architecture

### Components

1. **MarketDataEngine** (`core/market_data_engine.py`)
   - Historical candle fetching
   - Local cache management
   - LTP (Last Traded Price) retrieval
   - Multi-timeframe support

2. **Cache System**
   - JSON-based candle storage
   - Incremental updates
   - Timeframe-specific caching

3. **Kite Integration**
   - Historical data API calls
   - WebSocket tick processing
   - Instrument token resolution

## Features

### Candle Management

```python
# Fetch historical candles
candles = mde.fetch_historical("NIFTY", "5m", count=200)

# Load from cache
candles = mde.load_cache("NIFTY", "5m")

# Save to cache
mde.save_cache("NIFTY", "5m", candles)
```

### LTP Retrieval

```python
# Get last traded price
ltp = mde.get_ltp("NIFTY")

# Batch LTP for multiple symbols
ltps = mde.get_ltp_batch(["NIFTY", "BANKNIFTY", "FINNIFTY"])
```

### Multi-Timeframe

```python
# Configure multiple timeframes per symbol
config = {{
    "NIFTY": ["1m", "5m", "15m"],
    "BANKNIFTY": ["1m", "5m"]
}}

# Engine handles all timeframes automatically
```

## Cache Structure

```
artifacts/market_data/
├── NIFTY_1m.json
├── NIFTY_5m.json
├── BANKNIFTY_1m.json
└── ...
```

## Candle Format

```python
{{
    "ts": "2024-01-15T09:15:00+00:00",
    "open": 21500.0,
    "high": 21520.0,
    "low": 21495.0,
    "close": 21510.0,
    "volume": 1250000
}}
```

## Performance

- **Cache-First**: Reduces API calls
- **Incremental Updates**: Only fetches new candles
- **Async-Ready**: Supports concurrent requests
- **Rate Limiting**: Respects Kite API limits

## Timeframe Support

| Timeframe | Interval | Use Case |
|-----------|----------|----------|
| 1m | minute | Scalping |
| 3m | 3minute | Quick trades |
| 5m | 5minute | Intraday |
| 15m | 15minute | Swing |
| 60m | 60minute | Hourly |
| day | day | Daily |

---
*Auto-generated on 2025-11-17T19:09:52.557869+00:00*
