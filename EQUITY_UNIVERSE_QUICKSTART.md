# Equity Universe Filtering - Quick Start

## What This Does

Restricts equity trading to **NIFTY 50 and NIFTY 100 stocks only**, eliminating random illiquid and penny stocks. FnO and options trading remain unchanged.

## Quick Test (No Kite Credentials Needed)

```bash
# Run all verification steps
python tests/verify_equity_universe_implementation.py
```

Expected output: `✅ ALL VERIFICATIONS PASSED!`

## Usage with Kite

```bash
# 1. Login
python -m scripts.run_day --login --engines none

# 2. Start equity engine
python -m scripts.run_day --mode paper --engines equity

# 3. Check logs for:
#    "Equity universe loaded from scanner (mode=nifty_lists, symbols=~100)"
```

## Configuration

File: `configs/dev.yaml`

```yaml
equity_universe_config:
  mode: "nifty_lists"              # Use NIFTY lists
  include_indices: ["NIFTY50", "NIFTY100"]
  max_symbols: 120                 # Soft cap
  min_price: 100                   # Filter penny stocks
```

## Results

- **Before:** ~126+ symbols (includes random stocks)
- **After:** ~70-120 symbols (NIFTY 50/100 only, price ≥ ₹100)

## Reverting

To revert to old behavior:

```yaml
equity_universe_config:
  mode: "all"  # or simply omit the entire section
```

## Tests

```bash
python tests/test_equity_universe.py                      # Unit tests
python tests/test_equity_universe_integration.py          # Integration tests
python tests/verify_equity_universe_implementation.py     # Final verification
```

All tests: ✅ PASS

## Documentation

See `EQUITY_UNIVERSE_IMPLEMENTATION.md` for complete guide.

## Status

✅ **COMPLETE AND PRODUCTION READY**

- All tests passing
- No security issues
- Backward compatible
- FnO/Options unchanged
- Well documented
