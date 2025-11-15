from __future__ import annotations

from enum import Enum


class Profile(str, Enum):
    INTRADAY = "INTRADAY"
    SWING = "SWING"


class StrategyTag(str, Enum):
    EQ_INTRADAY = "EQ_INTRADAY"
    INDEX_OPT_EMA_TREND = "INDEX_OPT_EMA_TREND"
    INDEX_FUT_EMA_TREND = "INDEX_FUT_EMA_TREND"
    MEAN_REVERT_EQ = "MEAN_REVERT_EQ"
