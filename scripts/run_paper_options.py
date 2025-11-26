"""
Run index options paper trading engine using configs/dev.yaml (paper) or live.yaml (dry-run live reuse).

Usage:
    python -m scripts.run_paper_options --config configs/dev.yaml
"""

import argparse
import logging

from core.config import load_config
from core.logging_utils import setup_logging
from core.json_log import install_engine_json_logger
from engine.options_paper_engine import OptionsPaperEngine


logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run index options paper trading engine.")
    parser.add_argument("--config", default="configs/dev.yaml", help="Path to YAML config file.")
    parser.add_argument(
        "--mode",
        choices=["paper", "live"],
        default="paper",
        help="Run mode: paper (default) or live-dry-run for reuse in live sessions.",
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    setup_logging(cfg.logging)
    install_engine_json_logger()

    # Normalize/allow mode for live dry-run reuse
    trading = cfg.raw.get("trading", {})
    yaml_mode = str(trading.get("mode", "")).lower()
    cli_mode = args.mode.lower()
    effective_mode = cli_mode or yaml_mode or "paper"
    if "trading" not in cfg.raw:
        cfg.raw["trading"] = {}
    cfg.raw["trading"]["mode"] = effective_mode

    # Safety: force dry-run always for this runner
    if "execution" not in cfg.raw:
        cfg.raw["execution"] = {}
    cfg.raw["execution"]["dry_run"] = True
    logger.warning("[OPTIONS] Forcing execution.dry_run=True (safety guard for live reuse).")

    underlyings = (cfg.raw.get("trading", {}) or {}).get("options_underlyings", [])
    logger.info(
        "[OPTIONS] Starting options engine (mode=%s, dry_run=True) config=%s underlyings=%s",
        effective_mode,
        args.config,
        underlyings,
    )

    engine = OptionsPaperEngine(cfg)
    engine.run_forever()


if __name__ == "__main__":
    main()
