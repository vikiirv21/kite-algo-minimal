"""
Run FnO paper trading engine using configs/dev.yaml (or another config).

Usage:
    python -m scripts.run_paper_fno --config configs/dev.yaml
"""

import argparse

from core.config import load_config
from core.logging_utils import setup_logging
from core.json_log import install_engine_json_logger
from engine.paper_engine import PaperEngine


def main() -> None:
    parser = argparse.ArgumentParser(description="Run FnO paper trading engine.")
    parser.add_argument("--config", default="configs/dev.yaml", help="Path to YAML config file.")
    args = parser.parse_args()

    cfg = load_config(args.config)
    setup_logging(cfg.logging)
    install_engine_json_logger()

    engine = PaperEngine(cfg)
    engine.run_forever()


if __name__ == "__main__":
    main()
