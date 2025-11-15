from __future__ import annotations

from typing import Optional

from analytics.multi_timeframe_engine import MultiTimeframeEngine
from engine.meta_strategy_engine import MetaStrategyEngine
from risk.cost_model import CostModel
from risk.trade_quality import TradeQualityFilter

_multi_timeframe_engine: Optional[MultiTimeframeEngine] = None
_meta_strategy_engine: Optional[MetaStrategyEngine] = None
_cost_model: Optional[CostModel] = None
_trade_quality_filter: Optional[TradeQualityFilter] = None


def set_multi_timeframe_engine(engine: Optional[MultiTimeframeEngine]) -> None:
    global _multi_timeframe_engine
    _multi_timeframe_engine = engine


def get_multi_timeframe_engine() -> Optional[MultiTimeframeEngine]:
    return _multi_timeframe_engine


def set_meta_strategy_engine(engine: Optional[MetaStrategyEngine]) -> None:
    global _meta_strategy_engine
    _meta_strategy_engine = engine


def get_meta_strategy_engine() -> Optional[MetaStrategyEngine]:
    return _meta_strategy_engine


def set_cost_model(model: Optional[CostModel]) -> None:
    global _cost_model
    _cost_model = model


def get_cost_model() -> Optional[CostModel]:
    return _cost_model


def set_trade_quality_filter(filter_: Optional[TradeQualityFilter]) -> None:
    global _trade_quality_filter
    _trade_quality_filter = filter_


def get_trade_quality_filter() -> Optional[TradeQualityFilter]:
    return _trade_quality_filter
