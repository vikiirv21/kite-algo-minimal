from __future__ import annotations

import csv
import json
import asyncio
import logging
import os
import re
import threading
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Iterable
from zoneinfo import ZoneInfo
from dataclasses import dataclass
from datetime import datetime, date, time as dtime, timezone, timedelta  # keep alias dtime

from kiteconnect import KiteConnect, exceptions as kite_exceptions
from fastapi import APIRouter, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from analytics.strategy_performance import (
    load_strategy_performance,
    aggregate_by_strategy,
)
from analytics.telemetry_bus import get_telemetry_bus
from analytics.benchmarks import get_benchmarks
from analytics.risk_service import (
    load_risk_limits,
    save_risk_limits,
    compute_breaches,
    compute_var,
)
from broker.live_broker import LiveBroker
from core.config import AppConfig, load_config
from core.history_loader import _resolve_instrument_token  # type: ignore import
from core.runtime_mode import get_mode
from core.market_session import now_ist, is_market_open
from core.state_store import JournalStateStore, store
from core.strategy_registry import STRATEGY_REGISTRY
from core.json_log import ENGINE_LOG_PATH
from core.signal_quality import signal_quality_manager
from core.trade_monitor import trade_monitor
from core.trade_throttler import latest_throttler_summary
from core.universe import fno_underlyings, load_equity_universe
from core.universe_builder import load_universe as load_cached_universe
from data.instruments import resolve_fno_symbols
from engine.bootstrap import bootstrap_state

try:
    from analytics.trade_recorder import TradeRecorder
except Exception:  # noqa: BLE001
    TradeRecorder = None

# ---- loggers must exist before any function defaults use them ----
logger = logging.getLogger("ui.dashboard")
logger.setLevel(logging.INFO)

# Bridge to our file-based auth in core/kite_env
from core.kite_env import (
    make_kite_client_from_files,
    read_tokens,
    read_api_creds,
    describe_creds_for_logs,
    BASE_DIR as KE_BASE,
    SECRETS_DIR as KE_SECRETS_DIR,
    API_FILE as KE_API_FILE,
    TOK_FILE as KE_TOK_FILE,
)

# --- shim functions expected by this module (use our file-based impls) ---
def read_kite_api_secrets() -> dict:
    """Return {'KITE_API_KEY': ..., 'KITE_API_SECRET': ...} from /secrets/kite.env."""
    api_key, api_secret = read_api_creds()
    return {"KITE_API_KEY": api_key, "KITE_API_SECRET": api_secret}

def read_kite_token() -> str | None:
    """Return access token from /secrets/kite_tokens.env (or None)."""
    access_token, *_ = read_tokens()
    return access_token

def make_kite_client_from_env(reload: bool = False):
    """Compatibility alias: create Kite client from files."""
    return make_kite_client_from_files()

def token_is_valid(kite) -> bool:
    """Lightweight validity check using profile(), with diagnostics."""
    try:
        prof = kite.profile()
        logger.info("Kite profile OK: user_id=%s", (prof or {}).get("user_id"))
        return True
    except kite_exceptions.TokenException as e:
        logger.error("Kite token invalid: %s", getattr(e, "message", repr(e)))
        return False
    except kite_exceptions.InputException as e:
        logger.error("Kite input exception: %s", getattr(e, "message", repr(e)))
        return False
    except Exception as e:
        logger.error("Kite profile() failed: %r", e, exc_info=True)
        return False

def print_loaded_paths(log: Optional[logging.Logger] = None) -> None:
    """Pretty log of where we read creds/tokens from."""
    _log = log or logger
    try:
        _log.info("Auth paths: BASE_DIR=%s SECRETS_DIR=%s", KE_BASE, KE_SECRETS_DIR)
        _log.info("Auth files: API_FILE=%s TOK_FILE=%s", KE_API_FILE, KE_TOK_FILE)
        _log.info(describe_creds_for_logs())
    except Exception:
        pass

# --- paths / config ---
BASE_DIR = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = BASE_DIR / "ui" / "templates"
DEFAULT_ARTIFACTS = BASE_DIR / "artifacts"
ARTIFACTS_ROOT = Path(os.environ.get("KITE_ALGO_ARTIFACTS", str(DEFAULT_ARTIFACTS))).expanduser()
if not ARTIFACTS_ROOT.is_absolute():
    ARTIFACTS_ROOT = (BASE_DIR / ARTIFACTS_ROOT).resolve()
CHECKPOINTS_DIR = ARTIFACTS_ROOT / "checkpoints"
PAPER_CHECKPOINT_PATH = CHECKPOINTS_DIR / "paper_state_latest.json"
BACKTESTS_ROOT = ARTIFACTS_ROOT / "backtests"
DEFAULT_CONFIG_PATH = BASE_DIR / "configs" / "dev.yaml"
CONFIG_PATH = Path(os.environ.get("HFT_CONFIG", os.environ.get("KITE_DASHBOARD_CONFIG", str(DEFAULT_CONFIG_PATH))))
SIGNALS_PATH = ARTIFACTS_ROOT / "signals.csv"
QUOTES_PATH  = ARTIFACTS_ROOT / "live_quotes.json"  # optional cache (another process may write)
SNAPSHOTS_PATH = ARTIFACTS_ROOT / "snapshots.csv"
LOG_CATEGORY_PATTERNS: Dict[str, Tuple[str, ...]] = {
    "engine": (
        "engine",
        "paperengine",
        "runbook",
        "meta_engine",
    ),
    "trades": (
        "trade",
        "broker",
        "order",
        "execution",
        "fill",
        "throttler",
    ),
    "signals": (
        "signal",
        "strategy",
        "indicator",
        "alpha",
    ),
}


def _resolve_checkpoint_path() -> Optional[Path]:
    """
    Pick the most recent checkpoint file from a list of known candidates.

    This allows the dashboard to work whether the engine writes to:
      - artifacts/checkpoints/paper_state_latest.json  (new JournalStateStore)
      - artifacts/checkpoints/paper_state.json        (alt)
      - artifacts/paper_state_latest.json             (flat)
      - artifacts/paper_state.json                    (legacy)
    """
    candidates: List[Path] = [
        PAPER_CHECKPOINT_PATH,
        CHECKPOINTS_DIR / "paper_state.json",
        ARTIFACTS_ROOT / "paper_state_latest.json",
        ARTIFACTS_ROOT / "paper_state.json",
    ]
    existing: List[Tuple[float, Path]] = []
    for path in candidates:
        try:
            if path.exists():
                mtime = path.stat().st_mtime
                existing.append((mtime, path))
        except Exception:
            continue

    if not existing:
        return None

    # Return the newest one
    existing.sort(key=lambda t: t[0])
    return existing[-1][1]

def _resolve_orders_path() -> Path:
    if TradeRecorder is not None:
        try:
            tmp = TradeRecorder()
            for attr in ("orders_path", "orders_csv_path", "orders_file", "orders_csv"):
                candidate = getattr(tmp, attr, None)
                if candidate:
                    return Path(candidate)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Unable to derive orders path from TradeRecorder: %s", exc)
    return ARTIFACTS_ROOT / "orders.csv"

ORDERS_PATH = _resolve_orders_path()

_CONFIG_CACHE: Optional[AppConfig] = None
LOT_SIZES = {"NIFTY": 25, "BANKNIFTY": 15, "FINNIFTY": 40}
_LOG_DIR_CACHE: Optional[Path] = None
_LOG_PREFIX_CACHE: Optional[str] = None

IST_TZ = timezone(timedelta(hours=5, minutes=30))
LOG_LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}[^[]*?)\s*\[(?P<level>[A-Z]+)\]\s*(?P<logger>[^-]+)-\s*(?P<message>.*)$"
)
EVENT_KIND_RE = re.compile(r"^\[KIND:(?P<kind>[A-Z_]+)\]\s*(?P<body>.*)$")
LOGS_DIR = ARTIFACTS_ROOT / "logs"
DEFAULT_LOG_FILE = LOGS_DIR / "app.log"
IST_ZONE = ZoneInfo("Asia/Kolkata")

app = FastAPI(title="Arthayukti Dashboard")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add middleware for static file caching
@app.middleware("http")
async def add_cache_headers(request: Request, call_next):
    response = await call_next(request)
    # Cache static assets for 1 hour
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "public, max-age=3600"
        response.headers["X-Content-Type-Options"] = "nosniff"
    return response

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
STATIC_DIR = BASE_DIR / "ui" / "static"



def _resolve_dashboard_template_name() -> Optional[str]:
    """
    Pick the dashboard template to use (dashboard.html preferred, index.html fallback).
    """
    dashboard = TEMPLATES_DIR / "dashboard.html"
    index = TEMPLATES_DIR / "index.html"
    if dashboard.exists():
        return "dashboard.html"
    if index.exists():
        return "index.html"
    return None


DASHBOARD_TEMPLATE_NAME = _resolve_dashboard_template_name()
REACT_BUILD_DIR = BASE_DIR / "ui" / "static-react"

# Debug logging for React build directory
print("[dashboard] REACT_BUILD_DIR:", REACT_BUILD_DIR)
print("[dashboard] index.html exists:", (REACT_BUILD_DIR / "index.html").exists())
assets_dir = REACT_BUILD_DIR / "assets"
print("[dashboard] assets dir exists:", assets_dir.exists())
if assets_dir.exists():
    print("[dashboard] sample assets:", list(assets_dir.iterdir())[:5])


# NOTE: The root path ("/") is now served by StaticFiles mount below (see bottom of file)
# This route is commented out to avoid conflicts with React SPA routing
# @app.get("/", response_class=HTMLResponse)
# async def index(request: Request) -> HTMLResponse:
#     """Render the main Arthayukti dashboard (React SPA)"""
#     try:
#         # Serve the React app's index.html
#         react_index = REACT_BUILD_DIR / "index.html"
#         if react_index.exists():
#             return HTMLResponse(content=react_index.read_text(encoding="utf-8"))
#         else:
#             # Fallback to old dashboard if React build doesn't exist
#             logger.warning("React build not found at %s, falling back to old dashboard", REACT_BUILD_DIR)
#             return templates.TemplateResponse("dashboard.html", {
#                 "request": request,
#             })
#     except Exception as exc:
#         logger.error("Failed to render dashboard: %s", exc)
#         raise HTTPException(status_code=500, detail=str(exc)) from exc

# NOTE: This route is for the old Jinja/HTMX dashboard and is now disabled
# since we're using React SPA exclusively. Keeping it would interfere with
# React Router by catching paths like /signals, /risk, etc.
# @app.get("/pages/{page_name}", response_class=HTMLResponse)
# async def get_page(request: Request, page_name: str) -> HTMLResponse:
#     """Serve individual page templates for HTMX loading"""
#     valid_pages = [
#         "overview", "portfolio", "engines", "strategies", 
#         "orders", "signals", "pnl_analytics", "logs", 
#         "trade_flow", "system_health"
#     ]
#     
#     if page_name not in valid_pages:
#         raise HTTPException(status_code=404, detail="Page not found")
#     
#     try:
#         return templates.TemplateResponse(f"pages/{page_name}.html", {
#             "request": request,
#         })
#     except Exception as exc:
#         logger.error("Failed to render page %s: %s", page_name, exc)
#         raise HTTPException(status_code=500, detail=str(exc)) from exc

def load_app_config() -> AppConfig:
    global _CONFIG_CACHE  # noqa: PLW0603
    if _CONFIG_CACHE is None:
        _CONFIG_CACHE = load_config(str(CONFIG_PATH))
    return _CONFIG_CACHE


def _load_dashboard_config() -> AppConfig:
    """Backwards-compatible alias used elsewhere in this module."""
    return load_app_config()


def summarize_config(cfg: AppConfig) -> Dict[str, Any]:
    """
    Produce a compact summary of trading/risk settings for the dashboard.
    """
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
    # Handle max_positions: null means unlimited
    max_positions_raw = trading.get("max_open_positions") or trading.get("max_positions") or risk.get("max_positions")
    if max_positions_raw is None:
        max_positions = None
    else:
        max_positions = int(max_positions_raw) if max_positions_raw else 5

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
        "max_positions": max_positions,
        "risk_profile": risk_profile,
        "meta_enabled": meta_enabled,
    }


def _coerce_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool): return value
    if value is None: return None
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"1","true","yes","on"}: return True
        if v in {"0","false","no","off"}: return False
    return None

def _load_state() -> Dict[str, Any]:
    path = _state_path()
    if not path.exists():
        raise FileNotFoundError(f"{path} not found")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def _load_signals(limit: int = 150) -> List[Dict[str, Any]]:
    if not SIGNALS_PATH.exists(): return []
    rows: List[Dict[str, Any]] = []
    with SIGNALS_PATH.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f): rows.append(row)
    if limit > 0 and len(rows) > limit: rows = rows[-limit:]
    return rows

def _load_orders_from_csv(limit: int = 150) -> List[Dict[str, Any]]:
    if not ORDERS_PATH.exists(): return []
    rows: List[Dict[str, Any]] = []
    with ORDERS_PATH.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f): rows.append(row)
    if limit > 0 and len(rows) > limit: rows = rows[-limit:]
    return rows


def tail_file(path: Path, limit: int = 200) -> List[str]:
    """
    Return up to the last `limit` non-empty lines from a log file.
    """
    try:
        if not path or not path.exists():
            return []
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            lines = [line.rstrip("\n") for line in handle.readlines()]
        lines = [ln for ln in lines if ln.strip()]
        if not lines:
            return []
        return lines[-limit:]
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to tail log file %s: %s", path, exc)
        return []


def parse_log_lines(lines: List[str]) -> List[Dict[str, str]]:
    """
    Parse log lines of the form 'ts [LEVEL] logger - message'.
    """
    parsed: List[Dict[str, str]] = []
    for raw in lines:
        if not raw:
            continue
        ts = ""
        level = ""
        logger_name = ""
        message = raw
        prefix = raw
        try:
            prefix, message = raw.split(" - ", 1)
            message = message.strip()
        except ValueError:
            message = raw

        try:
            parts = prefix.split("[", 1)
            if len(parts) == 2:
                ts_part, rest = parts
                ts = ts_part.strip()
                level_part, *logger_parts = rest.split("]", 1)
                level = level_part.strip()
                if logger_parts:
                    logger_name = logger_parts[0].strip()
            else:
                logger_name = prefix.strip()
        except Exception:
            logger_name = prefix.strip()

        parsed.append(
            {
                "ts": ts,
                "level": level,
                "logger": logger_name,
                "message": message,
            }
        )
    return parsed


def _normalize_log_entries(entries: List[Dict[str, str]]) -> List[Dict[str, str]]:
    normalized: List[Dict[str, str]] = []
    for entry in entries:
        timestamp = entry.get("timestamp") or entry.get("ts") or ""
        level = (entry.get("level") or "INFO").upper()
        source = entry.get("logger") or entry.get("source") or ""
        message = entry.get("message") or entry.get("raw") or ""
        normalized.append(
            {
                "timestamp": timestamp,
                "level": level,
                "source": source,
                "message": message,
            }
        )
    return normalized


def derive_log_health(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Provide basic error/warning counts from parsed log entries.
    """
    if not entries:
        return {
            "last_log_ts": None,
            "last_error_ts": None,
            "error_count_recent": 0,
            "warning_count_recent": 0,
        }
    last_entry = entries[-1]
    last_log_ts = last_entry.get("timestamp") or last_entry.get("ts") or None
    last_error_ts = None
    error_count = 0
    warning_count = 0
    for entry in entries:
        level = (entry.get("level") or "").upper()
        if level == "ERROR":
            error_count += 1
            ts = entry.get("timestamp") or entry.get("ts") or None
            last_error_ts = ts or last_error_ts
        elif level == "WARNING":
            warning_count += 1
    return {
        "last_log_ts": last_log_ts,
        "last_error_ts": last_error_ts,
        "error_count_recent": error_count,
        "warning_count_recent": warning_count,
    }


def compute_market_status(now_utc: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Determine basic market status relative to IST trading hours.
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    now_ist = now_utc.astimezone(IST_ZONE)
    open_time = now_ist.replace(hour=9, minute=0, second=0, microsecond=0)
    close_time = now_ist.replace(hour=15, minute=30, second=0, microsecond=0)
    if now_ist < open_time:
        status = "PRE_OPEN"
        seconds_to_open = int((open_time - now_ist).total_seconds())
        seconds_to_close = None
    elif open_time <= now_ist < close_time:
        status = "OPEN"
        seconds_to_open = 0
        seconds_to_close = int((close_time - now_ist).total_seconds())
    else:
        status = "CLOSED"
        seconds_to_open = None
        seconds_to_close = 0
    return {
        "now_ist": now_ist.isoformat(),
        "status": status,
        "seconds_to_open": seconds_to_open,
        "seconds_to_close": seconds_to_close,
    }


def load_recent_signals(limit: int = 50) -> List[Dict[str, Any]]:
    """
    Return up to `limit` most recent signals from signals.csv.
    """
    if not SIGNALS_PATH.exists():
        logger.warning("Signals file missing at %s", SIGNALS_PATH)
        return []

    rows: List[Dict[str, Any]] = []
    try:
        with SIGNALS_PATH.open("r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                if isinstance(row, dict):
                    rows.append(row)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to read signals CSV: %s", exc)
        return []

    if not rows:
        return []

    rows = rows[-limit:]

    normalized: List[Dict[str, Any]] = []
    for entry in rows:
        ts = (entry.get("ts") or entry.get("timestamp") or "").strip()
        symbol = (entry.get("symbol") or "").strip()
        logical = (entry.get("logical") or "").strip()
        signal = (entry.get("signal") or "").strip().upper()
        tf = (entry.get("tf") or entry.get("timeframe") or "").strip()
        price_raw = entry.get("price") or entry.get("close") or ""
        profile = (entry.get("profile") or "").strip()
        strategy = (entry.get("strategy") or "").strip()

        try:
            price = float(price_raw) if price_raw not in ("", None) else None
        except (TypeError, ValueError):
            price = None

        normalized.append(
            {
                "ts": ts,
                "symbol": symbol,
                "logical": logical,
                "signal": signal,
                "tf": tf,
                "price": price,
                "profile": profile,
                "strategy": strategy,
            }
        )

    return normalized


def load_strategy_stats_from_signals(limit_days: int = 1) -> List[Dict[str, Any]]:
    """
    Aggregate strategy statistics from the signals CSV.

    - Groups by logical name (if present) or "SYMBOL|STRATEGY".
    - Adds quality metrics from signal_quality_manager where available.
    """
    if not SIGNALS_PATH.exists():
        return []

    aggregate: Dict[str, Dict[str, Any]] = {}
    now_utc = datetime.now(timezone.utc)

    try:
        with SIGNALS_PATH.open("r", encoding="utf-8", errors="ignore") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                ts_raw = row.get("timestamp") or row.get("ts") or ""
                if ts_raw:
                    try:
                        ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                        if limit_days > 0 and ts.tzinfo is not None:
                            age_days = (now_utc - ts.astimezone(timezone.utc)).days
                            if age_days > (limit_days - 1):
                                continue
                    except Exception:
                        # If timestamp is malformed, just keep the row
                        pass

                logical = (row.get("logical") or "").strip()
                strategy = (row.get("strategy") or "").strip()
                symbol = (row.get("symbol") or "").strip()
                key = logical or f"{symbol}|{strategy}".strip("|")
                if not key:
                    continue

                sig = (row.get("signal") or "").strip().upper()
                price_raw = row.get("price")
                tf = (row.get("tf") or row.get("timeframe") or "").strip()
                mode = (row.get("mode") or "").strip()

                stats = aggregate.get(key)
                if stats is None:
                    last_price = None
                    if price_raw not in (None, ""):
                        try:
                            last_price = float(price_raw)
                        except ValueError:
                            last_price = None

                    stats = {
                        "key": key,
                        "logical": logical or key,
                        "symbol": symbol,
                        "strategy": strategy or "",
                        "last_ts": ts_raw,
                        "last_signal": sig,
                        "last_price": last_price,
                        "timeframe": tf,
                        "buy_count": 0,
                        "sell_count": 0,
                        "exit_count": 0,
                        "hold_count": 0,
                        "mode": mode,
                    }
                    aggregate[key] = stats

                # Update counters
                if sig == "BUY":
                    stats["buy_count"] += 1
                elif sig == "SELL":
                    stats["sell_count"] += 1
                elif sig == "EXIT":
                    stats["exit_count"] += 1
                elif sig == "HOLD":
                    stats["hold_count"] += 1

                # Keep latest info
                if ts_raw:
                    stats["last_ts"] = ts_raw
                if price_raw not in (None, ""):
                    try:
                        stats["last_price"] = float(price_raw)
                    except ValueError:
                        pass
                if tf:
                    stats["timeframe"] = tf
                if mode:
                    stats["mode"] = mode
                if symbol:
                    stats["symbol"] = symbol
                if logical:
                    stats["logical"] = logical
                if strategy:
                    stats["strategy"] = strategy
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to load strategy stats from %s: %s", SIGNALS_PATH, exc)
        return []

    # Merge in quality metrics from signal_quality_manager
    quality_metrics = signal_quality_manager.strategy_metrics_snapshot()
    rows: List[Dict[str, Any]] = []
    for stats in aggregate.values():
        strategy = stats.get("strategy") or ""
        symbol = stats.get("symbol") or ""
        metrics = quality_metrics.get((strategy, symbol), {}) or {}
        stats["trades_today"] = metrics.get("trades_today", 0)
        stats["winrate_20"] = metrics.get("winrate_20", 0.0)
        stats["avg_r_20"] = metrics.get("avg_r_20", 0.0)
        stats["avg_signal_score"] = metrics.get("avg_signal_score", 0.0)
        stats["veto_count_today"] = metrics.get("veto_count_today", 0)
        rows.append(stats)

    return sorted(
        rows,
        key=lambda item: item.get("logical") or item.get("key") or "",
    )


def load_equity_curve(limit_days: int = 1, max_points: int = 200) -> List[Dict[str, Any]]:
    """
    Load equity snapshots for the requested lookback window.
    """
    if not SNAPSHOTS_PATH.exists():
        return []

    now = datetime.now(timezone.utc)
    snapshots: List[Dict[str, Any]] = []

    try:
        with SNAPSHOTS_PATH.open("r", encoding="utf-8", errors="ignore") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                ts_raw = row.get("timestamp") or row.get("ts")
                if not ts_raw:
                    continue
                try:
                    ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                except Exception:
                    continue

                age_days = (now - ts.astimezone(timezone.utc)).days
                if age_days > (limit_days - 1):
                    continue

                def _float(name: str, default: float = 0.0) -> float:
                    value = row.get(name)
                    if value in (None, "",):
                        return default
                    try:
                        return float(value)
                    except ValueError:
                        return default

                snapshots.append(
                    {
                        "ts": ts.isoformat(),
                        "equity": _float("equity"),
                        "paper_capital": _float("paper_capital"),
                        "realized": _float("total_realized_pnl"),
                        "unrealized": _float("total_unrealized_pnl"),
                    }
                )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to load equity curve from %s: %s", SNAPSHOTS_PATH, exc)
        return []

    if not snapshots:
        return []

    snapshots.sort(key=lambda item: item["ts"])
    count = len(snapshots)
    if count > max_points:
        step = max(1, count // max_points)
        snapshots = [snapshots[i] for i in range(0, count, step)]

    return snapshots


def _parse_login_timestamp(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    text = raw.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%d %H:%M:%S%z", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _compute_login_age_minutes(login_ts: Optional[str]) -> Optional[float]:
    ts = _parse_login_timestamp(login_ts)
    if ts is None:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    else:
        ts = ts.astimezone(timezone.utc)
    delta = datetime.now(timezone.utc) - ts
    return round(delta.total_seconds() / 60.0, 2)


def _read_token_snapshot() -> Dict[str, Any]:
    info = {
        "access_token": None,
        "login_ts": None,
        "login_age_minutes": None,
        "error": None,
    }
    try:
        access_token, _public_token, login_ts, _token_key = read_tokens()
    except Exception as exc:  # noqa: BLE001
        info["error"] = str(exc)
        return info

    info["access_token"] = access_token
    info["login_ts"] = login_ts
    info["login_age_minutes"] = _compute_login_age_minutes(login_ts)
    return info


def _kite_preflight_snapshot() -> Tuple[bool, Optional[str], Optional[str]]:
    try:
        kite = make_kite_client_from_files()
    except Exception as exc:  # noqa: BLE001
        return False, None, str(exc)

    try:
        profile = kite.profile()
        user_id = profile.get("user_id") or profile.get("USER_ID") or profile.get("userID")
        return True, user_id, None
    except kite_exceptions.TokenException as exc:
        return False, None, str(exc)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Kite preflight failed: %s", exc, exc_info=True)
        return False, None, str(exc)


def _load_paper_engine_status() -> Dict[str, Any]:
    path = _resolve_checkpoint_path()
    base = {
        "engine": "fno_paper",
        "running": False,
        "last_checkpoint_ts": None,
        "checkpoint_age_seconds": None,
        "market_open": is_market_open(),
        "mode": "paper",
        "error": None,
        "checkpoint_path": str(path) if path else None,
    }

    if path is None or not path.exists():
        base["error"] = "checkpoint_missing"
        return base

    checkpoint_dt: Optional[datetime] = None
    checkpoint_iso: Optional[str] = None
    age_seconds: Optional[float] = None
    payload: Any = None

    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Unable to read paper checkpoint at %s: %s", path, exc, exc_info=True)
        base["error"] = f"read_error: {exc}"

    raw_ts = None
    if isinstance(payload, dict):
        raw_ts = payload.get("timestamp") or payload.get("ts") or payload.get("updated_at")

    if raw_ts:
        checkpoint_dt = _parse_login_timestamp(str(raw_ts))

    if checkpoint_dt is None:
        try:
            checkpoint_dt = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        except Exception:  # noqa: BLE001
            checkpoint_dt = None

    if checkpoint_dt is not None:
        if checkpoint_dt.tzinfo is None:
            checkpoint_dt = checkpoint_dt.replace(tzinfo=timezone.utc)
        else:
            checkpoint_dt = checkpoint_dt.astimezone(timezone.utc)

        checkpoint_iso = checkpoint_dt.isoformat()
        now_utc = datetime.now(timezone.utc)
        age_seconds = (now_utc - checkpoint_dt).total_seconds()
    else:
        checkpoint_iso = None
        age_seconds = None

    running = bool(age_seconds is not None and age_seconds >= 0 and age_seconds < 180.0)

    base.update(
        {
            "running": running,
            "last_checkpoint_ts": checkpoint_iso,
            "checkpoint_age_seconds": round(age_seconds, 2) if age_seconds is not None else None,
        }
    )
    return base


def _default_portfolio_summary() -> Dict[str, Any]:
    return {
        "paper_capital": None,
        "total_realized_pnl": None,
        "total_unrealized_pnl": None,
        "equity": None,
        "total_notional": None,
        "free_notional": None,
        "exposure_pct": None,
        "daily_pnl": None,
        "has_positions": False,
        "position_count": 0,
        "note": "No data",
    }


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(fallback)


def _load_runtime_state_payload() -> Optional[Dict[str, Any]]:
    try:
        payload = store.load_checkpoint()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to load runtime checkpoint: %s", exc)
        return None
    return payload if isinstance(payload, dict) else None


def _list_backtest_runs() -> List[Dict[str, str]]:
    runs: List[Dict[str, str]] = []
    if not BACKTESTS_ROOT.exists():
        return runs
    for strategy_dir in sorted(BACKTESTS_ROOT.iterdir()):
        if not strategy_dir.is_dir():
            continue
        strategy = strategy_dir.name
        for run_dir in sorted(strategy_dir.iterdir(), reverse=True):
            if not run_dir.is_dir():
                continue
            result_path = run_dir / "result.json"
            if not result_path.is_file():
                continue
            runs.append(
                {
                    "strategy": strategy,
                    "run": run_dir.name,
                    "path": f"{strategy}/{run_dir.name}",
                }
            )
    return runs


def _load_backtest_result_payload(rel_path: str) -> Dict[str, Any]:
    if not rel_path:
        raise FileNotFoundError("missing path")
    candidate = Path(rel_path.strip().strip("/"))
    if candidate.is_absolute() or ".." in candidate.parts:
        raise FileNotFoundError("invalid path")
    target_dir = (BACKTESTS_ROOT / candidate).resolve()
    root = BACKTESTS_ROOT.resolve()
    if not str(target_dir).startswith(str(root)):
        raise FileNotFoundError("invalid path")
    result_file = target_dir / "result.json"
    if not result_file.is_file():
        raise FileNotFoundError("result not found")
    try:
        with result_file.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError as exc:  # noqa: BLE001
        logger.error("Invalid backtest result at %s: %s", result_file, exc)
        raise HTTPException(status_code=500, detail="Backtest result is invalid") from exc


def _default_today_summary(snapshot_date: date, note: str = "") -> Dict[str, Any]:
    return {
        "date": snapshot_date.isoformat(),
        "realized_pnl": 0.0,
        "num_trades": 0,
        "win_trades": 0,
        "loss_trades": 0,
        "win_rate": 0.0,
        "largest_win": 0.0,
        "largest_loss": 0.0,
        "avg_r": 0.0,
        "note": note,
    }


def load_paper_portfolio_summary() -> Dict[str, Any]:
    """
    Build the portfolio snapshot from the canonical runtime state checkpoint.
    """
    state = _load_runtime_state_payload()
    if not state:
        summary = _default_portfolio_summary()
        summary["note"] = "No runtime checkpoint"
        return summary

    equity = state.get("equity") or {}
    pnl = state.get("pnl") or {}
    paper_capital = _safe_float(equity.get("paper_capital"), 0.0)
    total_realized = _safe_float(equity.get("realized_pnl"), 0.0)
    total_unrealized = _safe_float(equity.get("unrealized_pnl"), 0.0)
    equity_value = _safe_float(
        equity.get("equity"),
        paper_capital + total_realized + total_unrealized,
    )
    total_notional = _safe_float(equity.get("total_notional"), 0.0)
    free_notional = _safe_float(
        equity.get("free_notional"),
        equity_value - total_notional,
    )
    exposure_pct = (total_notional / equity_value) if equity_value > 0 else None
    daily_pnl = _safe_float(pnl.get("day_pnl"), total_realized + total_unrealized)

    positions_data = state.get("positions") or []
    if isinstance(positions_data, dict):
        positions_list = list(positions_data.values())
    else:
        positions_list = list(positions_data)
    position_count = sum(
        1 for pos in positions_list if isinstance(pos, dict) and _safe_float(pos.get("quantity"), 0.0) != 0.0
    )

    # Get position limit from config
    cfg = load_app_config()
    trading = cfg.trading or {}
    risk = cfg.risk or {}
    max_positions_raw = trading.get("max_open_positions") or trading.get("max_positions") or risk.get("max_positions")
    position_limit = int(max_positions_raw) if max_positions_raw is not None else None
    
    # Calculate position_used_pct: 0.0 when unlimited (position_limit is None)
    if position_limit is None or position_limit == 0:
        position_used_pct = 0.0
    else:
        position_used_pct = (position_count / position_limit) * 100.0

    return {
        "paper_capital": paper_capital,
        "total_realized_pnl": total_realized,
        "total_unrealized_pnl": total_unrealized,
        "equity": equity_value,
        "total_notional": total_notional,
        "free_notional": free_notional,
        "exposure_pct": exposure_pct,
        "daily_pnl": daily_pnl,
        "has_positions": position_count > 0,
        "position_count": position_count,
        "position_limit": position_limit,
        "open_positions": position_count,
        "position_used_pct": position_used_pct,
        "note": "",
    }


def _parse_float(row: Dict[str, Any], *keys: str) -> float:
    for key in keys:
        val = row.get(key)
        if val in (None, "", "null"):
            continue
        try:
            return float(val)
        except (TypeError, ValueError):
            continue
    return 0.0


def _find_todays_orders_file(today: date) -> Optional[Path]:
    journal_path = ARTIFACTS_ROOT / "journal" / today.strftime("%Y-%m-%d") / "orders.csv"
    if journal_path.exists():
        return journal_path
    fallback = ARTIFACTS_ROOT / "orders.csv"
    return fallback if fallback.exists() else None


def compute_today_summary(today: Optional[date] = None) -> Dict[str, Any]:
    """
    Compute today's realized PnL and trade stats.

    Preference order:
    1. Canonical runtime checkpoint (state["summary"])
    2. Today's journal CSV (orders.csv)
    3. Fallback zeros
    """
    today = today or now_ist().date()
    state = _load_runtime_state_payload()
    if isinstance(state, dict):
        summary_state = state.get("summary")
        if isinstance(summary_state, dict):
            baseline = _default_today_summary(today)
            baseline.update(
                {
                    "date": summary_state.get("date") or baseline["date"],
                    "realized_pnl": _safe_float(summary_state.get("realized_pnl"), baseline["realized_pnl"]),
                    "num_trades": int(summary_state.get("num_trades") or 0),
                    "win_trades": int(summary_state.get("win_trades") or 0),
                    "loss_trades": int(summary_state.get("loss_trades") or 0),
                    "win_rate": float(summary_state.get("win_rate") or 0.0),
                    "largest_win": _safe_float(summary_state.get("largest_win"), 0.0),
                    "largest_loss": _safe_float(summary_state.get("largest_loss"), 0.0),
                    "avg_r": _safe_float(summary_state.get("avg_r"), 0.0),
                    "note": summary_state.get("note") or "",
                }
            )
            return baseline

    orders_path = _find_todays_orders_file(today)
    if not orders_path:
        return _default_today_summary(today, note="No journal for today")

    num_trades = 0
    win_trades = 0
    loss_trades = 0
    realized_pnl = 0.0
    largest_win = 0.0
    largest_loss = 0.0
    r_sum = 0.0
    r_count = 0

    try:
        with orders_path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                status = (row.get("status") or "").upper()
                side = (row.get("side") or "").upper()
                if status not in {"FILLED", "CLOSED", "COMPLETE"}:
                    continue
                if side not in {"BUY", "SELL"}:
                    continue

                num_trades += 1
                pnl = _parse_float(row, "pnl", "realized_pnl")
                realized_pnl += pnl
                largest_win = max(largest_win, pnl)
                largest_loss = min(largest_loss, pnl)

                if pnl > 0:
                    win_trades += 1
                elif pnl < 0:
                    loss_trades += 1

                r_multiple = _parse_float(row, "r_multiple", "r")
                if r_multiple != 0.0:
                    r_sum += r_multiple
                    r_count += 1
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to compute today summary from %s: %s", orders_path, exc)

    # Fallback to checkpoint realized PnL if we clearly traded but CSV has 0 PnL
    if num_trades and realized_pnl == 0.0:
        try:
            if PAPER_CHECKPOINT_PATH.exists():
                raw = PAPER_CHECKPOINT_PATH.read_text(encoding="utf-8")
                payload = json.loads(raw)
                meta = payload.get("meta") if isinstance(payload, dict) else {}
                fallback_realized = _safe_float(meta.get("total_realized_pnl"), 0.0)
                if fallback_realized != 0.0:
                    realized_pnl = fallback_realized
        except Exception:
            pass

    win_rate = (win_trades / num_trades * 100.0) if num_trades else 0.0
    avg_r = (r_sum / r_count) if r_count else 0.0

    summary = {
        "date": today.isoformat(),
        "realized_pnl": realized_pnl,
        "num_trades": num_trades,
        "win_trades": win_trades,
        "loss_trades": loss_trades,
        "win_rate": win_rate,
        "largest_win": largest_win,
        "largest_loss": largest_loss,
        "avg_r": avg_r,
    }

    quality_summary = signal_quality_manager.daily_summary()
    summary["total_trades_allowed"] = quality_summary.get("total_trades_allowed", 0)
    summary["total_trades_vetoed"] = quality_summary.get("total_trades_vetoed", 0)
    summary["avg_signal_score_executed"] = quality_summary.get("avg_signal_score_executed", 0.0)
    return summary


def _resolve_logs_dir() -> Path:
    global _LOG_DIR_CACHE  # noqa: PLW0603
    if _LOG_DIR_CACHE is not None:
        return _LOG_DIR_CACHE
    cfg = _load_dashboard_config()
    raw_dir = cfg.logging.get("directory", "logs")
    log_dir = Path(raw_dir).expanduser()
    if not log_dir.is_absolute():
        log_dir = (BASE_DIR / log_dir).resolve()
    _LOG_DIR_CACHE = log_dir
    return log_dir


def _resolve_log_prefix() -> str:
    global _LOG_PREFIX_CACHE  # noqa: PLW0603
    if _LOG_PREFIX_CACHE is not None:
        return _LOG_PREFIX_CACHE
    cfg = _load_dashboard_config()
    prefix = str(cfg.logging.get("file_prefix", "kite_algo"))
    _LOG_PREFIX_CACHE = prefix
    return prefix


def _latest_log_file() -> Optional[Path]:
    log_dir = _resolve_logs_dir()
    if not log_dir.exists():
        return None
    prefix = _resolve_log_prefix()
    candidates = sorted(log_dir.glob(f"{prefix}_*.log"))
    if not candidates:
        return None
    return candidates[-1]


def _split_event_tags(message: str) -> Tuple[str, List[Dict[str, str]]]:
    if " | " not in message:
        return message.strip(), []
    parts = [part.strip() for part in message.split(" | ")]
    base = parts[0]
    tags: List[Dict[str, str]] = []
    for chunk in parts[1:]:
        if not chunk:
            continue
        segments = [seg.strip() for seg in chunk.split(",")]
        for seg in segments:
            if not seg:
                continue
            if "=" in seg:
                key, value = seg.split("=", 1)
                tags.append({"label": key.strip(), "value": value.strip()})
            else:
                tags.append({"label": "", "value": seg})
    return base, tags


def _parse_log_line(line: str) -> Dict[str, str]:
    raw = line.rstrip("\n")
    info = {"timestamp": raw, "level": "INFO", "source": "", "message": raw, "raw": raw}
    match = LOG_LINE_RE.match(raw)
    if not match:
        return info
    ts = match.group("ts").strip()
    level = match.group("level").strip().upper()
    source = match.group("logger").strip()
    message = match.group("message").strip()
    event_kind = None
    event_tags: List[Dict[str, str]] = []
    event_match = EVENT_KIND_RE.match(message)
    if event_match:
        event_kind = event_match.group("kind").strip().upper()
        message = event_match.group("body").strip()
    message, event_tags = _split_event_tags(message)
    return {
        "timestamp": ts,
        "level": level,
        "source": source,
        "message": message,
        "raw": raw,
        "event_kind": event_kind,
        "event_tags": event_tags,
    }


def _tail_logs(limit: int = 200) -> Tuple[List[Dict[str, str]], Optional[Path], List[str]]:
    """
    Return (entries, source_path) for the most recent log file. If limit <= 0, return all lines.
    """
    path = _latest_log_file()
    if path is None or not path.exists():
        return [], None, []
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            lines = handle.readlines()
    except Exception:
        return [], path, []
    if limit > 0 and len(lines) > limit:
        lines = lines[-limit:]
    entries = [_parse_log_line(line) for line in lines]
    stripped_lines = [line.rstrip("\n") for line in lines]
    return entries, path, stripped_lines


def load_logs_from_disk(limit: int = 200) -> List[Dict[str, Any]]:
    """
    Read the JSONL engine log tail and return up to `limit` entries (oldest -> newest).
    """
    max_lines = max(int(limit or 0), 0)
    if max_lines == 0:
        return []
    path = ENGINE_LOG_PATH
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as handle:
            lines = deque(handle, maxlen=max_lines)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to read engine log file %s: %s", path, exc)
        return []

    entries: List[Dict[str, Any]] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            entries.append(
                {
                    "ts": None,
                    "level": "UNKNOWN",
                    "logger": "engine",
                    "message": line,
                }
            )
    return entries


def _matches_category(entry: Dict[str, Any], patterns: Tuple[str, ...]) -> bool:
    logger_name = str(entry.get("logger") or "").lower()
    message = str(entry.get("message") or "").lower()
    for pattern in patterns:
        token = pattern.lower()
        if token in logger_name or token in message:
            return True
    return False


def _filter_logs_by_category(
    logs: List[Dict[str, Any]],
    category: Optional[str],
) -> List[Dict[str, Any]]:
    if not category:
        return logs

    normalized = category.strip().lower()
    if not normalized:
        return logs

    if normalized == "system":
        patterns = list(LOG_CATEGORY_PATTERNS.values())
        return [
            entry
            for entry in logs
            if not any(_matches_category(entry, pats) for pats in patterns)
        ]

    patterns = LOG_CATEGORY_PATTERNS.get(normalized)
    if not patterns:
        return logs
    return [entry for entry in logs if _matches_category(entry, patterns)]


def _build_logs_payload(
    *,
    limit: int,
    level: Optional[str],
    contains: Optional[str],
    kind: Optional[str] = None,
) -> Dict[str, Any]:
    effective_limit = max(int(limit or 0), 0)
    logs = load_logs_from_disk(limit=effective_limit if effective_limit > 0 else 0)

    level_filter: Optional[str] = (
        level.strip().upper() if isinstance(level, str) and level.strip() else None
    )
    needle: Optional[str] = (
        contains.strip().lower() if isinstance(contains, str) and contains.strip() else None
    )

    if level_filter:
        logs = [entry for entry in logs if (entry.get("level") or "").upper() == level_filter]
    if needle:
        logs = [
            entry
            for entry in logs
            if needle in str(entry.get("message") or "").lower()
        ]

    logs = _filter_logs_by_category(logs, kind)
    return {"logs": logs, "entries": logs}

def _load_quotes() -> Dict[str, Any]:
    """
    Load live quotes from artifacts/live_quotes.json (if some other process writes it).
    """
    if not QUOTES_PATH.exists(): return {}
    try:
        with QUOTES_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def _load_ticks_cache(state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    src = state or {}
    broker = src.get("broker") if isinstance(src, dict) else None
    ticks = broker.get("ticks_by_symbol") if isinstance(broker, dict) else None
    return ticks if isinstance(ticks, dict) else {}

def _parse_instrument(symbol: str) -> Dict[str, Optional[str]]:
    upper = (symbol or "").upper()
    info: Dict[str, Optional[str]] = {
        "productType": "EQ","base": None,"expiry": None,"strike": None,"optionType": None,
    }
    if not upper: return info
    if "CE" in upper or "PE" in upper:
        info["productType"] = "OPT"; info["optionType"] = "CE" if "CE" in upper else "PE"
    elif "FUT" in upper:
        info["productType"] = "FUT"
    base_match = re.match(r"^(NIFTY|BANKNIFTY|FINNIFTY)", upper) or re.search(r"(NIFTY|BANKNIFTY|FINNIFTY)", upper)
    if base_match:
        info["base"] = base_match.group(1)
        remainder = upper[base_match.end():]
        expiry_match = re.match(r"([0-9]{2}[A-Z]{2}[0-9]{2})", remainder)
        if expiry_match: info["expiry"] = expiry_match.group(1)
        if info["productType"] == "OPT":
            strike_match = re.search(r"([0-9]{3,6})(CE|PE)", remainder)
            if strike_match: info["strike"] = strike_match.group(1)
    else:
        letters = re.sub(r"[^A-Z]", "", upper)
        info["base"] = letters[:6] if letters else None
    return info

def _to_float(value: Any) -> Optional[float]:
    if value is None: return None
    try: return float(value)
    except (TypeError, ValueError): return None

def resolve_last_for_symbol_with_source(
    symbol: str,
    pos: Dict[str, Any],
    quotes: Dict[str, Any],
    ticks: Dict[str, Any],
) -> tuple[float, str]:
    """Return (last_price, source) where source in {'tick','quote','pos','avg'}."""
    info = _parse_instrument(symbol)
    product = info.get("productType") or "EQ"

    def _sanitize(x: Optional[float]) -> Optional[float]:
        if x is None or x <= 0:
            return None
        if product == "OPT" and x > 10_000:
            return None
        return x

    keys = list({symbol, symbol.upper(), symbol.lower()})
    for k in keys:
        tick = ticks.get(k) if isinstance(ticks, dict) else None
        if isinstance(tick, dict):
            last = _sanitize(_to_float(tick.get("last_price") or tick.get("ltp")))
            if last is not None:
                return last, "tick"
    for k in keys:
        quote = quotes.get(k) if isinstance(quotes, dict) else None
        if isinstance(quote, dict):
            last = _sanitize(_to_float(quote.get("last_price") or quote.get("last")))
            if last is not None:
                return last, "quote"

    pos_last = _sanitize(_to_float(pos.get("last_price") or pos.get("ltp") or pos.get("mark_price")))
    if pos_last is not None:
        return pos_last, "pos"

    avg_price = _to_float(pos.get("avg_price") or pos.get("average_price") or pos.get("price")) or 0.0
    return avg_price, "avg"


def resolve_last_for_symbol(symbol: str, pos: Dict[str, Any], quotes: Dict[str, Any], ticks: Dict[str, Any]) -> float:
    info = _parse_instrument(symbol)
    product = info.get("productType") or "EQ"

    def _sanitize(price: Optional[float]) -> Optional[float]:
        if price is None or price <= 0: return None
        if product == "OPT" and price > 10_000: return None
        return price

    symbol_keys = list({symbol, symbol.upper(), symbol.lower()})
    for key in symbol_keys:
        tick = ticks.get(key) if isinstance(ticks, dict) else None
        if isinstance(tick, dict):
            last = _sanitize(_to_float(tick.get("last_price") or tick.get("ltp")))
            if last is not None: return last
    for key in symbol_keys:
        quote = quotes.get(key) if isinstance(quotes, dict) else None
        if isinstance(quote, dict):
            last = _sanitize(_to_float(quote.get("last_price") or quote.get("last")))
            if last is not None: return last
    pos_last = _sanitize(_to_float(pos.get("last_price") or pos.get("ltp") or pos.get("mark_price")))
    if pos_last is not None: return pos_last
    avg_price = _to_float(pos.get("avg_price") or pos.get("average_price") or pos.get("price")) or 0.0
    return avg_price

def compute_unrealized_pnl(avg_price: float, last_price: float, quantity: float) -> float:
    return (last_price - avg_price) * quantity


def _ist_now_with_tz() -> datetime:
    """
    Return current IST time with timezone info attached for downstream consumers.
    """
    return now_ist().replace(tzinfo=IST_TZ)


# ---------- market / meta ----------
def _market_status_payload() -> Dict[str, Any]:
    now = now_ist()
    start = dtime(9, 0)
    end   = dtime(15, 30)
    label = "CLOSED"
    phase = "closed"
    if is_market_open(now):
        status, message = "ONLINE", "Trading session live"
        label = "OPEN"
        phase = "open"
    elif now.time() < start:
        status, message = "PRE_OPEN", "Market has not opened yet"
        label = "PRE-MARKET"
        phase = "pre"
    else:
        status, message = "CLOSED", "Session complete"
    return {
        "status": status,
        "message": message,
        "ist_timestamp": now.isoformat(),
        "label": label,
        "phase": phase,
    }


def _inject_runtime_meta(state: Dict[str, Any]) -> None:
    """
    Populate frequently used runtime metadata on the state payload without mutating engine data.
    """
    meta = state.setdefault("meta", {})
    ist_now = _ist_now_with_tz()
    meta["server_time"] = ist_now.isoformat()
    meta["server_time_epoch_ms"] = int(ist_now.timestamp() * 1000)
    meta["is_market_open"] = bool(is_market_open(ist_now))
    meta.setdefault("mode", get_mode())
    meta["mode"] = str(meta["mode"]).upper()
    meta["next_session_time"] = dtime(9, 15).strftime("%H:%M")
    realized = float(meta.get("total_realized_pnl") or state.get("total_realized_pnl") or 0.0)
    unrealized = float(meta.get("total_unrealized_pnl") or state.get("total_unrealized_pnl") or 0.0)
    meta["day_pnl"] = realized + unrealized


def _parse_iso_date(ts: str) -> Optional[date]:
    if not ts:
        return None
    try:
        norm = ts.replace("Z", "+00:00")
        return datetime.fromisoformat(norm).date()
    except Exception:
        return None

def _resolve_query_date(date_str: Optional[str]) -> Optional[date]:
    if not date_str: return now_ist().date()
    try: return datetime.fromisoformat(date_str).date()
    except ValueError:
        try: return datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError: return None

def _augment_meta_budget(state: Dict[str, Any]) -> None:
    meta = state.setdefault("meta", {})
    budget_candidates = [
        meta.get("risk_budget"), meta.get("risk_budget_total"), meta.get("max_daily_loss"),
        state.get("risk_budget"), state.get("max_daily_loss"),
    ]
    budget_total = next((float(x) for x in budget_candidates if isinstance(x, (int, float)) and float(x) > 0), None)
    total_realized  = float(meta.get("total_realized_pnl")  or state.get("total_realized_pnl")  or 0.0)
    total_unreal    = float(meta.get("total_unrealized_pnl") or state.get("total_unrealized_pnl") or 0.0)
    total_pnl       = total_realized + total_unreal
    meta["risk_budget_total"] = budget_total
    risk_used = 0.0
    if budget_total and total_pnl < 0:
        risk_used = min(abs(total_pnl), budget_total)
    meta["risk_budget_used"]     = risk_used if budget_total else None
    meta["risk_budget_used_pct"] = ((risk_used / budget_total * 100.0) if (budget_total and risk_used) else None)

def _compute_hold_reasons(state: Dict[str, Any]) -> List[str]:
    meta = state.get("meta", {})
    reasons: List[str] = []
    market_status = meta.get("market_status", {})
    status = market_status.get("status")
    if status == "CLOSED": reasons.append("market closed")
    elif status == "PRE_OPEN": reasons.append("market pre-open")
    if meta.get("risk_lock"): reasons.append("risk lock")
    if meta.get("max_daily_loss_hit"): reasons.append("max daily loss hit")
    if meta.get("trading_enabled") is False or state.get("trading_enabled") is False: reasons.append("trading disabled")
    hold_from_meta = meta.get("hold_reasons") or []
    if isinstance(hold_from_meta, list): reasons.extend(str(r) for r in hold_from_meta if r)
    hold_state = state.get("hold_reason")
    if hold_state: reasons.append(str(hold_state))
    state_hold_list = state.get("hold_reasons") or []
    if isinstance(state_hold_list, list): reasons.extend(str(r) for r in state_hold_list if r)
    seen, deduped = set(), []
    for r in reasons:
        k = r.lower()
        if k not in seen:
            seen.add(k); deduped.append(r)
    return deduped

def _state_path() -> Path:
    """
    Resolve the best state file for the current mode.

    Prefer the same checkpoint the engine writes (paper_state_latest.json),
    falling back to legacy flat files if needed.
    """
    checkpoint = _resolve_checkpoint_path()
    if checkpoint is not None and checkpoint.exists():
        return checkpoint
    mode = get_mode()
    filename = "paper_state.json" if mode == "paper" else "live_state.json"
    return ARTIFACTS_ROOT / filename

# ======================= API =======================
@router.get("/api/state")
def api_state() -> JSONResponse:
    state = store.load_checkpoint()
    if state is None:
        return JSONResponse({"engines": {}, "pnl": {}, "ts": None})
    return JSONResponse(state)


@router.get("/api/meta")
def api_meta() -> JSONResponse:
    """
    Lightweight metadata endpoint for market clock/pill updates.
    Uses system time in Asia/Kolkata for display, and compute_market_status()
    for open/closed phase.
    """
    current_ist = datetime.now(IST_ZONE)
    market_status = compute_market_status()

    portfolio_summary = load_paper_portfolio_summary()
    payload = {
        "now_ist": current_ist.isoformat(),
        "market_open": market_status.get("status") == "OPEN",
        "market_status": market_status.get("status"),
        "status_payload": market_status,
        "regime": portfolio_summary.get("market_regime") or "UNKNOWN",
        "regime_snapshot": portfolio_summary.get("regime_snapshot") or {},
    }
    return JSONResponse(payload)


@router.get("/api/config/summary")
async def api_config_summary() -> JSONResponse:
    """
    Return a compact summary of the active trading configuration.
    """
    cfg = load_app_config()
    summary = summarize_config(cfg)
    return JSONResponse(summary)


@router.get("/api/summary/today")
async def api_summary_today() -> JSONResponse:
    """
    Return today's realized PnL and trade stats derived from orders CSV.
    """
    try:
        today = now_ist().date()
        summary = compute_today_summary(today)
    except Exception as exc:  # noqa: BLE001
        logger.exception("api_summary_today failed: %s", exc)
        today = now_ist().date()
        summary = {
            "date": today.isoformat(),
            "realized_pnl": 0.0,
            "num_trades": 0,
            "win_trades": 0,
            "loss_trades": 0,
            "win_rate": 0.0,
            "largest_win": 0.0,
            "largest_loss": 0.0,
            "avg_r": 0.0,
        }
    return JSONResponse(summary)


@router.get("/api/quality/summary")
async def api_quality_summary() -> JSONResponse:
    """
    Return throttler and trade quality stats for dashboard analytics.
    """
    throttler = latest_throttler_summary() or {}
    quality = signal_quality_manager.daily_summary()
    trade_flow_snapshot = trade_monitor.snapshot()
    today = now_ist().date().isoformat()
    veto_breakdown = throttler.get("veto_breakdown") or {}
    trade_caps = throttler.get("trade_caps") or {}
    total_signals = throttler.get("total_signals")
    if total_signals is None:
        total_signals = trade_flow_snapshot.get("signals_seen", 0)
    total_trades = throttler.get("total_trades_taken")
    if total_trades is None:
        total_trades = quality.get("total_trades_allowed", 0)
    total_vetoed = throttler.get("total_vetoed")
    if total_vetoed is None:
        total_vetoed = quality.get("total_trades_vetoed", 0)
    last_veto = throttler.get("last_veto_reason")
    cap_reason_codes = {"CAP_SYMBOL", "CAP_STRATEGY", "CAP_TOTAL", "DAILY_DRAWDOWN", "LOSS_STREAK"}

    payload = {
        "date": throttler.get("date") or quality.get("date") or today,
        "total_signals": int(total_signals or 0),
        "total_trades_taken": int(total_trades or 0),
        "total_vetoed": int(total_vetoed or 0),
        "veto_breakdown": veto_breakdown,
        "trade_caps": trade_caps,
        "quality_summary": quality,
        "trade_flow": trade_flow_snapshot,
        "drawdown_hit": bool(throttler.get("drawdown_hit")),
        "loss_streak": throttler.get("loss_streak"),
        "last_veto_reason": last_veto,
        "caps_active": bool(throttler.get("drawdown_hit") or (last_veto in cap_reason_codes)),
    }
    return JSONResponse(payload)

@router.get("/api/signals")
def api_signals(limit: int = 150, date_str: Optional[str] = Query(None, alias="date")) -> JSONResponse:
    rows = _load_signals(limit=0)
    target_date = _resolve_query_date(date_str)
    if target_date:
        rows = [r for r in rows if _parse_iso_date(r.get("timestamp", "")) == target_date]
    if limit > 0 and len(rows) > limit:
        rows = rows[-limit:]
    return JSONResponse(rows)

@router.get("/api/orders")
def api_orders(limit: int = 150, date_str: Optional[str] = Query(None, alias="date")) -> JSONResponse:
    target_date = _resolve_query_date(date_str)
    rows = _load_orders_from_csv(limit=0)
    if rows:
        if target_date:
            rows = [r for r in rows if _parse_iso_date(r.get("timestamp", "")) == target_date]
        if limit > 0 and len(rows) > limit:
            rows = rows[-limit:]
        return JSONResponse(rows)
    # Fallback: embedded broker.orders in state
    try:
        state = _load_state()
    except FileNotFoundError:
        return JSONResponse([])
    orders = state.get("broker", {}).get("orders", [])
    if target_date:
        orders = [o for o in orders if _parse_iso_date(o.get("timestamp", "")) == target_date]
    if limit > 0 and len(orders) > limit:
        orders = orders[-limit:]
    return JSONResponse(orders)

@router.get("/api/logs")
async def api_logs(
    limit: int = 150,
    level: Optional[str] = Query(None, description="Optional level filter (INFO/WARN/ERROR/DEBUG)"),
    contains: Optional[str] = Query(None, description="Case-insensitive substring filter"),
    kind: Optional[str] = Query(None, description="Logical stream: engine/trades/signals/system"),
) -> JSONResponse:
    payload = _build_logs_payload(
        limit=limit,
        level=level,
        contains=contains,
        kind=kind,
    )
    return JSONResponse(payload)


@router.get("/api/auth/status")
async def api_auth_status() -> JSONResponse:
    snapshot = _read_token_snapshot()
    access_token = snapshot["access_token"]
    login_ts = snapshot["login_ts"]
    login_age = snapshot["login_age_minutes"]
    base_payload = {
        "is_logged_in": False,
        "user_id": None,
        "login_ts": login_ts,
        "login_age_minutes": login_age,
        "token_valid": False,
        "error": snapshot["error"],
    }

    if not access_token:
        if base_payload["error"] is None:
            base_payload["error"] = "tokens_missing"
        return JSONResponse(base_payload)

    token_valid, user_id, preflight_error = _kite_preflight_snapshot()
    base_payload["token_valid"] = token_valid
    base_payload["is_logged_in"] = token_valid
    base_payload["user_id"] = user_id
    if not token_valid:
        base_payload["error"] = preflight_error or "expired_or_invalid"
    else:
        base_payload["error"] = None
    return JSONResponse(base_payload)


@router.get("/api/engines/status")
async def api_engines_status() -> JSONResponse:
    status = _load_paper_engine_status()
    return JSONResponse({"engines": [status]})


@router.get("/api/portfolio/summary")
async def api_portfolio_summary() -> JSONResponse:
    """
    Return a compact P&L / risk snapshot for the paper engine.
    """
    return JSONResponse(load_paper_portfolio_summary())


@router.get("/api/portfolio")
async def api_portfolio() -> JSONResponse:
    """
    Return live portfolio snapshot with up-to-date position values.
    
    This endpoint provides real-time portfolio data including:
    - Summary: equity, realized/unrealized PnL, total notional, margins
    - Positions: Per-symbol details with live LTP, unrealized PnL, and PnL%
    
    Works in both paper and live modes by loading from state store checkpoint
    and resolving current prices from market data cache.
    """
    try:
        # Load state from checkpoint
        state = _load_runtime_state_payload()
        if not state:
            return JSONResponse({
                "starting_capital": 0.0,
                "equity": 0.0,
                "realized_pnl": 0.0,
                "unrealized_pnl": 0.0,
                "total_notional": 0.0,
                "free_margin": 0.0,
                "margin_used": 0.0,
                "positions": [],
                "error": "No checkpoint data available",
            })
        
        # Load market data for price resolution
        quotes = _load_quotes()
        ticks = _load_ticks_cache(state)
        
        # Extract equity info from state
        equity_data = state.get("equity") or {}
        pnl_data = state.get("pnl") or {}
        
        # Try to get paper capital from equity, pnl, or config
        starting_capital = _safe_float(equity_data.get("paper_capital"), 0.0)
        if starting_capital == 0.0:
            starting_capital = _safe_float(pnl_data.get("paper_capital"), 0.0)
        if starting_capital == 0.0:
            # Fallback to config
            try:
                cfg = load_app_config()
                trading_section = cfg.trading or {}
                starting_capital = _safe_float(trading_section.get("paper_capital"), 500_000.0)
            except Exception:
                starting_capital = 500_000.0
        
        realized_pnl = _safe_float(equity_data.get("realized_pnl"), 0.0)
        
        # Process positions to compute live unrealized PnL
        positions_data = state.get("positions") or []
        if isinstance(positions_data, dict):
            positions_list = list(positions_data.values())
        else:
            positions_list = list(positions_data)
        
        processed_positions = []
        total_unrealized = 0.0
        total_notional = 0.0
        
        for pos in positions_list:
            if not isinstance(pos, dict):
                continue
            
            qty = _safe_float(pos.get("quantity") or pos.get("qty"), 0.0)
            if qty == 0:
                continue
            
            symbol = pos.get("symbol") or pos.get("tradingsymbol") or ""
            if not symbol:
                continue
            
            avg_price = _safe_float(pos.get("avg_price") or pos.get("average_price"), 0.0)
            last_price = resolve_last_for_symbol(symbol, pos, quotes, ticks)
            unrealized_pnl = compute_unrealized_pnl(avg_price, last_price, qty)
            notional = abs(qty * last_price)
            pnl_pct = ((last_price - avg_price) / avg_price * 100.0) if avg_price > 0 else 0.0
            
            total_unrealized += unrealized_pnl
            total_notional += notional
            
            processed_positions.append({
                "symbol": symbol,
                "side": "LONG" if qty > 0 else "SHORT",
                "quantity": int(abs(qty)),
                "avg_price": round(avg_price, 2),
                "last_price": round(last_price, 2),
                "notional": round(notional, 2),
                "unrealized_pnl": round(unrealized_pnl, 2),
                "pnl_pct": round(pnl_pct, 2),
            })
        
        # Compute final equity
        equity = starting_capital + realized_pnl + total_unrealized
        free_margin = equity - total_notional
        
        return JSONResponse({
            "starting_capital": round(starting_capital, 2),
            "equity": round(equity, 2),
            "realized_pnl": round(realized_pnl, 2),
            "unrealized_pnl": round(total_unrealized, 2),
            "total_notional": round(total_notional, 2),
            "free_margin": round(free_margin, 2),
            "margin_used": round(total_notional, 2),
            "positions": processed_positions,
        })
        
    except Exception as exc:
        logger.exception("Failed to load portfolio snapshot: %s", exc)
        return JSONResponse({
            "starting_capital": 0.0,
            "equity": 0.0,
            "realized_pnl": 0.0,
            "unrealized_pnl": 0.0,
            "total_notional": 0.0,
            "free_margin": 0.0,
            "margin_used": 0.0,
            "positions": [],
            "error": str(exc),
        }, status_code=500)


@router.get("/api/monitor/trade_flow")
async def api_monitor_trade_flow() -> JSONResponse:
    """
    Simple trade-flow funnel metrics for today.
    """
    return JSONResponse(trade_monitor.snapshot())


@router.get("/api/trade_flow")
async def api_trade_flow() -> JSONResponse:
    snapshot = load_trade_flow_snapshot()
    stats = snapshot.get("trade_flow") or _default_trade_flow()
    funnel = snapshot.get("funnel") or _build_trade_flow_funnel(stats)
    last_events = stats.get("last_events") or {}
    recent_hits = {
        "stop": {
            "count": int(stats.get("stop_hits", 0)),
            "last_ts": last_events.get("stop_hits"),
        },
        "target": {
            "count": int(stats.get("target_hits", 0)),
            "last_ts": last_events.get("target_hits"),
        },
    }
    payload = {
        "snapshot_ts": snapshot.get("snapshot_ts"),
        "trade_flow": stats,
        "funnel": funnel,
        "blocks": {
            "risk": snapshot.get("risk_reasons") or [],
            "time": snapshot.get("time_reasons") or [],
        },
        "recent_hits": recent_hits,
    }
    return JSONResponse(payload)


@router.get("/api/signals/recent")
async def api_signals_recent(limit: int = Query(50, ge=1, le=200)) -> JSONResponse:
    """
    Return up to `limit` most recent signals recorded by the paper engine.
    """
    return JSONResponse(load_recent_signals(limit=limit))


@router.get("/api/positions/open")
async def api_positions_open() -> JSONResponse:
    """
    Return open paper positions from the latest checkpoint.
    """
    return JSONResponse(load_open_positions())


def load_open_positions() -> List[Dict[str, Any]]:
    """
    Return open positions from the latest checkpoint.
    """
    try:
        state = _load_runtime_state_payload()
        if not state:
            return []
        
        quotes = _load_quotes()
        ticks = _load_ticks_cache(state)
        
        positions_data = state.get("positions") or []
        if isinstance(positions_data, dict):
            positions_list = list(positions_data.values())
        else:
            positions_list = list(positions_data)
        
        open_positions = []
        for pos in positions_list:
            if not isinstance(pos, dict):
                continue
            
            qty = _safe_float(pos.get("quantity") or pos.get("qty"), 0.0)
            if qty == 0:
                continue
            
            symbol = pos.get("symbol") or pos.get("tradingsymbol") or ""
            if not symbol:
                continue
            
            avg_price = _safe_float(pos.get("avg_price") or pos.get("average_price"), 0.0)
            last_price = resolve_last_for_symbol(symbol, pos, quotes, ticks)
            unrealized_pnl = compute_unrealized_pnl(avg_price, last_price, qty)
            
            open_positions.append({
                "symbol": symbol,
                "side": "LONG" if qty > 0 else "SHORT",
                "quantity": int(qty),
                "avg_price": avg_price,
                "last_price": last_price,
                "unrealized_pnl": unrealized_pnl,
            })
        
        return open_positions
    except Exception as exc:
        logger.exception("Failed to load open positions: %s", exc)
        return []


def _default_trade_flow() -> Dict[str, Any]:
    """
    Return default empty trade flow stats.
    """
    return {
        "signals_seen": 0,
        "signals_evaluated": 0,
        "trades_allowed": 0,
        "trades_vetoed": 0,
        "orders_placed": 0,
        "orders_filled": 0,
        "stop_hits": 0,
        "target_hits": 0,
        "last_events": {},
    }


def _build_trade_flow_funnel(stats: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Build funnel visualization data from trade flow stats.
    """
    signals_seen = int(stats.get("signals_seen", 0))
    signals_evaluated = int(stats.get("signals_evaluated", 0))
    trades_allowed = int(stats.get("trades_allowed", 0))
    trades_vetoed = int(stats.get("trades_vetoed", 0))
    orders_placed = int(stats.get("orders_placed", 0))
    orders_filled = int(stats.get("orders_filled", 0))
    
    return [
        {"stage": "Signals Seen", "count": signals_seen},
        {"stage": "Evaluated", "count": signals_evaluated},
        {"stage": "Allowed", "count": trades_allowed},
        {"stage": "Vetoed", "count": trades_vetoed},
        {"stage": "Orders Placed", "count": orders_placed},
        {"stage": "Orders Filled", "count": orders_filled},
    ]


def load_trade_flow_snapshot() -> Dict[str, Any]:
    """
    Load trade flow snapshot from trade monitor.
    """
    try:
        monitor_snapshot = trade_monitor.snapshot()
        stats = monitor_snapshot or _default_trade_flow()
        funnel = _build_trade_flow_funnel(stats)
        
        return {
            "snapshot_ts": datetime.now(timezone.utc).isoformat(),
            "trade_flow": stats,
            "funnel": funnel,
            "risk_reasons": [],
            "time_reasons": [],
        }
    except Exception as exc:
        logger.exception("Failed to load trade flow snapshot: %s", exc)
        return {
            "snapshot_ts": datetime.now(timezone.utc).isoformat(),
            "trade_flow": _default_trade_flow(),
            "funnel": [],
            "risk_reasons": [],
            "time_reasons": [],
        }


def load_recent_orders(limit: int = 40) -> Dict[str, List[Dict[str, Any]]]:
    """
    Return up to `limit` most recent paper orders from today's journal.
    """
    today = date.today()
    journal_path = ARTIFACTS_ROOT / "journal" / today.strftime("%Y-%m-%d") / "orders.csv"

    if not journal_path.exists():
        return {"orders": []}

    rows: List[Dict[str, Any]] = []
    try:
        with journal_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
    except Exception as exc:
        logger.exception("Failed to read orders from %s: %s", journal_path, exc)
        return {"orders": []}

    if not rows:
        return {"orders": []}

    ts_keys = ["ts", "timestamp", "created_at", "time"]
    ts_key = next((key for key in ts_keys if key in rows[0]), None)

    if ts_key:
        rows.sort(key=lambda r: r.get(ts_key, ""), reverse=True)

    if limit > 0 and len(rows) > limit:
        rows = rows[:limit]

    return {"orders": rows}


@router.get("/api/orders/recent")
async def api_orders_recent(limit: int = Query(50, ge=1, le=200)) -> JSONResponse:
    """
    Return up to `limit` most recent paper orders.
    """
    return JSONResponse(load_recent_orders(limit=limit))


@router.get("/api/stats/strategies")
async def api_stats_strategies(days: int = Query(1, ge=1, le=7)) -> JSONResponse:
    """
    Aggregate strategy stats from recent signals (default window: 1 day).
    """
    stats = load_strategy_stats_from_signals(limit_days=days)
    return JSONResponse(stats)


@router.get("/api/strategies/health")
async def api_strategies_health() -> JSONResponse:
    """
    Get real-time strategy health metrics combining telemetry and signal data.
    Returns structured health data for active strategies.
    """
    # Get signal quality metrics (win rates from actual trades)
    quality_metrics = signal_quality_manager.strategy_metrics_snapshot()
    
    # Get CSV-based signal stats (for symbol/timeframe info)
    csv_stats = load_strategy_stats_from_signals(limit_days=1)
    
    # Get telemetry for real-time counters
    bus = get_telemetry_bus()
    recent_events = bus.get_recent_events(event_type="engine_health", limit=10)
    
    telemetry_data = {}
    for event in reversed(recent_events):
        payload = event.get("payload", {})
        if payload.get("engine_name") == "StrategyEngineV2":
            metrics = payload.get("metrics", {})
            telemetry_data = metrics.get("strategies", {})
            break
    
    # Build combined strategy health entries
    strategies = []
    seen_keys = set()
    
    # Process CSV stats (has symbol/timeframe info)
    for stat in csv_stats:
        strategy_name = stat.get("strategy", "")
        symbol = stat.get("symbol", "")
        timeframe = stat.get("timeframe", "")
        mode = stat.get("mode", "paper")
        
        # Skip invalid entries
        if not strategy_name or "ema50=None" in str(strategy_name):
            continue
        
        key = (strategy_name, symbol)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        
        # Get quality metrics for this strategy+symbol
        quality = quality_metrics.get((strategy_name, symbol), {})
        win_rate_pct = quality.get("winrate_20", 0.0)
        win_rate = win_rate_pct / 100.0 if win_rate_pct > 0 else None
        
        # Get telemetry data for real-time counters
        telem = telemetry_data.get(strategy_name, {})
        signals_today = telem.get("signals_today", stat.get("trades_today", 0))
        last_signal = stat.get("last_signal", telem.get("last_signal", "HOLD"))
        last_signal_ts = telem.get("last_signal_ts")
        
        strategy_entry = {
            "strategy_name": strategy_name,
            "symbol": symbol or "N/A",
            "timeframe": timeframe or "N/A",
            "mode": mode,
            "signals_today": signals_today,
            "win_rate": win_rate,
            "last_signal": last_signal,
            "last_signal_ts": last_signal_ts,
            "regime": telem.get("regime"),
        }
        strategies.append(strategy_entry)
    
    return JSONResponse({"strategies": strategies})


@router.get("/api/stats/equity")
async def api_stats_equity(days: int = Query(1, ge=1, le=7)) -> JSONResponse:
    """
    Return equity curve snapshots for the requested lookback.
    """
    data = load_equity_curve(limit_days=days)
    return JSONResponse(data)


@router.get("/api/scanner/universe")
async def api_scanner_universe() -> JSONResponse:
    """
    Return the most recent instrument universe discovered by MarketScanner.
    """
    payload = load_cached_universe()
    return JSONResponse(payload)


@router.get("/api/market_data/window")
async def api_market_data_window(
    symbol: str = Query(..., description="Trading symbol (e.g., NIFTY24DECFUT)"),
    timeframe: str = Query("5m", description="Timeframe (e.g., 1m, 5m, 15m, 1h, 1d)"),
    limit: int = Query(50, ge=1, le=1000, description="Number of candles to return (max 1000)")
) -> JSONResponse:
    """
    Return the last N candles for the specified symbol and timeframe.
    This endpoint is used for charting and analysis in the dashboard.
    
    Returns:
        JSON array of candle objects with format:
        [{
            "ts": "2024-11-15T10:30:00+00:00",
            "open": 19500.0,
            "high": 19525.0,
            "low": 19490.0,
            "close": 19510.0,
            "volume": 12345.0
        }, ...]
    """
    try:
        from core.market_data_engine import MarketDataEngine
        from core.kite_env import make_kite_client_from_files
        
        # Create Kite client
        try:
            kite = make_kite_client_from_files()
        except Exception:
            kite = None
        
        # Load universe for token resolution
        universe_snapshot = load_cached_universe()
        
        # Create market data engine
        cache_dir = ARTIFACTS_ROOT / "market_data"
        mde = MarketDataEngine(kite, universe_snapshot, cache_dir=cache_dir)
        
        # Get window of candles
        candles = mde.get_window(symbol.upper(), timeframe, limit)
        
        return JSONResponse({
            "symbol": symbol.upper(),
            "timeframe": timeframe,
            "count": len(candles),
            "candles": candles
        })
    except Exception as exc:
        logger.exception("Failed to fetch market data window: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch market data: {str(exc)}"
        ) from exc


@router.get("/api/market_data/latest_tick")
async def api_market_data_latest_tick(
    symbol: str = Query(..., description="Trading symbol (e.g., NIFTY24DECFUT)")
) -> JSONResponse:
    """
    Get the latest tick for a symbol from Market Data Engine v2.
    
    If MDE v2 is not available, returns 503.
    
    Returns:
        {
            "symbol": "NIFTY24DECFUT",
            "ltp": 23850.0,
            "bid": 23845.0,
            "ask": 23855.0,
            "volume": 12345,
            "ts": "2024-11-15T10:30:00+00:00"
        }
    """
    try:
        # Try to get MDE v2 instance from active engines
        # This assumes we store a reference globally or in app state
        # For now, return a helpful message
        mde_v2 = getattr(app, "market_data_engine_v2", None)
        
        if not mde_v2:
            raise HTTPException(
                status_code=503,
                detail="Market Data Engine v2 not available. Enable with data.use_mde_v2=true in config."
            )
            
        tick = mde_v2.get_latest_tick(symbol.upper())
        
        if not tick:
            raise HTTPException(
                status_code=404,
                detail=f"No tick data available for symbol: {symbol}"
            )
            
        return JSONResponse(tick)
        
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to fetch latest tick: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch latest tick: {str(exc)}"
        ) from exc


@router.get("/api/market_data/candles")
async def api_market_data_candles_v2(
    symbol: str = Query(..., description="Trading symbol (e.g., NIFTY24DECFUT)"),
    timeframe: str = Query("5m", description="Timeframe (e.g., 1m, 5m, 15m)"),
    limit: int = Query(100, ge=1, le=500, description="Number of candles to return (max 500)")
) -> JSONResponse:
    """
    Get candles from Market Data Engine v2.
    
    If MDE v2 is not available, returns 503.
    
    Returns:
        {
            "symbol": "NIFTY24DECFUT",
            "timeframe": "5m",
            "count": 100,
            "candles": [
                {
                    "symbol": "NIFTY24DECFUT",
                    "timeframe": "5m",
                    "open_time": "2024-11-15T10:30:00+00:00",
                    "close_time": "2024-11-15T10:35:00+00:00",
                    "open": 23850.0,
                    "high": 23865.0,
                    "low": 23845.0,
                    "close": 23860.0,
                    "volume": 1234.5,
                    "tick_count": 25,
                    "is_closed": true,
                    "anomaly": false
                },
                ...
            ]
        }
    """
    try:
        mde_v2 = getattr(app, "market_data_engine_v2", None)
        
        if not mde_v2:
            raise HTTPException(
                status_code=503,
                detail="Market Data Engine v2 not available. Enable with data.use_mde_v2=true in config."
            )
            
        candles = mde_v2.get_candles(symbol.upper(), timeframe, limit)
        
        return JSONResponse({
            "symbol": symbol.upper(),
            "timeframe": timeframe,
            "count": len(candles),
            "candles": candles
        })
        
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to fetch candles from MDE v2: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch candles: {str(exc)}"
        ) from exc


@router.get("/api/market_data/v2/stats")
async def api_market_data_v2_stats() -> JSONResponse:
    """
    Get Market Data Engine v2 statistics.
    
    Returns:
        {
            "is_running": true,
            "feed_mode": "kite",
            "symbols_count": 3,
            "timeframes": ["1m", "5m"],
            "stats": {
                "ticks_received": 12345,
                "ticks_ignored": 10,
                "candles_created": 500,
                "candles_closed": 495,
                "anomalies_detected": 2
            }
        }
    """
    try:
        mde_v2 = getattr(app, "market_data_engine_v2", None)
        
        if not mde_v2:
            raise HTTPException(
                status_code=503,
                detail="Market Data Engine v2 not available."
            )
            
        return JSONResponse({
            "is_running": mde_v2.is_running,
            "feed_mode": mde_v2.feed_mode,
            "symbols_count": len(mde_v2.symbols),
            "timeframes": mde_v2.timeframes,
            "stats": mde_v2.get_stats(),
        })
        
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to fetch MDE v2 stats: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch MDE v2 stats: {str(exc)}"
        ) from exc


@router.get("/api/backtests/list")
async def api_backtests_list() -> JSONResponse:
    runs = _list_backtest_runs()
    return JSONResponse({"runs": runs})


@router.get("/api/backtests/result")
async def api_backtests_result(
    path: str = Query(..., description="strategy/run path, e.g. ema20_50_intraday/2025-11-14_1545")
) -> JSONResponse:
    try:
        payload = _load_backtest_result_payload(path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Backtest result not found") from None
    return JSONResponse(payload)


# --- New Backtest Explorer API endpoints ---

@router.get("/api/backtests")
async def api_backtests() -> JSONResponse:
    """
    List all available backtest runs with summary information.
    
    Returns:
        {
            "runs": [
                {
                    "run_id": "2025-11-14_1545",
                    "strategy": "ema20_50_intraday",
                    "symbol": "NIFTY",
                    "timeframe": "5m",
                    "date_from": "2025-11-01",
                    "date_to": "2025-11-14",
                    "net_pnl": 12500.50,
                    "win_rate": 65.5,
                    "total_trades": 42,
                    "created_at": 1700000000.0
                },
                ...
            ]
        }
    """
    try:
        from core.backtest_registry import list_backtest_runs
        runs = list_backtest_runs(str(BACKTESTS_ROOT))
        return JSONResponse({"runs": runs})
    except Exception as exc:
        logger.exception("Failed to list backtest runs: %s", exc)
        return JSONResponse({"runs": []})


@router.get("/api/backtests/{run_id:path}/summary")
async def api_backtest_summary(run_id: str) -> JSONResponse:
    """
    Get full summary data for a specific backtest run.
    
    Args:
        run_id: Full path like "ema20_50_intraday/2025-11-14_1545"
    
    Returns:
        {
            "run_id": "ema20_50_intraday/2025-11-14_1545",
            "summary": { ... full result.json contents ... }
        }
    """
    try:
        from core.backtest_registry import load_backtest_summary
        summary = load_backtest_summary(run_id, str(BACKTESTS_ROOT))
        
        if summary is None:
            raise HTTPException(status_code=404, detail="Backtest run not found")
        
        return JSONResponse({
            "run_id": run_id,
            "summary": summary,
        })
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to load backtest summary for %s: %s", run_id, exc)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load backtest summary: {str(exc)}"
        ) from exc


@router.get("/api/backtests/{run_id:path}/equity_curve")
async def api_backtest_equity_curve(run_id: str) -> JSONResponse:
    """
    Get equity curve data for a specific backtest run.
    
    Args:
        run_id: Full path like "ema20_50_intraday/2025-11-14_1545"
    
    Returns:
        {
            "run_id": "ema20_50_intraday/2025-11-14_1545",
            "equity_curve": [
                {"ts": "2025-11-14T10:30:00", "equity": 1000050.0, "pnl": 50.0},
                {"ts": "2025-11-14T10:35:00", "equity": 1000125.0, "pnl": 125.0},
                ...
            ]
        }
    """
    try:
        from core.backtest_registry import load_backtest_equity_curve
        curve = load_backtest_equity_curve(run_id, str(BACKTESTS_ROOT))
        
        return JSONResponse({
            "run_id": run_id,
            "equity_curve": curve,
        })
    except Exception as exc:
        logger.exception("Failed to load equity curve for %s: %s", run_id, exc)
        # Return empty curve instead of error to handle missing data gracefully
        return JSONResponse({
            "run_id": run_id,
            "equity_curve": [],
        })


@router.get("/api/logs/recent")
async def api_logs_recent(
    limit: int = Query(150, ge=10, le=500),
    level: Optional[str] = Query(None),
    contains: Optional[str] = Query(None),
    kind: Optional[str] = Query(None),
) -> JSONResponse:
    payload = _build_logs_payload(limit=limit, level=level, contains=contains, kind=kind)
    return JSONResponse(payload)


@router.get("/api/pm/log")
async def api_pm_log(
    limit: int = Query(200, ge=10, le=500),
    level: Optional[str] = Query(None),
    contains: Optional[str] = Query(None),
    kind: Optional[str] = Query(None),
) -> JSONResponse:
    payload = _build_logs_payload(limit=limit, level=level, contains=contains, kind=kind)
    return JSONResponse(payload)


@router.get("/api/system/time")
async def api_system_time() -> JSONResponse:
    now = datetime.utcnow().isoformat() + "Z"
    return JSONResponse({"utc": now})


@router.get("/api/health")
async def api_health() -> JSONResponse:
    """
    Aggregate engine status, log health, and market session info.
    """
    try:
        engine_snapshot = {"engines": [_load_paper_engine_status()]}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to compute engine status for health: %s", exc)
        engine_snapshot = {"engines": []}

    try:
        log_entries, _, _ = _tail_logs(limit=300)
        log_health = derive_log_health(log_entries)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to compute log health: %s", exc)
        log_health = {
            "last_log_ts": None,
            "last_error_ts": None,
            "error_count_recent": 0,
            "warning_count_recent": 0,
        }

    market_status = compute_market_status()

    payload = {
        "engine_status": engine_snapshot,
        "log_health": log_health,
        "market_status": market_status,
    }
    return JSONResponse(payload)

@router.get("/api/risk/summary")
def api_risk_summary() -> JSONResponse:
    state = store.load_checkpoint()
    cfg = load_app_config()
    risk_config = cfg.risk or {}
    risk_state = state.get("risk", {}) if state else {}
    portfolio_summary = load_paper_portfolio_summary()

    return JSONResponse(
        {
            "mode": risk_config.get("mode", "paper"),
            "per_trade_risk_pct": risk_config.get("per_trade_risk_pct"),
            "max_daily_loss_abs": risk_config.get("max_daily_loss_abs"),
            "max_daily_loss_pct": risk_config.get("max_daily_loss_pct"),
            "trading_halted": risk_state.get("trading_halted", False),
            "halt_reason": risk_state.get("halt_reason"),
            "current_day_pnl": portfolio_summary.get("daily_pnl"),
            "current_exposure": portfolio_summary.get("total_notional"),
        }
    )


@router.get("/api/strategy_performance")
def api_strategy_performance() -> JSONResponse:
    state = store.load_checkpoint()
    if not state or "strategies" not in state:
        return JSONResponse([])

    strategies = state["strategies"]
    performance_data = []
    for strategy_code, metrics in strategies.items():
        info = STRATEGY_REGISTRY.get(strategy_code)
        if info:
            performance_data.append(
                {
                    "name": info.name,
                    "code": info.strategy_code,
                    "pnl": metrics.get("day_pnl", 0.0),
                    "wins": metrics.get("win_trades", 0),
                    "losses": metrics.get("loss_trades", 0),
                    "entries": metrics.get("entry_count", 0),
                    "exits": metrics.get("exit_count", 0),
                }
            )
    return JSONResponse(performance_data)

@router.get("/api/quotes")
def api_quotes(keys: str | None = Query(default=None, description="Optional comma separated logical names")) -> JSONResponse:
    """
    Return latest quotes from artifacts/live_quotes.json (if present).
    This app no longer starts any WebSocket streamer; another process may update the file.
    """
    data = _load_quotes()
    if not keys: return JSONResponse(data)
    wanted = [k.strip() for k in keys.split(",") if k.strip()]
    filtered = {k: v for k, v in data.items() if k in wanted}
    return JSONResponse(filtered)

@router.get("/api/positions_normalized")
def api_positions_normalized() -> JSONResponse:
    try:
        state = _load_state()
    except FileNotFoundError:
        return JSONResponse({"positions": []})
    quotes = _load_quotes()
    ticks  = _load_ticks_cache(state)
    broker = state.get("broker") or {}
    raw_positions = broker.get("positions") or []
    normalized: List[Dict[str, Any]] = []
    for pos in raw_positions:
        if not isinstance(pos, dict): continue
        symbol = pos.get("symbol") or pos.get("tradingsymbol") or pos.get("trading_symbol")
        if not symbol: continue
        info = _parse_instrument(symbol)
        quantity = int(float(pos.get("quantity") or pos.get("net_quantity") or pos.get("qty") or 0))
        avg_price = _to_float(pos.get("avg_price") or pos.get("average_price") or pos.get("price")) or 0.0
        real_pnl  = _to_float(pos.get("realized_pnl") or pos.get("realised") or pos.get("realized")) or 0.0
        last_price, price_src = resolve_last_for_symbol_with_source(symbol, pos, quotes, ticks)
        unrealized = compute_unrealized_pnl(avg_price, last_price, quantity)
        lot_size = pos.get("lot_size") or pos.get("lotSize")
        base = info.get("base") or ""
        if lot_size is None and base:
            lot_size = LOT_SIZES.get(base) or LOT_SIZES.get(re.sub(r"[0-9]", "", base))
        if isinstance(lot_size, str):
            lot_size = lot_size.strip()
            try: lot_size = int(float(lot_size))
            except (TypeError, ValueError): lot_size = None
        lot_size_val = int(lot_size) if isinstance(lot_size, (int, float)) else None
        lots = (float(quantity) / lot_size_val) if (lot_size_val and lot_size_val != 0) else None
        normalized.append(
    {
        "symbol": symbol,
        "quantity": quantity,
        "avg_price": avg_price,
        "last_price": last_price,
        "price_source": price_src,   # <— new
        "realized_pnl": real_pnl,
        "unrealized_pnl": unrealized,
        "info": info,
        "lot_size": lot_size_val,
        "lots": lots,
    }
)
    return JSONResponse({"positions": normalized})

@router.get("/api/margins")
def api_margins() -> JSONResponse:
    mode = get_mode()
    if mode != "live":
        return JSONResponse({"mode": mode, "required": None, "available": None, "utilized": None, "span": None, "exposure": None, "final": None})
    try:
        kite = make_kite_client_from_env()
        broker = LiveBroker(kite)
        summary = broker.pretrade_margin_check([])
        summary["mode"] = mode
        return JSONResponse(summary)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Unable to fetch live margins: %s", exc)
        return JSONResponse({"mode": mode, "required": None, "available": None, "utilized": None, "span": None, "exposure": None, "final": None})

# --- Debug endpoint to verify auth quickly (non-streaming) ---
@router.get("/api/debug/auth")
def api_debug_auth() -> JSONResponse:
    detail = {}
    try:
        print_loaded_paths(logger)
        secrets = read_kite_api_secrets()
        access_token = read_kite_token()
        detail["has_api_key"] = bool(secrets.get("KITE_API_KEY"))
        detail["has_secret"] = bool(secrets.get("KITE_API_SECRET"))
        detail["has_access_token"] = bool(access_token)
        kite = make_kite_client_from_env()
        ok = token_is_valid(kite)
        detail["profile_ok"] = ok
        if ok:
            try:
                inst = kite.instruments(exchange="NSE")
                detail["instruments_sample"] = (len(inst) if isinstance(inst, list) else 0)
            except Exception as ixe:
                detail["instruments_error"] = repr(ixe)
        return JSONResponse({"ok": True, "detail": detail})
    except Exception as e:
        return JSONResponse({"ok": False, "error": repr(e), "detail": detail}, status_code=500)

@router.post("/api/resync")
def api_resync() -> JSONResponse:
    mode = get_mode()
    quotes = _load_quotes()
    try:
        if mode == "paper":
            store = JournalStateStore(mode="paper")
            state = store.rebuild_from_journal(today_only=True)
            state = store.compute_unrealized(state, quotes)
            store.save_checkpoint(state)
        else:
            kite = make_kite_client_from_env()
            cfg = _load_dashboard_config()
            state = bootstrap_state(cfg, "live", kite=kite, quotes=quotes)
        return JSONResponse({"ok": True, "mode": mode, "timestamp": state.get("timestamp")})
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Resync failed: {exc}") from exc

# ============================================================================
# Analytics API Endpoints (Strategy Analytics Engine v1)
# ============================================================================

@router.get("/api/analytics/summary")
def api_analytics_summary() -> JSONResponse:
    """
    Return combined analytics summary:
        {
          'daily': {...},
          'strategies': {...},
          'symbols': {...},
        }
    """
    try:
        from analytics.strategy_analytics import StrategyAnalyticsEngine
        
        mode = get_mode()
        journal_store = JournalStateStore(mode=mode)
        state_store = store  # Use global StateStore instance
        
        # Load config
        try:
            cfg = load_app_config()
            config_dict = cfg.__dict__ if hasattr(cfg, "__dict__") else {}
        except Exception:
            config_dict = {}
        
        # Create engine
        engine = StrategyAnalyticsEngine(
            journal_store=journal_store,
            state_store=state_store,
            logger=logger,
            config=config_dict,
        )
        
        # Load fills and generate payload
        engine.load_fills(today_only=True)
        payload = engine.generate_dashboard_payload()
        
        return JSONResponse(payload)
    except Exception as exc:
        logger.error("Analytics summary failed: %s", exc, exc_info=True)
        # Return empty analytics on error
        return JSONResponse({
            "daily": {
                "realized_pnl": 0.0,
                "num_trades": 0,
                "win_rate": 0.0,
                "loss_rate": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "pnl_distribution": {"wins": 0, "losses": 0, "breakeven": 0},
                "biggest_winner": 0.0,
                "biggest_loser": 0.0,
            },
            "strategies": {},
            "symbols": {},
            "error": str(exc),
        })

@router.get("/api/analytics/equity_curve")
def api_equity_curve(
    strategy: str | None = Query(default=None, description="Optional strategy filter"),
    symbol: str | None = Query(default=None, description="Optional symbol filter")
) -> JSONResponse:
    """
    Return equity curve and drawdown data.
    
    Query params:
        - strategy: Filter by strategy code (optional)
        - symbol: Filter by symbol (optional)
    
    Returns:
        {
          'equity_curve': [{'timestamp': ..., 'equity': ...}, ...],
          'drawdown': {'max_drawdown': ..., 'drawdown_series': [...]}
        }
    """
    try:
        from analytics.strategy_analytics import StrategyAnalyticsEngine
        
        mode = get_mode()
        journal_store = JournalStateStore(mode=mode)
        state_store = store
        
        # Load config
        try:
            cfg = load_app_config()
            config_dict = cfg.__dict__ if hasattr(cfg, "__dict__") else {}
        except Exception:
            config_dict = {}
        
        # Create engine
        engine = StrategyAnalyticsEngine(
            journal_store=journal_store,
            state_store=state_store,
            logger=logger,
            config=config_dict,
        )
        
        # Load fills
        engine.load_fills(today_only=True)
        
        # Compute equity curve
        curve = engine.compute_equity_curve(strategy=strategy, symbol=symbol)
        dd = engine.compute_drawdowns(curve)
        
        return JSONResponse({
            "equity_curve": curve,
            "drawdown": dd,
            "filters": {
                "strategy": strategy,
                "symbol": symbol,
            }
        })
    except Exception as exc:
        logger.error("Equity curve failed: %s", exc, exc_info=True)
        return JSONResponse({
            "equity_curve": [],
            "drawdown": {"max_drawdown": 0.0, "drawdown_series": []},
            "error": str(exc),
        })


@router.get("/api/performance")
async def api_performance() -> JSONResponse:
    """
    Return performance metrics from Performance Engine V2.
    
    Returns runtime_metrics.json if available, otherwise returns
    a default empty structure.
    """
    runtime_metrics_path = ARTIFACTS_ROOT / "analytics" / "runtime_metrics.json"
    
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
        with runtime_metrics_path.open("r", encoding="utf-8") as f:
            metrics = json.load(f)
        return JSONResponse(metrics)
    except Exception as exc:
        # Log error but return default structure
        logger.error("Failed to load performance metrics: %s", exc)
        return JSONResponse(default_metrics)


# ============================================================================
# Telemetry SSE Streaming Endpoint
# ============================================================================

@router.get("/api/telemetry/stream")
async def api_telemetry_stream(
    event_type: Optional[str] = Query(None, description="Filter by event type")
) -> StreamingResponse:
    """
    Stream telemetry events via Server-Sent Events (SSE).
    
    This endpoint provides real-time streaming of telemetry events from the
    TelemetryBus. Clients can optionally filter by event type.
    
    Args:
        event_type: Optional filter for specific event types
        
    Returns:
        StreamingResponse with text/event-stream content type
    """
    bus = get_telemetry_bus()
    
    async def event_generator():
        """Generate SSE events from telemetry bus."""
        last_index = 0
        
        # Get current buffer size to start streaming from
        last_index = len(bus.buffer)
        
        # Send initial heartbeat
        heartbeat = {
            "type": "heartbeat",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": {"status": "connected", "event_type_filter": event_type}
        }
        yield f"data: {json.dumps(heartbeat, default=str)}\n\n"
        
        try:
            while True:
                # Get new events since last check
                new_events = []
                current_size = len(bus.buffer)
                
                if current_size > last_index:
                    # Get new events
                    events_to_send = list(bus.buffer)[last_index:]
                    if event_type:
                        events_to_send = [e for e in events_to_send if e.get("type") == event_type]
                    new_events = events_to_send
                    last_index = current_size
                elif current_size < last_index:
                    # Buffer wrapped around, reset
                    last_index = 0
                
                # Send new events
                for event in new_events:
                    yield f"data: {json.dumps(event, default=str)}\n\n"
                
                # Send heartbeat to keep connection alive (every 5 seconds when no events)
                if not new_events:
                    heartbeat = {
                        "type": "heartbeat",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "payload": {}
                    }
                    yield f"data: {json.dumps(heartbeat, default=str)}\n\n"
                
                # Poll every 0.5 seconds
                await asyncio.sleep(0.5)
        
        except asyncio.CancelledError:
            logger.info("SSE stream cancelled for event_type=%s", event_type)
            raise
        except Exception as exc:
            logger.error("Error in SSE stream: %s", exc, exc_info=True)
            raise
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )


# ============================================================================
# Benchmarks API Endpoints
# ============================================================================

@router.get("/api/benchmarks")
async def api_benchmarks(
    days: int = Query(1, ge=1, le=365, description="Number of days to look back")
) -> JSONResponse:
    """
    Get benchmark index prices for the specified time window.
    
    Args:
        days: Number of days to look back (1-365)
        
    Returns:
        List of benchmark datapoints with NIFTY, BANKNIFTY, FINNIFTY prices
    """
    try:
        benchmarks = get_benchmarks(days=days)
        return JSONResponse(benchmarks)
    except Exception as exc:
        logger.error("Failed to load benchmarks: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load benchmarks: {str(exc)}"
        ) from exc


# ============================================================================
# Risk API Endpoints
# ============================================================================

@router.get("/api/risk/limits")
async def api_risk_limits() -> JSONResponse:
    """
    Get current risk limits configuration with source information.
    
    Returns:
        {
          "limits": { ...RiskLimits fields... },
          "source": {
            "base_config": "configs/dev.yaml",
            "overrides": "configs/risk_overrides.yaml"
          },
          "updated_at": <ISO timestamp or null>
        }
    """
    try:
        limits, metadata = load_risk_limits()
        return JSONResponse({
            "limits": {
                "max_daily_loss_rupees": limits.max_daily_loss_rupees,
                "max_daily_drawdown_pct": limits.max_daily_drawdown_pct,
                "max_trades_per_day": limits.max_trades_per_day,
                "max_trades_per_symbol_per_day": limits.max_trades_per_symbol_per_day,
                "max_loss_streak": limits.max_loss_streak,
            },
            "source": metadata.get("source", {}),
            "updated_at": metadata.get("updated_at"),
        })
    except Exception as exc:
        logger.error("Failed to load risk limits: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load risk limits: {str(exc)}"
        ) from exc


@router.post("/api/risk/limits")
async def api_risk_limits_update(request: Request) -> JSONResponse:
    """
    Update risk limits configuration.
    
    Request body should contain risk limit fields to update (partial patch):
    - max_daily_loss_rupees: float
    - max_daily_drawdown_pct: float
    - max_trades_per_day: int
    - max_trades_per_symbol_per_day: int
    - max_loss_streak: int
    
    Returns:
        { "status": "ok", "limits": { ...new limits... } }
    """
    try:
        body = await request.json()
        
        # Basic validation
        if "max_daily_loss_rupees" in body:
            if not isinstance(body["max_daily_loss_rupees"], (int, float)) or body["max_daily_loss_rupees"] <= 0:
                raise HTTPException(status_code=400, detail="max_daily_loss_rupees must be positive number")
        
        if "max_daily_drawdown_pct" in body:
            if not isinstance(body["max_daily_drawdown_pct"], (int, float)) or body["max_daily_drawdown_pct"] <= 0:
                raise HTTPException(status_code=400, detail="max_daily_drawdown_pct must be positive number")
        
        if "max_trades_per_day" in body:
            if not isinstance(body["max_trades_per_day"], int) or body["max_trades_per_day"] <= 0:
                raise HTTPException(status_code=400, detail="max_trades_per_day must be positive integer")
        
        if "max_trades_per_symbol_per_day" in body:
            if not isinstance(body["max_trades_per_symbol_per_day"], int) or body["max_trades_per_symbol_per_day"] <= 0:
                raise HTTPException(status_code=400, detail="max_trades_per_symbol_per_day must be positive integer")
        
        if "max_loss_streak" in body:
            if not isinstance(body["max_loss_streak"], int) or body["max_loss_streak"] <= 0:
                raise HTTPException(status_code=400, detail="max_loss_streak must be positive integer")
        
        # Save and get updated limits
        updated_limits = save_risk_limits(body)
        
        return JSONResponse({
            "status": "ok",
            "limits": {
                "max_daily_loss_rupees": updated_limits.max_daily_loss_rupees,
                "max_daily_drawdown_pct": updated_limits.max_daily_drawdown_pct,
                "max_trades_per_day": updated_limits.max_trades_per_day,
                "max_trades_per_symbol_per_day": updated_limits.max_trades_per_symbol_per_day,
                "max_loss_streak": updated_limits.max_loss_streak,
            }
        })
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to update risk limits: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update risk limits: {str(exc)}"
        ) from exc


@router.get("/api/risk/breaches")
async def api_risk_breaches() -> JSONResponse:
    """
    Get list of active risk limit breaches.
    
    Returns:
        { "breaches": [ ... ] }
        
        Each breach contains:
        - code: Breach code (e.g., "MAX_DAILY_LOSS")
        - severity: "warning" or "critical"
        - message: Human-readable description
        - metric: { current, limit, unit }
        - symbol: Trading symbol (or null)
        - since: ISO timestamp (or null)
    """
    try:
        limits, _ = load_risk_limits()
        breaches = compute_breaches(limits)
        return JSONResponse({"breaches": breaches})
    except Exception as exc:
        logger.error("Failed to compute risk breaches: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to compute risk breaches: {str(exc)}"
        ) from exc


@router.get("/api/risk/var")
async def api_risk_var(
    days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
    confidence: float = Query(0.95, ge=0.5, le=0.99, description="Confidence level (0.5-0.99)")
) -> JSONResponse:
    """
    Compute Value at Risk (VaR) from historical data.
    
    Args:
        days: Number of days to look back (1-365)
        confidence: Confidence level (0.5-0.99, default 0.95 for 95%)
        
    Returns:
        VaR computation results with:
        - var: Value at Risk in rupees
        - days: Number of days used
        - confidence: Confidence level
        - observations: Number of data points used
        - percentile: Percentile used for calculation
    """
    try:
        var_result = compute_var(days=days, confidence=confidence)
        return JSONResponse(var_result)
    except Exception as exc:
        logger.error("Failed to compute VaR: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to compute VaR: {str(exc)}"
        ) from exc


# Mount old static files (for backwards compatibility during transition)
if STATIC_DIR.exists():
    from starlette.staticfiles import StaticFiles as StarletteStaticFilesLegacy
    app.mount("/static", StarletteStaticFilesLegacy(directory=STATIC_DIR), name="static")

# Include all API routes BEFORE mounting the React UI at root
app.include_router(router)

# Mount React UI static assets BEFORE catch-all route
# This serves JS, CSS, images, etc. from /assets/
if REACT_BUILD_DIR.exists():
    print(f"[dashboard] Mounting React UI assets from {REACT_BUILD_DIR}")
    # Note: We don't use html=True here because we have a catch-all route below
    # that handles serving index.html for all non-asset paths
    assets_dir = REACT_BUILD_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="react-assets")
    
    # Also serve any root-level static files (like vite.svg, favicon, etc.)
    @app.get("/vite.svg")
    async def serve_vite_svg():
        from fastapi.responses import FileResponse
        svg_file = REACT_BUILD_DIR / "vite.svg"
        if svg_file.exists():
            return FileResponse(svg_file)
        raise HTTPException(status_code=404)
else:
    print(f"[dashboard] React UI directory not found: {REACT_BUILD_DIR}")

# SPA catch-all route: serve index.html for any non-API, non-asset path
# This ensures React Router can handle all frontend routes (e.g., /signals, /risk, /analytics)
# when users refresh the page or access them directly
from fastapi.responses import FileResponse

@app.get("/{full_path:path}")
async def spa_catch_all(full_path: str):
    """
    Catch-all route for React SPA.
    Serves index.html for all non-API paths, allowing React Router to handle routing.
    """
    # If path starts with "api/", this shouldn't have been caught here
    # (FastAPI should have matched the API routes first)
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API endpoint not found")
    
    # Serve the React app's index.html for all other paths
    index_file = REACT_BUILD_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    else:
        raise HTTPException(status_code=500, detail="React build not found")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("ui.dashboard:app", host="127.0.0.1", port=8765, reload=True)
