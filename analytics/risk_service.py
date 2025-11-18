"""
Risk Service Module for Advanced Risk Metrics Dashboard.

This module provides risk limit management, breach detection, and VaR calculations.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)

# Base directory for the project
BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = BASE_DIR / "configs" / "dev.yaml"
DEFAULT_OVERRIDES_PATH = BASE_DIR / "configs" / "risk_overrides.yaml"
ARTIFACTS_ROOT = BASE_DIR / "artifacts"
ANALYTICS_DIR = ARTIFACTS_ROOT / "analytics"
RUNTIME_METRICS_PATH = ANALYTICS_DIR / "runtime_metrics.json"
DAILY_METRICS_DIR = ANALYTICS_DIR / "daily"


@dataclass
class RiskLimits:
    """Risk limits configuration."""
    max_daily_loss_rupees: float
    max_daily_drawdown_pct: float
    max_trades_per_day: int
    max_trades_per_symbol_per_day: int
    max_loss_streak: int


def load_risk_limits(
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    overrides_path: str | Path = DEFAULT_OVERRIDES_PATH,
) -> tuple[RiskLimits, dict[str, Any]]:
    """
    Load risk limits from base config and overrides.
    
    Args:
        config_path: Path to base configuration file (dev.yaml)
        overrides_path: Path to risk overrides file (risk_overrides.yaml)
    
    Returns:
        Tuple of (RiskLimits instance, metadata dict with updated_at timestamp)
    """
    config_path = Path(config_path)
    overrides_path = Path(overrides_path)
    
    # Load base config
    base_config = {}
    if config_path.exists():
        try:
            with config_path.open("r", encoding="utf-8") as f:
                base_config = yaml.safe_load(f) or {}
        except Exception as exc:
            logger.warning("Failed to load base config from %s: %s", config_path, exc)
    
    # Extract base limits from config
    trading = base_config.get("trading", {})
    execution = base_config.get("execution", {})
    circuit_breakers = execution.get("circuit_breakers", {})
    strategy_engine = base_config.get("strategy_engine", {})
    
    # Default values from config
    limits = {
        "max_daily_loss_rupees": float(
            circuit_breakers.get("max_daily_loss_rupees") or 
            trading.get("max_daily_loss") or 
            5000.0
        ),
        "max_daily_drawdown_pct": float(
            circuit_breakers.get("max_daily_drawdown_pct") or 
            0.02
        ),
        "max_trades_per_day": int(
            circuit_breakers.get("max_trades_per_day") or 
            strategy_engine.get("max_trades_per_day") or 
            100
        ),
        "max_trades_per_symbol_per_day": int(
            circuit_breakers.get("max_trades_per_symbol_per_day") or 
            base_config.get("risk", {}).get("quality", {}).get("max_trades_per_symbol_per_day") or 
            5
        ),
        "max_loss_streak": int(
            circuit_breakers.get("max_loss_streak") or 
            strategy_engine.get("max_loss_streak") or 
            5
        ),
    }
    
    # Load and merge overrides
    updated_at = None
    if overrides_path.exists():
        try:
            with overrides_path.open("r", encoding="utf-8") as f:
                overrides = yaml.safe_load(f) or {}
            
            # Merge overrides
            for key in limits:
                if key in overrides:
                    limits[key] = overrides[key]
            
            # Get last modified time
            stat = overrides_path.stat()
            updated_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
        except Exception as exc:
            logger.warning("Failed to load overrides from %s: %s", overrides_path, exc)
    
    risk_limits = RiskLimits(**limits)
    
    metadata = {
        "updated_at": updated_at,
        "base_config": str(config_path),
        "overrides": str(overrides_path),
    }
    
    return risk_limits, metadata


def save_risk_limits(
    patch: dict[str, Any],
    overrides_path: str | Path = DEFAULT_OVERRIDES_PATH,
) -> RiskLimits:
    """
    Save risk limits by merging patch with existing overrides.
    
    Args:
        patch: Dictionary with updated risk limit values
        overrides_path: Path to risk overrides file
    
    Returns:
        Updated RiskLimits instance
    """
    overrides_path = Path(overrides_path)
    
    # Load existing overrides
    existing = {}
    if overrides_path.exists():
        try:
            with overrides_path.open("r", encoding="utf-8") as f:
                existing = yaml.safe_load(f) or {}
        except Exception as exc:
            logger.warning("Failed to load existing overrides: %s", exc)
    
    # Merge patch into existing
    existing.update(patch)
    
    # Ensure parent directory exists
    overrides_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write back to disk
    try:
        with overrides_path.open("w", encoding="utf-8") as f:
            yaml.dump(existing, f, default_flow_style=False, sort_keys=False)
    except Exception as exc:
        logger.error("Failed to save risk overrides to %s: %s", overrides_path, exc)
        raise
    
    # Reload limits to get merged result
    risk_limits, _ = load_risk_limits(overrides_path=overrides_path)
    
    return risk_limits


def compute_breaches(limits: RiskLimits) -> list[dict[str, Any]]:
    """
    Compute current risk breaches by comparing metrics against limits.
    
    Args:
        limits: RiskLimits instance with configured thresholds
    
    Returns:
        List of breach dictionaries with details about each violation
    """
    breaches = []
    
    # Load runtime metrics
    runtime_metrics = _load_runtime_metrics()
    
    if not runtime_metrics:
        logger.warning("No runtime metrics available for breach detection")
        return breaches
    
    # Extract current metrics
    equity = runtime_metrics.get("equity", {})
    overall = runtime_metrics.get("overall", {})
    per_symbol = runtime_metrics.get("per_symbol", {})
    
    realized_pnl = float(equity.get("realized_pnl", 0.0))
    max_drawdown = float(equity.get("max_drawdown", 0.0))
    total_trades = int(overall.get("total_trades", 0))
    loss_streak = int(overall.get("loss_streak", 0))
    
    # Check daily loss breach
    if realized_pnl < 0 and abs(realized_pnl) >= limits.max_daily_loss_rupees:
        breaches.append({
            "code": "MAX_DAILY_LOSS",
            "severity": "critical",
            "message": f"Daily loss of ₹{abs(realized_pnl):.2f} exceeds limit of ₹{limits.max_daily_loss_rupees:.2f}",
            "metric": {
                "current": abs(realized_pnl),
                "limit": limits.max_daily_loss_rupees,
                "unit": "rupees",
            },
            "symbol": None,
            "since": runtime_metrics.get("asof"),
        })
    
    # Check drawdown breach
    max_drawdown_pct = abs(max_drawdown) * 100.0
    if max_drawdown_pct >= limits.max_daily_drawdown_pct * 100.0:
        breaches.append({
            "code": "MAX_DRAWDOWN",
            "severity": "critical",
            "message": f"Drawdown of {max_drawdown_pct:.2f}% exceeds limit of {limits.max_daily_drawdown_pct * 100.0:.2f}%",
            "metric": {
                "current": max_drawdown_pct,
                "limit": limits.max_daily_drawdown_pct * 100.0,
                "unit": "percent",
            },
            "symbol": None,
            "since": runtime_metrics.get("asof"),
        })
    
    # Check total trades breach
    if total_trades >= limits.max_trades_per_day:
        severity = "critical" if total_trades > limits.max_trades_per_day else "warning"
        breaches.append({
            "code": "MAX_TRADES_PER_DAY",
            "severity": severity,
            "message": f"Total trades ({total_trades}) at or exceeds daily limit of {limits.max_trades_per_day}",
            "metric": {
                "current": total_trades,
                "limit": limits.max_trades_per_day,
                "unit": "trades",
            },
            "symbol": None,
            "since": runtime_metrics.get("asof"),
        })
    
    # Check per-symbol trade limits
    for symbol, symbol_data in per_symbol.items():
        symbol_trades = int(symbol_data.get("total_trades", 0))
        if symbol_trades >= limits.max_trades_per_symbol_per_day:
            severity = "warning" if symbol_trades == limits.max_trades_per_symbol_per_day else "critical"
            breaches.append({
                "code": "MAX_TRADES_PER_SYMBOL",
                "severity": severity,
                "message": f"Symbol {symbol} has {symbol_trades} trades, at or exceeds limit of {limits.max_trades_per_symbol_per_day}",
                "metric": {
                    "current": symbol_trades,
                    "limit": limits.max_trades_per_symbol_per_day,
                    "unit": "trades",
                },
                "symbol": symbol,
                "since": runtime_metrics.get("asof"),
            })
    
    # Check loss streak
    if loss_streak >= limits.max_loss_streak:
        severity = "critical" if loss_streak > limits.max_loss_streak else "warning"
        breaches.append({
            "code": "MAX_LOSS_STREAK",
            "severity": severity,
            "message": f"Loss streak of {loss_streak} at or exceeds limit of {limits.max_loss_streak}",
            "metric": {
                "current": loss_streak,
                "limit": limits.max_loss_streak,
                "unit": "trades",
            },
            "symbol": None,
            "since": runtime_metrics.get("asof"),
        })
    
    return breaches


def compute_var(days: int = 30, confidence: float = 0.95) -> dict[str, Any]:
    """
    Compute Value at Risk (VaR) using historical method.
    
    Args:
        days: Number of days of historical data to use
        confidence: Confidence level (e.g., 0.95 for 95% VaR)
    
    Returns:
        Dictionary with VaR calculation results
    """
    # Load daily PnL values
    daily_pnls = _load_daily_pnls(days)
    
    if not daily_pnls:
        logger.warning("No daily PnL data available for VaR calculation")
        return {
            "days": days,
            "confidence": confidence,
            "method": "historical",
            "var_rupees": 0.0,
            "var_pct": 0.0,
            "sample_size": 0,
        }
    
    # Sort PnL values (ascending order: worst losses first)
    sorted_pnls = sorted(daily_pnls)
    
    # Calculate VaR as percentile
    sample_size = len(sorted_pnls)
    percentile_index = int((1.0 - confidence) * sample_size)
    
    # Ensure we don't go out of bounds
    percentile_index = max(0, min(percentile_index, sample_size - 1))
    
    var_rupees = abs(sorted_pnls[percentile_index]) if sorted_pnls[percentile_index] < 0 else 0.0
    
    # Calculate VaR as percentage of starting capital
    var_pct = 0.0
    runtime_metrics = _load_runtime_metrics()
    if runtime_metrics:
        equity = runtime_metrics.get("equity", {})
        starting_capital = float(equity.get("starting_capital", 0.0))
        if starting_capital > 0:
            var_pct = (var_rupees / starting_capital) * 100.0
    
    return {
        "days": days,
        "confidence": confidence,
        "method": "historical",
        "var_rupees": var_rupees,
        "var_pct": var_pct,
        "sample_size": sample_size,
    }


def _load_runtime_metrics() -> Optional[dict[str, Any]]:
    """Load runtime metrics from artifacts/analytics/runtime_metrics.json."""
    if not RUNTIME_METRICS_PATH.exists():
        return None
    
    try:
        with RUNTIME_METRICS_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning("Failed to load runtime metrics: %s", exc)
        return None


def _load_daily_pnls(days: int) -> list[float]:
    """
    Load daily PnL values from daily metrics files.
    
    Args:
        days: Maximum number of days to load
    
    Returns:
        List of daily PnL values (float)
    """
    pnls = []
    
    # Ensure daily metrics directory exists
    if not DAILY_METRICS_DIR.exists():
        return pnls
    
    # Get all daily metrics files
    metrics_files = sorted(DAILY_METRICS_DIR.glob("*-metrics.json"), reverse=True)
    
    # Limit to requested number of days
    metrics_files = metrics_files[:days]
    
    for metrics_file in metrics_files:
        try:
            with metrics_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Extract realized PnL for the day
            equity = data.get("equity", {})
            realized_pnl = float(equity.get("realized_pnl", 0.0))
            pnls.append(realized_pnl)
        except Exception as exc:
            logger.warning("Failed to load daily metrics from %s: %s", metrics_file, exc)
            continue
    
    return pnls
