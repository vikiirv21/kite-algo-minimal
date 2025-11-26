"""
Strategy Engine v2

Modern strategy execution framework with unified indicator calculations.
Provides clean separation between strategy logic, market data, and execution.
"""

from __future__ import annotations

import logging
import importlib
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from analytics.telemetry_bus import publish_engine_health, publish_decision_trace, publish_signal_event, publish_indicator_event
from core import indicators
from core.market_data_engine import MarketDataEngine
from core.risk_engine import RiskAction, RiskConfig, RiskDecision, TradeContext
from strategies.base import Decision

logger = logging.getLogger(__name__)

# Import StrategyOrchestrator (optional - graceful fallback)
try:
    from core.strategy_orchestrator import StrategyOrchestrator
    ORCHESTRATOR_AVAILABLE = True
except ImportError:
    ORCHESTRATOR_AVAILABLE = False
    StrategyOrchestrator = None


class StrategySignal:
    """
    Normalized signal from a strategy before filtering.
    
    This is the standardized format all raw signals are converted to.
    """
    
    def __init__(
        self,
        timestamp: datetime,
        symbol: str,
        strategy_name: str,
        direction: str,  # "long", "short", "flat"
        strength: float = 0.0,  # Confidence/score (0-1)
        tags: Optional[Dict[str, Any]] = None,
    ):
        self.timestamp = timestamp
        self.symbol = symbol
        self.strategy_name = strategy_name
        self.direction = direction.lower()
        self.strength = max(0.0, min(1.0, strength))  # Clamp to [0, 1]
        self.tags = tags or {}
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "strategy_name": self.strategy_name,
            "direction": self.direction,
            "strength": self.strength,
            "tags": self.tags,
        }


@dataclass
class OrderIntent:
    """
    Unified OrderIntent dataclass for StrategyEngineV2.
    
    Represents a trading intent from a strategy before risk checks.
    All trading decisions flow through this standardized format.
    """
    # Core fields - provide defaults for backward compatibility
    symbol: str = ""
    signal: str = "HOLD"  # "BUY", "SELL", "EXIT", "HOLD"
    side: str = "FLAT"  # "LONG", "SHORT", "FLAT"
    logical: str = ""  # Logical symbol identifier (e.g., "NIFTY", "EQ_RELIANCE")
    timeframe: str = ""  # Timeframe (e.g., "5m", "15m")
    strategy_id: str = ""  # Strategy identifier
    confidence: float = 0.0  # Confidence score (0.0 to 1.0)
    
    # Optional fields
    qty_hint: Optional[int] = None  # Optional quantity hint
    qty: Optional[int] = None  # Legacy field for quantity
    reason: str = ""  # Entry/signal reason
    exit_reason: str = ""  # Exit reason (if applicable)
    extra: Dict[str, Any] = field(default_factory=dict)  # Additional metadata
    
    # Legacy fields for backward compatibility
    action: Optional[str] = None  # Maps to signal
    strategy_code: Optional[str] = None  # Maps to strategy_id
    metadata: Optional[Dict[str, Any]] = None  # Maps to extra
    
    def __post_init__(self):
        """Ensure signal is uppercase and legacy fields are synchronized."""
        # If action is provided, use it to set signal
        if self.action and not self.signal:
            self.signal = self.action.upper()
        else:
            self.signal = self.signal.upper()
        
        # If strategy_code is provided, use it
        if self.strategy_code and not self.strategy_id:
            self.strategy_id = self.strategy_code
        
        # If symbol is provided but not logical, set logical = symbol
        if self.symbol and not self.logical:
            self.logical = self.symbol
        
        # Sync legacy fields
        if self.action is None:
            self.action = self.signal
        if self.strategy_code is None:
            self.strategy_code = self.strategy_id
        if self.metadata is None:
            self.metadata = self.extra
        
        # Set side based on signal/action if not set
        if self.side == "FLAT" and self.signal in ["BUY", "LONG"]:
            self.side = "LONG"
        elif self.side == "FLAT" and self.signal in ["SELL", "SHORT"]:
            self.side = "SHORT"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal": self.signal,
            "side": self.side,
            "logical": self.logical,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "strategy_id": self.strategy_id,
            "confidence": self.confidence,
            "qty_hint": self.qty_hint,
            "qty": self.qty,
            "reason": self.reason,
            "exit_reason": self.exit_reason,
            "extra": self.extra,
            # Include legacy fields for backward compatibility
            "action": self.action,
            "strategy_code": self.strategy_code,
            "metadata": self.metadata,
        }


class StrategyState:
    """Maintains state for a strategy instance."""
    
    def __init__(self):
        self.positions: Dict[str, Dict[str, Any]] = {}  # symbol -> position info
        self.signals: List[Dict[str, Any]] = []
        self.metadata: Dict[str, Any] = {}
        
        # Per-strategy risk tracking
        self.trades_today: int = 0
        self.win_streak: int = 0
        self.loss_streak: int = 0
        self.win_count: int = 0
        self.loss_count: int = 0
        self.recent_pnl: float = 0.0
        self.last_signal_time: Optional[datetime] = None
        self.recent_decisions: List[Dict[str, Any]] = []  # Last N signal decisions
        
        # Health tracking fields for dashboard
        self.signals_today: int = 0
        self.last_signal: str = "HOLD"
        self.last_signal_ts: Optional[datetime] = None
        self.regime: Optional[str] = None
    
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
    
    def record_decision(self, symbol: str, decision: str, confidence: float, reason: str):
        """Record a signal decision for analytics."""
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "symbol": symbol,
            "decision": decision,
            "confidence": confidence,
            "reason": reason,
        }
        self.recent_decisions.append(entry)
        # Keep only last 20 decisions
        if len(self.recent_decisions) > 20:
            self.recent_decisions = self.recent_decisions[-20:]
    
    def update_pnl(self, pnl_delta: float):
        """Update PnL tracking and win/loss streaks."""
        self.recent_pnl += pnl_delta
        if pnl_delta > 0:
            self.win_streak += 1
            self.loss_streak = 0
            self.win_count += 1
        elif pnl_delta < 0:
            self.loss_streak += 1
            self.win_streak = 0
            self.loss_count += 1


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
        indicators: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Optional[Decision]:
        """
        Generate trading signal based on current candle, historical series, and indicators.
        
        Args:
            candle: Current candle dict with keys: open, high, low, close, volume
            series: Historical series dict with keys: open, high, low, close, volume (lists)
            indicators: Pre-computed indicators dict (EMA, RSI, ATR, etc.)
            context: Optional context dict with expiry info, session time, etc.
                    May include: is_expiry_day, is_expiry_week, time_to_expiry_minutes, session_time_ist
        
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
        config: dict,
        market_data_engine=None,
        state_store=None,
        analytics=None,
        regime_engine=None,
        market_context=None,
        **kwargs,
    ):
        # Backward compatibility: accept market_data_engine_v2 via kwargs
        if market_data_engine is None and "market_data_engine_v2" in kwargs:
            market_data_engine = kwargs["market_data_engine_v2"]
        
        # Also accept 'mde' as alias
        if market_data_engine is None and "mde" in kwargs:
            market_data_engine = kwargs["mde"]
        
        # Support other legacy kwargs
        portfolio_engine = kwargs.get("portfolio_engine", None)
        analytics_engine = kwargs.get("analytics_engine", None)
        logger = kwargs.get("logger", None)
        logger_instance = kwargs.get("logger_instance", None)
        risk_engine = kwargs.get("risk_engine", None)
        market_data_engine_v2 = kwargs.get("market_data_engine_v2", None)
        
        self.config = config or {}
        self.market_context = market_context
        self.market_data_engine = market_data_engine
        self.state_store = state_store
        self.analytics = analytics
        self.regime_engine = regime_engine
        
        # Backward compatibility aliases
        self.mde = self.market_data_engine
        self.market_data = self.market_data_engine
        self.market_data_v2 = market_data_engine_v2  # Optional MDE v2 instance
        self.portfolio_engine = portfolio_engine
        self.analytics_engine = analytics_engine or analytics
        self.logger = logger_instance or logger or logging.getLogger(__name__)
        self.risk_engine = risk_engine
        
        # Strategy registry
        self.strategies: Dict[str, BaseStrategy] = {}
        self.strategy_states: Dict[str, StrategyState] = {}
        
        # Configuration
        self.window_size = self.config.get("history_lookback", 200)
        self.enabled_strategies = self.config.get("strategies", [])
        self.primary_strategy_id = self.config.get("primary_strategy_id", "")
        
        # Conflict resolution config
        self.conflict_resolution_mode = self.config.get("conflict_resolution", "highest_confidence")
        self.strategy_priorities: Dict[str, int] = self.config.get("strategy_priorities", {})
        
        # Filtering config
        self.max_trades_per_day = self.config.get("max_trades_per_day", 10)
        self.max_loss_streak = self.config.get("max_loss_streak", 3)
        
        # Paper engine reference (for execution)
        self.paper_engine = None
        
        # Strategy Orchestrator v3 (optional)
        self.orchestrator = None
        self._init_orchestrator()
        
        # Telemetry support
        self._enable_telemetry = True
        self._telemetry_thread: Optional[threading.Thread] = None
        self._telemetry_stop = threading.Event()
        self._start_telemetry_thread()
        
        # Indicator warmup tracking: set of (symbol, indicator_name, timeframe) tuples
        # to log warmup only once per combination
        self._indicator_warmup_logged: set = set()
        
        self.logger.info("StrategyEngineV2 initialized with %d strategies", len(self.enabled_strategies))
        if self.regime_engine:
            self.logger.info("StrategyEngineV2: RegimeEngine enabled")
        if self.conflict_resolution_mode:
            self.logger.info("StrategyEngineV2: Conflict resolution mode: %s", self.conflict_resolution_mode)
    
    @classmethod
    def from_config(cls, cfg: Dict[str, Any], logger: Optional[logging.Logger] = None) -> "StrategyEngineV2":
        """
        Create StrategyEngineV2 instance from config.
        
        Reads cfg["strategy_engine"] (or {} if missing) and:
        - Iterates strategies_v2 list
        - Imports module and class for each
        - Instantiates strategy with (strategy_id, params, logger)
        - Registers in self.strategies dict keyed by id
        - Logs final list of strategies
        
        Args:
            cfg: Full application config dict
            logger: Optional logger instance
            
        Returns:
            Configured StrategyEngineV2 instance
        """
        log = logger or logging.getLogger(__name__)
        
        # Extract strategy_engine config safely
        strategy_engine_cfg = cfg.get("strategy_engine", {})
        if not isinstance(strategy_engine_cfg, dict):
            strategy_engine_cfg = {}
        
        # Create engine instance
        engine = cls(config=strategy_engine_cfg, logger_instance=log)
        
        # Load and register strategies_v2
        strategies_v2 = strategy_engine_cfg.get("strategies_v2", [])
        if not strategies_v2:
            log.warning("No strategies_v2 configured in strategy_engine config")
            return engine
        
        log.info("Loading %d strategies from config", len(strategies_v2))
        trading_cfg = cfg.get("trading", {}) if isinstance(cfg, dict) else {}
        # Determine trading style: prefer explicit style keys; ignore if value is "live"/"paper"
        style_raw = trading_cfg.get("strategy_mode") or trading_cfg.get("mode_style") or trading_cfg.get("style")
        mode_value = trading_cfg.get("mode")
        trading_style = None
        if isinstance(style_raw, str):
            trading_style = style_raw.lower()
        elif isinstance(mode_value, str) and mode_value.lower() in ("multi", "scalp", "intraday"):
            trading_style = mode_value.lower()
        if trading_style not in ("multi", "scalp", "intraday"):
            trading_style = "intraday"
        
        for strategy_cfg in strategies_v2:
            if not isinstance(strategy_cfg, dict):
                log.warning("Invalid strategy config (not a dict): %s", strategy_cfg)
                continue
            
            strategy_id = strategy_cfg.get("id", "")
            module_name = strategy_cfg.get("module", "")
            class_name = strategy_cfg.get("class", "")
            enabled = strategy_cfg.get("enabled", True)
            params = strategy_cfg.get("params", {})
            
            if not enabled:
                log.info("Strategy %s is disabled, skipping", strategy_id)
                continue
            
            if not strategy_id or not module_name or not class_name:
                log.warning(
                    "Strategy config missing required fields (id=%s, module=%s, class=%s)",
                    strategy_id, module_name, class_name
                )
                continue
            
            # Helper to register one strategy variant
            def _register_variant(var_id: str, variant_params: Dict[str, Any], role: str) -> None:
                try:
                    mod = importlib.import_module(module_name)
                    strategy_class = getattr(mod, class_name)
                    state = StrategyState()
                    full_config = {"strategy_id": var_id, **variant_params, "role": role}
                    strategy = strategy_class(config=full_config, strategy_state=state)
                    engine.register_strategy(var_id, strategy)
                    log.info(
                        "StrategyEngineV2: registered %s (role=%s, module=%s, class=%s, timeframe=%s)",
                        var_id,
                        role,
                        module_name,
                        class_name,
                        variant_params.get("timeframe"),
                    )
                except Exception as exc:  # noqa: BLE001
                    log.error(
                        "Failed to load strategy %s from %s.%s: %s",
                        var_id,
                        module_name,
                        class_name,
                        exc,
                        exc_info=True,
                    )

            # Intraday/base variant always loaded
            base_params = dict(params)
            base_params.setdefault("timeframe", base_params.get("intraday_timeframe", base_params.get("timeframe")))
            _register_variant(strategy_id, base_params, role="intraday")

            # Optional scalping variant for multi/scalp modes
            scalping_tf = params.get("scalping_timeframe") or trading_cfg.get("scalping_timeframe")
            if trading_style in ("multi", "scalp") and scalping_tf:
                scalp_id = f"{strategy_id}_SCALP"
                scalp_params = dict(params)
                scalp_params["timeframe"] = scalping_tf
                _register_variant(scalp_id, scalp_params, role="scalping")
        
        log.info(
            "StrategyEngineV2 loaded with strategies: %s",
            list(engine.strategies.keys())
        )
        
        return engine
    
    def evaluate(
        self,
        logical: str,
        symbol: str,
        timeframe: str,
        candle: Dict[str, float],
        indicators: Dict[str, Any],
        mode: str,
        profile: str,
        context: Optional[Dict[str, Any]] = None,
        market_context: Optional[Any] = None
    ) -> Tuple[OrderIntent, Dict[str, Any]]:
        """
        Evaluate trading decision using primary strategy.
        
        Args:
            logical: Logical symbol identifier (e.g., "NIFTY", "EQ_RELIANCE")
            symbol: Actual trading symbol
            timeframe: Timeframe (e.g., "5m", "15m")
            candle: Current candle dict (open, high, low, close, volume)
            indicators: Pre-computed indicators dict
            mode: Trading mode (e.g., "PAPER", "LIVE")
            profile: Trading profile (e.g., "INTRADAY", "SWING")
            context: Optional additional context
            market_context: Optional MarketContext for broad market awareness
            
        Returns:
            Tuple of (OrderIntent, debug_payload)
            debug_payload always includes indicators (ema20, ema50, ema100, ema200, rsi14, atr)
        """
        context = context or {}
        
        # Use instance market_context if not provided
        if market_context is None and self.market_context is not None:
            # Get current snapshot from market context
            if hasattr(self.market_context, "snapshot"):
                market_context = self.market_context.snapshot
        
        # Add market_context to indicators if provided
        if market_context is not None:
            indicators = {**indicators, "market_context": market_context}
        
        # Build debug payload with indicators
        debug_payload = {
            "logical": logical,
            "symbol": symbol,
            "timeframe": timeframe,
            "mode": mode,
            "profile": profile,
            "candle": candle,
            "indicators": {
                "ema20": indicators.get("ema20"),
                "ema50": indicators.get("ema50"),
                "ema100": indicators.get("ema100"),
                "ema200": indicators.get("ema200"),
                "rsi14": indicators.get("rsi14"),
                "atr": indicators.get("atr14"),  # Map atr14 to atr
                "atr14": indicators.get("atr14"),
            },
            "context": context,
        }
        
        # Add market context to debug payload if present
        if market_context is not None:
            debug_payload["market_context"] = market_context.to_dict() if hasattr(market_context, "to_dict") else str(market_context)
        
        # Get primary strategy
        strategy_id = self.primary_strategy_id
        if not strategy_id:
            # If no primary strategy configured, return HOLD
            intent = OrderIntent(
                signal="HOLD",
                side="FLAT",
                logical=logical,
                symbol=symbol,
                timeframe=timeframe,
                strategy_id="none",
                confidence=0.0,
                reason="no_primary_strategy_configured",
            )
            return intent, debug_payload
        
        if strategy_id not in self.strategies:
            # Primary strategy not found, return HOLD
            intent = OrderIntent(
                signal="HOLD",
                side="FLAT",
                logical=logical,
                symbol=symbol,
                timeframe=timeframe,
                strategy_id=strategy_id,
                confidence=0.0,
                reason="primary_strategy_not_found",
            )
            return intent, debug_payload
        
        strategy = self.strategies[strategy_id]
        
        try:
            # Build series dict (empty for now - strategies should use indicators)
            series = {}
            
            # Call strategy's generate_signal method with context
            decision = strategy.generate_signal(candle, series, indicators, context)
            
            # Convert Decision to OrderIntent
            if decision and decision.action and decision.action != "HOLD":
                # Map action to signal and side
                action = decision.action.upper()
                if action in ["BUY", "LONG"]:
                    signal = "BUY"
                    side = "LONG"
                elif action in ["SELL", "SHORT"]:
                    signal = "SELL"
                    side = "SHORT"
                elif action in ["EXIT", "CLOSE", "FLAT"]:
                    signal = "EXIT"
                    side = "FLAT"
                else:
                    signal = "HOLD"
                    side = "FLAT"
                
                intent = OrderIntent(
                    signal=signal,
                    side=side,
                    logical=logical,
                    symbol=symbol,
                    timeframe=timeframe,
                    strategy_id=strategy_id,
                    confidence=getattr(decision, "confidence", 0.0),
                    reason=getattr(decision, "reason", ""),
                    extra={"decision": decision.to_dict() if hasattr(decision, "to_dict") else {}},
                )
            else:
                # HOLD or no decision
                intent = OrderIntent(
                    signal="HOLD",
                    side="FLAT",
                    logical=logical,
                    symbol=symbol,
                    timeframe=timeframe,
                    strategy_id=strategy_id,
                    confidence=0.0,
                    reason=getattr(decision, "reason", "no_signal") if decision else "no_decision",
                )
            
            # Add decision details to debug payload
            if decision:
                debug_payload["decision"] = {
                    "action": decision.action,
                    "reason": getattr(decision, "reason", ""),
                    "confidence": getattr(decision, "confidence", 0.0),
                }
            
            # Emit diagnostics (non-blocking)
            self._emit_diagnostic(
                symbol=symbol,
                strategy_id=strategy_id,
                intent=intent,
                indicators=indicators,
                candle=candle,
                context=context,
            )
            
            return intent, debug_payload
            
        except Exception as exc:
            self.logger.error(
                "Strategy %s failed for %s: %s",
                strategy_id, symbol, exc,
                exc_info=True
            )
            
            # Return HOLD intent on error
            intent = OrderIntent(
                signal="HOLD",
                side="FLAT",
                logical=logical,
                symbol=symbol,
                timeframe=timeframe,
                strategy_id=strategy_id,
                confidence=0.0,
                reason=f"strategy_error: {str(exc)}",
            )
            debug_payload["error"] = str(exc)
            
            return intent, debug_payload
    
    def register_strategy(self, strategy_code: str, strategy: BaseStrategy):
        """Register a strategy instance."""
        if strategy_code not in self.strategy_states:
            self.strategy_states[strategy_code] = StrategyState()
        self.strategies[strategy_code] = strategy
        self.logger.info("Registered strategy: %s", strategy_code)
    
    def set_paper_engine(self, paper_engine: Any):
        """Set reference to paper engine for order execution."""
        self.paper_engine = paper_engine
    
    def _emit_diagnostic(
        self,
        symbol: str,
        strategy_id: str,
        intent: OrderIntent,
        indicators: Dict[str, Any],
        candle: Dict[str, float],
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Emit diagnostic record for strategy decision.
        
        This is a best-effort, non-blocking operation that captures
        key indicators and reasoning for debugging purposes.
        
        Args:
            symbol: Trading symbol
            strategy_id: Strategy identifier
            intent: OrderIntent produced by strategy
            indicators: Computed indicators dict
            candle: Current candle dict
            context: Optional context dict
        """
        try:
            from analytics.diagnostics import build_diagnostic_record, append_diagnostic
            
            # Extract price
            price = candle.get("close", 0.0)
            
            # Extract indicators
            ema20 = indicators.get("ema20")
            ema50 = indicators.get("ema50")
            rsi14 = indicators.get("rsi14")
            atr14 = indicators.get("atr14")
            
            # Calculate trend strength if EMAs available
            trend_strength = None
            if ema20 is not None and ema50 is not None and ema50 != 0:
                trend_strength = abs((ema20 - ema50) / ema50)
            
            # Extract regime if available
            regime = None
            if context and "regime" in context:
                regime = context["regime"]
            elif "market_context" in indicators:
                mc = indicators["market_context"]
                if hasattr(mc, "regime"):
                    regime = mc.regime
                elif isinstance(mc, dict) and "regime" in mc:
                    regime = mc["regime"]
            
            # Extract risk:reward if available
            rr = intent.extra.get("rr") if intent.extra else None
            
            # Determine risk block reason
            risk_block = "none"
            if intent.signal == "HOLD":
                reason_lower = intent.reason.lower()
                if "loss" in reason_lower or "drawdown" in reason_lower:
                    risk_block = "max_loss"
                elif "cooldown" in reason_lower or "streak" in reason_lower:
                    risk_block = "cooldown"
                elif "slippage" in reason_lower:
                    risk_block = "slippage"
            
            # Build diagnostic record
            record = build_diagnostic_record(
                price=price,
                decision=intent.signal,
                reason=intent.reason,
                confidence=intent.confidence,
                ema20=ema20,
                ema50=ema50,
                trend_strength=trend_strength,
                rr=rr,
                regime=regime,
                risk_block=risk_block,
                # Additional fields
                rsi14=rsi14,
                atr14=atr14,
                timeframe=intent.timeframe,
                side=intent.side,
            )
            
            # Append diagnostic (non-blocking)
            append_diagnostic(symbol, strategy_id, record)
            
        except Exception as exc:
            # Never let diagnostics crash the engine
            self.logger.debug("Failed to emit diagnostic: %s", exc)
    
    def _init_orchestrator(self) -> None:
        """
        Initialize the Strategy Orchestrator if enabled in config.
        """
        if not ORCHESTRATOR_AVAILABLE:
            self.orchestrator = None
            return
        
        cfg = self.config.get("strategy_orchestrator") or self.config.get("orchestrator") or {}
        enabled = cfg.get("enabled", False)
        
        if not enabled:
            self.orchestrator = None
            return
        
        try:
            # StrategyOrchestrator expects full config with strategy_orchestrator key
            # Create a config dict with the orchestrator config nested
            full_config = {
                "strategy_orchestrator": cfg
            }
            self.orchestrator = StrategyOrchestrator(
                config=full_config,
                state_store=self.state_store,
                analytics=self.analytics,
                logger_instance=self.logger,
            )
            self.logger.info("StrategyOrchestrator initialized successfully")
        except Exception as e:
            self.logger.warning("Failed to initialize StrategyOrchestrator: %s", e)
            self.orchestrator = None
    
    def compute_indicators(
        self,
        series: Dict[str, List[float]],
        config: Optional[Dict[str, Any]] = None,
        symbol: Optional[str] = None,
        timeframe: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Compute standard indicators from price series.
        
        Args:
            series: Dict with keys: open, high, low, close, volume (lists)
            config: Optional indicator configuration
            symbol: Optional symbol name for warmup logging
            timeframe: Optional timeframe for warmup logging
        
        Returns:
            Dict of computed indicators
        """
        from core.indicators import IndicatorWarmupError
        
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
            
        except IndicatorWarmupError as e:
            # This is expected during warmup - only log once per (symbol, indicator, timeframe)
            warmup_key = (symbol or "unknown", e.indicator_name, timeframe or "unknown")
            if warmup_key not in self._indicator_warmup_logged:
                self._indicator_warmup_logged.add(warmup_key)
                self.logger.info(
                    "Indicator warmup: %s on %s (%s) requires %d bars, currently have %d",
                    e.indicator_name,
                    symbol or "unknown",
                    timeframe or "unknown",
                    e.required,
                    e.actual
                )
            # Skip this indicator for now, continue with others
            pass
        except Exception as e:
            # Other errors (math errors, NaNs, etc.) should still be logged as warnings
            self.logger.warning("Indicator calculation error: %s", e)
        
        return ind
    
    def run_strategy(
        self,
        strategy_code: str,
        symbol: str,
        timeframe: str,
        market_regime: Optional[Dict[str, Any]] = None
    ) -> List[OrderIntent]:
        """
        Run a single strategy for a symbol.
        
        Args:
            strategy_code: Strategy identifier
            symbol: Trading symbol
            timeframe: Timeframe (e.g., '5m')
            market_regime: Optional market regime snapshot
        
        Returns:
            List of order intents
        """
        if strategy_code not in self.strategies:
            return []
        
        # Check with orchestrator if strategy should run
        if self.orchestrator:
            decision = self.orchestrator.should_run_strategy(strategy_code, market_regime)
            if not decision.allow:
                self.logger.info(
                    "[strategy-skip] %s: %s",
                    strategy_code,
                    decision.reason
                )
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
            ind = self.compute_indicators(series, symbol=symbol, timeframe=timeframe)
            
            # Publish indicator event to telemetry
            if self._enable_telemetry:
                publish_indicator_event(
                    symbol=symbol,
                    timeframe=timeframe,
                    indicators={k: v for k, v in ind.items() if isinstance(v, (int, float, str, bool))},
                    strategy=strategy_code
                )
            
            # Get regime snapshot if RegimeEngine is available
            if self.regime_engine:
                try:
                    regime_snapshot = self.regime_engine.snapshot(symbol)
                    ind["regime_trend"] = regime_snapshot.trend
                    ind["regime_volatility"] = regime_snapshot.volatility
                    ind["regime_structure"] = regime_snapshot.structure
                    ind["regime_velocity"] = regime_snapshot.velocity
                    ind["regime_atr"] = regime_snapshot.atr
                    ind["regime_slope"] = regime_snapshot.slope
                except Exception as e:
                    self.logger.debug("Failed to get regime snapshot for %s: %s", symbol, e)
            
            # Generate signal
            decision = strategy.generate_signal(current_candle, series, ind)
            
            # Publish decision trace to telemetry
            if self._enable_telemetry and decision:
                publish_decision_trace(
                    strategy_name=strategy_code,
                    symbol=symbol,
                    decision=decision.action if hasattr(decision, 'action') else str(decision),
                    trace_data={
                        "reason": decision.reason if hasattr(decision, 'reason') else "",
                        "confidence": decision.confidence if hasattr(decision, 'confidence') else 0.0,
                        "timeframe": timeframe,
                        "close_price": current_candle.get("close", 0.0),
                    }
                )
            
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
                
                # Update strategy state with signal info
                if strategy_code in self.strategy_states:
                    state = self.strategy_states[strategy_code]
                    state.signals_today += 1
                    state.last_signal = decision.action
                    state.last_signal_ts = datetime.now(timezone.utc)
                
                # Publish signal event to telemetry
                if self._enable_telemetry:
                    publish_signal_event(
                        symbol=symbol,
                        strategy_name=strategy_code,
                        signal=decision.action,
                        confidence=getattr(decision, "confidence", 0.0),
                        reason=decision.reason,
                        timeframe=timeframe,
                    )
            
            # Also get any pending intents from strategy helper methods
            pending = strategy.get_pending_intents()
            intents.extend(pending)
            
            return intents
            
        except Exception as e:
            self.logger.exception("Strategy %s failed for %s: %s", strategy_code, symbol, e)
            return []
    
    def _get_market_regime(self) -> Dict[str, Any]:
        """
        Get current market regime snapshot.
        
        Returns a stub regime if RegimeDetector is not available.
        In production, this would integrate with a real regime detection system.
        """
        # Try to get regime from shared regime detector if available
        try:
            from core.regime_detector import shared_regime_detector, Regime
            
            # Get regime for primary symbol (e.g., NIFTY)
            primary_symbol = self.config.get("primary_symbol", "NIFTY")
            regime = shared_regime_detector.get_regime(primary_symbol)
            
            # Convert to dict format
            return {
                "trend": regime == Regime.TREND_UP or regime == Regime.TREND_DOWN,
                "volatile": False,  # Could be enhanced with ATR threshold
                "low_vol": regime == Regime.CHOP,
            }
        except Exception as e:
            self.logger.debug("RegimeDetector not available or failed: %s", e)
            # Return stub regime
            return {
                "trend": False,
                "volatile": False,
                "low_vol": False,
            }
    
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
        
        # Get market regime once for all strategies
        market_regime = self._get_market_regime() if self.orchestrator else None
        
        for strategy_code in self.strategies.keys():
            for symbol in symbols:
                # Run strategy and get intents
                intents = self.run_strategy(strategy_code, symbol, tf, market_regime)
                
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
    
    def normalize_signal(self, decision: Decision, strategy_code: str, symbol: str) -> Optional[StrategySignal]:
        """
        Normalize a raw strategy decision into a StrategySignal.
        
        Args:
            decision: Raw decision from strategy
            strategy_code: Strategy identifier
            symbol: Trading symbol
        
        Returns:
            Normalized StrategySignal or None if invalid
        """
        if not decision or not decision.action:
            return None
        
        action = decision.action.upper()
        
        # Map action to direction
        if action in ["BUY", "LONG"]:
            direction = "long"
        elif action in ["SELL", "SHORT"]:
            direction = "short"
        elif action in ["EXIT", "FLAT", "CLOSE"]:
            direction = "flat"
        elif action == "HOLD":
            return None  # No signal for HOLD
        else:
            self.logger.warning("Unknown action %s from strategy %s", action, strategy_code)
            return None
        
        # Create normalized signal
        signal = StrategySignal(
            timestamp=datetime.utcnow().replace(tzinfo=timezone.utc),
            symbol=symbol,
            strategy_name=strategy_code,
            direction=direction,
            strength=getattr(decision, "confidence", 0.0),
            tags={
                "reason": getattr(decision, "reason", ""),
                "mode": getattr(decision, "mode", ""),
            }
        )
        
        return signal
    
    def filter_signal_basic(self, signal: StrategySignal) -> Tuple[bool, str]:
        """
        Basic validity filter: market open, tradable symbol, etc.
        
        Returns:
            (allowed, reason)
        """
        # Check symbol validity first (before market checks)
        if not getattr(signal, "symbol", None):
            return False, "invalid_symbol"
        
        # Check if market is open (simplified - can be enhanced)
        try:
            from core.market_session import is_market_open
            if not is_market_open():
                return False, "market_closed"
        except Exception:
            pass  # Market session check not available
        
        # Check direction validity
        if signal.direction not in ["long", "short", "flat"]:
            return False, "invalid_direction"
        
        return True, "passed_basic"
    
    def filter_signal_risk(self, signal: StrategySignal, state: StrategyState) -> Tuple[bool, str]:
        """
        Per-strategy risk filter: max trades/day, loss streaks, etc.
        
        Returns:
            (allowed, reason)
        """
        # Check max trades per day
        if state.trades_today >= self.max_trades_per_day:
            return False, f"max_trades_per_day:{self.max_trades_per_day}"
        
        # Check loss streak
        if state.loss_streak >= self.max_loss_streak:
            return False, f"loss_streak:{state.loss_streak}"
        
        # Check recent PnL (can be enhanced with more sophisticated checks)
        # For now, just basic checks
        
        return True, "passed_risk"
    
    def resolve_conflicts(self, signals: List[StrategySignal]) -> List[StrategySignal]:
        """
        Resolve conflicts when multiple strategies emit signals on the same symbol.
        
        Args:
            signals: List of signals from different strategies
        
        Returns:
            Filtered list of signals with conflicts resolved
        """
        if len(signals) <= 1:
            return signals
        
        # Group signals by symbol
        by_symbol: Dict[str, List[StrategySignal]] = {}
        for signal in signals:
            if signal.symbol not in by_symbol:
                by_symbol[signal.symbol] = []
            by_symbol[signal.symbol].append(signal)
        
        resolved = []
        
        for symbol, symbol_signals in by_symbol.items():
            if len(symbol_signals) == 1:
                resolved.append(symbol_signals[0])
                continue
            
            # Check for conflicting directions
            directions = set(s.direction for s in symbol_signals)
            
            if len(directions) == 1:
                # All strategies agree on direction - use highest confidence
                best = max(symbol_signals, key=lambda s: s.strength)
                resolved.append(best)
                self.logger.info(
                    "Multiple strategies agree on %s %s, using %s (conf=%.2f)",
                    symbol, directions.pop(), best.strategy_name, best.strength
                )
            else:
                # Conflicting directions - apply resolution strategy
                winner = self._resolve_conflict_by_mode(symbol_signals)
                if winner:
                    resolved.append(winner)
                    self.logger.info(
                        "Conflict resolved for %s: %s %s (conf=%.2f)",
                        symbol, winner.strategy_name, winner.direction, winner.strength
                    )
                else:
                    self.logger.info("Conflict for %s: no winner, skipping", symbol)
        
        return resolved
    
    def _resolve_conflict_by_mode(self, signals: List[StrategySignal]) -> Optional[StrategySignal]:
        """
        Apply conflict resolution strategy based on configured mode.
        
        Returns:
            Winning signal or None if conflict cannot be resolved
        """
        if self.conflict_resolution_mode == "highest_confidence":
            # Use signal with highest confidence
            return max(signals, key=lambda s: s.strength)
        
        elif self.conflict_resolution_mode == "priority":
            # Use strategy priorities
            def priority(signal: StrategySignal) -> int:
                return self.strategy_priorities.get(signal.strategy_name, 0)
            
            sorted_signals = sorted(signals, key=priority, reverse=True)
            return sorted_signals[0] if sorted_signals else None
        
        elif self.conflict_resolution_mode == "net_out":
            # Net out conflicting signals - if conflict is strong, skip
            # Count long vs short signals weighted by confidence
            long_weight = sum(s.strength for s in signals if s.direction == "long")
            short_weight = sum(s.strength for s in signals if s.direction == "short")
            
            # If net is strong enough, use it
            net_diff = abs(long_weight - short_weight)
            if net_diff > 0.5:  # Threshold
                if long_weight > short_weight:
                    return max((s for s in signals if s.direction == "long"), key=lambda s: s.strength)
                else:
                    return max((s for s in signals if s.direction == "short"), key=lambda s: s.strength)
            else:
                # Net is too weak, skip
                return None
        
        else:
            # Default: highest confidence
            return max(signals, key=lambda s: s.strength)
    
    def generate_decisions(
        self,
        market_snapshot: Dict[str, Any],
        state: Dict[str, Any],
        strategies: List[str]
    ) -> List[OrderIntent]:
        """
        Generate execution-ready decisions from market data.
        
        This is the main entry point for PaperEngine to get trading decisions.
        
        Args:
            market_snapshot: Current market data (prices, volumes, etc.)
            state: Current portfolio state
            strategies: List of strategy codes to run
        
        Returns:
            List of execution-ready OrderIntent objects
        """
        all_signals: List[StrategySignal] = []
        
        # Run each strategy and collect signals
        for strategy_code in strategies:
            if strategy_code not in self.strategies:
                continue
            
            strategy_state = self.strategy_states.get(strategy_code, StrategyState())
            
            # Get symbols from market snapshot
            symbols = list(market_snapshot.keys()) if isinstance(market_snapshot, dict) else []
            
            for symbol in symbols:
                # Run strategy for this symbol
                intents = self.run_strategy(strategy_code, symbol, self.config.get("timeframe", "5m"))
                
                # Convert intents to signals for filtering
                for intent in intents:
                    # Create decision from intent
                    decision = Decision(
                        action=intent.action,
                        reason=intent.reason,
                        confidence=intent.confidence
                    )
                    
                    # Normalize to signal
                    signal = self.normalize_signal(decision, strategy_code, symbol)
                    if signal:
                        # Apply filters
                        basic_ok, basic_reason = self.filter_signal_basic(signal)
                        if not basic_ok:
                            self.logger.debug("Signal rejected (basic): %s - %s", signal.strategy_name, basic_reason)
                            continue
                        
                        risk_ok, risk_reason = self.filter_signal_risk(signal, strategy_state)
                        if not risk_ok:
                            self.logger.debug("Signal rejected (risk): %s - %s", signal.strategy_name, risk_reason)
                            continue
                        
                        # Record decision
                        strategy_state.record_decision(symbol, signal.direction, signal.strength, signal.tags.get("reason", ""))
                        
                        all_signals.append(signal)
        
        # Resolve conflicts
        resolved_signals = self.resolve_conflicts(all_signals)
        
        # Convert signals back to OrderIntents for execution
        decisions: List[OrderIntent] = []
        for signal in resolved_signals:
            # Map direction back to action
            if signal.direction == "long":
                action = "BUY"
            elif signal.direction == "short":
                action = "SELL"
            elif signal.direction == "flat":
                action = "EXIT"
            else:
                continue
            
            intent = OrderIntent(
                symbol=signal.symbol,
                action=action,
                qty=None,  # Will be determined by portfolio engine
                reason=signal.tags.get("reason", ""),
                strategy_code=signal.strategy_name,
                confidence=signal.strength,
                metadata=signal.tags
            )
            decisions.append(intent)
        
        return decisions
    
    def on_candle_close(self, symbol: str, timeframe: str, candle: Dict[str, Any]) -> None:
        """
        Handler for MDE v2 candle close events.
        
        This is called by MarketDataEngineV2 when a candle closes.
        It triggers strategy execution for the given symbol and timeframe.
        
        Args:
            symbol: Trading symbol
            timeframe: Timeframe (e.g., '5m')
            candle: Closed candle dict
        """
        if not self.market_data_v2:
            # MDE v2 not configured, skip
            return
            
        self.logger.debug(
            "Candle close event: %s %s @ %.2f",
            symbol,
            timeframe,
            candle.get("close", 0.0),
        )
        
        # Run all registered strategies for this symbol/timeframe
        for strategy_code, strategy in self.strategies.items():
            # Check if strategy is interested in this timeframe
            strategy_tf = getattr(strategy, "timeframe", self.config.get("timeframe", "5m"))
            if strategy_tf != timeframe:
                continue
                
            try:
                # Fetch candle window from MDE v2
                candles = self.market_data_v2.get_candles(symbol, timeframe, self.window_size)
                
                if not candles or len(candles) < 20:
                    # During warmup, MDE v2 may not have enough candles yet
                    # Skip signal generation until sufficient data is available
                    self.logger.debug(
                        "Warmup: insufficient candles for %s/%s (have %d, need >= 20). Skipping signal generation.",
                        symbol,
                        timeframe,
                        len(candles) if candles else 0,
                    )
                    continue
                    
                # Build series dict
                series = {
                    "open": [c["open"] for c in candles],
                    "high": [c["high"] for c in candles],
                    "low": [c["low"] for c in candles],
                    "close": [c["close"] for c in candles],
                    "volume": [c.get("volume", 0) for c in candles],
                }
                
                # Compute indicators
                indicators = self.compute_indicators(series, symbol=symbol, timeframe=timeframe)
                
                # Run strategy
                decision = strategy.generate_signal(candle, series, indicators)
                
                # Process decision
                if decision and decision.action in ["BUY", "SELL", "EXIT"]:
                    intent = OrderIntent(
                        symbol=symbol,
                        action=decision.action,
                        qty=None,
                        reason=decision.reason,
                        strategy_code=strategy_code,
                        confidence=getattr(decision, "confidence", 0.0),
                        metadata={"timeframe": timeframe}
                    )
                    self._process_intent(intent, symbol, timeframe, strategy_code)
                    
                # Also collect any pending intents
                pending = strategy.get_pending_intents()
                for intent in pending:
                    self._process_intent(intent, symbol, timeframe, strategy_code)
                    
            except Exception as exc:
                self.logger.exception(
                    "Error processing candle close for %s/%s in strategy %s: %s",
                    symbol,
                    timeframe,
                    strategy_code,
                    exc,
                )
    
    def _start_telemetry_thread(self) -> None:
        """Start background thread for publishing strategy health."""
        self._telemetry_stop.clear()
        self._telemetry_thread = threading.Thread(
            target=self._telemetry_loop,
            name="strategy-telemetry",
            daemon=True
        )
        self._telemetry_thread.start()
        self.logger.debug("StrategyEngineV2 telemetry thread started")
    
    def _telemetry_loop(self) -> None:
        """Background loop to publish strategy health every 5 seconds."""
        try:
            while not self._telemetry_stop.wait(5.0):
                self._publish_health()
        except Exception as exc:
            self.logger.error("Strategy telemetry loop error: %s", exc, exc_info=True)
    
    def _publish_health(self) -> None:
        """Publish strategy health metrics to telemetry bus."""
        try:
            # Aggregate strategy states
            total_win_rate = 0.0
            total_loss_streak = 0
            total_confidence = 0.0
            strategy_count = len(self.strategy_states)
            
            for state in self.strategy_states.values():
                # Calculate win rate using getattr for robustness
                wins = getattr(state, "win_count", 0)
                losses = getattr(state, "loss_count", 0)
                total_trades = wins + losses
                if total_trades > 0:
                    total_win_rate += wins / total_trades
                total_loss_streak = max(total_loss_streak, state.loss_streak)
                # Estimate confidence based on recent performance
                if total_trades > 0:
                    total_confidence += wins / total_trades
            
            # Average metrics
            avg_win_rate = total_win_rate / strategy_count if strategy_count > 0 else 0.0
            avg_confidence = total_confidence / strategy_count if strategy_count > 0 else 0.0
            
            metrics = {
                "total_strategies": strategy_count,
                "avg_win_rate": avg_win_rate,
                "max_loss_streak": total_loss_streak,
                "avg_confidence": avg_confidence,
            }
            
            # Add per-strategy metrics
            strategy_metrics = {}
            for strategy_code, state in self.strategy_states.items():
                wins = getattr(state, "win_count", 0)
                losses = getattr(state, "loss_count", 0)
                total_trades = wins + losses
                win_rate = wins / total_trades if total_trades > 0 else None
                
                strategy_metrics[strategy_code] = {
                    "win_count": wins,
                    "loss_count": losses,
                    "win_rate": win_rate,
                    "loss_streak": state.loss_streak,
                    "win_streak": state.win_streak,
                    "open_positions": len(state.positions),
                    "signals_today": getattr(state, "signals_today", 0),
                    "last_signal": getattr(state, "last_signal", "HOLD"),
                    "last_signal_ts": getattr(state, "last_signal_ts", None).isoformat() if getattr(state, "last_signal_ts", None) else None,
                    "regime": getattr(state, "regime", None),
                }
            
            metrics["strategies"] = strategy_metrics
            
            publish_engine_health(
                engine_name="StrategyEngineV2",
                status="active",
                metrics=metrics
            )
        
        except Exception as exc:
            self.logger.error("Failed to publish strategy health: %s", exc, exc_info=True)
    
    def stop_telemetry(self) -> None:
        """Stop the telemetry thread."""
        if self._telemetry_thread and self._telemetry_thread.is_alive():
            self._telemetry_stop.set()
            self._telemetry_thread.join(timeout=5.0)
            self.logger.debug("StrategyEngineV2 telemetry thread stopped")
