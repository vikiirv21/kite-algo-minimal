"""
Strategy Engine v3 - Strategy Registry

Provides base class and strategy implementations for v3 engine.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from core.strategy_engine_v2 import OrderIntent


class StrategyV3Base(ABC):
    """
    Base class for Strategy Engine v3 strategies.
    
    All v3 strategies must inherit from this class and implement the generate() method.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize strategy with configuration.
        
        Args:
            config: Strategy-specific configuration dictionary
        """
        self.config = config or {}
        self.id = self.config.get("id", self.__class__.__name__)
        self.enabled = self.config.get("enabled", True)
    
    @abstractmethod
    def generate(
        self,
        symbol: str,
        ts: str,
        price: float,
        md: Dict[str, Any],
        bundle: Dict[str, Any]
    ) -> Optional[OrderIntent]:
        """
        Generate trading signal based on market data and indicators.
        
        Args:
            symbol: Trading symbol
            ts: Timestamp (ISO format)
            price: Current price
            md: Market data dictionary
            bundle: Indicator bundle computed by engine
        
        Returns:
            OrderIntent or None if no signal
        """
        pass


__all__ = ["StrategyV3Base", "OrderIntent"]
