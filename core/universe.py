from __future__ import annotations

import csv
from pathlib import Path
from typing import List


BASE_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = BASE_DIR / "config"

INDEX_BASES = ["NIFTY", "BANKNIFTY", "FINNIFTY"]
_DEFAULT_EQUITIES = ["RELIANCE", "TCS", "INFY"]


def _normalize_symbol(value: str | None) -> str:
    return (value or "").strip().upper()


def load_equity_universe() -> List[str]:
    """
    Load enabled cash-equity symbols from config/universe_equity.csv.
    Falls back to the legacy default list if the file is missing or empty.
    """
    path = CONFIG_DIR / "universe_equity.csv"
    if not path.exists():
        return list(_DEFAULT_EQUITIES)

    enabled: List[str] = []
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            symbol = _normalize_symbol(row.get("symbol"))
            if not symbol:
                continue
            enabled_flag = str(row.get("enabled", "1")).strip().lower()
            if enabled_flag in {"1", "true", "yes"}:
                enabled.append(symbol)

    return enabled or list(_DEFAULT_EQUITIES)


def fno_underlyings() -> List[str]:
    """
    Return the list of index bases that we currently support for FnO trading.
    """
    return list(INDEX_BASES)
