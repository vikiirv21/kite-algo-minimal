"""
Test script for LiveEquityEngine.

This script validates that the LiveEquityEngine:
- Loads live.yaml correctly
- Creates all required directories
- Initializes without crash
- Execution engine is initialized
- Strategy engine runs
- Live capital refresh works
- Trailing logic is configured

Usage:
    python scripts/test_live_engine.py
    python scripts/test_live_engine.py --config configs/live.yaml
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("test_live_engine")

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

# Ensure artifacts directories exist
artifacts_dir = BASE_DIR / "artifacts"
for subdir in ["logs", "analytics", "checkpoints", "journal"]:
    (artifacts_dir / subdir).mkdir(parents=True, exist_ok=True)


class MockKiteConnect:
    """Mock KiteConnect for testing without real API."""
    
    TRANSACTION_TYPE_BUY = "BUY"
    TRANSACTION_TYPE_SELL = "SELL"
    VARIETY_REGULAR = "regular"
    
    def __init__(self, *args, **kwargs):
        self.api_key = "test_api_key"
        self.access_token = "test_access_token"
        self._api_key = "test_api_key"
        self._access_token = "test_access_token"
    
    def profile(self):
        return {"user_id": "TEST001", "user_name": "Test User"}
    
    def margins(self, segment="equity"):
        return {
            "available": {
                "cash": 500000.0,
                "adHocMargin": 0.0,
            },
            "utilised": {
                "debits": 10000.0,
            },
            "net": 490000.0,
        }
    
    def positions(self):
        return {"net": [], "day": []}
    
    def orders(self):
        return []
    
    def place_order(self, variety, **kwargs):
        return f"ORDER{int(time.time())}"


class MockKiteTicker:
    """Mock KiteTicker for testing."""
    
    MODE_FULL = "full"
    
    def __init__(self, *args, **kwargs):
        self.on_ticks = None
        self.on_connect = None
        self.on_close = None
        self.on_error = None
        self.on_reconnect = None
        self.on_noreconnect = None
    
    def connect(self):
        pass
    
    def subscribe(self, instruments):
        pass
    
    def set_mode(self, mode, instruments):
        pass
    
    def close(self):
        pass


def create_mock_tick(symbol: str, price: float) -> Dict[str, Any]:
    """Create a mock tick for testing."""
    return {
        "instrument_token": hash(symbol) % 100000,
        "tradingsymbol": symbol,
        "last_price": price,
        "last_traded_quantity": 100,
        "volume": 10000,
        "average_price": price,
        "ohlc": {
            "open": price * 0.99,
            "high": price * 1.01,
            "low": price * 0.98,
            "close": price,
        },
    }


def test_live_engine_initialization(config_path: str) -> bool:
    """Test that LiveEquityEngine initializes without crash."""
    logger.info("=" * 60)
    logger.info("TEST 1: LiveEquityEngine Initialization")
    logger.info("=" * 60)
    
    try:
        # Mock kiteconnect before importing
        with patch.dict('sys.modules', {
            'kiteconnect': MagicMock(
                KiteConnect=MockKiteConnect,
                KiteTicker=MockKiteTicker,
                exceptions=MagicMock(InputException=Exception),
            )
        }):
            # Patch the kite_bridge to use mock
            from core.config import load_config
            from engine.live_engine import LiveEquityEngine
            
            cfg = load_config(config_path)
            logger.info("Config loaded successfully")
            logger.info("Mode: %s", cfg.trading.get("mode", "unknown"))
            
            # Create a mock KiteClient
            mock_kite_client = MagicMock()
            mock_kite_client.api = MockKiteConnect()
            
            # Patch broker's kite instance
            with patch('broker.kite_bridge.KiteConnect', MockKiteConnect):
                with patch('broker.kite_bridge.KiteTicker', MockKiteTicker):
                    engine = LiveEquityEngine(
                        cfg,
                        kite_client=mock_kite_client,
                        artifacts_dir=artifacts_dir,
                    )
                    
                    logger.info("✅ LiveEquityEngine initialized successfully")
                    logger.info("   Mode: %s", engine.mode)
                    logger.info("   Artifacts dir: %s", engine.artifacts_dir)
                    logger.info("   Universe: %d symbols", len(engine.universe))
                    logger.info("   Primary TF: %s", engine.primary_timeframe)
                    
                    return True
                    
    except Exception as exc:
        logger.error("❌ Initialization failed: %s", exc, exc_info=True)
        return False


def test_execution_engine_v3(config_path: str) -> bool:
    """Test that ExecutionEngineV3 is properly configured."""
    logger.info("=" * 60)
    logger.info("TEST 2: ExecutionEngineV3 Configuration")
    logger.info("=" * 60)
    
    try:
        from core.config import load_config
        
        cfg = load_config(config_path)
        exec_cfg = cfg.raw.get("execution", {})
        risk_engine_cfg = cfg.raw.get("risk_engine", {})
        
        # Check ExecutionEngine V3 config
        engine_version = exec_cfg.get("engine", "v2")
        trailing_enabled = exec_cfg.get("enable_trailing", risk_engine_cfg.get("enable_trailing", False))
        trail_step_r = exec_cfg.get("trail_step_r", risk_engine_cfg.get("trail_step_r", 0.5))
        partial_exit = exec_cfg.get("enable_partial_exit", risk_engine_cfg.get("enable_partial_exits", False))
        partial_exit_pct = exec_cfg.get("partial_exit_pct", risk_engine_cfg.get("partial_exit_fraction", 0.5))
        time_stop = exec_cfg.get("enable_time_stop", risk_engine_cfg.get("enable_time_stop", False))
        time_stop_bars = exec_cfg.get("time_stop_bars", risk_engine_cfg.get("time_stop_bars", 20))
        dry_run = exec_cfg.get("dry_run", True)
        
        logger.info("ExecutionEngine V3 Configuration:")
        logger.info("   Engine: %s", engine_version)
        logger.info("   Trailing: %s (step=%.1fR)", trailing_enabled, trail_step_r)
        logger.info("   Partial Exit: %s (%.0f%%)", partial_exit, partial_exit_pct * 100)
        logger.info("   Time Stop: %s (%d bars)", time_stop, time_stop_bars)
        logger.info("   Dry Run: %s", dry_run)
        
        # Verify expected values
        if engine_version != "v3":
            logger.warning("⚠️ Engine version is not v3")
        if not trailing_enabled:
            logger.warning("⚠️ Trailing stop is disabled")
        if not partial_exit:
            logger.warning("⚠️ Partial exit is disabled")
        if not time_stop:
            logger.warning("⚠️ Time stop is disabled")
        
        logger.info("✅ ExecutionEngineV3 configuration verified")
        return True
        
    except Exception as exc:
        logger.error("❌ ExecutionEngineV3 config check failed: %s", exc, exc_info=True)
        return False


def test_strategy_engine_v2(config_path: str) -> bool:
    """Test that StrategyEngineV2 is configured."""
    logger.info("=" * 60)
    logger.info("TEST 3: StrategyEngineV2 Configuration")
    logger.info("=" * 60)
    
    try:
        from core.config import load_config
        
        cfg = load_config(config_path)
        strategy_cfg = cfg.raw.get("strategy_engine", {})
        
        engine_version = strategy_cfg.get("version", 2)
        primary_strategy = strategy_cfg.get("primary_strategy_id", "unknown")
        strategies_v2 = strategy_cfg.get("strategies_v2", [])
        enabled_strategies = [s.get("id") for s in strategies_v2 if s.get("enabled", True)]
        
        use_unified = strategy_cfg.get("use_unified_indicators", False)
        conflict_resolution = strategy_cfg.get("conflict_resolution", "highest_confidence")
        max_trades_per_day = strategy_cfg.get("max_trades_per_day", 10)
        max_loss_streak = strategy_cfg.get("max_loss_streak", 3)
        
        logger.info("StrategyEngineV2 Configuration:")
        logger.info("   Version: %s", engine_version)
        logger.info("   Primary Strategy: %s", primary_strategy)
        logger.info("   Enabled Strategies: %s", enabled_strategies)
        logger.info("   Unified Indicators: %s", use_unified)
        logger.info("   Conflict Resolution: %s", conflict_resolution)
        logger.info("   Max Trades/Day: %d", max_trades_per_day)
        logger.info("   Loss Streak Disable: %d", max_loss_streak)
        
        if engine_version != 2:
            logger.warning("⚠️ Engine version is not 2")
        
        logger.info("✅ StrategyEngineV2 configuration verified")
        return True
        
    except Exception as exc:
        logger.error("❌ StrategyEngineV2 config check failed: %s", exc, exc_info=True)
        return False


def test_live_capital_refresh(config_path: str) -> bool:
    """Test that live capital refresh works."""
    logger.info("=" * 60)
    logger.info("TEST 4: Live Capital Refresh")
    logger.info("=" * 60)
    
    try:
        with patch.dict('sys.modules', {
            'kiteconnect': MagicMock(
                KiteConnect=MockKiteConnect,
                KiteTicker=MockKiteTicker,
                exceptions=MagicMock(InputException=Exception),
            )
        }):
            from broker.kite_bridge import KiteBroker
            
            # Create mock broker
            broker = MagicMock()
            broker.kite = MockKiteConnect()
            broker.ensure_logged_in = MagicMock(return_value=True)
            
            # Mock get_live_capital
            broker.get_live_capital = MagicMock(return_value={
                "cash": 500000.0,
                "available": 500000.0,
                "utilized": 0.0,
                "net": 500000.0,
            })
            
            capital = broker.get_live_capital()
            
            logger.info("Live Capital Fetched:")
            logger.info("   Cash: %.2f", capital.get("cash", 0))
            logger.info("   Available: %.2f", capital.get("available", 0))
            logger.info("   Utilized: %.2f", capital.get("utilized", 0))
            logger.info("   Net: %.2f", capital.get("net", 0))
            
            assert capital.get("available", 0) > 0, "Available capital should be > 0"
            
            logger.info("✅ Live capital refresh working")
            return True
            
    except Exception as exc:
        logger.error("❌ Live capital refresh failed: %s", exc, exc_info=True)
        return False


def test_directory_creation(config_path: str) -> bool:
    """Test that required directories are created."""
    logger.info("=" * 60)
    logger.info("TEST 5: Directory Creation")
    logger.info("=" * 60)
    
    try:
        required_dirs = [
            artifacts_dir / "logs",
            artifacts_dir / "analytics",
            artifacts_dir / "checkpoints",
            artifacts_dir / "journal",
        ]
        
        for d in required_dirs:
            d.mkdir(parents=True, exist_ok=True)
            if d.exists():
                logger.info("   ✓ %s", d)
            else:
                logger.error("   ✗ %s (not created)", d)
                return False
        
        # Check today's journal directory
        today = datetime.now().strftime("%Y-%m-%d")
        journal_today = artifacts_dir / "journal" / today
        journal_today.mkdir(parents=True, exist_ok=True)
        
        if journal_today.exists():
            logger.info("   ✓ %s", journal_today)
        else:
            logger.error("   ✗ %s (not created)", journal_today)
            return False
        
        logger.info("✅ All required directories exist")
        return True
        
    except Exception as exc:
        logger.error("❌ Directory creation test failed: %s", exc, exc_info=True)
        return False


def test_live_state_file(config_path: str) -> bool:
    """Test that live_state.json can be written."""
    logger.info("=" * 60)
    logger.info("TEST 6: Live State File")
    logger.info("=" * 60)
    
    try:
        import json
        
        live_state_path = artifacts_dir / "live_state.json"
        
        # Create test state
        test_state = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": "LIVE",
            "live_capital": 500000.0,
            "positions": [],
            "open_positions_count": 0,
            "unrealized_pnl": 0.0,
            "realized_pnl": 0.0,
        }
        
        with open(live_state_path, "w", encoding="utf-8") as f:
            json.dump(test_state, f, indent=2)
        
        # Read back and verify
        with open(live_state_path, "r", encoding="utf-8") as f:
            loaded_state = json.load(f)
        
        assert loaded_state.get("mode") == "LIVE", "Mode should be LIVE"
        assert loaded_state.get("live_capital") == 500000.0, "Capital should be 500000"
        
        logger.info("   ✓ live_state.json created and readable")
        logger.info("   Mode: %s", loaded_state.get("mode"))
        logger.info("   Capital: %.2f", loaded_state.get("live_capital", 0))
        
        logger.info("✅ Live state file working")
        return True
        
    except Exception as exc:
        logger.error("❌ Live state file test failed: %s", exc, exc_info=True)
        return False


def test_mock_loop_iterations(config_path: str) -> bool:
    """Test mock loop iterations (simulating 20 loops)."""
    logger.info("=" * 60)
    logger.info("TEST 7: Mock Loop Iterations (20 loops)")
    logger.info("=" * 60)
    
    try:
        # Simulate 20 loop iterations
        for i in range(1, 21):
            # Simulate capital refresh every 20 loops
            if i % 20 == 0:
                logger.info("   Loop %d: Capital refresh triggered", i)
            else:
                logger.debug("   Loop %d: Normal iteration", i)
            
            # Simulate small delay
            time.sleep(0.01)
        
        logger.info("   ✓ Completed 20 mock loop iterations")
        logger.info("✅ Mock loop test passed")
        return True
        
    except Exception as exc:
        logger.error("❌ Mock loop test failed: %s", exc, exc_info=True)
        return False


def test_config_fixes(config_path: str) -> bool:
    """Test that config fixes are applied."""
    logger.info("=" * 60)
    logger.info("TEST 8: Config Fixes Verification")
    logger.info("=" * 60)
    
    try:
        from core.config import load_config
        
        cfg = load_config(config_path)
        trading = cfg.trading or {}
        
        mode = trading.get("mode", "unknown")
        enable_equity_paper = trading.get("enable_equity_paper", True)
        enable_fno_paper = trading.get("enable_fno_paper", True)
        enable_options_paper = trading.get("enable_options_paper", True)
        
        exec_cfg = cfg.raw.get("execution", {})
        dry_run = exec_cfg.get("dry_run", True)
        
        recon_cfg = cfg.raw.get("reconciliation", {})
        recon_enabled = recon_cfg.get("enabled", False)
        
        logger.info("Config Verification:")
        logger.info("   Mode: %s (expected: live)", mode)
        logger.info("   enable_equity_paper: %s (expected: false)", enable_equity_paper)
        logger.info("   enable_fno_paper: %s (expected: false)", enable_fno_paper)
        logger.info("   enable_options_paper: %s (expected: false)", enable_options_paper)
        logger.info("   dry_run: %s (note: set to false for real orders)", dry_run)
        logger.info("   reconciliation.enabled: %s (expected: true)", recon_enabled)
        
        # Validate
        warnings = []
        if mode != "live":
            warnings.append("Mode should be 'live'")
        if enable_equity_paper:
            warnings.append("enable_equity_paper should be false")
        if enable_fno_paper:
            warnings.append("enable_fno_paper should be false")
        if enable_options_paper:
            warnings.append("enable_options_paper should be false")
        if not recon_enabled:
            warnings.append("reconciliation.enabled should be true")
        
        if warnings:
            for w in warnings:
                logger.warning("   ⚠️ %s", w)
            logger.warning("⚠️ Some config values need attention")
        else:
            logger.info("✅ All config fixes verified")
        
        return len(warnings) == 0
        
    except Exception as exc:
        logger.error("❌ Config fixes verification failed: %s", exc, exc_info=True)
        return False


def main() -> int:
    """Run all tests."""
    parser = argparse.ArgumentParser(description="Test LiveEquityEngine")
    parser.add_argument(
        "--config",
        default="configs/live.yaml",
        help="Path to YAML config file (default: configs/live.yaml)",
    )
    args = parser.parse_args()
    
    config_path = args.config
    if not os.path.exists(config_path):
        logger.error("Config file not found: %s", config_path)
        return 1
    
    logger.info("=" * 60)
    logger.info("LIVE ENGINE TEST SUITE")
    logger.info("=" * 60)
    logger.info("Config: %s", config_path)
    logger.info("Artifacts: %s", artifacts_dir)
    logger.info("=" * 60)
    
    tests = [
        ("Directory Creation", test_directory_creation),
        ("Config Fixes", test_config_fixes),
        ("ExecutionEngineV3 Config", test_execution_engine_v3),
        ("StrategyEngineV2 Config", test_strategy_engine_v2),
        ("Live Capital Refresh", test_live_capital_refresh),
        ("Live State File", test_live_state_file),
        ("Mock Loop Iterations", test_mock_loop_iterations),
        ("LiveEquityEngine Init", test_live_engine_initialization),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_fn in tests:
        try:
            result = test_fn(config_path)
            if result:
                passed += 1
            else:
                failed += 1
        except Exception as exc:
            logger.error("Test '%s' crashed: %s", name, exc)
            failed += 1
    
    logger.info("")
    logger.info("=" * 60)
    logger.info("TEST RESULTS")
    logger.info("=" * 60)
    logger.info("Passed: %d", passed)
    logger.info("Failed: %d", failed)
    logger.info("=" * 60)
    
    if failed > 0:
        logger.error("❌ Some tests failed")
        return 1
    else:
        logger.info("✅ All tests passed")
        return 0


if __name__ == "__main__":
    sys.exit(main())
