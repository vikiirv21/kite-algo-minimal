# Pull Request: Implement StrategyEngine v3 Orchestrator

## 📋 Overview

Implemented StrategyEngine v3 — a context-aware orchestration layer for strategy enable/disable, capital allocation, regime filtering, cooldowns, and strategy health scoring. All new logic is **DISABLED by default** to ensure Monday paper trading is not affected.

## 🎯 Implementation Summary

### New Files Created (4 files)

1. **`core/strategy_orchestrator.py`** (332 lines)
   - `StrategyState`: Per-strategy state tracking
   - `OrchestratorDecision`: Gate decision result
   - `StrategyOrchestrator`: Main orchestration engine

2. **`tests/test_strategy_orchestrator.py`** (377 lines)
   - 13 unit tests covering all orchestrator features
   - All tests passing

3. **`tests/test_integration_orchestrator.py`** (278 lines)
   - 4 integration tests
   - Verifies orchestrator integration with StrategyEngineV2
   - Tests backward compatibility

4. **`tests/verify_orchestrator_v3.py`** (282 lines)
   - 6 manual verification tests
   - Demonstrates all features

5. **`STRATEGY_ENGINE_V3_SUMMARY.md`** (243 lines)
   - Comprehensive documentation
   - Usage examples
   - Architecture details

### Modified Files (4 files)

1. **`core/strategy_engine_v2.py`** (+80 lines)
   - Added orchestrator integration
   - Added `_get_market_regime()` method
   - Modified `run_strategy()` to check orchestrator
   - Modified `run()` to pass regime
   - Maintained backward compatibility

2. **`core/config.py`** (+4 lines)
   - Added `strategy_orchestrator` property

3. **`configs/dev.yaml`** (+25 lines)
   - Added `strategy_orchestrator` section (disabled by default)
   - Added example strategy metadata

4. **`engine/paper_engine.py`** (+10 lines, -5 lines)
   - Pass `state_store` and `analytics` to StrategyEngineV2
   - Pass full config for orchestrator access

## ✨ Features Implemented

### 1. Loss Streak Cooldown
- Automatically disables strategy after N consecutive losses
- Configurable cooldown duration (default: 15 minutes)
- Auto re-enables after cooldown expires

### 2. Health Score Tracking
- Win rate based scoring (0.0 to 1.0)
- Configurable scoring window (default: 20 trades)
- Optional minimum threshold enforcement

### 3. Regime Compatibility Filtering
- `requires_regime`: List of required market regimes
- `avoid_regime`: List of regimes to avoid
- Flexible regime definition

### 4. Session Time Windows
- HH:MM format time ranges
- Automatic day boundary handling
- Per-strategy configuration

### 5. Day Filtering
- Weekday-based strategy execution
- Case-insensitive matching
- Strategy scheduling support

### 6. Stub Regime Detection
- Attempts to use `shared_regime_detector` if available
- Falls back to stub if not available
- No crashes on missing dependencies

## 🧪 Testing

### Test Coverage
- **13 unit tests** (`test_strategy_orchestrator.py`) - All passing ✅
- **4 integration tests** (`test_integration_orchestrator.py`) - All passing ✅
- **6 manual verification tests** (`verify_orchestrator_v3.py`) - All passing ✅
- **7 existing tests** (`test_strategy_engine_v2.py`) - All passing ✅

### Total: 30 tests, 0 failures

## 🔒 Safety & Backward Compatibility

### ✅ Safety Measures

1. **Disabled by default**: `enabled: false` in config
2. **Optional initialization**: Works without `state_store`
3. **Graceful degradation**: Missing config handled safely
4. **No breaking changes**: All existing functionality preserved
5. **No new dependencies**: Uses only existing libraries

### ✅ Backward Compatibility Verified

- Engine works without orchestrator (state_store optional)
- Orchestrator is disabled by default
- All existing tests pass
- No changes to core systems:
  - Token management
  - `run_day` logic
  - PortfolioEngine
  - TradeGuardian
  - UI components
  - Database operations

### ✅ Security

- CodeQL analysis: 0 vulnerabilities found
- No user input validation issues
- No SQL injection risks
- No XSS vulnerabilities
- Safe defaults throughout

## 📊 Configuration

### Default Configuration (Safe for Monday)

```yaml
strategy_orchestrator:
  enabled: false                      # DISABLED by default
  health_scoring_window: 20           
  loss_streak_disable: 3              
  disable_duration_seconds: 900       
  enforce_regimes: true               
  enforce_capital_budgets: true       
  min_health_score: 0.0
```

### Strategy Metadata (Optional)

```yaml
strategies:
  ema20_50_intraday:
    mode: intraday
    capital_pct: 0.3
    requires_regime: ["trend"]
    avoid_regime: ["low_vol"]
    session_times:
      start: "09:25"
      end: "14:55"
    allowed_days: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
```

## 🚀 Usage

### Enable Orchestrator

```yaml
strategy_orchestrator:
  enabled: true
```

### Check Before Execution (Automatic)

The orchestrator automatically gates strategy execution in `StrategyEngineV2.run_strategy()`:

```python
# Orchestrator check (automatic)
if self.orchestrator:
    decision = self.orchestrator.should_run_strategy(strategy_code, market_regime)
    if not decision.allow:
        logger.info("[strategy-skip] %s: %s", strategy_code, decision.reason)
        return []
```

### Update After Trade

```python
# After trade completes
orchestrator.update_after_trade(strategy_code, trade_pnl)
```

## 📈 Statistics

- **Total lines added**: 1,626
- **New files**: 5
- **Modified files**: 4
- **Test coverage**: 30 tests
- **Code quality**: 0 security issues
- **Documentation**: Comprehensive

## ✅ Checklist

- [x] Core orchestrator module implemented
- [x] Integration with StrategyEngine v2
- [x] Configuration schema added
- [x] Regime detection integration
- [x] Comprehensive testing (30 tests)
- [x] Backward compatibility verified
- [x] Security scan passed (0 issues)
- [x] Documentation created
- [x] No breaking changes
- [x] Monday paper trading safe

## 🎯 Next Steps (Future Work)

1. **Capital Budget Enforcement**: Full integration with PortfolioEngine
2. **Advanced Regime Detection**: Real-time regime indicators
3. **Strategy Analytics**: Deeper analytics integration
4. **UI Dashboard**: Visualize strategy health
5. **Dynamic Thresholds**: Auto-adjust based on conditions
6. **Strategy Groups**: Coordinate multiple strategies

## 📝 Notes

- All orchestrator logic is **disabled by default**
- No impact on Monday paper trading setup
- Clean separation of concerns maintained
- Ready for gradual rollout when enabled
- Can be enabled per-strategy or globally

## 🔗 Related Documentation

- `STRATEGY_ENGINE_V3_SUMMARY.md` - Detailed implementation guide
- `core/strategy_orchestrator.py` - Source code with inline docs
- `tests/verify_orchestrator_v3.py` - Usage examples

---

**Branch**: `feat/strategy-engine-v3` (as specified in requirements)  
**Status**: Ready for review and merge  
**Risk Level**: Low (disabled by default, comprehensive testing)  
**Deployment**: Safe for immediate deployment
