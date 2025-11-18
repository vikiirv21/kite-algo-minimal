"""
Risk Service Module

Provides risk limit management, breach detection, and VaR computation.
"""

import json
import logging
import yaml
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Base directory for configuration files
BASE_DIR = Path(__file__).resolve().parents[1]
CONFIGS_DIR = BASE_DIR / "configs"
DEV_CONFIG_PATH = CONFIGS_DIR / "dev.yaml"
RISK_OVERRIDES_PATH = CONFIGS_DIR / "risk_overrides.yaml"

# Base directory for artifacts
ARTIFACTS_DIR = BASE_DIR / "artifacts"
RUNTIME_METRICS_PATH = ARTIFACTS_DIR / "analytics" / "runtime_metrics.json"
DAILY_METRICS_DIR = ARTIFACTS_DIR / "analytics" / "daily"


@dataclass
class RiskLimits:
    """Risk limits configuration."""
    max_daily_loss_rupees: float = 5000.0
    max_daily_drawdown_pct: float = 0.02  # 2% as decimal (not percentage)
    max_trades_per_day: int = 100
    max_trades_per_symbol_per_day: int = 5
    max_loss_streak: int = 5


def load_risk_limits(
    config_path: str = str(DEV_CONFIG_PATH),
    overrides_path: str = str(RISK_OVERRIDES_PATH)
) -> tuple[RiskLimits, Dict[str, Any]]:
    """
    Load risk limits from config files.
    
    Reads from configs/dev.yaml and applies overrides from configs/risk_overrides.yaml.
    
    Args:
        config_path: Path to base config file (default: configs/dev.yaml)
        overrides_path: Path to overrides file (default: configs/risk_overrides.yaml)
    
    Returns:
        Tuple of (RiskLimits dataclass, metadata dict with updated_at timestamp)
    """
    limits = RiskLimits()
    config_path_obj = Path(config_path)
    overrides_path_obj = Path(overrides_path)
    updated_at = None
    
    # Load base config from dev.yaml
    try:
        if config_path_obj.exists():
            with config_path_obj.open("r", encoding="utf-8") as f:
                dev_config = yaml.safe_load(f) or {}
            
            # Extract risk section (check multiple locations)
            risk_section = dev_config.get("risk", {})
            execution = dev_config.get("execution", {})
            circuit_breakers = execution.get("circuit_breakers", {})
            
            # Try circuit_breakers first, then risk section
            if isinstance(circuit_breakers, dict):
                if "max_daily_loss_rupees" in circuit_breakers:
                    limits.max_daily_loss_rupees = float(circuit_breakers["max_daily_loss_rupees"])
                
                if "max_daily_drawdown_pct" in circuit_breakers:
                    limits.max_daily_drawdown_pct = float(circuit_breakers["max_daily_drawdown_pct"])
                
                if "max_trades_per_day" in circuit_breakers:
                    limits.max_trades_per_day = int(circuit_breakers["max_trades_per_day"])
                
                if "max_trades_per_strategy_per_day" in circuit_breakers:
                    limits.max_trades_per_symbol_per_day = int(circuit_breakers["max_trades_per_strategy_per_day"])
                
                if "max_loss_streak" in circuit_breakers:
                    limits.max_loss_streak = int(circuit_breakers["max_loss_streak"])
            
            # Also check risk.quality section for per-symbol limit
            if isinstance(risk_section, dict):
                quality = risk_section.get("quality", {})
                if isinstance(quality, dict):
                    if "max_trades_per_symbol_per_day" in quality:
                        limits.max_trades_per_symbol_per_day = int(quality["max_trades_per_symbol_per_day"])
                
                # Also check top-level risk keys
                if "max_daily_loss_abs" in risk_section:
                    limits.max_daily_loss_rupees = float(risk_section["max_daily_loss_abs"])
                elif "max_daily_loss" in risk_section:
                    limits.max_daily_loss_rupees = float(risk_section["max_daily_loss"])
                
                if "max_daily_drawdown_pct" in risk_section:
                    limits.max_daily_drawdown_pct = float(risk_section["max_daily_drawdown_pct"])
    except Exception as exc:
        logger.warning("Failed to load base config from %s: %s", config_path_obj, exc)
    
    # Apply overrides from risk_overrides.yaml
    try:
        if overrides_path_obj.exists():
            with overrides_path_obj.open("r", encoding="utf-8") as f:
                overrides = yaml.safe_load(f) or {}
            
            if isinstance(overrides, dict):
                if "max_daily_loss_rupees" in overrides:
                    limits.max_daily_loss_rupees = float(overrides["max_daily_loss_rupees"])
                
                if "max_daily_drawdown_pct" in overrides:
                    limits.max_daily_drawdown_pct = float(overrides["max_daily_drawdown_pct"])
                
                if "max_trades_per_day" in overrides:
                    limits.max_trades_per_day = int(overrides["max_trades_per_day"])
                
                if "max_trades_per_symbol_per_day" in overrides:
                    limits.max_trades_per_symbol_per_day = int(overrides["max_trades_per_symbol_per_day"])
                
                if "max_loss_streak" in overrides:
                    limits.max_loss_streak = int(overrides["max_loss_streak"])
                
                # Get file modification time as updated_at
                stat = overrides_path_obj.stat()
                updated_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
    except Exception as exc:
        logger.debug("No risk overrides found at %s: %s", overrides_path_obj, exc)
    
    metadata = {
        "updated_at": updated_at,
        "source": {
            "base_config": str(config_path),
            "overrides": str(overrides_path)
        }
    }
    
    return limits, metadata


def save_risk_limits(
    patch: Dict[str, Any],
    overrides_path: str = str(RISK_OVERRIDES_PATH)
) -> RiskLimits:
    """
    Save risk limit overrides to configs/risk_overrides.yaml.
    
    Args:
        patch: Dictionary of risk limit overrides to save
        overrides_path: Path to overrides file (default: configs/risk_overrides.yaml)
    
    Returns:
        Updated RiskLimits instance after applying patch
    """
    overrides_path_obj = Path(overrides_path)
    
    # Ensure configs directory exists
    overrides_path_obj.parent.mkdir(parents=True, exist_ok=True)
    
    # Load existing overrides
    existing = {}
    try:
        if overrides_path_obj.exists():
            with overrides_path_obj.open("r", encoding="utf-8") as f:
                existing = yaml.safe_load(f) or {}
    except Exception as exc:
        logger.warning("Failed to load existing overrides: %s", exc)
    
    # Merge with new values
    existing.update(patch)
    
    # Save to file
    try:
        with overrides_path_obj.open("w", encoding="utf-8") as f:
            yaml.safe_dump(existing, f, default_flow_style=False)
        logger.info("Risk overrides saved to %s", overrides_path_obj)
    except Exception as exc:
        logger.error("Failed to save risk overrides: %s", exc)
        raise
    
    # Reload and return updated limits
    limits, _ = load_risk_limits(overrides_path=str(overrides_path_obj))
    return limits


def compute_breaches(limits: RiskLimits) -> List[Dict[str, Any]]:
    """
    Compute active risk limit breaches based on current runtime metrics.
    
    Args:
        limits: RiskLimits instance with configured limits
    
    Returns:
        List of active breach dictionaries, each containing:
        - code: Breach code (e.g., "MAX_DAILY_LOSS", "MAX_DRAWDOWN")
        - severity: "warning" or "critical"
        - message: Human-readable message
        - metric: Dict with current, limit, and unit
        - symbol: Trading symbol (or null for global breaches)
        - since: ISO timestamp when breach was first detected (or null)
    """
    breaches = []
    
    # Load runtime metrics
    try:
        if not RUNTIME_METRICS_PATH.exists():
            logger.debug("Runtime metrics file not found: %s", RUNTIME_METRICS_PATH)
            return breaches
        
        with RUNTIME_METRICS_PATH.open("r", encoding="utf-8") as f:
            metrics = json.load(f)
    except Exception as exc:
        logger.warning("Failed to load runtime metrics: %s", exc)
        return breaches
    
    timestamp = datetime.now(timezone.utc).isoformat()
    
    # Check max daily loss - look for realized_pnl or net_pnl in equity section or overall section
    equity = metrics.get("equity", {})
    overall = metrics.get("overall", {})
    
    # Try multiple locations for PnL
    net_pnl = float(equity.get("realized_pnl", overall.get("net_pnl", 0.0)))
    
    if net_pnl < -limits.max_daily_loss_rupees:
        breaches.append({
            "code": "MAX_DAILY_LOSS",
            "severity": "critical",
            "message": f"Daily loss of ₹{abs(net_pnl):,.2f} exceeds limit of ₹{limits.max_daily_loss_rupees:,.2f}",
            "metric": {
                "current": abs(net_pnl),
                "limit": limits.max_daily_loss_rupees,
                "unit": "rupees"
            },
            "symbol": None,
            "since": timestamp,
        })
    
    # Check max daily drawdown - could be negative decimal or percentage
    max_drawdown = float(equity.get("max_drawdown", 0.0))
    max_equity = float(equity.get("max_equity", 0.0))
    current_equity = float(equity.get("current_equity", 0.0))
    
    # Calculate drawdown percentage
    if max_drawdown != 0.0:
        # max_drawdown is already calculated (could be negative decimal like -0.025)
        drawdown_pct = abs(max_drawdown) * 100.0 if abs(max_drawdown) < 1.0 else abs(max_drawdown)
    elif max_equity > 0:
        # Calculate from max and current equity
        drawdown_pct = ((max_equity - current_equity) / max_equity) * 100.0
    else:
        drawdown_pct = 0.0
    
    # Convert limit to percentage if needed (handle both decimal and percentage formats)
    limit_pct = limits.max_daily_drawdown_pct * 100.0 if limits.max_daily_drawdown_pct < 1.0 else limits.max_daily_drawdown_pct
    
    if drawdown_pct > limit_pct:
        breaches.append({
            "code": "MAX_DRAWDOWN",
            "severity": "critical",
            "message": f"Daily drawdown of {drawdown_pct:.2f}% exceeds limit of {limit_pct:.2f}%",
            "metric": {
                "current": drawdown_pct,
                "limit": limit_pct,
                "unit": "percent"
            },
            "symbol": None,
            "since": timestamp,
        })
    
    # Check max trades per day
    total_trades = int(overall.get("total_trades", 0))
    if total_trades > limits.max_trades_per_day:
        breaches.append({
            "code": "MAX_TRADES_PER_DAY",
            "severity": "warning",
            "message": f"Total trades ({total_trades}) exceeds daily limit of {limits.max_trades_per_day}",
            "metric": {
                "current": total_trades,
                "limit": limits.max_trades_per_day,
                "unit": "trades"
            },
            "symbol": None,
            "since": timestamp,
        })
    
    # Check max loss streak (can be at top level or in overall section)
    loss_streak = int(metrics.get("loss_streak", overall.get("loss_streak", 0)))
    if loss_streak > limits.max_loss_streak:
        breaches.append({
            "code": "MAX_LOSS_STREAK",
            "severity": "critical",
            "message": f"Loss streak of {loss_streak} exceeds limit of {limits.max_loss_streak}",
            "metric": {
                "current": loss_streak,
                "limit": limits.max_loss_streak,
                "unit": "trades"
            },
            "symbol": None,
            "since": timestamp,
        })
    
    # Check max trades per symbol
    per_symbol = metrics.get("per_symbol", {})
    if isinstance(per_symbol, dict):
        for symbol, symbol_metrics in per_symbol.items():
            if not isinstance(symbol_metrics, dict):
                continue
            symbol_trades = int(symbol_metrics.get("total_trades", 0))
            if symbol_trades > limits.max_trades_per_symbol_per_day:
                breaches.append({
                    "code": "MAX_TRADES_PER_SYMBOL",
                    "severity": "warning",
                    "message": f"Trades for {symbol} ({symbol_trades}) exceeds per-symbol limit of {limits.max_trades_per_symbol_per_day}",
                    "metric": {
                        "current": symbol_trades,
                        "limit": limits.max_trades_per_symbol_per_day,
                        "unit": "trades"
                    },
                    "symbol": symbol,
                    "since": timestamp,
                })
    
    return breaches


def compute_var(days: int = 30, confidence: float = 0.95) -> Dict[str, Any]:
    """
    Compute historical Value at Risk (VaR) from daily metrics.
    
    Args:
        days: Number of days to look back (default: 30)
        confidence: Confidence level (default: 0.95 for 95% confidence)
        
    Returns:
        Dictionary with VaR computation results:
        - days: Number of days used
        - confidence: Confidence level
        - method: "historical"
        - var_rupees: Value at Risk in rupees
        - var_pct: Value at Risk as percentage of capital
        - sample_size: Number of data points used
    """
    if not DAILY_METRICS_DIR.exists():
        logger.warning("Daily metrics directory not found: %s", DAILY_METRICS_DIR)
        return {
            "days": days,
            "confidence": confidence,
            "method": "historical",
            "var_rupees": 0.0,
            "var_pct": 0.0,
            "sample_size": 0,
        }
    
    # Load daily PnL values
    daily_pnls: List[float] = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    starting_capital = None
    
    try:
        for metrics_file in sorted(DAILY_METRICS_DIR.glob("*-metrics.json")):
            try:
                # Extract date from filename (format: YYYY-MM-DD-metrics.json)
                date_str = metrics_file.stem.replace("-metrics", "")
                file_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                
                if file_date < cutoff:
                    continue
                
                with metrics_file.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                
                # Extract net PnL - try multiple locations
                equity = data.get("equity", {})
                overall = data.get("overall", {})
                
                # Try equity.realized_pnl first (used by tests), then overall.net_pnl
                net_pnl = float(equity.get("realized_pnl", overall.get("net_pnl", 0.0)))
                daily_pnls.append(net_pnl)
                
                # Get starting capital if available
                if starting_capital is None:
                    starting_capital = float(equity.get("starting_capital", 0.0))
            except Exception as exc:
                logger.debug("Failed to load daily metrics from %s: %s", metrics_file, exc)
                continue
    except Exception as exc:
        logger.error("Failed to load daily metrics: %s", exc)
        return {
            "days": days,
            "confidence": confidence,
            "method": "historical",
            "var_rupees": 0.0,
            "var_pct": 0.0,
            "sample_size": 0,
        }
    
    # Try to get starting capital from runtime metrics if not found
    if starting_capital is None or starting_capital == 0.0:
        try:
            if RUNTIME_METRICS_PATH.exists():
                with RUNTIME_METRICS_PATH.open("r", encoding="utf-8") as f:
                    runtime_data = json.load(f)
                equity = runtime_data.get("equity", {})
                starting_capital = float(equity.get("starting_capital", 500000.0))
        except Exception:
            starting_capital = 500000.0  # Default fallback
    
    if not daily_pnls:
        return {
            "days": days,
            "confidence": confidence,
            "method": "historical",
            "var_rupees": 0.0,
            "var_pct": 0.0,
            "sample_size": 0,
        }
    
    # Sort PnLs (ascending order, worst losses first)
    daily_pnls.sort()
    
    # Calculate VaR at the specified confidence level
    # VaR is the (1-confidence) percentile of losses
    # e.g., at 95% confidence, VaR is the 5th percentile
    index = int((len(daily_pnls) * (1.0 - confidence)))
    index = max(0, min(index, len(daily_pnls) - 1))
    
    var_rupees = abs(daily_pnls[index])  # VaR is expressed as positive number
    var_pct = (var_rupees / starting_capital) * 100.0 if starting_capital > 0 else 0.0
    
    return {
        "days": days,
        "confidence": confidence,
        "method": "historical",
        "var_rupees": var_rupees,
        "var_pct": var_pct,
        "sample_size": len(daily_pnls),
    }
