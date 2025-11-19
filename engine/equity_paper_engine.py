from __future__ import annotations

import json
import logging
import time
from datetime import date
from pathlib import Path
from typing import List, Dict, Any, Optional
from types import SimpleNamespace

from core.config import AppConfig
from core.modes import TradingMode
from core.pattern_filters import should_trade_trend
from core.strategy_tags import Profile
from core.state_store import record_strategy_signal
from core.strategy_metrics import StrategyMetricsTracker
from core.strategy_registry import STRATEGY_REGISTRY
from core.universe import load_equity_universe
from core.market_session import is_market_open
from broker.execution_router import ExecutionRouter
from broker.paper_broker import PaperBroker
from broker.kite_client import KiteClient
from configs.timeframes import MULTI_TF_CONFIG, resolve_multi_tf_config
from data.broker_feed import BrokerFeed
from kiteconnect import KiteConnect
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
    STYLE_SWING,
)
from risk.position_sizer import DynamicPositionSizer, PortfolioState, SizerConfig, load_portfolio_state
from risk.cost_model import CostBreakdown, CostModel, load_cost_config_from_yaml
from risk.trade_quality import (
    TradeProposal,
    TradeQualityFilter,
    load_quality_config_from_yaml,
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

logger = logging.getLogger("engine.equity_paper_engine")

BASE_DIR = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = BASE_DIR / "artifacts"
STATE_PATH = ARTIFACTS_DIR / "paper_state.json"
PROFILE_INTRADAY = {"1m", "3m", "5m"}
PROFILE_SWING = {"15m", "30m", "1h", "60m"}


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


class EquityPaperEngine:
    """
    Paper engine for NSE equity intraday trading.

    - Uses trading.equity_universe from config (NSE symbols, e.g. RELIANCE, TCS).
    - Fetches LTP from NSE for each symbol.
    - Applies FnoIntradayTrendStrategy on prices.
    - Places PAPER orders via ExecutionRouter.
    - Records signals and orders via TradeRecorder.
    - Enforces per-symbol loss limit (kill switch).
    - Enforces per-trade max loss on open equity positions.
    - Tags logical as "EQ_<SYMBOL>|<STRATEGY_ID>" for analytics.
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
        equity_universe_override: Optional[List[str]] = None,
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

        # --- NEW: ensure self.universe is always defined ---
        self.universe: List[str] = []
        trading = getattr(cfg, "trading", None) or {}
        raw_universe = (
            trading.get("equity_universe")
            or trading.get("equity_symbols")
            or trading.get("equity_watchlist")
            or None
        )
        if raw_universe is None:
            try:
                self.universe = load_equity_universe()
                logger.info(
                    "Equity universe loaded via load_equity_universe(): %s",
                    self.universe,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to load equity universe; running with empty universe: %s",
                    exc,
                )
                self.universe = []
        else:
            if isinstance(raw_universe, str):
                raw_universe = [raw_universe]
            self.universe = [str(sym).strip().upper() for sym in raw_universe if sym]

        logger.info(
            "Equity universe for EquityPaperEngine (initial): %s",
            self.universe,
        )
        # --- END NEW ---

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
        self.strategies_by_symbol: Dict[str, List[FnoIntradayTrendStrategy]] = {}
        self.regime_detector = shared_regime_detector
        if self.universe:
            self.regime_detector.set_primary_symbol(self.universe[0])

        self.router = ExecutionRouter(mode=self.mode, paper_broker=self.paper_broker, kite_client=self.kite_client)

        self.artifacts_dir = artifacts_dir or ARTIFACTS_DIR
        self.state_path = self.artifacts_dir / "paper_state.json"
        base_universe = equity_universe_override if equity_universe_override is not None else self._load_equity_universe()
        self.universe = [str(sym).strip().upper() for sym in base_universe if sym]
        logger.info("Equity universe from config: %s", self.universe)

        self.strategy_instances = self._build_strategy_instances()

        self.sleep_sec = 5
        self.exchange = "NSE"
        self.running = True

        self.paper_capital: float = float(self.cfg.trading.get("paper_capital", 500000))
        self.per_symbol_max_loss: float = float(self.cfg.trading.get("per_symbol_max_loss", 3000))
        self.max_loss_pct_per_trade: float = float(self.cfg.trading.get("max_loss_pct_per_trade", 0.01))

        # Cache last known prices for P&L snapshots
        self.last_prices: Dict[str, float] = {}

        # Snapshot every N loops
        self.snapshot_every_n_loops = 5
        self._loop_counter = 0

        # Per-symbol kill switch state
        self.banned_symbols: set[str] = set()

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
        self.allowed_equity_styles = {STYLE_INTRADAY, STYLE_SWING}
        if self.meta_enabled:
            self.multi_tf_engine = MultiTimeframeEngine(
                symbols=self.universe,
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
            logger.info("Initializing Strategy Engine v2 for equity trading")
            try:
                self.strategy_engine_v2 = StrategyEngineV2.from_config(self.cfg.raw, logger)
                
                # Set engines
                if self.market_data_engine:
                    self.strategy_engine_v2.mde = self.market_data_engine
                    self.strategy_engine_v2.market_data = self.market_data_engine
                    self.strategy_engine_v2.market_data_engine = self.market_data_engine
                self.strategy_engine_v2.regime_engine = self.regime_detector
                
                logger.info(
                    "Strategy Engine v2 initialized for equity with %d strategies",
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
                logger.error("Failed to initialize Strategy Engine v2 for equity: %s", exc, exc_info=True)
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
        self.strategies_by_symbol = {}
        if not getattr(self, "universe", None):
            return instances
        for symbol in self.universe:
            per_symbol: List[FnoIntradayTrendStrategy] = []
            for cfg in self.multi_tf_config or MULTI_TF_CONFIG:
                timeframe = str(cfg.get("timeframe") or self.default_timeframe)
                mode = str(cfg.get("mode") or self.strategy_mode)
                strat = FnoIntradayTrendStrategy(timeframe=timeframe)
                strat.logical = symbol
                strat.timeframe = timeframe
                strat.mode = mode
                instances.append(strat)
                per_symbol.append(strat)
            self.strategies_by_symbol[symbol] = per_symbol
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
        preferred = (self.cfg.trading or {}).get("equity_strategy_code")
        if isinstance(preferred, str) and preferred.strip():
            return preferred.strip()
        if "ema20_50_intraday" in STRATEGY_REGISTRY:
            return "ema20_50_intraday"
        return next(iter(STRATEGY_REGISTRY.keys()), "ema20_50_intraday")

    def _infer_strategy_code(self, symbol: str, override: Optional[str] = None) -> Optional[str]:
        return self.strategy_metrics.infer(symbol, override=override)

    def _record_regime_sample(self, symbol: str, price: float) -> None:
        if not self.regime_detector or not symbol or price is None or price <= 0:
            return
        try:
            self.regime_detector.update(symbol=symbol, close=float(price))
        except Exception as exc:  # noqa: BLE001
            logger.debug("Regime detector update failed for equity %s: %s", symbol, exc)

    def run_forever(self) -> None:
        if not self.universe:
            logger.error("No equity_universe configured. Aborting EquityPaperEngine.")
            publish_engine_health(
                "equity_paper_engine",
                "error",
                {"mode": self.mode.value, "error": "no_universe"}
            )
            return

        logger.info(
            "Starting EquityPaperEngine for NSE symbols=%s (mode=%s)",
            self.universe,
            self.mode.value,
        )
        
        # Publish engine startup telemetry
        publish_engine_health(
            "equity_paper_engine",
            "starting",
            {
                "mode": self.mode.value,
                "universe_size": len(self.universe),
                "strategy_name": self.strategy_name,
            }
        )

        try:
            while self.running:
                try:
                    if not is_market_open():
                        logger.info("Market appears closed (EquityPaperEngine); sleeping...")
                        time.sleep(self.sleep_sec)
                        continue

                    self._loop_once()
                    time.sleep(self.sleep_sec)
                except KeyboardInterrupt:
                    logger.info("EquityPaperEngine interrupted by user.")
                    self.running = False
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Unexpected error in equity engine loop: %s", exc)
                    time.sleep(self.sleep_sec)
        finally:
            # Publish engine shutdown telemetry
            publish_engine_health(
                "equity_paper_engine",
                "stopped",
                {"mode": self.mode.value}
            )

    def _loop_once(self) -> None:
        self._loop_counter += 1

        price_cache: Dict[str, float] = {}

        def _ltp(symbol: str) -> float:
            if symbol not in price_cache:
                price = self.feed.get_ltp(symbol, exchange=self.exchange)
                price_cache[symbol] = price
                self.last_prices[symbol] = price
            return price_cache[symbol]

        # If Strategy Engine v2 is available, use it
        if self.strategy_engine_v2 and self.market_data_engine:
            for symbol in self.universe:
                if symbol in self.banned_symbols:
                    logger.info("Equity %s is banned for this session due to per-symbol loss limit; skipping.", symbol)
                    continue

                if not self._meta_allows_trade(symbol, self.allowed_equity_styles):
                    logger.debug("Meta engine filtered equity %s for mismatched style/confidence.", symbol)
                    continue

                try:
                    price = _ltp(symbol)
                    if price is None:
                        continue
                    
                    self._record_regime_sample(symbol, price)
                    
                    logical_base = f"EQ_{symbol}"
                    tf = self.default_timeframe
                    
                    # Update market data cache
                    try:
                        self.market_data_engine.update_cache(symbol, tf)
                    except Exception as exc:
                        logger.debug("Market data cache update failed for %s: %s", symbol, exc)
                    
                    # Fetch candle window
                    window = self.market_data_engine.get_window(symbol, tf, 200)
                    
                    if not window or len(window) < 20:
                        logger.debug("Insufficient candles for %s/%s: %d", symbol, tf, len(window) if window else 0)
                        continue
                    
                    # Build series
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
                    indicators = self.strategy_engine_v2.compute_indicators(series, symbol=symbol, timeframe=tf)
                    
                    # Safety check
                    if not current_candle or current_candle.get("close") is None:
                        logger.debug("Invalid candle for %s, skipping", symbol)
                        continue
                    
                    if not indicators or indicators.get("ema20") is None:
                        logger.debug("Indicators not ready for %s, skipping", symbol)
                        continue
                    
                    # Call evaluate
                    intent, debug = self.strategy_engine_v2.evaluate(
                        logical=logical_base,
                        symbol=symbol,
                        timeframe=tf,
                        candle=current_candle,
                        indicators=indicators,
                        mode=self.mode.value,
                        profile="EQUITY_INTRADAY",
                        context={"ltp": price},
                    )
                    
                    # Always log the signal
                    signal_ts = self.recorder.log_signal(
                        logical=f"{logical_base}|{intent.strategy_id}",
                        symbol=symbol,
                        price=price,
                        signal=intent.signal,
                        tf=tf,
                        reason=intent.reason,
                        profile="EQUITY_INTRADAY",
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
                    
                    # Process non-HOLD signals
                    record_strategy_signal(self.primary_strategy_code, timestamp=signal_ts)
                    self._handle_signal(
                        symbol,
                        intent.signal,
                        price,
                        logical_base,
                        tf=tf,
                        profile="EQUITY_INTRADAY",
                        mode=self.mode.value,
                        strategy_name=intent.strategy_id,
                        strategy_code=self.primary_strategy_code,
                        confidence=intent.confidence,
                        reason=intent.reason,
                        signal_timestamp=signal_ts,
                    )
                    
                except Exception as exc:
                    logger.exception("Error processing equity symbol=%s with v2 engine: %s", symbol, exc)
        else:
            # Use legacy strategy instances
            for strat in self.strategy_instances:
                symbol = getattr(strat, "logical", "")
                if not symbol:
                    continue

                if symbol in self.banned_symbols:
                    logger.info("Equity %s is banned for this session due to per-symbol loss limit; skipping.", symbol)
                    continue

                if not self._meta_allows_trade(symbol, self.allowed_equity_styles):
                    logger.debug("Meta engine filtered equity %s for mismatched style/confidence.", symbol)
                    continue

                try:
                    price = _ltp(symbol)
                    if price is not None:
                        self._record_regime_sample(symbol, price)

                    tf_label = self._resolve_timeframe(getattr(strat, "timeframe", None))
                    bar = {"close": price, "tf": tf_label}
                    raw_decision = strat.on_bar(symbol, bar)
                    decision = self._ensure_decision(strat, raw_decision)
                    signal = decision.action
                    mode_label = decision.mode or getattr(strat, "mode", self.strategy_mode)

                    logical_base = f"EQ_{symbol}"
                    strategy_label = getattr(strat, "name", self.strategy_name)
                    logical_tagged = f"{logical_base}|{strategy_label}"

                    logger.info(
                        "Equity logical=%s tf=%s mode=%s strategy=%s price=%s signal=%s",
                        logical_base,
                        tf_label,
                        mode_label,
                        strategy_label,
                        f"{price:.2f}" if price is not None else "None",
                        signal,
                    )

                    indicators = strat.get_latest_indicators(symbol) or {}
                    regime = strat.get_latest_regime(symbol)
                    market_regime = (
                        self.regime_detector.current_regime(symbol)
                        if self.regime_detector
                        else Regime.UNKNOWN.value
                    )
                    if (
                        strategy_label == "EMA_TREND"
                        and signal in {"BUY", "SELL"}
                        and market_regime in {Regime.CHOP.value, Regime.UNKNOWN.value}
                    ):
                        logger.warning(
                            "[QUALITY_VETO] EMA_TREND blocked due to regime=%s equity=%s",
                            market_regime,
                            symbol,
                        )
                        decision = Decision(
                            action="HOLD",
                            reason=f"regime_block_{market_regime.lower()}",
                            mode=decision.mode,
                            confidence=decision.confidence,
                        )
                        signal = decision.action
                    meta_decision = self._last_meta_decisions.get(symbol)
                    profile = _profile_from_tf(tf_label)
                    pattern_ok, pattern_reason = should_trade_trend(
                        logical=logical_tagged,
                        symbol=symbol,
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
                        symbol=symbol,
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
                            symbol,
                            final_signal,
                            price,
                            logical_base,
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
                    logger.exception("Error processing equity symbol=%s: %s", symbol, exc)

        # Per-trade stop-loss on open equity positions
        self._enforce_per_trade_stop()

        # Snapshot state periodically (with meta)
        if self._loop_counter % self.snapshot_every_n_loops == 0:
            meta = self._compute_portfolio_meta()
            self.recorder.snapshot_paper_state(self.paper_broker, last_prices=self.last_prices, meta=meta)

        # Per-symbol risk check
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
            logger.warning("Not placing equity order for %s: symbol is banned by per-symbol loss limit.", symbol)
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
                "Skipping %s equity order for %s: position sizer returned zero qty (price=%.2f, free_notional=%.2f).",
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

        logical_name = logical or f"EQ_{symbol}"
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
        logger.info("Equity order executed (mode=%s): %s", self.mode.value, order)

        extra_payload: Dict[str, Any] = {
            "status": getattr(order, "status", "FILLED"),
            "strategy": strategy_label,
            "strategy_code": strategy_code_value,
            "mode": mode_label,
            "logical": logical_name,
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
        post_position = self.paper_broker.get_position(symbol)
        post_qty = post_position.quantity if post_position else 0
        self.strategy_metrics.record_fill(
            symbol,
            prev_qty=prev_position_qty,
            new_qty=post_qty,
            pnl_delta=pnl_delta,
            strategy_code=strategy_code_value,
        )

        meta = self._compute_portfolio_meta()
        self.recorder.snapshot_paper_state(self.paper_broker, last_prices=self.last_prices, meta=meta)

    def _enforce_per_trade_stop(self) -> None:
        """
        Enforce per-trade max loss on open equity positions.
        LONG: (last - avg) / avg <= -max_loss_pct_per_trade -> close (SELL).
        SHORT: (avg - last) / avg <= -max_loss_pct_per_trade -> close (BUY).
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
                ret = (last - avg) / avg
                if ret <= -self.max_loss_pct_per_trade:
                    logger.warning(
                        "Per-trade stop-loss triggered for equity %s (LONG): avg=%.2f last=%.2f loss=%.2f%% >= %.2f%%. "
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
                        "Per-trade stop-loss triggered for equity %s (SHORT): avg=%.2f last=%.2f loss=%.2f%% >= %.2f%%. "
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
        logger.info("Equity close-position order executed (mode=%s): %s", self.mode.value, order)

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
        Compute portfolio-level metrics for the equity book.

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
        return meta

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
                    "Per-symbol loss limit reached for equity symbol %s (realized=%.2f <= -%.2f). "
                    "Disabling further trades in this symbol for this session.",
                    symbol,
                    realized,
                    self.per_symbol_max_loss,
                )
                self.banned_symbols.add(symbol)

    def _load_equity_universe(self) -> List[str]:
        """
        Load equity universe with the following precedence:
        1. From scanner's universe.json (if equity_universe key exists)
        2. From artifacts/equity_universe.json
        3. From config trading.equity_universe
        4. From config/universe_equity.csv (via load_equity_universe)
        """
        # Try scanner's universe.json first (new behavior)
        scanner_universe_path = self.artifacts_dir / "scanner" / date.today().isoformat() / "universe.json"
        if scanner_universe_path.exists():
            try:
                with scanner_universe_path.open("r", encoding="utf-8") as f:
                    universe_data = json.load(f)
                if isinstance(universe_data, dict):
                    equity_universe = universe_data.get("equity_universe")
                    if equity_universe and isinstance(equity_universe, list):
                        cleaned = [str(sym).strip().upper() for sym in equity_universe if sym]
                        if cleaned:
                            # Determine mode for logging
                            mode = "nifty_lists" if len(cleaned) <= 120 else "all"
                            logger.info(
                                "Equity universe loaded from scanner (mode=%s, symbols=%d): %s",
                                mode,
                                len(cleaned),
                                cleaned[:10] if len(cleaned) > 10 else cleaned,
                            )
                            return cleaned
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to load equity_universe from scanner universe.json: %s", exc)
        
        # Fallback to artifacts/equity_universe.json
        artifacts_file = self.artifacts_dir / "equity_universe.json"
        if artifacts_file.exists():
            try:
                with artifacts_file.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    raw = data.get("symbols") or data.get("universe") or []
                elif isinstance(data, list):
                    raw = data
                else:
                    raw = []
                cleaned = [str(sym).strip().upper() for sym in raw if sym]
                if cleaned:
                    logger.info(
                        "Loaded equity universe from artifacts (%d symbols).",
                        len(cleaned),
                    )
                    return cleaned
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to load artifacts/equity_universe.json: %s", exc)
        
        # Fallback to config trading.equity_universe
        cfg_list = [str(sym).strip().upper() for sym in self.cfg.trading.get("equity_universe", []) or [] if sym]
        if cfg_list:
            return cfg_list
        
        # Final fallback to load_equity_universe (config/universe_equity.csv)
        return load_equity_universe()

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
            max_trades=_safe_int(
                risk_cfg.get("max_concurrent_trades", trading_cfg.get("max_open_positions", 10)),
                10
            ),
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
        _ = symbol
        return "EQ"

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
                "Equity trade rejected by quality filter: symbol=%s side=%s qty=%s reason=%s",
                symbol,
                side,
                qty,
                decision.reason,
            )
            return False, {}

        logger.info(
            "Equity trade accepted by quality filter: symbol=%s side=%s qty=%s reason=%s",
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

    def _meta_allows_trade(self, symbol: str, allowed_styles: set[str]) -> bool:
        if not self.meta_engine:
            return True

        decision = self.meta_engine.decide_for_symbol(symbol)
        self._last_meta_decisions[symbol] = decision

        if decision is None:
            return self.meta_engine.allow_fallback

        if decision.style not in allowed_styles:
            return False

        if decision.confidence <= 0.0:
            return False

        return True
