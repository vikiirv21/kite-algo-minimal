"""
Backtest registry: utilities for discovering and loading backtest run data.

This module provides functions to:
- List all available backtest runs from the artifacts directory
- Load summary data for specific runs
- Reconstruct equity curves from fills.csv or orders.csv
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def list_backtest_runs(base_dir: str = "artifacts/backtests") -> List[Dict[str, Any]]:
    """
    Discover all backtest runs in the artifacts/backtests directory.
    
    Returns a list of run metadata dictionaries with:
    - run_id: unique identifier (e.g., "2025-11-14_1545")
    - strategy: strategy code (e.g., "ema20_50_intraday")
    - symbol: primary symbol (extracted from config if available)
    - timeframe: timeframe used (extracted from config if available)
    - date_from: start date
    - date_to: end date
    - net_pnl: total P&L
    - win_rate: win rate percentage
    - total_trades: number of trades
    - created_at: timestamp when the run was created
    """
    runs: List[Dict[str, Any]] = []
    base_path = Path(base_dir)
    
    if not base_path.exists():
        logger.warning("Backtests directory not found: %s", base_path)
        return runs
    
    # Iterate through strategy directories
    for strategy_dir in sorted(base_path.iterdir()):
        if not strategy_dir.is_dir():
            continue
        
        strategy_code = strategy_dir.name
        
        # Iterate through run directories
        for run_dir in sorted(strategy_dir.iterdir(), reverse=True):
            if not run_dir.is_dir():
                continue
            
            run_id = run_dir.name
            
            # Check for result.json (or summary.json as fallback)
            result_path = run_dir / "result.json"
            summary_path = run_dir / "summary.json"
            
            if result_path.exists():
                data_path = result_path
            elif summary_path.exists():
                data_path = summary_path
            else:
                logger.debug("No result/summary file found for %s/%s", strategy_code, run_id)
                continue
            
            try:
                with data_path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                
                # Extract summary information
                summary = data.get("summary", {})
                config = data.get("config", {})
                
                # Get symbols (may be a list)
                symbols = config.get("symbols", [])
                symbol = symbols[0] if isinstance(symbols, list) and symbols else "N/A"
                
                # Extract dates
                date_from = config.get("from", "N/A")
                date_to = config.get("to", "N/A")
                
                # Extract metrics
                net_pnl = summary.get("total_pnl", 0.0)
                win_rate = summary.get("win_rate", 0.0)
                total_trades = summary.get("total_trades", 0)
                
                # Get creation timestamp from directory mtime or from data
                try:
                    created_at = run_dir.stat().st_mtime
                except Exception:
                    created_at = None
                
                runs.append({
                    "run_id": run_id,
                    "strategy": strategy_code,
                    "symbol": symbol,
                    "timeframe": config.get("timeframe", "N/A"),
                    "date_from": date_from,
                    "date_to": date_to,
                    "net_pnl": float(net_pnl),
                    "win_rate": float(win_rate),
                    "total_trades": int(total_trades),
                    "created_at": created_at,
                })
                
            except Exception as exc:
                logger.warning(
                    "Failed to load backtest data for %s/%s: %s",
                    strategy_code,
                    run_id,
                    exc,
                )
                continue
    
    return runs


def load_backtest_summary(
    run_id: str,
    base_dir: str = "artifacts/backtests",
) -> Optional[Dict[str, Any]]:
    """
    Load the full summary data for a specific backtest run.
    
    Args:
        run_id: Full path to run, e.g., "ema20_50_intraday/2025-11-14_1545"
        base_dir: Base directory for backtests
    
    Returns:
        Dictionary containing the full result.json contents, or None if not found.
    """
    base_path = Path(base_dir)
    
    # Parse run_id which should be "strategy/run_id"
    parts = run_id.split("/")
    if len(parts) != 2:
        logger.error("Invalid run_id format: %s (expected strategy/run_id)", run_id)
        return None
    
    strategy_code, run_timestamp = parts
    run_dir = base_path / strategy_code / run_timestamp
    
    if not run_dir.exists():
        logger.warning("Run directory not found: %s", run_dir)
        return None
    
    # Try result.json first, then summary.json
    result_path = run_dir / "result.json"
    summary_path = run_dir / "summary.json"
    
    if result_path.exists():
        data_path = result_path
    elif summary_path.exists():
        data_path = summary_path
    else:
        logger.warning("No result/summary file found in %s", run_dir)
        return None
    
    try:
        with data_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.exception("Failed to load summary from %s: %s", data_path, exc)
        return None


def load_backtest_equity_curve(
    run_id: str,
    base_dir: str = "artifacts/backtests",
) -> List[Dict[str, Any]]:
    """
    Reconstruct the equity curve from fills.csv or orders.csv.
    
    Args:
        run_id: Full path to run, e.g., "ema20_50_intraday/2025-11-14_1545"
        base_dir: Base directory for backtests
    
    Returns:
        List of equity curve points with format:
        [{"ts": "2025-11-14T10:30:00", "equity": 1000050.0, "pnl": 50.0}, ...]
    """
    base_path = Path(base_dir)
    
    # Parse run_id
    parts = run_id.split("/")
    if len(parts) != 2:
        logger.error("Invalid run_id format: %s", run_id)
        return []
    
    strategy_code, run_timestamp = parts
    run_dir = base_path / strategy_code / run_timestamp
    
    if not run_dir.exists():
        logger.warning("Run directory not found: %s", run_dir)
        return []
    
    # Try to load starting capital from result.json
    starting_capital = 1_000_000.0
    result_path = run_dir / "result.json"
    summary_path = run_dir / "summary.json"
    
    if result_path.exists():
        try:
            with result_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
                starting_capital = float(data.get("config", {}).get("capital", starting_capital))
        except Exception:
            pass
    elif summary_path.exists():
        try:
            with summary_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
                starting_capital = float(data.get("config", {}).get("capital", starting_capital))
        except Exception:
            pass
    
    # Try fills.csv first (more accurate for equity curve)
    fills_path = run_dir / "fills.csv"
    orders_path = run_dir / "orders.csv"
    
    curve: List[Dict[str, Any]] = []
    cumulative_pnl = 0.0
    
    # Add initial point
    curve.append({
        "ts": None,
        "equity": starting_capital,
        "pnl": 0.0,
    })
    
    if fills_path.exists():
        try:
            with fills_path.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    ts = row.get("ts", "")
                    realized_pnl = float(row.get("realized_pnl", 0.0))
                    
                    cumulative_pnl += realized_pnl
                    equity = starting_capital + cumulative_pnl
                    
                    curve.append({
                        "ts": ts,
                        "equity": equity,
                        "pnl": cumulative_pnl,
                    })
        except Exception as exc:
            logger.warning("Failed to parse fills.csv from %s: %s", fills_path, exc)
    
    elif orders_path.exists():
        # Fallback to orders.csv if fills.csv doesn't exist
        try:
            with orders_path.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Only include filled/closed orders
                    status = row.get("status", "").upper()
                    if status not in ("FILLED", "CLOSED", "COMPLETE"):
                        continue
                    
                    ts = row.get("ts", "")
                    # Try to get realized PnL if available
                    realized_pnl = float(row.get("realized_pnl", row.get("pnl", 0.0)))
                    
                    cumulative_pnl += realized_pnl
                    equity = starting_capital + cumulative_pnl
                    
                    curve.append({
                        "ts": ts,
                        "equity": equity,
                        "pnl": cumulative_pnl,
                    })
        except Exception as exc:
            logger.warning("Failed to parse orders.csv from %s: %s", orders_path, exc)
    else:
        logger.warning("Neither fills.csv nor orders.csv found in %s", run_dir)
    
    # If we only have the initial point, return empty list
    if len(curve) <= 1:
        return []
    
    return curve
