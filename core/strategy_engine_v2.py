"""
Strategy Engine v2

Modern strategy execution framework with unified indicator calculations.
Provides clean separation between strategy logic, market data, and execution.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from core import indicators
from core.market_data_engine import MarketDataEngine
from core.risk_engine import RiskAction, RiskConfig, RiskDecision, TradeContext
from strategies.base import Decision

logger = logging.getLogger(__name__)


class OrderIntent:
    """Represents a trading intent from a strategy before risk checks."""
    
    def __init__(
        self,
        symbol: str,
        action: str,  # "BUY", "SELL", "EXIT"
        qty: Optional[int] = None,
        reason: str = "",
        strategy_code: str = "",
        confidence: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.symbol = symbol
        self.action = action.upper()
        self.qty = qty
        self.reason = reason
        self.strategy_code = strategy_code
        self.confidence = confidence
        self.metadata = metadata or {}
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "action": self.action,
            "qty": self.qty,
            "reason": self.reason,
            "strategy_code": self.strategy_code,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }


class StrategyState:
    """Maintains state for a strategy instance."""
    
    def __init__(self):
        self.positions: Dict[str, Dict[str, Any]] = {}  # symbol -> position info
        self.signals: List[Dict[str, Any]] = []
        self.metadata: Dict[str, Any] = {}
    
    def is_position_open(self, symbol: str) -> bool:
        """Check if position is open for symbol."""
        return symbol in self.positions and self.positions[symbol].get("qty", 0) != 0
    
    def is_long(self, symbol: str) -> bool:
        """Check if we have a long position."""
        return symbol in self.positions and self.positions[symbol].get("qty", 0) > 0
    
    def is_short(self, symbol: str) -> bool:
        """Check if we have a short position."""
        return symbol in self.positions and self.positions[symbol].get("qty", 0) < 0
    
    def update_position(self, symbol: str, qty: int, entry_price: float = 0.0):
        """Update position tracking."""
        if qty == 0:
            self.positions.pop(symbol, None)
        else:
            self.positions[symbol] = {
                "qty": qty,
                "entry_price": entry_price,
                "entry_time": datetime.utcnow().isoformat()
            }


class BaseStrategy(ABC):
    """
    Base class for Strategy Engine v2 strategies.
    
    Strategies should not fetch market data directly.
    All data is provided via generate_signal() parameters.
    """
    
    def __init__(self, config: Dict[str, Any], strategy_state: StrategyState):
        self.config = config
        self.state = strategy_state
        self.name = config.get("name", "UnknownStrategy")
        self.timeframe = config.get("timeframe", "5m")
        self._pending_intents: List[OrderIntent] = []
    
    @abstractmethod
    def generate_signal(
        self, 
        candle: Dict[str, float], 
        series: Dict[str, List[float]], 
        indicators: Dict[str, Any]
    ) -> Optional[Decision]:
        """
        Generate trading signal based on current candle, historical series, and indicators.
        
        Args:
            candle: Current candle dict with keys: open, high, low, close, volume
            series: Historical series dict with keys: open, high, low, close, volume (lists)
            indicators: Pre-computed indicators dict (EMA, RSI, ATR, etc.)
        
        Returns:
            Decision object or None
        """
        pass
    
    def long(self, symbol: str, qty: Optional[int] = None, reason: str = "") -> OrderIntent:
        """Create a long (BUY) order intent."""
        intent = OrderIntent(
            symbol=symbol,
            action="BUY",
            qty=qty,
            reason=reason,
            strategy_code=self.name,
            confidence=0.0
        )
        self._pending_intents.append(intent)
        return intent
    
    def short(self, symbol: str, qty: Optional[int] = None, reason: str = "") -> OrderIntent:
        """Create a short (SELL) order intent."""
        intent = OrderIntent(
            symbol=symbol,
            action="SELL",
            qty=qty,
            reason=reason,
            strategy_code=self.name,
            confidence=0.0
        )
        self._pending_intents.append(intent)
        return intent
    
    def exit(self, symbol: Optional[str] = None, reason: str = "") -> OrderIntent:
        """Create an exit order intent."""
        # If no symbol specified, exit all positions
        if symbol is None:
            for sym in list(self.state.positions.keys()):
                intent = OrderIntent(
                    symbol=sym,
                    action="EXIT",
                    qty=None,
                    reason=reason,
                    strategy_code=self.name,
                    confidence=0.0
                )
                self._pending_intents.append(intent)
            return None
        
        intent = OrderIntent(
            symbol=symbol,
            action="EXIT",
            qty=None,
            reason=reason,
            strategy_code=self.name,
            confidence=0.0
        )
        self._pending_intents.append(intent)
        return intent
    
    def position_is_long(self, symbol: str) -> bool:
        """Check if we have a long position in symbol."""
        return self.state.is_long(symbol)
    
    def position_is_short(self, symbol: str) -> bool:
        """Check if we have a short position in symbol."""
        return self.state.is_short(symbol)
    
    def get_pending_intents(self) -> List[OrderIntent]:
        """Get and clear pending order intents."""
        intents = self._pending_intents.copy()
        self._pending_intents.clear()
        return intents


class StrategyEngineV2:
    """
    Strategy Engine v2
    
    Orchestrates strategy execution with unified indicator calculations
    and clean separation of concerns.
    """
    
    def __init__(
        self,
        config: Dict[str, Any],
        market_data_engine: MarketDataEngine,
        risk_engine: Optional[Any] = None,
        logger_instance: Optional[logging.Logger] = None
    ):
        self.config = config
        self.market_data = market_data_engine
        self.risk_engine = risk_engine
        self.logger = logger_instance or logger
        
        # Strategy registry
        self.strategies: Dict[str, BaseStrategy] = {}
        self.strategy_states: Dict[str, StrategyState] = {}
        
        # Configuration
        self.window_size = config.get("history_lookback", 200)
        self.enabled_strategies = config.get("strategies", [])
        
        # Paper engine reference (for execution)
        self.paper_engine = None
        
        self.logger.info("StrategyEngineV2 initialized with %d strategies", len(self.enabled_strategies))
    
    def register_strategy(self, strategy_code: str, strategy: BaseStrategy):
        """Register a strategy instance."""
        if strategy_code not in self.strategy_states:
            self.strategy_states[strategy_code] = StrategyState()
        self.strategies[strategy_code] = strategy
        self.logger.info("Registered strategy: %s", strategy_code)
    
    def set_paper_engine(self, paper_engine: Any):
        """Set reference to paper engine for order execution."""
        self.paper_engine = paper_engine
    
    def compute_indicators(
        self,
        series: Dict[str, List[float]],
        config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Compute standard indicators from price series.
        
        Args:
            series: Dict with keys: open, high, low, close, volume (lists)
            config: Optional indicator configuration
        
        Returns:
            Dict of computed indicators
        """
        close = series.get("close", [])
        high = series.get("high", [])
        low = series.get("low", [])
        volume = series.get("volume", [])
        
        if not close or len(close) < 20:
            return {}
        
        ind = {}
        
        try:
            # EMAs
            ind["ema9"] = indicators.ema(close, 9)
            ind["ema20"] = indicators.ema(close, 20)
            ind["ema50"] = indicators.ema(close, 50)
            if len(close) >= 100:
                ind["ema100"] = indicators.ema(close, 100)
            if len(close) >= 200:
                ind["ema200"] = indicators.ema(close, 200)
            
            # SMAs
            ind["sma20"] = indicators.sma(close, 20)
            ind["sma50"] = indicators.sma(close, 50)
            
            # RSI
            if len(close) >= 15:
                ind["rsi14"] = indicators.rsi(close, 14)
            
            # ATR
            if len(high) >= 14 and len(low) >= 14:
                ind["atr14"] = indicators.atr(high, low, close, 14)
            
            # Bollinger Bands
            if len(close) >= 20:
                bb = indicators.bollinger(close, 20, 2.0)
                ind["bb_upper"] = bb["upper"]
                ind["bb_middle"] = bb["middle"]
                ind["bb_lower"] = bb["lower"]
            
            # SuperTrend
            if len(high) >= 10 and len(low) >= 10:
                st = indicators.supertrend(high, low, close, 10, 3.0)
                ind["supertrend"] = st["supertrend"]
                ind["supertrend_direction"] = st["direction"]
            
            # VWAP
            if volume and len(volume) == len(close):
                ind["vwap"] = indicators.vwap(close, volume)
            
            # Slope
            if len(close) >= 10:
                ind["slope10"] = indicators.slope(close, 10)
            
            # HL2/HL3
            if high and low:
                ind["hl2"] = indicators.hl2(high, low)
                ind["hl3"] = indicators.hl3(high, low, close)
            
            # Trend determination
            if "ema20" in ind and "ema50" in ind:
                ind["trend"] = "up" if ind["ema20"] > ind["ema50"] else "down"
            
        except Exception as e:
            self.logger.warning("Indicator calculation error: %s", e)
        
        return ind
    
    def run_strategy(
        self,
        strategy_code: str,
        symbol: str,
        timeframe: str
    ) -> List[OrderIntent]:
        """
        Run a single strategy for a symbol.
        
        Returns:
            List of order intents
        """
        if strategy_code not in self.strategies:
            return []
        
        strategy = self.strategies[strategy_code]
        
        try:
            # Fetch windowed series from market data engine
            window = self.market_data.get_window(symbol, timeframe, self.window_size)
            
            if not window or len(window) < 20:
                self.logger.debug("Insufficient data for %s/%s", symbol, timeframe)
                return []
            
            # Build series dict
            series = {
                "open": [c["open"] for c in window],
                "high": [c["high"] for c in window],
                "low": [c["low"] for c in window],
                "close": [c["close"] for c in window],
                "volume": [c.get("volume", 0) for c in window],
            }
            
            # Get current candle
            current_candle = window[-1]
            
            # Compute indicators
            ind = self.compute_indicators(series)
            
            # Generate signal
            decision = strategy.generate_signal(current_candle, series, ind)
            
            # Convert decision to order intents
            intents = []
            
            if decision and decision.action in ["BUY", "SELL", "EXIT"]:
                intent = OrderIntent(
                    symbol=symbol,
                    action=decision.action,
                    qty=None,  # Will be determined by risk engine
                    reason=decision.reason,
                    strategy_code=strategy_code,
                    confidence=getattr(decision, "confidence", 0.0),
                    metadata={"timeframe": timeframe}
                )
                intents.append(intent)
            
            # Also get any pending intents from strategy helper methods
            pending = strategy.get_pending_intents()
            intents.extend(pending)
            
            return intents
            
        except Exception as e:
            self.logger.exception("Strategy %s failed for %s: %s", strategy_code, symbol, e)
            return []
    
    def run(self, symbols: List[str], timeframe: Optional[str] = None) -> None:
        """
        Run all enabled strategies for given symbols.
        
        Args:
            symbols: List of symbols to trade
            timeframe: Optional timeframe override
        """
        if not self.strategies:
            return
        
        tf = timeframe or self.config.get("timeframe", "5m")
        
        for strategy_code in self.strategies.keys():
            for symbol in symbols:
                # Run strategy and get intents
                intents = self.run_strategy(strategy_code, symbol, tf)
                
                # Process each intent
                for intent in intents:
                    self._process_intent(intent, symbol, tf, strategy_code)
    
    def _process_intent(
        self,
        intent: OrderIntent,
        symbol: str,
        timeframe: str,
        strategy_code: str
    ) -> None:
        """
        Process an order intent through risk engine and execution.
        """
        if not self.paper_engine:
            self.logger.warning("No paper engine set, cannot execute intent")
            return
        
        # Get current price
        candle = self.market_data.get_latest_candle(symbol, timeframe)
        if not candle:
            self.logger.warning("No candle data for %s, cannot process intent", symbol)
            return
        
        price = candle.get("close", 0.0)
        if price <= 0:
            return
        
        # Apply risk checks if risk engine available
        if self.risk_engine:
            # Build trade context
            context = TradeContext(
                symbol=symbol,
                action=intent.action,
                price=price,
                qty=intent.qty or 1,
                strategy_code=strategy_code,
            )
            
            # Check risk (simplified - actual implementation may vary)
            # For now, just pass through
            pass
        
        # Forward to paper engine
        try:
            logical_name = getattr(self.paper_engine, "logical_alias", {}).get(symbol, symbol)
            
            self.paper_engine._handle_signal(
                symbol=symbol,
                action=intent.action,
                price=price,
                logical=logical_name,
                tf=timeframe,
                strategy_name=strategy_code,
                strategy_code=strategy_code,
                confidence=intent.confidence,
                reason=intent.reason,
            )
            
            # Update strategy state
            if strategy_code in self.strategy_states:
                state = self.strategy_states[strategy_code]
                if intent.action == "BUY":
                    state.update_position(symbol, intent.qty or 1, price)
                elif intent.action == "SELL":
                    state.update_position(symbol, -(intent.qty or 1), price)
                elif intent.action == "EXIT":
                    state.update_position(symbol, 0)
            
        except Exception as e:
            self.logger.exception("Failed to execute intent for %s: %s", symbol, e)
