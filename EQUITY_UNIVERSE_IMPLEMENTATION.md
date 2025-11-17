# Equity Universe Filtering - Implementation Guide

## Overview

This implementation restricts the equity trading universe to only NIFTY 50 and NIFTY 100 stocks, eliminating random illiquid and penny stocks. FnO (NIFTY, BANKNIFTY, options) continue to work as-is.

## What Was Changed

### 1. Configuration (configs/dev.yaml)

Added new `equity_universe_config` section:

```yaml
trading:
  # ... existing config ...
  
  equity_universe_config:
    mode: "nifty_lists"              # "nifty_lists" or "all" (default)
    include_indices: ["NIFTY50", "NIFTY100"]
    max_symbols: 120                 # soft cap
    min_price: 100                   # drop penny/very low-priced stocks
```

**Configuration Options:**
- `mode`: 
  - `"nifty_lists"`: Use NIFTY 50/100 stocks
  - `"all"` (or any other value): Falls back to existing behavior (config/universe_equity.csv)
- `include_indices`: List of indices to include (e.g., ["NIFTY50"], ["NIFTY100"], or both)
- `max_symbols`: Maximum number of symbols to trade (soft cap)
- `min_price`: Minimum stock price threshold to filter out penny stocks

**Backward Compatibility:**
If this configuration block is missing, the system will fall back to the existing behavior (loading from config/universe_equity.csv).

### 2. NIFTY Lists Module (data/universe/nifty_lists.py)

New module containing:
- `NIFTY50`: List of 50 NIFTY 50 constituent stocks
- `NIFTY100`: List of 100 NIFTY 100 constituent stocks (includes NIFTY 50 + 50 additional)
- `get_equity_universe_from_indices(indices)`: Helper function to build deduplicated, sorted universe

Example usage:
```python
from data.universe.nifty_lists import get_equity_universe_from_indices

# Get NIFTY 50 stocks
nifty50 = get_equity_universe_from_indices(["NIFTY50"])

# Get NIFTY 100 stocks
nifty100 = get_equity_universe_from_indices(["NIFTY100"])

# Get combined (will be same as NIFTY100 due to deduplication)
combined = get_equity_universe_from_indices(["NIFTY50", "NIFTY100"])
```

### 3. Scanner Updates (core/scanner.py)

Added two new helper functions:

#### `filter_low_price_equities(symbols, min_price, kite)`
Filters out low-priced stocks using batch LTP fetch to avoid hammering the broker API.

#### `build_equity_universe(cfg, kite)`
Main logic for building the equity universe based on configuration:
1. If mode is "nifty_lists", uses NIFTY indices
2. Applies max_symbols cap if configured
3. Applies min_price filter if configured
4. Falls back to existing behavior for other modes

**Updated MarketScanner:**
- `_scan_nse_equities()` now calls `build_equity_universe()` instead of `load_equity_universe()`
- Scanner's `universe.json` output now includes `equity_universe` key

### 4. Engine Updates (engine/equity_paper_engine.py)

Updated `_load_equity_universe()` to check multiple sources in order:

1. **Scanner's universe.json** (NEW) - checks `equity_universe` key
2. artifacts/equity_universe.json (existing)
3. config trading.equity_universe (existing)
4. config/universe_equity.csv via `load_equity_universe()` (existing)

**Added Logging:**
```
Equity universe loaded from scanner (mode=nifty_lists, symbols=95): ['ABB', 'ACC', ...]
```

## How to Use

### Testing Without Kite Credentials

Run the test suites to verify everything works:

```bash
# Run unit tests
python tests/test_equity_universe.py

# Run integration tests
python tests/test_equity_universe_integration.py
```

Both test suites should show all tests passing.

### Testing With Kite Credentials

1. **Login and refresh tokens:**
   ```bash
   python -m scripts.run_day --login --engines none
   ```

2. **Start the equity paper engine:**
   ```bash
   python -m scripts.run_day --mode paper --engines equity
   ```

3. **Check the logs for:**
   - "MarketScanner: scanning X enabled equity symbols"
   - "Equity universe loaded from scanner (mode=nifty_lists, symbols=X): [...]"
   
   You should see approximately 70-120 symbols (depending on min_price filter) instead of the full 126+ symbols from universe_equity.csv.

### Verifying the Universe

After the scanner runs, check the universe file:
```bash
cat artifacts/scanner/$(date +%Y-%m-%d)/universe.json | jq '.equity_universe | length'
```

This should show approximately 70-120 symbols when using NIFTY 50/100 mode.

## Configuration Examples

### Example 1: NIFTY 50 Only
```yaml
equity_universe_config:
  mode: "nifty_lists"
  include_indices: ["NIFTY50"]
  max_symbols: 50
  min_price: 100
```
Result: ~40-50 symbols (NIFTY 50 stocks above ₹100)

### Example 2: NIFTY 100 with Higher Price Filter
```yaml
equity_universe_config:
  mode: "nifty_lists"
  include_indices: ["NIFTY100"]
  max_symbols: 100
  min_price: 500
```
Result: ~60-80 symbols (NIFTY 100 stocks above ₹500)

### Example 3: Fallback to Existing Behavior
```yaml
equity_universe_config:
  mode: "all"
```
Or simply omit the `equity_universe_config` section entirely.
Result: Uses config/universe_equity.csv as before

## Impact on Other Components

### ✅ No Changes Needed
- **FnO Engine**: Continues to work with NIFTY, BANKNIFTY, FINNIFTY futures
- **Options Engine**: Continues to work with index options
- **Existing universe_equity.csv**: Still works as fallback
- **Existing strategies**: No changes needed

### ✅ Enhanced Features
- **Scanner**: Now outputs `equity_universe` key in universe.json
- **Equity Engine**: Now loads from scanner's universe.json first
- **Logging**: Better visibility into equity universe size and mode

## Troubleshooting

### Issue: Engine still shows 100+ symbols

**Solution:** Check that:
1. The scanner ran successfully and created today's universe.json
2. The config has `equity_universe_config.mode: "nifty_lists"`
3. The engine restarted after the scanner ran

### Issue: Universe is empty

**Solution:** Check that:
1. The scanner has access to Kite API
2. The min_price threshold isn't too high
3. The indices are spelled correctly in config (case-insensitive: "NIFTY50", "nifty50", etc.)

### Issue: Getting too few symbols

**Solution:**
1. Lower the `min_price` threshold
2. Remove or increase `max_symbols` cap
3. Add both NIFTY50 and NIFTY100 to `include_indices`

## Testing Checklist

- [x] Unit tests pass (tests/test_equity_universe.py)
- [x] Integration tests pass (tests/test_equity_universe_integration.py)
- [x] Security scan passes (no vulnerabilities found)
- [x] Backward compatibility verified (falls back correctly)
- [x] FnO/Options unchanged
- [ ] Manual verification with Kite credentials (requires user)
- [ ] Equity engine logs show reduced universe size
- [ ] No random penny stocks in trading universe

## Files Modified

| File | Changes | Purpose |
|------|---------|---------|
| configs/dev.yaml | +7 lines | Added equity_universe_config |
| data/universe/nifty_lists.py | +71 lines (new) | NIFTY 50/100 stock lists |
| data/universe/__init__.py | +1 line (new) | Module init |
| core/scanner.py | +109 lines | Universe building logic |
| engine/equity_paper_engine.py | +36 lines | Load from scanner |
| tests/test_equity_universe.py | +181 lines (new) | Unit tests |
| tests/test_equity_universe_integration.py | +225 lines (new) | Integration tests |
| .gitignore | +1 line | Ignore scanner artifacts |

**Total:** 643 insertions, 28 deletions across 8 files

## Support

For issues or questions:
1. Check the logs for "Equity universe loaded" messages
2. Verify config is correct
3. Run the test suites to verify functionality
4. Check that scanner ran successfully for today

## Summary

This implementation provides a clean, tested, and backward-compatible way to restrict equity trading to NIFTY 50/100 stocks while keeping all other functionality unchanged. The system will automatically filter out illiquid and penny stocks, reducing the universe from 100+ symbols to approximately 70-120 high-quality stocks.
