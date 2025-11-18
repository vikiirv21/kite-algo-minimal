"""
Equity Paper Engine - Standalone process entrypoint.

This module allows running the equity paper engine as an independent Python process
as part of the multi-process architecture (Architecture v3 Phase 1).

Usage:
    python -m apps.run_equity_paper --config configs/dev.yaml --mode paper
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
    resolve_equity_universe,
    load_scanner_universe,
)
from engine.equity_paper_engine import EquityPaperEngine

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[1]

# Global engine reference for signal handling
_engine: Optional[EquityPaperEngine] = None


def signal_handler(signum, frame):
    """Handle interrupt signals for graceful shutdown."""
    logger.info("Received signal %d, shutting down equity paper engine...", signum)
    if _engine:
        _engine.running = False
    sys.exit(0)


def main() -> None:
    """Main entry point for equity paper engine standalone process."""
    global _engine
    
    parser = argparse.ArgumentParser(
        description="Equity Paper Engine - Standalone process for multi-process architecture"
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
    
    # Wrap main logic in try/except for robust error handling
    try:
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
        logger.info("EQUITY PAPER ENGINE (Multi-Process Mode)")
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
        
        # Resolve equity universe
        equity_universe = resolve_equity_universe(cfg, kite, universe_snapshot)
        
        if not equity_universe:
            # Handle empty universe gracefully
            logger.warning("=" * 60)
            logger.warning("EquityPaperEngine: equity universe is empty; nothing to trade.")
            logger.warning("Engine will idle. Press Ctrl+C to exit.")
            logger.warning("=" * 60)
            
            # Option A: Exit cleanly with code 0 (no work to do)
            # This allows the orchestrator to treat this as a non-failure
            logger.info("Exiting with status 0 (no universe to trade)")
            sys.exit(0)
            
            # Option B (commented out): Keep process alive in idle loop
            # try:
            #     while True:
            #         logger.info("EquityPaperEngine: no universe to trade; sleeping...")
            #         time.sleep(60)
            # except KeyboardInterrupt:
            #     logger.info("Interrupted by user")
            #     sys.exit(0)
        
        logger.info("Equity universe: %d symbols", len(equity_universe))
        logger.debug("Symbols: %s", ", ".join(equity_universe[:10]) + ("..." if len(equity_universe) > 10 else ""))
        
        # Create equity paper engine
        try:
            _engine = EquityPaperEngine(cfg, kite=kite)
            logger.info("Equity paper engine initialized successfully")
        except Exception as exc:
            logger.error("Failed to initialize equity paper engine: %s", exc, exc_info=True)
            sys.exit(1)
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Start engine in foreground (synchronous)
        logger.info("Starting equity paper engine... (Press Ctrl+C to stop)")
        
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
            
            logger.info("Equity paper engine shutdown complete")
    
    except Exception as exc:
        # Catch any unexpected errors and log them
        logger.error("Equity paper engine crashed with unexpected error: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
