"""
Run LIVE equity trading using ExecutionEngine V3 path.

Usage:
    python -m scripts.run_live_equity --config configs/dev.yaml
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from core.config import load_config
from core.logging_utils import setup_logging
from engine.live_engine import LiveEquityEngine

BASE_DIR = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = BASE_DIR / "artifacts"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run LIVE equity engine (ExecutionEngine V3).")
    parser.add_argument("--config", default="configs/dev.yaml", help="Path to YAML config file.")
    parser.add_argument("--no-reconcile", action="store_true", help="Disable reconciliation loop on startup.")
    args = parser.parse_args()

    cfg = load_config(args.config)
    setup_logging(cfg.logging)
    logger = logging.getLogger("run_live_equity")

    # Force dry-run for all live runs for now
    if "execution" not in cfg.raw:
        cfg.raw["execution"] = {}
    cfg.raw["execution"]["dry_run"] = True
    logger.warning("[LIVE] Forcing execution.dry_run=True (no real orders will be sent).")

    mode = str(cfg.trading.get("mode", "paper")).lower()
    if mode != "live":
        logger.warning("Config mode is %s; forcing LIVE for this runner.", mode)
        cfg.trading["mode"] = "live"

    try:
        engine = LiveEquityEngine(cfg, artifacts_dir=ARTIFACTS_DIR)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to initialize LiveEquityEngine: %s", exc, exc_info=True)
        return 1

    # Optional: disable reconciliation if requested
    if args.no_reconcile and getattr(engine, "reconciler", None):
        engine.reconciler.enabled = False
        logger.info("Reconciliation disabled via --no-reconcile")

    logger.warning("🚨 LIVE TRADING MODE: real orders may be placed. Proceeding to run_forever().")
    engine.run_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
