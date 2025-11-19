"""
Advanced Risk API Endpoints

Provides REST API for risk limit management, breach detection, and VaR computation.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from dataclasses import asdict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from analytics.risk_service import (
    load_risk_limits,
    save_risk_limits,
    compute_breaches,
    compute_var,
    RiskLimits,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ==================== Pydantic Models ====================

class RiskLimitsResponse(BaseModel):
    """Risk limits response model."""
    max_daily_loss_rupees: float
    max_daily_drawdown_pct: float
    max_trades_per_day: int
    max_trades_per_symbol_per_day: int
    max_loss_streak: int
    metadata: Optional[Dict[str, Any]] = None


class RiskLimitsUpdate(BaseModel):
    """Request model for updating risk limits."""
    max_daily_loss_rupees: Optional[float] = Field(None, gt=0, description="Maximum daily loss in rupees")
    max_daily_drawdown_pct: Optional[float] = Field(None, gt=0, le=1.0, description="Maximum daily drawdown (as decimal, e.g., 0.02 for 2%)")
    max_trades_per_day: Optional[int] = Field(None, gt=0, description="Maximum trades per day")
    max_trades_per_symbol_per_day: Optional[int] = Field(None, gt=0, description="Maximum trades per symbol per day")
    max_loss_streak: Optional[int] = Field(None, gt=0, description="Maximum consecutive losses before halt")


class RiskBreach(BaseModel):
    """Risk breach model."""
    code: str
    severity: str
    message: str
    metric: Dict[str, Any]
    symbol: Optional[str] = None
    since: Optional[str] = None


class VaRResponse(BaseModel):
    """Value at Risk response model."""
    horizon_days: int
    confidence: float
    method: str
    var_rupees: float
    var_pct: float
    sample_size: int


# ==================== API Endpoints ====================

@router.get("/limits", response_model=RiskLimitsResponse)
async def get_risk_limits():
    """
    Get current risk limits.
    
    Returns the effective risk settings (base config + overrides).
    """
    try:
        limits, metadata = load_risk_limits()
        
        return RiskLimitsResponse(
            max_daily_loss_rupees=limits.max_daily_loss_rupees,
            max_daily_drawdown_pct=limits.max_daily_drawdown_pct,
            max_trades_per_day=limits.max_trades_per_day,
            max_trades_per_symbol_per_day=limits.max_trades_per_symbol_per_day,
            max_loss_streak=limits.max_loss_streak,
            metadata=metadata,
        )
    except Exception as exc:
        logger.error("Failed to load risk limits: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to load risk limits: {exc}")


@router.post("/limits", response_model=RiskLimitsResponse)
async def update_risk_limits(update: RiskLimitsUpdate):
    """
    Update risk limits.
    
    Accepts partial updates and persists them to risk_overrides.yaml.
    Only provided fields will be updated.
    """
    try:
        # Build patch dictionary with only provided fields
        patch = {}
        
        if update.max_daily_loss_rupees is not None:
            patch["max_daily_loss_rupees"] = update.max_daily_loss_rupees
        
        if update.max_daily_drawdown_pct is not None:
            patch["max_daily_drawdown_pct"] = update.max_daily_drawdown_pct
        
        if update.max_trades_per_day is not None:
            patch["max_trades_per_day"] = update.max_trades_per_day
        
        if update.max_trades_per_symbol_per_day is not None:
            patch["max_trades_per_symbol_per_day"] = update.max_trades_per_symbol_per_day
        
        if update.max_loss_streak is not None:
            patch["max_loss_streak"] = update.max_loss_streak
        
        if not patch:
            raise HTTPException(status_code=400, detail="No fields provided to update")
        
        # Save and reload
        limits = save_risk_limits(patch)
        _, metadata = load_risk_limits()
        
        return RiskLimitsResponse(
            max_daily_loss_rupees=limits.max_daily_loss_rupees,
            max_daily_drawdown_pct=limits.max_daily_drawdown_pct,
            max_trades_per_day=limits.max_trades_per_day,
            max_trades_per_symbol_per_day=limits.max_trades_per_symbol_per_day,
            max_loss_streak=limits.max_loss_streak,
            metadata=metadata,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to update risk limits: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to update risk limits: {exc}")


@router.get("/breaches", response_model=List[RiskBreach])
async def get_risk_breaches():
    """
    Get active risk limit breaches.
    
    Analyzes current runtime metrics and returns any active breaches.
    """
    try:
        limits, _ = load_risk_limits()
        breaches = compute_breaches(limits)
        
        return [
            RiskBreach(
                code=breach["code"],
                severity=breach["severity"],
                message=breach["message"],
                metric=breach["metric"],
                symbol=breach.get("symbol"),
                since=breach.get("since"),
            )
            for breach in breaches
        ]
    except Exception as exc:
        logger.error("Failed to compute risk breaches: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to compute breaches: {exc}")


@router.get("/var", response_model=VaRResponse)
async def get_var(
    horizon_days: int = 1,
    confidence: float = 0.95,
):
    """
    Get Value at Risk (VaR) calculation.
    
    Args:
        horizon_days: Number of days for VaR horizon (default: 1)
        confidence: Confidence level (default: 0.95 for 95%)
    
    Returns:
        VaR calculation using historical method
    """
    try:
        # Validate inputs
        if horizon_days < 1:
            raise HTTPException(status_code=400, detail="horizon_days must be >= 1")
        
        if confidence <= 0 or confidence >= 1:
            raise HTTPException(status_code=400, detail="confidence must be between 0 and 1")
        
        # For multi-day horizons, use 30 days of data minimum
        lookback_days = max(30, horizon_days * 10)
        
        result = compute_var(days=lookback_days, confidence=confidence)
        
        # Scale VaR by horizon if needed (simple sqrt(T) scaling for multi-day)
        if horizon_days > 1:
            import math
            scaling_factor = math.sqrt(horizon_days)
            result["var_rupees"] = result["var_rupees"] * scaling_factor
            result["var_pct"] = result["var_pct"] * scaling_factor
        
        return VaRResponse(
            horizon_days=horizon_days,
            confidence=result["confidence"],
            method=result["method"],
            var_rupees=result["var_rupees"],
            var_pct=result["var_pct"],
            sample_size=result["sample_size"],
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to compute VaR: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to compute VaR: {exc}")
