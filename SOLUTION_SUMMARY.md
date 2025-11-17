# Solution Summary: Fix PaperEngine Crash with Null strategy_engine Config

## Problem
PaperEngine crashed with `TypeError: 'NoneType' object is not iterable` when `strategy_engine` config was set to `null` in dev.yaml or learned_overrides.yaml.

## Root Cause
When YAML has `strategy_engine: null`, Python's `dict.get("strategy_engine", {})` returns `None` instead of the default `{}` because the key exists (with null value). This caused crashes when:
1. Calling `.get()` methods on None: `strategy_engine_config.get("version", 1)`
2. Iterating over None: `for strategy_code in strategy_engine_config.get("strategies_v2", [])`

## Solution
Made three minimal, surgical changes to `engine/paper_engine.py`:

### Change 1: Normalize strategy_engine_config (Lines 651-655)
```python
strategy_engine_config = self.cfg.raw.get("strategy_engine")
if strategy_engine_config is None:
    logger.warning("No strategy_engine config provided, v2 strategies will not be registered")
    strategy_engine_config = {}
self.strategy_engine_config = strategy_engine_config
```

### Change 2: Safe strategy list extraction (Lines 742-748)
```python
strategy_engine_config = self.strategy_engine_config or {}
strategies_v2 = strategy_engine_config.get("strategies_v2") or []
strategies_v1 = strategy_engine_config.get("strategies") or []

if not strategies_v2 and not strategies_v1:
    logger.warning("No strategies configured (strategies_v2 and strategies are both empty). Engine will run in idle mode.")

for strategy_code in strategies_v2:  # Now safe
    # ...
```

### Change 3: Fix TradeGuardian (Line 622)
```python
# Changed from self.checkpoint_store (doesn't exist)
# To self.state_store (correct attribute)
self.guardian = TradeGuardian(self.cfg.raw, self.state_store, logger)
```

## Testing
Created comprehensive test suite:
- `test_paper_engine_null_config.py` - Unit tests
- `manual_test_null_config.py` - Manual crash simulation
- `test_yaml_null_config.py` - YAML config loading tests
- `validate_fix.py` - Final validation of all scenarios

All tests pass ✅

## Security
CodeQL scan: 0 alerts ✅

## Impact
- Engine no longer crashes with null configs
- Logs appropriate warnings
- Starts in idle mode when no strategies configured
- No breaking changes to existing functionality

## Verified Scenarios
✅ `strategy_engine: null` in YAML  
✅ `strategies_v2: null`  
✅ `strategies: null`  
✅ Empty strategy lists  
✅ Missing strategy_engine section  
✅ Config overrides with null values  
✅ TradeGuardian initialization  
