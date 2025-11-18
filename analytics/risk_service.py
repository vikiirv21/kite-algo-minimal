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
    max_daily_drawdown_pct: float = 5.0
    max_trades_per_day: int = 20
    max_trades_per_symbol_per_day: int = 5
    max_loss_streak: int = 3


def load_risk_limits() -> RiskLimits:
    """
    Load risk limits from config files.
    
    Reads from configs/dev.yaml and applies overrides from configs/risk_overrides.yaml.
    
    Returns:
        RiskLimits dataclass with merged configuration
    """
    limits = RiskLimits()
    
    # Load base config from dev.yaml
    try:
        if DEV_CONFIG_PATH.exists():
            with DEV_CONFIG_PATH.open("r", encoding="utf-8") as f:
                dev_config = yaml.safe_load(f) or {}
            
            # Extract risk section
            risk_section = dev_config.get("risk", {})
            
            if isinstance(risk_section, dict):
                # Map config keys to RiskLimits fields
                if "max_daily_loss_abs" in risk_section:
                    limits.max_daily_loss_rupees = float(risk_section["max_daily_loss_abs"])
                elif "max_daily_loss" in risk_section:
                    limits.max_daily_loss_rupees = float(risk_section["max_daily_loss"])
                
                if "max_daily_drawdown_pct" in risk_section:
                    limits.max_daily_drawdown_pct = float(risk_section["max_daily_drawdown_pct"])
                
                if "max_trades_per_day" in risk_section:
                    limits.max_trades_per_day = int(risk_section["max_trades_per_day"])
                
                if "max_trades_per_symbol_per_day" in risk_section:
                    limits.max_trades_per_symbol_per_day = int(risk_section["max_trades_per_symbol_per_day"])
                
                if "max_loss_streak" in risk_section:
                    limits.max_loss_streak = int(risk_section["max_loss_streak"])
    except Exception as exc:
        logger.warning("Failed to load base config from %s: %s", DEV_CONFIG_PATH, exc)
    
    # Apply overrides from risk_overrides.yaml
    try:
        if RISK_OVERRIDES_PATH.exists():
            with RISK_OVERRIDES_PATH.open("r", encoding="utf-8") as f:
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
    except Exception as exc:
        logger.debug("No risk overrides found at %s: %s", RISK_OVERRIDES_PATH, exc)
    
    return limits


def save_risk_limits(patch_dict: Dict[str, Any]) -> None:
    """
    Save risk limit overrides to configs/risk_overrides.yaml.
    
    Args:
        patch_dict: Dictionary of risk limit overrides to save
    """
    # Ensure configs directory exists
    CONFIGS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Load existing overrides
    existing = {}
    try:
        if RISK_OVERRIDES_PATH.exists():
            with RISK_OVERRIDES_PATH.open("r", encoding="utf-8") as f:
                existing = yaml.safe_load(f) or {}
    except Exception as exc:
        logger.warning("Failed to load existing overrides: %s", exc)
    
    # Merge with new values
    existing.update(patch_dict)
    
    # Save to file
    try:
        with RISK_OVERRIDES_PATH.open("w", encoding="utf-8") as f:
            yaml.safe_dump(existing, f, default_flow_style=False)
        logger.info("Risk overrides saved to %s", RISK_OVERRIDES_PATH)
    except Exception as exc:
        logger.error("Failed to save risk overrides: %s", exc)
        raise


def compute_breaches() -> List[Dict[str, Any]]:
    """
    Compute active risk limit breaches based on current runtime metrics.
    
    Returns:
        List of active breach dictionaries, each containing:
        - type: Breach type (e.g., "max_daily_loss", "max_trades_per_day")
        - limit: The limit value
        - current: The current value
        - timestamp: When the breach was detected
    """
    breaches = []
    
    # Load risk limits
    limits = load_risk_limits()
    
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
    
    # Check max daily loss
    overall = metrics.get("overall", {})
    net_pnl = float(overall.get("net_pnl", 0.0))
    if net_pnl < -limits.max_daily_loss_rupees:
        breaches.append({
            "type": "max_daily_loss",
            "limit": limits.max_daily_loss_rupees,
            "current": abs(net_pnl),
            "timestamp": timestamp,
        })
    
    # Check max daily drawdown
    equity = metrics.get("equity", {})
    max_equity = float(equity.get("max_equity", 0.0))
    current_equity = float(equity.get("current_equity", 0.0))
    
    if max_equity > 0:
        drawdown_pct = ((max_equity - current_equity) / max_equity) * 100.0
        if drawdown_pct > limits.max_daily_drawdown_pct:
            breaches.append({
                "type": "max_daily_drawdown_pct",
                "limit": limits.max_daily_drawdown_pct,
                "current": drawdown_pct,
                "timestamp": timestamp,
            })
    
    # Check max trades per day
    total_trades = int(overall.get("total_trades", 0))
    if total_trades > limits.max_trades_per_day:
        breaches.append({
            "type": "max_trades_per_day",
            "limit": limits.max_trades_per_day,
            "current": total_trades,
            "timestamp": timestamp,
        })
    
    # Check max loss streak
    # This would require tracking consecutive losing trades
    # For now, we can check if there's a loss_streak field in metrics
    loss_streak = int(metrics.get("loss_streak", 0))
    if loss_streak > limits.max_loss_streak:
        breaches.append({
            "type": "max_loss_streak",
            "limit": limits.max_loss_streak,
            "current": loss_streak,
            "timestamp": timestamp,
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
        - var: Value at Risk in rupees
        - days: Number of days used
        - confidence: Confidence level
        - observations: Number of data points used
        - percentile: Percentile used for calculation
    """
    if not DAILY_METRICS_DIR.exists():
        logger.warning("Daily metrics directory not found: %s", DAILY_METRICS_DIR)
        return {
            "var": None,
            "days": days,
            "confidence": confidence,
            "observations": 0,
            "percentile": (1.0 - confidence) * 100.0,
            "error": "No daily metrics available",
        }
    
    # Load daily PnL values
    daily_pnls: List[float] = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    
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
                
                # Extract net PnL
                overall = data.get("overall", {})
                net_pnl = float(overall.get("net_pnl", 0.0))
                daily_pnls.append(net_pnl)
            except Exception as exc:
                logger.debug("Failed to load daily metrics from %s: %s", metrics_file, exc)
                continue
    except Exception as exc:
        logger.error("Failed to load daily metrics: %s", exc)
        return {
            "var": None,
            "days": days,
            "confidence": confidence,
            "observations": 0,
            "percentile": (1.0 - confidence) * 100.0,
            "error": str(exc),
        }
    
    if not daily_pnls:
        return {
            "var": None,
            "days": days,
            "confidence": confidence,
            "observations": 0,
            "percentile": (1.0 - confidence) * 100.0,
            "error": "No observations in the time window",
        }
    
    # Sort PnLs (ascending order, worst losses first)
    daily_pnls.sort()
    
    # Calculate VaR at the specified confidence level
    # VaR is the (1-confidence) percentile of losses
    # e.g., at 95% confidence, VaR is the 5th percentile
    percentile = (1.0 - confidence) * 100.0
    index = int((len(daily_pnls) * (1.0 - confidence)))
    index = max(0, min(index, len(daily_pnls) - 1))
    
    var_value = abs(daily_pnls[index])  # VaR is expressed as positive number
    
    return {
        "var": var_value,
        "days": days,
        "confidence": confidence,
        "observations": len(daily_pnls),
        "percentile": percentile,
        "worst_loss": abs(min(daily_pnls)),
        "best_gain": max(daily_pnls),
    }
