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


@router.get("/api/trades/open")
async def api_trades_open() -> JSONResponse:
    """
    Return all open trades from the open_trades.json registry.
    """
    try:
        from core.state_store import StateStore
        state_store = StateStore()
        open_trades = state_store.load_open_trades()
        return JSONResponse({"open_trades": open_trades, "count": len(open_trades)})
    except Exception as exc:
        import logging
        logger = logging.getLogger(__name__)
        logger.error("Failed to load open trades: %s", exc)
        return JSONResponse({"open_trades": [], "count": 0, "error": str(exc)})


@router.get("/api/trades/closed/today")
async def api_trades_closed_today() -> JSONResponse:
    """
    Return closed trades from today's orders.csv (where status="FILLED" and tag contains "exit").
    """
    try:
        import csv
        from datetime import date
        
        # Path to today's journal
        today_str = date.today().strftime("%Y-%m-%d")
        journal_path = BASE_DIR / "artifacts" / "journal" / today_str / "orders.csv"
        
        closed_trades = []
        if journal_path.exists():
            with journal_path.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Filter for exit orders
                    tag = (row.get("tag") or "").lower()
                    status = (row.get("status") or "").upper()
                    if "exit" in tag and status in ["FILLED", "COMPLETE", "EXECUTED"]:
                        closed_trades.append(row)
        
        return JSONResponse({"closed_trades": closed_trades, "count": len(closed_trades)})
    except Exception as exc:
        import logging
        logger = logging.getLogger(__name__)
        logger.error("Failed to load closed trades: %s", exc)
        return JSONResponse({"closed_trades": [], "count": 0, "error": str(exc)})


@router.get("/api/telemetry/runtime")
async def api_telemetry_runtime() -> JSONResponse:
    """
    Return runtime metrics from runtime_metrics.json.
    """
    try:
        import json
        runtime_metrics_path = BASE_DIR / "artifacts" / "analytics" / "runtime_metrics.json"
        
        if not runtime_metrics_path.exists():
            return JSONResponse({
                "active_positions": 0,
                "realized_pnl": 0.0,
                "unrealized_pnl": 0.0,
                "total_pnl": 0.0,
                "total_orders": 0,
            })
        
        with runtime_metrics_path.open("r", encoding="utf-8") as f:
            metrics = json.load(f)
        return JSONResponse(metrics)
    except Exception as exc:
        import logging
        logger = logging.getLogger(__name__)
        logger.error("Failed to load runtime metrics: %s", exc)
        return JSONResponse({"error": str(exc)})


@router.get("/api/telemetry/trade_lifecycle")
async def api_telemetry_trade_lifecycle() -> JSONResponse:
    """
    Return trade lifecycle telemetry combining open trades and runtime metrics.
    """
    try:
        import json
        from core.state_store import StateStore
        
        state_store = StateStore()
        open_trades = state_store.load_open_trades()
        
        # Load runtime metrics
        runtime_metrics_path = BASE_DIR / "artifacts" / "analytics" / "runtime_metrics.json"
        runtime_metrics = {}
        if runtime_metrics_path.exists():
            with runtime_metrics_path.open("r", encoding="utf-8") as f:
                runtime_metrics = json.load(f)
        
        # Compute summary statistics
        total_unrealized_pnl = 0.0
        for trade in open_trades:
            entry_price = float(trade.get('entry_price', 0))
            qty = int(trade.get('qty', 0))
            side = trade.get('side')
            
            # We'd need current price to calculate unrealized PnL accurately
            # For now, just provide the trade data
            
        return JSONResponse({
            "open_trades_count": len(open_trades),
            "open_trades": open_trades,
            "runtime_metrics": runtime_metrics,
            "timestamp": datetime.now().isoformat(),
        })
    except Exception as exc:
        import logging
        logger = logging.getLogger(__name__)
        logger.error("Failed to load trade lifecycle telemetry: %s", exc)
        return JSONResponse({"error": str(exc)})


router.include_router(dashboard_module.router)
router.include_router(dashboard_logs.router)

app = FastAPI(title="Dashboard")
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.include_router(router)
app.include_router(api_strategies.router, prefix="/api/strategies", tags=["strategies"])

__all__ = ["router", "app"]
