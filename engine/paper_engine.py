from __future__ import annotations

import logging
import threading
import time
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
import csv
import uuid
from types import SimpleNamespace

# Bulletproof import/fallback for resolve_multi_tf_config
try:
    # Preferred: if you already have a canonical resolver
    from core.multi_tf import resolve_multi_tf_config  # noqa: F401
except Exception:
    # Fallback: safe default/normalizer so engine never crashes
    def resolve_multi_tf_config(overrides: dict | None) -> dict[str, list[str]]:
        """
        Return a dict like {"NIFTY": ["1m","5m"], ...}.
        - Uses defaults if nothing provided.
        - Merges any overrides from config.
        - Normalizes single values to list[str].
        """
        default = {
            "NIFTY": ["1m", "5m"],
            "BANKNIFTY": ["1m", "5m"],
            "FINNIFTY": ["1m", "5m"],
        }
        if not overrides:
            return default

        merged = {**default, **overrides}
        out: dict[str, list[str]] = {}
        for k, v in merged.items():
            if v is None:
                continue
            if isinstance(v, str):
                out[k] = [v]
            elif isinstance(v, (list, tuple)):
                out[k] = [str(x) for x in v if x is not None]
            else:
                out[k] = [str(v)]
        return out

from core.config import AppConfig
from core.modes import TradingMode
from core.market_session import is_market_open
from core.pattern_filters import should_trade_trend
from core.strategy_tags import Profile
from core.universe import fno_underlyings
from core.portfolio_engine import PortfolioEngine, PortfolioConfig

from broker.execution_router import ExecutionRouter
from broker.paper_broker import PaperBroker

from data.broker_feed import BrokerFeed
from data.instruments import resolve_fno_symbols

from kiteconnect import KiteConnect

from risk.adaptive_risk_manager import AdaptiveRiskManager

from strategies.base import Decision
from strategies.fno_intraday_trend import (
    FnoIntradayTrendStrategy,
    build_reason,
)

from analytics.trade_recorder import TradeRecorder
from analytics.trade_journal import finalize_trade, TRADE_JOURNAL_FIELDS
from analytics.multi_timeframe_engine import MultiTimeframeEngine
from analytics.telemetry_bus import (
    publish_engine_health,
    publish_signal_event,
    publish_order_event,
    publish_position_event,
    publish_decision_trace,
)
from core.strategy_engine import StrategyRunner

# Strategy Engine v2 (optional - fallback to v1 if not available)
try:
    from core.strategy_engine_v2 import StrategyEngineV2, StrategyState
    from strategies.ema20_50_intraday_v2 import EMA2050IntradayV2
    STRATEGY_ENGINE_V2_AVAILABLE = True
except ImportError:
    STRATEGY_ENGINE_V2_AVAILABLE = False
    StrategyEngineV2 = None
    StrategyState = None
    EMA2050IntradayV2 = None

# Market Context (optional - graceful fallback)
try:
    from core.market_context import (
        MarketContext,
        MarketContextBuilder,
        MarketContextConfig,
        initialize_market_context,
    )
    MARKET_CONTEXT_AVAILABLE = True
except ImportError:
    MARKET_CONTEXT_AVAILABLE = False
    MarketContext = None
    MarketContextBuilder = None
    MarketContextConfig = None
    initialize_market_context = None
    StrategyEngineV2 = None
    StrategyState = None
    EMA2050IntradayV2 = None

from engine.meta_strategy_engine import (
    MetaDecision,
    MetaStrategyEngine,
    STYLE_INTRADAY,
)

from risk.position_sizer import (
    DynamicPositionSizer,
    PortfolioState,
    SizerConfig,
    load_portfolio_state,
)
from risk.cost_model import (
    CostBreakdown,
    CostConfig,
    CostModel,
    load_cost_config_from_yaml,
)
from risk.trade_quality import (
    QualityConfig,
    TradeDecision,
    TradeProposal,
    TradeQualityFilter,
    load_quality_config_from_yaml,
)
from risk.factory import build_cost_model, build_trade_quality_filter
from core.risk_engine import (
    RiskConfig,
    TradeContext,
    build_risk_config,
    compute_exit_decision,
)
from core.market_data_engine import MarketDataEngine
from core.universe_builder import load_universe
from core.atr_risk import (
    ATRConfig,
    TimeFilterConfig,
    compute_sl_tp_from_atr,
    is_entry_time_allowed,
)
from analytics.learning_engine import load_tuning
from core.risk_engine import (
    RiskConfig,
    TradeContext,
    build_risk_config,
    compute_exit_decision,
)
from analytics.learning_engine import load_tuning
from core.state_store import JournalStateStore, StateStore
from core.signal_quality import SignalContext, signal_quality_manager
from core.trade_monitor import trade_monitor
from core.event_logging import log_event
from core.regime_detector import Regime, shared_regime_detector
from core.trade_throttler import (
    DEFAULT_EXPECTED_EDGE_RUPEES,
    TradeThrottler,
    build_throttler_config,
)
from core.risk_engine import RiskEngine, RiskDecision, RiskAction
from core.strategy_registry import STRATEGY_REGISTRY
from core.strategy_metrics import StrategyMetricsTracker

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = BASE_DIR / "artifacts"
STATE_PATH = ARTIFACTS_DIR / "paper_state.json"

PROFILE_INTRADAY = {"1m", "3m", "5m"}
PROFILE_SWING = {"15m", "30m", "1h", "60m"}
FILLED_ORDER_STATUSES = {"FILLED", "COMPLETE", "SUCCESS", "EXECUTED", "CLOSED"}


def _safe_int(value, default):
    """Convert to int safely, falling back if value is None or invalid."""
    try:
        if value is None:
            raise TypeError("None not allowed")
        return int(value)
    except (TypeError, ValueError):
        return default


def _profile_from_tf(tf: str) -> str:
    tf_norm = (tf or "").lower()
    if tf_norm in PROFILE_INTRADAY:
        return Profile.INTRADAY.value
    if tf_norm in PROFILE_SWING:
        return Profile.SWING.value
    return Profile.INTRADAY.value


@dataclass
class ActiveTrade:
    trade_id: str
    signal_id: str
    symbol: str
    strategy: str
    side: str
    entry_ts: datetime
    entry_price: float
    planned_risk: float
    quantity: int
    initial_size: int
    meta: Dict[str, Any] = field(default_factory=dict)
    max_favorable_excursion: float = 0.0
    max_adverse_excursion: float = 0.0
    adds: int = 0
    reduces: int = 0
    bars_in_trade: int = 0
    realized_pnl: float = 0.0
    exit_reason: str = ""
    exit_detail: str = ""
    exit_ts: Optional[datetime] = None
    exit_price: Optional[float] = None
    last_qty: int = 0
    sl_price: Optional[float] = None
    tp_price: Optional[float] = None
    atr_method: str = ""
    atr_value: Optional[float] = None
    product_type: str = ""

    def direction_multiplier(self) -> int:
        return 1 if self.side == "LONG" else -1

    def update_price(self, current_price: float) -> None:
        direction = self.direction_multiplier()
        delta = (current_price - self.entry_price) * direction * max(1, abs(self.last_qty))
        self.max_favorable_excursion = max(self.max_favorable_excursion, delta)
        self.max_adverse_excursion = min(self.max_adverse_excursion, delta)
class PaperEngine:
    """
    Paper engine for FnO symbols (NIFTY, BANKNIFTY, FINNIFTY).

    Flow:
    - Read logical FnO names from config.
    - Resolve them to current NFO FUT tradingsymbols using instruments().
    - Initialize paper broker, execution router, data feed, and strategy.
    - Loop (only when market is open):
      - For each symbol:
        - Fetch LTP from NFO.
        - Run strategy to get signal.
        - Record every signal (with strategy tag in 'logical').
        - If BUY/SELL:
          - Check capital / notional constraints.
          - Enforce per-symbol loss limit ("kill switch").
          - Place order via ExecutionRouter (PAPER by default).
          - Record order.
      - Enforce per-trade max loss (stop-loss per position).
      - Periodically snapshot paper broker state, including P&L metrics.
      - Enforce global and per-symbol risk checks.
    """

    def _init_trade_flow_state(self) -> Dict[str, Any]:
        return {
            "signals_total": 0,
            "signals_actionable": 0,
            "risk_blocks": 0,
            "time_blocks": 0,
            "orders_submitted": 0,
            "orders_filled": 0,
            "stop_hits": 0,
            "target_hits": 0,
            "last_events": {},
            "risk_block_reasons": {},
            "time_block_reasons": {},
        }

    @staticmethod
    def _trade_flow_timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _record_trade_flow_event(
        self,
        key: str,
        *,
        reason: Optional[str] = None,
        bucket: Optional[str] = None,
    ) -> None:
        if not hasattr(self, "trade_flow_state") or self.trade_flow_state is None:
            return
        state = self.trade_flow_state
        state[key] = int(state.get(key, 0)) + 1
        last_events = state.setdefault("last_events", {})
        last_events[key] = self._trade_flow_timestamp()
        if bucket and reason:
            reason_key = "risk_block_reasons" if bucket == "risk" else "time_block_reasons"
            bucket_map = state.setdefault(reason_key, {})
            bucket_map[reason] = int(bucket_map.get(reason, 0)) + 1

    def _trade_flow_snapshot(self) -> Dict[str, Any]:
        state = self.trade_flow_state or {}
        snapshot = {
            "signals_total": int(state.get("signals_total", 0)),
            "signals_actionable": int(state.get("signals_actionable", 0)),
            "risk_blocks": int(state.get("risk_blocks", 0)),
            "time_blocks": int(state.get("time_blocks", 0)),
            "orders_submitted": int(state.get("orders_submitted", 0)),
            "orders_filled": int(state.get("orders_filled", 0)),
            "stop_hits": int(state.get("stop_hits", 0)),
            "target_hits": int(state.get("target_hits", 0)),
            "last_events": dict(state.get("last_events", {})),
            "risk_block_reasons": dict(state.get("risk_block_reasons", {})),
            "time_block_reasons": dict(state.get("time_block_reasons", {})),
        }
        return snapshot

    def __init__(
        self,
        cfg: AppConfig,
        journal_store: Optional[JournalStateStore] = None,
        checkpoint_store: Optional[StateStore] = None,
        kite: Optional[KiteConnect] = None,
        cost_model: Optional[CostModel] = None,
        trade_quality_filter: Optional[TradeQualityFilter] = None,
        *,
        trading_mode: Optional[TradingMode] = None,
        artifacts_dir: Optional[Path] = None,
        data_feed: Optional[BrokerFeed] = None,
        logical_universe_override: Optional[List[str]] = None,
        symbol_map_override: Optional[Dict[str, str]] = None,
        execution_engine_v2: Any = None,
    ) -> None:
        self.cfg = cfg
        cfg_mode = self.cfg.trading.get("mode", TradingMode.PAPER.value)
        
        # Normalize mode to handle both enum instances and strings (case-insensitive)
        mode_raw = trading_mode or cfg_mode
        if isinstance(mode_raw, TradingMode):
            self.mode = mode_raw
        else:
            # Normalize string to lowercase to match enum values
            mode_str = str(mode_raw).strip().lower()
            self.mode = TradingMode(mode_str)

        # Broker + router
        self.paper_broker = PaperBroker()
        # Execution router used for all order placement in paper mode
        self.router = ExecutionRouter(
            mode=self.mode,
            paper_broker=self.paper_broker,
        )

        # Market data feed (shared Kite client)
        self.kite = kite
        self.feed = data_feed or (BrokerFeed(self.kite) if self.kite else None)
        if self.feed is None:
            raise RuntimeError("PaperEngine requires a Kite client or provided data_feed for market data.")

        # Ensure logical_universe always exists before later checks
        self.logical_universe: List[str] = []
        trading = getattr(cfg, "trading", None) or {}
        lu = (
            trading.get("logical_universe")
            or trading.get("universe")
            or []
        )
        if isinstance(lu, str):
            lu = [lu]
        self.logical_universe = [str(x).strip() for x in lu if x]

        # Strategy metadata
        self.strategy_name = str(getattr(FnoIntradayTrendStrategy, "name", "UNKNOWN"))
        self.strategy_mode = str(getattr(FnoIntradayTrendStrategy, "mode", "UNKNOWN"))
        self.primary_strategy_code = self._resolve_primary_strategy_code()
        self.strategy_metrics = StrategyMetricsTracker(default_code=self.primary_strategy_code)
        self.recorder = TradeRecorder()

        # Multi-timeframe configuration (per logical symbol)
        raw_multi_tf = self.cfg.trading.get("multi_tf_config")
        overrides = raw_multi_tf if isinstance(raw_multi_tf, dict) else None
        self.multi_tf_config = resolve_multi_tf_config(overrides)
        self.default_timeframe = (
            next(iter(self.multi_tf_config.values()), ["5m"])[0]
            if self.multi_tf_config
            else str(getattr(FnoIntradayTrendStrategy, "timeframe", "5m"))
        )
        self.strategy_instances: List[FnoIntradayTrendStrategy] = []
        self.strategies_by_logical: Dict[str, List[FnoIntradayTrendStrategy]] = {}
        self.regime_detector = shared_regime_detector
        if self.logical_universe:
            self.regime_detector.set_primary_symbol(self.logical_universe[0])
        self._last_regime_value: str = Regime.UNKNOWN.value

        # Logical universe from config or default (NIFTY/BANKNIFTY/FINNIFTY)
        cfg_fno = self.cfg.trading.get("fno_universe", []) or []
        logical_universe: List[str] = (
            [str(sym).strip().upper() for sym in cfg_fno if sym] or fno_underlyings()
        )
        if logical_universe_override:
            logical_universe = [
                str(sym).strip().upper() for sym in logical_universe_override if sym
            ]
        self.logical_universe = logical_universe
        logger.info("Logical FnO universe: %s", logical_universe)

        # Resolve to current FUT symbols
        if symbol_map_override is not None:
            self.symbol_map = {
                str(k).strip().upper(): str(v).strip().upper()
                for k, v in symbol_map_override.items()
            }
        else:
            if self.kite is None:
                raise RuntimeError(
                    "FnO symbol resolution requires a Kite client or an explicit symbol map override."
                )
            # Shim to match resolve_fno_symbols(kite_client=...) expectation
            shim = SimpleNamespace(api=self.kite)
            self.symbol_map = resolve_fno_symbols(logical_universe, kite_client=shim)

        self.universe: List[str] = list(self.symbol_map.values())  # actual tradingsymbols
        self.logical_alias: Dict[str, str] = {
            v: k for k, v in self.symbol_map.items()
        }

        logger.info("Resolved FnO universe: %s", self.symbol_map)

        # Build strategies per logical symbol / timeframe
        self.strategy_instances = self._build_strategy_instances()

        self.sleep_sec = 5
        self.fno_exchange = "NFO"

        # Risk + capital
        self.paper_capital: float = float(
            self.cfg.trading.get("paper_capital", 500000)
        )
        self.max_daily_loss: float = float(
            self.cfg.trading.get("max_daily_loss", 3000)
        )
        self.per_symbol_max_loss: float = float(
            self.cfg.trading.get(
                "per_symbol_max_loss", self.max_daily_loss
            )
        )
        self.max_loss_pct_per_trade: float = float(
            self.cfg.trading.get("max_loss_pct_per_trade", 0.01)
        )

        self.running = True

        # How often to snapshot broker state (in loops)
        self.snapshot_every_n_loops = 5
        self._loop_counter = 0

        # Last known prices for unrealized P&L
        self.last_prices: Dict[str, float] = {}

        # Per-symbol kill switch state
        self.banned_symbols: set[str] = set()

        # Trailing stop configuration/state
        self.trailing_state: Dict[str, Dict[str, float]] = {}
        self.enable_trailing_stops: bool = bool(
            self.cfg.trading.get("enable_trailing_stops", True)
        )
        self.trail_start_r: float = float(
            self.cfg.trading.get("trail_start_r_multiple", 1.0)
        )
        self.trail_step_r: float = float(
            self.cfg.trading.get("trail_step_r_multiple", 0.5)
        )
        self.trail_lock_r: float = float(
            self.cfg.trading.get("trail_lock_r_multiple", 0.5)
        )

        self.active_trades: Dict[str, ActiveTrade] = {}
        self.last_signal_ids: Dict[str, str] = {}
        self.trade_flow_state: Dict[str, Any] = self._init_trade_flow_state()

        # Artifacts/state paths
        self.artifacts_dir = Path(artifacts_dir).resolve() if artifacts_dir else ARTIFACTS_DIR
        self.state_path = self.artifacts_dir / "paper_state.json"
        if journal_store is None:
            journal_store = JournalStateStore(mode="paper", artifacts_dir=self.artifacts_dir)
        self.journal = journal_store
        if checkpoint_store is None:
            checkpoint_path = getattr(self.journal, "checkpoint_path", None)
            checkpoint_store = StateStore(checkpoint_path=checkpoint_path)
        self.state_store = checkpoint_store
        self.equity_snapshot_interval_sec = int(self.cfg.trading.get("equity_snapshot_interval_sec", 60))
        self._last_equity_snapshot_ts = 0.0
        self._order_sequence = 0

        risk_cfg_raw = self.cfg.risk_engine or {}
        self.risk_engine_cfg: Optional[RiskConfig] = build_risk_config(risk_cfg_raw) if risk_cfg_raw else None

        risk_section = self.cfg.risk or {}
        atr_section = risk_section.get("atr") or {}
        self.atr_config = ATRConfig(
            enabled=bool(atr_section.get("enabled", True)),
            lookback=int(atr_section.get("lookback", 14)),
            sl_r_multiple=float(atr_section.get("sl_r_multiple", 1.0)),
            tp_r_multiple=float(atr_section.get("tp_r_multiple", 2.0)),
            hard_sl_pct_cap=float(atr_section.get("hard_sl_pct_cap", 0.03)),
            hard_tp_pct_cap=float(atr_section.get("hard_tp_pct_cap", 0.06)),
            min_atr_value=float(atr_section.get("min_atr_value", 0.5)),
            per_product=atr_section.get("per_product"),
        )
        time_section = risk_section.get("time_filter") or {}
        self.time_filter_config = TimeFilterConfig(
            enabled=bool(time_section.get("enabled", False)),
            allow_sessions=time_section.get("allow_sessions"),
            block_expiry_scalps_after=time_section.get("block_expiry_scalps_after"),
            min_time=time_section.get("min_time"),
            max_time=time_section.get("max_time"),
        )

        learning_cfg = self.cfg.learning_engine or {}
        self.learning_enabled = bool(learning_cfg.get("enabled"))
        default_learning_path = self.artifacts_dir / "learning" / "strategy_tuning.json"
        tuning_path_raw = learning_cfg.get("tuning_path", default_learning_path)
        tuning_path = Path(tuning_path_raw)
        if not tuning_path.is_absolute():
            tuning_path = (BASE_DIR / tuning_path).resolve()
        self.learning_tuning_path = tuning_path
        self.learning_min_multiplier = float(learning_cfg.get("min_risk_multiplier", 0.25))
        self.learning_max_multiplier = float(learning_cfg.get("max_risk_multiplier", 2.0))
        self.learning_tuning = self._load_learning_tuning() if self.learning_enabled else {}

        # Dynamic position sizing
        self.sizer_config = self._build_sizer_config()
        self.signal_quality = signal_quality_manager
        self.position_sizer = DynamicPositionSizer(self.sizer_config)
        self.default_lot_size = int(self.cfg.trading.get("default_lot_size", 1))

        journal_root = self.artifacts_dir / "journal"
        self.adaptive_risk = AdaptiveRiskManager(journal_root=journal_root)
        adj = self.adaptive_risk.recommend(date.today())
        self.sizer_config.risk_per_trade_pct *= adj.risk_per_trade_scale
        self.sizer_config.max_exposure_pct *= adj.max_exposure_scale
        scaled_lot = int(round(self.default_lot_size * adj.lot_size_scale))
        self.default_lot_size = max(1, scaled_lot)
        logger.info(
            "Adaptive risk mode=%s risk_scale=%.2f lot_scale=%.2f reason=%s",
            adj.mode,
            adj.risk_per_trade_scale,
            adj.lot_size_scale,
            adj.reason,
        )

        # Meta-strategy / multi-timeframe engine
        self.meta_cfg = self.cfg.meta
        self.meta_enabled = bool(self.meta_cfg.get("enabled", True))
        if self.mode == TradingMode.REPLAY:
            self.meta_enabled = False
        self.meta_engine: Optional[MetaStrategyEngine] = None
        self.multi_tf_engine: Optional[MultiTimeframeEngine] = None
        self._last_meta_decisions: Dict[str, Optional[MetaDecision]] = {}
        if self.meta_enabled:
            meta_symbols = set(self.universe)
            focus = self.meta_cfg.get("symbols_focus", [])
            for item in focus:
                if not isinstance(item, str):
                    continue
                token = item.strip().upper()
                for sym, base in self.logical_alias.items():
                    if token in base.upper() or token in sym:
                        meta_symbols.add(sym)
            self.multi_tf_engine = MultiTimeframeEngine(
                symbols=meta_symbols,
                signals_path=self.artifacts_dir / "signals.csv",
            )
            self.meta_engine = MetaStrategyEngine(
                multi_engine=self.multi_tf_engine,
                config=self.meta_cfg,
            )

        # Cost model + trade quality / edge filtering
        risk_cfg = self.cfg.risk
        self.cost_model: Optional[CostModel] = (
            cost_model if cost_model is not None else build_cost_model(self.cfg.raw)
        )
        self.trade_quality_filter: Optional[TradeQualityFilter] = (
            trade_quality_filter
            if trade_quality_filter is not None
            else build_trade_quality_filter(self.cfg.raw)
        )
        self.default_raw_edge_bps = float(risk_cfg.get("default_raw_edge_bps", 20.0))
        throttler_raw = self.cfg.trading.get("trade_throttler")
        throttler_config = build_throttler_config(throttler_raw)
        self.trade_throttler = TradeThrottler(
            config=throttler_config,
            capital=self.paper_capital,
        )
        universe_snapshot = load_universe()
        cache_dir = self.artifacts_dir / "market_data"
        self.market_data_engine = MarketDataEngine(self.kite, universe_snapshot, cache_dir=cache_dir)
        
        # Initialize Market Data Engine v2 (optional, based on config)
        data_config = self.cfg.raw.get("data", {})
        use_mde_v2 = data_config.get("use_mde_v2", False)
        self.market_data_engine_v2 = None
        
        if use_mde_v2:
            try:
                from core.market_data_engine_v2 import MarketDataEngineV2
                
                # Get universe metadata from scanner
                universe_meta = universe_snapshot.get("meta", {}) if isinstance(universe_snapshot, dict) else {}
                
                logger.info(
                    "MarketDataEngineV2 enabled for FnO engine with symbols: %s",
                    self.universe
                )
                
                # Initialize MDE v2 with proper parameters
                self.market_data_engine_v2 = MarketDataEngineV2(
                    cfg=data_config,
                    kite=self.kite,
                    universe=self.universe,
                    meta=universe_meta,
                    logger_instance=logger,
                )
                
                # Start the engine
                self.market_data_engine_v2.start()
                logger.info("Market Data Engine v2 started successfully")
            except Exception as exc:
                logger.warning("Failed to initialize MDE v2: %s", exc, exc_info=True)
                self.market_data_engine_v2 = None
        
        # Initialize ExecutionEngine v2 (optional)
        self.execution_engine_v2 = execution_engine_v2
        self.execution_engine_v3 = None
        
        if self.execution_engine_v2 is None:
            exec_config = self.cfg.raw.get("execution", {})
            engine_version = exec_config.get("engine", "v2")
            
            # Initialize ExecutionEngine V3 if configured
            if engine_version == "v3":
                try:
                    from engine.execution_v3_integration import create_execution_engine_v3
                    logger.info("Initializing ExecutionEngine V3 for paper mode")
                    self.execution_engine_v3 = create_execution_engine_v3(
                        config=self.cfg.raw,
                        market_data_engine=self.feed,
                        trade_recorder=self.recorder,
                        state_store=self.state_store,
                    )
                    if self.execution_engine_v3:
                        logger.info("ExecutionEngine V3 initialized successfully")
                except Exception as exc:
                    logger.warning("Failed to initialize ExecutionEngine V3: %s", exc)
                    self.execution_engine_v3 = None
            
            # Fall back to ExecutionEngine v2 if V3 not enabled/available
            use_exec_v2 = exec_config.get("use_execution_engine_v2", False)
            if use_exec_v2 and self.execution_engine_v3 is None:
                try:
                    from engine.execution_bridge import create_execution_engine_v2
                    logger.info("Initializing ExecutionEngine v2 for paper mode")
                    self.execution_engine_v2 = create_execution_engine_v2(
                        mode="paper",
                        broker=None,
                        state_store=self.state_store,
                        journal_store=self.journal,
                        trade_throttler=self.trade_throttler,
                        config=self.cfg.raw,
                        mde=self.market_data_engine_v2,
                    )
                except Exception as exc:
                    logger.warning("Failed to initialize ExecutionEngine v2: %s", exc)
                    self.execution_engine_v2 = None
        
        # Initialize Trade Guardian v1 (optional, for legacy path when ExecutionEngine v2 not used)
        self.guardian = None
        try:
            from core.trade_guardian import TradeGuardian
            # Use self.state_store instead of self.checkpoint_store which doesn't exist
            self.guardian = TradeGuardian(self.cfg.raw, self.state_store, logger)
        except Exception as exc:
            logger.warning("Failed to initialize TradeGuardian: %s", exc)
        
        # Initialize PortfolioEngine v1 (optional, based on config)
        self.portfolio_engine = None
        portfolio_config_raw = self.cfg.raw.get("portfolio")
        if portfolio_config_raw:
            try:
                logger.info("Initializing PortfolioEngine v1")
                portfolio_config = PortfolioConfig.from_dict(portfolio_config_raw)
                self.portfolio_engine = PortfolioEngine(
                    portfolio_config=portfolio_config,
                    state_store=self.state_store,
                    journal_store=self.journal,
                    logger_instance=logger,
                    mde=self.market_data_engine_v2,
                )
                logger.info(
                    "PortfolioEngine v1 initialized: mode=%s, max_exposure_pct=%.2f",
                    portfolio_config.position_sizing_mode,
                    portfolio_config.max_exposure_pct,
                )
            except Exception as exc:
                logger.warning("Failed to initialize PortfolioEngine v1: %s", exc, exc_info=True)
                self.portfolio_engine = None
        
        # Initialize Strategy Engine (v1, v2, or v3 based on config)
        # Normalize strategy_engine_config - handle None/null values
        strategy_engine_config = self.cfg.raw.get("strategy_engine")
        if strategy_engine_config is None:
            logger.warning("No strategy_engine config provided, v2 strategies will not be registered")
            strategy_engine_config = {}
        self.strategy_engine_config = strategy_engine_config
        
        strategy_engine_version = strategy_engine_config.get("version", 1)
        strategy_engine_mode = strategy_engine_config.get("mode", "").lower()  # Can be "v3" to force v3
        
        # Check if v3 mode is explicitly requested
        use_v3 = (strategy_engine_mode == "v3") or (strategy_engine_version == 3)
        
        if use_v3:
            # Initialize Strategy Engine v3
            try:
                from core.strategy_engine_v3 import StrategyEngineV3
                from services.common.event_bus import InMemoryEventBus
                
                logger.info("Initializing Strategy Engine v3")
                
                # Load v3 configuration
                v3_config = self.cfg.raw.get("strategy_engine_v3", {})
                if not v3_config:
                    logger.warning("strategy_engine_v3 config not found, using defaults")
                    v3_config = {
                        "primary_tf": "5m",
                        "secondary_tf": "15m",
                        "strategies": []
                    }
                
                # Create EventBus if not provided
                event_bus = InMemoryEventBus()
                event_bus.start()
                
                self.strategy_engine_v3 = StrategyEngineV3(v3_config, bus=event_bus)
                self.strategy_engine_v2 = None
                self.strategy_runner = None
                
                logger.info(
                    "Strategy Engine v3 initialized with %d strategies",
                    len(self.strategy_engine_v3.strategies)
                )
                
            except ImportError as e:
                logger.error("Failed to import Strategy Engine v3: %s", e)
                logger.info("Falling back to v1")
                use_v3 = False
            except Exception as e:
                logger.error("Failed to initialize Strategy Engine v3: %s", e, exc_info=True)
                logger.info("Falling back to v1")
                use_v3 = False
        
        if not use_v3:
            if strategy_engine_version == 2 and STRATEGY_ENGINE_V2_AVAILABLE:
                # Initialize Strategy Engine v2 using from_config
                logger.info("Initializing Strategy Engine v2 from config")
                
                try:
                    self.strategy_engine_v2 = StrategyEngineV2.from_config(self.cfg.raw, logger)
                    self.strategy_engine_v2.set_paper_engine(self)
                    
                    # Set additional engines
                    self.strategy_engine_v2.mde = self.market_data_engine
                    self.strategy_engine_v2.market_data = self.market_data_engine
                    self.strategy_engine_v2.market_data_engine = self.market_data_engine
                    self.strategy_engine_v2.market_data_v2 = self.market_data_engine_v2
                    self.strategy_engine_v2.portfolio_engine = self.portfolio_engine
                    self.strategy_engine_v2.regime_engine = self.regime_detector
                    self.strategy_engine_v2.state_store = self.state_store
                    
                    # Wire MDE v2 candle close events to strategy engine
                    if self.market_data_engine_v2:
                        self.market_data_engine_v2.on_candle_close_handlers.append(
                            self.strategy_engine_v2.on_candle_close
                        )
                        logger.info("Wired MDE v2 candle_close events to StrategyEngineV2")
                    
                    self.strategy_runner = None  # Disable v1 when using v2
                    self.strategy_engine_v3 = None  # Disable v3 when using v2
                    logger.info(
                        "Strategy Engine v2 initialized with %d strategies",
                        len(self.strategy_engine_v2.strategies)
                    )
                    
                    # Initialize MarketContext if enabled
                    self.market_context = None
                    self._market_context_thread = None
                    self._market_context_stop = threading.Event()
                    
                    if MARKET_CONTEXT_AVAILABLE:
                        mc_config = self.cfg.raw.get("market_context", {})
                        if mc_config.get("enabled", False):
                            try:
                                self.market_context = initialize_market_context(
                                    config=self.cfg.raw,
                                    kite_client=self.kite,
                                    market_data_engine=self.market_data_engine,
                                )
                                
                                # Set as global context for API access
                                from core.market_context import set_market_context
                                set_market_context(self.market_context)
                                
                                # Pass market context to strategy engine
                                self.strategy_engine_v2.market_context = self.market_context
                                
                                # Start background refresh thread
                                self._start_market_context_refresh()
                                
                                logger.info("MarketContext initialized and enabled with background refresh")
                            except Exception as exc:
                                logger.warning("Failed to initialize MarketContext: %s", exc)
                                self.market_context = None
                        else:
                            logger.info("MarketContext disabled in config")
                            self.market_context = None
                    else:
                        logger.debug("MarketContext module not available")
                        self.market_context = None
                        
                except Exception as exc:
                    logger.error("Failed to initialize Strategy Engine v2: %s", exc, exc_info=True)
                    logger.info("Falling back to v1")
                    self.strategy_engine_v2 = None
            else:
                # Use legacy Strategy Engine v1
                if strategy_engine_version == 2:
                    logger.warning("Strategy Engine v2 requested but not available, falling back to v1")
                logger.info("Using Strategy Engine v1 (legacy)")
                self.strategy_runner = StrategyRunner(
                    self.state_store,
                    self,
                    market_data_engine=self.market_data_engine,
                )
                self.strategy_engine_v2 = None
                self.strategy_engine_v3 = None
        
        risk_config = self.cfg.risk or {}
        self.risk_engine = RiskEngine(risk_config, self.state_store.load_checkpoint() or {}, logger)
        
        # Initialize Expiry Risk Adapter
        try:
            from core.expiry_risk_adapter import create_expiry_risk_adapter_from_config
            self.expiry_risk_adapter = create_expiry_risk_adapter_from_config(self.cfg.raw)
            logger.info("Expiry Risk Adapter initialized (enabled=%s)", self.expiry_risk_adapter.config.enabled)
        except Exception as exc:
            logger.warning("Failed to initialize Expiry Risk Adapter: %s. Continuing without expiry awareness.", exc)
            self.expiry_risk_adapter = None
        
        # Initialize Paper Account Manager for reset rules
        try:
            from core.account_manager import PaperAccountManager
            paper_account_config = self.cfg.raw.get("paper_account", {})
            starting_capital = float(paper_account_config.get("starting_capital", self.paper_capital))
            max_drawdown_reset = float(paper_account_config.get("max_drawdown_reset", 50000.0))
            
            self.account_manager = PaperAccountManager(
                artifacts_dir=self.artifacts_dir,
                starting_capital=starting_capital,
                max_drawdown_reset=max_drawdown_reset,
            )
            
            # Check if account should be reset based on yesterday's performance
            if self.account_manager.should_reset_for_today():
                logger.warning("Paper account reset triggered due to yesterday's drawdown")
                self._reset_paper_account()
            else:
                logger.info("Paper account continuing from existing state")
        except Exception as exc:
            logger.warning("Failed to initialize PaperAccountManager: %s. Continuing without reset logic.", exc)
            self.account_manager = None

    # -------------------------------------------------------------------------
    # MarketContext Management
    # -------------------------------------------------------------------------
    
    def _start_market_context_refresh(self) -> None:
        """Start background thread for periodic market context refresh."""
        if self.market_context is None:
            return
        
        self._market_context_stop.clear()
        self._market_context_thread = threading.Thread(
            target=self._market_context_refresh_loop,
            name="market-context-refresh",
            daemon=True
        )
        self._market_context_thread.start()
        logger.info("MarketContext refresh thread started (30s interval)")
    
    def _market_context_refresh_loop(self) -> None:
        """Background loop that refreshes market context every 30 seconds."""
        while not self._market_context_stop.is_set():
            try:
                if self.market_context is not None:
                    self.market_context.refresh()
            except Exception as exc:
                logger.error("MarketContext refresh error: %s", exc, exc_info=True)
            
            # Wait 30 seconds before next refresh
            self._market_context_stop.wait(30.0)
    
    def _stop_market_context_refresh(self) -> None:
        """Stop the market context refresh thread."""
        if self._market_context_thread and self._market_context_thread.is_alive():
            self._market_context_stop.set()
            self._market_context_thread.join(timeout=5.0)
            logger.info("MarketContext refresh thread stopped")

    # -------------------------------------------------------------------------
    # Paper Account Reset
    # -------------------------------------------------------------------------
    
    def _reset_paper_account(self) -> None:
        """
        Reset the paper account to configured starting capital.
        
        This method:
        - Calls account_manager.reset_paper_account() to reset checkpoint
        - Clears the paper broker state
        - Resets active trades and trailing states
        - Optionally clears stale checkpoints
        """
        if not self.account_manager:
            logger.warning("Cannot reset paper account: account_manager not initialized")
            return
        
        try:
            # Reset checkpoint via account manager
            checkpoint_path = self.state_path
            self.account_manager.reset_paper_account(
                checkpoint_path=checkpoint_path,
                reason="drawdown_threshold",
            )
            
            # Reset paper broker state
            self.paper_broker = PaperBroker()
            self.router = ExecutionRouter(
                mode=self.mode,
                paper_broker=self.paper_broker,
            )
            
            # Clear active trades and trailing states
            self.active_trades.clear()
            self.trailing_state.clear()
            self.banned_symbols.clear()
            self.last_signal_ids.clear()
            
            # Reset capital to starting value
            paper_account_config = self.cfg.raw.get("paper_account", {})
            self.paper_capital = float(
                paper_account_config.get("starting_capital", 500000.0)
            )
            
            # Clear stale checkpoints (keep last 7 days)
            checkpoints_dir = self.artifacts_dir / "checkpoints"
            self.account_manager.clear_stale_checkpoints(
                checkpoints_dir=checkpoints_dir,
                keep_days=7,
            )
            
            logger.info("Paper account reset completed successfully")
            
        except Exception as exc:
            logger.error("Failed to reset paper account: %s", exc, exc_info=True)
            raise

    # -------------------------------------------------------------------------
    # Strategy instances
    # -------------------------------------------------------------------------

    def _build_strategy_instances(self) -> List[FnoIntradayTrendStrategy]:
        instances: List[FnoIntradayTrendStrategy] = []
        self.strategies_by_logical = {}
        if not getattr(self, "logical_universe", None):
            return instances

        for logical in self.logical_universe:
            per_symbol: List[FnoIntradayTrendStrategy] = []
            for tf in self.multi_tf_config.get(logical, []):
                timeframe = str(tf or self.default_timeframe)
                mode = self.strategy_mode
                strat = FnoIntradayTrendStrategy(timeframe=timeframe)
                strat.logical = logical
                strat.timeframe = timeframe
                strat.mode = mode
                instances.append(strat)
                per_symbol.append(strat)
            self.strategies_by_logical[logical] = per_symbol
        return instances

    def _ensure_decision(
        self,
        strat: FnoIntradayTrendStrategy,
        raw: Decision | str | None,
    ) -> Decision:
        if isinstance(raw, Decision):
            mode = raw.mode or getattr(strat, "mode", self.strategy_mode)
            confidence = float(raw.confidence or 0.0)
            action = raw.action or "HOLD"
            reason = raw.reason or ""
            return Decision(
                action=action,
                reason=reason,
                mode=mode,
                confidence=confidence,
            )

        action = str(raw or "HOLD").upper()
        if action not in {"BUY", "SELL", "EXIT", "HOLD"}:
            action = "HOLD"
        return Decision(
            action=action,
            reason="",
            mode=getattr(strat, "mode", self.strategy_mode),
            confidence=0.0,
        )

    def _resolve_timeframe(self, preferred: Optional[str] = None) -> str:
        tf = preferred or self.default_timeframe
        return tf or "5m"

    def _resolve_primary_strategy_code(self) -> str:
        trading_section = getattr(self.cfg, "trading", {}) or {}
        preferred = trading_section.get("primary_strategy_code")
        if isinstance(preferred, str) and preferred.strip():
            return preferred.strip()
        for code, info in STRATEGY_REGISTRY.items():
            if info.enabled:
                return code
        return next(iter(STRATEGY_REGISTRY.keys()), "ema20_50_intraday")

    @staticmethod
    def _strategy_name_from_code(strategy_code: Optional[str]) -> Optional[str]:
        if not strategy_code:
            return None
        info = STRATEGY_REGISTRY.get(strategy_code)
        return info.name if info else None

    def _lookup_strategy_code(self, symbol: str) -> Optional[str]:
        trade = self.active_trades.get(symbol)
        if trade:
            meta = getattr(trade, "meta", {}) or {}
            code = meta.get("strategy_code")
            if code:
                return code
        return self.strategy_metrics.infer(symbol)

    def _record_regime_sample(self, logical_symbol: str, price: float) -> None:
        if not self.regime_detector or not logical_symbol or price is None or price <= 0:
            return
        try:
            self.regime_detector.update(symbol=logical_symbol, close=float(price))
            self._last_regime_value = self.regime_detector.current_regime()
        except Exception as exc:  # noqa: BLE001
            logger.debug("Regime detector update failed for %s: %s", logical_symbol, exc)

    # -------------------------------------------------------------------------
    # Main loop
    # -------------------------------------------------------------------------

    def run_forever(self) -> None:
        if not self.universe:
            logger.error(
                "No resolved FnO symbols to trade. Check config and instrument permissions."
            )
            publish_engine_health(
                "paper_engine",
                "error",
                {"mode": self.mode.value, "error": "no_universe"}
            )
            return

        logger.info(
            "Starting PaperEngine with tradingsymbol universe: %s (mode=%s)",
            self.universe,
            self.mode.value,
        )
        # Publish engine startup telemetry
        publish_engine_health(
            "paper_engine",
            "starting",
            {
                "mode": self.mode.value,
                "universe_size": len(self.universe),
                "strategy_name": self.strategy_name,
            }
        )
        
        try:
            while self.running:
                if not is_market_open():
                    logger.info(
                        "Market appears closed (PaperEngine); sleeping..."
                    )
                    time.sleep(self.sleep_sec)
                    continue

                self._loop_once()
                time.sleep(self.sleep_sec)
        except Exception as exc:
            logger.error("PaperEngine error: %s", exc, exc_info=True)
            publish_engine_health(
                "paper_engine",
                "error",
                {"mode": self.mode.value, "error": str(exc)}
            )
            raise
        finally:
            # Stop MDE v2 if running
            if self.market_data_engine_v2:
                try:
                    self.market_data_engine_v2.stop()
                    logger.info("Market Data Engine v2 stopped")
                except Exception as exc:
                    logger.warning("Error stopping MDE v2: %s", exc)
            
            # Publish engine shutdown telemetry
            publish_engine_health(
                "paper_engine",
                "stopped",
                {"mode": self.mode.value}
            )

    def _loop_once(self) -> None:
        self._loop_counter += 1

        price_cache: Dict[str, float | None] = {}

        def _ltp(symbol: str) -> float | None:
            if symbol not in price_cache:
                price = self.feed.get_ltp(symbol, exchange=self.fno_exchange)
                price_cache[symbol] = price
                if price is not None:
                    self.last_prices[symbol] = price
            return price_cache[symbol]

        # Update market data cache for all symbols before strategies run
        if self.market_data_engine:
            for symbol in self.universe:
                try:
                    # Determine timeframe - use default or symbol-specific
                    logical = self.logical_alias.get(symbol, symbol)
                    timeframes = self.multi_tf_config.get(logical, [self.default_timeframe])
                    tf = timeframes[0] if timeframes else self.default_timeframe
                    self.market_data_engine.update_cache(symbol, tf)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Market data cache update failed for %s: %s", symbol, exc)

        ticks = {}
        for symbol in self.universe:
            ltp = _ltp(symbol)
            if ltp is not None:
                ticks[symbol] = {"close": ltp}
                
                # Feed ticks to MDE v2 if available
                if self.market_data_engine_v2:
                    # Get instrument token for this symbol
                    token = self.market_data_engine_v2.symbol_tokens.get(symbol.upper())
                    if token:
                        tick_data = {
                            "instrument_token": token,
                            "last_price": ltp,
                            "timestamp": datetime.now(timezone.utc),
                        }
                        try:
                            self.market_data_engine_v2.on_tick_batch([tick_data])
                        except Exception as exc:  # noqa: BLE001
                            logger.debug("MDE v2 tick processing failed for %s: %s", symbol, exc)
        
        # Update ExecutionEngine V3 positions with latest prices
        if self.execution_engine_v3 is not None:
            try:
                tick_prices = {sym: data.get("close") for sym, data in ticks.items() if data.get("close")}
                if tick_prices:
                    self.execution_engine_v3.update_positions(tick_prices)
                    # Update trade lifecycle (SL/TP/trailing/time-stop checks)
                    self.execution_engine_v3.update_trade_lifecycle()
            except Exception as exc:  # noqa: BLE001
                logger.debug("ExecutionEngine V3 position update failed: %s", exc)

        # Run strategy engine (v1, v2, or v3 based on initialization)
        if hasattr(self, 'strategy_engine_v3') and self.strategy_engine_v3:
            # Use Strategy Engine v3
            for symbol in self.universe:
                logical = self.logical_alias.get(symbol, symbol)
                ltp = ticks.get(symbol, {}).get("close")
                
                if ltp is None:
                    continue
                
                # Prepare market data for v3
                # Get primary and secondary timeframe series
                primary_tf = self.strategy_engine_v3.primary_tf
                secondary_tf = self.strategy_engine_v3.secondary_tf
                
                # Fetch primary series
                primary_window = self.market_data_engine.get_window(symbol, primary_tf, 200)
                primary_series = {}
                if primary_window and len(primary_window) >= 20:
                    primary_series = {
                        "open": [c["open"] for c in primary_window],
                        "high": [c["high"] for c in primary_window],
                        "low": [c["low"] for c in primary_window],
                        "close": [c["close"] for c in primary_window],
                        "volume": [c.get("volume", 0) for c in primary_window],
                    }
                
                # Fetch secondary series
                secondary_window = self.market_data_engine.get_window(symbol, secondary_tf, 200)
                secondary_series = {}
                if secondary_window and len(secondary_window) >= 20:
                    secondary_series = {
                        "open": [c["open"] for c in secondary_window],
                        "high": [c["high"] for c in secondary_window],
                        "low": [c["low"] for c in secondary_window],
                        "close": [c["close"] for c in secondary_window],
                        "volume": [c.get("volume", 0) for c in secondary_window],
                    }
                
                # Prepare market data dict
                md = {
                    "primary_series": primary_series,
                    "secondary_series": secondary_series,
                }
                
                # Evaluate v3 engine
                try:
                    ts = datetime.now(timezone.utc).isoformat()
                    
                    intent = self.strategy_engine_v3.evaluate(symbol, ts, ltp, md)
                    
                    # Emit diagnostics for V3 engine (non-blocking, best-effort)
                    if intent:
                        try:
                            from analytics.diagnostics import build_diagnostic_record, append_diagnostic
                            
                            # Extract metadata
                            metadata = intent.metadata or {}
                            indicators = metadata.get("indicators", {})
                            
                            # Get indicator values
                            ema20 = indicators.get("ema20")
                            ema50 = indicators.get("ema50")
                            trend_strength = indicators.get("trend_strength")
                            
                            # Get regime if available
                            regime_label = indicators.get("regime")
                            
                            # Get RR if available
                            rr = indicators.get("rr") or indicators.get("risk_reward")
                            
                            # Determine risk block
                            risk_block = "none"
                            if intent.action == "HOLD":
                                reason_lower = intent.reason.lower()
                                if "loss" in reason_lower or "capital" in reason_lower:
                                    risk_block = "max_loss"
                                elif "cooldown" in reason_lower or "throttle" in reason_lower:
                                    risk_block = "cooldown"
                                elif "slippage" in reason_lower:
                                    risk_block = "slippage"
                            
                            # Build diagnostic record
                            diagnostic = build_diagnostic_record(
                                price=ltp,
                                decision=intent.action,
                                reason=intent.reason,
                                confidence=intent.confidence,
                                ema20=ema20,
                                ema50=ema50,
                                trend_strength=trend_strength,
                                rr=rr,
                                regime=regime_label,
                                risk_block=risk_block,
                                # Additional fields
                                strategy_id=intent.strategy_code,
                                timeframe=primary_tf,
                                setup=metadata.get("setup", ""),
                            )
                            
                            append_diagnostic(logical, intent.strategy_code, diagnostic)
                        except Exception as diag_exc:
                            # Never let diagnostics crash the engine
                            logger.debug("Diagnostics emission failed for %s: %s", symbol, diag_exc)
                    
                    # Process intent if not HOLD
                    if intent and intent.action != "HOLD":
                        # Extract metadata for logging
                        metadata = intent.metadata or {}
                        indicators = metadata.get("indicators", {})
                        
                        # Log the fused signal
                        self.recorder.log_fused_signal(
                            symbol=symbol,
                            price=ltp,
                            action=intent.action,
                            confidence=intent.confidence,
                            setup=metadata.get("setup", ""),
                            fuse_reason=metadata.get("fuse_reason", ""),
                            multi_tf_status=metadata.get("multi_tf_status", ""),
                            num_strategies=metadata.get("num_strategies", 0),
                            strategy_codes=metadata.get("strategy_codes", []),
                            indicators=indicators,
                        )
                        
                        # Call _handle_signal to execute the trade
                        self._handle_signal(
                            symbol=symbol,
                            signal=intent.action,
                            price=ltp,
                            logical=logical,
                            tf=primary_tf,
                            strategy_name=intent.strategy_code,
                            strategy_code=intent.strategy_code,
                            confidence=intent.confidence,
                            reason=intent.reason,
                            indicators=indicators,
                            playbook=metadata.get("setup", ""),
                        )
                except Exception as e:
                    logger.error("Strategy Engine v3 evaluation failed for %s: %s", symbol, e, exc_info=True)
        
        elif self.strategy_engine_v2:
            # Use Strategy Engine v2 with evaluate() method
            
            # Build MarketContext once per tick if available
            market_context = None
            if hasattr(self, "market_context_builder") and self.market_context_builder:
                try:
                    market_context = self.market_context_builder.build(symbols=self.universe)
                except Exception as exc:
                    logger.debug("Failed to build MarketContext: %s", exc)
                    market_context = None
            
            for symbol in self.universe:
                logical = self.logical_alias.get(symbol, symbol)
                ltp = ticks.get(symbol, {}).get("close")
                
                if ltp is None:
                    continue
                
                # Get timeframe
                timeframes = self.multi_tf_config.get(logical, [self.default_timeframe])
                tf = timeframes[0] if timeframes else self.default_timeframe
                
                # Fetch candle window from market data engine
                window = self.market_data_engine.get_window(symbol, tf, 200)
                
                if not window or len(window) < 20:
                    logger.debug("Insufficient candles for %s/%s: %d", symbol, tf, len(window) if window else 0)
                    continue
                
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
                
                # Compute indicators using the strategy engine
                indicators = self.strategy_engine_v2.compute_indicators(series, symbol=symbol, timeframe=tf)
                
                # Safety check: validate candle and indicators
                if not current_candle or current_candle.get("close") is None:
                    logger.debug("Invalid candle for %s, skipping", symbol)
                    continue
                
                if not indicators or indicators.get("ema20") is None or indicators.get("ema50") is None:
                    logger.debug("Indicators not ready for %s, skipping", symbol)
                    continue
                
                # Build expiry context for the underlying
                expiry_context = {}
                try:
                    from core.expiry_calendar import build_expiry_context
                    import pytz
                    
                    now_ist = datetime.now(pytz.timezone("Asia/Kolkata"))
                    expiry_context = build_expiry_context(logical, now_ist)
                except Exception as exc:
                    logger.debug("Failed to build expiry context for %s: %s", logical, exc)
                    expiry_context = {}
                
                # Merge with existing context
                full_context = {"ltp": ltp, **expiry_context}
                
                # Call evaluate with market_context and expiry context
                try:
                    intent, debug = self.strategy_engine_v2.evaluate(
                        logical=logical,
                        symbol=symbol,
                        timeframe=tf,
                        candle=current_candle,
                        indicators=indicators,
                        mode=self.mode.value,
                        profile=_profile_from_tf(tf),
                        context=full_context,
                        market_context=market_context,  # Pass MarketContext here
                    )
                    
                    # Emit diagnostics (non-blocking, best-effort)
                    try:
                        from analytics.diagnostics import build_diagnostic_record, append_diagnostic
                        
                        # Extract indicator values
                        ema20 = indicators.get("ema20")
                        ema50 = indicators.get("ema50")
                        trend_strength = debug.get("trend_strength")
                        
                        # Get regime info if available
                        regime_label = None
                        if market_context and hasattr(market_context, 'regime'):
                            regime_label = str(market_context.regime) if market_context.regime else None
                        
                        # Calculate risk:reward if available
                        rr = debug.get("rr") or debug.get("risk_reward")
                        
                        # Determine risk block reason
                        risk_block = "none"
                        if intent.signal == "HOLD":
                            # Check if it's a risk block
                            reason_lower = intent.reason.lower()
                            if "loss" in reason_lower or "capital" in reason_lower:
                                risk_block = "max_loss"
                            elif "cooldown" in reason_lower or "throttle" in reason_lower:
                                risk_block = "cooldown"
                            elif "slippage" in reason_lower:
                                risk_block = "slippage"
                        
                        # Build and append diagnostic record
                        diagnostic = build_diagnostic_record(
                            price=ltp,
                            decision=intent.signal,
                            reason=intent.reason,
                            confidence=intent.confidence,
                            ema20=ema20,
                            ema50=ema50,
                            trend_strength=trend_strength,
                            rr=rr,
                            regime=regime_label,
                            risk_block=risk_block,
                            # Additional fields
                            strategy_id=intent.strategy_id,
                            timeframe=tf,
                        )
                        
                        append_diagnostic(logical, intent.strategy_id, diagnostic)
                    except Exception as diag_exc:
                        # Never let diagnostics crash the engine
                        logger.debug("Diagnostics emission failed for %s: %s", symbol, diag_exc)
                    
                    # Always log the signal
                    self.recorder.log_signal(
                        logical=logical,
                        symbol=symbol,
                        price=ltp,
                        signal=intent.signal,
                        tf=tf,
                        reason=intent.reason,
                        profile=_profile_from_tf(tf),
                        mode=self.mode.value,
                        confidence=intent.confidence,
                        strategy=intent.strategy_id,
                        ema20=debug.get("indicators", {}).get("ema20"),
                        ema50=debug.get("indicators", {}).get("ema50"),
                        ema100=debug.get("indicators", {}).get("ema100"),
                        ema200=debug.get("indicators", {}).get("ema200"),
                        rsi14=debug.get("indicators", {}).get("rsi14"),
                        atr=debug.get("indicators", {}).get("atr"),
                    )
                    
                    # If HOLD, skip order placement
                    if intent.signal == "HOLD":
                        continue
                    
                    # Process non-HOLD signals through risk and execution
                    # Call _handle_signal to execute the trade
                    self._handle_signal(
                        symbol=symbol,
                        signal=intent.signal,
                        price=ltp,
                        logical=logical,
                        tf=tf,
                        strategy_name=intent.strategy_id,
                        strategy_code=intent.strategy_id,
                        confidence=intent.confidence,
                        reason=intent.reason,
                        indicators=debug.get("indicators", {}),
                    )
                    
                except Exception as exc:
                    logger.error(
                        "Strategy Engine v2 evaluation failed for %s: %s",
                        symbol, exc, exc_info=True
                    )
        elif self.strategy_runner:
            # Use Strategy Engine v1 (legacy)
            self.strategy_runner.run(ticks)

        # Enforce per-trade stop-loss on open positions
        self._enforce_per_trade_stop()
        self._enforce_trailing_stops()
        self._apply_risk_engine()
        self._enforce_trade_sl_tp()

        # Periodically snapshot paper broker state
        if self._loop_counter % self.snapshot_every_n_loops == 0:
            meta = self._compute_portfolio_meta()
            self._snapshot_state(meta, reason="loop_tick")

        # Risk checks (global + per-symbol)
        self._check_risk()

    # -------------------------------------------------------------------------
    # Order handling / trade filters
    # -------------------------------------------------------------------------

    def _handle_signal(
        self,
        symbol: str,
        signal: str,
        price: float,
        logical: Optional[str] = None,
        *,
        tf: str = "",
        profile: str = "",
        signal_timestamp: str = "",
        mode: str = "",
        strategy_name: Optional[str] = None,
        strategy_code: Optional[str] = None,
        confidence: Optional[float] = None,
        playbook: str = "",
        reason: str = "",
        indicators: Optional[Dict[str, Any]] = None,
        vol_regime: str = "",
        trend_context: str = "",
    ) -> None:
        tf = tf or self._resolve_timeframe()
        profile = profile or _profile_from_tf(tf)
        strategy_code_value = strategy_code or self.primary_strategy_code
        strategy_label = (
            strategy_name
            or self._strategy_name_from_code(strategy_code_value)
            or self.strategy_name
        )
        mode_label = mode or self.strategy_mode
        confidence_value = float(confidence) if confidence is not None else 0.0
        playbook_value = playbook or ""
        reason_value = reason or ""

        prev_position = self.paper_broker.get_position(symbol)
        prev_position_qty = prev_position.quantity if prev_position else 0

        if symbol in self.banned_symbols:
            logger.warning(
                "Not placing order for %s: symbol is banned by per-symbol loss limit.",
                symbol,
            )
            return
        if prev_position_qty == 0 and not self._check_time_filter(symbol, strategy_label, True):
            return

        portfolio_state = self._load_portfolio_state()
        
        # Use PortfolioEngine if available, otherwise fall back to legacy position_sizer
        if self.portfolio_engine is not None:
            # PortfolioEngine v1: compute position size
            # Create a mock intent object for the PortfolioEngine
            from types import SimpleNamespace
            intent = SimpleNamespace(
                symbol=symbol,
                strategy_code=strategy_code_value,
                side=signal,
                qty=None,  # Let PortfolioEngine determine qty
            )
            
            # Get ATR value if available (for ATR-based sizing)
            atr_value = None
            if indicators and "atr" in indicators:
                atr_value = float(indicators.get("atr", 0.0))
            
            qty = self.portfolio_engine.compute_position_size(
                intent=intent,
                last_price=price,
                atr_value=atr_value,
            )
            
            if qty == 0:
                logger.info(
                    "PortfolioEngine blocked order for %s: computed qty=0 (price=%.2f)",
                    symbol,
                    price,
                )
                return
        else:
            # Legacy position sizer
            qty = self.position_sizer.size_order(
                portfolio_state,
                symbol=symbol,
                last_price=price,
                side=signal,
                lot_size=self.default_lot_size,
            )

            if qty == 0:
                logger.info(
                    "Skipping %s order for %s: position sizer returned zero qty (price=%.2f, free_notional=%.2f).",
                    signal,
                    symbol,
                    price,
                    portfolio_state.free_notional,
                )
                return

        qty = self._apply_learning_adjustments(symbol, strategy_label, qty)
        if qty == 0:
            logger.info(
                "learning_engine blocked order for %s/%s based on tuning file %s",
                symbol,
                strategy_label,
                self.learning_tuning_path,
            )
            return

        side = signal
        if qty < 0:
            side = "SELL"
            qty = abs(qty)
            if side != signal:
                logger.info(
                    "Position sizer flipped signal %s to SELL for %s based on exposure.",
                    signal,
                    symbol,
                )

        if signal not in ("BUY", "SELL"):  # Allow exits
            pass
        else:
            # Apply expiry risk adapter for new entries (BUY/SELL only)
            if self.expiry_risk_adapter is not None:
                try:
                    import pytz
                    
                    # Determine if this is an option instrument
                    # Simple heuristic: symbol contains "CE" or "PE"
                    is_option = "CE" in symbol.upper() or "PE" in symbol.upper()
                    
                    # Get the underlying logical name
                    underlying_logical = logical or self.logical_alias.get(symbol, symbol)
                    
                    # Evaluate expiry risk
                    now_ist = datetime.now(pytz.timezone("Asia/Kolkata"))
                    expiry_decision = self.expiry_risk_adapter.evaluate(
                        symbol=underlying_logical,
                        dt=now_ist,
                        is_option=is_option,
                        is_new_entry=True,
                    )
                    
                    # Log decision if significant
                    self.expiry_risk_adapter.log_decision(underlying_logical, expiry_decision)
                    
                    # Block if not allowed
                    if not expiry_decision.allow_new_entry:
                        logger.warning(
                            "Expiry risk adapter blocked new entry for %s: %s",
                            symbol, expiry_decision.reason
                        )
                        log_event(
                            "EXPIRY_RISK_BLOCK",
                            expiry_decision.reason,
                            symbol=symbol,
                            strategy_id=strategy_label,
                            extra={"is_option": is_option, "underlying": underlying_logical},
                        )
                        return
                    
                    # Apply risk scale to quantity if needed
                    if expiry_decision.risk_scale < 1.0:
                        original_qty = qty
                        qty = max(1, int(qty * expiry_decision.risk_scale))
                        logger.info(
                            "Expiry risk adapter scaled qty for %s: %d -> %d (scale=%.2f, reason=%s)",
                            symbol, original_qty, qty, expiry_decision.risk_scale, expiry_decision.reason
                        )
                        log_event(
                            "EXPIRY_RISK_SCALE",
                            expiry_decision.reason,
                            symbol=symbol,
                            strategy_id=strategy_label,
                            extra={
                                "original_qty": original_qty,
                                "scaled_qty": qty,
                                "risk_scale": expiry_decision.risk_scale,
                            },
                        )
                except Exception as exc:
                    logger.warning("Failed to evaluate expiry risk for %s: %s", symbol, exc)
                    # Continue with order placement on error (fail-safe)
            
            order_intent = {
                "symbol": symbol,
                "signal": signal,
                "price": price,
                "quantity": qty,
                "strategy": strategy_label,
            }
            portfolio_state = self._compute_portfolio_meta()
            checkpoint_snapshot = self.state_store.load_checkpoint() or {}
            strategy_snapshot = (
                (checkpoint_snapshot.get("strategies") or {}).get(strategy_label, {})
                if isinstance(checkpoint_snapshot, dict)
                else {}
            )
            risk_decision = self.risk_engine.check_order(
                order_intent,
                portfolio_state,
                strategy_snapshot,
            )

            if risk_decision.action == RiskAction.BLOCK:
                log_event(
                    "RISK_BLOCK",
                    risk_decision.reason,
                    symbol=symbol,
                    strategy_id=strategy_label,
                    extra={"qty": qty, "price": price},
                )
                return
            elif risk_decision.action == RiskAction.REDUCE:
                log_event(
                    "RISK_REDUCE",
                    risk_decision.reason,
                    symbol=symbol,
                    strategy_id=strategy_label,
                    extra={"original_qty": qty, "adjusted_qty": risk_decision.adjusted_qty},
                )
                qty = risk_decision.adjusted_qty
            elif risk_decision.action == RiskAction.HALT_SESSION:
                log_event(
                    "HALT_SESSION",
                    risk_decision.reason,
                    symbol=symbol,
                    strategy_id=strategy_label,
                )
                self.running = False
                return

        logical_name = logical or self.logical_alias.get(symbol, symbol)

        quality_ctx = self._build_signal_context(
            symbol=symbol,
            strategy=strategy_label,
            side=side,
            price=price,
            regime=trend_context or regime or "",
            indicators=indicators,
            decision_conf=decision.confidence,
        )
        quality_score = self.signal_quality.score_signal(quality_ctx)
        if quality_score.vetoed:
            self.signal_quality.record_veto(strategy_label, symbol)
            logger.info(
                "[QUALITY_VETO] %s/%s %s score=%.2f reason=%s",
                strategy_label,
                symbol,
                side,
                quality_score.score,
                quality_score.veto_reason or quality_score.reason,
            )
            return
        logger.info(
            "[QUALITY_OK] %s/%s %s score=%.2f reason=%s",
            strategy_label,
            symbol,
            side,
            quality_score.score,
            quality_score.reason,
        )

        extra_payload: Dict[str, Any] = {
            "strategy": strategy_label,
            "strategy_code": strategy_code_value,
            "mode": mode_label,
            "logical": logical_name,
            "tf": tf,
            "confidence": confidence_value,
            "signal_timestamp": signal_timestamp,
            "playbook": playbook_value,
            "reason": reason_value,
            "vol_regime": vol_regime,
            "trend_context": trend_context,
            "profile": profile,
            "quality_score": round(quality_score.score, 3),
            "market_regime": market_regime,
        }
        meta_decision = self._last_meta_decisions.get(symbol)
        if meta_decision:
            extra_payload["meta_style"] = meta_decision.style
            extra_payload["meta_tf"] = meta_decision.timeframe
            extra_payload["meta_conf"] = round(meta_decision.confidence, 3)
            extra_payload["meta_reason"] = meta_decision.reason

        approved, filter_payload = self._maybe_apply_trade_filters(
            symbol=symbol,
            side=side,
            qty=qty,
            price=price,
            logical_name=logical_name,
            portfolio_state=portfolio_state,
        )
        if not approved:
            return
        if filter_payload:
            extra_payload.update(filter_payload)

        throttler_allowed = True
        throttler_reason = "OK"
        expected_edge_rupees = DEFAULT_EXPECTED_EDGE_RUPEES
        if self.trade_throttler:
            notional = abs(float(qty) * float(price))
            throttler_allowed, throttler_reason = self.trade_throttler.should_allow_entry(
                symbol=symbol,
                strategy=strategy_label,
                notional=notional,
                expected_edge_rupees=expected_edge_rupees,
            )
        if not throttler_allowed:
            trade_monitor.increment("entries_blocked_risk")
            self._record_trade_flow_event("risk_blocks", reason=throttler_reason, bucket="risk")
            logger.warning(
                "[QUALITY_VETO] symbol=%s strategy=%s reason=%s",
                symbol,
                strategy_label,
                throttler_reason,
            )
            log_event(
                "RISK_BLOCK",
                "Trade throttler vetoed entry",
                symbol=symbol,
                strategy_id=strategy_label,
                extra={
                    "reason": throttler_reason,
                    "mode": mode_label,
                },
            )
            return
        extra_payload["throttler_reason"] = throttler_reason
        extra_payload["expected_edge_rupees"] = expected_edge_rupees

        trade_monitor.increment("entries_allowed")
        
        # Publish decision trace telemetry
        publish_decision_trace(
            strategy_name=strategy_label,
            symbol=symbol,
            decision=signal,
            trace_data={
                "confidence": confidence_value,
                "playbook": playbook_value,
                "reason": reason_value,
                "tf": tf,
                "profile": profile,
                "indicators": indicators or {},
            }
        )
        
        # Publish signal event telemetry
        publish_signal_event(
            symbol=symbol,
            strategy_name=strategy_label,
            signal=signal,
            confidence=confidence_value,
            timeframe=tf,
            price=price,
            logical=logical_name,
        )
        
        atr_meta = self._compute_sl_tp_for_order(
            symbol=symbol,
            side=side,
            price=price,
            indicators=indicators,
        )
        extra_payload["sl_price"] = atr_meta.get("sl_price")
        extra_payload["tp_price"] = atr_meta.get("tp_price")
        extra_payload["atr_method"] = atr_meta.get("method")
        extra_payload["atr_value"] = atr_meta.get("atr_used")

        order_context = {
            "side": side,
            "qty": qty,
            "price": round(price, 2),
            "strategy": strategy_label,
            "tf": tf,
            "mode": mode_label,
        }
        self.strategy_metrics.remember(symbol, strategy_code_value)
        self._record_trade_flow_event("orders_submitted")
        log_event(
            "ORDER_NEW",
            "[ENTRY] Submitting entry order",
            symbol=symbol,
            strategy_id=strategy_label,
            extra=order_context,
        )
        logger.info(
            "Placing PAPER order: %s %d x %s @ %.2f (strategy=%s)",
            side,
            qty,
            symbol,
            price,
            extra_payload.get("strategy"),
        )
        realized_before = self._realized_pnl(symbol)
        trade_monitor.increment("orders_submitted")
        
        # Use ExecutionEngine v2 if available
        # Try ExecutionEngine V3 first, then V2, then legacy
        if self.execution_engine_v3 is not None:
            try:
                from engine.execution_v3_integration import convert_to_order_intent
                # Determine logical symbol for context
                logical = self.logical_alias.get(symbol, symbol)
                
                # Convert to ExecutionEngine V3 OrderIntent + ExecutionContext
                intent, context = convert_to_order_intent(
                    symbol=symbol,
                    signal=side,
                    qty=qty,
                    price=price,
                    strategy_code=strategy_label,
                    logical_symbol=logical,
                    product=self.cfg.trading.get("default_product", "MIS"),
                    mode=self.mode.value,
                    timeframe=tf or self.default_timeframe,
                    exchange=self.fno_exchange,
                    sl_price=extra_payload.get("sl_price"),
                    tp_price=extra_payload.get("tp_price"),
                    time_stop_bars=extra_payload.get("time_stop_bars"),
                    reason=extra_payload.get("reason", ""),
                )
                
                # Execute via ExecutionEngine V3
                result = self.execution_engine_v3.process_signal(symbol, intent, context)
                if result and result.status == "FILLED":
                    logger.info("Order executed via ExecutionEngine V3: %s", result.order_id)
                    return
                elif result and result.status == "REJECTED":
                    logger.warning("Order rejected by ExecutionEngine V3: %s", result.reason)
                    return
            except Exception as exc:
                logger.warning("ExecutionEngine V3 failed, falling back: %s", exc)
        
        # Fall back to ExecutionEngine v2
        if self.execution_engine_v2 is not None:
            try:
                from engine.execution_bridge import convert_strategy_intent_to_execution_intent
                # Convert to ExecutionEngine v2 OrderIntent
                exec_intent = convert_strategy_intent_to_execution_intent(
                    strategy_intent=None,  # Not available here
                    symbol=symbol,
                    strategy_code=strategy_label,
                    qty=qty,
                    order_type="MARKET",
                    product="MIS",
                    price=price,
                )
                exec_intent.reason = extra_payload.get("reason", "")
                
                # Execute via ExecutionEngine v2
                result = self.execution_engine_v2.execute_intent(exec_intent)
                
                # Convert ExecutionResult to order format for compatibility
                order = SimpleNamespace(
                    order_id=result.order_id,
                    status=result.status,
                    symbol=result.symbol,
                    side=result.side,
                    qty=result.qty,
                    price=result.avg_price,
                )
                logger.info("Order executed via ExecutionEngine v2: %s", order)
            except Exception as exc:
                logger.warning("ExecutionEngine v2 failed, falling back to legacy: %s", exc)
                # Guardian check for legacy fallback path
                if self.guardian:
                    from core.strategy_engine_v2 import OrderIntent as StrategyOrderIntent
                    legacy_intent = StrategyOrderIntent(
                        symbol=symbol,
                        action=side,
                        qty=qty,
                        reason=extra_payload.get("reason", ""),
                        strategy_code=strategy_label,
                    )
                    guardian_decision = self.guardian.validate_pre_trade(legacy_intent, None)
                    if not guardian_decision.allow:
                        logger.warning(
                            "[guardian-block] %s - skipping order", guardian_decision.reason
                        )
                        return
                order = self.router.place_order(symbol, side, qty, price)
        else:
            # Legacy execution path - check guardian before placing order
            if self.guardian:
                from core.strategy_engine_v2 import OrderIntent as StrategyOrderIntent
                legacy_intent = StrategyOrderIntent(
                    symbol=symbol,
                    action=side,
                    qty=qty,
                    reason=extra_payload.get("reason", ""),
                    strategy_code=strategy_label,
                )
                guardian_decision = self.guardian.validate_pre_trade(legacy_intent, None)
                if not guardian_decision.allow:
                    logger.warning(
                        "[guardian-block] %s - skipping order", guardian_decision.reason
                    )
                    return
            order = self.router.place_order(symbol, side, qty, price)
        if self.trade_throttler:
            self.trade_throttler.register_fill(
                symbol=symbol,
                strategy=strategy_label,
                side=side,
                qty=qty,
                price=price,
                realized_pnl=0.0,
            )
        logger.info("Order executed (mode=%s): %s", self.mode.value, order)
        
        # Publish order event telemetry
        order_id = getattr(order, "order_id", "")
        status = str(getattr(order, "status", "FILLED") or "FILLED").upper()
        publish_order_event(
            order_id=order_id or f"paper-{symbol}-{int(time.time())}",
            symbol=symbol,
            side=side,
            status=status,
            quantity=qty,
            price=price,
            strategy=strategy_label,
            mode=mode_label,
        )
        
        self.signal_quality.record_execution(strategy_label, symbol, quality_score.score)
        if status in FILLED_ORDER_STATUSES:
            trade_monitor.increment("orders_filled")
            self._record_trade_flow_event("orders_filled")
            log_event(
                "ORDER_FILL",
                "Order filled",
                symbol=symbol,
                strategy_id=strategy_label,
                extra={
                    **order_context,
                    "status": status,
                },
            )

        if self.enable_trailing_stops:
            pos = self.paper_broker.get_position(symbol)
            if pos:
                r_basis = max(price * 0.005, 1.0)
                entry = pos.avg_price or price
                self.trailing_state[symbol] = {
                    "entry": entry,
                    "r_basis": r_basis,
                    "max_favorable_r": 0.0,
                    "trail_price": 0.0,
                }

        # Record order for audit / learning
        extra_payload["status"] = status
        self.recorder.record_order(
            symbol=symbol,
            side=signal,
            quantity=qty,
            price=price,
            status=status,
            tf=tf or self.default_timeframe,
            profile=profile or _profile_from_tf(tf),
            strategy=strategy_label,
            parent_signal_timestamp=signal_timestamp,
            extra=extra_payload,
        )

        realized_after = self._realized_pnl(symbol)
        pnl_delta = realized_after - realized_before
        r_multiple = self._compute_r_multiple(pnl_delta)
        self._journal_order(
            symbol=symbol,
            side=signal,
            quantity=qty,
            price=price,
            status=status,
            tf=tf or self.default_timeframe,
            profile=profile or _profile_from_tf(tf),
            strategy=strategy_label,
            parent_signal_timestamp=signal_timestamp,
            extra=extra_payload,
            realized_delta=pnl_delta,
            r_multiple=r_multiple,
            signal_id=signal_timestamp,
            exit_reason="",
            trade_strategy=strategy_label,
            trade_tf=tf or self.default_timeframe,
            trade_profile=profile or _profile_from_tf(tf),
            trade_payload=extra_payload,
        )
        post_position = self.paper_broker.get_position(symbol)
        post_qty = post_position.quantity if post_position else 0
        self.strategy_metrics.record_fill(
            symbol,
            prev_qty=prev_position_qty,
            new_qty=post_qty,
            pnl_delta=pnl_delta,
            strategy_code=strategy_code_value,
        )

        self.last_signal_ids[symbol] = signal_timestamp

        # Snapshot state after each order as well
        meta_after = self._compute_portfolio_meta()
        self._snapshot_state(meta_after, reason="order_fill")

    def _enforce_per_trade_stop(self) -> None:
        """
        Enforce per-trade max loss (percentage of entry price) on open positions.
        For each position:
            LONG: if (last - avg) / avg <= -max_loss_pct_per_trade -> close (SELL).
            SHORT: if (avg - last) / avg <= -max_loss_pct_per_trade -> close (BUY).
        """
        if self.max_loss_pct_per_trade <= 0:
            return

        for symbol, pos in self.paper_broker.get_all_positions().items():
            if pos.quantity == 0:
                continue

            avg = pos.avg_price or 0.0
            if avg <= 0:
                continue

            last = self.last_prices.get(symbol, avg)
            if last <= 0:
                continue

            qty = pos.quantity
            if qty > 0:
                # LONG
                ret = (last - avg) / avg
                if ret <= -self.max_loss_pct_per_trade:
                    logger.warning(
                        "Per-trade stop-loss triggered for %s (LONG): avg=%.2f last=%.2f loss=%.2f%% >= %.2f%%. "
                        "Closing position.",
                        symbol,
                        avg,
                        last,
                        abs(ret) * 100.0,
                        self.max_loss_pct_per_trade * 100.0,
                    )
                    self._record_trade_flow_event("stop_hits")
                    log_event(
                        "STOP_HIT",
                        "[STOP_LOSS] Per-trade stop loss triggered (LONG)",
                        symbol=symbol,
                        strategy_id=self.strategy_name,
                        extra={"avg": round(avg, 2), "last": round(last, 2), "pct": round(abs(ret) * 100.0, 2)},
                    )
                    self._close_position(symbol, "SELL", qty, last)
            elif qty < 0:
                # SHORT
                ret = (avg - last) / avg
                if ret <= -self.max_loss_pct_per_trade:
                    logger.warning(
                        "Per-trade stop-loss triggered for %s (SHORT): avg=%.2f last=%.2f loss=%.2f%% >= %.2f%%. "
                        "Closing position.",
                        symbol,
                        avg,
                        last,
                        abs(ret) * 100.0,
                        self.max_loss_pct_per_trade * 100.0,
                    )
                    self._record_trade_flow_event("stop_hits")
                    log_event(
                        "STOP_HIT",
                        "[STOP_LOSS] Per-trade stop loss triggered (SHORT)",
                        symbol=symbol,
                        strategy_id=self.strategy_name,
                        extra={"avg": round(avg, 2), "last": round(last, 2), "pct": round(abs(ret) * 100.0, 2)},
                    )
                    self._close_position(symbol, "BUY", abs(qty), last)

    def _enforce_trailing_stops(self) -> None:
        """
        Enforce trailing profit locks based on R multiples.
        """
        if not self.enable_trailing_stops:
            return

        for symbol, pos in self.paper_broker.get_all_positions().items():
            if pos.quantity == 0:
                self.trailing_state.pop(symbol, None)
                continue

            state = self.trailing_state.get(symbol)
            if not state:
                continue

            last = self.last_prices.get(symbol, pos.avg_price or 0.0)
            entry = state.get("entry", pos.avg_price or last)
            r_basis = max(state.get("r_basis", 1.0), 1e-6)

            if pos.quantity > 0:
                unreal = last - entry
            else:
                unreal = entry - last

            current_r = unreal / r_basis
            state["max_favorable_r"] = max(state.get("max_favorable_r", 0.0), current_r)

            if current_r < self.trail_start_r:
                continue

            locked_r = max(
                self.trail_lock_r,
                state["max_favorable_r"] - self.trail_step_r,
            )
            locked_r = max(0.0, locked_r)

            trail = state.get("trail_price", 0.0)
            if pos.quantity > 0:
                desired = entry + locked_r * r_basis
                if desired > trail:
                    state["trail_price"] = desired
            else:
                desired = entry - locked_r * r_basis
                if trail == 0.0 or desired < trail:
                    state["trail_price"] = desired

            trail = state.get("trail_price", 0.0)
            if trail <= 0:
                continue

            if pos.quantity > 0 and last <= trail:
                logger.warning(
                    "Trailing stop hit for %s (LONG): entry=%.2f last=%.2f trail=%.2f (R≈%.2f). Closing.",
                    symbol,
                    entry,
                    last,
                    trail,
                    current_r,
                )
                self._close_position(symbol, "SELL", pos.quantity, last)
                self.trailing_state.pop(symbol, None)
            elif pos.quantity < 0 and last >= trail:
                logger.warning(
                    "Trailing stop hit for %s (SHORT): entry=%.2f last=%.2f trail=%.2f (R≈%.2f). Closing.",
                    symbol,
                    entry,
                    last,
                    trail,
                    current_r,
                )
                self._close_position(symbol, "BUY", abs(pos.quantity), last)
                self.trailing_state.pop(symbol, None)

    def _apply_risk_engine(self) -> None:
        self._age_trades()
        if not self.risk_engine_cfg:
            return
        positions = list(self.paper_broker.get_all_positions().items())
        if not positions:
            return
        risk_cfg = self.risk_engine_cfg
        risk_unit = self.paper_capital * self.sizer_config.risk_per_trade_pct
        state_meta = {"risk_lock": not self.running}
        for symbol, pos in positions:
            qty = pos.quantity
            if qty == 0:
                continue
            entry = pos.avg_price or 0.0
            last = self.last_prices.get(symbol, entry)
            if entry <= 0 or last <= 0:
                continue
            trade_state = self.active_trades.get(symbol)
            if trade_state:
                trade_state.update_price(last)
                trade_state.bars_in_trade += 1
            pnl_value = (last - entry) * qty
            denom = entry * max(1, abs(qty))
            pnl_pct = (pnl_value / denom) * 100.0 if denom > 0 else 0.0
            exit_side = "SELL" if qty > 0 else "BUY"
            r_multiple = None
            if risk_unit > 0:
                r_multiple = pnl_value / risk_unit
            trail_state = self.trailing_state.get(symbol, {})
            meta = {
                "r_multiple": r_multiple,
                "trail_locked_r": trail_state.get("max_favorable_r"),
            }
            ctx = TradeContext(
                symbol=symbol,
                strategy=self.strategy_name,
                mode=self.mode.value,
                entry_price=entry,
                current_price=last,
                quantity=qty,
                ts=datetime.now(timezone.utc),
                pnl_pct=pnl_pct,
                pnl_abs=pnl_value,
                timeframe=None,
                meta=meta,
            )
            decision = compute_exit_decision(ctx, risk_cfg, state_meta=state_meta)
            action = decision.get("action", "hold")
            if action == "hold":
                continue
            reason = decision.get("reason", "risk_engine")
            logger.info(
                "risk_engine: action=%s reason=%s symbol=%s pnl_pct=%.2f qty=%s",
                action,
                reason,
                symbol,
                pnl_pct,
                qty,
            )
            if action == "exit":
                self._close_position(symbol, exit_side, abs(qty), last, reason=reason)
            elif action == "reduce":
                fraction = float(decision.get("reduce_fraction", risk_cfg.partial_exit_fraction))
                reduce_qty = max(1, int(abs(qty) * max(0.1, min(0.9, fraction))))
                if reduce_qty >= abs(qty):
                    self._close_position(symbol, exit_side, abs(qty), last, reason=reason)
                else:
                    self._close_position(symbol, exit_side, reduce_qty, last, reason=reason)

    def _close_position(
        self,
        symbol: str,
        side: str,
        qty: int,
        price: float,
        reason: str = "per_trade_stop",
        strategy_code: Optional[str] = None,
    ) -> None:
        """
        Place a closing order and record it, including snapshot after.
        """
        prev_position = self.paper_broker.get_position(symbol)
        prev_qty = prev_position.quantity if prev_position else 0
        code_for_metrics = strategy_code or self._lookup_strategy_code(symbol)
        realized_before = self._realized_pnl(symbol)
        order_context = {
            "side": side,
            "qty": qty,
            "price": round(price, 2),
            "reason": reason,
        }
        self._record_trade_flow_event("orders_submitted")
        log_event(
            "ORDER_NEW",
            "[EXIT] Submitting exit order",
            symbol=symbol,
            strategy_id=self.strategy_name,
            extra=order_context,
        )
        order = self.router.place_order(symbol, side, qty, price)
        trade_monitor.increment("orders_submitted")
        logger.info("Close-position order executed (mode=%s): %s", self.mode.value, order)

        status = str(getattr(order, "status", "FILLED") or "FILLED").upper()
        if status in FILLED_ORDER_STATUSES:
            trade_monitor.increment("orders_filled")
            self._record_trade_flow_event("orders_filled")
            log_event(
                "ORDER_FILL",
                "Exit order filled",
                symbol=symbol,
                strategy_id=self.strategy_name,
                extra={**order_context, "status": status},
            )
        tf = self._resolve_timeframe()
        profile = _profile_from_tf(tf)
        extra_payload = {
            "reason": reason,
            "status": status,
            "tf": tf,
            "mode": self.strategy_mode,
            "strategy": self.strategy_name,
        }
        self.recorder.record_order(
            symbol=symbol,
            side=side,
            quantity=qty,
            price=price,
            status=status,
            tf=tf,
            profile=profile,
            strategy=self.strategy_name,
            parent_signal_timestamp="",
            extra=extra_payload,
        )

        realized_after = self._realized_pnl(symbol)
        pnl_delta = realized_after - realized_before
        r_multiple = self._compute_r_multiple(pnl_delta)
        signal_ref = ""
        trade_ref = self.active_trades.get(symbol)
        if trade_ref:
            signal_ref = trade_ref.signal_id
        elif symbol in self.last_signal_ids:
            signal_ref = self.last_signal_ids[symbol]
        self._journal_order(
            symbol=symbol,
            side=side,
            quantity=qty,
            price=price,
            status=status,
            tf=tf,
            profile=profile,
            strategy=self.strategy_name,
            parent_signal_timestamp="",
            extra=extra_payload,
            realized_delta=pnl_delta,
            r_multiple=r_multiple,
            signal_id=signal_ref,
            exit_reason=reason,
            trade_strategy=self.strategy_name,
            trade_tf=tf,
            trade_profile=profile,
            trade_payload=extra_payload,
        )
        post_position = self.paper_broker.get_position(symbol)
        post_qty = post_position.quantity if post_position else 0
        self.strategy_metrics.record_fill(
            symbol,
            prev_qty=prev_qty,
            new_qty=post_qty,
            pnl_delta=pnl_delta,
            strategy_code=code_for_metrics,
        )
        if self.trade_throttler:
            self.trade_throttler.register_fill(
                symbol=symbol,
                strategy=self.strategy_name,
                side=side,
                qty=qty,
                price=price,
                realized_pnl=pnl_delta,
                count_towards_limits=False,
            )

        meta = self._compute_portfolio_meta()
        self._snapshot_state(meta, reason="close_position")

    # -------------------------------------------------------------------------
    # State + journaling helpers
    # -------------------------------------------------------------------------

    def _realized_pnl(self, symbol: str) -> float:
        pos = self.paper_broker.get_position(symbol)
        return float(pos.realized_pnl if pos else 0.0)

    def _compute_r_multiple(self, pnl_value: float) -> Optional[float]:
        risk_unit = self.paper_capital * self.sizer_config.risk_per_trade_pct
        if risk_unit <= 0:
            return None
        return pnl_value / risk_unit if risk_unit else None

    def _journal_order(
        self,
        *,
        symbol: str,
        side: str,
        quantity: int,
        price: float,
        status: str,
        tf: str,
        profile: str,
        strategy: str,
        parent_signal_timestamp: str,
        extra: Dict[str, Any],
        realized_delta: float,
        r_multiple: Optional[float],
        signal_id: Optional[str],
        exit_reason: str,
        trade_strategy: Optional[str],
        trade_tf: Optional[str],
        trade_profile: Optional[str],
        trade_payload: Optional[Dict[str, Any]],
    ) -> None:
        if not self.journal:
            return
        trade = self._ensure_trade_context(
            symbol=symbol,
            signal_id=signal_id,
            strategy=trade_strategy or strategy,
            price=price,
            tf=trade_tf or tf,
            profile=trade_profile or profile,
            payload=trade_payload or extra,
        )
        self._order_sequence += 1
        timestamp = datetime.now(timezone.utc).isoformat()
        order_id = f"paper-{int(time.time() * 1_000_000)}-{self._order_sequence}"
        payload: Dict[str, Any] = {
            "timestamp": timestamp,
            "order_id": order_id,
            "symbol": symbol,
            "tradingsymbol": symbol,
            "transaction_type": side,
            "side": side,
            "quantity": quantity,
            "filled_quantity": quantity,
            "price": price,
            "average_price": price,
            "status": status,
            "exchange": self.fno_exchange,
            "product": "MIS",
            "variety": "REGULAR",
            "parent_order_id": "",
            "tag": strategy,
            "tf": tf,
            "profile": profile,
            "strategy": strategy,
            "parent_signal_timestamp": parent_signal_timestamp or "",
            "underlying": self.logical_alias.get(symbol, symbol),
            "extra": json.dumps(extra or {}, ensure_ascii=False, default=str),
            "pnl": round(realized_delta, 2),
            "realized_pnl": round(realized_delta, 2),
        }
        if r_multiple is not None:
            payload["r"] = round(r_multiple, 4)
            payload["r_multiple"] = round(r_multiple, 4)
        payload["trade_id"] = trade.trade_id if trade else ""
        payload["signal_id"] = signal_id or (trade.signal_id if trade else "")
        if trade:
            payload["entry_price"] = round(trade.entry_price, 4)
        else:
            payload["entry_price"] = ""
        payload["exit_price"] = round(price, 4) if exit_reason else ""
        payload["realized_pnl_pct"] = (
            round(self._compute_realized_pct(realized_delta, trade), 4) if (trade and exit_reason) else ""
        )
        payload["exit_reason"] = exit_reason or ""
        payload["exit_detail"] = extra.get("reason") if extra else exit_reason
        try:
            self.journal.append_orders([payload])
            state = self.state_store.load_checkpoint() or {}
            strategies = state.setdefault("strategies", {})
            strat_metrics = strategies.setdefault(
                strategy,
                {"day_pnl": 0.0, "entry_count": 0, "exit_count": 0, "win_trades": 0, "loss_trades": 0},
            )
            strat_metrics["day_pnl"] = strat_metrics.get("day_pnl", 0.0) + realized_delta
            if exit_reason:
                strat_metrics["exit_count"] = strat_metrics.get("exit_count", 0) + 1
                if realized_delta > 0:
                    strat_metrics["win_trades"] = strat_metrics.get("win_trades", 0) + 1
                else:
                    strat_metrics["loss_trades"] = strat_metrics.get("loss_trades", 0) + 1
            else:
                strat_metrics["entry_count"] = strat_metrics.get("entry_count", 0) + 1
            self.state_store.save_checkpoint(state)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to append journal order for %s: %s", symbol, exc, exc_info=True)
        self._update_trade_after_order(symbol, trade, realized_delta, price, exit_reason)

    def _snapshot_state(
        self,
        meta: Optional[Dict[str, Any]] = None,
        *,
        reason: str = "",
        force_snapshot: bool = False,
    ) -> None:
        meta_payload = dict(meta or self._compute_portfolio_meta())
        meta_payload["trade_flow"] = self._trade_flow_snapshot()
        timestamp = datetime.now(timezone.utc).isoformat()
        try:
            self.recorder.snapshot_paper_state(
                self.paper_broker,
                last_prices=self.last_prices,
                meta=meta_payload,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("TradeRecorder snapshot failed: %s", exc, exc_info=True)

        state_payload = {
            "timestamp": timestamp,
            "broker": self.paper_broker.to_state_dict(last_prices=self.last_prices),
            "meta": meta_payload,
        }
        
        # Publish position snapshot telemetry periodically
        if reason in ("loop_tick", "order_fill"):
            positions = []
            for symbol, pos in self.paper_broker.get_all_positions().items():
                if pos.quantity != 0:
                    positions.append({
                        "symbol": symbol,
                        "quantity": pos.quantity,
                        "avg_price": pos.avg_price,
                        "realized_pnl": pos.realized_pnl,
                        "last_price": self.last_prices.get(symbol),
                    })
            if positions:
                publish_position_event(
                    symbol="portfolio",
                    position_size=len(positions),
                    positions=positions,
                    equity=meta_payload.get("equity", 0.0),
                    total_notional=meta_payload.get("total_notional", 0.0),
                )
        
        try:
            self.state_store.save_checkpoint(state_payload)
            logger.info(
                "Saved paper checkpoint (reason=%s, equity=%.2f realized=%.2f unrealized=%.2f)",
                reason or "loop",
                float(meta_payload.get("equity") or 0.0),
                float(meta_payload.get("total_realized_pnl") or 0.0),
                float(meta_payload.get("total_unrealized_pnl") or 0.0),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to persist paper checkpoint: %s", exc, exc_info=True)

        self._maybe_append_equity_snapshot(state_payload, force_snapshot=force_snapshot)

    def _maybe_append_equity_snapshot(
        self,
        state_payload: Dict[str, Any],
        *,
        force_snapshot: bool = False,
    ) -> None:
        interval = max(0, self.equity_snapshot_interval_sec)
        now = time.time()
        if not force_snapshot and interval > 0 and (now - self._last_equity_snapshot_ts) < interval:
            return
        try:
            path = self.journal.append_equity_snapshot(state_payload)
            self._last_equity_snapshot_ts = now
            meta = state_payload.get("meta") or {}
            logger.info(
                "Equity snapshot appended (equity=%.2f realized=%.2f path=%s)",
                float(meta.get("equity") or 0.0),
                float(meta.get("total_realized_pnl") or 0.0),
                path,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to append equity snapshot: %s", exc, exc_info=True)

    def _load_learning_tuning(self) -> Dict[str, Any]:
        try:
            return load_tuning(self.learning_tuning_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load learning tuning file %s: %s", self.learning_tuning_path, exc)
            return {}

    def _apply_learning_adjustments(
        self,
        symbol: str,
        strategy_label: str,
        qty: int,
    ) -> int:
        if not self.learning_enabled or qty <= 0:
            return qty
        key = f"{symbol}|{strategy_label}"
        fallback_key = f"{self.logical_alias.get(symbol, symbol)}|{strategy_label}"
        entry = self.learning_tuning.get(key) or self.learning_tuning.get(fallback_key)
        if not entry:
            return qty
        status = str(entry.get("status", "active")).lower()
        if status in {"disabled", "disabled_bad_performance"}:
            logger.info(
                "learning_engine: status=%s blocking symbol=%s strategy=%s",
                status,
                symbol,
                strategy_label,
            )
            return 0
        multiplier = float(entry.get("risk_multiplier", 1.0))
        multiplier = max(self.learning_min_multiplier, min(self.learning_max_multiplier, multiplier))
        adjusted = int(round(qty * multiplier))
        if adjusted == 0 and multiplier > 0:
            adjusted = 1
        if adjusted != qty:
            logger.info(
                "learning_engine: adjusted qty %s -> %s for %s/%s (multiplier=%.2f)",
                qty,
                adjusted,
                symbol,
                strategy_label,
                multiplier,
            )
        return adjusted

    def _is_expiry_instrument(self, symbol: str) -> bool:
        s = (symbol or "").upper()
        return any(tag in s for tag in ("CE", "PE")) and any(idx in s for idx in ("NIFTY", "BANKNIFTY", "FINNIFTY"))

    def _resolve_product_type(self, symbol: str) -> str:
        s = (symbol or "").upper()
        if self._is_expiry_instrument(symbol):
            return "OPT"
        if "FUT" in s:
            return "FUT"
        return "EQ"

    def _check_time_filter(self, symbol: str, strategy_label: str, is_entry: bool) -> bool:
        if not is_entry or not self.time_filter_config.enabled:
            return True
        allowed, reason = is_entry_time_allowed(
            self.time_filter_config,
            symbol=symbol,
            strategy_id=strategy_label,
            is_expiry_instrument=self._is_expiry_instrument(symbol),
        )
        if not allowed:
            logger.info(
                "time_filter_blocked symbol=%s strategy=%s reason=%s",
                symbol,
                strategy_label,
                reason,
            )
            detail = reason or "time_window"
            trade_monitor.increment("entries_blocked_time")
            self._record_trade_flow_event(
                "time_blocks",
                reason=detail,
                bucket="time",
            )
            log_event(
                "TIME_BLOCK",
                "Entry blocked by time filter",
                symbol=symbol,
                strategy_id=strategy_label,
                extra={"reason": detail},
            )
        return allowed

    def _compute_sl_tp_for_order(
        self,
        *,
        symbol: str,
        side: str,
        price: float,
        indicators: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not self.atr_config.enabled or price <= 0:
            return {"sl_price": None, "tp_price": None, "method": "disabled", "atr_used": None}
        atr_value = None
        if indicators:
            atr_value = indicators.get("atr") or indicators.get("ATR")
            if isinstance(atr_value, str):
                try:
                    atr_value = float(atr_value)
                except ValueError:
                    atr_value = None
        result = compute_sl_tp_from_atr(
            symbol=symbol,
            product_type=self._resolve_product_type(symbol),
            side=side,
            entry_price=price,
            atr_value=atr_value,
            cfg=self.atr_config,
        )
        if result["method"] == "pct_fallback":
            logger.info(
                "atr_missing_fallback symbol=%s side=%s entry=%.2f sl=%.2f tp=%.2f",
                symbol,
                side,
                price,
                result["sl_price"],
                result["tp_price"],
            )
        elif result["method"] == "atr":
            logger.info(
                "atr_risk_applied symbol=%s side=%s entry=%.2f atr=%.4f sl=%.2f tp=%.2f",
                symbol,
                side,
                price,
                result["atr_used"],
                result["sl_price"],
                result["tp_price"],
            )
        return result

    def _enforce_trade_sl_tp(self) -> None:
        if not self.active_trades:
            return
        for symbol, trade in list(self.active_trades.items()):
            qty = trade.quantity
            if qty == 0:
                continue
            last_price = self.last_prices.get(symbol)
            if last_price is None:
                continue
            side = trade.side.upper()
            if trade.sl_price is not None:
                if (side == "LONG" and last_price <= trade.sl_price) or (
                    side == "SHORT" and last_price >= trade.sl_price
                ):
                    logger.info("atr_sl_hit symbol=%s price=%.2f sl=%.2f", symbol, last_price, trade.sl_price)
                    self._record_trade_flow_event("stop_hits")
                    log_event(
                        "STOP_HIT",
                        "[STOP_LOSS] ATR stop triggered",
                        symbol=symbol,
                        strategy_id=trade.strategy or self.strategy_name,
                        extra={
                            "price": round(last_price, 2),
                            "sl_price": trade.sl_price,
                            "qty": abs(qty),
                        },
                    )
                    self._close_position(symbol, "SELL" if side == "LONG" else "BUY", abs(qty), last_price, reason="atr_sl")
                    continue
            if trade.tp_price is not None:
                if (side == "LONG" and last_price >= trade.tp_price) or (
                    side == "SHORT" and last_price <= trade.tp_price
                ):
                    logger.info("atr_tp_hit symbol=%s price=%.2f tp=%.2f", symbol, last_price, trade.tp_price)
                    self._record_trade_flow_event("target_hits")
                    log_event(
                        "TP_HIT",
                        "[TAKE_PROFIT] ATR target hit",
                        symbol=symbol,
                        strategy_id=trade.strategy or self.strategy_name,
                        extra={
                            "price": round(last_price, 2),
                            "tp_price": trade.tp_price,
                            "qty": abs(qty),
                        },
                    )
                    self._close_position(symbol, "SELL" if side == "LONG" else "BUY", abs(qty), last_price, reason="atr_tp")

    def _ensure_trade_context(
        self,
        *,
        symbol: str,
        signal_id: Optional[str],
        strategy: str,
        price: float,
        tf: str,
        profile: str,
        payload: Dict[str, Any],
    ) -> Optional[ActiveTrade]:
        pos = self.paper_broker.get_position(symbol)
        net_qty = pos.quantity if pos else 0
        trade = self.active_trades.get(symbol)
        direction = "LONG" if net_qty > 0 else "SHORT" if net_qty < 0 else None
        if trade and direction and trade.side != direction:
            self._force_finalize_trade(symbol, trade, price, "reverse")
            trade = None
        if direction is None:
            return trade
        if trade is None or trade.quantity == 0:
            entry_price = pos.avg_price or price
            planned_risk = max(
                1e-6,
                self.paper_capital
                * self.sizer_config.risk_per_trade_pct
                * max(1, abs(net_qty) / max(1, self.default_lot_size)),
            )
            meta = {
                "tf": tf,
                "profile": profile,
                "vol_regime": (payload or {}).get("vol_regime"),
                "trend_context": (payload or {}).get("trend_context"),
                "playbook": (payload or {}).get("playbook"),
                "reason": (payload or {}).get("reason"),
                "strategy_code": (payload or {}).get("strategy_code"),
            }
            trade = ActiveTrade(
                trade_id=f"{symbol}-{uuid.uuid4().hex[:10]}",
                signal_id=signal_id or self.last_signal_ids.get(symbol, ""),
                symbol=symbol,
                strategy=strategy or self.strategy_name,
                side=direction,
                entry_ts=datetime.now(timezone.utc),
                entry_price=entry_price,
                planned_risk=planned_risk,
                quantity=net_qty,
                initial_size=abs(net_qty),
                meta=meta,
                last_qty=net_qty,
                sl_price=payload.get("sl_price"),
                tp_price=payload.get("tp_price"),
                atr_method=str(payload.get("atr_method") or ""),
                atr_value=payload.get("atr_value"),
                product_type=self._resolve_product_type(symbol),
            )
            self.active_trades[symbol] = trade
        else:
            if abs(net_qty) > abs(trade.last_qty):
                trade.adds += 1
            elif abs(net_qty) < abs(trade.last_qty):
                trade.reduces += 1
            trade.quantity = net_qty
            trade.entry_price = pos.avg_price or trade.entry_price
            trade.meta.setdefault("tf", tf)
            trade.meta.setdefault("profile", profile)
            trade.meta.setdefault("vol_regime", (payload or {}).get("vol_regime"))
            trade.meta.setdefault("trend_context", (payload or {}).get("trend_context"))
            if payload and payload.get("strategy_code"):
                trade.meta["strategy_code"] = payload.get("strategy_code")
            if trade.sl_price is None and payload.get("sl_price") is not None:
                trade.sl_price = payload.get("sl_price")
            if trade.tp_price is None and payload.get("tp_price") is not None:
                trade.tp_price = payload.get("tp_price")
        trade.last_qty = net_qty
        return trade

    def _compute_realized_pct(self, realized_delta: float, trade: Optional[ActiveTrade]) -> float:
        if not trade:
            return 0.0
        denom = trade.entry_price * max(1, trade.initial_size)
        if denom == 0:
            return 0.0
        return (realized_delta / denom) * 100.0

    def _update_trade_after_order(
        self,
        symbol: str,
        trade: Optional[ActiveTrade],
        realized_delta: float,
        price: float,
        exit_reason: str,
    ) -> None:
        trade = trade or self.active_trades.get(symbol)
        if not trade:
            return
        if realized_delta:
            trade.realized_pnl += realized_delta
        if exit_reason:
            trade.exit_reason = exit_reason
            trade.exit_detail = exit_reason
            trade.exit_price = price
            trade.exit_ts = datetime.now(timezone.utc)
        pos = self.paper_broker.get_position(symbol)
        net_qty = pos.quantity if pos else 0
        trade.quantity = net_qty
        trade.last_qty = net_qty
        direction = 1 if trade.side == "LONG" else -1
        if direction == 1 and net_qty < 0:
            self._force_finalize_trade(symbol, trade, price, exit_reason or "reverse")
            return
        if direction == -1 and net_qty > 0:
            self._force_finalize_trade(symbol, trade, price, exit_reason or "reverse")
            return
        if net_qty == 0:
            trade.exit_price = trade.exit_price or price
            if not trade.exit_reason:
                trade.exit_reason = exit_reason or "closed"
            trade.exit_ts = trade.exit_ts or datetime.now(timezone.utc)
            self._finalize_trade(symbol, trade)

    def _force_finalize_trade(self, symbol: str, trade: ActiveTrade, price: float, reason: str) -> None:
        trade.exit_price = price
        trade.exit_reason = reason
        trade.exit_detail = reason
        trade.exit_ts = datetime.now(timezone.utc)
        self._finalize_trade(symbol, trade)

    def _finalize_trade(self, symbol: str, trade: ActiveTrade) -> None:
        trade.exit_ts = trade.exit_ts or datetime.now(timezone.utc)
        r_multiple = trade.realized_pnl / max(1e-6, trade.planned_risk)
        trade_dict = {
            "trade_id": trade.trade_id,
            "signal_id": trade.signal_id,
            "symbol": trade.symbol,
            "strategy": trade.strategy,
            "side": trade.side,
            "entry_ts": trade.entry_ts,
            "exit_ts": trade.exit_ts,
            "bars_in_trade": trade.bars_in_trade,
            "entry_price": trade.entry_price,
            "exit_price": trade.exit_price or trade.entry_price,
            "initial_size": trade.initial_size,
            "realized_pnl": trade.realized_pnl,
            "planned_risk": trade.planned_risk,
            "r_multiple": r_multiple,
            "max_favorable_excursion": trade.max_favorable_excursion,
            "max_adverse_excursion": trade.max_adverse_excursion,
            "adds": trade.adds,
            "reduces": trade.reduces,
            "exit_reason": trade.exit_reason,
            "exit_detail": trade.exit_detail,
            "meta": trade.meta,
            "sl_price": trade.sl_price,
            "tp_price": trade.tp_price,
            "atr_method": trade.atr_method,
            "atr_value": trade.atr_value,
        }
        row = finalize_trade(trade_dict)
        self._append_trade_row(row)
        self.signal_quality.update_trade_outcome(trade_dict)
        logger.info(
            "journal: trade closed trade_id=%s symbol=%s strategy=%s pnl=%.2f r=%.2f exit=%s",
            trade.trade_id,
            trade.symbol,
            trade.strategy,
            trade.realized_pnl,
            r_multiple,
            trade.exit_reason or "closed",
        )
        self.active_trades.pop(symbol, None)

    def _append_trade_row(self, row: Dict[str, Any]) -> None:
        day_dir = self.journal.latest_journal_path_for_today().parent
        path = day_dir / "trades.csv"
        file_exists = path.exists()
        with path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=TRADE_JOURNAL_FIELDS)
            if not file_exists:
                writer.writeheader()
            ordered = {field: row.get(field, "") for field in TRADE_JOURNAL_FIELDS}
            writer.writerow(ordered)

    def _age_trades(self) -> None:
        if not self.active_trades:
            return
        for symbol, trade in self.active_trades.items():
            last = self.last_prices.get(symbol, trade.entry_price)
            trade.update_price(last)
            trade.bars_in_trade += 1

    # -------------------------------------------------------------------------
    # Risk / portfolio meta
    # -------------------------------------------------------------------------

    def _compute_portfolio_meta(self) -> Dict[str, Any]:
        """
        Compute portfolio-level metrics for risk and analytics.

        Returns dict with:
        - paper_capital
        - total_realized_pnl
        - total_unrealized_pnl
        - equity
        - total_notional
        """
        total_realized = 0.0
        total_unrealized = 0.0
        total_notional = 0.0

        for symbol, pos in self.paper_broker.get_all_positions().items():
            last_price = self.last_prices.get(symbol, pos.avg_price or 0.0)
            notional = abs(last_price * pos.quantity)
            total_notional += notional

            total_realized += float(pos.realized_pnl or 0.0)

            if pos.quantity > 0:
                unreal = (last_price - pos.avg_price) * pos.quantity
            elif pos.quantity < 0:
                unreal = (pos.avg_price - last_price) * abs(pos.quantity)
            else:
                unreal = 0.0
            total_unrealized += unreal

        equity = self.paper_capital + total_realized + total_unrealized
        gross_limit = equity * self.sizer_config.max_exposure_pct
        free_notional = max(0.0, gross_limit - total_notional)

        meta = {
            "paper_capital": self.paper_capital,
            "total_realized_pnl": total_realized,
            "total_unrealized_pnl": total_unrealized,
            "equity": equity,
            "total_notional": total_notional,
            "free_notional": free_notional,
        }
        if self.regime_detector:
            meta["market_regime"] = self.regime_detector.current_regime()
            meta["regime_snapshot"] = self.regime_detector.snapshot()
        else:
            meta["market_regime"] = Regime.UNKNOWN.value
        
        # Add expiry status for active underlyings
        try:
            from core.expiry_calendar import build_expiry_context
            import pytz
            
            now_ist = datetime.now(pytz.timezone("Asia/Kolkata"))
            expiry_status = {}
            is_expiry_day_any = False
            
            # Collect expiry info for all underlyings
            for logical in self.logical_underlyings:
                try:
                    context = build_expiry_context(logical, now_ist)
                    expiry_status[logical] = {
                        "is_expiry_day": context.get("is_expiry_day", False),
                        "is_expiry_week": context.get("is_expiry_week", False),
                        "next_expiry": context.get("next_expiry_dt"),
                    }
                    if context.get("is_expiry_day"):
                        is_expiry_day_any = True
                except Exception as exc:
                    logger.debug("Failed to get expiry info for %s: %s", logical, exc)
            
            if expiry_status:
                meta["expiry_status"] = expiry_status
                meta["is_expiry_day_any"] = is_expiry_day_any
        except Exception as exc:
            logger.debug("Failed to add expiry status to meta: %s", exc)
        
        return meta

    def _build_signal_context(
        self,
        *,
        symbol: str,
        strategy: str,
        side: str,
        price: float,
        regime: str,
        indicators: Optional[Dict[str, Any]],
        decision_conf: float,
    ) -> SignalContext:
        direction = "LONG" if side.upper() == "BUY" else "SHORT"
        risk_per_trade = float(self.paper_capital * self.sizer_config.risk_per_trade_pct)
        atr = float(indicators.get("atr")) if indicators and indicators.get("atr") else None
        volatility = atr or float(indicators.get("volatility")) if indicators else None
        return SignalContext(
            symbol=symbol,
            strategy=strategy,
            timestamp=datetime.now(timezone.utc),
            direction=direction,
            regime=regime or "",
            atr=atr,
            volatility=volatility,
            price=price,
            risk_per_trade=risk_per_trade,
            raw_signal_strength=max(0.0, float(decision_conf or 0.0)),
        )

    def _check_risk(self) -> None:
        # Per-symbol loss limits
        self._check_symbol_risk()

        # Global daily loss limit (realized only)
        meta = self._compute_portfolio_meta()
        total_realized = meta["total_realized_pnl"]

        if total_realized <= -self.max_daily_loss:
            logger.warning(
                "Max daily loss reached (realized=%.2f <= -%.2f). Stopping engine.",
                total_realized,
                self.max_daily_loss,
            )
            self.running = False
            log_event(
                "RISK_BLOCK",
                "Max daily loss reached, halting engine",
                strategy_id=self.strategy_name,
                extra={"realized": round(total_realized, 2)},
                level=logging.WARNING,
            )

    def _check_symbol_risk(self) -> None:
        """
        Check per-symbol realized PnL and ban symbols whose loss exceeds per_symbol_max_loss.
        """
        for symbol, pos in self.paper_broker.get_all_positions().items():
            realized = float(pos.realized_pnl or 0.0)
            if symbol in self.banned_symbols:
                continue
            if realized <= -self.per_symbol_max_loss:
                logger.warning(
                    "Per-symbol loss limit reached for %s (realized=%.2f <= -%.2f). "
                    "Disabling further trades in this symbol for this session.",
                    symbol,
                    realized,
                    self.per_symbol_max_loss,
                )
                self.banned_symbols.add(symbol)
                log_event(
                    "RISK_BLOCK",
                    "Per-symbol loss limit reached",
                    symbol=symbol,
                    strategy_id=self.strategy_name,
                    extra={"realized": round(realized, 2)},
                    level=logging.WARNING,
                )

    def _build_sizer_config(self) -> SizerConfig:
        risk_cfg = self.cfg.risk
        trading_cfg = self.cfg.trading

        max_exposure = float(
            risk_cfg.get(
                "max_gross_exposure_pct",
                risk_cfg.get(
                    "max_exposure_pct",
                    trading_cfg.get("max_notional_multiplier", 2.0),
                ),
            )
        )

        return SizerConfig(
            max_exposure_pct=max_exposure,
            risk_per_trade_pct=float(
                risk_cfg.get("risk_per_trade_pct", 0.005)
            ),
            min_order_notional=float(
                risk_cfg.get("min_order_notional", 5000.0)
            ),
            max_order_notional_pct=float(
                risk_cfg.get("max_order_notional_pct", 0.2)
            ),
            max_trades=_safe_int(
                risk_cfg.get(
                    "max_concurrent_trades",
                    trading_cfg.get("max_open_positions", 10),
                ),
                10,
            ),
            risk_scale_min=float(
                risk_cfg.get("risk_scale_min", 0.3)
            ),
            risk_scale_max=float(
                risk_cfg.get("risk_scale_max", 2.0)
            ),
            risk_down_threshold=float(
                risk_cfg.get("risk_down_threshold", -0.02)
            ),
            risk_up_threshold=float(
                risk_cfg.get("risk_up_threshold", 0.02)
            ),
        )

    def _load_portfolio_state(self) -> PortfolioState:
        meta = self._compute_portfolio_meta()
        fallback_positions = {
            symbol: pos.quantity
            for symbol, pos in self.paper_broker.get_all_positions().items()
        }
        return load_portfolio_state(
            self.state_path,
            capital=self.paper_capital,
            fallback_meta=meta,
            fallback_positions=fallback_positions,
            config=self.sizer_config,
        )

    # -------------------------------------------------------------------------
    # Cost / trade quality helpers
    # -------------------------------------------------------------------------

    def _estimate_costs(
        self,
        symbol: str,
        side: str,
        qty: int,
        price: float,
        segment: str,
    ) -> CostBreakdown:
        if self.cost_model:
            return self.cost_model.estimate(symbol, side, qty, price, segment)
        return CostBreakdown(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    def _build_trade_proposal(
        self,
        symbol: str,
        side: str,
        qty: int,
        price: float,
        logical: Optional[str] = None,
    ) -> TradeProposal:
        decision = self._last_meta_decisions.get(symbol)
        style = decision.style if decision else "intraday"
        timeframe = decision.timeframe if decision else "5m"
        _ = logical  # reserved for future use (strategy-specific heuristics)
        return TradeProposal(
            symbol=symbol,
            side=side,
            qty=qty,
            price=price,
            style=style,
            timeframe=timeframe,
            raw_edge_bps=self.default_raw_edge_bps,
        )

    def _segment_for_symbol(self, symbol: str) -> str:
        _ = symbol
        return "FNO"

    def _approximate_edge_bps(
        self,
        symbol: str,
        side: str,
        price: float,
    ) -> float:
        _ = (symbol, side, price)
        return self.default_raw_edge_bps

    def _maybe_apply_trade_filters(
        self,
        symbol: str,
        side: str,
        qty: int,
        price: float,
        logical_name: str,
        portfolio_state: PortfolioState,
    ) -> Tuple[bool, Dict[str, Any]]:
        if qty <= 0:
            return False, {}

        if self.cost_model is None or self.trade_quality_filter is None:
            return True, {}

        segment = self._segment_for_symbol(symbol)
        costs = self.cost_model.estimate(symbol, side, qty, price, segment)
        proposal = self._build_trade_proposal(
            symbol, side, qty, price, logical_name
        )
        proposal.raw_edge_bps = self._approximate_edge_bps(
            symbol, side, price
        )

        decision = self.trade_quality_filter.evaluate(
            proposal, costs, portfolio_state
        )
        if not decision.accept:
            logger.info(
                "Trade rejected by quality filter: symbol=%s side=%s qty=%s reason=%s",
                symbol,
                side,
                qty,
                decision.reason,
            )
            trade_monitor.increment("entries_blocked_risk")
            reason = decision.reason or "quality_filter_block"
            self._record_trade_flow_event(
                "risk_blocks",
                reason=reason,
                bucket="risk",
            )
            log_event(
                "RISK_BLOCK",
                "Trade quality filter rejected order",
                symbol=symbol,
                strategy_id=self.strategy_name,
                extra={
                    "side": side,
                    "qty": qty,
                    "reason": reason,
                },
            )
            return False, {}

        logger.info(
            "Trade accepted by quality filter: symbol=%s side=%s qty=%s reason=%s",
            symbol,
            side,
            qty,
            decision.reason,
        )
        payload = {
            "costs": {
                "brokerage": costs.brokerage,
                "exchange_tx": costs.exchange_tx,
                "stt": costs.stt,
                "gst": costs.gst,
                "stamp_duty": costs.stamp_duty,
                "other": costs.other,
                "total": costs.total,
            },
            "trade_quality_reason": decision.reason,
        }
        return True, payload

    # -------------------------------------------------------------------------
    # Meta-engine adapter
    # -------------------------------------------------------------------------

    def _meta_allows_trade(self, symbol: str, required_style: str) -> bool:
        if not self.meta_engine:
            return True

        decision = self.meta_engine.decide_for_symbol(symbol)
        self._last_meta_decisions[symbol] = decision

        if decision is None:
            return self.meta_engine.allow_fallback

        if decision.style != required_style:
            return False

        if decision.confidence <= 0.0:
            return False

        return True
