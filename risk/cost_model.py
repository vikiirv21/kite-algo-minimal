from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class CostBreakdown:
    brokerage: float
    exchange_tx: float
    stt: float
    gst: float
    stamp_duty: float
    other: float
    total: float


@dataclass
class CostConfig:
    brokerage_per_order: float = 20.0
    turnover_pct: float = 0.0003
    stt_pct: float = 0.00025
    gst_pct: float = 0.18
    stamp_duty_pct: float = 0.00003
    other_pct: float = 0.0


class CostModel:
    """
    Minimal cost estimator for brokerage / exchange / taxes.
    """

    def __init__(self, cfg: Optional[CostConfig] = None) -> None:
        self.cfg = cfg or CostConfig()

    def estimate(self, symbol: str, side: str, qty: int, price: float, segment: str) -> CostBreakdown:
        """
        Estimate transaction costs for a trade.

        Currently segment is unused but kept for future segment-specific tables.
        """
        _ = (symbol, side, segment)
        notional = max(0.0, float(qty) * float(price))

        brokerage = self.cfg.brokerage_per_order
        exchange_tx = self.cfg.turnover_pct * notional
        stt = self.cfg.stt_pct * notional
        gst = self.cfg.gst_pct * brokerage
        stamp_duty = self.cfg.stamp_duty_pct * notional
        other = self.cfg.other_pct * notional

        total = brokerage + exchange_tx + stt + gst + stamp_duty + other
        return CostBreakdown(
            brokerage=brokerage,
            exchange_tx=exchange_tx,
            stt=stt,
            gst=gst,
            stamp_duty=stamp_duty,
            other=other,
            total=total,
        )


def load_cost_config_from_yaml(raw_cfg: Dict[str, Any]) -> CostConfig:
    """
    Extract CostConfig from a raw AppConfig raw dict.
    """
    risk_cfg = (raw_cfg or {}).get("risk", {})
    cost_cfg = risk_cfg.get("cost", {}) or {}

    return CostConfig(
        brokerage_per_order=float(cost_cfg.get("brokerage_per_order", CostConfig.brokerage_per_order)),
        turnover_pct=float(cost_cfg.get("turnover_pct", CostConfig.turnover_pct)),
        stt_pct=float(cost_cfg.get("stt_pct", CostConfig.stt_pct)),
        gst_pct=float(cost_cfg.get("gst_pct", CostConfig.gst_pct)),
        stamp_duty_pct=float(cost_cfg.get("stamp_duty_pct", CostConfig.stamp_duty_pct)),
        other_pct=float(cost_cfg.get("other_pct", CostConfig.other_pct)),
    )
