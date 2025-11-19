# ExecutionEngine V3 - User Guide

## Overview

ExecutionEngine V3 is a unified execution layer that provides comprehensive order lifecycle management with advanced features like stop loss, take profit, trailing stops, partial exits, and time-based exits.

## Features

- **Order Lifecycle Management**: CREATED → SUBMITTED → FILLED → ACTIVE → CLOSED → ARCHIVED
- **Fill Simulation**: Configurable fill modes (mid/bid_ask/ltp) with realistic slippage
- **Stop Loss Management**: Automatic SL monitoring with optional partial exit
- **Take Profit Management**: Automatic TP monitoring and full position exit
- **Trailing Stop Loss**: Dynamic SL adjustment as price moves favorably
- **Time-Based Exits**: Close positions after N bars if no SL/TP hit
- **Position Tracking**: Real-time unrealized PnL calculation
- **Runtime Metrics**: Automatic updates to `artifacts/analytics/runtime_metrics.json`

## Configuration

Add the following to your `configs/dev.yaml`:

```yaml
execution:
  engine: v3  # Enable ExecutionEngine V3
  
  # Fill configuration
  fill_mode: "mid"  # Options: "mid", "bid_ask", "ltp"
  slippage_bps: 5   # Slippage in basis points (5 bps = 0.05%)
  
  # Partial exit configuration
  enable_partial_exit: true  # Exit 50% on SL breach
  partial_exit_pct: 0.5      # 50% partial exit
  
  # Trailing stop configuration
  enable_trailing: true  # Enable trailing stop loss
  trail_step_r: 0.5      # Trail at 0.5R (half of initial risk)
  
  # Time stop configuration
  enable_time_stop: true  # Enable time-based exits
  time_stop_bars: 20      # Exit after 20 bars if no SL/TP
```

## How It Works

### 1. Order Entry

When a strategy signal is generated:

```python
# Strategy generates signal
signal_obj = OrderIntent(
    symbol="NIFTY25JAN26000CE",
    signal="BUY",
    qty=50,
    strategy_id="ema_crossover"
)

# ExecutionEngine V3 processes it
order = exec_engine.process_signal(symbol, signal_obj)
```

### 2. Order Lifecycle

**CREATED** → Order built with OrderBuilder
- Symbol, qty, side extracted
- SL/TP/time stop parameters set
- Unique order ID generated

**SUBMITTED** → Order submitted to FillEngine
- Fill price determined (mid/bid_ask/ltp + slippage)
- Order marked as SUBMITTED

**FILLED** → Order filled at determined price
- Entry price recorded
- Fill timestamp recorded
- Order marked as FILLED

**ACTIVE** → Position now monitored
- Every tick: Check SL, TP, trailing
- Every candle: Increment bars_held, check time stop
- Unrealized PnL updated continuously

**CLOSED** → Position closed
- Reason: SL hit, TP hit, time stop, or manual exit
- Realized PnL calculated
- Trade recorder notified

### 3. Stop Loss Behavior

**Without Partial Exit:**
```
Price hits SL → Close 100% of position → Mark CLOSED
```

**With Partial Exit (default):**
```
1. Price hits SL → Exit 50% of position
2. Remaining 50% gets trailing SL activated
3. Trailing SL tracks favorable price movement
4. Position closed when trailing SL hit or TP reached
```

### 4. Trailing Stop Loss

After partial exit (or immediately if enabled):
```
For LONG:
- Track highest_price
- When price moves up: new_sl = highest_price - (initial_risk * trail_step_r)
- Only raise SL, never lower

For SHORT:
- Track lowest_price
- When price moves down: new_sl = lowest_price + (initial_risk * trail_step_r)
- Only lower SL, never raise
```

### 5. Time Stop

Prevents positions from staying open indefinitely:
```
Every candle close:
  bars_held += 1
  
If bars_held >= time_stop_bars and no SL/TP hit:
  Close position at market
  Reason: "time_stop"
```

## Example Scenarios

### Scenario 1: Winning Trade with TP

```
Entry: BUY 50 @ 100, SL=95, TP=110
Bar 1: Price=102, unrealized_pnl=+100
Bar 2: Price=105, unrealized_pnl=+250
Bar 3: Price=111, TP HIT → Close 50 @ 111
Result: realized_pnl=+550 (11 points gain)
```

### Scenario 2: Losing Trade with Partial SL

```
Entry: BUY 50 @ 100, SL=95, TP=110
Bar 1: Price=98, unrealized_pnl=-100
Bar 2: Price=94, SL HIT → Partial exit 25 @ 94
  - realized_pnl=-150 (6 points loss on 25 qty)
  - remaining=25, trailing_sl=active, new_sl=96
Bar 3: Price=105, unrealized_pnl=+125 on remaining
Bar 4: Price=103, trailing SL not hit yet
Bar 5: Price=96, trailing SL HIT → Close 25 @ 96
  - realized_pnl=-150 + (-100) = -250 total
Result: Limited loss through partial exit + trailing
```

### Scenario 3: Time Stop Exit

```
Entry: BUY 50 @ 100, SL=95, TP=110, time_stop_bars=20
Bars 1-20: Price oscillates 98-102, no SL/TP hit
Bar 20: bars_held=20, TIME STOP → Close 50 @ 101
Result: Small profit, position didn't trend
```

## Integration with Existing Engines

### Paper Engine

ExecutionEngine V3 integrates with `paper_engine.py`:

1. **Initialization**: Engine detects `execution.engine: v3` in config
2. **Signal Processing**: Signals routed to V3 via `process_signal()`
3. **Position Updates**: Every tick updates all active positions
4. **Fallback**: If V3 fails, falls back to v2 or legacy execution

### Strategy Engine V2

Strategies using StrategyEngineV2 work seamlessly:

```python
# Strategy emits OrderIntent
intent = OrderIntent(
    symbol="NIFTY25JAN26000CE",
    signal="BUY",
    qty=50,
    sl_price=95.0,
    tp_price=110.0,
)

# Paper engine routes to ExecutionEngine V3
exec_engine.process_signal(symbol, intent)
```

## Runtime Metrics

ExecutionEngine V3 updates `artifacts/analytics/runtime_metrics.json`:

```json
{
  "total_orders": 10,
  "active_positions": 3,
  "realized_pnl": 1250.50,
  "unrealized_pnl": 350.25,
  "total_pnl": 1600.75
}
```

## Monitoring and Debugging

### View Active Positions

```python
positions = exec_engine.get_positions()
for pos in positions:
    print(f"{pos.symbol}: {pos.qty} @ {pos.entry_price}, "
          f"PnL: {pos.unrealized_pnl}")
```

### View Order History

```python
for order in exec_engine.active_orders.values():
    print(f"Order {order.order_id}:")
    print(f"  State: {order.state}")
    print(f"  Entry: {order.entry_price}")
    print(f"  Current: {order.current_price}")
    print(f"  SL: {order.sl_price}, TP: {order.tp_price}")
    print(f"  Bars held: {order.bars_held}")
    print(f"  Events: {len(order.events)}")
```

### Check Metrics

```python
metrics = exec_engine.get_metrics()
print(f"Active positions: {metrics['active_positions']}")
print(f"Realized PnL: {metrics['realized_pnl']:.2f}")
print(f"Unrealized PnL: {metrics['unrealized_pnl']:.2f}")
```

## Testing

Run the test suite:

```bash
pytest tests/test_execution_engine_v3_new.py -v
```

All 24 tests should pass:
- OrderBuilder (3 tests)
- FillEngine (3 tests)
- StopLossManager (5 tests)
- TakeProfitManager (3 tests)
- TrailingStopManager (1 test)
- TimeStopManager (3 tests)
- TradeLifecycleManager (3 tests)
- ExecutionEngineV3 (3 tests)

## Best Practices

1. **Set Reasonable SL/TP**: Use ATR-based or percentage-based levels
2. **Use Partial Exits**: Reduces risk while allowing profits to run
3. **Enable Trailing**: Maximizes profits on trending moves
4. **Set Time Stops**: Prevents capital lock in non-trending positions
5. **Monitor Metrics**: Check runtime_metrics.json regularly
6. **Test in Paper Mode**: Validate configuration before live trading

## Troubleshooting

### ExecutionEngine V3 not initializing

Check config:
```yaml
execution:
  engine: v3  # Must be "v3", not "V3" or "v2"
```

### Positions not updating

Ensure market data engine is providing prices:
```python
# Check if prices are being received
ltp = mde.get_last_price(symbol)
print(f"LTP for {symbol}: {ltp}")
```

### SL/TP not triggering

Verify prices are crossing levels:
```python
order = exec_engine.active_orders[order_id]
print(f"Entry: {order.entry_price}")
print(f"Current: {order.current_price}")
print(f"SL: {order.sl_price}, TP: {order.tp_price}")
```

## Architecture

```
StrategyEngineV2
    |
    | OrderIntent
    |
    v
ExecutionEngineV3
    |
    +-- OrderBuilder (construct orders)
    +-- FillEngine (determine fill price)
    +-- TradeLifecycleManager (state transitions)
    |
    +-- Position Monitoring Loop
        |
        +-- StopLossManager (check SL)
        +-- TakeProfitManager (check TP)
        +-- TrailingStopManager (update trailing SL)
        +-- TimeStopManager (check time stop)
        |
        v
    TradeRecorder (persist trades)
    RuntimeMetrics (update metrics)
```

## Future Enhancements

Potential future additions:
- Multiple SL/TP levels
- Scale-in (add to winning positions)
- Bracket orders for options
- Execution quality metrics
- Slippage analysis
- Fill rate statistics
