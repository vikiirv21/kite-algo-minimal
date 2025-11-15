from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, Optional


@dataclass
class RiskContext:
    """Snapshot of current performance that risk manager will use."""

    realized_pnl: float
    max_drawdown: float
    rolling_pnl_1d: float
    rolling_pnl_5d: float
    win_rate_20: float
    num_trades_20: int


@dataclass
class RiskAdjustment:
    """Recommended multipliers for various knobs."""

    risk_per_trade_scale: float = 1.0
    max_exposure_scale: float = 1.0
    lot_size_scale: float = 1.0
    mode: str = "neutral"  # "aggressive" | "defensive" | "neutral"
    reason: str = ""


class AdaptiveRiskManager:
    """Simple rule-based scaler driven by journalled performance."""

    def __init__(
        self,
        journal_root: Path,
        max_scale_up: float = 1.5,
        max_scale_down: float = 0.3,
    ) -> None:
        self.journal_root = journal_root
        self.max_scale_up = max_scale_up
        self.max_scale_down = max_scale_down

    def _load_recent_stats(self, today: date) -> RiskContext:
        from analytics.performance_utils import compute_daily_stats

        stats = compute_daily_stats(self.journal_root, today)
        realized = stats.get("realized_pnl", 0.0)
        dd = stats.get("max_drawdown", 0.0)
        win_rate_20 = stats.get("win_rate_20", 0.0)
        num_trades_20 = stats.get("num_trades_20", 0)

        return RiskContext(
            realized_pnl=realized,
            max_drawdown=dd,
            rolling_pnl_1d=realized,
            rolling_pnl_5d=realized,
            win_rate_20=win_rate_20,
            num_trades_20=num_trades_20,
        )

    def recommend(self, today: date) -> RiskAdjustment:
        ctx = self._load_recent_stats(today)
        if ctx.num_trades_20 < 10:
            return RiskAdjustment(
                mode="neutral",
                reason="Insufficient sample size for adaptive risk; keeping defaults.",
            )

        scale = 1.0
        mode = "neutral"
        reasons = []

        if ctx.max_drawdown <= -0.03 * max(1.0, ctx.rolling_pnl_5d):
            scale = 0.4
            mode = "defensive"
            reasons.append("Large recent drawdown vs capital; scaling risk down hard.")
        elif ctx.rolling_pnl_1d < 0 and ctx.win_rate_20 < 40:
            scale = 0.6
            mode = "defensive"
            reasons.append("Losing recent day and low win rate; defensive risk mode.")
        elif ctx.rolling_pnl_5d > 0 and ctx.win_rate_20 > 55:
            scale = 1.2
            mode = "aggressive"
            reasons.append("Consistent positive P&L and healthy win rate; gently scaling risk up.")
        else:
            reasons.append("No strong edge or danger; staying neutral.")

        scale = max(self.max_scale_down, min(self.max_scale_up, scale))

        return RiskAdjustment(
            risk_per_trade_scale=scale,
            max_exposure_scale=scale,
            lot_size_scale=scale,
            mode=mode,
            reason=" ".join(reasons),
        )
