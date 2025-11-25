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
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from analytics.runtime_metrics import RuntimeMetricsTracker
from analytics.trade_recorder import TradeRecorder
from broker.kite_bridge import KiteBroker
from broker.kite_client import KiteClient
from core.capital_provider import CapitalProvider, create_capital_provider
from core.config import AppConfig
from core.market_data_engine_v2 import MarketDataEngineV2
from core.market_session import is_market_open
from core.modes import TradingMode
from core.state_store import JournalStateStore, StateStore
from core.strategy_engine_v2 import StrategyEngineV2
from core.universe import load_equity_universe
from core.reconciliation_engine import ReconciliationEngine
from engine.execution_engine_v3_adapter import create_execution_engine
from engine.execution_engine import OrderIntent
from risk.position_sizer import SizerConfig, DynamicPositionSizer, PortfolioState

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = BASE_DIR / "artifacts"
CHECKPOINTS_DIR = ARTIFACTS_DIR / "checkpoints"


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

        # Brokers/clients
        self.kite_client = kite_client or KiteClient()
        self.kite = self.kite_client.api
        self.broker = KiteBroker(cfg.raw, logger_instance=logger)

        # State + journal
        self.state_store = StateStore(checkpoint_path=self.checkpoint_path)
        self.journal_store = JournalStateStore(mode="live", artifacts_dir=self.artifacts_dir)
        self.recorder = TradeRecorder(artifacts_dir=self.artifacts_dir)

        # Metrics - use config capital as starting value for metrics tracker
        config_capital = float(
            cfg.trading.get("live_capital", cfg.trading.get("paper_capital", 500_000))
        )
        self.metrics_tracker = RuntimeMetricsTracker(
            starting_capital=config_capital,
            mode="live",
            artifacts_dir=self.artifacts_dir,
            equity_curve_maxlen=500,
        )

        # Capital provider - fetches real-time capital from Kite API in LIVE mode
        self.capital_provider: CapitalProvider = create_capital_provider(
            mode="LIVE",
            kite=self.kite,
            config_capital=config_capital,
            cache_ttl_seconds=30.0,
        )

        # Universe + sizing
        self.universe: List[str] = self._load_equity_universe()
        self.primary_timeframe = str(
            (cfg.trading.get("multi_tf_config") or [{"timeframe": "5m"}])[0].get("timeframe", "5m")
        )
        self.default_qty = int(cfg.trading.get("default_quantity", 1))
        trading_cfg = cfg.trading or {}
        risk_cfg = cfg.risk or {}
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
            max_trades=int(risk_cfg.get("max_concurrent_trades", trading_cfg.get("max_open_positions", 5))),
            risk_scale_min=float(risk_cfg.get("risk_scale_min", 0.3)),
            risk_scale_max=float(risk_cfg.get("risk_scale_max", 2.0)),
            risk_down_threshold=float(risk_cfg.get("risk_down_threshold", -0.02)),
            risk_up_threshold=float(risk_cfg.get("risk_up_threshold", 0.02)),
        )
        self.position_sizer = DynamicPositionSizer(sizer_cfg)

        # Market data v2 (live ticks)
        data_cfg = cfg.raw.get("data", {})
        data_cfg.setdefault("feed", "kite")
        self.market_data_engine = MarketDataEngineV2(
            cfg=data_cfg,
            kite=self.kite,
            universe=self.universe,
            meta={},
            logger_instance=logger,
        )

        # Strategy engine v2 (signals) wired to this engine for execution
        self.strategy_engine = StrategyEngineV2.from_config(cfg.raw, logger)
        self.strategy_engine.market_data = self.market_data_engine
        self.strategy_engine.market_data_engine = self.market_data_engine
        self.strategy_engine.mde = self.market_data_engine
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
        logger.info("✅ LiveEquityEngine initialized (symbols=%d)", len(self.universe))

    def _load_equity_universe(self) -> List[str]:
        trading_cfg = self.cfg.trading or {}
        cfg_list = trading_cfg.get("equity_universe") or trading_cfg.get("equity_symbols") or []
        if isinstance(cfg_list, str):
            cfg_list = [cfg_list]
        cleaned = [str(sym).strip().upper() for sym in cfg_list if sym]
        if cleaned:
            return cleaned
        try:
            return load_equity_universe()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Falling back to empty equity universe (load error: %s)", exc)
            return []

    # ------------------------------------------------------------------ ticks
    def _on_tick(self, tick: Dict[str, Any]) -> None:
        """Handle normalized tick from KiteBroker."""
        if not tick:
            return
        symbol = tick.get("tradingsymbol")
        ltp = tick.get("last_price")
        if symbol and ltp:
            self.last_prices[symbol] = float(ltp)
            self.market_data_engine.on_tick_batch([tick])

    # ------------------------------------------------------------------ loop
    def run_forever(self) -> None:
        """Main live loop."""
        if not self.broker.ensure_logged_in():
            logger.error("Cannot start LiveEquityEngine: not logged in. Run scripts/login_kite.py")
            return

        # Start market data + tick subscription
        self.market_data_engine.start()
        tokens = list(self.market_data_engine.symbol_tokens.values())
        if tokens:
            self.broker.subscribe_ticks(tokens, self._on_tick)

        logger.info("LiveEquityEngine starting loop (tf=%s)", self.primary_timeframe)
        try:
            while self.running:
                if not is_market_open():
                    logger.info("Market closed; sleeping 30s")
                    time.sleep(30)
                    continue

                # Run strategies (will call _handle_signal via StrategyEngineV2)
                try:
                    self.strategy_engine.run(self.universe, timeframe=self.primary_timeframe)
                except Exception as exc:  # noqa: BLE001
                    logger.error("Strategy engine run failed: %s", exc, exc_info=True)

                # Update unrealized + equity snapshots
                self._update_unrealized_and_metrics()

                # Optional reconciliation
                if self.reconciler and self.reconciler.enabled:
                    try:
                        asyncio.run(self.reconciler.reconcile_orders())
                        asyncio.run(self.reconciler.reconcile_positions())
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("Reconciliation error (live): %s", exc)

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
        except Exception:
            qty = max(1, self.default_qty)

        if qty == 0:
            logger.info("Skipping %s for %s: sized qty=0", side, symbol)
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

            logger.info("Live order placed: %s %s x%s (id=%s status=%s)", side, symbol, qty, order_id, status)
        except Exception as exc:  # noqa: BLE001
            logger.error("Live order failed for %s: %s", symbol, exc, exc_info=True)

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
        live_capital = self.capital_provider.refresh()

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
