from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

from analytics.learning_engine import compute_strategy_tuning, write_tuning_json
from core.config import load_config

logger = logging.getLogger("learning_engine")

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACTS = BASE_DIR / "artifacts"


def _resolve_artifacts_root() -> Path:
    root = os.environ.get("KITE_ALGO_ARTIFACTS")
    if not root:
        return DEFAULT_ARTIFACTS
    root_path = Path(root).expanduser()
    if not root_path.is_absolute():
        root_path = (BASE_DIR / root_path).resolve()
    return root_path


def _collect_order_paths(artifacts_root: Path, lookback_days: int) -> List[Path]:
    paths: List[Path] = []
    today = datetime.now().date()
    for offset in range(lookback_days):
        day = today - timedelta(days=offset)
        path = artifacts_root / "journal" / day.strftime("%Y-%m-%d") / "orders.csv"
        if path.exists():
            paths.append(path)
    fallback = artifacts_root / "orders.csv"
    if fallback.exists():
        paths.append(fallback)
    return paths


def _collect_trade_paths(artifacts_root: Path, lookback_days: int) -> List[Path]:
    paths: List[Path] = []
    today = datetime.now().date()
    for offset in range(lookback_days):
        day = today - timedelta(days=offset)
        path = artifacts_root / "journal" / day.strftime("%Y-%m-%d") / "trades.csv"
        if path.exists():
            paths.append(path)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute learning-engine tuning from journaled orders.")
    parser.add_argument("--config", default="configs/dev.yaml", help="Path to config file.")
    parser.add_argument("--lookback", type=int, help="Override lookback days for journal files.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    cfg = load_config(args.config)
    learning_cfg = cfg.learning_engine or {}
    lookback = args.lookback or int(learning_cfg.get("lookback_days", 5))

    artifacts_root = _resolve_artifacts_root()
    orders_paths = _collect_order_paths(artifacts_root, lookback)
    trade_paths = _collect_trade_paths(artifacts_root, lookback)
    if not orders_paths:
        logger.warning("No journal files found under %s", artifacts_root)

    tuning = compute_strategy_tuning(orders_paths, trade_paths=trade_paths, lookback_days=lookback)

    tuning_path_raw = learning_cfg.get("tuning_path", artifacts_root / "learning" / "strategy_tuning.json")
    tuning_path = Path(tuning_path_raw)
    if not tuning_path.is_absolute():
        tuning_path = (BASE_DIR / tuning_path).resolve()

    write_tuning_json(tuning, tuning_path)
    logger.info("Learning engine wrote tuning for %d keys to %s", len(tuning), tuning_path)


if __name__ == "__main__":
    main()
