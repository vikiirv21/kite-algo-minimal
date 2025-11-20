from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any

import pytz
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.config import AppConfig, load_config
from core.market_session import is_market_open
from ui import dashboard as dashboard_module
from apps import dashboard_logs
from apps import api_strategies

BASE_DIR = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
DEFAULT_CONFIG_PATH = BASE_DIR / "configs" / "dev.yaml"
CONFIG_PATH = Path(
    os.environ.get("HFT_CONFIG", os.environ.get("KITE_DASHBOARD_CONFIG", str(DEFAULT_CONFIG_PATH)))
).expanduser()

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()
_config_cache: AppConfig | None = None


def load_app_config() -> AppConfig:
    global _config_cache  # noqa: PLW0603
    if _config_cache is None:
        _config_cache = load_config(str(CONFIG_PATH))
    return _config_cache


def summarize_config(cfg: AppConfig) -> dict[str, Any]:
    trading = cfg.trading or {}
    risk = cfg.risk or {}
    meta = cfg.meta or {}

    mode_raw = trading.get("mode", "paper")
    try:
        from core.modes import TradingMode
        
        # Normalize to lowercase to match enum values
        mode_str = str(mode_raw).strip().lower()
        mode = TradingMode(mode_str).value
    except Exception:
        mode = str(mode_raw).lower()

    fno_universe = trading.get("fno_universe") or []
    if isinstance(fno_universe, (str, bytes)):
        fno_universe = [fno_universe]
    fno_universe = [str(item).strip().upper() for item in fno_universe if item]

    paper_capital = float(trading.get("paper_capital", 500_000))
    risk_per_trade_pct = float(risk.get("risk_per_trade_pct", 0.005))
    max_daily_loss = float(trading.get("max_daily_loss", 3_000))
    max_exposure_pct = float(
        risk.get(
            "max_gross_exposure_pct",
            risk.get("max_exposure_pct", trading.get("max_notional_multiplier", 2.0)),
        )
    )

    if risk_per_trade_pct <= 0.004 and max_exposure_pct <= 1.5:
        risk_profile = "Conservative"
    elif risk_per_trade_pct >= 0.01 or max_exposure_pct >= 3.0:
        risk_profile = "Aggressive"
    else:
        risk_profile = "Default"

    meta_enabled = bool(meta.get("enabled", True))

    return {
        "config_path": str(CONFIG_PATH),
        "mode": mode,
        "fno_universe": fno_universe,
        "paper_capital": paper_capital,
        "risk_per_trade_pct": risk_per_trade_pct,
        "max_daily_loss": max_daily_loss,
        "max_exposure_pct": max_exposure_pct,
        "risk_profile": risk_profile,
        "meta_enabled": meta_enabled,
    }


@router.get("/", response_class=HTMLResponse)
async def dashboard_page(request: Request) -> HTMLResponse:
    """
    Render the main dashboard shell with optional config YAML injection.
    """
    config_yaml = ""
    try:
        candidate_paths = [
            CONFIG_PATH,
            DEFAULT_CONFIG_PATH,
        ]
        for path in candidate_paths:
            if path.exists():
                config_yaml = path.read_text(encoding="utf-8")
                break
    except Exception:
        config_yaml = ""

    context: dict[str, Any] = {
        "request": request,
        "config_yaml": config_yaml,
    }
    return templates.TemplateResponse("dashboard.html", context)


@router.get("/api/meta")
async def get_meta() -> dict[str, Any]:
    """
    Returns IST time + whether the market is open.
    """
    ist = pytz.timezone("Asia/Kolkata")
    now_ist = datetime.now(ist)
    return {
        "now_ist": now_ist.isoformat(),
        "market_open": is_market_open(),
    }


@router.get("/api/config/summary")
async def api_config_summary() -> JSONResponse:
    cfg = load_app_config()
    summary = summarize_config(cfg)
    return JSONResponse(summary)


@router.get("/api/performance")
async def api_performance() -> JSONResponse:
    """
    Return performance metrics from Performance Engine V2.
    
    Returns runtime_metrics.json if available, otherwise returns
    a default empty structure.
    """
    runtime_metrics_path = BASE_DIR / "artifacts" / "analytics" / "runtime_metrics.json"
    
    # Default empty structure
    default_metrics = {
        "asof": None,
        "mode": "paper",
        "equity": {
            "starting_capital": 0.0,
            "current_equity": 0.0,
            "realized_pnl": 0.0,
            "unrealized_pnl": 0.0,
            "max_drawdown": 0.0,
            "max_equity": 0.0,
            "min_equity": 0.0,
        },
        "overall": {
            "total_trades": 0,
            "win_trades": 0,
            "loss_trades": 0,
            "breakeven_trades": 0,
            "win_rate": 0.0,
            "gross_profit": 0.0,
            "gross_loss": 0.0,
            "net_pnl": 0.0,
            "profit_factor": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "avg_r_multiple": 0.0,
            "biggest_win": 0.0,
            "biggest_loss": 0.0,
        },
        "per_strategy": {},
        "per_symbol": {},
    }
    
    if not runtime_metrics_path.exists():
        return JSONResponse(default_metrics)
    
    try:
        import json
        with runtime_metrics_path.open("r", encoding="utf-8") as f:
            metrics = json.load(f)
        return JSONResponse(metrics)
    except Exception as exc:
        # Log error but return default structure
        import logging
        logger = logging.getLogger(__name__)
        logger.error("Failed to load performance metrics: %s", exc)
        return JSONResponse(default_metrics)


@router.get("/api/data/health")
async def api_data_health() -> JSONResponse:
    """
    Returns data health snapshot from Market Data Engine V2 if enabled.
    
    Returns health information per symbol/timeframe including:
    - last_update_ts: timestamp of last data update
    - staleness_sec: seconds since last update
    - num_bars: number of historical candles available
    - is_stale: boolean indicating if data is stale
    
    Response format:
    {
      "enabled": true/false,
      "asof": "2025-11-19T08:45:12+05:30",
      "items": [
        {
          "symbol": "NIFTY25NOVFUT",
          "timeframe": "1m",
          "last_update_ts": "2025-11-19T08:44:59+05:30",
          "staleness_sec": 3.2,
          "num_bars": 215,
          "is_stale": false
        },
        ...
      ]
    }
    
    If MDE v2 is not enabled, returns {"enabled": false, "reason": "mde_v2_disabled"}
    """
    import json
    import pytz
    
    try:
        cfg = load_app_config()
        data_cfg = cfg.data or {}
        
        use_mde_v2 = data_cfg.get("use_mde_v2", False)
        
        if not use_mde_v2:
            return JSONResponse({
                "enabled": False,
                "reason": "mde_v2_disabled"
            })
        
        # Check if MDE v2 instance is running
        # For now, we'll check for a telemetry file that MDE v2 could write
        # In a real implementation, this would access a shared MDE v2 instance
        mde_health_path = BASE_DIR / "artifacts" / "mde_v2" / "health_snapshot.json"
        
        if not mde_health_path.exists():
            return JSONResponse({
                "enabled": True,
                "asof": None,
                "items": [],
                "reason": "no_data_available"
            })
        
        # Read health snapshot
        with mde_health_path.open("r", encoding="utf-8") as f:
            health_data = json.load(f)
        
        return JSONResponse(health_data)
        
    except Exception as exc:
        import logging
        logger = logging.getLogger(__name__)
        logger.error("Failed to get MDE v2 health: %s", exc)
        return JSONResponse({
            "enabled": False,
            "reason": f"error: {str(exc)}"
        })


@router.get("/api/data/ltp")
async def api_data_ltp(symbol: str) -> JSONResponse:
    """
    Returns current LTP and last update timestamp for a single symbol.
    
    Query params:
    - symbol: Trading symbol (e.g., "NIFTY25NOVFUT", "RELIANCE")
    
    Response format:
    {
      "enabled": true/false,
      "symbol": "NIFTY25NOVFUT",
      "ltp": 23850.0,
      "last_update_ts": "2025-11-19T08:45:12+05:30"
    }
    
    If MDE v2 is not enabled or symbol not found, returns appropriate error.
    """
    import json
    
    try:
        cfg = load_app_config()
        data_cfg = cfg.data or {}
        
        use_mde_v2 = data_cfg.get("use_mde_v2", False)
        
        if not use_mde_v2:
            return JSONResponse({
                "enabled": False,
                "reason": "mde_v2_disabled"
            })
        
        # Check for MDE v2 LTP data
        # In a real implementation, this would access a shared MDE v2 instance
        mde_ltp_path = BASE_DIR / "artifacts" / "mde_v2" / "ltp_snapshot.json"
        
        if not mde_ltp_path.exists():
            return JSONResponse({
                "enabled": True,
                "symbol": symbol.upper(),
                "ltp": None,
                "last_update_ts": None,
                "reason": "no_data_available"
            })
        
        # Read LTP snapshot
        with mde_ltp_path.open("r", encoding="utf-8") as f:
            ltp_data = json.load(f)
        
        symbol_upper = symbol.upper()
        symbol_data = ltp_data.get(symbol_upper)
        
        if not symbol_data:
            return JSONResponse({
                "enabled": True,
                "symbol": symbol_upper,
                "ltp": None,
                "last_update_ts": None,
                "reason": "symbol_not_found"
            })
        
        return JSONResponse({
            "enabled": True,
            "symbol": symbol_upper,
            "ltp": symbol_data.get("ltp"),
            "last_update_ts": symbol_data.get("last_update_ts")
        })
        
    except Exception as exc:
        import logging
        logger = logging.getLogger(__name__)
        logger.error("Failed to get MDE v2 LTP for %s: %s", symbol, exc)
        return JSONResponse({
            "enabled": False,
            "symbol": symbol.upper(),
            "reason": f"error: {str(exc)}"
        })


router.include_router(dashboard_module.router)
router.include_router(dashboard_logs.router)

app = FastAPI(title="Dashboard")
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.include_router(router)
app.include_router(api_strategies.router, prefix="/api/strategies", tags=["strategies"])

__all__ = ["router", "app"]
