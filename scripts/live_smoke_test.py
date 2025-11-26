"""
Live Engine Dry-Run Smoke Test CLI.

Runs the LiveEquityEngine loop for a short time with dry_run=true and NO real orders.

Usage:
    python -m scripts.live_smoke_test --config configs/live.yaml --max-loops 60 --sleep-seconds 1.0

This script:
- Loads config via core.config.load_config
- FORCES execution.dry_run=True at runtime (regardless of config)
- FORCES guardian.enabled=True and risk_engine.enabled=True for safety
- Constructs LiveEquityEngine with modified config
- Runs engine.run_smoke_test(max_loops, sleep_seconds)
- NO REAL ORDERS are ever placed
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.config import load_config
from core.logging_utils import setup_logging

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = BASE_DIR / "artifacts"


def _get_session_info(cfg_raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract session timing info from config for logging.
    
    Returns dict with:
        - allow_sessions: list of session dicts
        - current_time_ist: current time string
    """
    risk_cfg = cfg_raw.get("risk", {})
    time_filter = risk_cfg.get("time_filter", {})
    allow_sessions = time_filter.get("allow_sessions", [])
    
    # Get current IST time
    try:
        from core.market_session import now_ist
        current_time = now_ist().strftime("%H:%M:%S")
    except Exception:
        current_time = datetime.now().strftime("%H:%M:%S")
    
    return {
        "allow_sessions": allow_sessions,
        "current_time_ist": current_time,
    }


def main() -> int:
    """Main entry point for the live smoke test CLI."""
    parser = argparse.ArgumentParser(
        description="Run LIVE engine dry-run smoke test (no real orders)."
    )
    parser.add_argument(
        "--config",
        default="configs/live.yaml",
        help="Path to YAML config file (default: configs/live.yaml)",
    )
    parser.add_argument(
        "--max-loops",
        type=int,
        default=60,
        help="Maximum number of loop iterations (default: 60)",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=1.0,
        help="Sleep time between loops in seconds (default: 1.0)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    
    args = parser.parse_args()
    config_path = args.config
    max_loops = args.max_loops
    sleep_seconds = args.sleep_seconds
    
    # Load config
    try:
        cfg = load_config(config_path)
    except Exception as exc:
        print(f"ERROR: Failed to load config {config_path}: {exc}")
        return 1
    
    # Setup logging
    setup_logging(cfg.logging)
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # ============================================================
    # SAFETY OVERRIDES - Force dry_run, guardian, risk_engine
    # ============================================================
    
    # Force execution.dry_run = True
    if "execution" not in cfg.raw:
        cfg.raw["execution"] = {}
    original_dry_run = cfg.raw["execution"].get("dry_run", True)
    cfg.raw["execution"]["dry_run"] = True
    logger.warning("[LIVE-SMOKE] Forcing execution.dry_run=True for safety (no real orders will be placed).")
    if not original_dry_run:
        logger.warning("[LIVE-SMOKE] Config had dry_run=False, overridden to True for smoke test.")
    
    # Force guardian.enabled = True
    if "guardian" not in cfg.raw:
        cfg.raw["guardian"] = {}
    if not cfg.raw["guardian"].get("enabled", False):
        cfg.raw["guardian"]["enabled"] = True
        logger.info("[LIVE-SMOKE] Enabling guardian in-memory override for test.")
    
    # Force risk_engine.enabled = True
    if "risk_engine" not in cfg.raw:
        cfg.raw["risk_engine"] = {}
    if not cfg.raw["risk_engine"].get("enabled", False):
        cfg.raw["risk_engine"]["enabled"] = True
        logger.info("[LIVE-SMOKE] Enabling risk_engine in-memory override for test.")
    
    # ============================================================
    # Print banner
    # ============================================================
    logger.info("=" * 60)
    logger.info("LIVE ENGINE SMOKE TEST (DRY RUN)")
    logger.info("=" * 60)
    logger.info("Config: %s", config_path)
    logger.info("Max loops: %s", max_loops)
    logger.info("Sleep per loop: %ss", sleep_seconds)
    logger.warning("!!! IMPORTANT: execution.dry_run=True => NO REAL ORDERS WILL BE SENT")
    logger.info("=" * 60)
    
    # Log session info
    session_info = _get_session_info(cfg.raw)
    logger.info("Current time (IST): %s", session_info["current_time_ist"])
    if session_info["allow_sessions"]:
        logger.info("Configured trading sessions:")
        for i, sess in enumerate(session_info["allow_sessions"], 1):
            start = sess.get("start", "??:??")
            end = sess.get("end", "??:??")
            logger.info("  Session %d: %s - %s", i, start, end)
    else:
        logger.info("No trading sessions configured (will run outside market hours)")
    logger.info("=" * 60)
    
    # ============================================================
    # Construct and run LiveEquityEngine
    # ============================================================
    try:
        from engine.live_engine import LiveEquityEngine
        
        logger.info("Initializing LiveEquityEngine...")
        engine = LiveEquityEngine(cfg, artifacts_dir=ARTIFACTS_DIR)
        
        logger.info("Starting smoke test loop...")
        engine.run_smoke_test(max_loops=max_loops, sleep_seconds=sleep_seconds)
        
        logger.info("=" * 60)
        logger.info("LIVE ENGINE SMOKE TEST COMPLETED SUCCESSFULLY")
        logger.info("=" * 60)
        return 0
        
    except Exception:
        logger.exception("Smoke test failed during LiveEquityEngine initialization")
        return 1


if __name__ == "__main__":
    sys.exit(main())
