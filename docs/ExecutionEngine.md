# Execution Engine

## Overview

The **Execution Router** provides mode-aware order routing, directing orders to the appropriate broker based on the trading mode.

## Architecture

### ExecutionRouter

Located in `broker/execution_router.py`, the router determines where orders go:

- **PAPER/REPLAY**: Routes to `PaperBroker`
- **LIVE**: Routes to `KiteClient` (real orders)

### Components

1. **ExecutionRouter** (`broker/execution_router.py`)
   - Mode detection
   - Order routing logic
   - Broker initialization

2. **PaperBroker** (`broker/paper_broker.py`)
   - In-memory position tracking
   - Instant fill simulation
   - P&L calculation

3. **LiveBroker/KiteBroker** (`broker/kite_bridge.py`)
   - Real Kite API integration
   - Order placement and tracking
   - WebSocket order updates

4. **BacktestBroker** (`broker/backtest_broker.py`)
   - Historical data replay
   - Slippage simulation
   - Commission modeling

## Order Flow

```
Strategy Signal
      ↓
Risk Validation
      ↓
Order Intent
      ↓
ExecutionRouter
      ↓
   [Mode Check]
      ↓
Paper → PaperBroker.place_order()
Live  → KiteBroker.place_order()
```

## Broker Interfaces

### PaperBroker

```python
def place_order(symbol, side, quantity, price):
    # Instant fill at requested price
    # Update internal positions
    # Return order_id
```

### KiteBroker

```python
def place_order(symbol, side, quantity, price):
    # Call Kite API
    # Track pending order
    # Wait for WebSocket confirmation
    # Return order_id
```

## Key Features

- **Unified Interface**: Same API regardless of mode
- **Mode Isolation**: Clear separation between paper/live
- **Safety**: Validation at router level
- **Flexibility**: Easy to add new brokers

## Configuration

```yaml
trading:
  mode: PAPER  # or LIVE, REPLAY, BACKTEST
```

---
*Auto-generated on 2025-11-17T19:09:52.551102+00:00*
