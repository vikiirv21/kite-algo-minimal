"""
Live Equity Engine (ExecutionEngine V3 first)

Minimal live trading loop for equities using:
- StrategyEngineV2 for signal generation
- MarketDataEngineV2 for live candles/ltp
- ExecutionEngine V3 (via V2 adapter) for order lifecycle
- TradeRecorder + RuntimeMetricsTracker for artifacts

The class is intentionally small and conservative. It focuses on wiring the
live path without touching existing paper/backtest flows.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from analytics.runtime_metrics import RuntimeMetricsTracker
from analytics.learning_engine import load_tuning
from analytics.trade_recorder import TradeRecorder
from broker.kite_bridge import KiteBroker
from broker.kite_client import KiteClient
from core.capital_provider import CapitalProvider, create_capital_provider, LiveCapitalProvider
from core.kite_client import make_kite_client
from core.config import AppConfig
from core.market_data_engine_v2 import MarketDataEngineV2
from core.market_session import is_market_open
from core.modes import TradingMode
from core.state_store import JournalStateStore, StateStore
from core.strategy_engine_v2 import StrategyEngineV2
from core.universe import load_equity_universe
from core.regime_engine import RegimeEngine
from core.reconciliation_engine import ReconciliationEngine
from engine.execution_engine_v3_adapter import create_execution_engine
from engine.execution_engine import OrderIntent
from risk.position_sizer import SizerConfig, DynamicPositionSizer, PortfolioState
from core.atr_risk import TimeFilterConfig, is_entry_time_allowed

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = BASE_DIR / "artifacts"
CHECKPOINTS_DIR = ARTIFACTS_DIR / "checkpoints"


def create_dir_if_not_exists(path: Path) -> None:
    """Create directory if it doesn't exist."""
    path.mkdir(parents=True, exist_ok=True)


class LiveEquityEngine:
    """
    Lightweight LIVE equity engine built on StrategyEngineV2 + ExecutionEngineV3.
    """

    def __init__(
        self,
        cfg: AppConfig,
        kite_client: Optional[KiteClient] = None,
        *,
        artifacts_dir: Optional[Path] = None,
    ) -> None:
        self.cfg = cfg
        self.mode = TradingMode.LIVE
        self.artifacts_dir = Path(artifacts_dir).resolve() if artifacts_dir else ARTIFACTS_DIR
        self.checkpoint_path = self.artifacts_dir / "checkpoints" / "live_state_latest.json"
        self.live_state_path = self.artifacts_dir / "live_state.json"
        self.capital_provider: Optional[LiveCapitalProvider] = None
        
        # Create required directories
        self._create_required_directories()

        # Brokers/clients (we keep KiteClient placeholder but rely on capital_provider for auth)
        self.kite_client = kite_client or KiteClient()
        self.kite = None
        self.broker = KiteBroker(cfg.raw, logger_instance=logger)

        # Learning engine tuning (optional)
        learning_cfg = cfg.learning_engine or {}
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

        # Metrics - use config capital as starting value for metrics tracker
        config_capital = float(
            cfg.trading.get("live_capital", cfg.trading.get("paper_capital", 500_000))
        )
        trading_cfg = cfg.trading or {}
        style_raw = (
            trading_cfg.get("strategy_mode")
            or trading_cfg.get("mode_style")
            or trading_cfg.get("style")
        )
        mode_value = trading_cfg.get("mode")
        if isinstance(style_raw, str):
            self.trading_style = style_raw.lower()
        elif isinstance(mode_value, str) and mode_value.lower() in ("multi", "scalp", "intraday"):
            self.trading_style = mode_value.lower()
        else:
            self.trading_style = "intraday"
        self.scalping_mode = bool(trading_cfg.get("scalping_mode", False)) or self.trading_style in ("multi", "scalp")
        self.scalping_timeframe = str(trading_cfg.get("scalping_timeframe", "1m"))
        self.primary_timeframe_override = trading_cfg.get("primary_timeframe") or trading_cfg.get("intraday_timeframe")
        self.metrics_tracker = RuntimeMetricsTracker(
            starting_capital=config_capital,
            mode="live",
            artifacts_dir=self.artifacts_dir,
            equity_curve_maxlen=500,
        )
        self.config_fallback_capital = config_capital
        self.live_capital = config_capital

        # Capital provider - fetches real-time capital from Kite API in LIVE mode
        self.capital_provider = create_capital_provider(
        mode="LIVE",
        kite=None,  # provider will build using shared auth helper
        config_capital=config_capital,
        cache_ttl_seconds=30.0,
        )
        # Use the same Kite client as capital provider for validation
        self.kite = self.capital_provider.get_client() if hasattr(self.capital_provider, 'get_client') else None
        try:
            self.live_capital = self.capital_provider.get_current_capital()
            source = getattr(self.capital_provider, "capital_source", "broker")
            logger.info(
                "[LIVE] Effective live capital for sizing: %.2f (source=%s)",
                self.live_capital,
                source,
            )
        except Exception:
            logger.warning(
                "[LIVE] Unable to refresh capital during init; using config fallback %.2f",
                self.live_capital,
            )

        # State + journal
        self.state_store = StateStore(checkpoint_path=self.checkpoint_path)
        self.journal_store = JournalStateStore(mode="live", artifacts_dir=self.artifacts_dir)
        # TradeRecorder expects base_dir (parent of artifacts), not artifacts_dir directly
        # Pass the base_dir so TradeRecorder creates artifacts_dir correctly
        self.recorder = TradeRecorder(base_dir=str(self.artifacts_dir.parent))

        # Universe + sizing
        self.universe: List[str] = self._load_equity_universe()
        default_tf = "5m"
        configured_tf = (trading_cfg.get("multi_tf_config") or [{"timeframe": default_tf}])[0].get("timeframe", default_tf)
        intraday_tf = str(self.primary_timeframe_override or configured_tf or default_tf)
        # Primary timeframe used for intraday layer
        self.primary_timeframe = intraday_tf
        self.default_qty = int(trading_cfg.get("default_quantity", 1))
        risk_cfg = cfg.risk or {}
        portfolio_cfg = cfg.raw.get("portfolio", {}) or {}
        self.max_exposure_pct = float(portfolio_cfg.get("max_exposure_pct", 1.0))
        self.strategy_budgets: Dict[str, Any] = portfolio_cfg.get("strategy_budgets", {}) or {}
        time_section = risk_cfg.get("time_filter") or {}
        self.time_filter_config = TimeFilterConfig(
            enabled=bool(time_section.get("enabled", False)),
            allow_sessions=time_section.get("allow_sessions"),
            block_expiry_scalps_after=time_section.get("block_expiry_scalps_after"),
            min_time=time_section.get("min_time"),
            max_time=time_section.get("max_time"),
        )
        sizer_cfg = SizerConfig(
            max_exposure_pct=float(
                risk_cfg.get(
                    "max_gross_exposure_pct",
                    risk_cfg.get("max_exposure_pct", trading_cfg.get("max_notional_multiplier", 1.0)),
                )
            ),
            risk_per_trade_pct=float(risk_cfg.get("risk_per_trade_pct", 0.005)),
            min_order_notional=float(risk_cfg.get("min_order_notional", 0.0)),
            max_order_notional_pct=float(risk_cfg.get("max_order_notional_pct", 0.2)),
            # Handle null config values explicitly (max_open_positions can be null = unlimited)
            max_trades=int(
                risk_cfg.get("max_concurrent_trades") 
                if risk_cfg.get("max_concurrent_trades") is not None 
                else (trading_cfg.get("max_open_positions") if trading_cfg.get("max_open_positions") is not None else 5)
            ),
            risk_scale_min=float(risk_cfg.get("risk_scale_min", 0.3)),
            risk_scale_max=float(risk_cfg.get("risk_scale_max", 2.0)),
            risk_down_threshold=float(risk_cfg.get("risk_down_threshold", -0.02)),
            risk_up_threshold=float(risk_cfg.get("risk_up_threshold", 0.02)),
        )
        self.position_sizer = DynamicPositionSizer(sizer_cfg)

        # Market data v2 (live ticks)
        data_cfg = cfg.raw.get("data", {})
        data_cfg.setdefault("feed", "kite")
        if self.trading_style == "multi":
            tf_list = [self.scalping_timeframe, intraday_tf]
        elif self.trading_style == "scalp":
            tf_list = [self.scalping_timeframe]
        else:
            tf_list = [intraday_tf]
        # Deduplicate while preserving order
        seen = set()
        timeframes = []
        for tf in tf_list:
            if tf not in seen:
                seen.add(tf)
                timeframes.append(tf)
        data_cfg["timeframes"] = timeframes
        self.market_data_engine = MarketDataEngineV2(
            cfg=data_cfg,
            kite=self.kite,
            universe=self.universe,
            meta={},
            logger_instance=logger,
        )

        # Regime engine (optional)
        self.regime_engine = None
        try:
            regime_cfg = cfg.raw.get("regime_engine", {})
            if regime_cfg.get("enabled", True):
                self.regime_engine = RegimeEngine(cfg.raw, self.market_data_engine, logger_instance=logger)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to initialize RegimeEngine: %s", exc)

        # Strategy engine v2 (signals) wired to this engine for execution
        if self.trading_style == "scalp":
            # Pure scalp mode: force strategies to use scalping timeframe
            try:
                strategies_v2 = cfg.raw.get("strategy_engine", {}).get("strategies_v2", [])
                for strat in strategies_v2:
                    params = strat.setdefault("params", {})
                    tf_override = params.get("scalping_timeframe") or self.scalping_timeframe
                    if tf_override:
                        params["timeframe"] = tf_override
            except Exception:
                logger.debug("Could not apply scalping timeframe override", exc_info=True)
        self.strategy_engine = StrategyEngineV2.from_config(
            cfg.raw,
            logger=logger,
        )
        self.strategy_engine.market_data = self.market_data_engine
        self.strategy_engine.market_data_engine = self.market_data_engine
        self.strategy_engine.mde = self.market_data_engine
        self.strategy_engine.state_store = self.state_store
        self.strategy_engine.regime_engine = self.regime_engine
        self.strategy_engine.set_paper_engine(self)

        # Execution engine v3 (adapter)
        self.execution_engine = create_execution_engine(
            mode="live",
            config=cfg.raw,
            state_store=self.state_store,
            journal_store=self.journal_store,
            mde=self.market_data_engine,
            broker=self.broker,
            logger_instance=logger,
            use_v3=True,
        )

        # Reconciliation engine (polling)
        self.reconciler = None
        try:
            recon_exec = getattr(self.execution_engine, "v3_engine", self.execution_engine)
            recon_bus = getattr(self.execution_engine, "event_bus", None)
            self.reconciler = ReconciliationEngine(
                execution_engine=recon_exec,
                state_store=self.execution_engine.state_store
                if hasattr(self.execution_engine, "state_store")
                else self.state_store,
                event_bus=recon_bus,
                kite_broker=self.broker,
                config=cfg.raw,
                mode="LIVE",
                logger_instance=logger,
                capital_provider=self.capital_provider,  # Wire up capital provider for LIVE mode
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to initialize reconciliation engine: %s", exc, exc_info=True)

        self.running = True
        self.last_prices: Dict[str, float] = {}
        self._last_session_status: Optional[str] = None
        self._last_capital_refresh = 0.0

        # Log startup summary
        self._log_startup_summary(cfg)


    def _validate_kite_session(self) -> bool:
        """
        Validate Kite session using the same client as LiveCapitalProvider.
        """
        if not self.capital_provider:
            logger.error(
                'Kite token validation failed - no capital provider. '
                'Run `python -m scripts.run_day --login --engines none` and retry.',
            )
            return False

        kite = self.kite or self.capital_provider.get_client()
        if kite is None:
            logger.warning(
                'LiveEquityEngine: no Kite client from capital_provider; attempting to build from env...'
            )
            try:
                from broker.auth import make_kite_client_from_env

                kite = make_kite_client_from_env(strict=False)
                self.kite = kite
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    'Kite token validation failed - could not create Kite client: %s. '
                    'Run `python -m scripts.run_day --login --engines none` and retry.',
                    exc,
                )
                return False

        try:
            profile = kite.profile()
            user_id = (
                profile.get('user_id')
                if isinstance(profile, dict)
                else getattr(profile, 'user_id', 'UNKNOWN')
            )
            logger.info('LiveEquityEngine: Kite session OK (user_id=%s)', user_id)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error(
                'Kite token validation failed in LiveEquityEngine: %s. '
                'Run `python -m scripts.run_day --login --engines none` and retry.',
                exc,
            )
            return False
    def run_smoke_test(self, max_loops: int = 60, sleep_seconds: float = 1.0) -> bool:
        """
        Run a short, bounded main loop for smoke testing.
        
        - Uses the same internal logic as run_forever, but breaks after max_loops.
        - Logs basic heartbeat each loop.
        - Never places real orders if execution.dry_run=True.
        
        Args:
            max_loops: Maximum number of loop iterations (default: 60)
            sleep_seconds: Sleep time between loops in seconds (default: 1.0)
        """
        logger.info("Starting LIVE smoke test loop: max_loops=%s, sleep=%ss", max_loops, sleep_seconds)
        
        # Ensure session is valid before starting
        if not self._validate_kite_session():
            logger.error(
                "Cannot start smoke test: not logged in. "
                "Run `python -m scripts.run_day --login --engines none`."
            )
            return False

        # Start market data + tick subscription
        self.market_data_engine.start()
        tokens = list(self.market_data_engine.symbol_tokens.values())
        if tokens:
            self.broker.subscribe_ticks(tokens, self._on_tick)
        
        # Initial capital refresh
        self._refresh_live_capital(force=True)
        # Save initial live state
        self._save_live_state()

        logger.info("[LIVE-SMOKE] LiveEquityEngine smoke test starting (tf=%s)", self.primary_timeframe)
        loops = 0
        try:
            while loops < max_loops and self.running:
                loops += 1
                
                # Note: For smoke test, we run even if market is closed
                # but log the status
                if not is_market_open():
                    logger.debug("[LIVE-SMOKE] Market appears closed, but continuing smoke test")
                
                # Run one tick of the main loop
                self._tick_once()
                
                # Periodic heartbeat
                if loops % 10 == 0:
                    logger.info("LIVE smoke test heartbeat — loop %s/%s", loops, max_loops)
                
                # Refresh capital periodically
                if loops % 20 == 0:
                    self._refresh_live_capital()
                    self._save_live_state()
                
                time.sleep(sleep_seconds)
        except KeyboardInterrupt:
            logger.info("Smoke test interrupted by user")
        finally:
            logger.info("LIVE smoke test completed after %s loops", loops)
            # Minimal cleanup - don't write full stop checkpoint
            try:
                self.market_data_engine.stop()
            except Exception:
                pass
        return True

    def run_forever(self) -> None:
        """Main live loop."""
        if not self._validate_kite_session():
            return

        # Start market data + tick subscription
        self.market_data_engine.start()
        tokens = list(self.market_data_engine.symbol_tokens.values())
        if tokens:
            self.broker.subscribe_ticks(tokens, self._on_tick)
        # Initial capital refresh
        self._refresh_live_capital(force=True)
        # Save initial live state
        self._save_live_state()

        logger.info("[LIVE] LiveEquityEngine starting loop (tf=%s)", self.primary_timeframe)
        loop_count = 0
        try:
            while self.running:
                loop_count += 1
                
                if not is_market_open():
                    logger.info("Market closed; sleeping 30s")
                    time.sleep(30)
                    continue

                # Run one tick of the main loop
                self._tick_once()
                
                # Refresh capital every N loops (N=20)
                if loop_count % 20 == 0:
                    self._refresh_live_capital()
                    self._save_live_state()

                time.sleep(5)
        except KeyboardInterrupt:
            logger.info("Stopping LiveEquityEngine (keyboard interrupt)")
        finally:
            self.stop()

    # ------------------------------------------------------------------ signals
    def _handle_signal(
        self,
        symbol: str,
        action: str,
        price: float,
        logical: Optional[str] = None,
        *,
        tf: str = "",
        strategy_name: Optional[str] = None,
        strategy_code: Optional[str] = None,
        confidence: Optional[float] = None,
        reason: str = "",
        **_: Any,
    ) -> None:
        """Handle StrategyEngineV2 intent -> send to execution v3."""
        side = "BUY" if action.upper() in ("BUY", "LONG") else "SELL"
        qty = max(1, self.default_qty)

        # Log signal creation
        strategy_label = strategy_code or strategy_name or "EQUITY_LIVE"
        logger.info(
            "[LIVE] Signal: %s %s price=%.2f conf=%.2f strategy=%s reason=%s",
            action.upper(), symbol, price, confidence or 0.0, strategy_label, reason
        )

        # Enforce session/time filter for entries only (exits allowed anytime)
        if action.upper() in ("BUY", "LONG", "SELL", "SHORT") and self.time_filter_config.enabled:
            allowed, block_reason = is_entry_time_allowed(
                self.time_filter_config,
                symbol=symbol,
                strategy_id=strategy_label,
                is_expiry_instrument=False,
            )
            if not allowed:
                now_hhmm = datetime.now().strftime("%H:%M")
                logger.info(
                    "[LIVE] Blocked entry for %s: outside allowed session (now=%s, reason=%s, sessions=%s)",
                    symbol,
                    now_hhmm,
                    block_reason,
                    self.time_filter_config.allow_sessions,
                )
                return

        # Refresh capital before placing order
        self._refresh_live_capital()

        # Apply simple sizing if position_sizer present
        try:
            portfolio_state = self._build_portfolio_state()
            qty = self.position_sizer.size_order(
                portfolio_state,
                symbol=symbol,
                last_price=price,
                side=side,
                lot_size=max(1, self.default_qty),
            )
            if not self._within_portfolio_limits(
                strategy=strategy_label,
                notional=abs(qty * price),
                portfolio_state=portfolio_state,
            ):
                return
        except Exception:
            qty = max(1, self.default_qty)

        # Learning engine adjustments (optional, allow block/scale)
        qty = self._apply_learning_adjustments(symbol, strategy_label, qty)

        if qty == 0:
            logger.info("[LIVE] Skipping %s for %s: sized qty=0", side, symbol)
            return

        intent = OrderIntent(
            symbol=symbol,
            strategy_code=strategy_code or strategy_name or "EQUITY_LIVE",
            side=side,
            qty=qty,
            order_type="MARKET",
            product="MIS",
            validity="DAY",
            price=None,
            trigger_price=None,
            tag=logical or f"EQ_{symbol}",
            reason=reason or "",
            confidence=confidence or 0.0,
            metadata={"tf": tf or self.primary_timeframe, "mode": "live"},
        )

        try:
            result = self.execution_engine.execute_intent(intent)
            order_id = getattr(result, "order_id", None) or getattr(result, "id", None)
            status = getattr(result, "status", "UNKNOWN")
            self.recorder.record_order(
                symbol=symbol,
                side=side,
                quantity=qty,
                price=price,
                status=status,
                tf=tf or self.primary_timeframe,
                profile="INTRADAY",
                strategy=strategy_code or strategy_name or "EQUITY_LIVE",
                parent_signal_timestamp="",
                extra={
                    "mode": "live",
                    "order_id": order_id,
                    "reason": reason or "",
                    "confidence": confidence or 0.0,
                },
            )

            # Metrics
            if self.metrics_tracker:
                try:
                    self.metrics_tracker.update_after_fill(
                        symbol=symbol,
                        strategy=strategy_code or strategy_name or "EQUITY_LIVE",
                        realized_pnl=0.0,
                        fill_price=price,
                        qty=qty,
                        side=side,
                    )
                    self.metrics_tracker.save()
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Failed to update live metrics: %s", exc)

            # Refresh capital after fill to get updated available margin
            self._refresh_capital_after_fill()

            logger.info("[LIVE] Order placed: %s %s x%s (id=%s status=%s)", side, symbol, qty, order_id, status)
        except Exception as exc:  # noqa: BLE001
            logger.error("[LIVE] Order failed for %s: %s", symbol, exc, exc_info=True)

    # ------------------------------------------------------------------ helpers
    def _build_portfolio_state(self) -> PortfolioState:
        """
        Build portfolio state with real-time capital from Kite API.

        In LIVE mode, fetches fresh capital from margins("equity") API
        before every trade to ensure accurate position sizing.
        """
        positions = []
        positions_dict = {}
        total_notional = 0.0
        try:
            positions = self.broker.fetch_positions()
            for pos in positions or []:
                symbol = pos.get("tradingsymbol") or pos.get("symbol")
                qty = int(pos.get("quantity") or 0)
                if symbol and qty != 0:
                    positions_dict[symbol] = qty
                    avg_price = float(pos.get("average_price") or 0.0)
                    total_notional += abs(qty) * avg_price
        except Exception:
            positions = []

        # Fetch real-time capital from Kite API (or config fallback)
        live_capital = self.live_capital if self.live_capital > 0 else self.capital_provider.refresh()

        # Calculate equity (capital + unrealized PnL)
        unrealized_pnl = 0.0
        for pos in positions or []:
            symbol = pos.get("tradingsymbol") or pos.get("symbol")
            qty = float(pos.get("quantity") or 0.0)
            avg_price = float(pos.get("average_price") or 0.0)
            last_price = self.last_prices.get(symbol, avg_price)
            if qty > 0:
                unrealized_pnl += (last_price - avg_price) * qty
            elif qty < 0:
                unrealized_pnl += (avg_price - last_price) * abs(qty)

        equity = live_capital + unrealized_pnl

        return PortfolioState(
            capital=live_capital,
            equity=equity,
            total_notional=total_notional,
            realized_pnl=0.0,  # Will be updated from journal if needed
            unrealized_pnl=unrealized_pnl,
            free_notional=max(0.0, equity - total_notional),
            open_positions=len(positions_dict),
            positions=positions_dict,
        )

    def _refresh_capital_after_fill(self) -> None:
        """
        Refresh capital from Kite API after a fill.

        This ensures subsequent trades use the updated available margin
        after funds are utilized by the completed order.
        """
        try:
            # Force refresh capital from Kite API
            fresh_capital = self.capital_provider.refresh()
            logger.debug("Capital refreshed after fill: %.2f", fresh_capital)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Failed to refresh capital after fill: %s", exc)

    def _refresh_live_capital(self, *, force: bool = False) -> None:
        """
        Refresh live_capital from broker margins API.
        
        """
        now = time.time()
        if not force and (now - self._last_capital_refresh) < 60:
            return
        try:
            new_cap = self.capital_provider.refresh()
            source = getattr(self.capital_provider, "capital_source", "config")
            last_err = getattr(self.capital_provider, "last_error", "")

            if new_cap > 0 and new_cap != self.live_capital:
                old_cap = self.live_capital
                self.live_capital = new_cap
                self.metrics_tracker.starting_capital = new_cap
                logger.info(
                    "[LIVE] Updated live capital (%s): %.2f -> %.2f",
                    source,
                    old_cap,
                    self.live_capital,
                )
            elif source == "fallback" and last_err:
                logger.warning(
                    "[LIVE] Using FALLBACK capital=%.2f (reason=%s)",
                    self.live_capital,
                    last_err,
                )
            self._last_capital_refresh = now
        except Exception as exc:  # noqa: BLE001
            logger.warning("[LIVE] Failed to refresh capital: %s", exc)

    def _update_unrealized_and_metrics(self) -> None:
        if not self.metrics_tracker:
            return
        try:
            positions = self.broker.fetch_positions()
            total_unrealized = 0.0
            for pos in positions or []:
                symbol = pos.get("tradingsymbol") or pos.get("symbol")
                qty = float(pos.get("quantity") or 0.0)
                avg_price = float(pos.get("average_price") or 0.0)
                last_price = self.last_prices.get(symbol, avg_price)
                if qty > 0:
                    unreal = (last_price - avg_price) * qty
                elif qty < 0:
                    unreal = (avg_price - last_price) * abs(qty)
                else:
                    unreal = 0.0
                total_unrealized += unreal

            self.metrics_tracker.update_unrealized_pnl(total_unrealized)
            self.metrics_tracker.push_equity_snapshot(min_interval_sec=5.0)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Failed to update unrealized metrics: %s", exc)

    def stop(self) -> None:
        self.running = False
        try:
            self.market_data_engine.stop()
        except Exception:
            pass
        try:
            self.state_store.save_checkpoint(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "mode": "LIVE",
                    "positions": [],
                    "reason": "stop",
                }
            )
        except Exception:
            pass
        logger.info("LiveEquityEngine stopped")


# Backward-compatible name
LiveEngine = LiveEquityEngine
