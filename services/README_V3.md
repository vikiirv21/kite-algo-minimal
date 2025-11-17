# HFT Architecture v3 Services

Service-oriented architecture for high-frequency trading with modular, event-driven components.

## Overview

HFT Architecture v3 introduces a clean service layer that sits on top of existing trading engines. Each service is:
- **Modular**: Independent components with clear responsibilities
- **Event-driven**: Communicate via EventBus with no shared mutable state
- **Resilient**: Graceful error handling, no crashes on missing data
- **Testable**: Fully tested with comprehensive test suite

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Dashboard/UI                       │
└────────────────────┬────────────────────────────────┘
                     │
                     ▼
            ┌─────────────────┐
            │ DashboardFeed   │  ◄─── Aggregates state
            └────────┬────────┘
                     │
                     ▼
            ┌─────────────────┐
            │    EventBus     │  ◄─── Central communication
            └────────┬────────┘
                     │
        ┌────────────┼────────────┐
        │            │            │
        ▼            ▼            ▼
┌──────────┐  ┌──────────┐  ┌──────────┐
│Strategy  │  │Execution │  │Portfolio │
│Service   │  │Service   │  │Service   │
└─────┬────┘  └─────┬────┘  └─────┬────┘
      │             │              │
      ▼             ▼              ▼
┌──────────────────────────────────────┐
│         MarketDataService            │
└──────────────────────────────────────┘
      │
      ▼
┌──────────────────────────────────────┐
│  broker_feed + market_data_engine    │
└──────────────────────────────────────┘
```

## Services

### 1. EventBus (`services/event_bus.py`)

Minimal in-process event bus for service communication.

**Features:**
- Synchronous publish/subscribe pattern
- Thread-safe with locking
- Event buffering for history
- Safe no-op if no subscribers

**API:**
```python
from services import EventBus

bus = EventBus(buffer_size=1000)

# Subscribe to events
def on_signal(event):
    print(f"Signal: {event['payload']}")

bus.subscribe("signals.fused", on_signal)

# Publish events
bus.publish("signals.fused", {
    "symbol": "RELIANCE",
    "action": "BUY",
    "confidence": 0.85
})

# Get recent events
recent = bus.get_recent_events(event_type="signals.fused", limit=10)
```

### 2. MarketDataService (`services/market_data_service.py`)

Unified market data access with caching and indicator computation.

**Features:**
- Wraps broker_feed.get_ltp and market_data_engine
- In-memory caching with configurable TTL
- Computes indicator bundles (EMA, RSI, ATR, VWAP)
- Graceful error handling

**API:**
```python
from services import MarketDataService

mds = MarketDataService(
    broker_feed=broker_feed,
    market_data_engine=mde,
    cache_ttl_seconds=1.0
)

# Get last traded price
ltp = mds.get_ltp("RELIANCE")

# Get indicator bundle
bundle = mds.get_bundle("RELIANCE", "5m")
# Returns: {
#   "ema20": 2500.0,
#   "ema50": 2480.0,
#   "rsi": 65.0,
#   "atr": 25.0,
#   "vwap": 2495.0,
#   "slope": 20.0,
#   "trend_signal": "bullish"
# }

# Get historical candles
history = mds.get_history("RELIANCE", "5m", n=100)
```

### 3. StrategyService (`services/strategy_service_v3.py`)

Integrates StrategyEngineV3 with data fetching and signal publishing.

**Features:**
- Multi-timeframe evaluation (primary + secondary)
- Signal fusion and confidence scoring
- Publishes raw and fused signals to EventBus
- Returns OrderIntent for execution

**API:**
```python
from services import StrategyService

strategy_svc = StrategyService(
    strategy_engine=strategy_engine_v3,
    market_data_service=mds,
    event_bus=bus,
    primary_tf="5m",
    secondary_tf="15m"
)

# Run strategy for a symbol
intent = strategy_svc.run_symbol("RELIANCE", ts=None)

# Returns OrderIntent:
# - action: "BUY", "SELL", or "HOLD"
# - confidence: 0.0 to 1.0
# - reason: explanation
# - metadata: indicators, signals
```

### 4. ExecutionService (`services/execution_service.py`)

Order validation and routing to paper or live broker.

**Features:**
- Order validation (symbol, qty, side)
- Position sizing with configurable limits
- Routes to paper or live broker
- Publishes order.filled events

**API:**
```python
from services import ExecutionService

exec_svc = ExecutionService(
    broker=broker,
    portfolio_service=portfolio,
    event_bus=bus,
    mode="paper",  # or "live"
    max_position_size=100
)

# Execute an order intent
result = exec_svc.execute(order_intent)

# Returns OrderResult:
# - order_id: unique identifier
# - status: "FILLED", "REJECTED", "PLACED"
# - avg_price: execution price
# - message: status or error message
```

### 5. PortfolioService (`services/portfolio_service.py`)

Position tracking, PnL management, and checkpointing.

**Features:**
- Tracks positions and PnL (realized + unrealized)
- Updates on fill events
- Checkpoints to disk for persistence
- Publishes portfolio.updated events

**API:**
```python
from services import PortfolioService

portfolio = PortfolioService(
    initial_capital=100000.0,
    event_bus=bus,
    checkpoint_dir=Path("artifacts/portfolio")
)

# Subscribe to fill events
bus.subscribe("order.filled", portfolio.on_fill)

# Get portfolio snapshot
snapshot = portfolio.get_snapshot()
# Returns: {
#   "positions": [...],
#   "cash": 95000.0,
#   "equity": 105000.0,
#   "realized_pnl": 5000.0,
#   "unrealized_pnl": 2000.0,
#   "exposure": 50000.0,
#   "position_count": 3
# }

# Get specific position
pos = portfolio.get_position("RELIANCE")
```

### 6. DashboardFeed (`services/dashboard_feed.py`)

Aggregates state from all services for dashboard consumption.

**Features:**
- Subscribes to all service events
- Aggregates signals, orders, positions
- Thread-safe state management
- Provides JSON snapshot for dashboard

**API:**
```python
from services import DashboardFeed

feed = DashboardFeed(
    event_bus=bus,
    max_signals=100,
    max_orders=100
)

# Get dashboard snapshot
snapshot = feed.get_snapshot()
# Returns: {
#   "signals": [...],
#   "orders": [...],
#   "positions": [...],
#   "portfolio": {...},
#   "system": {...}
# }

# Update system state
feed.update_system_state("status", "running")
```

## Quick Start

### Basic Wiring

```python
from services import (
    EventBus,
    MarketDataService,
    StrategyService,
    ExecutionService,
    PortfolioService,
    DashboardFeed
)

# 1. Initialize EventBus
bus = EventBus()

# 2. Initialize MarketDataService
mds = MarketDataService(broker_feed, mde)

# 3. Initialize StrategyService
strategy_svc = StrategyService(strategy_engine, mds, bus)

# 4. Initialize PortfolioService
portfolio = PortfolioService(100000.0, bus)
bus.subscribe("order.filled", portfolio.on_fill)

# 5. Initialize ExecutionService
exec_svc = ExecutionService(broker, portfolio, bus, mode="paper")

# 6. Initialize DashboardFeed
feed = DashboardFeed(bus)
```

### Trading Loop

```python
# Run strategy for each symbol
for symbol in symbols:
    intent = strategy_svc.run_symbol(symbol)
    
    # Execute if actionable
    if intent.action in ("BUY", "SELL") and intent.confidence > 0.5:
        result = exec_svc.execute(intent)
        
# Get dashboard state
snapshot = feed.get_snapshot()
```

## Demo & Tests

### Run Demo

```bash
python examples/demo_services_v3.py
```

Shows complete service wiring and integration.

### Run Tests

```bash
python tests/test_services_v3.py
```

Comprehensive test suite covering all services.

## Event Types

The EventBus supports these event types:

- `signals.raw` - Raw signals from individual strategies
- `signals.fused` - Fused signal after multi-strategy evaluation
- `order.filled` - Order execution complete
- `portfolio.updated` - Portfolio state changed

## Configuration

Services use these configuration patterns:

```python
# EventBus
bus = EventBus(buffer_size=1000)

# MarketDataService
mds = MarketDataService(
    broker_feed=broker_feed,
    market_data_engine=mde,
    cache_ttl_seconds=1.0
)

# StrategyService
strategy_svc = StrategyService(
    strategy_engine=engine,
    market_data_service=mds,
    event_bus=bus,
    primary_tf="5m",
    secondary_tf="15m"
)

# ExecutionService
exec_svc = ExecutionService(
    broker=broker,
    portfolio_service=portfolio,
    event_bus=bus,
    mode="paper",
    max_position_size=100
)

# PortfolioService
portfolio = PortfolioService(
    initial_capital=100000.0,
    event_bus=bus,
    checkpoint_dir=Path("artifacts/portfolio")
)

# DashboardFeed
feed = DashboardFeed(
    event_bus=bus,
    max_signals=100,
    max_orders=100
)
```

## Error Handling

All services implement graceful error handling:

- Return `None` or empty collections on errors
- Log warnings instead of raising exceptions
- Never crash on missing data or invalid inputs
- Validate inputs before processing

## Threading & Concurrency

- **EventBus**: Thread-safe with locks
- **MarketDataService**: Thread-safe caching
- **PortfolioService**: Thread-safe with locks
- **DashboardFeed**: Thread-safe with locks
- **StrategyService**: Stateless (thread-safe)
- **ExecutionService**: Stateless (thread-safe)

## Production Usage

To use in production:

1. Wire services into `run_trader.py` or `run_day.py`
2. Configure with real Kite API credentials
3. Set strategy parameters in YAML
4. Enable live trading mode (`mode="live"`)
5. Connect dashboard to `DashboardFeed.get_snapshot()`
6. Monitor via logs and dashboard

## Compatibility

- ✓ Works with existing StrategyEngineV3
- ✓ Compatible with ExecutionEngineV3
- ✓ No modifications to existing engines
- ✓ Supports both paper and live trading
- ✓ Drop-in replacement for manual wiring

## Files

```
services/
├── __init__.py                  # Package exports
├── event_bus.py                 # EventBus implementation
├── market_data_service.py       # Market data wrapper
├── strategy_service_v3.py       # Strategy service
├── execution_service.py         # Execution service
├── portfolio_service.py         # Portfolio tracker
└── dashboard_feed.py            # Dashboard aggregator

examples/
└── demo_services_v3.py          # Complete demo

tests/
└── test_services_v3.py          # Test suite
```

## License

Same as parent project.
