# ExecutionEngine v2 Implementation Summary

## Overview

ExecutionEngine v2 is a unified execution layer that sits between StrategyEngine v2 + RiskEngine and the actual execution path (PaperEngine or LiveEngine). It provides normalized interfaces, circuit breakers, and consistent execution handling for both paper and live trading.

## Architecture

```
┌─────────────────────┐
│  StrategyEngine v2  │
└──────────┬──────────┘
           │ OrderIntent
           ▼
┌─────────────────────┐
│   RiskEngine        │
└──────────┬──────────┘
           │ Approved OrderIntent
           ▼
┌─────────────────────────────────┐
│   ExecutionEngine v2            │
│  ┌──────────────────────────┐   │
│  │  Circuit Breakers        │   │
│  │  - Max daily loss        │   │
│  │  - Max drawdown          │   │
│  │  - Trading halted check  │   │
│  └────────┬─────────────────┘   │
│           │                      │
│     ┌─────▼──────┐              │
│     │   Router   │              │
│     └─────┬──────┘              │
│      ┌────┴─────┐               │
│      │          │               │
│  ┌───▼───┐  ┌───▼──────┐       │
│  │ Paper │  │   Live   │       │
│  │ Smart │  │  Broker  │       │
│  │ Fill  │  │  (Kite)  │       │
│  │ Sim   │  │          │       │
│  └───┬───┘  └───┬──────┘       │
│      │          │               │
│      └──────┬───┘               │
│             │ ExecutionResult   │
└─────────────┼───────────────────┘
              │
              ▼
     ┌────────────────┐
     │  JournalStore  │
     │  StateStore    │
     └────────────────┘
```

## Key Components

### 1. OrderIntent (Extended)
```python
@dataclass
class OrderIntent:
    symbol: str
    strategy_code: str
    side: str          # 'BUY' / 'SELL'
    qty: int
    order_type: str    # 'MARKET' / 'LIMIT'
    product: str       # 'MIS' / 'NRML' / 'CNC'
    validity: str      # 'DAY' / 'IOC'
    price: Optional[float]
    trigger_price: Optional[float]
    tag: Optional[str]
    reason: str
    confidence: float
    metadata: Dict[str, Any]
```

### 2. ExecutionResult
```python
@dataclass
class ExecutionResult:
    order_id: Optional[str]
    status: str        # 'PLACED', 'REJECTED', 'FILLED', 'PARTIAL', 'CANCELLED'
    symbol: str
    side: str
    qty: int
    avg_price: Optional[float]
    message: Optional[str]
    raw: Optional[Dict[str, Any]]
    timestamp: Optional[str]
```

### 3. SmartFillSimulator (Paper Mode)
- Simulates order fills using market data from MarketDataEngine v2
- Configurable slippage (default 5 basis points)
- MARKET orders: Fill at LTP ± slippage
- LIMIT orders: Fill only if price is marketable
- Instant fills (partial fill support ready for future)

### 4. ExecutionEngineV2
Main execution engine with:
- **Circuit breakers**: Checks before routing
- **Mode routing**: Paper → SmartFillSimulator, Live → Broker
- **Position tracking**: Updates via StateStore
- **Journal updates**: Appends to JournalStateStore
- **Error handling**: Graceful fallback to legacy execution

## Configuration

Add to `configs/dev.yaml`:

```yaml
execution:
  # ExecutionEngine v2 configuration
  use_execution_engine_v2: false  # Set to true to enable
  dry_run: false  # When true, simulates live orders without actual placement
  slippage_bps: 5.0  # Slippage in basis points for paper fills
  use_bid_ask_spread: false  # Use bid-ask spread for more realistic fills
  
  circuit_breakers:
    max_daily_loss_rupees: 5000.0  # Stop trading when daily loss exceeds this
    max_daily_drawdown_pct: 0.02  # Stop trading when drawdown exceeds 2%
    max_trades_per_day: 100  # Maximum trades per day
    max_trades_per_strategy_per_day: 50  # Maximum trades per strategy per day
    max_loss_streak: 5  # Stop trading after N consecutive losses
```

## Usage

### Paper Mode
```python
# In PaperEngine initialization, ExecutionEngine v2 is automatically
# initialized if config flag is enabled

# When placing orders, PaperEngine will use ExecutionEngine v2 if available
if self.execution_engine_v2 is not None:
    result = self.execution_engine_v2.execute_intent(intent)
else:
    # Fall back to legacy execution
    order = self.router.place_order(symbol, side, qty, price)
```

### Live Mode
```python
# In LiveEngine initialization, ExecutionEngine v2 is automatically
# initialized if config flag is enabled

# When placing orders
if self.execution_engine_v2 is not None:
    result = self.execution_engine_v2.execute_intent(intent)
else:
    # Fall back to legacy execution
    result = self.broker.place_order(intent)
```

## Circuit Breakers

ExecutionEngine v2 checks the following before routing orders:

1. **TradeThrottler**: If configured, uses throttler's can_trade() check
2. **Max Daily Loss**: Blocks if realized_pnl < -max_daily_loss_rupees
3. **Max Drawdown**: Blocks if drawdown_pct > max_daily_drawdown_pct
4. **Trading Halted**: Blocks if risk engine has halted trading

When circuit breaker fires:
- Returns ExecutionResult with status='REJECTED'
- Logs WARNING with reason
- Does NOT place order

## Testing

Comprehensive test suite in `tests/test_execution_engine_v2.py`:

```bash
python tests/test_execution_engine_v2.py
```

Tests cover:
- ✅ SmartFillSimulator MARKET orders (BUY/SELL with slippage)
- ✅ SmartFillSimulator LIMIT orders (marketable/non-marketable)
- ✅ Circuit breakers (max loss, trading halted)
- ✅ ExecutionEngine paper mode execution
- ✅ ExecutionEngine live mode with dry_run
- ✅ Journal updates after execution

## Migration Path

### Phase 1: Paper Mode Testing
1. Set `execution.use_execution_engine_v2: true` in config
2. Run paper engine: `python -m scripts.run_day --mode paper --engines all`
3. Verify orders are executed via ExecutionEngine v2
4. Check journals in `artifacts/journal/`

### Phase 2: Live Mode Dry Run
1. Keep `execution.use_execution_engine_v2: true`
2. Set `execution.dry_run: true`
3. Run live engine (orders will be simulated, not placed)
4. Verify circuit breakers work correctly

### Phase 3: Live Mode Production
1. Set `execution.dry_run: false`
2. Monitor first few orders closely
3. Verify fills are tracked correctly
4. Check position and journal updates

## Backward Compatibility

- ExecutionEngine v2 is **OFF by default** (`use_execution_engine_v2: false`)
- When disabled, engines use legacy execution path
- If v2 initialization fails, falls back to legacy execution
- If v2 execution fails, falls back to legacy execution
- No breaking changes to existing code

## Files Changed

### New Files
- `engine/execution_engine.py` - Core implementation (750 lines)
- `engine/execution_bridge.py` - Integration helpers (150 lines)
- `tests/test_execution_engine_v2.py` - Test suite (400 lines)

### Modified Files
- `configs/dev.yaml` - Added execution config section
- `engine/paper_engine.py` - Optional v2 initialization and usage
- `engine/live_engine.py` - Optional v2 initialization and usage

## Benefits

1. **Unified Interface**: Single execution layer for both paper and live
2. **Safety**: Circuit breakers prevent catastrophic losses
3. **Flexibility**: Easy to add new execution modes (e.g., backtesting)
4. **Testing**: Dry run mode for safe live testing
5. **Observability**: Consistent logging and journaling
6. **Maintainability**: Separation of concerns, easier to extend

## Future Enhancements

Potential improvements for later:
- [ ] Partial fill simulation in paper mode
- [ ] Advanced slippage models (volume-based, volatility-based)
- [ ] Order book depth simulation
- [ ] Multi-leg order support (spreads, combos)
- [ ] Smart order routing (TWAP, VWAP, Iceberg)
- [ ] Fill probability modeling
- [ ] Execution cost analysis
- [ ] Performance attribution per execution method

## Support

For issues or questions:
1. Check logs in `artifacts/logs/`
2. Review journals in `artifacts/journal/`
3. Run test suite: `python tests/test_execution_engine_v2.py`
4. Verify config settings in `configs/dev.yaml`
