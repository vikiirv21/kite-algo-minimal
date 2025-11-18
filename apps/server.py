from __future__ import annotations

import asyncio
import atexit
import json
import logging
import os
import signal
import threading
import time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from kiteconnect import KiteConnect, exceptions as kite_exceptions
from pydantic import BaseModel, Field

from analytics.telemetry_bus import get_telemetry_bus
from apps.dashboard import router as dashboard_router
from core.config import load_config
from core.kite_env import (
    load_kite_env,
    make_kite_client_from_env,
    store_access_token,
    token_is_valid,
)
from core.kite_http import kite_request
from core.runtime_mode import get_mode as get_runtime_mode, on_change as on_mode_change, set_mode as write_runtime_mode
from engine.bootstrap import bootstrap_state
from scripts.run_day import start_engines_from_config
from ui.dashboard import LiveQuotesService, LIVE_QUOTES_ENABLED, QUOTES_PATH

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = BASE_DIR / "static"
DEFAULT_ARTIFACTS = BASE_DIR / "artifacts"
ARTIFACTS_ROOT = Path(os.environ.get("KITE_ALGO_ARTIFACTS", str(DEFAULT_ARTIFACTS))).expanduser()
if not ARTIFACTS_ROOT.is_absolute():
    ARTIFACTS_ROOT = (BASE_DIR / ARTIFACTS_ROOT).resolve()
CONFIG_PATH = Path(os.environ.get("KITE_DASHBOARD_CONFIG", str(BASE_DIR / "configs" / "dev.yaml")))
APP_CONFIG = load_config(str(CONFIG_PATH))
LOG_DIR = ARTIFACTS_ROOT / "logs"
SERVER_LOG_PATH = LOG_DIR / "server.log"
STATE_PATH = ARTIFACTS_ROOT / "paper_state.json"


def _setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(SERVER_LOG_PATH, maxBytes=5_000_000, backupCount=5)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    handler.setFormatter(formatter)
    root = logging.getLogger()
    if not any(isinstance(h, RotatingFileHandler) and getattr(h, "baseFilename", "") == str(SERVER_LOG_PATH) for h in root.handlers):
        root.addHandler(handler)
    root.setLevel(logging.INFO)


_setup_logging()


class RuntimeState:
    def __init__(self, mode: str) -> None:
        self._lock = threading.Lock()
        self.mode = mode
        self.token_ok = False
        self.last_sync: Optional[datetime] = None

    def update(self, **values: Any) -> None:
        with self._lock:
            for key, value in values.items():
                setattr(self, key, value)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "mode": self.mode,
                "token_ok": self.token_ok,
                "last_sync": self.last_sync.isoformat() if self.last_sync else None,
            }


class QuotesSupervisor:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._service: Optional[LiveQuotesService] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if not LIVE_QUOTES_ENABLED:
            logger.info("Live quotes service disabled via config toggle.")
            return
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._service = LiveQuotesService(QUOTES_PATH)
            self._thread = threading.Thread(target=self._run, name="quotes-service", daemon=True)
            self._thread.start()
            logger.info("QuotesSupervisor started.")

    def stop(self) -> None:
        with self._lock:
            service = self._service
            thread = self._thread
            self._service = None
            self._thread = None
        if service:
            service.stop()
        if thread:
            thread.join(timeout=5.0)
            logger.info("QuotesSupervisor stopped.")

    def _run(self) -> None:
        assert self._service is not None
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._service.run_forever())
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:  # noqa: BLE001
                pass
            loop.close()


class EngineSupervisor:
    def __init__(self, config_path: str = "configs/dev.yaml") -> None:
        self.config_path = config_path
        self._lock = threading.Lock()
        self._handles: Dict[str, Dict[str, Any]] = {}
        self._mode: Optional[str] = None
        self._live_stop = threading.Event()
        self._live_thread: Optional[threading.Thread] = None

    def start(self, mode: str) -> None:
        with self._lock:
            if self._mode == mode and self._is_running():
                return
            self._stop_locked()
            if mode == "paper":
                logger.info("Starting paper engines via EngineSupervisor.")
                self._handles = start_engines_from_config(config_path=self.config_path)
                self._mode = mode
            else:
                logger.info("Starting live supervisor loop.")
                self._start_live_locked()
                self._mode = mode

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()

    def _is_running(self) -> bool:
        if self._mode == "paper":
            return any(
                isinstance(info.get("thread"), threading.Thread) and info["thread"].is_alive()
                for info in self._handles.values()
            )
        if self._mode == "live":
            return bool(self._live_thread and self._live_thread.is_alive())
        return False

    def _stop_locked(self) -> None:
        if self._handles:
            for info in self._handles.values():
                engine = info.get("engine")
                if engine is not None and hasattr(engine, "running"):
                    setattr(engine, "running", False)
            for info in self._handles.values():
                thread = info.get("thread")
                if isinstance(thread, threading.Thread) and thread.is_alive():
                    thread.join(timeout=5.0)
            self._handles.clear()
            logger.info("Paper engines stopped.")
        if self._live_thread:
            self._live_stop.set()
            self._live_thread.join(timeout=5.0)
            self._live_thread = None
            logger.info("Live supervisor loop stopped.")
        self._live_stop.clear()
        self._mode = None

    def _start_live_locked(self) -> None:
        if self._live_thread and self._live_thread.is_alive():
            return
        self._live_stop.clear()
        self._live_thread = threading.Thread(target=self._live_loop, name="live-engine-supervisor", daemon=True)
        self._live_thread.start()

    def _live_loop(self) -> None:
        while not self._live_stop.wait(5.0):
            logger.info("Live EngineSupervisor heartbeat - strategies managed externally.")


class Reconciler:
    def __init__(self, runtime_state: RuntimeState, state_path: Path, poll_interval: float = 4.0) -> None:
        self._state = runtime_state
        self._state_path = state_path
        self._poll_interval = poll_interval
        self._mode = runtime_state.mode
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def start(self, mode: str) -> None:
        with self._lock:
            self._mode = mode
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="reconciler", daemon=True)
            self._thread.start()
            logger.info("Reconciler thread started.")

    def stop(self) -> None:
        with self._lock:
            self._stop.set()
            thread = self._thread
            self._thread = None
        if thread:
            thread.join(timeout=5.0)
            logger.info("Reconciler thread stopped.")

    def set_mode(self, mode: str) -> None:
        with self._lock:
            self._mode = mode

    def _run(self) -> None:
        backoff = 3.0
        while not self._stop.is_set():
            if self._mode != "live":
                time.sleep(2.0)
                continue
            try:
                self._sync_once()
                backoff = 3.0
                time.sleep(self._poll_interval)
            except kite_exceptions.TokenException:
                self._state.update(token_ok=False)
                time.sleep(backoff)
                backoff = min(backoff * 1.5, 30.0)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Reconciler loop failed: %s", exc)
                time.sleep(backoff)
                backoff = min(backoff * 1.5, 30.0)
            if self._stop.is_set():
                break

    def _sync_once(self) -> None:
        env = load_kite_env()
        if not env.access_token:
            self._state.update(token_ok=False)
            logger.warning("Reconciler skipped - missing access token.")
            time.sleep(5.0)
            return
        kite = make_kite_client_from_env(env, reload=True)
        token_ok = token_is_valid(kite)
        self._state.update(token_ok=token_ok)
        if not token_ok:
            logger.warning("Kite token invalid during reconciliation.")
            time.sleep(5.0)
            return

        orders = kite_request(kite.orders)
        positions = kite_request(kite.positions)
        self._write_state(orders or [], positions or [])
        self._state.update(last_sync=datetime.now(timezone.utc))

    def _write_state(self, orders: Any, positions: Any) -> None:
        target_path = self._state_path if self._mode == "paper" else self._state_path.with_name("live_state.json")
        current: Dict[str, Any] = {}
        if target_path.exists():
            try:
                current = json.loads(target_path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                current = {}
        broker = current.setdefault("broker", {})
        broker["orders"] = [self._sanitize(item) for item in orders]
        broker["positions"] = [self._sanitize(item) for item in positions]
        current.setdefault("meta", {})["mode"] = self._mode
        current["timestamp"] = datetime.now(timezone.utc).isoformat()

        tmp_path = target_path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(current, indent=2), encoding="utf-8")
        tmp_path.replace(target_path)

    @staticmethod
    def _sanitize(entry: Any) -> Any:
        if isinstance(entry, dict):
            clean: Dict[str, Any] = {}
            for key, value in entry.items():
                if isinstance(value, datetime):
                    clean[key] = value.isoformat()
                else:
                    clean[key] = value
            return clean
        return entry


class ServiceRegistry:
    def __init__(self) -> None:
        self.state = RuntimeState(get_runtime_mode())
        self._lock = threading.Lock()
        self._quotes = QuotesSupervisor()
        self._engines = EngineSupervisor()
        self._reconciler = Reconciler(self.state, STATE_PATH)
        self._bootstrap_state_snapshot(self.state.mode)
        on_mode_change(self._handle_mode_change)

    def start_all(self) -> None:
        with self._lock:
            self._quotes.start()
            self._engines.start(self.state.mode)
            self._reconciler.start(self.state.mode)
            logger.info("All services started.")
        self.refresh_token_state()

    def stop_all(self) -> None:
        with self._lock:
            self._reconciler.stop()
            self._engines.stop()
            self._quotes.stop()
            logger.info("All services stopped.")

    def refresh_token_state(self) -> bool:
        try:
            kite = make_kite_client_from_env()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Unable to build Kite client for health check: %s", exc)
            self.state.update(token_ok=False)
            return False
        ok = token_is_valid(kite)
        self.state.update(token_ok=ok)
        return ok

    def set_mode(self, mode: str) -> str:
        return write_runtime_mode(mode)

    def _handle_mode_change(self, mode: str) -> None:
        logger.info("Runtime mode updated to %s; refreshing services.", mode)
        self.state.update(mode=mode)
        self._bootstrap_state_snapshot(mode)
        self._engines.start(mode)
        self._reconciler.set_mode(mode)

    def _bootstrap_state_snapshot(self, mode: Optional[str] = None) -> Optional[Dict[str, Any]]:
        target_mode = mode or self.state.mode
        kite = None
        if target_mode == "live":
            try:
                kite = make_kite_client_from_env()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Unable to build Kite client for live bootstrap: %s", exc)
        try:
            return bootstrap_state(APP_CONFIG, target_mode, kite=kite)
        except Exception as exc:  # noqa: BLE001
            logger.warning("State bootstrap failed for mode=%s: %s", target_mode, exc)
            return None


registry = ServiceRegistry()


class LoginRequest(BaseModel):
    request_token: str = Field(..., min_length=4)


class ModeRequest(BaseModel):
    mode: str


app = FastAPI(title="Arthayukti Control Plane")
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.include_router(dashboard_router)


@app.on_event("startup")
async def _startup_event() -> None:
    registry.start_all()


@app.on_event("shutdown")
async def _shutdown_event() -> None:
    registry.stop_all()


@app.get("/healthz")
def healthz() -> JSONResponse:
    registry.refresh_token_state()
    snapshot = registry.state.snapshot()
    payload = {"ok": True, **snapshot}
    return JSONResponse(payload)


@app.post("/admin/login")
def admin_login(body: LoginRequest) -> JSONResponse:
    env = load_kite_env()
    kite = KiteConnect(api_key=env.api_key)
    try:
        session = kite.generate_session(body.request_token, api_secret=env.api_secret)
    except kite_exceptions.TokenException as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Kite login failed: {exc}") from exc
    access_token = session.get("access_token")
    if not access_token:
        raise HTTPException(status_code=500, detail="Kite did not return an access_token.")
    store_access_token(access_token)
    registry.refresh_token_state()
    return JSONResponse({"ok": True})


@app.post("/admin/mode")
def admin_mode(body: ModeRequest) -> JSONResponse:
    mode = registry.set_mode(body.mode)
    snapshot = registry.state.snapshot()
    snapshot["mode"] = mode
    return JSONResponse({"ok": True, **snapshot})


@app.post("/admin/start")
def admin_start() -> JSONResponse:
    registry.start_all()
    return JSONResponse({"ok": True, **registry.state.snapshot()})


@app.post("/admin/stop")
def admin_stop() -> JSONResponse:
    registry.stop_all()
    return JSONResponse({"ok": True})


@app.post("/admin/resync")
def admin_resync() -> JSONResponse:
    snapshot = registry.state.snapshot()
    mode = snapshot["mode"]
    try:
        state = registry._bootstrap_state_snapshot(mode)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Resync failed: {exc}") from exc
    registry.state.update(last_sync=datetime.now(timezone.utc))
    payload = {"ok": True, "mode": mode, "timestamp": state.get("timestamp") if state else None}
    return JSONResponse(payload)


@app.get("/api/portfolio/limits")
def get_portfolio_limits() -> JSONResponse:
    """
    Get current portfolio limits and usage.
    
    Returns equity, exposure limits, and per-strategy budgets.
    This endpoint requires a running engine with PortfolioEngine initialized.
    """
    try:
        # Try to get portfolio engine from registry
        # For now, we'll return a placeholder response indicating the feature is available
        # In a full implementation, we'd access the running engine's portfolio_engine instance
        
        from core.state_store import StateStore
        from core.portfolio_engine import PortfolioEngine, PortfolioConfig
        
        # Load portfolio config from APP_CONFIG
        portfolio_config_raw = APP_CONFIG.raw.get("portfolio")
        if not portfolio_config_raw:
            return JSONResponse({
                "ok": False,
                "error": "Portfolio engine not configured in config file"
            }, status_code=404)
        
        # Create a temporary PortfolioEngine instance for API response
        portfolio_config = PortfolioConfig.from_dict(portfolio_config_raw)
        state_store = StateStore()
        portfolio_engine = PortfolioEngine(
            portfolio_config=portfolio_config,
            state_store=state_store,
            logger_instance=logger,
        )
        
        limits = portfolio_engine.get_portfolio_limits()
        return JSONResponse({
            "ok": True,
            **limits
        })
        
    except Exception as exc:
        logger.error("Failed to get portfolio limits: %s", exc, exc_info=True)
        return JSONResponse({
            "ok": False,
            "error": str(exc)
        }, status_code=500)


@app.get("/api/telemetry/stream")
async def telemetry_stream(event_type: Optional[str] = None) -> StreamingResponse:
    """
    Stream real-time telemetry events via Server-Sent Events (SSE).
    
    Query Parameters:
    - event_type (optional): Filter events by type (e.g., 'signal_event', 'order_event')
    
    Returns:
        StreamingResponse with SSE-formatted events
        
    Event Types:
    - signal_event: Strategy signals generated
    - indicator_event: Indicator calculations
    - order_event: Order lifecycle events
    - position_event: Position updates
    - engine_health: Engine health metrics
    - decision_trace: Strategy decision traces
    - universe_scan: Universe scanning results
    - performance_update: Performance metrics updates
    """
    telemetry_bus = get_telemetry_bus()
    
    return StreamingResponse(
        telemetry_bus.stream_events(event_type=event_type),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@app.get("/api/telemetry/stats")
def telemetry_stats() -> JSONResponse:
    """
    Get telemetry bus statistics.
    
    Returns:
        JSON with buffer stats and event counts
    """
    telemetry_bus = get_telemetry_bus()
    stats = telemetry_bus.get_stats()
    return JSONResponse({"ok": True, **stats})


@app.get("/api/telemetry/events")
def telemetry_events(event_type: Optional[str] = None, limit: int = 100) -> JSONResponse:
    """
    Get recent telemetry events.
    
    Query Parameters:
    - event_type (optional): Filter events by type
    - limit (optional): Maximum number of events to return (default: 100, max: 1000)
    
    Returns:
        JSON with list of recent events
    """
    telemetry_bus = get_telemetry_bus()
    limit = min(limit, 1000)  # Cap at 1000 events
    events = telemetry_bus.get_recent_events(event_type=event_type, limit=limit)
    return JSONResponse({"ok": True, "events": events, "count": len(events)})


def _install_signal_handlers() -> None:
    if os.name != "nt":
        return

    def _handle_signal(signum, _frame) -> None:  # type: ignore[override]
        logger.info("Signal %s received; stopping services.", signum)
        registry.stop_all()

    signal.signal(signal.SIGINT, _handle_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handle_signal)


_install_signal_handlers()
atexit.register(registry.stop_all)


def main() -> None:
    uvicorn.run(
        "apps.server:app",
        host=os.environ.get("UVICORN_HOST", "0.0.0.0"),
        port=int(os.environ.get("UVICORN_PORT", "9000")),
        reload=bool(os.environ.get("UVICORN_RELOAD", "1") == "1"),
    )


if __name__ == "__main__":
    main()
