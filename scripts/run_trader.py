"""
Unified high-level entrypoint for PAPER and LIVE trading.

This is the **canonical user-facing command** for starting trading engines.
It provides a simple, clear interface while delegating to run_day.py for actual engine management.

Architecture:
    run_session (full day orchestration) [optional]
        → run_trader (canonical entrypoint) [you are here]
            → run_day (engine wiring) [low-level]

Usage:
    # PAPER mode (default, uses configs/dev.yaml)
    python -m scripts.run_trader paper

    # PAPER mode with explicit config
    python -m scripts.run_trader paper --config configs/dev.yaml

    # LIVE mode (requires explicit config)
    python -m scripts.run_trader live --config configs/live.yaml

    # Force Kite re-login before starting
    python -m scripts.run_trader paper --login
    python -m scripts.run_trader live --login --config configs/live.yaml

    # Override engines (default: all)
    python -m scripts.run_trader paper --engines fno
    python -m scripts.run_trader paper --engines options --login

Features:
    - Single, clear command for PAPER and LIVE modes
    - Sensible defaults (paper uses dev.yaml, reuses tokens by default)
    - Token reuse by default (--login forces refresh)
    - Backwards compatible (run_day.py still works as before)
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[1]


def _run_day_subprocess(
    mode: str,
    config: str,
    engines: str,
    login: bool,
) -> int:
    """
    Invoke run_day.py as a subprocess with the specified parameters.
    
    Args:
        mode: Trading mode ("paper" or "live")
        config: Path to config file
        engines: Engine selection ("all", "fno", "options", "equity", "none")
        login: Whether to force interactive login
    
    Returns:
        Exit code from run_day.py
    """
    cmd: List[str] = [
        sys.executable,
        "-m",
        "scripts.run_day",
        "--mode", mode,
        "--engines", engines,
        "--config", config,
    ]
    
    if login:
        cmd.append("--login")
    
    logger.info("Executing: %s", " ".join(cmd))
    
    try:
        # Use subprocess.run to stream output to terminal and get exit code
        result = subprocess.run(cmd, cwd=BASE_DIR)
        return result.returncode
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        return 130  # Standard exit code for Ctrl+C
    except Exception as exc:
        logger.error("Failed to execute run_day: %s", exc)
        return 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Unified entrypoint for PAPER and LIVE trading engines.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # PAPER mode (simple, recommended)
  python -m scripts.run_trader paper

  # PAPER mode with explicit config
  python -m scripts.run_trader paper --config configs/dev.yaml

  # LIVE mode (requires explicit config)
  python -m scripts.run_trader live --config configs/live.yaml

  # Force Kite re-login before starting
  python -m scripts.run_trader paper --login
  python -m scripts.run_trader live --login --config configs/live.yaml

  # Override engines
  python -m scripts.run_trader paper --engines fno
  python -m scripts.run_trader paper --engines options

Notes:
  - By default, reuses existing Kite tokens (fast startup)
  - Use --login to force interactive Kite login and refresh tokens
  - PAPER mode defaults to configs/dev.yaml
  - LIVE mode requires explicit --config (no default for safety)
  - For advanced usage, you can still use scripts.run_day directly
        """,
    )
    
    parser.add_argument(
        "mode",
        choices=["paper", "live"],
        help="Trading mode: 'paper' for simulation, 'live' for real trading.",
    )
    
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help=(
            "Path to YAML config file. "
            "Defaults to 'configs/dev.yaml' for PAPER mode. "
            "REQUIRED for LIVE mode (no default for safety)."
        ),
    )
    
    parser.add_argument(
        "--engines",
        choices=["all", "none", "fno", "options", "equity"],
        default="all",
        help=(
            "Which engines to run (default: all). "
            "Use 'none' with --login to refresh tokens only."
        ),
    )
    
    parser.add_argument(
        "--login",
        action="store_true",
        help=(
            "Perform interactive Kite login before starting engines. "
            "This will refresh and save tokens to secrets/kite_tokens.env. "
            "If not specified, reuses existing tokens (faster startup)."
        ),
    )
    
    args = parser.parse_args()
    
    # Configure basic logging for this script
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    
    # Determine config path
    config_path: str
    if args.config:
        config_path = args.config
    else:
        if args.mode == "paper":
            config_path = "configs/dev.yaml"
            logger.info("Using default PAPER config: %s", config_path)
        else:
            # LIVE mode requires explicit config for safety
            logger.error(
                "LIVE mode requires explicit --config flag. "
                "Example: python -m scripts.run_trader live --config configs/live.yaml"
            )
            sys.exit(1)
    
    # Warn about LIVE mode
    if args.mode == "live":
        logger.warning("=" * 70)
        logger.warning("⚠️  LIVE TRADING MODE - REAL MONEY AT RISK ⚠️")
        logger.warning("⚠️  REAL ORDERS WILL BE PLACED VIA KITE ⚠️")
        logger.warning("⚠️  Ensure all settings and risk limits are correct ⚠️")
        logger.warning("=" * 70)
        logger.warning("Config: %s", config_path)
        logger.warning("Engines: %s", args.engines)
        logger.warning("Force login: %s", args.login)
        logger.warning("=" * 70)
    
    # Provide helpful context for token behavior
    if args.login:
        logger.info("Will perform interactive Kite login (--login specified)")
    else:
        logger.info("Will reuse existing Kite tokens (no --login flag)")
        logger.info("To force token refresh, add --login flag")
    
    logger.info(
        "Starting %s mode with config=%s, engines=%s",
        args.mode.upper(),
        config_path,
        args.engines,
    )
    
    # Delegate to run_day.py
    exit_code = _run_day_subprocess(
        mode=args.mode,
        config=config_path,
        engines=args.engines,
        login=args.login,
    )
    
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
