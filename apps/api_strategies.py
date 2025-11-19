"""
Strategy Lab API Endpoints

Provides REST API for strategy management, parameter updates, and backtesting.
"""

from __future__ import annotations

import json
import logging
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.strategy_registry import STRATEGY_REGISTRY, StrategyInfo
from core.config import load_config

logger = logging.getLogger(__name__)

# Configuration paths
BASE_DIR = Path(__file__).resolve().parents[1]
CONFIGS_DIR = BASE_DIR / "configs"
LEARNED_OVERRIDES_PATH = CONFIGS_DIR / "learned_overrides.yaml"
DEV_CONFIG_PATH = CONFIGS_DIR / "dev.yaml"

router = APIRouter()


# ==================== Pydantic Models ====================

class StrategyParamsUpdate(BaseModel):
    """Request model for updating strategy parameters."""
    params: Dict[str, Any] = Field(..., description="Strategy parameter overrides")


class BacktestRequest(BaseModel):
    """Request model for backtesting a strategy."""
    symbol: str = Field(..., description="Trading symbol (e.g., SBIN, NIFTY)")
    engine: str = Field("equity", description="Engine type: equity, fno, or options")
    timeframe: str = Field("5m", description="Timeframe (e.g., 1m, 5m, 15m)")
    from_date: str = Field(..., description="Start date (YYYY-MM-DD)")
    to_date: str = Field(..., description="End date (YYYY-MM-DD)")
    params_override: Optional[Dict[str, Any]] = Field(None, description="Optional parameter overrides")


class StrategyDetail(BaseModel):
    """Detailed strategy information."""
    id: str
    name: str
    strategy_code: str
    engine: str
    timeframe: str
    mode: str = "paper"
    enabled: bool
    params: Dict[str, Any]
    tags: List[str]


class BacktestResult(BaseModel):
    """Backtest execution result."""
    summary: Dict[str, Any]
    equity_curve: Optional[List[List[Any]]] = None


# ==================== Helper Functions ====================

def load_strategy_overrides() -> Dict[str, Any]:
    """Load strategy overrides from learned_overrides.yaml."""
    try:
        if LEARNED_OVERRIDES_PATH.exists():
            with LEARNED_OVERRIDES_PATH.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                return data.get("strategies", {})
    except Exception as exc:
        logger.warning("Failed to load strategy overrides: %s", exc)
    return {}


def save_strategy_overrides(overrides: Dict[str, Any]) -> None:
    """Save strategy overrides to learned_overrides.yaml."""
    try:
        # Ensure configs directory exists
        LEARNED_OVERRIDES_PATH.parent.mkdir(parents=True, exist_ok=True)
        
        # Load existing data
        existing = {}
        if LEARNED_OVERRIDES_PATH.exists():
            with LEARNED_OVERRIDES_PATH.open("r", encoding="utf-8") as f:
                existing = yaml.safe_load(f) or {}
        
        # Update strategies section
        existing["strategies"] = overrides
        
        # Save to file
        with LEARNED_OVERRIDES_PATH.open("w", encoding="utf-8") as f:
            yaml.safe_dump(existing, f, default_flow_style=False)
        
        logger.info("Strategy overrides saved to %s", LEARNED_OVERRIDES_PATH)
    except Exception as exc:
        logger.error("Failed to save strategy overrides: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to save overrides: {exc}")


def get_strategy_params(strategy_id: str) -> Dict[str, Any]:
    """Get strategy parameters from config."""
    try:
        config = load_config(str(DEV_CONFIG_PATH))
        strategy_engine = config.raw.get("strategy_engine", {})
        
        # Check if it's a v2 strategy
        strategies_v2 = strategy_engine.get("strategies_v2", [])
        for strat in strategies_v2:
            if strat.get("id") == strategy_id:
                return strat.get("params", {})
        
        # Fallback to empty params
        return {}
    except Exception as exc:
        logger.warning("Failed to load strategy params for %s: %s", strategy_id, exc)
        return {}


def list_strategies() -> List[StrategyDetail]:
    """List all available strategies with their current configuration."""
    strategies = []
    overrides = load_strategy_overrides()
    
    try:
        config = load_config(str(DEV_CONFIG_PATH))
        strategy_engine = config.raw.get("strategy_engine", {})
        strategies_v2 = strategy_engine.get("strategies_v2", [])
        
        for strat in strategies_v2:
            strategy_id = strat.get("id", "")
            if not strategy_id:
                continue
            
            # Get base params
            base_params = strat.get("params", {})
            
            # Apply overrides
            strategy_override = overrides.get(strategy_id, {})
            enabled = strategy_override.get("enabled", strat.get("enabled", True))
            params_override = strategy_override.get("params", {})
            
            # Merge params
            final_params = {**base_params, **params_override}
            
            # Determine engine from tags or default to equity
            tags = []
            engine = "equity"
            
            # Check registry for additional metadata
            if strategy_id in STRATEGY_REGISTRY or strategy_id.lower() in STRATEGY_REGISTRY:
                registry_key = strategy_id if strategy_id in STRATEGY_REGISTRY else strategy_id.lower()
                registry_info = STRATEGY_REGISTRY[registry_key]
                tags = registry_info.tags
                
                # Infer engine from tags
                if "fno" in tags or "futures" in tags:
                    engine = "fno"
                elif "options" in tags:
                    engine = "options"
                else:
                    engine = "equity"
            
            strategies.append(StrategyDetail(
                id=strategy_id,
                name=strat.get("class", strategy_id),
                strategy_code=strategy_id,
                engine=engine,
                timeframe=final_params.get("timeframe", "5m"),
                mode="paper",  # TODO: Get from runtime state
                enabled=enabled,
                params=final_params,
                tags=tags,
            ))
    except Exception as exc:
        logger.error("Failed to list strategies: %s", exc)
    
    return strategies


def set_strategy_enabled(strategy_id: str, enabled: bool) -> StrategyDetail:
    """Enable or disable a strategy."""
    # Load current overrides
    overrides = load_strategy_overrides()
    
    # Update enabled status
    if strategy_id not in overrides:
        overrides[strategy_id] = {}
    overrides[strategy_id]["enabled"] = enabled
    
    # Save overrides
    save_strategy_overrides(overrides)
    
    # Return updated strategy
    strategies = list_strategies()
    for strat in strategies:
        if strat.id == strategy_id:
            return strat
    
    raise HTTPException(status_code=404, detail=f"Strategy {strategy_id} not found")


def update_strategy_params(strategy_id: str, params: Dict[str, Any]) -> StrategyDetail:
    """Update strategy parameters."""
    # Load current overrides
    overrides = load_strategy_overrides()
    
    # Update params
    if strategy_id not in overrides:
        overrides[strategy_id] = {}
    
    # Merge with existing param overrides
    existing_params = overrides[strategy_id].get("params", {})
    existing_params.update(params)
    overrides[strategy_id]["params"] = existing_params
    
    # Save overrides
    save_strategy_overrides(overrides)
    
    # Return updated strategy
    strategies = list_strategies()
    for strat in strategies:
        if strat.id == strategy_id:
            return strat
    
    raise HTTPException(status_code=404, detail=f"Strategy {strategy_id} not found")


def run_backtest(strategy_id: str, request: BacktestRequest) -> BacktestResult:
    """
    Run a simple backtest for the given strategy.
    
    This is a v1 implementation that returns mock results.
    TODO: Implement actual backtest execution using backtest engine.
    """
    logger.info(
        "Backtest requested for strategy=%s, symbol=%s, timeframe=%s, dates=%s to %s",
        strategy_id,
        request.symbol,
        request.timeframe,
        request.from_date,
        request.to_date,
    )
    
    # TODO: Implement actual backtest logic
    # For now, return mock results to enable UI development
    
    # Generate mock equity curve (starting at 500000, ending with modest gain)
    from datetime import datetime, timedelta
    start = datetime.strptime(request.from_date, "%Y-%m-%d")
    end = datetime.strptime(request.to_date, "%Y-%m-%d")
    days = (end - start).days
    
    equity_curve = []
    equity = 500000.0
    
    for i in range(days + 1):
        date = start + timedelta(days=i)
        # Add some random walk
        import random
        equity += random.uniform(-2000, 3000)
        equity = max(equity, 480000)  # Floor
        equity_curve.append([date.strftime("%Y-%m-%d"), round(equity, 2)])
    
    summary = {
        "trades": random.randint(20, 50),
        "win_rate": round(random.uniform(0.50, 0.65), 2),
        "total_pnl": round(equity - 500000.0, 2),
        "max_drawdown_pct": round(random.uniform(-5.0, -1.0), 2),
        "avg_pnl_per_trade": round((equity - 500000.0) / max(1, random.randint(20, 50)), 2),
    }
    
    return BacktestResult(summary=summary, equity_curve=equity_curve)


# ==================== API Endpoints ====================

@router.get("/", response_model=List[StrategyDetail])
async def get_strategies():
    """List all available strategies."""
    return list_strategies()


@router.post("/{strategy_id}/enable", response_model=StrategyDetail)
async def enable_strategy(strategy_id: str):
    """Enable a strategy."""
    return set_strategy_enabled(strategy_id, True)


@router.post("/{strategy_id}/disable", response_model=StrategyDetail)
async def disable_strategy(strategy_id: str):
    """Disable a strategy."""
    return set_strategy_enabled(strategy_id, False)


@router.put("/{strategy_id}/params", response_model=StrategyDetail)
async def update_params(strategy_id: str, update: StrategyParamsUpdate):
    """Update strategy parameters."""
    return update_strategy_params(strategy_id, update.params)


@router.post("/{strategy_id}/backtest", response_model=BacktestResult)
async def backtest_strategy(strategy_id: str, request: BacktestRequest):
    """Run a backtest for the given strategy."""
    return run_backtest(strategy_id, request)
