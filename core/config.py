"""
Config loading utilities.

- Loads YAML config (e.g., configs/dev.yaml).
- Provides a simple dict-like object for other modules.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import yaml

import logging

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[1]
LEARNED_OVERRIDES_PATH = BASE_DIR / "configs" / "learned_overrides.yaml"


@dataclass
class AppConfig:
    raw: Dict[str, Any]

    @property
    def trading(self) -> Dict[str, Any]:
        return self.raw.get("trading", {})

    @property
    def data(self) -> Dict[str, Any]:
        return self.raw.get("data", {})

    @property
    def logging(self) -> Dict[str, Any]:
        return self.raw.get("logging", {})

    @property
    def risk(self) -> Dict[str, Any]:
        return self.raw.get("risk", {})

    @property
    def meta(self) -> Dict[str, Any]:
        return self.raw.get("meta", {})

    @property
    def risk_engine(self) -> Dict[str, Any]:
        return self.raw.get("risk_engine", {})

    @property
    def learning_engine(self) -> Dict[str, Any]:
        return self.raw.get("learning_engine", {})


def load_config(path: str) -> AppConfig:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    _apply_learned_overrides(raw)
    return AppConfig(raw=raw)


def _apply_learned_overrides(raw: Dict[str, Any]) -> None:
    path = LEARNED_OVERRIDES_PATH
    if not path.exists():
        return
    try:
        overrides = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to read learned overrides at %s: %s", path, exc)
        return
    if not isinstance(overrides, dict) or not overrides:
        return
    _recursive_merge(raw, overrides)
    logger.info(
        "Applied learned overrides from %s (keys=%s)",
        path,
        ", ".join(overrides.keys()),
    )


def _recursive_merge(target: Dict[str, Any], overrides: Dict[str, Any]) -> None:
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _recursive_merge(target[key], value)
        else:
            target[key] = value
