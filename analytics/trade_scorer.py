from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class TradeStat:
    symbol: str
    strategy: str
    trades: int = 0
    wins: int = 0
    losses: int = 0
    realized_pnl: float = 0.0
    max_win: float = 0.0
    max_loss: float = 0.0
    avg_r: float = 0.0
    last_side: Optional[str] = None


@dataclass
class LearningSnapshot:
    per_symbol: Dict[str, TradeStat] = field(default_factory=dict)
    per_strategy: Dict[str, TradeStat] = field(default_factory=dict)


def _key(symbol: str, strategy: str) -> str:
    return f"{symbol}|{strategy}"


def load_recent_trades(orders_csv_path: Path, lookback_trades: int = 200) -> LearningSnapshot:
    """
    Parse orders.csv -> approximate per-symbol/per-strategy stats.
    Assumes rows contain pnl/r info when trade closes.
    """
    if not orders_csv_path.exists():
        return LearningSnapshot()

    rows: List[Dict[str, Any]] = []
    with orders_csv_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    rows = rows[-lookback_trades:]

    per_symbol: Dict[str, TradeStat] = {}
    per_strategy: Dict[str, TradeStat] = {}

    for row in rows:
        symbol = row.get("symbol") or row.get("tradingsymbol") or "UNKNOWN"
        strategy = row.get("strategy") or "UNKNOWN"
        side = (row.get("side") or row.get("transaction_type") or "").upper()

        pnl = float(row.get("pnl") or row.get("realized_pnl") or 0.0)
        r_multiple = float(row.get("r_multiple") or row.get("r") or 0.0)

        if symbol not in per_symbol:
            per_symbol[symbol] = TradeStat(symbol=symbol, strategy="ALL")
        if strategy not in per_strategy:
            per_strategy[strategy] = TradeStat(symbol="ALL", strategy=strategy)

        for stat in (per_symbol[symbol], per_strategy[strategy]):
            stat.trades += 1
            stat.realized_pnl += pnl
            if pnl > 0:
                stat.wins += 1
                stat.max_win = max(stat.max_win, pnl)
            elif pnl < 0:
                stat.losses += 1
                stat.max_loss = min(stat.max_loss, pnl)
            if r_multiple:
                if stat.avg_r == 0:
                    stat.avg_r = r_multiple
                else:
                    stat.avg_r = (stat.avg_r + r_multiple) / 2.0
            stat.last_side = side or stat.last_side

    return LearningSnapshot(per_symbol=per_symbol, per_strategy=per_strategy)


def compute_symbol_quality_multiplier(symbol: str, strategy: str, snapshot: LearningSnapshot) -> float:
    """
    Map historic performance -> multiplier in [0.1, 1.5].
    """
    base_mult = 1.0
    sym_stat = snapshot.per_symbol.get(symbol)
    strat_stat = snapshot.per_strategy.get(strategy)

    if sym_stat and sym_stat.trades >= 10:
        total = sym_stat.wins + sym_stat.losses
        if sym_stat.realized_pnl < 0:
            base_mult *= 0.5
        if total > 0:
            win_rate = sym_stat.wins / total
            if win_rate < 0.4:
                base_mult *= 0.5
            elif win_rate > 0.6:
                base_mult *= 1.1

    if strat_stat and strat_stat.trades >= 20:
        total = strat_stat.wins + strat_stat.losses
        if strat_stat.realized_pnl < 0:
            base_mult *= 0.7
        if total > 0:
            win_rate = strat_stat.wins / total
            if win_rate < 0.45:
                base_mult *= 0.7
            elif win_rate > 0.6:
                base_mult *= 1.1

    return max(0.1, min(1.5, base_mult))
