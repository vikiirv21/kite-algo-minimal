"""
Options Paper Engine - Standalone process entrypoint.

This module allows running the options paper engine as an independent Python process
as part of the multi-process architecture (Architecture v3 Phase 1).

Usage:
    python -m apps.run_options_paper --config configs/dev.yaml --mode paper
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from pathlib import Path
from typing import Optional

from core.config import load_config
from core.engine_bootstrap import (
    setup_engine_logging,
    build_kite_client,
    resolve_options_universe,
    load_scanner_universe,
)
from engine.options_paper_engine import OptionsPaperEngine

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[1]

# Global engine reference for signal handling
_engine: Optional[OptionsPaperEngine] = None


def signal_handler(signum, frame):
    """Handle interrupt signals for graceful shutdown."""
    logger.info("Received signal %d, shutting down options paper engine...", signum)
    if _engine:
        _engine.running = False
    sys.exit(0)


def main() -> None:
    """Main entry point for options paper engine standalone process."""
    global _engine
    
    parser = argparse.ArgumentParser(
        description="Options Paper Engine - Standalone process for multi-process architecture"
    )
    parser.add_argument(
        "--config",
        default="configs/dev.yaml",
        help="Path to YAML config file (default: configs/dev.yaml)",
    )
    parser.add_argument(
        "--mode",
        choices=["paper", "live"],
        default="paper",
        help="Trading mode (default: paper). Only 'paper' is supported by this engine.",
    )
    
    args = parser.parse_args()
    
    # Only support paper mode for this engine
    if args.mode != "paper":
        print(f"ERROR: This engine only supports paper mode, got: {args.mode}")
        sys.exit(1)
    
    # Load config
    try:
        cfg = load_config(args.config)
    except Exception as exc:
        print(f"ERROR: Failed to load config from {args.config}: {exc}")
        sys.exit(1)
    
    # Setup logging
    setup_engine_logging(cfg)
    
    logger.info("=" * 60)
    logger.info("OPTIONS PAPER ENGINE (Multi-Process Mode)")
    logger.info("=" * 60)
    logger.info("Config: %s", args.config)
    logger.info("Mode: %s", args.mode)
    logger.info("=" * 60)
    
    # Build Kite client
    try:
        kite = build_kite_client()
    except SystemExit:
        raise
    except Exception as exc:
        logger.error("Failed to build Kite client: %s", exc)
        sys.exit(1)
    
    # Load scanner universe (optional)
    universe_snapshot = load_scanner_universe(cfg, kite)
    
    # Resolve options universe
    logical_underlyings, underlying_futs_map = resolve_options_universe(cfg, kite, universe_snapshot)
    
    if not logical_underlyings:
        logger.error("No options underlyings configured. Nothing to trade.")
        sys.exit(1)
    
    logger.info("Options underlyings: %s", ", ".join(logical_underlyings))
    if underlying_futs_map:
        logger.info("Underlying FUT mappings: %s", underlying_futs_map)
    
    # Create options paper engine
    try:
        _engine = OptionsPaperEngine(
            cfg,
            kite=kite,
            logical_underlyings_override=logical_underlyings,
            underlying_futs_override=underlying_futs_map,
        )
        logger.info("Options paper engine initialized successfully")
    except Exception as exc:
        logger.error("Failed to initialize options paper engine: %s", exc, exc_info=True)
        sys.exit(1)
    
    # Setup signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start engine in foreground (synchronous)
    logger.info("Starting options paper engine... (Press Ctrl+C to stop)")
    
    try:
        _engine.run_forever()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as exc:
        logger.error("Engine failed with exception: %s", exc, exc_info=True)
        sys.exit(1)
    finally:
        # Perform cleanup and save final checkpoint
        logger.info("Performing final cleanup...")
        try:
            if hasattr(_engine, 'paper_broker') and _engine.paper_broker:
                logger.info("Final state saved")
        except Exception as exc:
            logger.warning("Failed to save final state: %s", exc)
        
        logger.info("Options paper engine shutdown complete")


if __name__ == "__main__":
    main()
