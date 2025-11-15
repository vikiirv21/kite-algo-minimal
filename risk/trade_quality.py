from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from risk.cost_model import CostBreakdown
from risk.position_sizer import PortfolioState


@dataclass
class TradeProposal:
    symbol: str
    side: str  # "BUY" / "SELL"
    qty: int
    price: float
    style: str  # intraday / swing / positional
    timeframe: str
    raw_edge_bps: float


@dataclass
class TradeDecision:
    accept: bool
    reason: str


@dataclass
class QualityConfig:
    min_edge_after_costs_bps: float = 10.0
    max_trades_per_symbol_per_day: int = 5
    cooldown_after_loss_trades: int = 2


class TradeQualityFilter:
    """
    Stateless-ish filter that applies simple heuristics before an order is sent.
    """

    def __init__(self, cfg: Optional[QualityConfig] = None) -> None:
        self.cfg = cfg or QualityConfig()
        self._trade_counts: Dict[Tuple[str, str], int] = {}
        self._loss_streaks: Dict[str, int] = {}

    def _today_key(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def evaluate(self, proposal: TradeProposal, costs: CostBreakdown, state: PortfolioState) -> TradeDecision:
        _ = state  # placeholder for future hooks (risk state, heatmaps, etc.)

        if proposal.qty <= 0:
            return TradeDecision(False, "zero quantity")

        notional = max(0.0, proposal.qty * proposal.price)
        if notional <= 0:
            return TradeDecision(False, "invalid notional")

        gross_edge_amt = proposal.raw_edge_bps / 10_000.0 * notional
        net_edge_amt = gross_edge_amt - costs.total
        net_edge_bps = (net_edge_amt / notional) * 10_000.0

        if net_edge_bps < self.cfg.min_edge_after_costs_bps:
            return TradeDecision(False, "edge too small after costs")

        day_key = self._today_key()
        count_key = (proposal.symbol.upper(), day_key)
        symbol_trades = self._trade_counts.get(count_key, 0)
        if symbol_trades >= self.cfg.max_trades_per_symbol_per_day:
            return TradeDecision(False, "trade cap reached")

        loss_streak = self._loss_streaks.get(proposal.symbol.upper(), 0)
        if loss_streak >= self.cfg.cooldown_after_loss_trades and net_edge_bps < (
            self.cfg.min_edge_after_costs_bps * 1.5
        ):
            return TradeDecision(False, "cooldown after losses")

        # Accept
        self._trade_counts[count_key] = symbol_trades + 1
        reason = f"net edge {net_edge_bps:.2f} bps after costs"
        return TradeDecision(True, reason)


def load_quality_config_from_yaml(raw_cfg: Dict[str, Any]) -> QualityConfig:
    risk_cfg = (raw_cfg or {}).get("risk", {})
    quality_cfg = risk_cfg.get("quality", {}) or {}
    return QualityConfig(
        min_edge_after_costs_bps=float(quality_cfg.get("min_edge_after_costs_bps", QualityConfig.min_edge_after_costs_bps)),
        max_trades_per_symbol_per_day=int(
            quality_cfg.get("max_trades_per_symbol_per_day", QualityConfig.max_trades_per_symbol_per_day)
        ),
        cooldown_after_loss_trades=int(
            quality_cfg.get("cooldown_after_loss_trades", QualityConfig.cooldown_after_loss_trades)
        ),
    )
