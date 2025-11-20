# Advanced Risk Metrics API - Implementation Summary

## Overview

This implementation adds backend support for the "Advanced Risk Metrics" section on the dashboard, providing comprehensive risk monitoring and management capabilities.

## API Endpoints

### 1. GET /api/risk/limits

Returns all configured risk limits from config + overrides.

**Response Structure:**
```json
{
  "mode": "paper",
  "capital": 500000.0,
  "limits": {
    "max_daily_loss_rupees": 5000.0,
    "max_daily_drawdown_pct": 0.02,
    "max_trades_per_day": 100,
    "max_trades_per_strategy_per_day": 50,
    "max_loss_streak": 5,
    "per_symbol_max_loss": 1500.0,
    "max_open_positions": null,
    "max_exposure_pct": 0.8,
    "max_leverage": 2.0,
    "max_risk_per_trade_pct": 0.01,
    "max_daily_loss_pct": 0.01
  },
  "source": {
    "config_file": "configs/dev.yaml",
    "overrides_file": "configs/learned_overrides.yaml"
  }
}
```

**Data Sources:**
- `config["trading"]` - Paper capital, per-symbol max loss, max open positions
- `config["execution"]["circuit_breakers"]` - Daily loss limits, trade limits, loss streak
- `config["portfolio"]` - Exposure limits, leverage, risk per trade
- `configs/learned_overrides.yaml` - Runtime overrides

### 2. GET /api/risk/breaches

Returns current risk violations by evaluating runtime state against configured limits.

**Response Structure:**
```json
{
  "mode": "paper",
  "asof": "2025-11-20T04:39:49.588671",
  "breaches": [
    {
      "id": "daily_loss_exceeded",
      "severity": "critical",
      "message": "Daily realized PnL -7500.0 below limit -5000.0",
      "metric": "realized_pnl",
      "value": -7500.0,
      "limit": -5000.0
    }
  ]
}
```

**Breach Types:**
- `daily_loss_exceeded` - Daily PnL below max_daily_loss_rupees (critical)
- `daily_drawdown_exceeded` - Equity drawdown exceeds max_daily_drawdown_pct (critical)
- `max_exposure_exceeded` - Total notional exposure exceeds max_exposure_pct (warning)
- `max_open_positions_exceeded` - Too many open positions (warning)
- `max_trades_per_day_exceeded` - Too many trades today (warning)

**Data Sources:**
- `artifacts/analytics/runtime_metrics.json` - Performance metrics (primary)
- `artifacts/checkpoints/runtime_state_latest.json` - Runtime state (fallback)
- `artifacts/orders.csv` - Order history

### 3. GET /api/risk/var

Returns Value at Risk (VaR) calculation based on historical trades.

**Query Parameters:**
- `confidence` (float, optional): Confidence level (0.5-0.99), default 0.95

**Response Structure:**
```json
{
  "mode": "paper",
  "confidence": 0.95,
  "var_rupees": 2500.0,
  "var_pct": 0.005,
  "sample_trades": 120,
  "status": "ok"
}
```

**Status Values:**
- `ok` - VaR calculated successfully (requires ≥10 closed trades)
- `insufficient_data` - Not enough trades for calculation
- `error` - Calculation error

**Method:**
Simple empirical VaR using historical trade PnL distribution:
1. Load filled orders from artifacts/orders.csv
2. Reconstruct closed trades using FIFO position model
3. Sort trade PnLs and extract percentile at (1 - confidence)
4. VaR = absolute value of loss at percentile

### 4. POST /api/risk/limits

Update risk limits via runtime overrides. Changes are persisted to `configs/learned_overrides.yaml`.

**Request Body:**
```json
{
  "max_daily_loss_rupees": 6000.0,
  "max_trades_per_day": 120
}
```

**Allowed Fields:**
- `max_daily_loss_rupees` (float) - Maximum daily loss in rupees
- `max_daily_drawdown_pct` (float) - Maximum daily drawdown percentage
- `max_trades_per_day` (int) - Maximum trades per day
- `max_trades_per_strategy_per_day` (int) - Maximum trades per strategy per day
- `max_loss_streak` (int) - Maximum consecutive losses
- `max_exposure_pct` (float) - Maximum exposure as % of equity
- `max_leverage` (float) - Maximum leverage multiplier
- `max_risk_per_trade_pct` (float) - Maximum risk per trade as % of equity
- `per_symbol_max_loss` (float) - Maximum loss per symbol in rupees
- `max_open_positions` (int or null) - Maximum open positions (null = unlimited)

**Validation:**
- Numeric fields must be non-negative
- Integer fields must be positive
- Invalid fields are ignored with warning
- Type mismatches return 400 error

**Response Structure:**
```json
{
  "status": "ok",
  "limits": { /* updated limits object */ },
  "updated_fields": ["max_daily_loss_rupees", "max_trades_per_day"]
}
```

## Implementation Details

### Module: analytics/risk_metrics.py

**Function: load_risk_limits(config, overrides)**
- Aggregates risk limits from multiple config sections
- Applies overrides with proper nested structure
- Calculates derived metrics (e.g., max_daily_loss_pct from rupees)
- Returns normalized limits structure

**Function: compute_risk_breaches(config, runtime_metrics_path, checkpoint_path, orders_path, mode)**
- Loads runtime metrics (primary) or checkpoint (fallback)
- Extracts current equity, PnL, positions, trades
- Evaluates each limit against current state
- Returns list of violations with severity classification

**Function: compute_var(orders_path, capital, confidence, mode)**
- Loads filled orders from CSV
- Reconstructs closed trades using FIFO position model
- Computes empirical VaR from trade PnL distribution
- Handles insufficient data gracefully

### Module: apps/dashboard.py

**Helper: load_config_and_overrides(default_config_path)**
- Loads base config from YAML
- Loads overrides from learned_overrides.yaml
- Returns tuple (config_dict, overrides_dict)
- Used consistently by all risk endpoints

**Endpoints:**
- All endpoints use defensive error handling
- Missing files return sensible defaults instead of errors
- Errors are logged but don't crash the server
- Response structures match expected API contract

## Testing

### Integration Tests: tests/test_risk_metrics_integration.py
- Tests all three core functions
- Validates config loading with/without overrides
- Verifies breach detection logic
- Tests VaR calculation with different confidence levels
- Validates override update logic

### Manual Validation: tests/validate_risk_api.py
- Simulates all four endpoints without server
- Validates request/response structures
- Tests payload validation logic
- Provides usage instructions

### Existing Test: tests/manual_test_risk_api.py
- End-to-end test with running server
- Tests all endpoints via HTTP
- Validates updates and error cases
- Requires: `python -m uvicorn apps.dashboard:app --host 127.0.0.1 --port 8765`

## Design Principles

1. **Non-Breaking**: All changes are additive, no existing functionality modified
2. **Defensive**: Graceful degradation when files missing or data incomplete
3. **Generic**: Works for both paper and live modes
4. **Consistent**: Reuses existing config loading and performance helpers
5. **Minimal**: Smallest possible changes to achieve requirements

## Configuration Sources

Risk limits are loaded from multiple config sections:

```yaml
# configs/dev.yaml
trading:
  paper_capital: 500000
  max_daily_loss: 3000
  per_symbol_max_loss: 1500
  max_open_positions: null

execution:
  circuit_breakers:
    max_daily_loss_rupees: 5000.0
    max_daily_drawdown_pct: 0.02
    max_trades_per_day: 100
    max_trades_per_strategy_per_day: 50
    max_loss_streak: 5

portfolio:
  max_leverage: 2.0
  max_exposure_pct: 0.8
  max_risk_per_trade_pct: 0.01
```

Overrides are applied from:
```yaml
# configs/learned_overrides.yaml
execution:
  circuit_breakers:
    max_daily_loss_rupees: 6000.0
```

## Future Enhancements

1. **Correlation-Adjusted Exposure**: Track position correlations for better risk measurement
2. **Historical VaR**: Support multi-day VaR calculations
3. **Conditional VaR (CVaR)**: Expected shortfall beyond VaR
4. **Stress Testing**: Simulate extreme scenarios
5. **Real-time Alerts**: Push notifications for breach events
6. **Historical Breach Log**: Track breach history over time

## Usage Examples

### Get Current Limits
```bash
curl http://127.0.0.1:8765/api/risk/limits
```

### Check for Breaches
```bash
curl http://127.0.0.1:8765/api/risk/breaches
```

### Calculate VaR
```bash
curl "http://127.0.0.1:8765/api/risk/var?confidence=0.99"
```

### Update Limits
```bash
curl -X POST http://127.0.0.1:8765/api/risk/limits \
  -H "Content-Type: application/json" \
  -d '{"max_daily_loss_rupees": 6000.0, "max_trades_per_day": 120}'
```

## Files Changed

- `analytics/risk_metrics.py` (NEW) - Core risk metrics functions
- `apps/dashboard.py` - Added 4 risk API endpoints + config helper
- `tests/test_risk_metrics_integration.py` (NEW) - Integration tests
- `tests/validate_risk_api.py` (NEW) - Manual validation script

## Security

- All numeric inputs are validated
- Type checking prevents injection attacks
- Only allowed fields can be updated via API
- File writes use safe YAML serialization
- CodeQL scan: 0 vulnerabilities found

## Status

✅ Implementation complete
✅ All tests passing
✅ Security scan clean
✅ Ready for production use
