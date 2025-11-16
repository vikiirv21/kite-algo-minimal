"""
Backtest Engine v3 - Main orchestrator for offline backtesting.

This module provides the core backtest engine that:
- Reuses StrategyEngine v2, PortfolioEngine, RegimeEngine, RiskEngine, TradeGuardian
- Runs completely offline on historical data
- Writes structured reports for analytics
- Does NOT modify or interfere with live/paper paths
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from analytics.strategy_analytics import StrategyAnalyticsEngine
from backtest.data_loader import HistoricalDataLoader
from core.portfolio_engine import PortfolioConfig, PortfolioEngine
from core.regime_detector import RegimeDetector
from core.risk_engine_v2 import OrderPlan, RiskConfig, RiskEngine, RiskState
from core.state_store import JournalStateStore, StateStore, make_fresh_state_from_config
from core.strategy_engine_v2 import OrderIntent, StrategyEngineV2
from core.trade_guardian import TradeGuardian

logger = logging.getLogger(__name__)


@dataclass
class BacktestConfig:
    """
    Configuration for backtest runs.
    
    Attributes:
        symbols: List of trading symbols
        strategies: List of strategy codes to enable
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        data_source: Data source type ('csv', 'hdf', 'kite_historical')
        timeframe: Bar timeframe ('1m', '5m', '15m', '1h', '1d')
        initial_equity: Starting capital
        position_sizing_mode: Position sizing mode ('fixed_qty', 'fixed_risk_atr')
    """
    
    symbols: List[str]
    strategies: List[str]
    start_date: str
    end_date: str
    data_source: str = "csv"
    timeframe: str = "5m"
    initial_equity: float = 100000.0
    position_sizing_mode: str = "fixed_qty"
    
    # Optional overrides
    portfolio_config: Optional[Dict[str, Any]] = None
    risk_config: Optional[Dict[str, Any]] = None
    regime_config: Optional[Dict[str, Any]] = None
    enable_guardian: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "symbols": self.symbols,
            "strategies": self.strategies,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "data_source": self.data_source,
            "timeframe": self.timeframe,
            "initial_equity": self.initial_equity,
            "position_sizing_mode": self.position_sizing_mode,
            "enable_guardian": self.enable_guardian,
        }


@dataclass
class BacktestResult:
    """
    Results from a backtest run.
    
    Attributes:
        run_id: Unique run identifier
        config: BacktestConfig used
        equity_curve: List of equity snapshots over time
        per_strategy: Per-strategy performance metrics
        per_symbol: Per-symbol performance metrics
        trades: List of all trades/fills
        overall_metrics: Overall performance metrics
    """
    
    run_id: str
    config: BacktestConfig
    equity_curve: List[Dict[str, Any]] = field(default_factory=list)
    per_strategy: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    per_symbol: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    trades: List[Dict[str, Any]] = field(default_factory=list)
    overall_metrics: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "run_id": self.run_id,
            "config": self.config.to_dict(),
            "equity_curve": self.equity_curve,
            "per_strategy": self.per_strategy,
            "per_symbol": self.per_symbol,
            "trades": self.trades,
            "overall_metrics": self.overall_metrics,
        }


class BacktestEngineV3:
    """
    Backtest Engine v3 - Offline backtesting with core component reuse.
    
    Architecture:
    - HistoricalDataLoader: Load bars from data source
    - RegimeEngine: Compute market regime
    - StrategyEngine v2: Generate trading signals
    - PortfolioEngine: Compute position sizes
    - RiskEngine: Apply risk checks
    - TradeGuardian: Pre-execution validation (optional)
    - Simulated execution: Fill orders at bar close prices
    - StateStore + JournalStore: Track state and journal trades
    """
    
    def __init__(
        self,
        bt_config: BacktestConfig,
        config: Dict[str, Any],
        logger_instance: Optional[logging.Logger] = None,
    ):
        """
        Initialize the backtest engine.
        
        Args:
            bt_config: Backtest-specific configuration
            config: Main application config (YAML)
            logger_instance: Optional logger instance
        """
        self.bt_config = bt_config
        self.config = config
        self.logger = logger_instance or logger
        
        # Generate run ID
        self.run_id = f"bt_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        
        # Setup output directory
        base_dir = Path(__file__).resolve().parents[1]
        self.artifacts_dir = base_dir / "artifacts"
        self.backtest_dir = self.artifacts_dir / "backtests" / self.run_id
        self.backtest_dir.mkdir(parents=True, exist_ok=True)
        
        self.logger.info("BacktestEngineV3 initialized: run_id=%s", self.run_id)
        
        # Initialize state stores (isolated for backtest)
        self.state_store = StateStore(
            checkpoint_path=self.backtest_dir / "state_checkpoint.json",
            log_path=self.backtest_dir / "events.jsonl",
        )
        
        self.journal_store = JournalStateStore(
            artifacts_dir=self.backtest_dir,
            mode="backtest",
        )
        
        # Initialize state
        self.state = make_fresh_state_from_config(config)
        self.state["mode"] = "BACKTEST"
        self.state["equity"]["paper_capital"] = bt_config.initial_equity
        self.state["equity"]["cash"] = bt_config.initial_equity
        self.state["equity"]["free_notional"] = bt_config.initial_equity
        
        # Initialize data loader
        self.data_loader = HistoricalDataLoader(
            data_source=bt_config.data_source,
            timeframe=bt_config.timeframe,
            symbols=bt_config.symbols,
            config=config,
            logger_instance=self.logger,
        )
        
        # Initialize regime engine
        regime_cfg = bt_config.regime_config or config.get("regime", {})
        self.regime_engine = RegimeDetector(
            short_window=regime_cfg.get("short_window", 21),
            long_window=regime_cfg.get("long_window", 55),
            atr_window=regime_cfg.get("atr_window", 21),
            atr_threshold=regime_cfg.get("atr_threshold", 0.75),
            primary_symbol=bt_config.symbols[0] if bt_config.symbols else None,
        )
        
        # Initialize portfolio engine
        portfolio_cfg_dict = bt_config.portfolio_config or config.get("portfolio", {})
        portfolio_cfg_dict["position_sizing_mode"] = bt_config.position_sizing_mode
        portfolio_cfg = PortfolioConfig.from_dict(portfolio_cfg_dict)
        self.portfolio_engine = PortfolioEngine(
            portfolio_config=portfolio_cfg,
            state_store=self.state,
            journal_store=self.journal_store,
            logger_instance=self.logger,
            mde=None,  # No MDE in backtest
        )
        
        # Initialize risk engine
        risk_cfg_dict = bt_config.risk_config or config.get("risk", {})
        risk_cfg_dict["capital"] = bt_config.initial_equity
        self.risk_config = RiskConfig(**{k: v for k, v in risk_cfg_dict.items() if hasattr(RiskConfig, k)})
        self.risk_engine = RiskEngine(self.risk_config, state=None)
        
        # Initialize trade guardian (optional)
        self.guardian = None
        if bt_config.enable_guardian:
            guardian_config = config.get("guardian", {})
            guardian_config["enabled"] = True
            self.guardian = TradeGuardian(
                config={"guardian": guardian_config},
                state_store=self.state,
                logger_instance=self.logger,
            )
        
        # Initialize strategy engine v2 (will be configured when strategies are registered)
        self.strategy_engine = None
        
        # Tracking
        self.current_bar: Optional[Dict[str, Any]] = None
        self.bar_index = 0
        self.positions: Dict[str, Dict[str, Any]] = {}  # symbol -> position
        self.equity_history: List[Dict[str, Any]] = []
        self.trades: List[Dict[str, Any]] = []
        
        self.logger.info("BacktestEngineV3 initialization complete")
    
    def run(self) -> BacktestResult:
        """
        Run the backtest.
        
        Returns:
            BacktestResult with equity curve, trades, and metrics
        """
        self.logger.info("Starting backtest run: %s", self.run_id)
        self.logger.info("Config: %s", self.bt_config.to_dict())
        
        # Save config
        config_path = self.backtest_dir / "config.json"
        with config_path.open("w") as f:
            json.dump(self.bt_config.to_dict(), f, indent=2)
        
        # Initialize strategy engine (needs to be done before running)
        self._initialize_strategy_engine()
        
        # Run backtest for each symbol
        for symbol in self.bt_config.symbols:
            self.logger.info("Processing symbol: %s", symbol)
            self._process_symbol(symbol)
        
        # Compute final results
        result = self._compute_results()
        
        # Save results
        self._save_results(result)
        
        self.logger.info("Backtest complete: %s", self.run_id)
        return result
    
    def _initialize_strategy_engine(self):
        """Initialize strategy engine with configured strategies."""
        # For now, we'll use a mock strategy engine
        # In a full implementation, this would load actual strategies
        self.logger.info("Initializing strategy engine with strategies: %s", self.bt_config.strategies)
        
        # Note: StrategyEngineV2 requires a MarketDataEngine, which we don't have in backtest
        # We'll need to either mock it or create a lightweight version
        # For now, we'll defer actual strategy execution
    
    def _process_symbol(self, symbol: str):
        """
        Process all bars for a symbol.
        
        Args:
            symbol: Trading symbol
        """
        bars_processed = 0
        
        for bar in self.data_loader.iter_bars(symbol, self.bt_config.start_date, self.bt_config.end_date):
            self.current_bar = bar
            self.bar_index += 1
            
            # Update regime
            self._update_regime(symbol, bar)
            
            # Generate signals (simplified for now)
            intents = self._generate_signals(symbol, bar)
            
            # Process intents
            for intent in intents:
                self._process_intent(intent, bar)
            
            # Update equity snapshot
            self._record_equity_snapshot(bar)
            
            bars_processed += 1
        
        self.logger.info("Processed %d bars for %s", bars_processed, symbol)
    
    def _update_regime(self, symbol: str, bar: Dict[str, Any]):
        """Update market regime."""
        self.regime_engine.update(
            symbol=symbol,
            close=bar["close"],
            high=bar["high"],
            low=bar["low"],
            timestamp=bar["timestamp"],
        )
    
    def _generate_signals(self, symbol: str, bar: Dict[str, Any]) -> List[OrderIntent]:
        """
        Generate trading signals.
        
        For now, this is a placeholder. In full implementation,
        this would call StrategyEngine v2.
        """
        # Placeholder: no signals
        return []
    
    def _process_intent(self, intent: OrderIntent, bar: Dict[str, Any]):
        """
        Process an order intent.
        
        Args:
            intent: Order intent from strategy
            bar: Current bar
        """
        # Apply portfolio sizing
        sized_intent = self._apply_portfolio_sizing(intent, bar)
        if sized_intent is None:
            return
        
        # Apply risk checks
        if not self._apply_risk_checks(sized_intent, bar):
            return
        
        # Apply guardian checks (if enabled)
        if self.guardian is not None:
            if not self._apply_guardian_checks(sized_intent, bar):
                return
        
        # Simulate fill
        self._simulate_fill(sized_intent, bar)
    
    def _apply_portfolio_sizing(
        self,
        intent: OrderIntent,
        bar: Dict[str, Any],
    ) -> Optional[OrderIntent]:
        """Apply portfolio sizing logic."""
        # Simplified: use intent as-is
        # Full implementation would call PortfolioEngine.compute_position_size()
        return intent
    
    def _apply_risk_checks(self, intent: OrderIntent, bar: Dict[str, Any]) -> bool:
        """Apply risk engine checks."""
        # Simplified: always approve
        # Full implementation would call RiskEngine.plan_order()
        return True
    
    def _apply_guardian_checks(self, intent: OrderIntent, bar: Dict[str, Any]) -> bool:
        """Apply trade guardian checks."""
        # Simplified: always approve
        # Full implementation would call TradeGuardian.validate_pre_trade()
        return True
    
    def _simulate_fill(self, intent: OrderIntent, bar: Dict[str, Any]):
        """
        Simulate order fill at bar close price.
        
        Args:
            intent: Order intent
            bar: Current bar
        """
        fill_price = bar["close"]
        fill_time = bar["timestamp"]
        
        # Update position
        current_qty = self.positions.get(intent.symbol, {}).get("qty", 0)
        
        if intent.action == "BUY":
            new_qty = current_qty + intent.qty
        elif intent.action == "SELL":
            new_qty = current_qty - intent.qty
        else:  # EXIT
            new_qty = 0
        
        # Record trade
        trade = {
            "timestamp": fill_time.isoformat(),
            "symbol": intent.symbol,
            "strategy": intent.strategy_code,
            "side": intent.action,
            "qty": intent.qty,
            "price": fill_price,
            "reason": intent.reason,
            "bar_index": self.bar_index,
        }
        self.trades.append(trade)
        
        # Update position tracking
        if new_qty == 0:
            self.positions.pop(intent.symbol, None)
        else:
            self.positions[intent.symbol] = {
                "qty": new_qty,
                "entry_price": fill_price,
                "entry_time": fill_time,
            }
        
        # Update state
        self._update_state_after_fill(intent, fill_price, new_qty)
        
        # Journal the trade
        self._journal_trade(trade)
    
    def _update_state_after_fill(self, intent: OrderIntent, fill_price: float, new_qty: int):
        """Update state after a fill."""
        # Update equity (simplified)
        # Full implementation would track P&L properly
        pass
    
    def _journal_trade(self, trade: Dict[str, Any]):
        """Journal a trade to the store."""
        order_row = {
            "timestamp": trade["timestamp"],
            "symbol": trade["symbol"],
            "strategy": trade.get("strategy", ""),
            "side": trade["side"],
            "quantity": trade["qty"],
            "price": trade["price"],
            "status": "FILLED",
            "order_id": f"BT_{self.run_id}_{len(self.trades)}",
        }
        self.journal_store.append_orders([order_row])
    
    def _record_equity_snapshot(self, bar: Dict[str, Any]):
        """Record equity snapshot."""
        # Compute equity (simplified)
        cash = self.state["equity"]["cash"]
        unrealized_pnl = 0.0
        
        # Calculate unrealized P&L from open positions
        for symbol, pos in self.positions.items():
            if symbol == bar.get("symbol"):
                current_price = bar["close"]
                entry_price = pos["entry_price"]
                qty = pos["qty"]
                unrealized_pnl += (current_price - entry_price) * qty
        
        equity = cash + unrealized_pnl
        
        snapshot = {
            "timestamp": bar["timestamp"].isoformat(),
            "equity": equity,
            "cash": cash,
            "unrealized_pnl": unrealized_pnl,
            "bar_index": self.bar_index,
        }
        self.equity_history.append(snapshot)
    
    def _compute_results(self) -> BacktestResult:
        """Compute final backtest results."""
        self.logger.info("Computing backtest results...")
        
        # Compute overall metrics
        overall_metrics = self._compute_overall_metrics()
        
        # Compute per-strategy metrics (placeholder)
        per_strategy = {}
        for strategy_code in self.bt_config.strategies:
            per_strategy[strategy_code] = {
                "trades": 0,
                "pnl": 0.0,
                "win_rate": 0.0,
            }
        
        # Compute per-symbol metrics (placeholder)
        per_symbol = {}
        for symbol in self.bt_config.symbols:
            per_symbol[symbol] = {
                "trades": 0,
                "pnl": 0.0,
                "win_rate": 0.0,
            }
        
        result = BacktestResult(
            run_id=self.run_id,
            config=self.bt_config,
            equity_curve=self.equity_history,
            per_strategy=per_strategy,
            per_symbol=per_symbol,
            trades=self.trades,
            overall_metrics=overall_metrics,
        )
        
        return result
    
    def _compute_overall_metrics(self) -> Dict[str, Any]:
        """Compute overall performance metrics."""
        if not self.equity_history:
            return {}
        
        initial_equity = self.bt_config.initial_equity
        final_equity = self.equity_history[-1]["equity"] if self.equity_history else initial_equity
        
        total_return = final_equity - initial_equity
        total_return_pct = (total_return / initial_equity) * 100 if initial_equity > 0 else 0.0
        
        return {
            "initial_equity": initial_equity,
            "final_equity": final_equity,
            "total_return": total_return,
            "total_return_pct": total_return_pct,
            "total_trades": len(self.trades),
            "bars_processed": self.bar_index,
        }
    
    def _save_results(self, result: BacktestResult):
        """Save backtest results to disk."""
        self.logger.info("Saving backtest results...")
        
        # Save summary JSON
        summary_path = self.backtest_dir / "summary.json"
        with summary_path.open("w") as f:
            json.dump(result.to_dict(), f, indent=2, default=str)
        
        # Save trades CSV
        trades_path = self.backtest_dir / "trades.csv"
        if self.trades:
            import csv
            with trades_path.open("w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=self.trades[0].keys())
                writer.writeheader()
                writer.writerows(self.trades)
        
        # Save equity curve JSON
        equity_path = self.backtest_dir / "equity_curve.json"
        with equity_path.open("w") as f:
            json.dump(self.equity_history, f, indent=2, default=str)
        
        self.logger.info("Results saved to: %s", self.backtest_dir)
