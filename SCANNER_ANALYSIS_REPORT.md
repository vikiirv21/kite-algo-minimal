# Scanner Universe Analysis & Fix Report

**Date**: 2025-11-17  
**Issue**: Only 2 FnO symbols in scanner output, no equity stocks  
**Status**: ✅ RESOLVED

---

## Executive Summary

### Problem Identified
The `MarketScanner` class was only scanning NFO futures (NIFTY, BANKNIFTY) and completely ignoring NSE equity instruments, resulting in:
- Empty signals.csv and orders.csv
- No equity trading activity
- Universe JSON containing only 2 symbols instead of 100+

### Root Cause
1. Scanner was hardcoded to only fetch NFO instruments
2. No integration with `load_equity_universe()` function
3. No NSE exchange scanning
4. No penny stock filtering logic
5. Universe schema missing "equity" field

### Solution Delivered
- Extended scanner to include NSE equity scanning
- Added penny stock filter (< ₹20)
- Expanded universe from 7 to 126 liquid stocks
- Comprehensive test coverage (8 tests, all passing)

---

## Part 1: Journal File Analysis

### Findings

**`artifacts/orders.csv`:**
```csv
timestamp,symbol,side,quantity,price,status,tf,profile,strategy,parent_signal_timestamp,underlying,extra
(empty - only header)
```

**`artifacts/signals.csv`:**
```csv
timestamp,signal_id,logical,symbol,price,signal,tf,reason,profile,mode,confidence,trend_context,vol_regime,htf_trend,playbook,setup_type,ema20,ema50,ema100,ema200,rsi14,atr,adx14,adx,vwap,rel_volume,vol_spike,strategy
(empty - only header)
```

**Analysis:**
- ✅ CSV headers are correctly defined
- ❌ Zero signals generated
- ❌ Zero orders placed
- ❌ No trading activity whatsoever

**Conclusion:** Scanner universe was incomplete, preventing strategy engine from generating signals.

---

## Part 2: Scanner Analysis

### Original Code Issues

**File:** `core/scanner.py`

**Problem 1: FnO-Only Scanning**
```python
def scan(self) -> Dict[str, Any]:
    # Only fetches NFO instruments
    instruments = self.kite.instruments("NFO")
    
    # Only scans NIFTY and BANKNIFTY
    targets = ("NIFTY", "BANKNIFTY")
```

**Problem 2: Missing Equity Support**
- No call to `load_equity_universe()`
- No NSE instrument fetching
- No equity filtering logic

**Problem 3: Limited Universe Schema**
```python
payload = {
    "fno": selected,  # Only FnO
    "meta": meta,
    # Missing "equity" field
}
```

### Fixed Implementation

**Added NSE Equity Scanning:**
```python
def _scan_nse_equities(self) -> tuple[List[str], Dict[str, Dict[str, Any]]]:
    """
    Scan NSE for equity instruments from the configured universe.
    
    Applies filters:
    - Enabled in config/universe_equity.csv
    - Valid instrument metadata
    - Not a penny stock (last_price >= threshold if available)
    """
    enabled_symbols = load_equity_universe()
    instruments = self.kite.instruments("NSE")
    
    # Build lookup and validate each symbol
    # Apply penny stock filter
    # Return validated equity list
```

**Added Penny Stock Filter:**
```python
PENNY_STOCK_THRESHOLD = 20.0  # ₹

def _is_valid_equity_instrument(self, inst: Dict[str, Any], symbol: str) -> bool:
    # Check instrument_token
    # Check segment (NSE, NSE-EQ)
    # Filter price < ₹20
    # Validate metadata
```

**Enhanced Universe Schema:**
```python
payload = {
    "date": "2025-11-17",
    "fno": ["NIFTY", "BANKNIFTY"],
    "equity": ["RELIANCE", "TCS", "INFY", ...],  # NEW
    "meta": {...}
}
```

---

## Part 3: Instrument Loader Analysis

### Configuration Structure

**File:** `config/universe_equity.csv`

**Before (7 symbols):**
```csv
symbol,enabled,sector,notes
RELIANCE,1,INDEX_HEAVY,""
TCS,1,INDEX_HEAVY,""
INFY,1,INDEX_HEAVY,""
HDFCBANK,1,INDEX_HEAVY,""
ICICIBANK,1,INDEX_HEAVY,""
SBIN,1,INDEX_HEAVY,""
LT,1,INDEX_HEAVY,""
```

**After (126 symbols):**
```csv
symbol,enabled,sector,notes
RELIANCE,1,INDEX_HEAVY,"Reliance Industries"
TCS,1,INDEX_HEAVY,"Tata Consultancy Services"
INFY,1,INDEX_HEAVY,"Infosys"
...
(123 more liquid NSE stocks)
```

**Categories Added:**
- NIFTY 50 stocks: ~40 symbols
- NIFTY 100 stocks: ~60 symbols
- High-quality mid-caps: ~26 symbols
- Sectors: BANK, IT, AUTO, PHARMA, FMCG, METALS, POWER, OIL_GAS, etc.

### Loader Function

**File:** `core/universe.py`

```python
def load_equity_universe() -> List[str]:
    """
    Load enabled cash-equity symbols from config/universe_equity.csv.
    Falls back to the legacy default list if the file is missing or empty.
    """
    path = CONFIG_DIR / "universe_equity.csv"
    # Reads CSV, filters enabled=1
    # Returns list of symbols
```

**Status:** ✅ Function works correctly, now properly integrated into scanner

---

## Part 4: Penny Stock Detection

### Filter Implementation

**Threshold:** ₹20.00

**Logic:**
```python
def _is_valid_equity_instrument(self, inst: Dict[str, Any], symbol: str) -> bool:
    last_price = inst.get("last_price")
    if last_price is not None:
        price = float(last_price)
        if price > 0 and price < PENNY_STOCK_THRESHOLD:
            logger.info(
                "MarketScanner: filtered penny stock %s (price=%.2f < %.2f)",
                symbol, price, PENNY_STOCK_THRESHOLD
            )
            return False
    return True
```

**Characteristics:**
- ✅ Filters stocks < ₹20
- ✅ Allows through if price unavailable (fail-open for data issues)
- ✅ Logs filtered symbols for auditing
- ✅ Configurable threshold constant

**Test Coverage:**
```python
def test_penny_stock_filtering():
    # Test valid (₹100) → passes
    # Test penny (₹19) → filtered
    # Test no price → passes (fail-open)
```

**Result:** ✅ Penny stocks correctly filtered out

---

## Part 5: End-to-End Validation

### Test Suite Results

**File:** `tests/test_scanner_equity.py`

**8 Tests, 8 Passed ✅**

1. **test_load_equity_universe**
   - Validates CSV loading
   - Checks expected symbols present

2. **test_equity_universe_size**
   - Verifies 100-200 symbol range
   - Current: 126 symbols

3. **test_scanner_initialization**
   - Scanner object creation
   - Config/kite injection

4. **test_empty_universe_structure**
   - Schema validation
   - Required fields present

5. **test_scan_with_mock_data**
   - Full scan simulation
   - Mocked NFO + NSE responses
   - Validates FnO + equity separation

6. **test_penny_stock_filtering**
   - Tests ₹20 threshold
   - Edge cases (no price, zero price)

7. **test_invalid_instrument_filtering**
   - Token validation
   - Segment validation
   - Metadata completeness

8. **test_universe_save_and_load**
   - JSON persistence
   - Round-trip validation

### Expected Behavior After Fix

**Before:**
- Universe: 2 FnO symbols (NIFTY, BANKNIFTY)
- Equity: 0 symbols
- Signals: None
- Orders: None

**After:**
- Universe: 2 FnO + 126 equity symbols
- Equity: Full NSE liquid universe
- Signals: Generated for all valid symbols
- Orders: Placed based on signals

---

## Part 6: Recommendations & Next Steps

### Immediate Actions

1. **Deploy Scanner Update** ✅
   - Code merged to branch
   - Tests passing

2. **Verify Live Scanning**
   - Run scanner with real Kite API
   - Validate universe.json contains equity symbols
   - Check scanner logs for validation messages

3. **Test Equity Engine**
   - Verify equity engine picks up new universe
   - Monitor signal generation
   - Track order creation

### Configuration Tuning

**Penny Stock Threshold:**
- Current: ₹20
- Recommended: Consider ₹50 for better liquidity
- Configurable via constant `PENNY_STOCK_THRESHOLD`

**Volume Filters (Future Enhancement):**
```python
MIN_DAILY_VOLUME = 100_000  # shares
MIN_DELIVERABLE_PCT = 40.0  # %
```

**Circuit Limit Awareness:**
- Track stocks in upper/lower circuit
- Skip symbols with circuit breaker active

### Additional Filters to Consider

1. **Liquidity Filters:**
   - Minimum average volume (30-day)
   - Minimum deliverable percentage
   - Bid-ask spread thresholds

2. **Volatility Filters:**
   - ATR-based exclusions
   - Recent gap-up/gap-down checks

3. **Banned Lists:**
   - GSM/ASM stage stocks
   - Stocks with surveillance concerns
   - Corporate action pending

4. **FnO Universe Integration:**
   - Cross-reference with FnO list
   - Prioritize FnO stocks for better liquidity

### Monitoring Setup

**Metrics to Track:**
1. Scanner execution time
2. Equity symbols validated vs rejected
3. Penny stocks filtered count
4. Signals generated per symbol
5. Orders placed per symbol
6. Fill rates by symbol

**Alerts:**
- Scanner returns < 50 equity symbols
- Zero signals for > 1 hour
- Zero orders for > 2 hours
- Penny stock count > 10% of universe

---

## Validation Checklist

- [x] Scanner fetches NFO instruments
- [x] Scanner fetches NSE instruments
- [x] Equity universe loaded from CSV (126 symbols)
- [x] Penny stock filter active (< ₹20)
- [x] Instrument validation (token, segment)
- [x] Universe JSON schema includes "equity"
- [x] Save/load persistence works
- [x] Comprehensive test coverage (8 tests)
- [x] All tests passing
- [ ] Live Kite API validation (requires credentials)
- [ ] Equity engine signal generation (requires market hours)
- [ ] Order placement verification (requires market hours)

---

## Technical Debt Cleared

1. ✅ Scanner no longer FnO-only
2. ✅ Equity universe properly integrated
3. ✅ Penny stock protection added
4. ✅ Test coverage for scanner functionality
5. ✅ Configurable filters and thresholds
6. ✅ Enhanced logging for debugging

---

## Files Modified

1. **`core/scanner.py`** - Enhanced scanner with equity support
2. **`config/universe_equity.csv`** - Expanded to 126 symbols
3. **`tests/test_scanner_equity.py`** - New comprehensive test suite

---

## Conclusion

**Root Cause:** Scanner was hardcoded for FnO-only scanning.

**Impact:** Zero equity trading activity, no signals, no orders.

**Resolution:** Extended scanner to include NSE equity instruments with proper filtering.

**Outcome:** 
- 126 liquid NSE stocks now scanned
- Penny stock filter protecting against low-quality symbols
- Comprehensive test coverage ensuring reliability
- Ready for live trading validation

**Risk Assessment:** ✅ LOW
- Changes are additive, not breaking
- FnO scanning unchanged
- Test coverage validates behavior
- Fail-open design prevents data issues

**Next PR:** Equity engine integration testing and live validation.

---

## Appendix: Sample Universe Output

**Expected `artifacts/scanner/2025-11-17/universe.json`:**
```json
{
  "date": "2025-11-17",
  "asof": "2025-11-17T10:00:00Z",
  "fno": ["NIFTY", "BANKNIFTY"],
  "equity": [
    "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK",
    "SBIN", "LT", "BHARTIARTL", "HINDUNILVR", "ITC",
    ...
  ],
  "meta": {
    "NIFTY": {
      "tradingsymbol": "NIFTY25NOVFUT",
      "instrument_token": 9485826,
      "lot_size": 75,
      "exchange": "NFO"
    },
    "RELIANCE": {
      "tradingsymbol": "RELIANCE",
      "instrument_token": 738561,
      "lot_size": 1,
      "exchange": "NSE"
    },
    ...
  }
}
```

---

**Report End**
