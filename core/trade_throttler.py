from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ThrottlerConfig:
    max_trades_per_symbol_per_day: int = 20
    max_trades_per_strategy_per_day: int = 80
    max_total_trades_per_day: int = 300
    max_daily_drawdown_pct: float = 0.02
    max_loss_streak: int = 5
    min_edge_vs_cost_rupees: float = 50.0


DEFAULT_EXPECTED_EDGE_RUPEES = 100.0

_SHARED_THROTTLER_SUMMARY: Dict[str, Any] = {}


def _set_shared_throttler_summary(payload: Dict[str, Any]) -> None:
    global _SHARED_THROTTLER_SUMMARY
    _SHARED_THROTTLER_SUMMARY = payload


def latest_throttler_summary() -> Dict[str, Any]:
    """
    Return the most recent throttler summary published by any TradeThrottler instance.
    """
    return dict(_SHARED_THROTTLER_SUMMARY)

def build_throttler_config(raw: Optional[Dict[str, Any]]) -> ThrottlerConfig:
    if not isinstance(raw, dict):
        return ThrottlerConfig()
    allowed = {}
    for field_name in ThrottlerConfig.__dataclass_fields__.keys():  # type: ignore[attr-defined]
        if field_name in raw:
            allowed[field_name] = raw[field_name]
    return ThrottlerConfig(**allowed)


@dataclass
class _ThrottleState:
    symbol_counts: Dict[str, int] = field(default_factory=dict)
    strategy_counts: Dict[str, int] = field(default_factory=dict)
    total_trades: int = 0
    realized_pnl: float = 0.0
    loss_streak: int = 0
    recent_pnls: List[float] = field(default_factory=list)
    stamp: date = field(default_factory=date.today)
    veto_counts: Dict[str, int] = field(default_factory=dict)
    evaluations: int = 0
    last_veto_reason: Optional[str] = None


class TradeThrottler:
    """
    In-memory guard rail that enforces per-symbol, per-strategy, and
    global trade caps along with basic daily-loss heuristics.

    The throttler operates on "today" (date.today()) and can be reset when the
    date rolls. It keeps lightweight state so it can be warm-started later.
    """

    def __init__(
        self,
        *,
        config: Optional[ThrottlerConfig] = None,
        capital: float = 0.0,
        realized_pnl: float = 0.0,
        warm_state: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.config = config or ThrottlerConfig()
        self.capital = float(capital or 0.0)
        self._state = _ThrottleState()
        self._state.realized_pnl = float(realized_pnl or 0.0)
        if warm_state:
            self._load_warm_state(warm_state)
        logger.info("TradeThrottler initialized: %s", asdict(self.config))
        self._publish_summary()

    # ------------------------------------------------------------------ utils
    def _load_warm_state(self, payload: Dict[str, Any]) -> None:
        try:
            symbol_counts = dict(payload.get("symbol_counts") or {})
            strategy_counts = dict(payload.get("strategy_counts") or {})
            total_trades = int(payload.get("total_trades", 0))
            realized = float(payload.get("realized_pnl", 0.0))
            loss_streak = int(payload.get("loss_streak", 0))
            recent = list(payload.get("recent_pnls") or [])
            evaluations = int(payload.get("evaluations", payload.get("total_signals", 0)))
            veto_counts = dict(payload.get("veto_counts") or {})
            last_veto = payload.get("last_veto_reason")
            stamp = payload.get("stamp")
            stamp_date = stamp if isinstance(stamp, date) else None
            if stamp_date is None:
                raw = str(stamp) if stamp else ""
                try:
                    stamp_date = date.fromisoformat(raw)
                except Exception:
                    stamp_date = date.today()
        except Exception:  # noqa: BLE001
            return

        self._state.symbol_counts = {str(k).upper(): int(v) for k, v in symbol_counts.items()}
        self._state.strategy_counts = {str(k): int(v) for k, v in strategy_counts.items()}
        self._state.total_trades = max(0, total_trades)
        self._state.realized_pnl = realized
        self._state.loss_streak = max(0, loss_streak)
        self._state.recent_pnls = recent[-50:]
        self._state.stamp = stamp_date or date.today()
        self._state.evaluations = max(0, evaluations)
        self._state.veto_counts = {str(k).upper(): int(v) for k, v in veto_counts.items()}
        self._state.last_veto_reason = str(last_veto) if last_veto else None

    def snapshot(self) -> Dict[str, Any]:
        return {
            "symbol_counts": dict(self._state.symbol_counts),
            "strategy_counts": dict(self._state.strategy_counts),
            "total_trades": self._state.total_trades,
            "realized_pnl": self._state.realized_pnl,
            "loss_streak": self._state.loss_streak,
            "recent_pnls": list(self._state.recent_pnls),
            "stamp": self._state.stamp.isoformat(),
            "evaluations": self._state.evaluations,
            "veto_counts": dict(self._state.veto_counts),
            "last_veto_reason": self._state.last_veto_reason,
        }

    def reset_for_new_day(
        self,
        *,
        today: Optional[date] = None,
        new_capital: Optional[float] = None,
        realized_pnl: float = 0.0,
    ) -> None:
        target_day = today or date.today()
        self._state = _ThrottleState()
        self._state.realized_pnl = float(realized_pnl)
        self._state.stamp = target_day
        if new_capital is not None:
            self.capital = float(new_capital)
        logger.info("TradeThrottler reset for %s", self._state.stamp.isoformat())
        self._publish_summary()

    def _ensure_today(self, today: Optional[date] = None) -> None:
        target_day = today or self._state.stamp or date.today()
        if self._state.stamp != target_day:
            self.reset_for_new_day(today=target_day, new_capital=self.capital, realized_pnl=0.0)

    def update_context(
        self,
        *,
        today: Optional[date] = None,
        realized_pnl: Optional[float] = None,
        capital: Optional[float] = None,
    ) -> None:
        """
        Synchronize throttler context with portfolio metrics (day + realized PnL).
        """
        target_day = today or self._state.stamp or date.today()
        if self._state.stamp != target_day:
            self.reset_for_new_day(
                today=target_day,
                new_capital=capital if capital is not None else self.capital,
                realized_pnl=float(realized_pnl) if realized_pnl is not None else 0.0,
            )
            return
        if capital is not None:
            self.capital = float(capital)
        if realized_pnl is not None:
            self._state.realized_pnl = float(realized_pnl)
        self._publish_summary()

    def _record_veto(self, reason: str) -> None:
        code = (reason or "UNKNOWN").upper()
        self._state.veto_counts[code] = self._state.veto_counts.get(code, 0) + 1
        self._state.last_veto_reason = code
        self._publish_summary()

    def _deny(self, reason: str) -> Tuple[bool, str]:
        self._record_veto(reason)
        return False, reason

    def _publish_summary(self) -> None:
        try:
            _set_shared_throttler_summary(self.quality_summary())
        except Exception:  # noqa: BLE001
            logger.debug("Failed to publish throttler summary", exc_info=True)

    # ----------------------------------------------------------------- public
    def register_fill(
        self,
        symbol: str,
        strategy: str,
        side: str,
        qty: int,
        price: float,
        realized_pnl: Optional[float],
        *,
        count_towards_limits: bool = True,
        trade_day: Optional[date] = None,
    ) -> None:
        """
        Record an executed order so throttling heuristics stay in sync.
        """
        self._ensure_today(trade_day)
        if count_towards_limits:
            key_symbol = (symbol or "").upper()
            key_strategy = strategy or "UNKNOWN"
            if key_symbol:
                self._state.symbol_counts[key_symbol] = self._state.symbol_counts.get(key_symbol, 0) + 1
            if key_strategy:
                self._state.strategy_counts[key_strategy] = self._state.strategy_counts.get(key_strategy, 0) + 1
            self._state.total_trades += 1

        pnl_value = float(realized_pnl or 0.0)
        self._state.realized_pnl += pnl_value
        if abs(pnl_value) > 1e-6:
            if pnl_value < 0:
                self._state.loss_streak += 1
            else:
                self._state.loss_streak = 0
            self._state.recent_pnls.append(pnl_value)
            if len(self._state.recent_pnls) > 50:
                self._state.recent_pnls = self._state.recent_pnls[-50:]
        self._publish_summary()

    def should_allow_entry(
        self,
        symbol: str,
        strategy: str,
        notional: float,
        expected_edge_rupees: float,
        *,
        trade_day: Optional[date] = None,
    ) -> Tuple[bool, str]:
        """
        Return (allowed, reason_code) for proposed entry order.
        """
        self._ensure_today(trade_day)
        self._state.evaluations += 1
        min_edge = float(self.config.min_edge_vs_cost_rupees or 0.0)
        if expected_edge_rupees < min_edge:
            return self._deny("EDGE_BELOW_COST")

        if self.config.max_total_trades_per_day > 0 and self._state.total_trades >= self.config.max_total_trades_per_day:
            return self._deny("CAP_TOTAL")

        symbol_key = (symbol or "").upper()
        if (
            self.config.max_trades_per_symbol_per_day > 0
            and symbol_key
            and self._state.symbol_counts.get(symbol_key, 0) >= self.config.max_trades_per_symbol_per_day
        ):
            return self._deny("CAP_SYMBOL")

        strat_key = strategy or "UNKNOWN"
        if (
            self.config.max_trades_per_strategy_per_day > 0
            and strat_key
            and self._state.strategy_counts.get(strat_key, 0) >= self.config.max_trades_per_strategy_per_day
        ):
            return self._deny("CAP_STRATEGY")

        loss_limit = 0.0
        if self.capital > 0 and self.config.max_daily_drawdown_pct > 0:
            loss_limit = self.capital * self.config.max_daily_drawdown_pct
        if loss_limit > 0 and -self._state.realized_pnl >= loss_limit:
            return self._deny("DAILY_DRAWDOWN")

        if self.config.max_loss_streak > 0 and self._state.loss_streak >= self.config.max_loss_streak:
            return self._deny("LOSS_STREAK")

        _ = notional  # notional reserved for future heuristics
        self._state.last_veto_reason = None
        self._publish_summary()
        return True, "OK"

    def quality_summary(self) -> Dict[str, Any]:
        """
        Lightweight snapshot suited for dashboards/monitoring.
        """
        max_drawdown = 0.0
        if self.capital > 0 and self.config.max_daily_drawdown_pct > 0:
            max_drawdown = self.capital * self.config.max_daily_drawdown_pct
        drawdown_hit = bool(max_drawdown > 0 and -self._state.realized_pnl >= max_drawdown)
        veto_breakdown = dict(
            sorted(self._state.veto_counts.items(), key=lambda item: item[1], reverse=True)
        )
        return {
            "date": self._state.stamp.isoformat(),
            "total_signals": self._state.evaluations,
            "total_trades_taken": self._state.total_trades,
            "total_vetoed": sum(veto_breakdown.values()),
            "veto_breakdown": veto_breakdown,
            "trade_caps": {
                "max_trades_per_symbol_per_day": self.config.max_trades_per_symbol_per_day,
                "max_trades_per_strategy_per_day": self.config.max_trades_per_strategy_per_day,
                "max_total_trades_per_day": self.config.max_total_trades_per_day,
                "max_daily_drawdown_pct": self.config.max_daily_drawdown_pct,
                "max_loss_streak": self.config.max_loss_streak,
                "min_edge_vs_cost_rupees": self.config.min_edge_vs_cost_rupees,
            },
            "loss_streak": self._state.loss_streak,
            "realized_pnl": round(self._state.realized_pnl, 2),
            "drawdown_hit": drawdown_hit,
            "last_veto_reason": self._state.last_veto_reason,
        }
