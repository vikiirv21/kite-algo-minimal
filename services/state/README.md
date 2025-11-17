# State / Portfolio Service

Architecture v3 - Phase 5: Real-time portfolio state tracking service.

## Overview

The State Service is a standalone process that subscribes to execution fill events and maintains real-time portfolio state. It tracks positions, computes P&L, and maintains per-strategy statistics.

## Features

- **Real-time State Tracking**: Subscribes to `exec.fill.*` events from Execution Service
- **Portfolio Management**: Tracks positions, cash, realized/unrealized P&L
- **Strategy Analytics**: Per-strategy statistics (wins, losses, entry/exit counts, day P&L)
- **Checkpoint Persistence**: Automatically saves state to disk at configurable intervals
- **Safe Restarts**: Can restart mid-day and resume from last checkpoint
- **EventBus Integration**: Publishes state snapshots to `state.snapshot.updated.global` topic

## Architecture

```
┌─────────────────┐         ┌──────────────────┐         ┌─────────────────┐
│ Execution       │         │  EventBus        │         │ State           │
│ Service         │────────>│ (exec.fill.*)    │────────>│ Service         │
└─────────────────┘         └──────────────────┘         └─────────────────┘
                                                                    │
                                                                    v
                                                          ┌─────────────────┐
                                                          │ Checkpoint      │
                                                          │ Files           │
                                                          └─────────────────┘
```

## Data Structures

### Position
```python
@dataclass
class Position:
    symbol: str
    logical: str | None = None
    quantity: int = 0
    avg_price: float = 0.0
    realized_pnl: float = 0.0
    last_price: float | None = None
    profile: str | None = None
    strategy: str | None = None
```

### StrategyStats
```python
@dataclass
class StrategyStats:
    strategy: str
    day_pnl: float = 0.0
    win_trades: int = 0
    loss_trades: int = 0
    open_trades: int = 0
    closed_trades: int = 0
    entry_count: int = 0
    exit_count: int = 0
```

### PortfolioEquity
```python
@dataclass
class PortfolioEquity:
    starting_capital: float
    cash: float
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    day_pnl: float = 0.0
```

## Usage

### Starting the Service

```bash
# Paper mode (default)
python -m apps.run_service state

# Live mode
python -m apps.run_service state --mode live

# With custom config
python -m apps.run_service state --config configs/dev.yaml
```

### Configuration

In your `configs/dev.yaml`:

```yaml
trading:
  mode: "paper"
  paper_capital: 500000
  starting_capital: 500000

state:
  checkpoint_interval: 10  # Checkpoint every N fills (default: 10)
```

### Checkpoint Files

The service creates checkpoint files at:
- `artifacts/checkpoints/runtime_state_latest.json` (global checkpoint)
- `artifacts/checkpoints/paper_state_latest.json` (mode-specific)

Example checkpoint structure:
```json
{
  "mode": "paper",
  "equity": {
    "paper_capital": 500000.0,
    "starting_capital": 500000.0,
    "cash": 503772.81,
    "realized_pnl": 3772.81,
    "unrealized_pnl": 0.0,
    "day_pnl": 3772.81,
    "equity": 503772.81,
    "total_notional": 0.0,
    "free_notional": 503772.81
  },
  "positions": [],
  "strategies": {
    "ema20_50_intraday": {
      "day_pnl": 3772.81,
      "win_trades": 1,
      "loss_trades": 0,
      "open_trades": 0,
      "closed_trades": 1,
      "entry_count": 1,
      "exit_count": 1
    }
  },
  "last_heartbeat_ts": "2025-11-17T17:22:34.665308",
  "timestamp": "2025-11-17T17:22:34.665308"
}
```

## Dashboard Integration

The dashboard backend automatically reads state from checkpoints:

- **`/api/portfolio`**: Reads equity and position data from `runtime_state_latest.json`
- **`/api/strategy_performance`**: Reads per-strategy stats from `runtime_state_latest.json`

No changes needed to dashboard code - it already uses the right structure via `StateStore`.

## Event Flow

1. **Risk Service** approves order → publishes `risk.order_approved.*`
2. **Execution Service** receives approved order → places order → publishes `exec.fill.*`
3. **State Service** receives fill event → updates portfolio state → checkpoints state
4. **Dashboard** reads checkpoint → displays updated state

## P&L Calculation

### Realized P&L
- **BUY fill**: Updates average price using weighted average
- **SELL fill**: Realizes P&L = `(sell_price - avg_price) * quantity`

### Unrealized P&L
- Computed as: `(last_price - avg_price) * open_quantity`
- Uses most recent fill price as `last_price`

### Day P&L
- Total P&L for the day: `realized_pnl + unrealized_pnl`

## Strategy Statistics

The service tracks per-strategy metrics:
- **day_pnl**: Total P&L contribution from this strategy today
- **win_trades**: Number of trades closed with profit
- **loss_trades**: Number of trades closed with loss
- **open_trades**: Current number of open positions
- **closed_trades**: Total trades closed today
- **entry_count**: Total BUY fills
- **exit_count**: Total SELL fills

## Safety Features

- **Type-safe**: Never calls `float(None)` - all conversions are defensive
- **Validation**: Validates all incoming fill events
- **Checkpointing**: Periodic saves prevent data loss
- **Restart-safe**: Loads from checkpoint on startup
- **Backward Compatible**: Checkpoint format matches existing StateStore

## Testing

Run the included test script:
```bash
python tests/test_state_service.py
```

The test verifies:
- Position tracking accuracy
- P&L calculations
- Strategy statistics
- Checkpoint persistence
- Dashboard compatibility

## Limitations & Future Work

- **Last Price**: Currently uses fill price as last price. Future: integrate with market data for real-time quotes
- **Multi-day**: Currently designed for intraday. Future: add multi-day position tracking
- **Risk Metrics**: Future: add exposure limits, margin tracking, etc.
- **Performance**: Future: optimize for high-frequency scenarios

## Related Services

- **Execution Service** (`services/execution/`): Places orders and publishes fills
- **Risk Service** (`services/risk_portfolio/`): Approves/rejects orders
- **Strategy Service** (`services/strategy/`): Generates trading signals

## Support

For issues or questions, see the main project README.
