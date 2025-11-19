from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from types import SimpleNamespace

from core.config import AppConfig
from core.modes import TradingMode
from core.market_session import is_market_open
from core.pattern_filters import should_trade_trend
from core.strategy_tags import Profile
from core.state_store import record_strategy_signal
from core.strategy_metrics import StrategyMetricsTracker
from core.strategy_registry import STRATEGY_REGISTRY
from core.universe import fno_underlyings
from broker.execution_router import ExecutionRouter
from broker.paper_broker import PaperBroker
from broker.kite_client import KiteClient
from kiteconnect import KiteConnect
from configs.timeframes import MULTI_TF_CONFIG, resolve_multi_tf_config
from data.broker_feed import BrokerFeed
from data.instruments import resolve_fno_symbols
from data.options_instruments import OptionUniverse
from strategies.base import Decision
from strategies.fno_intraday_trend import (
    FnoIntradayTrendStrategy,
    build_reason,
)
from analytics.trade_recorder import TradeRecorder
from analytics.multi_timeframe_engine import MultiTimeframeEngine
from analytics.telemetry_bus import (
    publish_engine_health,
    publish_signal_event,
    publish_order_event,
    publish_position_event,
    publish_decision_trace,
)
from engine.meta_strategy_engine import (
    MetaDecision,
    MetaStrategyEngine,
    STYLE_INTRADAY,
)
from risk.position_sizer import DynamicPositionSizer, PortfolioState, SizerConfig, load_portfolio_state
from risk.cost_model import CostBreakdown, CostConfig, CostModel
from risk.trade_quality import (
    QualityConfig,
    TradeDecision,
    TradeProposal,
    TradeQualityFilter,
)
from risk.factory import build_cost_model, build_trade_quality_filter
from core.regime_detector import Regime, shared_regime_detector
from core.trade_throttler import (
    DEFAULT_EXPECTED_EDGE_RUPEES,
    TradeThrottler,
    build_throttler_config,
)

# Strategy Engine v2 (optional - fallback if not available)
try:
    from core.strategy_engine_v2 import StrategyEngineV2, StrategyState
    from strategies.ema20_50_intraday_v2 import EMA2050IntradayV2
    from core.market_data_engine import MarketDataEngine
    from core.market_context import MarketContext, initialize_market_context
    STRATEGY_ENGINE_V2_AVAILABLE = True
    MARKET_CONTEXT_AVAILABLE = True
except ImportError:
    STRATEGY_ENGINE_V2_AVAILABLE = False
    MARKET_CONTEXT_AVAILABLE = False
    StrategyEngineV2 = None
    StrategyState = None
    EMA2050IntradayV2 = None
    MarketDataEngine = None
    MarketContext = None
    initialize_market_context = None

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = BASE_DIR / "artifacts"
STATE_PATH = ARTIFACTS_DIR / "paper_state.json"
PROFILE_INTRADAY = {"1m", "3m", "5m"}
PROFILE_SWING = {"15m", "30m", "1h", "60m"}

def _profile_from_tf(tf: str) -> str:
    tf_norm = (tf or "").lower()
    if tf_norm in PROFILE_INTRADAY:
        return Profile.INTRADAY.value
    if tf_norm in PROFILE_SWING:
        return Profile.SWING.value
    return Profile.INTRADAY.value


class OptionsPaperEngine:
    """
    Paper engine for index options (NIFTY, BANKNIFTY, FINNIFTY).

    - Uses underlying FUT LTP as "spot".
    - For each logical index:
      - Resolves current ATM CE and ATM PE on nearest expiry.
      - Applies the existing FnoIntradayTrendStrategy on option prices.
      - Places PAPER orders via ExecutionRouter.
      - Records signals and orders via TradeRecorder.
    - Only trades when market_session.is_market_open() is True.
    - Enforces per-symbol loss limit ("kill switch") on options symbols.
    - Enforces per-trade max loss on open option positions.
    """

    def __init__(
        self,
        cfg: AppConfig,
        kite: KiteConnect | None = None,
        cost_model: Optional[CostModel] = None,
        trade_quality_filter: Optional[TradeQualityFilter] = None,
        *,
        trading_mode: Optional[TradingMode] = None,
        artifacts_dir: Optional[Path] = None,
        data_feed: Optional[BrokerFeed] = None,
        kite_client: Optional[KiteClient] = None,
        logical_underlyings_override: Optional[List[str]] = None,
        underlying_futs_override: Optional[Dict[str, str]] = None,
        option_universe_override: Optional[OptionUniverse] = None,
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

        self.paper_broker = PaperBroker()
        self.kite: KiteConnect | None = kite
        self.kite_client: KiteClient | SimpleNamespace | None = kite_client

        if self.kite_client is not None:
            if self.kite is None:
                self.kite = self.kite_client.api
        elif self.kite is not None:
            self.kite_client = SimpleNamespace(api=self.kite)
        elif self.mode == TradingMode.REPLAY:
            self.kite_client = None
            self.kite = None
        else:
            self.kite_client = KiteClient()
            self.kite = self.kite_client.api

        feed_override = data_feed
        if feed_override is not None:
            self.feed = feed_override
        else:
            if self.kite is None:
                raise RuntimeError("Data feed override is required when Kite client is disabled.")
            self.feed = BrokerFeed(self.kite)

        # Ensure logical_underlyings exists before later checks
        self.logical_underlyings: List[str] = []
        trading = getattr(cfg, "trading", None) or {}
        lu = (
            trading.get("logical_underlyings")
            or trading.get("fno_universe")
            or []
        )
        if isinstance(lu, str):
            lu = [lu]
        self.logical_underlyings = [str(x).strip().upper() for x in lu if x]

        self.strategy_name = str(getattr(FnoIntradayTrendStrategy, "name", "UNKNOWN"))
        self.strategy_mode = str(getattr(FnoIntradayTrendStrategy, "mode", "UNKNOWN"))
        self.primary_strategy_code = self._resolve_primary_strategy_code()
        self.strategy_metrics = StrategyMetricsTracker(default_code=self.primary_strategy_code)
        self.recorder = TradeRecorder()

        raw_multi_tf = self.cfg.trading.get("multi_tf_config")
        overrides = raw_multi_tf if isinstance(raw_multi_tf, list) else None
        self.multi_tf_config = resolve_multi_tf_config(overrides)
        self.default_timeframe = (self.multi_tf_config[0].get("timeframe") if self.multi_tf_config else None) or str(
            getattr(FnoIntradayTrendStrategy, "timeframe", "5m")
        )
        self.strategy_instances: List[FnoIntradayTrendStrategy] = []
        self.strategies_by_logical: Dict[str, List[FnoIntradayTrendStrategy]] = {}
        self.regime_detector = shared_regime_detector
        if self.logical_underlyings:
            self.regime_detector.set_primary_symbol(self.logical_underlyings[0])

        self.router = ExecutionRouter(mode=self.mode, paper_broker=self.paper_broker, kite_client=self.kite_client)

        cfg_opts = self.cfg.trading.get("options_underlyings", []) or []
        logical_opts = [str(sym).strip().upper() for sym in cfg_opts if sym]
        if not logical_opts:
            cfg_fno = self.cfg.trading.get("fno_universe", []) or []
            logical_opts = [str(sym).strip().upper() for sym in cfg_fno if sym]
        if not logical_opts:
            logical_opts = fno_underlyings()
        if logical_underlyings_override:
            logical_opts = [str(sym).strip().upper() for sym in logical_underlyings_override if sym]
        self.logical_underlyings = logical_opts

        logger.info("Options underlyings from config: %s", self.logical_underlyings)

        # Underlying FUT mapping for spot reference
        if underlying_futs_override is not None:
            self.underlying_futs = {str(k).strip().upper(): str(v).strip().upper() for k, v in underlying_futs_override.items()}
        else:
            if self.kite_client is None:
                raise RuntimeError("Underlying future mapping requires Kite client or explicit override.")
            self.underlying_futs = resolve_fno_symbols(self.logical_underlyings, kite_client=self.kite_client)
        logger.info("Resolved underlying FUTs for options: %s", self.underlying_futs)

        self.strategy_instances = self._build_strategy_instances()

        # NFO option universe
        if option_universe_override is not None:
            self.option_universe = option_universe_override
        else:
            if self.kite_client is None:
                raise RuntimeError("Option universe requires Kite client or explicit override.")
            self.option_universe = OptionUniverse(self.kite_client)

        self.sleep_sec = 5
        self.fno_exchange = "NFO"
        self.running = True

        # Cache last known prices for P&L snapshots
        self.last_prices: Dict[str, float] = {}
        self.position_price_refresh_interval = float(self.cfg.trading.get("position_price_refresh_sec", 5.0))
        self._last_position_price_refresh = 0.0

        # Snapshot every N loops
        self.snapshot_every_n_loops = 5
        self._loop_counter = 0

        # Capital and basic risk meta (reuse paper_capital from config)
        self.paper_capital: float = float(self.cfg.trading.get("paper_capital", 500000))
        self.per_symbol_max_loss: float = float(self.cfg.trading.get("per_symbol_max_loss", 3000))
        self.max_loss_pct_per_trade: float = float(self.cfg.trading.get("max_loss_pct_per_trade", 0.01))

        # Per-symbol kill switch state for options (tradingsymbols that are "banned" for the session)
        self.banned_symbols: set[str] = set()

        self.artifacts_dir = artifacts_dir or ARTIFACTS_DIR
        self.state_path = self.artifacts_dir / "paper_state.json"
        self.sizer_config = self._build_sizer_config()
        self.position_sizer = DynamicPositionSizer(self.sizer_config)
        self.default_lot_size = int(self.cfg.trading.get("default_lot_size", 1))
        self.meta_cfg = self.cfg.meta
        self.meta_enabled = bool(self.meta_cfg.get("enabled", True))
        if self.mode == TradingMode.REPLAY:
            self.meta_enabled = False
        self.multi_tf_engine: Optional[MultiTimeframeEngine] = None
        self.meta_engine: Optional[MetaStrategyEngine] = None
        self._last_meta_decisions: Dict[str, Optional[MetaDecision]] = {}
        if self.meta_enabled:
            meta_symbols = set(self.logical_underlyings)
            self.multi_tf_engine = MultiTimeframeEngine(
                symbols=meta_symbols,
                signals_path=self.artifacts_dir / "signals.csv",
            )
            self.meta_engine = MetaStrategyEngine(
                multi_engine=self.multi_tf_engine,
                config=self.meta_cfg,
            )

        risk_cfg = self.cfg.risk
        self.cost_model: Optional[CostModel] = cost_model if cost_model is not None else build_cost_model(self.cfg.raw)
        self.trade_quality_filter: Optional[TradeQualityFilter] = (
            trade_quality_filter if trade_quality_filter is not None else build_trade_quality_filter(self.cfg.raw)
        )
        self.default_raw_edge_bps = float(risk_cfg.get("default_raw_edge_bps", 20.0))
        throttler_raw = self.cfg.trading.get("trade_throttler")
        throttler_config = build_throttler_config(throttler_raw)
        self.trade_throttler = TradeThrottler(
            config=throttler_config,
            capital=self.paper_capital,
        )
        
        # Initialize MarketDataEngine (for v2 strategies)
        self.market_data_engine = None
        if STRATEGY_ENGINE_V2_AVAILABLE and MarketDataEngine and self.kite:
            try:
                cache_dir = self.artifacts_dir / "market_data"
                cache_dir.mkdir(parents=True, exist_ok=True)
                universe_snapshot = {}  # Can be populated from universe
                self.market_data_engine = MarketDataEngine(
                    self.kite,
                    universe_snapshot,
                    cache_dir=cache_dir
                )
            except Exception as exc:
                logger.warning("Failed to initialize MarketDataEngine: %s", exc)
                self.market_data_engine = None
        
        # Initialize Strategy Engine v2 (optional, based on config)
        strategy_engine_config = self.cfg.raw.get("strategy_engine", {})
        strategy_engine_version = strategy_engine_config.get("version", 1)
        self.strategy_engine_v2 = None
        
        if strategy_engine_version == 2 and STRATEGY_ENGINE_V2_AVAILABLE:
            logger.info("Initializing Strategy Engine v2 for options trading")
            try:
                self.strategy_engine_v2 = StrategyEngineV2.from_config(self.cfg.raw, logger)
                
                # Set engines
                if self.market_data_engine:
                    self.strategy_engine_v2.mde = self.market_data_engine
                    self.strategy_engine_v2.market_data = self.market_data_engine
                    self.strategy_engine_v2.market_data_engine = self.market_data_engine
                self.strategy_engine_v2.regime_engine = self.regime_detector
                
                logger.info(
                    "Strategy Engine v2 initialized for options with %d strategies",
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
                logger.error("Failed to initialize Strategy Engine v2 for options: %s", exc, exc_info=True)
                self.strategy_engine_v2 = None
    
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

    def _build_strategy_instances(self) -> List[FnoIntradayTrendStrategy]:
        instances: List[FnoIntradayTrendStrategy] = []
        self.strategies_by_logical = {}
        if not getattr(self, "logical_underlyings", None):
            return instances
        for logical in self.logical_underlyings:
            per_symbol: List[FnoIntradayTrendStrategy] = []
            for cfg in self.multi_tf_config or MULTI_TF_CONFIG:
                timeframe = str(cfg.get("timeframe") or self.default_timeframe)
                mode = str(cfg.get("mode") or self.strategy_mode)
                strat = FnoIntradayTrendStrategy(timeframe=timeframe)
                strat.logical = logical
                strat.timeframe = timeframe
                strat.mode = mode
                instances.append(strat)
                per_symbol.append(strat)
            self.strategies_by_logical[logical] = per_symbol
        return instances

    def _ensure_decision(self, strat: FnoIntradayTrendStrategy, raw: Decision | str | None) -> Decision:
        if isinstance(raw, Decision):
            mode = raw.mode or getattr(strat, "mode", self.strategy_mode)
            confidence = float(raw.confidence or 0.0)
            action = raw.action or "HOLD"
            reason = raw.reason or ""
            return Decision(action=action, reason=reason, mode=mode, confidence=confidence)

        action = str(raw or "HOLD").upper()
        if action not in {"BUY", "SELL", "EXIT", "HOLD"}:
            action = "HOLD"
        return Decision(action=action, reason="", mode=getattr(strat, "mode", self.strategy_mode), confidence=0.0)

    def _resolve_timeframe(self, preferred: Optional[str] = None) -> str:
        tf = preferred or self.default_timeframe
        return tf or "5m"

    def _resolve_primary_strategy_code(self) -> str:
        preferred = (self.cfg.trading or {}).get("options_strategy_code")
        if isinstance(preferred, str) and preferred.strip():
            return preferred.strip()
        if "expiry_scalper" in STRATEGY_REGISTRY:
            return "expiry_scalper"
        if "ema20_50_intraday" in STRATEGY_REGISTRY:
            return "ema20_50_intraday"
        return next(iter(STRATEGY_REGISTRY.keys()), "expiry_scalper")

    def _infer_strategy_code(self, symbol: str, override: Optional[str] = None) -> Optional[str]:
        return self.strategy_metrics.infer(symbol, override=override)

    def _record_regime_sample(self, logical_symbol: str, price: float) -> None:
        if not self.regime_detector or not logical_symbol or price is None or price <= 0:
            return
        try:
            self.regime_detector.update(symbol=logical_symbol, close=float(price))
        except Exception as exc:  # noqa: BLE001
            logger.debug("Regime detector update failed for %s: %s", logical_symbol, exc)

    def run_forever(self) -> None:
        if not self.logical_underlyings:
            logger.error("No options_underlyings configured. Aborting.")
            publish_engine_health(
                "options_paper_engine",
                "error",
                {"mode": self.mode.value, "error": "no_underlyings"}
            )
            return

        logger.info(
            "Starting OptionsPaperEngine for underlyings=%s (mode=%s)",
            self.logical_underlyings,
            self.mode.value,
        )
        
        # Publish engine startup telemetry
        publish_engine_health(
            "options_paper_engine",
            "starting",
            {
                "mode": self.mode.value,
                "underlyings": self.logical_underlyings,
                "strategy_name": self.strategy_name,
            }
        )

        try:
            while self.running:
                try:
                    if not is_market_open():
                        logger.info("Market appears closed (OptionsPaperEngine); sleeping...")
                        time.sleep(self.sleep_sec)
                        continue

                    self._loop_once()
                    time.sleep(self.sleep_sec)
                except KeyboardInterrupt:
                    logger.info("OptionsPaperEngine interrupted by user.")
                    self.running = False
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Unexpected error in options engine loop: %s", exc)
                    time.sleep(self.sleep_sec)
        finally:
            # Publish engine shutdown telemetry
            publish_engine_health(
                "options_paper_engine",
                "stopped",
                {"mode": self.mode.value}
            )

    def _loop_once(self) -> None:
        self._loop_counter += 1

        # Step 1: get underlying FUT spots
        spots: Dict[str, float] = {}
        for logical_base, fut_ts in self.underlying_futs.items():
            try:
                price = self.feed.get_ltp(fut_ts, exchange=self.fno_exchange)
                spots[logical_base] = price
                self.last_prices[fut_ts] = price
                if price is not None:
                    self._record_regime_sample(logical_base, price)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Error fetching FUT LTP for logical=%s symbol=%s: %s", logical_base, fut_ts, exc)

        if not spots:
            logger.debug("No underlying spots available this loop; skipping.")
            return

        # Step 2: resolve ATM options for each underlying
        atm_map = self.option_universe.resolve_atm_for_many(spots)

        price_cache: Dict[str, float] = {}

        def _ltp(symbol: str) -> float:
            if symbol not in price_cache:
                price = self.feed.get_ltp(symbol, exchange=self.fno_exchange)
                price_cache[symbol] = price
                self.last_prices[symbol] = price
            return price_cache[symbol]

        # Step 3: process each strategy instance (per logical + timeframe)
        for strat in self.strategy_instances:
            logical_base = getattr(strat, "logical", "")
            if not logical_base:
                continue
            option_series = atm_map.get(logical_base)
            if not option_series:
                continue

            strategy_label = getattr(strat, "name", self.strategy_name)
            tf_label = self._resolve_timeframe(getattr(strat, "timeframe", None))

            for opt_type, ts in option_series.items():  # opt_type in {"CE", "PE"}
                if ts in self.banned_symbols:
                    logger.info("Option %s is banned for this session due to per-symbol loss limit; skipping.", ts)
                    continue

                if not self._meta_allows_trade(ts, STYLE_INTRADAY):
                    logger.debug(
                        "Meta engine filtered option %s (%s_%s) for lack of intraday conviction.",
                        ts,
                        logical_base,
                        opt_type,
                    )
                    continue

                try:
                    price = _ltp(ts)
                    bar = {"close": price, "tf": tf_label, "option_type": opt_type}
                    raw_decision = strat.on_bar(ts, bar)
                    decision = self._ensure_decision(strat, raw_decision)
                    signal = decision.action
                    mode_label = decision.mode or getattr(strat, "mode", self.strategy_mode)
                    base_logical = f"{logical_base}_{opt_type}"
                    logical_tagged = f"{base_logical}|{strategy_label}"

                    logger.info(
                        "Underlying=%s tf=%s mode=%s strategy=%s option=%s type=%s price=%.2f signal=%s",
                        logical_base,
                        tf_label,
                        mode_label,
                        strategy_label,
                        ts,
                        opt_type,
                        price,
                        signal,
                    )

                    indicators = strat.get_latest_indicators(ts) or {}
                    regime = strat.get_latest_regime(ts)
                    market_regime = (
                        self.regime_detector.current_regime(logical_base)
                        if self.regime_detector
                        else Regime.UNKNOWN.value
                    )
                    if (
                        strategy_label == "EMA_TREND"
                        and signal in {"BUY", "SELL"}
                        and market_regime in {Regime.CHOP.value, Regime.UNKNOWN.value}
                    ):
                        logger.warning(
                            "[QUALITY_VETO] EMA_TREND blocked due to regime=%s option=%s logical=%s",
                            market_regime,
                            ts,
                            logical_base,
                        )
                        decision = Decision(
                            action="HOLD",
                            reason=f"regime_block_{market_regime.lower()}",
                            mode=decision.mode,
                            confidence=decision.confidence,
                        )
                        signal = decision.action
                    meta_decision = self._last_meta_decisions.get(ts)
                    profile = _profile_from_tf(tf_label)
                    pattern_ok, pattern_reason = should_trade_trend(
                        logical=logical_tagged,
                        symbol=ts,
                        tf=tf_label,
                        indicators=indicators,
                        price=price,
                    )
                    base_reason = build_reason(price, indicators, regime, signal)
                    final_signal = signal
                    if signal in ("BUY", "SELL"):
                        if not pattern_ok:
                            final_signal = "HOLD"
                            reason = pattern_reason or decision.reason or "pattern_filter_block"
                        else:
                            reason_parts = [decision.reason, pattern_reason, base_reason]
                            reason = "|".join(part for part in reason_parts if part)
                    else:
                        reason_parts = [pattern_reason, decision.reason, base_reason]
                        reason = "|".join(part for part in reason_parts if part)

                    trend_context = regime or ""
                    vol_spike_flag = bool(indicators.get("vol_spike")) if indicators else False
                    vol_regime = "HIGH" if vol_spike_flag else ("NORMAL" if indicators else "")
                    htf_trend = meta_decision.timeframe if meta_decision else ""
                    playbook = pattern_reason or ""
                    adx_value = indicators.get("adx14") if indicators else None

                    signal_ts = self.recorder.log_signal(
                        logical=logical_tagged,
                        symbol=ts,
                        price=price,
                        signal=final_signal,
                        tf=tf_label,
                        reason=reason,
                        profile=profile,
                        mode=mode_label,
                        confidence=round(decision.confidence, 4),
                        trend_context=trend_context,
                        vol_regime=vol_regime,
                        htf_trend=htf_trend,
                        playbook=playbook,
                        ema20=indicators.get("ema20"),
                        ema50=indicators.get("ema50"),
                        ema100=indicators.get("ema100"),
                        ema200=indicators.get("ema200"),
                        rsi14=indicators.get("rsi14"),
                        atr=indicators.get("atr"),
                        adx14=indicators.get("adx14"),
                        adx=adx_value,
                        vwap=indicators.get("vwap"),
                        vol_spike=indicators.get("vol_spike"),
                        strategy=strategy_label,
                    )

                    if final_signal in ("BUY", "SELL"):
                        record_strategy_signal(self.primary_strategy_code, timestamp=signal_ts)
                        self._handle_signal(
                            ts,
                            final_signal,
                            price,
                            base_logical,
                            tf=tf_label,
                            profile=profile,
                            mode=mode_label,
                            strategy_name=strategy_label,
                            strategy_code=self.primary_strategy_code,
                            confidence=decision.confidence,
                            playbook=playbook,
                            reason=reason,
                            signal_timestamp=signal_ts,
                        )
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Error processing option logical=%s symbol=%s: %s", logical_base, ts, exc)

        # Step 4: enforce per-trade stop-loss on options positions
        self._enforce_per_trade_stop()

        # Step 5: snapshot state periodically (with meta)
        if self._loop_counter % self.snapshot_every_n_loops == 0:
            meta = self._compute_portfolio_meta()
            self.recorder.snapshot_paper_state(self.paper_broker, last_prices=self.last_prices, meta=meta)

        # Step 6: per-symbol risk check
        self._check_symbol_risk()

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
    ) -> None:
        tf = tf or self._resolve_timeframe()
        profile = profile or _profile_from_tf(tf)
        strategy_code_value = strategy_code or self.primary_strategy_code
        strategy_label = strategy_name or self.strategy_name
        mode_label = mode or self.strategy_mode
        confidence_value = float(confidence) if confidence is not None else 0.0
        playbook_value = playbook or ""
        reason_value = reason or ""
        if symbol in self.banned_symbols:
            logger.warning("Not placing options order for %s: symbol is banned by per-symbol loss limit.", symbol)
            return

        portfolio_state = self._load_portfolio_state()
        qty = self.position_sizer.size_order(
            portfolio_state,
            symbol=symbol,
            last_price=price,
            side=signal,
            lot_size=self.default_lot_size,
        )
        if qty == 0:
            logger.info(
                "Skipping %s options order for %s: position sizer returned zero qty (price=%.2f, free_notional=%.2f).",
                signal,
                symbol,
                price,
                portfolio_state.free_notional,
            )
            return

        side = signal
        if qty < 0:
            side = "SELL"
            qty = abs(qty)
            if side != signal:
                logger.info("Position sizer flipped signal %s to SELL for %s based on exposure.", signal, symbol)

        logical_name = logical or symbol
        prev_position = self.paper_broker.get_position(symbol)
        prev_position_qty = prev_position.quantity if prev_position else 0

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
            logger.warning(
                "[QUALITY_VETO] symbol=%s strategy=%s reason=%s",
                symbol,
                strategy_label,
                throttler_reason,
            )
            return

        self.strategy_metrics.remember(symbol, strategy_code_value)
        realized_before = self._realized_pnl(symbol)
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
        logger.info("Options order executed (mode=%s): %s", self.mode.value, order)

        extra_payload: Dict[str, Any] = {
            "status": getattr(order, "status", "FILLED"),
            "logical": logical_name,
            "strategy": strategy_label,
            "strategy_code": strategy_code_value,
            "mode": mode_label,
            "tf": tf,
            "confidence": confidence_value,
            "signal_timestamp": signal_timestamp,
            "playbook": playbook_value,
            "reason": reason_value,
            "market_regime": market_regime,
        }
        meta_decision = self._last_meta_decisions.get(symbol)
        if meta_decision:
            extra_payload["meta_style"] = meta_decision.style
            extra_payload["meta_tf"] = meta_decision.timeframe
            extra_payload["meta_conf"] = round(meta_decision.confidence, 3)
            extra_payload["meta_reason"] = meta_decision.reason
        if filter_payload:
            extra_payload.update(filter_payload)
        extra_payload["throttler_reason"] = throttler_reason
        extra_payload["expected_edge_rupees"] = expected_edge_rupees

        status = extra_payload["status"]
        realized_after = self._realized_pnl(symbol)
        pnl_delta = realized_after - realized_before
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

        post_position = self.paper_broker.get_position(symbol)
        post_qty = post_position.quantity if post_position else 0
        self.strategy_metrics.record_fill(
            symbol,
            prev_qty=prev_position_qty,
            new_qty=post_qty,
            pnl_delta=pnl_delta,
            strategy_code=strategy_code_value,
        )

        # Snapshot state right after the order as well
        meta = self._compute_portfolio_meta()
        self.recorder.snapshot_paper_state(self.paper_broker, last_prices=self.last_prices, meta=meta)

    def _enforce_per_trade_stop(self) -> None:
        """
        Enforce per-trade max loss on open options positions.
        LONG: (last - avg) / avg <= -max_loss_pct_per_trade -> close (SELL).
        SHORT: (avg - last) / avg <= -max_loss_pct_per_trade -> close (BUY).
        """
        if self.max_loss_pct_per_trade <= 0:
            return

        self._refresh_last_prices_for_positions()

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
                ret = (last - avg) / avg
                if ret <= -self.max_loss_pct_per_trade:
                    logger.warning(
                        "Per-trade stop-loss triggered for option %s (LONG): avg=%.2f last=%.2f loss=%.2f%% >= %.2f%%. "
                        "Closing position.",
                        symbol,
                        avg,
                        last,
                        abs(ret) * 100.0,
                        self.max_loss_pct_per_trade * 100.0,
                    )
                    self._close_position(symbol, "SELL", qty, last)
            elif qty < 0:
                ret = (avg - last) / avg
                if ret <= -self.max_loss_pct_per_trade:
                    logger.warning(
                        "Per-trade stop-loss triggered for option %s (SHORT): avg=%.2f last=%.2f loss=%.2f%% >= %.2f%%. "
                        "Closing position.",
                        symbol,
                        avg,
                        last,
                        abs(ret) * 100.0,
                        self.max_loss_pct_per_trade * 100.0,
                    )
                    self._close_position(symbol, "BUY", abs(qty), last)

    def _close_position(
        self,
        symbol: str,
        side: str,
        qty: int,
        price: float,
        *,
        strategy_code: Optional[str] = None,
    ) -> None:
        prev_position = self.paper_broker.get_position(symbol)
        prev_qty = prev_position.quantity if prev_position else 0
        code_for_metrics = self._infer_strategy_code(symbol, override=strategy_code)
        realized_before = self._realized_pnl(symbol)
        order = self.router.place_order(symbol, side, qty, price)
        logger.info("Options close-position order executed (mode=%s): %s", self.mode.value, order)

        status = getattr(order, "status", "FILLED")
        tf = self._resolve_timeframe()
        profile = _profile_from_tf(tf)
        extra_payload = {
            "reason": "per_trade_stop",
            "status": status,
            "tf": tf,
            "mode": self.strategy_mode,
            "strategy": self.strategy_name,
            "strategy_code": code_for_metrics,
            "confidence": 0.0,
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
        post_position = self.paper_broker.get_position(symbol)
        post_qty = post_position.quantity if post_position else 0
        self.strategy_metrics.record_fill(
            symbol,
            prev_qty=prev_qty,
            new_qty=post_qty,
            pnl_delta=pnl_delta,
            strategy_code=code_for_metrics,
        )

        meta = self._compute_portfolio_meta()
        self.recorder.snapshot_paper_state(self.paper_broker, last_prices=self.last_prices, meta=meta)
        realized_after = self._realized_pnl(symbol)
        pnl_delta = realized_after - realized_before
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

    def _realized_pnl(self, symbol: str) -> float:
        pos = self.paper_broker.get_position(symbol)
        return float(pos.realized_pnl if pos else 0.0)

    def _compute_portfolio_meta(self) -> Dict[str, Any]:
        """
        Compute portfolio-level metrics for options book.

        Returns dict with:
        - paper_capital
        - total_realized_pnl
        - total_unrealized_pnl
        - equity
        - total_notional
        """
        self._refresh_last_prices_for_positions()
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
        return meta

    def _refresh_last_prices_for_positions(self, force: bool = False) -> None:
        """
        Ensure we have LTPs for every open option symbol so state snapshots stay accurate.
        """
        if not self.paper_broker.positions:
            return

        now = time.time()
        if not force and self.position_price_refresh_interval > 0:
            if now - getattr(self, "_last_position_price_refresh", 0.0) < self.position_price_refresh_interval:
                return

        for symbol, pos in self.paper_broker.get_all_positions().items():
            if not symbol or pos.quantity == 0:
                continue
            try:
                price = self.feed.get_ltp(symbol, exchange=self.fno_exchange)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Failed to refresh LTP for %s: %s", symbol, exc)
                continue
            self.last_prices[symbol] = price

        self._last_position_price_refresh = now

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
                    "Per-symbol loss limit reached for options symbol %s (realized=%.2f <= -%.2f). "
                    "Disabling further trades in this symbol for this session.",
                    symbol,
                    realized,
                    self.per_symbol_max_loss,
                )
                self.banned_symbols.add(symbol)

    def _build_sizer_config(self) -> SizerConfig:
        risk_cfg = self.cfg.risk
        trading_cfg = self.cfg.trading
        max_exposure = float(
            risk_cfg.get(
                "max_gross_exposure_pct",
                risk_cfg.get("max_exposure_pct", trading_cfg.get("max_notional_multiplier", 2.0)),
            )
        )
        return SizerConfig(
            max_exposure_pct=max_exposure,
            risk_per_trade_pct=float(risk_cfg.get("risk_per_trade_pct", 0.005)),
            min_order_notional=float(risk_cfg.get("min_order_notional", 5000.0)),
            max_order_notional_pct=float(risk_cfg.get("max_order_notional_pct", 0.2)),
            max_trades=int(risk_cfg.get("max_concurrent_trades", trading_cfg.get("max_open_positions", 10))),
            risk_scale_min=float(risk_cfg.get("risk_scale_min", 0.3)),
            risk_scale_max=float(risk_cfg.get("risk_scale_max", 2.0)),
            risk_down_threshold=float(risk_cfg.get("risk_down_threshold", -0.02)),
            risk_up_threshold=float(risk_cfg.get("risk_up_threshold", 0.02)),
        )

    def _load_portfolio_state(self) -> PortfolioState:
        meta = self._compute_portfolio_meta()
        fallback_positions = {symbol: pos.quantity for symbol, pos in self.paper_broker.get_all_positions().items()}
        return load_portfolio_state(
            self.state_path,
            capital=self.paper_capital,
            fallback_meta=meta,
            fallback_positions=fallback_positions,
            config=self.sizer_config,
        )

    def _estimate_costs(self, symbol: str, side: str, qty: int, price: float, segment: str) -> CostBreakdown:
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
        _ = logical
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
        sym = symbol.upper()
        if sym.endswith("CE") or sym.endswith("PE"):
            return "OPT"
        if sym.endswith("FUT"):
            return "FNO"
        return "OPT"

    def _approximate_edge_bps(self, symbol: str, side: str, price: float) -> float:
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
        proposal = self._build_trade_proposal(symbol, side, qty, price, logical_name)
        proposal.raw_edge_bps = self._approximate_edge_bps(symbol, side, price)

        decision = self.trade_quality_filter.evaluate(proposal, costs, portfolio_state)
        if not decision.accept:
            logger.info(
                "Options trade rejected by quality filter: symbol=%s side=%s qty=%s reason=%s",
                symbol,
                side,
                qty,
                decision.reason,
            )
            return False, {}

        logger.info(
            "Options trade accepted by quality filter: symbol=%s side=%s qty=%s reason=%s",
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
