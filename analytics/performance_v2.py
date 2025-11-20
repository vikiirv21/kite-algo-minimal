"""
Analytics + Performance Engine V2

Computes proper trade statistics (PnL, win rate, profit factor, per-strategy
and per-symbol metrics) from orders.csv and exposes them via JSON files.

Key features:
- Load orders from artifacts/orders.csv
- Reconstruct trades from orders using FIFO position model
- Compute comprehensive metrics including equity, overall, per-strategy, and per-symbol stats
- Write metrics to JSON files for dashboard consumption
"""

from __future__ import annotations

import csv
import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Trade:
    """Represents a completed trade with entry and exit."""
    symbol: str
    strategy: str
    side: str  # "BUY" or "SELL"
    qty: float
    entry_price: float
    exit_price: float
    pnl: float
    open_ts: str
    close_ts: str
    mode: str
    profile: str


def load_orders(orders_path: Path) -> list[dict]:
    """
    Load orders from orders.csv.
    
    Args:
        orders_path: Path to orders.csv file
        
    Returns:
        List of order dictionaries
    """
    if not orders_path.exists():
        logger.warning("Orders file not found: %s", orders_path)
        return []
    
    orders = []
    try:
        with orders_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Only include filled orders
                status = (row.get("status") or "").upper()
                if status == "FILLED":
                    orders.append(row)
        logger.info("Loaded %d filled orders from %s", len(orders), orders_path)
    except Exception as exc:
        logger.error("Failed to load orders from %s: %s", orders_path, exc)
        return []
    
    return orders


def reconstruct_trades(orders: list[dict]) -> list[Trade]:
    """
    Reconstruct trades from orders using a simple FIFO position model.
    
    For each symbol+strategy combination:
    - Track open positions
    - When opposite side order comes in, close positions FIFO
    - Generate Trade objects for completed trades
    
    Args:
        orders: List of order dictionaries
        
    Returns:
        List of Trade objects representing completed trades
    """
    trades = []
    # Track positions by (symbol, strategy) key
    positions: dict[tuple[str, str], list[dict]] = {}
    
    for order in orders:
        symbol = order.get("symbol", "")
        strategy = order.get("strategy", "")
        side = (order.get("side") or "").upper()
        
        if not symbol or not strategy or side not in ("BUY", "SELL"):
            continue
        
        try:
            qty = float(order.get("quantity", 0))
            price = float(order.get("price", 0))
        except (ValueError, TypeError):
            logger.warning("Invalid quantity or price in order: %s", order)
            continue
        
        if qty <= 0 or price <= 0:
            continue
        
        key = (symbol, strategy)
        timestamp = order.get("timestamp", "")
        mode = order.get("mode", "")
        profile = order.get("profile", "")
        
        # Initialize position list if needed
        if key not in positions:
            positions[key] = []
        
        position_list = positions[key]
        
        # Check if we have opposite positions to close
        remaining_qty = qty
        
        while remaining_qty > 0 and position_list:
            # Check if first position is opposite side
            first_pos = position_list[0]
            if first_pos["side"] == side:
                # Same side, don't close
                break
            
            # Close position FIFO
            pos_qty = first_pos["qty"]
            close_qty = min(remaining_qty, pos_qty)
            
            # Determine entry and exit based on original position side
            if first_pos["side"] == "BUY":
                # Long position closed by SELL
                entry_price = first_pos["price"]
                exit_price = price
                pnl = (exit_price - entry_price) * close_qty
            else:
                # Short position closed by BUY
                entry_price = first_pos["price"]
                exit_price = price
                pnl = (entry_price - exit_price) * close_qty
            
            # Create trade
            trade = Trade(
                symbol=symbol,
                strategy=strategy,
                side=first_pos["side"],
                qty=close_qty,
                entry_price=first_pos["price"],
                exit_price=price,
                pnl=pnl,
                open_ts=first_pos["timestamp"],
                close_ts=timestamp,
                mode=mode or first_pos.get("mode", ""),
                profile=profile or first_pos.get("profile", ""),
            )
            trades.append(trade)
            
            # Update position
            first_pos["qty"] -= close_qty
            if first_pos["qty"] <= 0:
                position_list.pop(0)
            
            remaining_qty -= close_qty
        
        # If there's remaining quantity, add as new position
        if remaining_qty > 0:
            position_list.append({
                "side": side,
                "qty": remaining_qty,
                "price": price,
                "timestamp": timestamp,
                "mode": mode,
                "profile": profile,
            })
    
    logger.info("Reconstructed %d trades from orders", len(trades))
    return trades


def compute_metrics(
    trades: list[Trade],
    starting_capital: float,
    state_path: Path | None = None,
) -> dict[str, Any]:
    """
    Compute comprehensive metrics from trades.
    
    Args:
        trades: List of Trade objects
        starting_capital: Starting capital for equity calculation
        state_path: Optional path to state file for unrealized PnL
        
    Returns:
        Dictionary with metrics structure:
        {
            "asof": "...",
            "mode": "...",
            "equity": {...},
            "overall": {...},
            "per_strategy": {...},
            "per_symbol": {...}
        }
    """
    now = datetime.now().isoformat()
    
    # Compute overall metrics
    total_trades = len(trades)
    win_trades = sum(1 for t in trades if t.pnl > 0)
    loss_trades = sum(1 for t in trades if t.pnl < 0)
    breakeven_trades = total_trades - win_trades - loss_trades
    
    win_rate = (win_trades / total_trades * 100) if total_trades > 0 else 0.0
    
    gross_profit = sum(t.pnl for t in trades if t.pnl > 0)
    gross_loss = abs(sum(t.pnl for t in trades if t.pnl < 0))
    net_pnl = sum(t.pnl for t in trades)
    
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 0.0
    
    avg_win = (gross_profit / win_trades) if win_trades > 0 else 0.0
    avg_loss = (gross_loss / loss_trades) if loss_trades > 0 else 0.0
    
    # R-multiple (simplified: using avg_loss as baseline risk)
    avg_r_multiple = 0.0
    if avg_loss > 0 and total_trades > 0:
        total_r = sum(t.pnl / avg_loss for t in trades)
        avg_r_multiple = total_r / total_trades
    
    biggest_win = max((t.pnl for t in trades), default=0.0)
    biggest_loss = min((t.pnl for t in trades), default=0.0)
    
    # Compute equity metrics
    realized_pnl = net_pnl
    unrealized_pnl = 0.0
    total_notional = 0.0
    
    # Try to load unrealized PnL and total_notional from state if available
    if state_path and state_path.exists():
        try:
            with state_path.open("r", encoding="utf-8") as f:
                state = json.load(f)
                equity_data = state.get("equity", {})
                unrealized_pnl = float(equity_data.get("unrealized_pnl", 0.0))
                total_notional = float(equity_data.get("total_notional", 0.0))
        except Exception as exc:
            logger.debug("Could not load unrealized PnL/notional from state: %s", exc)
    
    current_equity = starting_capital + realized_pnl + unrealized_pnl
    
    # Compute drawdown from equity curve
    equity_curve = [starting_capital]
    running_pnl = 0.0
    for trade in trades:
        running_pnl += trade.pnl
        equity_curve.append(starting_capital + running_pnl)
    
    max_equity = max(equity_curve)
    min_equity = min(equity_curve)
    
    # Calculate max drawdown
    max_drawdown = 0.0
    peak = equity_curve[0]
    for equity in equity_curve:
        if equity > peak:
            peak = equity
        drawdown = peak - equity
        if drawdown > max_drawdown:
            max_drawdown = drawdown
    
    # Per-strategy metrics
    strategy_stats: dict[str, dict[str, Any]] = {}
    for trade in trades:
        if trade.strategy not in strategy_stats:
            strategy_stats[trade.strategy] = {
                "trades": 0,
                "win_trades": 0,
                "loss_trades": 0,
                "gross_profit": 0.0,
                "gross_loss": 0.0,
                "net_pnl": 0.0,
            }
        
        stats = strategy_stats[trade.strategy]
        stats["trades"] += 1
        stats["net_pnl"] += trade.pnl
        
        if trade.pnl > 0:
            stats["win_trades"] += 1
            stats["gross_profit"] += trade.pnl
        elif trade.pnl < 0:
            stats["loss_trades"] += 1
            stats["gross_loss"] += abs(trade.pnl)
    
    # Add computed fields to strategy stats
    for strategy, stats in strategy_stats.items():
        trades_count = stats["trades"]
        stats["win_rate"] = (stats["win_trades"] / trades_count * 100) if trades_count > 0 else 0.0
        stats["profit_factor"] = (
            (stats["gross_profit"] / stats["gross_loss"])
            if stats["gross_loss"] > 0
            else 0.0
        )
        stats["avg_win"] = (
            (stats["gross_profit"] / stats["win_trades"])
            if stats["win_trades"] > 0
            else 0.0
        )
        stats["avg_loss"] = (
            (stats["gross_loss"] / stats["loss_trades"])
            if stats["loss_trades"] > 0
            else 0.0
        )
    
    # Per-symbol metrics
    symbol_stats: dict[str, dict[str, Any]] = {}
    for trade in trades:
        if trade.symbol not in symbol_stats:
            symbol_stats[trade.symbol] = {
                "trades": 0,
                "win_trades": 0,
                "loss_trades": 0,
                "gross_profit": 0.0,
                "gross_loss": 0.0,
                "net_pnl": 0.0,
            }
        
        stats = symbol_stats[trade.symbol]
        stats["trades"] += 1
        stats["net_pnl"] += trade.pnl
        
        if trade.pnl > 0:
            stats["win_trades"] += 1
            stats["gross_profit"] += trade.pnl
        elif trade.pnl < 0:
            stats["loss_trades"] += 1
            stats["gross_loss"] += abs(trade.pnl)
    
    # Add computed fields to symbol stats
    for symbol, stats in symbol_stats.items():
        trades_count = stats["trades"]
        stats["win_rate"] = (stats["win_trades"] / trades_count * 100) if trades_count > 0 else 0.0
        stats["profit_factor"] = (
            (stats["gross_profit"] / stats["gross_loss"])
            if stats["gross_loss"] > 0
            else 0.0
        )
    
    # Determine mode from first trade if available
    mode = trades[0].mode if trades else "paper"
    
    return {
        "asof": now,
        "mode": mode,
        "equity": {
            "starting_capital": starting_capital,
            "current_equity": current_equity,
            "realized_pnl": realized_pnl,
            "unrealized_pnl": unrealized_pnl,
            "total_notional": total_notional,
            "max_drawdown": max_drawdown,
            "max_equity": max_equity,
            "min_equity": min_equity,
        },
        "overall": {
            "total_trades": total_trades,
            "win_trades": win_trades,
            "loss_trades": loss_trades,
            "breakeven_trades": breakeven_trades,
            "win_rate": win_rate,
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "net_pnl": net_pnl,
            "profit_factor": profit_factor,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "avg_r_multiple": avg_r_multiple,
            "biggest_win": biggest_win,
            "biggest_loss": biggest_loss,
        },
        "per_strategy": strategy_stats,
        "per_symbol": symbol_stats,
    }


def write_metrics(
    orders_path: Path,
    state_path: Path | None,
    output_path: Path,
    starting_capital: float,
) -> None:
    """
    Complete pipeline: load orders, reconstruct trades, compute metrics, write JSON.
    
    Args:
        orders_path: Path to orders.csv
        state_path: Optional path to state file for unrealized PnL
        output_path: Path to write metrics JSON
        starting_capital: Starting capital for equity calculation
    """
    logger.info("Computing performance metrics...")
    logger.info("  Orders: %s", orders_path)
    logger.info("  State: %s", state_path)
    logger.info("  Output: %s", output_path)
    logger.info("  Starting capital: %.2f", starting_capital)
    
    # Load orders
    orders = load_orders(orders_path)
    
    # Reconstruct trades
    trades = reconstruct_trades(orders)
    
    # Compute metrics
    metrics = compute_metrics(trades, starting_capital, state_path)
    
    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write to file
    try:
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2, default=str)
        logger.info("Metrics written to: %s", output_path)
    except Exception as exc:
        logger.error("Failed to write metrics to %s: %s", output_path, exc)
        raise


def update_runtime_metrics(
    orders_path: Path | str,
    state_path: Path | str | None = None,
    starting_capital: float = 500_000.0,
    output_path: Path | str | None = None,
) -> dict[str, Any]:
    """
    Idempotent helper to update runtime_metrics.json.
    
    This is the canonical way to update runtime metrics for both CLI and dashboard.
    Handles missing/empty orders gracefully by returning safe default metrics.
    
    Args:
        orders_path: Path to orders.csv file
        state_path: Optional path to state checkpoint for unrealized PnL/notional
        starting_capital: Starting capital (default: 500000)
        output_path: Output JSON path (default: artifacts/analytics/runtime_metrics.json)
        
    Returns:
        Dictionary containing the computed metrics
        
    Examples:
        >>> # Update runtime metrics from current orders and state
        >>> metrics = update_runtime_metrics(
        ...     orders_path="artifacts/orders.csv",
        ...     state_path="artifacts/checkpoints/paper_state_latest.json",
        ...     starting_capital=500000.0,
        ... )
        >>> print(f"Equity: {metrics['equity']['current_equity']}")
    """
    # Convert to Path objects
    orders_path = Path(orders_path)
    state_path = Path(state_path) if state_path else None
    
    # Default output path if not specified
    if output_path is None:
        # Assume we're in project root or can find it
        base_dir = Path(__file__).resolve().parents[1]
        artifacts_dir = base_dir / "artifacts" / "analytics"
        output_path = artifacts_dir / "runtime_metrics.json"
    else:
        output_path = Path(output_path)
    
    # Load orders (returns empty list if missing)
    orders = load_orders(orders_path)
    
    # Reconstruct trades
    trades = reconstruct_trades(orders)
    
    # Compute metrics
    metrics = compute_metrics(trades, starting_capital, state_path)
    
    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write metrics to file
    try:
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2, default=str)
        logger.info("Runtime metrics updated: %s", output_path)
    except Exception as exc:
        logger.error("Failed to write runtime metrics to %s: %s", output_path, exc)
        raise
    
    return metrics
        logger.error("Failed to write metrics to %s: %s", output_path, exc)
        raise
