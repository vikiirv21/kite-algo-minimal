# Portfolio & Position Sizing Engine v1

## Overview

The Portfolio & Position Sizing Engine v1 is a comprehensive position sizing system that calculates **how much to trade** for each order based on:

- Per-strategy capital budgets
- Per-symbol exposure limits
- Overall account equity
- Optional volatility (ATR) sizing
- Risk rules (max risk per trade, max leverage)

The engine sits between the Strategy Engine and Execution Engine in the order pipeline:

```
StrategyEngine v2 → (raw trade idea: direction only)
       ↓
PortfolioEngine v1 → (fills in qty/size)
       ↓
RiskEngine + ExecutionEngine → (approve + execute)
```

## Features

### Position Sizing Modes

1. **Fixed Quantity Mode (`fixed_qty`)**
   - Uses pre-configured quantities
   - Can set per-strategy or global defaults
   - Simple and predictable

2. **ATR-Based Risk Mode (`fixed_risk_atr`)**
   - Dynamically sizes based on volatility
   - Uses ATR (Average True Range) for stop distance
   - Formula: `qty = risk_per_trade / (atr_multiplier * ATR * point_value)`

### Capital Management

- **Strategy Budgets**: Allocate % of equity to each strategy
- **Exposure Limits**: Cap total portfolio exposure
- **Leverage Control**: Set maximum leverage multiplier
- **Risk Per Trade**: Limit risk as % of equity per trade

## Configuration

Add to `configs/dev.yaml`:

```yaml
portfolio:
  # Position sizing mode
  position_sizing_mode: "fixed_qty"  # or "fixed_risk_atr"
  
  # Risk limits
  max_leverage: 2.0                  # Max 2x leverage
  max_exposure_pct: 0.8              # Max 80% of equity exposed
  max_risk_per_trade_pct: 0.01       # Risk 1% per trade
  max_risk_per_strategy_pct: 0.2     # Max 20% risk per strategy (fallback)
  
  # Fixed quantity mode settings
  default_fixed_qty: 1               # Default qty if not specified
  
  # ATR mode settings
  atr_stop_multiplier: 2.0           # Stop distance = 2 * ATR
  lot_size_fallback: 25              # Default lot size for FnO
  
  # Per-strategy budgets
  strategy_budgets:
    ema20_50_intraday:
      capital_pct: 0.3               # 30% of equity
      fixed_qty: 1                   # Optional: override default_fixed_qty
    
    expiry_scalper:
      capital_pct: 0.4               # 40% of equity
      fixed_qty: 2
```

## Usage

### Automatic Integration

The PortfolioEngine is automatically initialized and integrated if the `portfolio` section exists in your config. No code changes needed!

**Paper Trading:**
```bash
python -m scripts.run_day --mode paper --engines all
```

**Live Trading:**
```bash
python -m scripts.run_day --mode live --engines all
```

### API Monitoring

Check portfolio status via API:

```bash
curl http://localhost:9000/api/portfolio/limits
```

Response:
```json
{
  "ok": true,
  "equity": 500000.0,
  "max_exposure": 800000.0,
  "current_exposure": 150000.0,
  "available_exposure": 650000.0,
  "exposure_utilization_pct": 18.75,
  "per_strategy": {
    "ema20_50_intraday": {
      "budget": 150000.0,
      "used": 50000.0,
      "available": 100000.0,
      "utilization_pct": 33.33
    },
    "expiry_scalper": {
      "budget": 200000.0,
      "used": 100000.0,
      "available": 100000.0,
      "utilization_pct": 50.0
    }
  },
  "config": {
    "max_leverage": 2.0,
    "max_exposure_pct": 0.8,
    "max_risk_per_trade_pct": 0.01,
    "position_sizing_mode": "fixed_qty"
  }
}
```

## How It Works

### Order Pipeline

When a strategy generates a trade signal:

1. **Strategy Engine** creates an `OrderIntent` with:
   - Symbol
   - Side (BUY/SELL)
   - Strategy code
   - Optional: qty (if already determined)

2. **PortfolioEngine** computes position size:
   - If `qty` already set: validates and clamps to limits
   - If `qty` is None: calculates based on mode (fixed_qty or ATR)
   - Enforces exposure limits
   - Enforces strategy budgets

3. **RiskEngine** validates the trade

4. **ExecutionEngine** places the order

### Fixed Quantity Mode

Priority order for determining qty:
1. Intent's pre-set qty (if provided)
2. Strategy-specific `fixed_qty` from config
3. Global `default_fixed_qty` from config

The computed qty is then clamped by:
- Total exposure limit (equity * max_exposure_pct * max_leverage)
- Strategy budget (equity * strategy_capital_pct)

### ATR-Based Mode

For each trade:

1. **Get ATR value** (from strategy or MDE)
2. **Calculate risk**: `risk = equity * max_risk_per_trade_pct`
3. **Calculate stop distance**: `stop = atr_stop_multiplier * ATR`
4. **Calculate quantity**:
   - For equity: `qty = floor(risk / stop)`
   - For FnO: `qty = floor(risk / (stop * lot_size)) * lot_size`
5. **Apply exposure limits** (same as fixed mode)

## Architecture

### Core Classes

#### `PortfolioConfig`

Configuration dataclass with all portfolio settings.

**Key attributes:**
- `position_sizing_mode`: "fixed_qty" or "fixed_risk_atr"
- `max_leverage`: Maximum leverage multiplier
- `max_exposure_pct`: Max portfolio exposure as % of equity
- `max_risk_per_trade_pct`: Risk per trade as % of equity
- `strategy_budgets`: Dict of strategy configurations

#### `PortfolioEngine`

Main engine class for position sizing.

**Key methods:**

```python
def get_equity() -> float:
    """Read current equity from state store."""

def compute_strategy_budget(strategy_code: str) -> float:
    """Calculate max capital allocation for strategy."""

def compute_symbol_exposure(symbol: str) -> float:
    """Return current exposure for symbol."""

def compute_position_size(
    intent: OrderIntent,
    last_price: float,
    atr_value: Optional[float] = None
) -> int:
    """
    Core method: compute quantity for an order.
    Returns 0 if trade should not be taken.
    """

def get_portfolio_limits() -> Dict[str, Any]:
    """Get portfolio status for API/dashboard."""
```

### Integration Points

**PaperEngine** (`engine/paper_engine.py`):
- Initialized in `__init__` if portfolio config present
- Called in `_place_paper_order()` before executing
- Falls back to legacy sizer if not configured

**LiveEngine** (`engine/live_engine.py`):
- Same integration pattern as paper mode
- Ensures consistent sizing across modes

## Testing

### Unit Tests

Run the comprehensive test suite:

```bash
python tests/test_portfolio_engine.py
```

Tests cover:
- Config loading
- Equity reading
- Strategy budget calculation
- Fixed qty mode
- ATR-based mode
- Exposure limits enforcement
- Portfolio limits API

### Integration Tests

Validate the full integration:

```bash
python tests/validate_portfolio_engine.py
```

Validates:
- Config loading
- Engine initialization
- Position sizing modes
- Exposure calculation
- API functionality
- Integration with Paper/Live engines

## Advanced Configuration

### Multiple Strategies

```yaml
portfolio:
  position_sizing_mode: "fixed_risk_atr"
  max_exposure_pct: 0.9
  
  strategy_budgets:
    ema_crossover:
      capital_pct: 0.25
    
    breakout_strategy:
      capital_pct: 0.30
    
    mean_reversion:
      capital_pct: 0.20
    
    momentum_strategy:
      capital_pct: 0.25
```

### Mixed Mode Strategies

You can mix fixed and dynamic strategies:

```yaml
portfolio:
  position_sizing_mode: "fixed_qty"
  default_fixed_qty: 1
  
  strategy_budgets:
    conservative_strategy:
      capital_pct: 0.3
      fixed_qty: 1          # Small fixed size
    
    aggressive_strategy:
      capital_pct: 0.4
      fixed_qty: 5          # Larger fixed size
```

## Troubleshooting

### Zero Quantity Computed

**Symptom**: `compute_position_size()` returns 0

**Possible causes:**
1. No equity in state store (check checkpoint file)
2. Exposure limit reached
3. Strategy budget exhausted
4. ATR value too low or not provided (in ATR mode)

**Solution:**
- Check logs for specific reason
- Verify state checkpoint exists
- Review exposure limits in config

### Unexpected Quantity Size

**Symptom**: Qty different than expected

**Check:**
1. Position sizing mode (fixed_qty vs ATR)
2. Strategy-specific `fixed_qty` override
3. Exposure limits clamping the size
4. ATR value if using ATR mode

## Future Enhancements

Potential improvements for v2:

1. **Per-symbol exposure limits**
   - Cap exposure per individual symbol
   - Prevent concentration risk

2. **Kelly Criterion sizing**
   - Optimal bet sizing based on win rate
   - Adaptive to strategy performance

3. **Correlation-aware sizing**
   - Reduce size for correlated positions
   - Better portfolio diversification

4. **Dynamic budget rebalancing**
   - Adjust strategy allocations based on performance
   - Integration with learning engine

5. **Drawdown-based scaling**
   - Reduce size during drawdowns
   - Increase size during winning streaks

## References

- ATR (Average True Range): Volatility indicator used for sizing
- Position Sizing: Determining trade quantity based on risk
- Kelly Criterion: Mathematical formula for optimal bet sizing
- Exposure Management: Tracking and limiting capital at risk

## Support

For issues or questions:
1. Check logs: `artifacts/logs/`
2. Run validation: `python tests/validate_portfolio_engine.py`
3. Review config: `configs/dev.yaml`
4. Check API: `GET /api/portfolio/limits`
