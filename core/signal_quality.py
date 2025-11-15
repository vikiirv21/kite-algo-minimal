from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any, Deque, Dict, Literal, Optional, Tuple


# Tunable knobs (TODO: load from config)
MAX_TRADES_PER_DAY = 40
MAX_TRADES_PER_SYMBOL = 10
MAX_TRADES_PER_STRATEGY = 20
COOLDOWN_MINUTES_AFTER_LOSS = 15
MIN_SCORE_TO_TRADE = 0.6
COST_MULTIPLIER = 2.0
ATR_MIN = 1.0
ATR_MAX = 120.0

STATS_WINDOW = 50
RECENT_WINDOW = 20


@dataclass
class SignalContext:
    symbol: str
    strategy: str
    timestamp: datetime
    direction: Literal["LONG", "SHORT"]
    regime: str
    atr: Optional[float]
    volatility: Optional[float]
    price: float
    risk_per_trade: float
    raw_signal_strength: float = 1.0


@dataclass
class SignalScore:
    symbol: str
    strategy: str
    timestamp: datetime
    score: float
    reason: str
    vetoed: bool
    veto_reason: Optional[str] = None


class SignalQualityManager:
    """
    Maintains rolling trade stats and applies lightweight quality heuristics.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._history: Dict[Tuple[str, str], Deque[Dict[str, float]]] = defaultdict(
            lambda: deque(maxlen=STATS_WINDOW)
        )
        self._last_loss: Dict[Tuple[str, str], datetime] = {}
        self._per_key_metrics: Dict[Tuple[str, str], Dict[str, float]] = defaultdict(
            lambda: {
                "score_sum": 0.0,
                "score_count": 0,
                "veto_count": 0,
                "trades_today": 0,
                "last_updated_date": "",
            }
        )
        self._daily_stats = self._new_daily_stats()

    # ------------------------------------------------------------------ internals
    def _today(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _new_daily_stats(self) -> Dict[str, Any]:
        return {
            "date": self._today(),
            "total_allowed": 0,
            "total_vetoed": 0,
            "score_sum": 0.0,
            "score_count": 0,
            "per_symbol": defaultdict(int),
            "per_strategy": defaultdict(int),
            "per_key": defaultdict(lambda: {"trades_today": 0, "veto_count": 0}),
        }

    def _ensure_today(self) -> None:
        today = self._today()
        if self._daily_stats["date"] != today:
            self._daily_stats = self._new_daily_stats()
        for key_metrics in self._per_key_metrics.values():
            if key_metrics["last_updated_date"] != today:
                key_metrics["trades_today"] = 0
                key_metrics["veto_count"] = 0
                key_metrics["last_updated_date"] = today

    # ------------------------------------------------------------------ scoring helpers
    def _stats_for_key(self, key: Tuple[str, str]) -> Dict[str, float]:
        history = self._history.get(key)
        if not history:
            return {
                "winrate": 0.5,
                "avg_r": 0.0,
                "avg_win_r": 1.0,
                "avg_loss_r": -1.0,
            }
        wins = [item["r"] for item in history if item["r"] > 0]
        losses = [item["r"] for item in history if item["r"] <= 0]
        total = len(history)
        winrate = len(wins) / total if total else 0.5
        avg_r = sum(item["r"] for item in history) / total if total else 0.0
        avg_win_r = sum(wins) / len(wins) if wins else 1.0
        avg_loss_r = sum(losses) / len(losses) if losses else -1.0
        return {
            "winrate": winrate,
            "avg_r": avg_r,
            "avg_win_r": avg_win_r,
            "avg_loss_r": avg_loss_r,
        }

    def _normalized_avg_r(self, avg_r: float) -> float:
        return max(0.0, min(1.0, (avg_r + 1.0) / 2.0))

    def _volatility_penalty(self, ctx: SignalContext) -> Tuple[float, str]:
        if ctx.atr is None:
            return 1.0, ""
        atr = ctx.atr
        if atr < ATR_MIN:
            return 0.8, "atr_low"
        if atr > ATR_MAX:
            return 0.82, "atr_high"
        return 1.0, ""

    def _time_penalty(self, ts: datetime) -> Tuple[float, str]:
        hour = ts.hour
        minute = ts.minute
        total_minutes = hour * 60 + minute
        open_minutes = 9 * 60 + 15
        close_minutes = 15 * 60 + 30
        if total_minutes < open_minutes + 10:
            return 0.85, "near_open"
        if total_minutes > close_minutes - 15:
            return 0.88, "near_close"
        return 1.0, ""

    def _enough_history(self, key: Tuple[str, str]) -> bool:
        history = self._history.get(key)
        return bool(history and len(history) >= 5)

    def _per_symbol_count(self, symbol: str) -> int:
        return int(self._daily_stats["per_symbol"][symbol])

    def _per_strategy_count(self, strategy: str) -> int:
        return int(self._daily_stats["per_strategy"][strategy])

    def _per_key_count(self, key: Tuple[str, str]) -> int:
        return int(self._daily_stats["per_key"][key]["trades_today"])

    def _per_key_veto(self, key: Tuple[str, str]) -> int:
        return int(self._daily_stats["per_key"][key]["veto_count"])

    # ------------------------------------------------------------------ public API
    def estimate_cost(self, symbol: str, segment: str) -> float:
        segment_upper = (segment or "").upper()
        if segment_upper in {"FNO", "F&O", "FUT", "OPT"}:
            return 40.0
        if segment_upper in {"EQ", "EQUITY"}:
            return 25.0
        if symbol.upper().endswith("FUT") or symbol.upper().endswith("CE") or symbol.upper().endswith("PE"):
            return 40.0
        return 20.0

    def score_signal(self, ctx: SignalContext) -> SignalScore:
        with self._lock:
            self._ensure_today()
            key = (ctx.strategy, ctx.symbol)
            stats = self._stats_for_key(key)
            base = stats["winrate"] * 0.6 + self._normalized_avg_r(stats["avg_r"]) * 0.4
            base = max(0.0, min(1.0, base))

            vol_penalty, vol_reason = self._volatility_penalty(ctx)
            time_penalty, time_reason = self._time_penalty(ctx.timestamp)
            base *= vol_penalty
            base *= time_penalty

            reasons = []
            if vol_reason:
                reasons.append(vol_reason)
            if time_reason:
                reasons.append(time_reason)

            veto_reason: Optional[str] = None
            now = ctx.timestamp

            if self._per_symbol_count(ctx.symbol) >= MAX_TRADES_PER_SYMBOL:
                veto_reason = "symbol_budget"
            elif self._per_strategy_count(ctx.strategy) >= MAX_TRADES_PER_STRATEGY:
                veto_reason = "strategy_budget"
            elif self._daily_stats["total_allowed"] >= MAX_TRADES_PER_DAY:
                veto_reason = "daily_budget"

            last_loss = self._last_loss.get(key)
            if veto_reason is None and last_loss:
                if (now - last_loss) < timedelta(minutes=COOLDOWN_MINUTES_AFTER_LOSS):
                    veto_reason = "cooldown_active"

            if veto_reason is None:
                expected_r = self._expected_r(stats)
                estimated_cost = self.estimate_cost(ctx.symbol, "FNO")
                expected_pnl = expected_r * max(ctx.risk_per_trade, 1.0)
                if expected_pnl < COST_MULTIPLIER * estimated_cost:
                    veto_reason = "cost_exceeds_edge"

            if veto_reason is None and base < MIN_SCORE_TO_TRADE:
                veto_reason = "score_below_threshold"

            score = max(0.0, min(1.0, base))
            reason = "good" if not reasons else "+".join(reasons)
            return SignalScore(
                symbol=ctx.symbol,
                strategy=ctx.strategy,
                timestamp=ctx.timestamp,
                score=score,
                reason=reason or "ok",
                vetoed=veto_reason is not None,
                veto_reason=veto_reason,
            )

    def _expected_r(self, stats: Dict[str, float]) -> float:
        winrate = stats["winrate"]
        avg_win = max(stats["avg_win_r"], 0.1)
        avg_loss = abs(stats["avg_loss_r"]) if stats["avg_loss_r"] else 1.0
        return winrate * avg_win - (1 - winrate) * avg_loss

    def record_veto(self, strategy: str, symbol: str) -> None:
        with self._lock:
            self._ensure_today()
            key = (strategy, symbol)
            key_metrics = self._per_key_metrics[key]
            key_metrics["last_updated_date"] = self._today()
            key_metrics["veto_count"] += 1
            self._daily_stats["total_vetoed"] += 1
            self._daily_stats["per_key"][key]["veto_count"] += 1

    def record_execution(self, strategy: str, symbol: str, score: float) -> None:
        with self._lock:
            self._ensure_today()
            key = (strategy, symbol)
            key_metrics = self._per_key_metrics[key]
            key_metrics["score_sum"] += score
            key_metrics["score_count"] += 1
            key_metrics["last_updated_date"] = self._today()
            key_metrics["trades_today"] += 1

            self._daily_stats["total_allowed"] += 1
            self._daily_stats["score_sum"] += score
            self._daily_stats["score_count"] += 1
            self._daily_stats["per_symbol"][symbol] += 1
            self._daily_stats["per_strategy"][strategy] += 1
            self._daily_stats["per_key"][key]["trades_today"] += 1

    def update_trade_outcome(self, trade: Dict[str, Any]) -> None:
        symbol = trade.get("symbol") or "UNKNOWN"
        strategy = trade.get("strategy") or "UNKNOWN"
        key = (strategy, symbol)
        try:
            r_multiple = float(trade.get("r_multiple") or 0.0)
        except (TypeError, ValueError):
            r_multiple = 0.0
        exit_ts = trade.get("exit_ts") or datetime.now(timezone.utc)
        if isinstance(exit_ts, str):
            try:
                exit_ts = datetime.fromisoformat(exit_ts)
            except ValueError:
                exit_ts = datetime.now(timezone.utc)
        with self._lock:
            history = self._history[key]
            history.append(
                {
                    "r": r_multiple,
                    "ts": exit_ts,
                }
            )
            if r_multiple < 0:
                self._last_loss[key] = exit_ts

    def strategy_metrics_snapshot(self) -> Dict[Tuple[str, str], Dict[str, float]]:
        with self._lock:
            self._ensure_today()
            snapshot: Dict[Tuple[str, str], Dict[str, float]] = {}
            for key, history in self._history.items():
                recent = list(history)[-RECENT_WINDOW:]
                if recent:
                    wins = [item["r"] for item in recent if item["r"] > 0]
                    losses = [item["r"] for item in recent if item["r"] <= 0]
                    winrate = len(wins) / len(recent) if recent else 0.0
                    avg_r = sum(item["r"] for item in recent) / len(recent)
                else:
                    winrate = 0.0
                    avg_r = 0.0
                metrics = self._per_key_metrics.get(key, {})
                avg_score = (
                    (metrics.get("score_sum", 0.0) / metrics.get("score_count", 1))
                    if metrics
                    else 0.0
                )
                snapshot[key] = {
                    "trades_today": metrics.get("trades_today", 0),
                    "winrate_20": round(winrate * 100.0, 2),
                    "avg_r_20": round(avg_r, 2),
                    "avg_signal_score": round(avg_score, 3),
                    "veto_count_today": metrics.get("veto_count", 0),
                }
            return snapshot

    def daily_summary(self) -> Dict[str, float]:
        with self._lock:
            self._ensure_today()
            score_count = self._daily_stats["score_count"] or 1
            avg_score = self._daily_stats["score_sum"] / score_count
            return {
                "date": self._daily_stats["date"],
                "total_trades_allowed": self._daily_stats["total_allowed"],
                "total_trades_vetoed": self._daily_stats["total_vetoed"],
                "avg_signal_score_executed": round(avg_score, 3),
            }


signal_quality_manager = SignalQualityManager()
