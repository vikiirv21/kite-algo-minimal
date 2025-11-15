from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from core.universe import INDEX_BASES, load_equity_universe


BASE_DIR = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = BASE_DIR / "artifacts"
ORDERS_PATH = ARTIFACTS_DIR / "orders.csv"

EQ_BUCKET = set(load_equity_universe())


@dataclass
class Stats:
    num_orders: int = 0
    total_volume: float = 0.0
    total_notional: float = 0.0
    realized_pnl: float = 0.0
    round_trips: int = 0

    def apply_order(self, side: str, qty: float, price: float) -> None:
        if qty == 0:
            return
        self.num_orders += 1
        self.total_volume += abs(qty)
        self.total_notional += abs(qty * price)
        # realized_pnl and round_trips left as future enhancements


def _iter_orders() -> Iterable[Dict[str, str]]:
    if not ORDERS_PATH.exists():
        return []
    with ORDERS_PATH.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield row


def _guess_strategy(row: Dict[str, str]) -> str:
    explicit = row.get("strategy") or row.get("STRATEGY") or ""
    explicit = explicit.strip()
    if explicit:
        return explicit

    symbol = (row.get("symbol") or "").upper()
    from_index = None
    for base in INDEX_BASES:
        if symbol.startswith(base):
            from_index = base
            break

    if from_index:
        if "CE" in symbol or "PE" in symbol:
            return f"{from_index}_OPT_AUTOGEN"
        if "FUT" in symbol:
            return f"{from_index}_FUT_AUTOGEN"

    if symbol in EQ_BUCKET:
        return "EQ_INTRADAY_AUTOGEN"

    return "UNKNOWN"


def load_strategy_performance() -> Dict[Tuple[str, str], Stats]:
    stats_by_key: Dict[Tuple[str, str], Stats] = {}

    for row in _iter_orders():
        symbol = (row.get("symbol") or "").strip()
        if not symbol:
            continue

        side = (row.get("side") or row.get("transaction_type") or "").strip().upper()
        qty_str = row.get("quantity") or row.get("qty") or "0"
        price_str = row.get("price") or "0"
        try:
            qty = float(qty_str)
        except Exception:
            qty = 0.0
        try:
            price = float(price_str)
        except Exception:
            price = 0.0

        if qty == 0:
            continue

        strategy = _guess_strategy(row)
        key = (symbol, strategy)
        stats = stats_by_key.setdefault(key, Stats())
        stats.apply_order(side, qty, price)

    return stats_by_key


def aggregate_by_strategy(stats_by_key: Dict[Tuple[str, str], Stats]) -> Dict[str, Stats]:
    agg: Dict[str, Stats] = {}
    for (_symbol, strategy), st in stats_by_key.items():
        target = agg.setdefault(strategy, Stats())
        target.num_orders += st.num_orders
        target.total_volume += st.total_volume
        target.total_notional += st.total_notional
        target.realized_pnl += st.realized_pnl
        target.round_trips += st.round_trips
    return agg
