# Strategy Engine v2 - Implementation Guide

## Overview

Strategy Engine v2 is a modern, production-grade strategy execution framework designed to run in paper mode during live markets. It provides:

- **Unified signal intake** - Normalizes signals from all strategies into a common `StrategySignal` format
- **Per-strategy state management** - Tracks positions, PnL, win/loss streaks, and recent decisions
- **Deterministic filtering pipeline** - Validates signals through basic and risk-based filters
- **Pluggable conflict resolution** - Resolves conflicts when multiple strategies emit signals on the same symbol
- **Clean separation of concerns** - Clear interfaces between strategy logic, market data, and execution

## Architecture

```
Strategy Modules
       ↓
   Decisions
       ↓
  Normalize → StrategySignal
       ↓
  Basic Filter (market open, valid symbol)
       ↓
  Risk Filter (max trades, loss streaks)
       ↓
  Conflict Resolution (highest confidence / priority / net-out)
       ↓
  OrderIntent (execution-ready)
       ↓
  PaperEngine → Execution
```

## Configuration

Strategy Engine v2 is **opt-in** via configuration. The default remains v1 for backward compatibility.

### Enable Strategy Engine v2

In `configs/dev.yaml`:

```yaml
strategy_engine:
  version: 2                # Use v2 (default is 1)
  enabled: true
  
  # V2 strategies to enable
  strategies_v2:
    - ema20_50_intraday_v2
  
  # Historical window for indicators
  window_size: 200
  
  # Filtering configuration
  max_trades_per_day: 10    # Per-strategy daily limit
  max_loss_streak: 3        # Disable after N losses
  
  # Conflict resolution mode
  conflict_resolution: "highest_confidence"  # or "priority" or "net_out"
  
  # Optional: Strategy priorities for priority mode
  strategy_priorities:
    ema20_50_intraday_v2: 100
    other_strategy: 50
```

### Conflict Resolution Modes

1. **highest_confidence** (default)
   - When multiple strategies emit conflicting signals on the same symbol
   - Chooses the signal with the highest confidence score
   - Simple and effective for most cases

2. **priority**
   - Uses explicit strategy priorities from `strategy_priorities` config
   - Higher priority number = higher precedence
   - Useful when you have a preferred strategy hierarchy

3. **net_out**
   - Calculates weighted sum of long vs short signals
   - If net difference is strong enough (>0.5), uses that direction
   - Otherwise, skips the trade (conflict too strong)
   - Conservative approach for risk management

## Data Models

### StrategySignal

Normalized representation of a strategy decision:

```python
signal = StrategySignal(
    timestamp=datetime.utcnow(),
    symbol="NIFTY",
    strategy_name="ema20_50_intraday_v2",
    direction="long",  # "long", "short", or "flat"
    strength=0.8,      # Confidence 0.0-1.0
    tags={"reason": "bullish_crossover"}
)
```

### OrderIntent

Execution-ready trading intent:

```python
intent = OrderIntent(
    symbol="NIFTY",
    action="BUY",  # "BUY", "SELL", or "EXIT"
    qty=1,
    reason="bullish_crossover",
    strategy_code="ema20_50_intraday_v2",
    confidence=0.8,
    metadata={"timeframe": "5m"}
)
```

### StrategyState

Per-strategy state tracking:

```python
state = StrategyState()
state.trades_today = 5
state.win_streak = 2
state.loss_streak = 0
state.recent_pnl = 150.0
state.recent_decisions = [...]  # Last 20 decisions
```

## Writing v2 Strategies

Strategies for v2 inherit from `BaseStrategy` and implement `generate_signal()`:

```python
from core.strategy_engine_v2 import BaseStrategy, StrategyState
from strategies.base import Decision

class MyStrategyV2(BaseStrategy):
    def __init__(self, config, strategy_state):
        super().__init__(config, strategy_state)
        self.name = "my_strategy_v2"
    
    def generate_signal(self, candle, series, indicators):
        """
        Args:
            candle: Current candle dict (open, high, low, close, volume)
            series: Historical series dict (close, high, low lists)
            indicators: Pre-computed indicators (ema20, ema50, rsi14, etc.)
        
        Returns:
            Decision object (BUY, SELL, EXIT, HOLD)
        """
        close = candle.get("close", 0)
        ema20 = indicators.get("ema20")
        ema50 = indicators.get("ema50")
        
        if ema20 > ema50:
            return Decision(action="BUY", reason="bullish", confidence=0.8)
        elif ema20 < ema50:
            return Decision(action="SELL", reason="bearish", confidence=0.8)
        
        return Decision(action="HOLD", reason="neutral", confidence=0.0)
```

## Integration with PaperEngine

PaperEngine automatically switches between v1 and v2 based on config:

```python
# In engine/paper_engine.py (already implemented)
if strategy_engine_version == 2:
    self.strategy_engine_v2 = StrategyEngineV2(
        config=full_config,
        mde=self.market_data_engine,
        portfolio_engine=self.portfolio_engine,
        regime_engine=self.regime_detector,
        ...
    )
    self.strategy_runner = None  # Disable v1
else:
    self.strategy_runner = StrategyRunner(...)  # Use v1
    self.strategy_engine_v2 = None
```

In the main loop:

```python
if self.strategy_engine_v2:
    # Use v2
    self.strategy_engine_v2.run(symbols)
elif self.strategy_runner:
    # Use v1 (default)
    self.strategy_runner.run(ticks)
```

## Migration from v1 to v2

### Step 1: Test v1 (baseline)

Keep `version: 1` and validate current behavior:

```bash
# Run with v1
python scripts/run_paper_fno.py
```

### Step 2: Enable v2

Update config:

```yaml
strategy_engine:
  version: 2
  strategies_v2:
    - ema20_50_intraday_v2
```

### Step 3: Validate v2

Run same test scenario:

```bash
# Run with v2
python scripts/run_paper_fno.py
```

Compare results:
- Check `artifacts/signals.csv` - should have similar signal count
- Check `artifacts/orders.csv` - should have similar order flow
- Check `artifacts/equity.csv` - equity curve should be comparable

### Step 4: Monitor in production

- Start with one strategy in v2
- Monitor logs for "Using Strategy Engine v2" confirmation
- Check for any filtering/conflict resolution messages
- Gradually migrate more strategies

## Testing

Run comprehensive tests:

```bash
# Unit tests
python tests/test_strategy_engine_v2.py

# Integration validation
python tests/validate_strategy_engine_integration.py
```

## Backward Compatibility

✅ **Preserved**:
- Signal format in `signals.csv`
- Order format in `orders.csv`
- Equity snapshot format
- Performance metrics API
- Dashboard JSON shapes

✅ **Default behavior**:
- v1 (StrategyRunner) is default
- Existing paper engines work unchanged
- No breaking changes to public APIs

## Performance Considerations

v2 is designed to be efficient:

- Indicators computed once per symbol/timeframe (shared across strategies)
- Filtering pipeline short-circuits on first failure
- Conflict resolution only runs when conflicts exist
- State updates are incremental

Expected overhead vs v1: < 5% in typical scenarios

## Troubleshooting

### Strategy not running

Check logs for:
```
[strategy-skip] ema20_50_intraday_v2: <reason>
```

Common reasons:
- Market closed (`basic_filter: market_closed`)
- Max trades reached (`risk_filter: max_trades_per_day`)
- Loss streak limit (`risk_filter: loss_streak`)

### Signals filtered out

Enable debug logging:

```yaml
logging:
  level: "DEBUG"
```

Look for:
```
Signal rejected (basic): <strategy> - <reason>
Signal rejected (risk): <strategy> - <reason>
```

### Conflicts not resolved as expected

Check conflict resolution mode and priorities:

```
Conflict resolved for NIFTY: strategy_a long (conf=0.80)
```

Verify `conflict_resolution` and `strategy_priorities` config.

## Future Enhancements

Potential improvements for v3:

- [ ] Machine learning-based conflict resolution
- [ ] Dynamic risk adjustment based on market regime
- [ ] Multi-timeframe signal aggregation
- [ ] Portfolio-level position sizing
- [ ] Real-time performance attribution

## Support

For issues or questions:
1. Check logs in `artifacts/logs/`
2. Review test output from `tests/test_strategy_engine_v2.py`
3. Validate config with `tests/validate_strategy_engine_integration.py`
