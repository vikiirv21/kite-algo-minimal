"""
End-of-day analyzer that proposes strategy overrides based on recent trades.

Usage:
    python -m scripts.analyze_and_learn [--date YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
import csv
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Deque, Dict, List, Optional, Tuple

import yaml

from analytics.performance import load_state
from core.market_session import now_ist

BASE_DIR = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = BASE_DIR / "artifacts"
LEARNED_OVERRIDES_PATH = BASE_DIR / "configs" / "learned_overrides.yaml"

logger = logging.getLogger("scripts.analyze_and_learn")
logging.basicConfig(level=logging.INFO, format="%(message)s")

RECENT_WINDOW = 10
MIN_TRADES_FOR_ACTION = 4
WIN_RATE_STRONG = 0.65
WIN_RATE_WEAK = 0.40
AVG_PNL_STRONG = 75.0
AVG_PNL_WEAK = -40.0
AVG_R_STRONG = 0.20
AVG_R_WEAK = -0.15


def _orders_path_for_day(day: date) -> Optional[Path]:
    journal = ARTIFACTS_DIR / "journal" / day.strftime("%Y-%m-%d") / "orders.csv"
    if journal.exists():
        return journal
    legacy = ARTIFACTS_DIR / "orders.csv"
    return legacy if legacy.exists() else None


@dataclass
class StrategyStats:
    key: str
    symbol: str = ""
    strategy: str = ""
    trades: int = 0
    wins: int = 0
    losses: int = 0
    pnl_sum: float = 0.0
    r_sum: float = 0.0
    r_count: int = 0
    recent_pnls: Deque[float] = field(default_factory=lambda: deque(maxlen=RECENT_WINDOW))

    def record(self, pnl: float, r_multiple: Optional[float]) -> None:
        self.trades += 1
        self.pnl_sum += pnl
        self.recent_pnls.append(pnl)
        if pnl > 0:
            self.wins += 1
        elif pnl < 0:
            self.losses += 1
        if r_multiple is not None:
            self.r_sum += r_multiple
            self.r_count += 1

    @property
    def win_rate(self) -> float:
        if self.trades == 0:
            return 0.0
        return self.wins / self.trades

    @property
    def recent_win_rate(self) -> float:
        if not self.recent_pnls:
            return self.win_rate
        wins = sum(1 for pnl in self.recent_pnls if pnl > 0)
        return wins / len(self.recent_pnls)

    @property
    def avg_pnl(self) -> float:
        if self.trades == 0:
            return 0.0
        return self.pnl_sum / self.trades

    @property
    def avg_r(self) -> float:
        if self.r_count == 0:
            return 0.0
        return self.r_sum / self.r_count


def _read_orders(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [row for row in reader if isinstance(row, dict)]


def _parse_float(value: Optional[str]) -> float:
    if value in (None, "", "null"):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _aggregate_stats(rows: List[Dict[str, str]]) -> Dict[str, StrategyStats]:
    stats: Dict[str, StrategyStats] = {}
    for row in rows:
        status = (row.get("status") or "").upper()
        side = (row.get("side") or row.get("transaction_type") or "").upper()
        if status not in {"FILLED", "COMPLETE", "CLOSED"}:
            continue
        if side not in {"BUY", "SELL"}:
            continue
        symbol = (row.get("symbol") or "").strip().upper()
        strategy = (row.get("strategy") or "").strip()
        logical = (row.get("logical") or "").strip()
        key = logical or f"{symbol}|{strategy}".strip("|")
        if not key:
            continue
        pnl = _parse_float(row.get("pnl") or row.get("realized_pnl"))
        r_multiple = row.get("r_multiple") or row.get("r")
        r_value: Optional[float]
        try:
            r_value = float(r_multiple) if r_multiple not in ("", None) else None
        except (TypeError, ValueError):
            r_value = None

        entry = stats.get(key)
        if entry is None:
            entry = StrategyStats(key=key, symbol=symbol, strategy=strategy or key)
            stats[key] = entry
        if not entry.symbol and symbol:
            entry.symbol = symbol
        if not entry.strategy and strategy:
            entry.strategy = strategy
        entry.record(pnl, r_value)
    return stats


def _build_overrides(stats: Dict[str, StrategyStats]) -> Tuple[Dict[str, Dict[str, float]], List[str]]:
    overrides: Dict[str, Dict[str, float]] = {}
    messages: List[str] = []
    if not stats:
        return overrides, ["No orders found for the selected day; nothing to learn."]

    for key, st in stats.items():
        if st.trades < MIN_TRADES_FOR_ACTION:
            continue
        win_rate = st.recent_win_rate
        avg_pnl = st.avg_pnl
        avg_r = st.avg_r
        entry: Dict[str, float] = {}
        reason: Optional[str] = None

        if win_rate >= WIN_RATE_STRONG and avg_pnl >= AVG_PNL_STRONG:
            bump = min(0.25, win_rate - WIN_RATE_STRONG + 0.05)
            entry["position_size_multiplier"] = round(1.0 + bump, 2)
            if avg_r >= AVG_R_STRONG:
                entry["risk_factor"] = round(min(1.5, 1.0 + bump / 2), 2)
            reason = "boosted risk (strong win rate and pnl)"
        elif win_rate <= WIN_RATE_WEAK and avg_pnl <= AVG_PNL_WEAK:
            cut = min(0.4, WIN_RATE_WEAK - win_rate + 0.05)
            entry["position_size_multiplier"] = round(max(0.5, 1.0 - cut), 2)
            entry["quality_threshold"] = round(min(0.98, 0.8 + cut), 2)
            reason = "reduced risk (weak win rate and pnl)"
        elif avg_r <= AVG_R_WEAK:
            entry["quality_threshold"] = round(min(0.98, 0.82 + abs(avg_r)), 2)
            reason = "tightened filters (negative R multiples)"

        if entry and reason:
            overrides[key] = entry
            messages.append(
                f"{key}: trades={st.trades}, win={win_rate:.0%}, avg_pnl={avg_pnl:.1f}, avg_r={avg_r:.2f} -> {reason}"
            )

    if not overrides:
        messages.append("No strategies met thresholds for overrides today.")
    return overrides, messages


def _write_overrides(overrides: Dict[str, Dict[str, float]]) -> None:
    payload = {"strategies": overrides}
    LEARNED_OVERRIDES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LEARNED_OVERRIDES_PATH.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, default_flow_style=False, sort_keys=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze trade outcomes and emit learned overrides.")
    parser.add_argument("--date", type=str, help="Target date (YYYY-MM-DD). Defaults to today's IST date.")
    args = parser.parse_args()

    target_day = now_ist().date()
    if args.date:
        try:
            target_day = datetime.fromisoformat(args.date).date()
        except ValueError as exc:
            logger.error("Invalid --date value %s: %s", args.date, exc)
            return

    orders_path = _orders_path_for_day(target_day)
    if not orders_path:
        logger.error(
            "No orders.csv found for %s. Expected under artifacts/journal/DATE/orders.csv or artifacts/orders.csv.",
            target_day.isoformat(),
        )
        return

    rows = _read_orders(orders_path)
    stats = _aggregate_stats(rows)
    overrides, messages = _build_overrides(stats)
    portfolio_meta, _ = load_state()

    print("=== Learned Overrides ===")
    print(f"Target date     : {target_day.isoformat()}")
    print(f"Orders source   : {orders_path}")
    for line in messages:
        print(f"- {line}")

    _write_overrides(overrides)
    if overrides:
        print(f"\nSaved overrides for {len(overrides)} strategies to {LEARNED_OVERRIDES_PATH}")
    else:
        print("\nNo overrides generated; cleared overrides file to avoid stale values.")

    if portfolio_meta:
        print(
            "\nPortfolio snapshot: "
            f"ts={portfolio_meta.timestamp}, realized={portfolio_meta.realized:.2f}, "
            f"unrealized={portfolio_meta.unrealized:.2f}, equity={portfolio_meta.equity:.2f}"
        )
    else:
        print("\nPortfolio snapshot unavailable (paper_state.json missing).")


if __name__ == "__main__":
    main()
