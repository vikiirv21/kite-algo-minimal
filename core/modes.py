"""
Trading modes and basic enums.
"""

from enum import Enum


class TradingMode(str, Enum):
    PAPER = "paper"
    LIVE = "live"
    REPLAY = "replay"
