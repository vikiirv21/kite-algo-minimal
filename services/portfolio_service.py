"""
Portfolio Service

Tracks positions, PnL, equity, and exposure.
Updates on fills and publishes portfolio.updated events.

Features:
- on_fill(fill_event) - Update positions on new fills
- get_snapshot() - Get current portfolio state
- Track equity and exposure
- Write checkpoints to disk
- Publish portfolio.updated to dashboard feed
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.event_bus import EventBus

logger = logging.getLogger(__name__)


class PortfolioService:
    """
    Portfolio Service for position and PnL tracking.
    
    Manages:
    - Open positions (symbol, qty, avg_price)
    - Realized and unrealized PnL
    - Total equity and exposure
    - Checkpointing to disk
    """
    
    def __init__(
        self,
        initial_capital: float = 100000.0,
        event_bus: Optional[EventBus] = None,
        checkpoint_dir: Optional[Path] = None,
    ):
        """
        Initialize Portfolio Service.
        
        Args:
            initial_capital: Starting capital in account
            event_bus: EventBus for publishing updates
            checkpoint_dir: Directory for checkpoint files
        """
        self.initial_capital = initial_capital
        self.bus = event_bus
        self.checkpoint_dir = checkpoint_dir or Path("artifacts/portfolio")
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        
        # Portfolio state
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.realized_pnl: float = 0.0
        self.cash: float = initial_capital
        
        # Load from checkpoint if exists
        self._load_checkpoint()
        
        logger.info(
            "PortfolioService initialized (capital=%.2f, checkpoint_dir=%s)",
            initial_capital,
            self.checkpoint_dir
        )
    
    def on_fill(self, fill_event: Dict[str, Any]) -> None:
        """
        Handle fill event and update positions.
        
        Args:
            fill_event: Fill event dict or EventBus event with:
                - symbol: Trading symbol
                - side: BUY or SELL
                - qty: Quantity filled
                - avg_price: Average fill price
                - order_id: Order identifier
                
        Note: Handles both direct fill data or EventBus event format with payload.
        """
        # Handle EventBus event format (has 'payload' key)
        if "payload" in fill_event:
            fill_event = fill_event["payload"]
        
        symbol = fill_event.get("symbol")
        side = fill_event.get("side", "").upper()
        qty = fill_event.get("qty", 0)
        avg_price = fill_event.get("avg_price", 0.0)
        
        if not symbol or not side or qty <= 0 or avg_price <= 0:
            logger.warning("Invalid fill event: %s", fill_event)
            return
        
        logger.info(
            "Processing fill: %s %d %s @ %.2f",
            side, qty, symbol, avg_price
        )
        
        # Get or create position
        if symbol not in self.positions:
            self.positions[symbol] = {
                "symbol": symbol,
                "qty": 0,
                "avg_price": 0.0,
                "realized_pnl": 0.0,
                "last_updated": None,
            }
        
        pos = self.positions[symbol]
        current_qty = pos["qty"]
        current_avg = pos["avg_price"]
        
        # Update position based on side
        if side == "BUY":
            # Adding to position
            new_qty = current_qty + qty
            if new_qty != 0:
                # Update average price
                new_avg = (
                    (current_qty * current_avg) + (qty * avg_price)
                ) / new_qty
            else:
                new_avg = avg_price
            
            # Update cash
            self.cash -= qty * avg_price
            
            pos["qty"] = new_qty
            pos["avg_price"] = new_avg
            
        elif side == "SELL":
            # Reducing position
            new_qty = current_qty - qty
            
            # Calculate realized PnL for closed portion
            if current_qty > 0 and current_avg > 0:
                realized = (avg_price - current_avg) * min(qty, current_qty)
                pos["realized_pnl"] += realized
                self.realized_pnl += realized
                logger.info(
                    "Realized PnL for %s: %.2f (total=%.2f)",
                    symbol, realized, self.realized_pnl
                )
            
            # Update cash
            self.cash += qty * avg_price
            
            pos["qty"] = new_qty
            if new_qty == 0:
                pos["avg_price"] = 0.0
        
        # Update timestamp
        pos["last_updated"] = datetime.now(timezone.utc).isoformat()
        
        # Remove position if qty is zero
        if pos["qty"] == 0:
            logger.debug("Position closed for %s", symbol)
        
        # Save checkpoint
        self._save_checkpoint()
        
        # Publish portfolio.updated event
        if self.bus:
            try:
                snapshot = self.get_snapshot()
                self.bus.publish("portfolio.updated", snapshot)
            except Exception as exc:
                logger.debug("Error publishing portfolio.updated: %s", exc)
    
    def get_snapshot(self) -> Dict[str, Any]:
        """
        Get current portfolio snapshot.
        
        Returns:
            Dict with:
                - positions: List of open positions
                - cash: Available cash
                - equity: Total portfolio value
                - realized_pnl: Total realized PnL
                - unrealized_pnl: Total unrealized PnL
                - exposure: Total market exposure
                - position_count: Number of open positions
        """
        open_positions = [
            pos for pos in self.positions.values() if pos["qty"] != 0
        ]
        
        # Calculate unrealized PnL (would need current prices)
        # For now, just use position values at avg_price
        total_exposure = sum(
            abs(pos["qty"]) * pos["avg_price"]
            for pos in open_positions
        )
        
        # Estimate equity (cash + position values)
        # Note: This is approximate without current market prices
        position_value = sum(
            pos["qty"] * pos["avg_price"]
            for pos in open_positions
        )
        equity = self.cash + position_value
        
        return {
            "positions": open_positions,
            "cash": self.cash,
            "equity": equity,
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": 0.0,  # Would need current prices
            "exposure": total_exposure,
            "position_count": len(open_positions),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    
    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get position for a specific symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Position dict or None if no position
        """
        return self.positions.get(symbol)
    
    def _save_checkpoint(self) -> None:
        """Save portfolio state to checkpoint file."""
        try:
            checkpoint_path = self.checkpoint_dir / "portfolio_state.json"
            state = {
                "initial_capital": self.initial_capital,
                "cash": self.cash,
                "realized_pnl": self.realized_pnl,
                "positions": self.positions,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            checkpoint_path.write_text(json.dumps(state, indent=2))
            logger.debug("Portfolio checkpoint saved to %s", checkpoint_path)
        except Exception as exc:
            logger.warning("Failed to save checkpoint: %s", exc)
    
    def _load_checkpoint(self) -> None:
        """Load portfolio state from checkpoint file."""
        try:
            checkpoint_path = self.checkpoint_dir / "portfolio_state.json"
            if not checkpoint_path.exists():
                logger.debug("No checkpoint file found, starting fresh")
                return
            
            state = json.loads(checkpoint_path.read_text())
            self.cash = state.get("cash", self.initial_capital)
            self.realized_pnl = state.get("realized_pnl", 0.0)
            self.positions = state.get("positions", {})
            
            logger.info(
                "Portfolio checkpoint loaded: cash=%.2f, realized_pnl=%.2f, positions=%d",
                self.cash,
                self.realized_pnl,
                len(self.positions)
            )
        except Exception as exc:
            logger.warning("Failed to load checkpoint: %s", exc)
    
    def reset(self) -> None:
        """Reset portfolio to initial state."""
        self.positions.clear()
        self.realized_pnl = 0.0
        self.cash = self.initial_capital
        self._save_checkpoint()
        logger.info("Portfolio reset to initial state")
