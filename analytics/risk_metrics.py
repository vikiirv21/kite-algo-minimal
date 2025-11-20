"""
Risk Metrics Module

Provides unified risk limits loading, breach detection, and VaR calculation
for the Advanced Risk Metrics dashboard section.

Key functions:
- load_risk_limits: Build normalized risk limits from config + overrides
- compute_risk_breaches: Evaluate current risk state and return violations
- compute_var: Calculate simple empirical VaR from historical trades
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def load_risk_limits(config: dict, overrides: dict | None = None) -> dict:
    """
    Build a normalized risk-limits dict from config + optional overrides.
    
    Pulls from:
    - config["trading"]
    - config.get("risk", {})
    - config.get("risk_engine", {})
    - config.get("execution", {}).get("circuit_breakers", {})
    - config.get("portfolio", {})
    
    Args:
        config: Base configuration dict
        overrides: Optional overrides dict to apply
        
    Returns:
        Dict with normalized risk limits structure
    """
    trading = config.get("trading", {})
    risk = config.get("risk", {})
    risk_engine = config.get("risk_engine", {})
    execution = config.get("execution", {})
    circuit_breakers = execution.get("circuit_breakers", {})
    portfolio = config.get("portfolio", {})
    
    # Determine mode
    mode = str(trading.get("mode", "paper")).lower()
    
    # Get capital
    capital = float(trading.get("paper_capital", 500000))
    
    # Build limits dict from various config sections
    limits = {
        # From execution.circuit_breakers
        "max_daily_loss_rupees": float(circuit_breakers.get("max_daily_loss_rupees", 
                                                             trading.get("max_daily_loss", 5000.0))),
        "max_daily_drawdown_pct": float(circuit_breakers.get("max_daily_drawdown_pct", 0.02)),
        "max_trades_per_day": int(circuit_breakers.get("max_trades_per_day", 100)),
        "max_trades_per_strategy_per_day": int(circuit_breakers.get("max_trades_per_strategy_per_day", 50)),
        "max_loss_streak": int(circuit_breakers.get("max_loss_streak", 5)),
        
        # From trading
        "per_symbol_max_loss": float(trading.get("per_symbol_max_loss", 1500.0)),
        "max_open_positions": trading.get("max_open_positions"),  # Can be None for unlimited
        
        # From portfolio
        "max_exposure_pct": float(portfolio.get("max_exposure_pct", 0.8)),
        "max_leverage": float(portfolio.get("max_leverage", 2.0)),
        "max_risk_per_trade_pct": float(portfolio.get("max_risk_per_trade_pct", 0.01)),
    }
    
    # Compute max_daily_loss_pct from max_daily_loss_rupees if capital > 0
    if capital > 0:
        limits["max_daily_loss_pct"] = limits["max_daily_loss_rupees"] / capital
    
    # Apply overrides if provided
    if overrides:
        # Merge overrides for risk-related keys
        override_execution = overrides.get("execution", {})
        override_circuit_breakers = override_execution.get("circuit_breakers", {})
        override_portfolio = overrides.get("portfolio", {})
        override_trading = overrides.get("trading", {})
        
        if "max_daily_loss_rupees" in override_circuit_breakers:
            limits["max_daily_loss_rupees"] = float(override_circuit_breakers["max_daily_loss_rupees"])
        if "max_daily_drawdown_pct" in override_circuit_breakers:
            limits["max_daily_drawdown_pct"] = float(override_circuit_breakers["max_daily_drawdown_pct"])
        if "max_trades_per_day" in override_circuit_breakers:
            limits["max_trades_per_day"] = int(override_circuit_breakers["max_trades_per_day"])
        if "max_trades_per_strategy_per_day" in override_circuit_breakers:
            limits["max_trades_per_strategy_per_day"] = int(override_circuit_breakers["max_trades_per_strategy_per_day"])
        if "max_loss_streak" in override_circuit_breakers:
            limits["max_loss_streak"] = int(override_circuit_breakers["max_loss_streak"])
        
        if "max_exposure_pct" in override_portfolio:
            limits["max_exposure_pct"] = float(override_portfolio["max_exposure_pct"])
        if "max_leverage" in override_portfolio:
            limits["max_leverage"] = float(override_portfolio["max_leverage"])
        if "max_risk_per_trade_pct" in override_portfolio:
            limits["max_risk_per_trade_pct"] = float(override_portfolio["max_risk_per_trade_pct"])
        
        if "per_symbol_max_loss" in override_trading:
            limits["per_symbol_max_loss"] = float(override_trading["per_symbol_max_loss"])
        if "max_open_positions" in override_trading:
            limits["max_open_positions"] = override_trading["max_open_positions"]
        
        # Recalculate max_daily_loss_pct if capital or limit changed
        if capital > 0:
            limits["max_daily_loss_pct"] = limits["max_daily_loss_rupees"] / capital
    
    result = {
        "mode": mode,
        "capital": capital,
        "limits": limits,
        "source": {
            "config_file": "configs/dev.yaml",
            "overrides_file": "configs/learned_overrides.yaml" if overrides else None,
        }
    }
    
    return result


def compute_risk_breaches(
    config: dict,
    runtime_metrics_path: Path,
    checkpoint_path: Path,
    orders_path: Path | None = None,
    mode: str = "paper",
) -> dict:
    """
    Return current risk breaches by evaluating runtime state against limits.
    
    Returns:
        Dict with structure:
        {
          "mode": "paper",
          "asof": "...",
          "breaches": [
            {
              "id": "daily_loss_exceeded",
              "severity": "critical",
              "message": "...",
              "metric": "realized_pnl",
              "value": -7500.0,
              "limit": -5000.0
            },
            ...
          ]
        }
    """
    breaches = []
    asof = datetime.now().isoformat()
    
    # Load risk limits
    limits_data = load_risk_limits(config)
    limits = limits_data["limits"]
    capital = limits_data["capital"]
    
    # Try to load runtime metrics first
    runtime_metrics = None
    if runtime_metrics_path.exists():
        try:
            with runtime_metrics_path.open("r", encoding="utf-8") as f:
                runtime_metrics = json.load(f)
            logger.debug("Loaded runtime metrics from %s", runtime_metrics_path)
        except Exception as exc:
            logger.warning("Failed to load runtime metrics: %s", exc)
    
    # Fall back to checkpoint if runtime metrics unavailable
    checkpoint = None
    if checkpoint_path.exists():
        try:
            with checkpoint_path.open("r", encoding="utf-8") as f:
                checkpoint = json.load(f)
            logger.debug("Loaded checkpoint from %s", checkpoint_path)
        except Exception as exc:
            logger.warning("Failed to load checkpoint: %s", exc)
    
    # Extract metrics for breach detection
    if runtime_metrics:
        # From performance_v2 runtime_metrics.json
        equity_data = runtime_metrics.get("equity", {})
        overall_data = runtime_metrics.get("overall", {})
        
        current_equity = float(equity_data.get("current_equity", capital))
        starting_capital = float(equity_data.get("starting_capital", capital))
        realized_pnl = float(equity_data.get("realized_pnl", 0.0))
        unrealized_pnl = float(equity_data.get("unrealized_pnl", 0.0))
        max_equity = float(equity_data.get("max_equity", starting_capital))
        total_trades = int(overall_data.get("total_trades", 0))
        
        # Calculate daily PnL (approximation: use net_pnl as daily for now)
        daily_realized_pnl = realized_pnl
        
    elif checkpoint:
        # Fall back to checkpoint data
        pnl_data = checkpoint.get("pnl", {})
        equity_data = checkpoint.get("equity", {})
        
        daily_realized_pnl = float(pnl_data.get("realized_pnl", 0.0))
        unrealized_pnl = float(equity_data.get("unrealized_pnl", 0.0))
        current_equity = capital + daily_realized_pnl + unrealized_pnl
        starting_capital = capital
        max_equity = current_equity
        total_trades = int(pnl_data.get("num_trades", 0))
    else:
        # No data available, return empty breaches
        logger.info("No runtime metrics or checkpoint available for breach detection")
        return {"mode": mode, "asof": asof, "breaches": []}
    
    # Check breach conditions
    
    # 1. Max daily loss (rupees)
    max_daily_loss_rupees = limits["max_daily_loss_rupees"]
    if daily_realized_pnl < -max_daily_loss_rupees:
        breaches.append({
            "id": "daily_loss_exceeded",
            "severity": "critical",
            "message": f"Daily realized PnL {daily_realized_pnl:.2f} below limit -{max_daily_loss_rupees:.2f}",
            "metric": "realized_pnl",
            "value": daily_realized_pnl,
            "limit": -max_daily_loss_rupees,
        })
    
    # 2. Max daily drawdown (%)
    max_daily_drawdown_pct = limits["max_daily_drawdown_pct"]
    if max_equity > 0:
        equity_drawdown_pct = (max_equity - current_equity) / max_equity
        if equity_drawdown_pct > max_daily_drawdown_pct:
            breaches.append({
                "id": "daily_drawdown_exceeded",
                "severity": "critical",
                "message": f"Equity drawdown {equity_drawdown_pct:.2%} exceeds limit {max_daily_drawdown_pct:.2%}",
                "metric": "equity_drawdown_pct",
                "value": equity_drawdown_pct,
                "limit": max_daily_drawdown_pct,
            })
    
    # 3. Max exposure (%)
    max_exposure_pct = limits["max_exposure_pct"]
    if checkpoint:
        positions = checkpoint.get("positions", [])
        # Calculate total notional from positions (approximate)
        total_notional = 0.0
        for pos in positions:
            qty = abs(float(pos.get("quantity", 0)))
            avg_price = float(pos.get("avg_price", 0))
            total_notional += qty * avg_price
        
        if current_equity > 0:
            exposure_pct = total_notional / current_equity
            if exposure_pct > max_exposure_pct:
                breaches.append({
                    "id": "max_exposure_exceeded",
                    "severity": "warning",
                    "message": f"Exposure {exposure_pct:.2%} > max_exposure_pct {max_exposure_pct:.2%}",
                    "metric": "exposure_pct",
                    "value": exposure_pct,
                    "limit": max_exposure_pct,
                })
    
    # 4. Max open positions
    max_open_positions = limits["max_open_positions"]
    if max_open_positions is not None:
        if checkpoint:
            positions = checkpoint.get("positions", [])
            open_positions = sum(1 for p in positions if abs(float(p.get("quantity", 0))) > 0)
            if open_positions > max_open_positions:
                breaches.append({
                    "id": "max_open_positions_exceeded",
                    "severity": "warning",
                    "message": f"Open positions {open_positions} > max {max_open_positions}",
                    "metric": "open_positions",
                    "value": open_positions,
                    "limit": max_open_positions,
                })
    
    # 5. Max trades per day
    max_trades_per_day = limits["max_trades_per_day"]
    if total_trades > max_trades_per_day:
        breaches.append({
            "id": "max_trades_per_day_exceeded",
            "severity": "warning",
            "message": f"Total trades {total_trades} > max {max_trades_per_day}",
            "metric": "total_trades",
            "value": total_trades,
            "limit": max_trades_per_day,
        })
    
    return {
        "mode": mode,
        "asof": asof,
        "breaches": breaches,
    }


def compute_var(
    orders_path: Path,
    capital: float,
    confidence: float = 0.95,
    mode: str = "paper",
) -> dict:
    """
    Compute a simple empirical 1-day VaR from historical trade PnLs.
    
    Returns:
        Dict with structure:
        {
          "mode": "paper",
          "confidence": 0.95,
          "var_rupees": 2500.0,
          "var_pct": 0.005,
          "sample_trades": 120,
          "status": "ok"  # or "insufficient_data"
        }
    """
    if not orders_path.exists():
        logger.info("Orders file not found: %s", orders_path)
        return {
            "mode": mode,
            "confidence": confidence,
            "var_rupees": 0.0,
            "var_pct": 0.0,
            "sample_trades": 0,
            "status": "insufficient_data",
        }
    
    # Try to reconstruct trade PnLs from orders.csv
    try:
        import csv
        
        orders = []
        with orders_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("status", "").upper() == "FILLED":
                    orders.append(row)
        
        if len(orders) < 10:
            logger.info("Insufficient orders for VaR calculation: %d", len(orders))
            return {
                "mode": mode,
                "confidence": confidence,
                "var_rupees": 0.0,
                "var_pct": 0.0,
                "sample_trades": len(orders),
                "status": "insufficient_data",
            }
        
        # Simple approach: group by symbol+strategy and compute per-trade PnL
        # For a more accurate implementation, we'd need to reconstruct full trades
        # For now, use a proxy: look at price differences for same symbol
        
        # Group orders by symbol
        symbol_orders = {}
        for order in orders:
            symbol = order.get("symbol", "")
            if symbol not in symbol_orders:
                symbol_orders[symbol] = []
            symbol_orders[symbol].append(order)
        
        # Compute simple PnL approximations
        trade_pnls = []
        for symbol, sym_orders in symbol_orders.items():
            # Sort by timestamp
            sym_orders.sort(key=lambda x: x.get("timestamp", ""))
            
            # Simple heuristic: pairs of opposite sides
            position = 0.0
            entry_price = 0.0
            
            for order in sym_orders:
                side = order.get("side", "").upper()
                qty = float(order.get("quantity", 0))
                price = float(order.get("price", 0))
                
                if side == "BUY":
                    if position < 0:
                        # Closing short
                        pnl = abs(position) * (entry_price - price)
                        trade_pnls.append(pnl)
                        position = 0.0
                    else:
                        # Opening/adding to long
                        if position == 0:
                            entry_price = price
                        position += qty
                elif side == "SELL":
                    if position > 0:
                        # Closing long
                        pnl = position * (price - entry_price)
                        trade_pnls.append(pnl)
                        position = 0.0
                    else:
                        # Opening/adding to short
                        if position == 0:
                            entry_price = price
                        position -= qty
        
        if len(trade_pnls) < 10:
            logger.info("Insufficient closed trades for VaR: %d", len(trade_pnls))
            return {
                "mode": mode,
                "confidence": confidence,
                "var_rupees": 0.0,
                "var_pct": 0.0,
                "sample_trades": len(trade_pnls),
                "status": "insufficient_data",
            }
        
        # Calculate VaR as the percentile of losses
        trade_pnls.sort()
        percentile_index = int((1 - confidence) * len(trade_pnls))
        var_rupees = abs(trade_pnls[percentile_index])
        var_pct = var_rupees / capital if capital > 0 else 0.0
        
        return {
            "mode": mode,
            "confidence": confidence,
            "var_rupees": var_rupees,
            "var_pct": var_pct,
            "sample_trades": len(trade_pnls),
            "status": "ok",
        }
        
    except Exception as exc:
        logger.error("Failed to compute VaR: %s", exc)
        return {
            "mode": mode,
            "confidence": confidence,
            "var_rupees": 0.0,
            "var_pct": 0.0,
            "sample_trades": 0,
            "status": "error",
        }
