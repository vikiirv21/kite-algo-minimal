from __future__ import annotations

from typing import Any, Dict, Optional

from risk.cost_model import CostModel, load_cost_config_from_yaml
from risk.trade_quality import TradeQualityFilter, load_quality_config_from_yaml


def build_cost_model(raw_cfg: Dict[str, Any]) -> Optional[CostModel]:
    """
    Construct a CostModel only when enabled via config.
    """
    risk_cfg = (raw_cfg or {}).get("risk", {})
    if not risk_cfg.get("enable_cost_model"):
        return None
    cost_cfg = load_cost_config_from_yaml(raw_cfg)
    return CostModel(cost_cfg)


def build_trade_quality_filter(raw_cfg: Dict[str, Any]) -> Optional[TradeQualityFilter]:
    """
    Construct a TradeQualityFilter only when enabled via config.
    """
    risk_cfg = (raw_cfg or {}).get("risk", {})
    if not risk_cfg.get("enable_trade_quality_filter"):
        return None
    quality_cfg = load_quality_config_from_yaml(raw_cfg)
    return TradeQualityFilter(quality_cfg)
