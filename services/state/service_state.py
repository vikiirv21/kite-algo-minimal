"""
State / Portfolio Service - Architecture v3 Phase 5

Maintains real-time portfolio state by consuming execution fill events.
Publishes state snapshots for dashboard consumption.

Topics:
- Subscribes: exec.fill.*
- Publishes: state.snapshot.updated.global
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from services.common.event_bus import EventBus, Event

from core.state_store import StateStore

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """Represents an open position."""
    symbol: str
    logical: str | None = None
    quantity: int = 0
    avg_price: float = 0.0
    realized_pnl: float = 0.0
    last_price: float | None = None
    profile: str | None = None
    strategy: str | None = None


@dataclass
class StrategyStats:
    """Per-strategy performance metrics."""
    strategy: str
    day_pnl: float = 0.0
    win_trades: int = 0  # Changed from 'wins' to match dashboard expectations
    loss_trades: int = 0  # Changed from 'losses' to match dashboard expectations
    open_trades: int = 0
    closed_trades: int = 0
    entry_count: int = 0  # Added for dashboard compatibility
    exit_count: int = 0   # Added for dashboard compatibility


@dataclass
class PortfolioEquity:
    """Portfolio equity and P&L tracking."""
    starting_capital: float
    cash: float
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    day_pnl: float = 0.0


@dataclass
class RuntimeState:
    """Complete runtime state snapshot."""
    mode: str
    equity: PortfolioEquity
    positions: dict[str, Position] = field(default_factory=dict)
    strategies: dict[str, StrategyStats] = field(default_factory=dict)
    last_heartbeat_ts: str | None = None


@dataclass
class ServiceConfig:
    """Configuration for State service."""
    name: str = "state"
    enabled: bool = True
    checkpoint_interval: int = 10  # Checkpoint every N fills


class StateService:
    """
    State / Portfolio Service.
    
    Responsibilities:
    - Track portfolio positions from execution fills
    - Compute realized and unrealized P&L
    - Maintain per-strategy statistics
    - Checkpoint state to disk
    - Publish state snapshots to EventBus
    """
    
    def __init__(self, bus: EventBus, cfg: Dict[str, Any], mode: str = "paper"):
        """
        Initialize State service.
        
        Args:
            bus: EventBus instance for pub/sub
            cfg: Configuration dict with trading.starting_capital
            mode: Trading mode - "paper" or "live"
        """
        self.bus = bus
        self.cfg = cfg
        self.mode = mode
        self.state = self._init_state()
        self.store = StateStore()
        self.fill_counter = 0
        self.checkpoint_interval = cfg.get("checkpoint_interval", 10)
        self.running = False
        self._subscribe()
        logger.info("StateService initialized in mode=%s", mode)
    
    def _init_state(self) -> RuntimeState:
        """
        Initialize state from checkpoint or create fresh state.
        
        Returns:
            RuntimeState initialized from checkpoint or config
        """
        # Try to load existing checkpoint
        checkpoint = self.store.load_checkpoint()
        
        if checkpoint and isinstance(checkpoint, dict):
            # Restore from checkpoint
            logger.info("Loading state from checkpoint")
            try:
                equity_data = checkpoint.get("equity", {})
                equity = PortfolioEquity(
                    starting_capital=float(equity_data.get("starting_capital", 0.0)),
                    cash=float(equity_data.get("cash", 0.0)),
                    realized_pnl=float(equity_data.get("realized_pnl", 0.0)),
                    unrealized_pnl=float(equity_data.get("unrealized_pnl", 0.0)),
                    day_pnl=float(equity_data.get("day_pnl", 0.0)),
                )
                
                # Restore positions
                positions = {}
                positions_data = checkpoint.get("positions", [])
                if isinstance(positions_data, list):
                    for pos_data in positions_data:
                        if isinstance(pos_data, dict):
                            symbol = pos_data.get("symbol", "")
                            if symbol:
                                positions[symbol] = Position(
                                    symbol=symbol,
                                    logical=pos_data.get("logical"),
                                    quantity=int(pos_data.get("quantity", 0)),
                                    avg_price=float(pos_data.get("avg_price", 0.0)),
                                    realized_pnl=float(pos_data.get("realized_pnl", 0.0)),
                                    last_price=self._safe_float(pos_data.get("last_price")),
                                    profile=pos_data.get("profile"),
                                    strategy=pos_data.get("strategy"),
                                )
                
                # Restore strategy stats
                strategies = {}
                strategies_data = checkpoint.get("strategies", {})
                if isinstance(strategies_data, dict):
                    for strat_name, strat_data in strategies_data.items():
                        if isinstance(strat_data, dict):
                            strategies[strat_name] = StrategyStats(
                                strategy=strat_name,
                                day_pnl=float(strat_data.get("day_pnl", 0.0)),
                                win_trades=int(strat_data.get("win_trades", strat_data.get("wins", 0))),
                                loss_trades=int(strat_data.get("loss_trades", strat_data.get("losses", 0))),
                                open_trades=int(strat_data.get("open_trades", 0)),
                                closed_trades=int(strat_data.get("closed_trades", 0)),
                                entry_count=int(strat_data.get("entry_count", 0)),
                                exit_count=int(strat_data.get("exit_count", 0)),
                            )
                
                state = RuntimeState(
                    mode=checkpoint.get("mode", self.mode),
                    equity=equity,
                    positions=positions,
                    strategies=strategies,
                    last_heartbeat_ts=checkpoint.get("last_heartbeat_ts"),
                )
                
                logger.info(
                    "Restored state: capital=%.2f cash=%.2f realized_pnl=%.2f positions=%d",
                    state.equity.starting_capital,
                    state.equity.cash,
                    state.equity.realized_pnl,
                    len(state.positions),
                )
                return state
            except Exception as e:
                logger.warning("Failed to restore from checkpoint: %s", e, exc_info=True)
                # Fall through to create fresh state
        
        # Create fresh state from config
        logger.info("Creating fresh state from config")
        trading_cfg = self.cfg.get("trading", {})
        starting_capital = float(trading_cfg.get("starting_capital") or trading_cfg.get("paper_capital", 500000.0))
        
        return RuntimeState(
            mode=self.mode,
            equity=PortfolioEquity(
                starting_capital=starting_capital,
                cash=starting_capital,
            ),
        )
    
    def _subscribe(self):
        """Subscribe to execution fill events."""
        self.bus.subscribe("exec.fill.*", self.on_fill)
        logger.info("StateService subscribed to exec.fill.*")
    
    def on_fill(self, event: Event):
        """
        Handle execution fill events and update portfolio state.
        
        Expected payload:
        {
          "order_id": "...",
          "symbol": "...",
          "logical": "NIFTY" | "RELIANCE" | null,
          "side": "BUY" | "SELL",
          "fill_qty": 50,
          "fill_price": 24501.5,
          "mode": "paper" | "live",
          "profile": "INTRADAY",
          "strategy": "ema20_50_intraday",
          "timestamp": "...",
        }
        
        Args:
            event: Event containing fill data
        """
        payload = event.payload or {}
        
        # 1) Basic validation
        symbol = payload.get("symbol")
        side = payload.get("side")
        fill_qty = payload.get("fill_qty")
        fill_price = payload.get("fill_price")
        
        if not symbol or not side or fill_qty is None or fill_price is None:
            logger.warning(
                "Invalid fill event: symbol=%s side=%s fill_qty=%s fill_price=%s",
                symbol, side, fill_qty, fill_price
            )
            return
        
        # Safe conversion - never call float(None)
        try:
            fill_qty = int(fill_qty)
            fill_price = float(fill_price)
        except (TypeError, ValueError) as e:
            logger.warning(
                "Cannot convert fill_qty=%r or fill_price=%r: %s",
                fill_qty, fill_price, e
            )
            return
        
        # Normalize side
        side_upper = str(side).upper()
        
        # 2) Update position for this symbol
        position = self.state.positions.get(symbol)
        if position is None:
            position = Position(
                symbol=symbol,
                logical=payload.get("logical"),
                profile=payload.get("profile"),
                strategy=payload.get("strategy"),
            )
            self.state.positions[symbol] = position
        
        old_qty = position.quantity
        old_avg_price = position.avg_price
        realized_pnl_delta = 0.0
        
        if side_upper == "BUY":
            # Buy: Increase position
            new_qty = old_qty + fill_qty
            if new_qty > 0:
                # Average price calculation
                position.avg_price = (old_avg_price * old_qty + fill_price * fill_qty) / new_qty
            else:
                position.avg_price = fill_price
            position.quantity = new_qty
            
            # Update cash (buy decreases cash)
            self.state.equity.cash -= fill_price * fill_qty
            
        elif side_upper == "SELL":
            # Sell: Decrease position
            new_qty = old_qty - fill_qty
            
            # Calculate realized P&L
            if old_qty != 0:
                realized_pnl_delta = (fill_price - old_avg_price) * min(fill_qty, old_qty)
            
            position.quantity = new_qty
            position.realized_pnl += realized_pnl_delta
            
            # Update cash (sell increases cash)
            self.state.equity.cash += fill_price * fill_qty
            
            # If position is flat, we might keep it or remove it
            # For now, keep it to track realized_pnl per symbol
            if new_qty == 0:
                position.avg_price = 0.0
        
        # Update last price
        position.last_price = fill_price
        
        # 3) Update portfolio equity
        self.state.equity.realized_pnl += realized_pnl_delta
        
        # Compute unrealized P&L (simplified - use last_price as current price)
        total_unrealized = 0.0
        for pos in self.state.positions.values():
            if pos.quantity != 0 and pos.last_price is not None:
                unrealized = (pos.last_price - pos.avg_price) * pos.quantity
                total_unrealized += unrealized
        
        self.state.equity.unrealized_pnl = total_unrealized
        self.state.equity.day_pnl = self.state.equity.realized_pnl + self.state.equity.unrealized_pnl
        
        # 4) Update per-strategy stats
        strategy_name = payload.get("strategy")
        if strategy_name:
            if strategy_name not in self.state.strategies:
                self.state.strategies[strategy_name] = StrategyStats(strategy=strategy_name)
            
            stats = self.state.strategies[strategy_name]
            
            # Update day P&L with realized contribution
            stats.day_pnl += realized_pnl_delta
            
            # Track open/closed trades and entry/exit counts
            if side_upper == "BUY":
                # Entry - increment open trades and entry count
                stats.open_trades += 1
                stats.entry_count += 1
            elif side_upper == "SELL":
                # Exit - increment exit count
                stats.exit_count += 1
                
                # Could be partial or full exit
                if new_qty == 0 and old_qty > 0:
                    # Full exit - close the trade
                    stats.closed_trades += 1
                    stats.open_trades = max(0, stats.open_trades - 1)
                    
                    # Update wins/losses
                    if realized_pnl_delta > 0:
                        stats.win_trades += 1
                    elif realized_pnl_delta < 0:
                        stats.loss_trades += 1
        
        # 5) Update heartbeat timestamp
        self.state.last_heartbeat_ts = payload.get("timestamp", datetime.utcnow().isoformat())
        
        # 6) Increment fill counter and checkpoint if needed
        self.fill_counter += 1
        
        logger.info(
            "Fill processed: symbol=%s side=%s qty=%d price=%.2f | "
            "Position qty=%d avg=%.2f realized=%.2f | Portfolio realized=%.2f unrealized=%.2f",
            symbol, side_upper, fill_qty, fill_price,
            position.quantity, position.avg_price, position.realized_pnl,
            self.state.equity.realized_pnl, self.state.equity.unrealized_pnl,
        )
        
        # Checkpoint and publish snapshot
        self._checkpoint_if_needed()
        self._publish_snapshot()
    
    def _checkpoint_if_needed(self):
        """
        Checkpoint state to disk based on fill counter or interval.
        """
        if self.fill_counter % self.checkpoint_interval == 0:
            self._checkpoint()
    
    def _checkpoint(self):
        """
        Write state checkpoint to disk.
        
        Files written:
        - artifacts/checkpoints/runtime_state_latest.json (global)
        - artifacts/checkpoints/paper_state_latest.json (mode-specific)
        """
        snapshot = self._to_snapshot_dict()
        
        # Save to StateStore (runtime_state_latest.json)
        self.store.save_checkpoint(snapshot)
        
        # Also save mode-specific checkpoint
        artifacts_dir = Path(__file__).resolve().parents[2] / "artifacts"
        checkpoints_dir = artifacts_dir / "checkpoints"
        checkpoints_dir.mkdir(parents=True, exist_ok=True)
        
        mode_checkpoint_path = checkpoints_dir / f"{self.mode}_state_latest.json"
        try:
            with mode_checkpoint_path.open("w", encoding="utf-8") as f:
                json.dump(snapshot, f, indent=2, default=str)
            logger.debug("Checkpointed state to %s", mode_checkpoint_path)
        except Exception as e:
            logger.error("Failed to write mode-specific checkpoint: %s", e)
    
    def _publish_snapshot(self):
        """
        Publish current state snapshot to EventBus.
        
        Topic: state.snapshot.updated.global
        """
        snapshot = self._to_snapshot_dict()
        self.bus.publish("state.snapshot.updated.global", snapshot)
        logger.debug("Published state snapshot to EventBus")
    
    def _to_snapshot_dict(self) -> dict:
        """
        Convert RuntimeState to serializable dict.
        
        Returns:
            Dict representation of current state
        """
        # Convert positions dict to list
        positions_list = []
        for pos in self.state.positions.values():
            if pos.quantity != 0:  # Only include open positions
                positions_list.append({
                    "symbol": pos.symbol,
                    "logical": pos.logical,
                    "quantity": pos.quantity,
                    "avg_price": pos.avg_price,
                    "realized_pnl": pos.realized_pnl,
                    "last_price": pos.last_price,
                    "profile": pos.profile,
                    "strategy": pos.strategy,
                })
        
        # Convert strategies dict
        strategies_dict = {}
        for strat_name, stats in self.state.strategies.items():
            strategies_dict[strat_name] = {
                "day_pnl": stats.day_pnl,
                "win_trades": stats.win_trades,
                "loss_trades": stats.loss_trades,
                "open_trades": stats.open_trades,
                "closed_trades": stats.closed_trades,
                "entry_count": stats.entry_count,
                "exit_count": stats.exit_count,
            }
        
        # Compute additional metrics
        equity_value = (
            self.state.equity.starting_capital +
            self.state.equity.realized_pnl +
            self.state.equity.unrealized_pnl
        )
        
        # Calculate total notional exposure
        total_notional = 0.0
        for pos in self.state.positions.values():
            if pos.quantity != 0 and pos.last_price is not None:
                total_notional += abs(pos.quantity * pos.last_price)
        
        free_notional = equity_value - total_notional
        
        return {
            "mode": self.state.mode,
            "equity": {
                "paper_capital": self.state.equity.starting_capital,  # Dashboard expects this field
                "starting_capital": self.state.equity.starting_capital,
                "cash": self.state.equity.cash,
                "realized_pnl": self.state.equity.realized_pnl,
                "unrealized_pnl": self.state.equity.unrealized_pnl,
                "day_pnl": self.state.equity.day_pnl,
                "equity": equity_value,  # Total equity value
                "total_notional": total_notional,
                "free_notional": free_notional,
            },
            "positions": positions_list,
            "strategies": strategies_dict,
            "last_heartbeat_ts": self.state.last_heartbeat_ts,
            "timestamp": datetime.utcnow().isoformat(),
        }
    
    @staticmethod
    def _safe_float(value: Any) -> float | None:
        """
        Safely convert value to float, returning None if conversion fails.
        
        Args:
            value: Value to convert
            
        Returns:
            Float value or None
        """
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    
    def run_forever(self) -> None:
        """
        Main service loop with periodic checkpointing.
        
        The actual work is done by event handlers.
        This loop provides heartbeat and periodic checkpointing.
        """
        logger.info(f"StateService starting in mode={self.mode}...")
        self.running = True
        
        try:
            while self.running:
                # Update heartbeat
                self.state.last_heartbeat_ts = datetime.utcnow().isoformat()
                
                # Periodic checkpoint (every iteration)
                self._checkpoint()
                self._publish_snapshot()
                
                logger.debug("StateService heartbeat (mode=%s)", self.mode)
                time.sleep(10)  # Heartbeat every 10 seconds
                
        except KeyboardInterrupt:
            logger.info("StateService interrupted by user")
        finally:
            # Final checkpoint on shutdown
            self._checkpoint()
            self.running = False
            logger.info("StateService stopped")
