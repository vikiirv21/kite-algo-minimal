# Risk Engine

## Overview

The **Risk Engine** validates all trading decisions before execution, enforcing position limits, loss limits, and other safety guardrails.

## Architecture

### Components

1. **RiskEngine** (`core/risk_engine.py`)
   - Entry validation
   - Exit validation
   - Position sizing
   - Loss tracking

2. **RiskConfig** - Configuration dataclass
   - Capital limits
   - Position limits
   - Loss limits
   - Trade frequency limits

3. **RiskDecision** - Risk check result
   - ALLOW: Trade approved
   - BLOCK: Trade rejected
   - REDUCE: Trade approved with reduced size
   - HALT_SESSION: Stop all trading

## Risk Checks

### Entry Checks

```python
ctx = TradeContext(
    symbol="NIFTY",
    action="BUY",
    qty=75,
    capital=100000,
    ...
)

decision = risk_engine.check_entry(ctx)

if decision.action == RiskAction.ALLOW:
    # Place order
elif decision.action == RiskAction.REDUCE:
    # Place order with reduced qty
    adjusted_qty = decision.adjusted_qty
else:
    # Block trade
```

### Exit Checks

```python
ctx = TradeContext(
    symbol="NIFTY",
    action="EXIT",
    position_qty=75,
    ...
)

decision = risk_engine.check_exit(ctx)
# Exits are usually always allowed
```

## Risk Rules

### Position Limits

- **Max Positions Total**: Hard cap on concurrent positions
- **Max Positions Per Symbol**: Limit on same symbol
- **Position Sizing**: Based on capital and risk percentage

### Loss Limits

- **Max Daily Loss (Absolute)**: Hard rupee amount
- **Max Daily Loss (Percentage)**: Percentage of capital
- **Max Per-Trade Loss**: Stop loss per position

### Frequency Limits

- **Max Trades Per Symbol Per Day**: Prevent overtrading
- **Min Seconds Between Entries**: Cool-down period
- **Trade Throttling**: Rate limiting

## Configuration

```yaml
risk:
  mode: live
  capital: 100000
  per_trade_risk_pct: 2.0
  
  max_daily_loss_abs: 5000
  max_daily_loss_pct: 5.0
  
  max_positions_total: 5
  max_positions_per_symbol: 2
  max_trades_per_symbol_per_day: 3
  min_seconds_between_entries: 300
```

## Risk Actions

| Action | Meaning | Behavior |
|--------|---------|----------|
| ALLOW | Trade approved | Execute as requested |
| BLOCK | Trade rejected | Do not execute |
| REDUCE | Size reduced | Execute with smaller qty |
| HALT_SESSION | Emergency stop | Stop all trading immediately |

## State Tracking

The risk engine tracks:
- Open positions
- Daily P&L
- Trade counts per symbol
- Last trade timestamps
- Capital utilization

## Safety Features

- **Pre-Trade Validation**: All signals validated before execution
- **Dynamic Position Sizing**: Based on ATR or volatility
- **Circuit Breakers**: Auto-halt on loss limits
- **Override Capability**: Manual halt/resume

## Integration

```python
# Initialize
risk_engine = RiskEngine(config, state, logger)

# Check entry
decision = risk_engine.check_entry(trade_context)

# Update state after fill
risk_engine.update_state(fill_info)
```

---
*Auto-generated on 2025-11-15T21:49:59.729383+00:00*
