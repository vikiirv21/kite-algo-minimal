from __future__ import annotations

from datetime import date
from pathlib import Path
import csv
from typing import Dict


def compute_daily_stats(journal_root: Path, day: date) -> Dict[str, float]:
    """Return lightweight performance stats for a specific trading day."""
    day_str = day.strftime("%Y-%m-%d")
    orders_path = journal_root / day_str / "orders.csv"
    if not orders_path.exists():
        return {
            "realized_pnl": 0.0,
            "max_drawdown": 0.0,
            "win_rate_20": 0.0,
            "num_trades_20": 0,
        }

    realized = 0.0
    pnl_series = []
    num_trades = 0
    wins = 0

    with orders_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            status = (row.get("status") or "").upper()
            if status not in {"FILLED", "CLOSED", "COMPLETE"}:
                continue
            try:
                pnl = float(row.get("pnl") or row.get("realized_pnl") or 0.0)
            except (TypeError, ValueError):
                pnl = 0.0
            realized += pnl
            pnl_series.append(pnl)
            num_trades += 1
            if pnl > 0:
                wins += 1

    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for pnl in pnl_series:
        equity += pnl
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)

    last_20 = pnl_series[-20:]
    trades_20 = len(last_20)
    wins_20 = sum(1 for v in last_20 if v > 0)
    win_rate_20 = (wins_20 / trades_20 * 100.0) if trades_20 else 0.0

    return {
        "realized_pnl": realized,
        "max_drawdown": max_dd,
        "win_rate_20": win_rate_20,
        "num_trades_20": trades_20,
    }
