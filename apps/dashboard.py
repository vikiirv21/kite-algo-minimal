from __future__ import annotations

import datetime as dt
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pytz
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.config import AppConfig, load_config, LEARNED_OVERRIDES_PATH
from core.market_session import is_market_open
from ui import dashboard as dashboard_module
from apps import dashboard_logs
from apps import api_strategies
from analytics.risk_metrics import load_risk_limits, compute_risk_breaches, compute_var
from analytics.benchmarks import load_benchmarks
from analytics.diagnostics import load_diagnostics

BASE_DIR = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = BASE_DIR / "ui" / "templates"
STATIC_DIR = BASE_DIR / "ui" / "static"
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
    Render the HFT-style dashboard.
    """
    context: dict[str, Any] = {
        "request": request,
    }
    return templates.TemplateResponse("index_hft.html", context)


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


@router.get("/api/status")
async def api_status() -> JSONResponse:
    """
    Return current system status including mode and live capital.
    
    This endpoint provides:
    - mode: "paper" or "live"
    - live_capital: Current capital (from live_state.json in live mode)
    - market_open: Whether market is currently open
    - timestamp: Current server time
    """
    cfg = load_app_config()
    trading = cfg.trading or {}
    mode = str(trading.get("mode", "paper")).lower()
    
    # Default capital from config
    live_capital = float(trading.get("live_capital", trading.get("paper_capital", 500000)))
    
    # Try to load live capital from live_state.json if in live mode
    if mode == "live":
        live_state_path = BASE_DIR / "artifacts" / "live_state.json"
        if live_state_path.exists():
            try:
                with live_state_path.open("r", encoding="utf-8") as f:
                    live_state = json.load(f)
                    live_capital = float(live_state.get("live_capital", live_capital))
            except Exception:
                pass
    
    return JSONResponse({
        "mode": mode,
        "live_capital": live_capital,
        "market_open": is_market_open(),
        "timestamp": datetime.now().isoformat(),
    })


@router.get("/api/live/capital")
async def api_live_capital() -> JSONResponse:
    """
    Return live capital information.
    
    Reads from artifacts/live_state.json which is updated by LiveEquityEngine.
    """
    live_state_path = BASE_DIR / "artifacts" / "live_state.json"
    
    default_response = {
        "live_capital": 0.0,
        "positions": [],
        "open_positions_count": 0,
        "unrealized_pnl": 0.0,
        "realized_pnl": 0.0,
        "timestamp": None,
        "mode": "live",
    }
    
    if not live_state_path.exists():
        # Fall back to config capital
        cfg = load_app_config()
        trading = cfg.trading or {}
        default_response["live_capital"] = float(trading.get("live_capital", trading.get("paper_capital", 500000)))
        return JSONResponse(default_response)
    
    try:
        with live_state_path.open("r", encoding="utf-8") as f:
            live_state = json.load(f)
        return JSONResponse(live_state)
    except Exception as exc:
        import logging
        logger = logging.getLogger(__name__)
        logger.error("Failed to load live state: %s", exc)
        return JSONResponse(default_response)


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


def load_config_and_overrides(default_config_path: str | Path | None = None) -> tuple[dict, dict | None]:
    """
    Load base config and overrides consistently.
    
    Returns:
        Tuple of (config_dict, overrides_dict or None)
    """
    import yaml
    
    config_path = default_config_path or CONFIG_PATH
    
    # Load base config
    config = {}
    if Path(config_path).exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
        except Exception as exc:
            import logging
            logger = logging.getLogger(__name__)
            logger.error("Failed to load config from %s: %s", config_path, exc)
    
    # Load overrides
    overrides = None
    if LEARNED_OVERRIDES_PATH.exists():
        try:
            with open(LEARNED_OVERRIDES_PATH, "r", encoding="utf-8") as f:
                overrides = yaml.safe_load(f) or {}
        except Exception as exc:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("Failed to load overrides from %s: %s", LEARNED_OVERRIDES_PATH, exc)
    
    return config, overrides


@router.get("/api/analytics/summary")
async def api_analytics_summary() -> JSONResponse:
    """
    Return complete analytics summary from runtime_metrics.json.
    
    Returns all metrics including equity, PnL, positions, and strategy/symbol breakdowns.
    Never crashes - returns default structure if file is missing or corrupted.
    """
    runtime_metrics_path = BASE_DIR / "artifacts" / "analytics" / "runtime_metrics.json"
    
    # Default empty structure matching RuntimeMetricsTracker output
    default_response = {
        "asof": None,
        "mode": "paper",
        "equity": 0.0,
        "starting_capital": 0.0,
        "current_equity": 0.0,
        "realized_pnl": 0.0,
        "unrealized_pnl": 0.0,
        "daily_pnl": 0.0,
        "max_drawdown": 0.0,
        "max_equity": 0.0,
        "min_equity": 0.0,
        "open_positions_count": 0,
        "overall": {
            "total_trades": 0,
            "closed_trades": 0,
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
        "pnl_per_symbol": {},
        "pnl_per_strategy": {},
        "equity_curve": [],
    }
    
    if not runtime_metrics_path.exists():
        return JSONResponse(default_response)
    
    try:
        with runtime_metrics_path.open("r", encoding="utf-8") as f:
            metrics = json.load(f)
        return JSONResponse(metrics)
    except Exception as exc:
        import logging
        logger = logging.getLogger(__name__)
        logger.error("Failed to load analytics summary: %s", exc)
        return JSONResponse(default_response)


@router.get("/api/analytics/equity_curve")
async def api_analytics_equity_curve() -> JSONResponse:
    """
    Return equity curve data from runtime_metrics.json.
    
    Returns list of equity snapshots for charting.
    Never crashes - returns empty list if file is missing or corrupted.
    """
    runtime_metrics_path = BASE_DIR / "artifacts" / "analytics" / "runtime_metrics.json"
    
    if not runtime_metrics_path.exists():
        return JSONResponse({"equity_curve": []})
    
    try:
        with runtime_metrics_path.open("r", encoding="utf-8") as f:
            metrics = json.load(f)
        
        equity_curve = metrics.get("equity_curve", [])
        return JSONResponse({"equity_curve": equity_curve})
    except Exception as exc:
        import logging
        logger = logging.getLogger(__name__)
        logger.error("Failed to load equity curve: %s", exc)
        return JSONResponse({"equity_curve": []})


@router.get("/api/risk/limits")
async def get_risk_limits() -> JSONResponse:
    """
    Return normalized risk limits for current mode (paper/live).
    
    Returns all configured risk limits from config + overrides.
    """
    try:
        config, overrides = load_config_and_overrides(default_config_path=str(CONFIG_PATH))
        limits = load_risk_limits(config, overrides)
        return JSONResponse(limits)
    except Exception as exc:
        import logging
        logger = logging.getLogger(__name__)
        logger.error("Failed to load risk limits: %s", exc)
        return JSONResponse({
            "mode": "paper",
            "capital": 0.0,
            "limits": {},
            "source": {},
            "error": str(exc),
        })


@router.get("/api/risk/breaches")
async def get_risk_breaches() -> JSONResponse:
    """
    Return current risk breaches, derived from runtime_metrics + checkpoint + config.
    
    Evaluates current trading state against risk limits and returns violations.
    """
    try:
        config, overrides = load_config_and_overrides(default_config_path=str(CONFIG_PATH))
        
        mode = config.get("trading", {}).get("mode", "paper")
        
        runtime_metrics_path = BASE_DIR / "artifacts" / "analytics" / "runtime_metrics.json"
        paper_checkpoint = BASE_DIR / "artifacts" / "checkpoints" / "paper_state_latest.json"
        live_checkpoint = BASE_DIR / "artifacts" / "checkpoints" / "live_state_latest.json"
        checkpoint_path = paper_checkpoint
        
        # Prefer live checkpoint when in live mode
        if mode == "live" and live_checkpoint.exists():
            checkpoint_path = live_checkpoint
        elif not paper_checkpoint.exists():
            checkpoint_path = BASE_DIR / "artifacts" / "checkpoints" / "runtime_state_latest.json"
        
        orders_path = BASE_DIR / "artifacts" / "orders.csv"
        
        result = compute_risk_breaches(
            config=config,
            runtime_metrics_path=runtime_metrics_path,
            checkpoint_path=checkpoint_path,
            orders_path=orders_path,
            mode=mode,
        )
        return JSONResponse(result)
    except Exception as exc:
        import logging
        logger = logging.getLogger(__name__)
        logger.error("Failed to compute risk breaches: %s", exc)
        from datetime import datetime
        return JSONResponse({
            "mode": "paper",
            "asof": datetime.now().isoformat(),
            "breaches": [],
            "error": str(exc),
        })


@router.get("/api/risk/var")
async def get_risk_var(confidence: float = 0.95) -> JSONResponse:
    """
    Return simple VaR estimate based on historical trades.
    
    Args:
        confidence: Confidence level for VaR calculation (default 0.95 = 95%)
    """
    try:
        # Validate confidence parameter
        if not (0.5 <= confidence <= 0.99):
            confidence = 0.95
        
        config, overrides = load_config_and_overrides(default_config_path=str(CONFIG_PATH))
        capital = float(config.get("trading", {}).get("paper_capital", 500000))
        orders_path = BASE_DIR / "artifacts" / "orders.csv"
        mode = config.get("trading", {}).get("mode", "paper")
        
        result = compute_var(
            orders_path=orders_path,
            capital=capital,
            confidence=confidence,
            mode=mode,
        )
        return JSONResponse(result)
    except Exception as exc:
        import logging
        logger = logging.getLogger(__name__)
        logger.error("Failed to compute VaR: %s", exc)
        return JSONResponse({
            "mode": "paper",
            "confidence": confidence,
            "var_rupees": 0.0,
            "var_pct": 0.0,
            "sample_trades": 0,
            "status": "error",
            "error": str(exc),
        })


@router.get("/api/benchmarks")
async def get_benchmarks(days: int = 1) -> JSONResponse:
    """
    Return benchmark time-series for NIFTY / BANKNIFTY / FINNIFTY
    for the last `days` days.
    
    Args:
        days: Number of days to look back (default: 1, max: 10)
        
    Returns:
        Array of benchmark objects with ts, nifty, banknifty, finnifty fields
    """
    try:
        records = load_benchmarks(days=days)
        return JSONResponse(records)
    except Exception:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception("Failed to load benchmarks")
        # Return empty list instead of crashing
        return JSONResponse([])


@router.get("/api/diagnostics/strategy")
async def get_strategy_diagnostics(symbol: str, strategy: str, limit: int = 200) -> JSONResponse:
    """
    Return real-time diagnostics for a specific symbol/strategy combination.
    
    This endpoint provides visibility into WHY a strategy is giving BUY/SELL/HOLD
    decisions, including indicator values, confidence scores, and risk blocks.
    
    Args:
        symbol: Trading symbol (e.g., "NIFTY", "BANKNIFTY", "RELIANCE")
        strategy: Strategy identifier (e.g., "EMA_20_50", "FNO_TREND")
        limit: Maximum number of records to return (default: 200, max: 1000)
    
    Returns:
        {
          "symbol": str,
          "strategy": str,
          "data": [
            {
              "ts": ISO timestamp,
              "price": float,
              "ema20": float | null,
              "ema50": float | null,
              "trend_strength": float | null,
              "confidence": float,
              "rr": float | null,
              "regime": str | null,
              "risk_block": str,
              "decision": "BUY"|"SELL"|"HOLD",
              "reason": str
            },
            ...
          ]
        }
    
    Example:
        GET /api/diagnostics/strategy?symbol=NIFTY&strategy=EMA_20_50&limit=200
    """
    try:
        # Validate and clamp limit
        limit = max(1, min(limit, 1000))
        
        # Load diagnostics
        result = load_diagnostics(symbol, strategy, limit)
        
        return JSONResponse({
            "symbol": symbol,
            "strategy": strategy,
            "data": result,
            "count": len(result),
        })
        
    except Exception as exc:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception("Failed to load strategy diagnostics for %s/%s", symbol, strategy)
        
        return JSONResponse({
            "symbol": symbol,
            "strategy": strategy,
            "data": [],
            "count": 0,
            "error": str(exc),
        })


@router.post("/api/risk/limits")
async def update_risk_limits(payload: dict) -> JSONResponse:
    """
    Update risk limits via overrides file.
    
    Writes allowed risk limit updates to configs/learned_overrides.yaml.
    
    Args:
        payload: Dict with risk limit updates (e.g., {"max_daily_loss_rupees": 6000.0})
    """
    import yaml
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        # Define allowed fields for updates
        allowed_fields = {
            "max_daily_loss_rupees": ("execution", "circuit_breakers"),
            "max_daily_drawdown_pct": ("execution", "circuit_breakers"),
            "max_trades_per_day": ("execution", "circuit_breakers"),
            "max_trades_per_strategy_per_day": ("execution", "circuit_breakers"),
            "max_loss_streak": ("execution", "circuit_breakers"),
            "max_exposure_pct": ("portfolio",),
            "max_leverage": ("portfolio",),
            "max_risk_per_trade_pct": ("portfolio",),
            "per_symbol_max_loss": ("trading",),
            "max_open_positions": ("trading",),
        }
        
        # Validate payload
        updates = {}
        for key, value in payload.items():
            if key not in allowed_fields:
                logger.warning("Ignoring invalid field in risk limit update: %s", key)
                continue
            
            # Type validation
            if key == "max_open_positions" and value is not None:
                try:
                    value = int(value)
                except (ValueError, TypeError):
                    return JSONResponse({
                        "status": "error",
                        "message": f"Invalid type for {key}: expected integer or null",
                    }, status_code=400)
            elif key in ["max_trades_per_day", "max_trades_per_strategy_per_day", "max_loss_streak"]:
                try:
                    value = int(value)
                    if value <= 0:
                        return JSONResponse({
                            "status": "error",
                            "message": f"Invalid value for {key}: must be positive",
                        }, status_code=400)
                except (ValueError, TypeError):
                    return JSONResponse({
                        "status": "error",
                        "message": f"Invalid type for {key}: expected positive integer",
                    }, status_code=400)
            else:
                try:
                    value = float(value)
                    if value < 0:
                        return JSONResponse({
                            "status": "error",
                            "message": f"Invalid value for {key}: must be non-negative",
                        }, status_code=400)
                except (ValueError, TypeError):
                    return JSONResponse({
                        "status": "error",
                        "message": f"Invalid type for {key}: expected number",
                    }, status_code=400)
            
            updates[key] = value
        
        if not updates:
            return JSONResponse({
                "status": "error",
                "message": "No valid fields to update",
            }, status_code=400)
        
        # Load existing overrides
        overrides = {}
        if LEARNED_OVERRIDES_PATH.exists():
            try:
                with open(LEARNED_OVERRIDES_PATH, "r", encoding="utf-8") as f:
                    overrides = yaml.safe_load(f) or {}
            except Exception as exc:
                logger.warning("Failed to load existing overrides: %s", exc)
        
        # Apply updates to overrides structure
        for key, value in updates.items():
            path = allowed_fields[key]
            
            # Navigate to the nested dict location
            current = overrides
            for section in path[:-1]:
                if section not in current:
                    current[section] = {}
                current = current[section]
            
            # Set the value at the final location
            if len(path) == 1:
                # Top-level section
                if path[0] not in overrides:
                    overrides[path[0]] = {}
                overrides[path[0]][key] = value
            else:
                # Nested section
                final_section = path[-1]
                if final_section not in current:
                    current[final_section] = {}
                current[final_section][key] = value
        
        # Write overrides back to file
        try:
            with open(LEARNED_OVERRIDES_PATH, "w", encoding="utf-8") as f:
                yaml.safe_dump(overrides, f, default_flow_style=False, sort_keys=False)
            logger.info("Updated risk limits in overrides file: %s", updates)
        except Exception as exc:
            logger.error("Failed to write overrides file: %s", exc)
            return JSONResponse({
                "status": "error",
                "message": f"Failed to save updates: {exc}",
            }, status_code=500)
        
        # Reload config and return updated limits
        config, new_overrides = load_config_and_overrides(default_config_path=str(CONFIG_PATH))
        limits = load_risk_limits(config, new_overrides)
        
        return JSONResponse({
            "status": "ok",
            "limits": limits,
            "updated_fields": list(updates.keys()),
        })
        
    except Exception as exc:
        logger.error("Failed to update risk limits: %s", exc)
        return JSONResponse({
            "status": "error",
            "message": str(exc),
        }, status_code=500)


def load_engine_telemetry() -> dict:
    """
    Load telemetry for all engines from artifacts/telemetry/*_engine.json.
    
    Returns:
        {
          "asof": "...",
          "engines": [ ... ]
        }
    """
    telemetry_dir = BASE_DIR / "artifacts" / "telemetry"
    telemetry_dir.mkdir(parents=True, exist_ok=True)
    engines = []
    for path in telemetry_dir.glob("*_engine.json"):
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
                engines.append(data)
        except Exception:
            logger = logging.getLogger(__name__)
            logger.exception("Failed to read engine telemetry from %s", path)
    return {
        "asof": dt.datetime.now().isoformat(),
        "engines": engines,
    }


@router.get("/api/telemetry/engines")
async def get_telemetry_engines():
    """
    Aggregate engine telemetry for dashboard.
    
    Returns health status for all running engine processes (fno, equity, options).
    """
    try:
        return load_engine_telemetry()
    except Exception:
        logger = logging.getLogger(__name__)
        logger.exception("Failed to load engine telemetry")
        return {"asof": dt.datetime.now().isoformat(), "engines": []}


@router.get("/api/telemetry/engine_logs")
async def get_engine_logs(engine: str, lines: int = 200):
    """
    (Optional stub)
    In future, return last N lines from engine-specific log file.
    For now, just return {"engine": engine, "lines": []}.
    """
    return {"engine": engine, "lines": []}


@router.get("/api/analytics/summary")
async def get_analytics_summary() -> JSONResponse:
    """
    Return analytics summary from runtime_metrics.json.
    
    This endpoint provides comprehensive performance analytics including:
    - Current equity and PnL (realized and unrealized)
    - Per-symbol PnL breakdown
    - Per-strategy PnL breakdown
    - Equity curve (short rolling window)
    - Max drawdown and equity statistics
    
    Never crashes - returns sensible defaults if data unavailable.
    """
    try:
        from analytics.runtime_metrics import load_runtime_metrics
        
        # Load metrics with safe loader
        metrics = load_runtime_metrics()
        
        return JSONResponse(metrics)
        
    except Exception as exc:
        import logging
        logger = logging.getLogger(__name__)
        logger.error("Failed to load analytics summary: %s", exc)
        
        # Return default structure on error
        return JSONResponse({
            "asof": datetime.now().isoformat(),
            "mode": "paper",
            "starting_capital": 0.0,
            "current_equity": 0.0,
            "realized_pnl": 0.0,
            "unrealized_pnl": 0.0,
            "daily_pnl": 0.0,
            "max_equity": 0.0,
            "min_equity": 0.0,
            "max_drawdown": 0.0,
            "pnl_per_symbol": {},
            "pnl_per_strategy": {},
            "equity_curve": [],
            "error": str(exc),
        })


@router.get("/api/analytics/equity_curve")
async def get_equity_curve(max_rows: Optional[int] = 500) -> JSONResponse:
    """
    Return equity curve from snapshots.csv.
    
    This endpoint provides the historical equity curve with timestamp,
    equity, realized_pnl, and unrealized_pnl for each snapshot.
    
    Args:
        max_rows: Maximum number of rows to return (default: 500)
    
    Returns:
        List of equity snapshots in chronological order
        
    Never crashes - returns empty list if data unavailable.
    """
    try:
        from analytics.equity_curve import load_equity_curve
        
        # Validate and clamp max_rows
        if max_rows is not None:
            max_rows = max(1, min(max_rows, 10000))
        
        # Load equity curve with safe loader
        curve = load_equity_curve(max_rows=max_rows)
        
        return JSONResponse({
            "data": curve,
            "count": len(curve),
        })
        
    except Exception as exc:
        import logging
        logger = logging.getLogger(__name__)
        logger.error("Failed to load equity curve: %s", exc)
        
        # Return empty structure on error
        return JSONResponse({
            "data": [],
            "count": 0,
            "error": str(exc),
        })


router.include_router(dashboard_module.router)
router.include_router(dashboard_logs.router)

app = FastAPI(title="Dashboard")
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.include_router(router)
app.include_router(api_strategies.router, prefix="/api/strategies", tags=["strategies"])

__all__ = ["router", "app"]
