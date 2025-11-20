"""
Runtime Metrics Tracker v2 - Advanced Analytics Layer

This module provides real-time tracking and persistence of trading metrics including:
- Equity curve with realized/unrealized PnL
- Per-symbol and per-strategy PnL tracking
- Trade statistics (win rate, profit factor, etc.)
- Position counts and exposure metrics

The tracker automatically persists metrics to JSON for dashboard consumption.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


@dataclass
class EquitySnapshot:
    """Single point in the equity curve."""
    timestamp: str
    equity: float
    realized_pnl: float
    unrealized_pnl: float


@dataclass
class SymbolMetrics:
    """Per-symbol performance metrics."""
    symbol: str
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    total_pnl: float = 0.0
    trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0


@dataclass
class StrategyMetrics:
    """Per-strategy performance metrics."""
    strategy_id: str
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    total_pnl: float = 0.0
    trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0


class RuntimeMetricsTracker:
    """
    Advanced runtime metrics tracker for HFT trading system.
    
    Features:
    - Real-time equity curve tracking
    - Per-symbol and per-strategy PnL aggregation
    - Trade statistics (win rate, profit factor, R-multiples)
    - Automatic JSON persistence for dashboard
    - Thread-safe updates
    """
    
    def __init__(
        self,
        starting_capital: float,
        artifacts_dir: Optional[Path] = None,
        auto_persist: bool = True,
    ):
        """
        Initialize the RuntimeMetricsTracker.
        
        Args:
            starting_capital: Initial capital amount
            artifacts_dir: Directory to store metrics (default: artifacts/analytics)
            auto_persist: Whether to auto-save after each update
        """
        self.starting_capital = float(starting_capital)
        self.current_equity = self.starting_capital
        self.realized_pnl = 0.0
        self.unrealized_pnl = 0.0
        self.daily_pnl = 0.0
        self.auto_persist = auto_persist
        
        # Equity curve (list of snapshots)
        self.equity_curve: List[EquitySnapshot] = []
        
        # Per-symbol metrics
        self.symbol_metrics: Dict[str, SymbolMetrics] = {}
        
        # Per-strategy metrics
        self.strategy_metrics: Dict[str, StrategyMetrics] = {}
        
        # Trade counters
        self.total_trades = 0
        self.closed_trades = 0
        self.open_positions_count = 0
        self.win_trades = 0
        self.loss_trades = 0
        self.breakeven_trades = 0
        
        # PnL statistics
        self.gross_profit = 0.0
        self.gross_loss = 0.0
        self.biggest_win = 0.0
        self.biggest_loss = 0.0
        
        # Drawdown tracking
        self.max_equity = self.starting_capital
        self.min_equity = self.starting_capital
        self.max_drawdown = 0.0
        
        # Artifacts path setup
        if artifacts_dir is None:
            base_dir = Path(__file__).resolve().parents[1]
            artifacts_dir = base_dir / "artifacts" / "analytics"
        else:
            artifacts_dir = Path(artifacts_dir) / "analytics"
        
        self.artifacts_dir = artifacts_dir
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.metrics_path = self.artifacts_dir / "runtime_metrics.json"
        
        logger.info(
            "RuntimeMetricsTracker initialized: starting_capital=%.2f, metrics_path=%s",
            self.starting_capital,
            self.metrics_path,
        )
    
    def snapshot_equity(
        self,
        realized_pnl: float,
        unrealized_pnl: float,
        starting_capital: Optional[float] = None,
    ) -> None:
        """
        Take a snapshot of current equity for the equity curve.
        
        Args:
            realized_pnl: Current total realized PnL
            unrealized_pnl: Current total unrealized PnL
            starting_capital: Override starting capital if needed
        """
        if starting_capital is not None:
            self.starting_capital = float(starting_capital)
        
        self.realized_pnl = float(realized_pnl)
        self.unrealized_pnl = float(unrealized_pnl)
        self.current_equity = self.starting_capital + self.realized_pnl + self.unrealized_pnl
        self.daily_pnl = self.realized_pnl + self.unrealized_pnl
        
        # Update drawdown tracking
        if self.current_equity > self.max_equity:
            self.max_equity = self.current_equity
        if self.current_equity < self.min_equity:
            self.min_equity = self.current_equity
        
        drawdown = self.max_equity - self.current_equity
        if drawdown > self.max_drawdown:
            self.max_drawdown = drawdown
        
        # Add to equity curve
        snapshot = EquitySnapshot(
            timestamp=datetime.now(timezone.utc).isoformat(),
            equity=self.current_equity,
            realized_pnl=self.realized_pnl,
            unrealized_pnl=self.unrealized_pnl,
        )
        self.equity_curve.append(snapshot)
        
        # Limit equity curve to last 1000 points to prevent unbounded growth
        if len(self.equity_curve) > 1000:
            self.equity_curve = self.equity_curve[-1000:]
        
        if self.auto_persist:
            self.persist()
    
    def update_symbol_pnl(
        self,
        symbol: str,
        realized_delta: float = 0.0,
        unrealized_delta: float = 0.0,
    ) -> None:
        """
        Update PnL for a specific symbol.
        
        Args:
            symbol: Trading symbol
            realized_delta: Change in realized PnL for this update
            unrealized_delta: Change in unrealized PnL for this update
        """
        if symbol not in self.symbol_metrics:
            self.symbol_metrics[symbol] = SymbolMetrics(symbol=symbol)
        
        metrics = self.symbol_metrics[symbol]
        metrics.realized_pnl += float(realized_delta)
        metrics.unrealized_pnl += float(unrealized_delta)
        metrics.total_pnl = metrics.realized_pnl + metrics.unrealized_pnl
        
        # Update trade stats if this was a realized trade
        if realized_delta != 0:
            metrics.trades += 1
            if realized_delta > 0:
                metrics.wins += 1
            elif realized_delta < 0:
                metrics.losses += 1
            
            # Update win rate
            if metrics.trades > 0:
                metrics.win_rate = metrics.wins / metrics.trades
        
        if self.auto_persist:
            self.persist()
    
    def update_strategy_pnl(
        self,
        strategy_id: str,
        realized_delta: float = 0.0,
        unrealized_delta: float = 0.0,
    ) -> None:
        """
        Update PnL for a specific strategy.
        
        Args:
            strategy_id: Strategy identifier
            realized_delta: Change in realized PnL for this update
            unrealized_delta: Change in unrealized PnL for this update
        """
        if strategy_id not in self.strategy_metrics:
            self.strategy_metrics[strategy_id] = StrategyMetrics(strategy_id=strategy_id)
        
        metrics = self.strategy_metrics[strategy_id]
        metrics.realized_pnl += float(realized_delta)
        metrics.unrealized_pnl += float(unrealized_delta)
        metrics.total_pnl = metrics.realized_pnl + metrics.unrealized_pnl
        
        # Update trade stats if this was a realized trade
        if realized_delta != 0:
            metrics.trades += 1
            if realized_delta > 0:
                metrics.wins += 1
            elif realized_delta < 0:
                metrics.losses += 1
            
            # Update win rate
            if metrics.trades > 0:
                metrics.win_rate = metrics.wins / metrics.trades
        
        if self.auto_persist:
            self.persist()
    
    def set_open_positions_count(self, count: int) -> None:
        """
        Update the count of open positions.
        
        Args:
            count: Number of currently open positions
        """
        self.open_positions_count = int(count)
        
        if self.auto_persist:
            self.persist()
    
    def inc_closed_trades(self) -> None:
        """Increment the count of closed trades."""
        self.closed_trades += 1
        self.total_trades += 1
        
        if self.auto_persist:
            self.persist()
    
    def record_trade_result(self, pnl: float) -> None:
        """
        Record the result of a closed trade.
        
        Args:
            pnl: Realized PnL of the trade
        """
        self.closed_trades += 1
        self.total_trades += 1
        
        pnl_val = float(pnl)
        
        if pnl_val > 0:
            self.win_trades += 1
            self.gross_profit += pnl_val
            if pnl_val > self.biggest_win:
                self.biggest_win = pnl_val
        elif pnl_val < 0:
            self.loss_trades += 1
            self.gross_loss += abs(pnl_val)
            if pnl_val < self.biggest_loss:
                self.biggest_loss = pnl_val
        else:
            self.breakeven_trades += 1
        
        if self.auto_persist:
            self.persist()
    
    def compute_statistics(self) -> Dict[str, Any]:
        """
        Compute derived statistics like win rate, profit factor, etc.
        
        Returns:
            Dictionary of computed statistics
        """
        win_rate = self.win_trades / self.closed_trades if self.closed_trades > 0 else 0.0
        profit_factor = self.gross_profit / self.gross_loss if self.gross_loss > 0 else 0.0
        avg_win = self.gross_profit / self.win_trades if self.win_trades > 0 else 0.0
        avg_loss = self.gross_loss / self.loss_trades if self.loss_trades > 0 else 0.0
        avg_r_multiple = (avg_win / avg_loss) if avg_loss > 0 else 0.0
        
        return {
            "total_trades": self.total_trades,
            "closed_trades": self.closed_trades,
            "win_trades": self.win_trades,
            "loss_trades": self.loss_trades,
            "breakeven_trades": self.breakeven_trades,
            "win_rate": win_rate,
            "gross_profit": self.gross_profit,
            "gross_loss": self.gross_loss,
            "net_pnl": self.realized_pnl,
            "profit_factor": profit_factor,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "avg_r_multiple": avg_r_multiple,
            "biggest_win": self.biggest_win,
            "biggest_loss": self.biggest_loss,
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert metrics to dictionary for JSON serialization.
        
        Returns:
            Dictionary containing all metrics
        """
        stats = self.compute_statistics()
        
        return {
            "asof": datetime.now(timezone.utc).isoformat(),
            "mode": "paper",
            "equity": self.current_equity,
            "starting_capital": self.starting_capital,
            "current_equity": self.current_equity,
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl,
            "daily_pnl": self.daily_pnl,
            "max_drawdown": self.max_drawdown,
            "max_equity": self.max_equity,
            "min_equity": self.min_equity,
            "open_positions_count": self.open_positions_count,
            "overall": stats,
            "pnl_per_symbol": {
                symbol: {
                    "realized_pnl": m.realized_pnl,
                    "unrealized_pnl": m.unrealized_pnl,
                    "total_pnl": m.total_pnl,
                    "trades": m.trades,
                    "wins": m.wins,
                    "losses": m.losses,
                    "win_rate": m.win_rate,
                }
                for symbol, m in self.symbol_metrics.items()
            },
            "pnl_per_strategy": {
                strategy: {
                    "realized_pnl": m.realized_pnl,
                    "unrealized_pnl": m.unrealized_pnl,
                    "total_pnl": m.total_pnl,
                    "trades": m.trades,
                    "wins": m.wins,
                    "losses": m.losses,
                    "win_rate": m.win_rate,
                }
                for strategy, m in self.strategy_metrics.items()
            },
            "equity_curve": [
                {
                    "timestamp": snap.timestamp,
                    "equity": snap.equity,
                    "realized_pnl": snap.realized_pnl,
                    "unrealized_pnl": snap.unrealized_pnl,
                }
                for snap in self.equity_curve
            ],
        }
    
    def persist(self) -> None:
        """
        Persist metrics to JSON file.
        
        Writes metrics to artifacts/analytics/runtime_metrics.json for
        dashboard and API consumption.
        """
        try:
            metrics_dict = self.to_dict()
            
            # Ensure directory exists
            self.artifacts_dir.mkdir(parents=True, exist_ok=True)
            
            # Write to temp file first, then rename for atomic write
            temp_path = self.metrics_path.with_suffix(".tmp")
            with temp_path.open("w", encoding="utf-8") as f:
                json.dump(metrics_dict, f, indent=2, default=str)
            
            # Atomic rename
            temp_path.replace(self.metrics_path)
            
            logger.debug("Metrics persisted to %s", self.metrics_path)
        except Exception as exc:
            logger.error("Failed to persist metrics: %s", exc, exc_info=True)
    
    def load(self) -> bool:
        """
        Load metrics from JSON file if it exists.
        
        Returns:
            True if metrics were loaded, False otherwise
        """
        if not self.metrics_path.exists():
            logger.debug("No existing metrics file to load: %s", self.metrics_path)
            return False
        
        try:
            with self.metrics_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Restore equity state
            self.current_equity = float(data.get("current_equity", self.starting_capital))
            self.realized_pnl = float(data.get("realized_pnl", 0.0))
            self.unrealized_pnl = float(data.get("unrealized_pnl", 0.0))
            self.daily_pnl = float(data.get("daily_pnl", 0.0))
            self.max_drawdown = float(data.get("max_drawdown", 0.0))
            self.max_equity = float(data.get("max_equity", self.starting_capital))
            self.min_equity = float(data.get("min_equity", self.starting_capital))
            self.open_positions_count = int(data.get("open_positions_count", 0))
            
            # Restore overall stats
            overall = data.get("overall", {})
            self.total_trades = int(overall.get("total_trades", 0))
            self.closed_trades = int(overall.get("closed_trades", 0))
            self.win_trades = int(overall.get("win_trades", 0))
            self.loss_trades = int(overall.get("loss_trades", 0))
            self.breakeven_trades = int(overall.get("breakeven_trades", 0))
            self.gross_profit = float(overall.get("gross_profit", 0.0))
            self.gross_loss = float(overall.get("gross_loss", 0.0))
            self.biggest_win = float(overall.get("biggest_win", 0.0))
            self.biggest_loss = float(overall.get("biggest_loss", 0.0))
            
            # Restore per-symbol metrics
            pnl_per_symbol = data.get("pnl_per_symbol", {})
            for symbol, metrics in pnl_per_symbol.items():
                self.symbol_metrics[symbol] = SymbolMetrics(
                    symbol=symbol,
                    realized_pnl=float(metrics.get("realized_pnl", 0.0)),
                    unrealized_pnl=float(metrics.get("unrealized_pnl", 0.0)),
                    total_pnl=float(metrics.get("total_pnl", 0.0)),
                    trades=int(metrics.get("trades", 0)),
                    wins=int(metrics.get("wins", 0)),
                    losses=int(metrics.get("losses", 0)),
                    win_rate=float(metrics.get("win_rate", 0.0)),
                )
            
            # Restore per-strategy metrics
            pnl_per_strategy = data.get("pnl_per_strategy", {})
            for strategy, metrics in pnl_per_strategy.items():
                self.strategy_metrics[strategy] = StrategyMetrics(
                    strategy_id=strategy,
                    realized_pnl=float(metrics.get("realized_pnl", 0.0)),
                    unrealized_pnl=float(metrics.get("unrealized_pnl", 0.0)),
                    total_pnl=float(metrics.get("total_pnl", 0.0)),
                    trades=int(metrics.get("trades", 0)),
                    wins=int(metrics.get("wins", 0)),
                    losses=int(metrics.get("losses", 0)),
                    win_rate=float(metrics.get("win_rate", 0.0)),
                )
            
            # Restore equity curve
            equity_curve_data = data.get("equity_curve", [])
            self.equity_curve = [
                EquitySnapshot(
                    timestamp=snap["timestamp"],
                    equity=float(snap["equity"]),
                    realized_pnl=float(snap["realized_pnl"]),
                    unrealized_pnl=float(snap["unrealized_pnl"]),
                )
                for snap in equity_curve_data
            ]
            
            logger.info("Metrics loaded from %s", self.metrics_path)
            return True
        except Exception as exc:
            logger.error("Failed to load metrics: %s", exc, exc_info=True)
            return False
