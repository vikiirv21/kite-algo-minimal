"""
FnO Paper Engine - Standalone process entrypoint.

This module allows running the FnO paper engine as an independent Python process
as part of the multi-process architecture (Architecture v3 Phase 1).

Usage:
    python -m apps.run_fno_paper --config configs/dev.yaml --mode paper
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
    build_fno_universe,
)
from core.state_store import JournalStateStore, StateStore
from engine.paper_engine import PaperEngine

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[1]

# Global engine reference for signal handling
_engine: Optional[PaperEngine] = None


def signal_handler(signum, frame):
    """Handle interrupt signals for graceful shutdown."""
    logger.info("Received signal %d, shutting down FnO paper engine...", signum)
    if _engine:
        _engine.running = False
    sys.exit(0)


def main() -> None:
    """Main entry point for FnO paper engine standalone process."""
    global _engine
    
    parser = argparse.ArgumentParser(
        description="FnO Paper Engine - Standalone process for multi-process architecture"
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
        logger.info("FnO PAPER ENGINE (Multi-Process Mode)")
        logger.info("=" * 60)
        logger.info("Config: %s", args.config)
        logger.info("Mode: %s", args.mode)
        logger.info("=" * 60)
        
        # Build FnO universe using the same logic as scripts.run_day.py
        logger.info("Resolving FnO universe...")
        logical_universe, symbol_map = build_fno_universe(cfg)
        
        # Check if universe is empty
        if not logical_universe:
            logger.warning("=" * 60)
            logger.warning("FnoPaperEngine: no FnO universe resolved (logical=%s, symbol_map=%s); exiting with code 0.",
                         logical_universe, symbol_map)
            logger.warning("This is expected if:")
            logger.warning("  1. config.trading.fno_universe is empty")
            logger.warning("  2. Scanner data is unavailable")
            logger.warning("  3. Network/API issues prevent resolution")
            logger.warning("=" * 60)
            sys.exit(0)
        
        # Log resolved universe
        logger.info("=" * 60)
        logger.info("FnoPaperEngine: starting with logical_universe=%s", logical_universe)
        if symbol_map:
            logger.info("FnoPaperEngine: tradingsymbols=%s", list(symbol_map.values()))
            logger.info("FnoPaperEngine: symbol mappings:")
            for logical, trading in symbol_map.items():
                logger.info("  %s -> %s", logical, trading)
        else:
            logger.warning("FnoPaperEngine: symbol_map is empty, will rely on runtime resolution")
        logger.info("=" * 60)
        
        # Build Kite client (needed by PaperEngine)
        from core.engine_bootstrap import build_kite_client
        try:
            kite = build_kite_client()
        except SystemExit:
            raise
        except Exception as exc:
            logger.error("Failed to build Kite client: %s", exc)
            sys.exit(1)
        
        # Initialize state stores
        journal_store = JournalStateStore(mode="paper")
        checkpoint_store = StateStore(checkpoint_path=journal_store.checkpoint_path)
        
        # Create FnO paper engine
        try:
            _engine = PaperEngine(
                cfg,
                journal_store=journal_store,
                checkpoint_store=checkpoint_store,
                kite=kite,
                logical_universe_override=logical_universe,
                symbol_map_override=symbol_map,
            )
            logger.info("FnO paper engine initialized successfully")
        except Exception as exc:
            logger.error("Failed to initialize FnO paper engine: %s", exc, exc_info=True)
            sys.exit(1)
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Start engine in foreground (synchronous)
        logger.info("Starting FnO paper engine... (Press Ctrl+C to stop)")
        
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
                    # Save final state
                    checkpoint_store.save_checkpoint({
                        "mode": "paper",
                        "engine": "fno",
                        "last_update": time.time(),
                    })
                    logger.info("Final checkpoint saved")
            except Exception as exc:
                logger.warning("Failed to save final checkpoint: %s", exc)
            
            logger.info("FnO paper engine shutdown complete")
    
    except Exception as exc:
        # Catch any unexpected errors and log them
        logger.error("FnO paper engine crashed with unexpected error: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
