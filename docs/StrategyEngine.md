# Strategy Engine v2

## Overview

The **Strategy Engine v2** is a modern strategy execution framework with unified indicator calculations and clean separation between strategy logic, market data, and execution.

## Architecture

### Core Components

1. **StrategyEngineV2** (`core/strategy_engine_v2.py`)
   - Strategy lifecycle management
   - Signal generation coordination
   - State tracking

2. **BaseStrategy** - Abstract base class for all strategies
   - Signal generation interface
   - State management
   - Configuration handling

3. **StrategyState** - Per-strategy state tracking
   - Position tracking
   - Signal history
   - Metadata storage

4. **OrderIntent** - Pre-execution order representation
   - Symbol, action, quantity
   - Reason and confidence
   - Metadata

## Key Classes

### OrderIntent

Represents a trading intent from a strategy before risk checks.

**Methods:**
- `__init__()`
- `to_dict()`

### StrategyState

Maintains state for a strategy instance.

**Methods:**
- `__init__()`
- `is_position_open()`
- `is_long()`
- `is_short()`
- `update_position()`

### BaseStrategy

Base class for Strategy Engine v2 strategies.

Strategies should not fetch market data directly.
All data is provided via generate_signal() parameters.

**Methods:**
- `__init__()`
- `generate_signal()`
- `long()`
- `short()`
- `exit()`
- `position_is_long()`
- `position_is_short()`
- `get_pending_intents()`

### StrategyEngineV2

Strategy Engine v2

Orchestrates strategy execution with unified indicator calculations
and clean separation of concerns.

**Methods:**
- `__init__()`
- `register_strategy()`
- `set_paper_engine()`
- `compute_indicators()`
- `run_strategy()`
- `run()`


## Signal Flow

```
Market Data
     ↓
Strategy.generate_signal()
     ↓
OrderIntent
     ↓
Risk Validation
     ↓
Execution
```

## Strategy Implementation

### Example Strategy Structure

```python
class MyStrategy(BaseStrategy):
    def __init__(self, config, strategy_state):
        super().__init__(config, strategy_state)
        self.name = "MyStrategy"
        self.timeframe = "5m"
    
    def generate_signal(self, symbol, candles, ltp, metadata):
        # Calculate indicators
        # Generate trading signal
        # Return OrderIntent or None
        pass
```

## Strategy Registry

Strategies are registered in `core/strategy_registry.py`:

```python
STRATEGY_REGISTRY = {{
    "EMA_20_50": StrategyInfo(
        code="EMA_20_50",
        name="EMA 20/50 Crossover",
        enabled=True,
        ...
    )
}}
```

## Features

- **Indicator Integration**: Direct access to `core.indicators`
- **State Management**: Per-strategy position and signal tracking
- **Configuration**: YAML-based strategy parameters
- **Extensibility**: Easy to add new strategies
- **Testing**: Clean interfaces for unit testing

## Benefits Over v1

- **Cleaner API**: No direct market data fetching in strategies
- **Better Testing**: Strategies receive all data as parameters
- **Unified Indicators**: Single source of truth for calculations
- **State Isolation**: Each strategy has independent state

---
*Auto-generated on 2025-11-15T21:51:37.960882+00:00*
