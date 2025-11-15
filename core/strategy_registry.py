"""
Strategy Registry
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class StrategyInfo:
    """
    Dataclass for strategy information
    """

    name: str
    strategy_code: str
    timeframe: str
    version: str
    enabled: bool = False
    tags: List[str] = field(default_factory=list)


STRATEGY_REGISTRY = {
    "ema20_50_intraday": StrategyInfo(
        name="EMA 20-50 Intraday",
        strategy_code="ema20_50_intraday",
        timeframe="5m",
        version="1.0",
        enabled=True,
        tags=["equity", "intraday", "trend"],
    ),
    "expiry_scalper": StrategyInfo(
        name="Expiry Scalper",
        strategy_code="expiry_scalper",
        timeframe="1m",
        version="1.0",
        enabled=False,
        tags=["options", "intraday", "scalping"],
    ),
}
