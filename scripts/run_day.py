"""
Unified runbook for daily trading.

Features:
- (Optional) Interactive Kite login (updates secrets/kite_tokens.env with the latest access token).
- Starts FnO futures paper engine, index options paper engine, and/or equity paper engine.
- Uses the existing configs/dev.yaml file.

Usage examples:

    # Login only (refresh tokens, don't start engines)
    python -m scripts.run_day --login --engines none

    # Reuse stored token and run every engine
    python -m scripts.run_day --engines all

    # Login + run options only
    python -m scripts.run_day --login --engines options

    # Reuse stored token for just the FnO futures engine
    python -m scripts.run_day --engines fno
"""

from __future__ import annotations

import argparse
import logging
import sys
import threading
import time
from typing import Any, Dict, List, Literal, Sequence

from datetime import date, datetime, timezone

from core.config import AppConfig, load_config
from core.logging_utils import setup_logging
from core.json_log import install_engine_json_logger
from engine.paper_engine import PaperEngine
from engine.options_paper_engine import OptionsPaperEngine
from engine.equity_paper_engine import EquityPaperEngine
# Unified file-based secrets (no OS env at runtime)

from kiteconnect import KiteConnect, exceptions as kite_exceptions
from core.broker_sync import rotate_day_files, sync_from_kite
from engine.bootstrap import bootstrap_state
from core.state_store import JournalStateStore, StateStore, store, make_fresh_state_from_config
from core.scanner import MarketScanner
from scripts.login_kite import interactive_login_files
from core.kite_env import (
    make_kite_client_from_files,
    describe_creds_for_logs,    # optional but handy for logging
    read_tokens,
)



logger = logging.getLogger(__name__)
log = logger

EngineKind = Literal["fno", "options", "equity"]
LOGIN_HINT = "python -m scripts.run_day --login --engines none"


def _start_engine_thread(engine, name: str) -> threading.Thread:
    t = threading.Thread(target=engine.run_forever, name=name, daemon=True)
    t.start()
    return t


def _gather_engine_status(registry: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    status: Dict[str, Dict[str, Any]] = {}
    for kind, payload in registry.items():
        engine = payload.get("engine")
        thread = payload.get("thread")
        running = bool(getattr(engine, "running", False))
        entry = {
            "running": running,
            "thread_alive": bool(thread.is_alive()) if isinstance(thread, threading.Thread) else False,
            "status": "running" if running else "stopped",
        }
        error = getattr(engine, "last_error", None) or getattr(engine, "error", None)
        if error:
            entry["error"] = str(error)
            entry["status"] = "error"
        mode = getattr(engine, "mode", None)
        if mode is not None:
            entry["mode"] = getattr(mode, "value", str(mode))
        status[kind] = entry
    return status


def _gather_pnl_summary(registry: Dict[str, Dict[str, Any]]) -> Dict[str, float]:
    realized = 0.0
    open_positions = 0
    for payload in registry.values():
        engine = payload.get("engine")
        broker = getattr(engine, "paper_broker", None)
        if broker is None:
            continue
        positions = getattr(broker, "positions", {}) or {}
        for pos in positions.values():
            realized += float(getattr(pos, "realized_pnl", 0.0) or 0.0)
            qty = getattr(pos, "quantity", 0)
            if qty:
                open_positions += 1
    return {
        "day_pnl": realized,
        "realized_pnl": realized,
        "unrealized_pnl": 0.0,
        "open_positions": open_positions,
        "num_trades": 0,
        "win_trades": 0,
        "loss_trades": 0,
        "win_rate": 0.0,
        "largest_win": 0.0,
        "largest_loss": 0.0,
        "avg_r": 0.0,
    }


def _collect_positions_from_registry(
    registry: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    aggregated: Dict[str, Dict[str, Any]] = {}
    for info in registry.values():
        engine = info.get("engine")
        broker = getattr(engine, "paper_broker", None)
        if broker is None:
            continue
        positions = getattr(broker, "positions", {}) or {}
        for symbol, pos in positions.items():
            aggregated[symbol] = {
                "symbol": symbol,
                "quantity": getattr(pos, "quantity", 0),
                "avg_price": getattr(pos, "avg_price", 0.0),
                "realized_pnl": getattr(pos, "realized_pnl", 0.0),
            }
    return list(aggregated.values())


def _utcnow_iso() -> str:
    return datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()


def _mode_from_config(cfg: AppConfig) -> str:
    trading = getattr(cfg, "trading", {}) or {}
    mode = trading.get("mode") or getattr(cfg, "mode", "PAPER")
    return str(mode or "PAPER").upper()


def _load_or_init_runtime_state(cfg: AppConfig) -> tuple[Dict[str, Any], bool]:
    existing = store.load_checkpoint()
    if isinstance(existing, dict):
        positions = len(existing.get("positions") or [])
        open_orders = len(existing.get("open_orders") or [])
        log.info(
            "State loaded from checkpoint (mode=%s, positions=%d, open_orders=%d)",
            existing.get("mode"),
            positions,
            open_orders,
        )
        return existing, True

    fresh = make_fresh_state_from_config(cfg)
    log.info("Initialized fresh runtime state from config (mode=%s)", fresh.get("mode"))
    return fresh, False


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_live_positions(payload: Any) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    if isinstance(payload, dict):
        entries = payload.get("net") or payload.get("day") or []
    elif isinstance(payload, list):
        entries = payload

    positions: List[Dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        symbol = entry.get("tradingsymbol") or entry.get("symbol")
        if not symbol:
            continue
        positions.append(
            {
                "symbol": symbol,
                "quantity": _safe_float(entry.get("quantity") or entry.get("net_quantity") or 0.0),
                "avg_price": _safe_float(entry.get("average_price") or 0.0),
                "last_price": _safe_float(entry.get("last_price") or entry.get("last") or 0.0),
                "realized_pnl": _safe_float(entry.get("realised") or entry.get("realized") or 0.0),
                "unrealized_pnl": _safe_float(entry.get("unrealised") or entry.get("unrealized") or 0.0),
            }
        )
    return positions


CLOSED_ORDER_STATUSES = {
    "COMPLETE",
    "CANCELLED",
    "CANCELED",
    "REJECTED",
    "CANCELLED AMO",
}


def _normalize_open_orders(raw_orders: Any) -> List[Dict[str, Any]]:
    orders_list = raw_orders if isinstance(raw_orders, list) else []
    open_orders: List[Dict[str, Any]] = []
    for entry in orders_list:
        if not isinstance(entry, dict):
            continue
        status = (entry.get("status") or "").upper()
        if status in CLOSED_ORDER_STATUSES:
            continue
        open_orders.append(
            {
                "order_id": entry.get("order_id"),
                "symbol": entry.get("tradingsymbol") or entry.get("symbol"),
                "status": status,
                "quantity": _safe_float(entry.get("quantity") or entry.get("pending_quantity") or 0.0),
                "price": _safe_float(entry.get("price") or entry.get("trigger_price") or 0.0),
                "side": (entry.get("transaction_type") or entry.get("side") or "").upper(),
            }
        )
    return open_orders


def _reconcile_live_state(kite: KiteConnect, state: Dict[str, Any]) -> None:
    try:
        broker_positions = kite.positions()
        broker_orders = kite.orders()
    except Exception as exc:  # noqa: BLE001
        log.error("Failed to reconcile state with broker: %s", exc, exc_info=True)
        return

    positions = _normalize_live_positions(broker_positions)
    open_orders = _normalize_open_orders(broker_orders)
    state["positions"] = positions
    state["open_orders"] = open_orders
    state["last_broker_sync_ts"] = _utcnow_iso()
    log.info(
        "Reconciled positions with broker, %d positions, %d open orders",
        len(positions),
        len(open_orders),
    )
    store.save_checkpoint(state)


def _seed_paper_state_from_journal(state: Dict[str, Any]) -> None:
    journal_store = JournalStateStore(mode="paper")
    rebuilt = journal_store.rebuild_from_journal(today_only=True)
    if not rebuilt:
        return
    broker_state = rebuilt.get("broker") or {}
    positions = broker_state.get("positions") or []
    if positions:
        state["positions"] = positions
    meta = rebuilt.get("meta") or {}
    equity = state.setdefault("equity", {})
    equity["realized_pnl"] = _safe_float(meta.get("total_realized_pnl"), equity.get("realized_pnl", 0.0))
    equity["unrealized_pnl"] = _safe_float(meta.get("total_unrealized_pnl"), equity.get("unrealized_pnl", 0.0))
    state["last_broker_sync_ts"] = _utcnow_iso()
    store.save_checkpoint(state)
    log.info(
        "Paper state rebuilt from journal entries (positions=%d)",
        len(state.get("positions") or []),
    )


def _ensure_daily_universe(kite: KiteConnect, cfg: AppConfig, runtime_state: Dict[str, Any]) -> Dict[str, Any]:
    today_str = date.today().isoformat()
    current = runtime_state.get("universe")
    if isinstance(current, dict) and current.get("date") == today_str:
        return current

    scanner = MarketScanner(kite, cfg)
    data = scanner.load_today()
    if not data:
        data = scanner.scan()
        if data:
            scanner.save(data)

    if not isinstance(data, dict):
        data = {
            "date": today_str,
            "asof": datetime.utcnow().isoformat() + "Z",
            "fno": [],
            "meta": {},
        }
    runtime_state["universe"] = data
    try:
        store.save_checkpoint(runtime_state)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to persist universe checkpoint: %s", exc)
    return data


def _publish_runtime_state(registry: Dict[str, Dict[str, Any]], state: Dict[str, Any]) -> None:
    disk_state = store.load_checkpoint()
    if isinstance(disk_state, dict):
        state.clear()
        state.update(disk_state)

    engines = _gather_engine_status(registry)
    pnl = _gather_pnl_summary(registry)
    state["engines"] = engines
    state["pnl"] = pnl
    equity = state.setdefault("equity", {})
    equity["realized_pnl"] = pnl.get("realized_pnl", equity.get("realized_pnl", 0.0))
    equity["unrealized_pnl"] = pnl.get("unrealized_pnl", equity.get("unrealized_pnl", 0.0))
    equity["day_pnl"] = pnl.get("day_pnl", equity.get("day_pnl", 0.0))

    snapshot_date = datetime.utcnow().date().isoformat()
    state["summary"] = {
        "date": snapshot_date,
        "realized_pnl": pnl.get("realized_pnl", 0.0),
        "num_trades": pnl.get("num_trades", 0),
        "win_trades": pnl.get("win_trades", 0),
        "loss_trades": pnl.get("loss_trades", 0),
        "win_rate": pnl.get("win_rate", 0.0),
        "open_positions": pnl.get("open_positions", 0),
        "largest_win": pnl.get("largest_win", 0.0),
        "largest_loss": pnl.get("largest_loss", 0.0),
        "avg_r": pnl.get("avg_r", 0.0),
        "note": "",
    }
    if state.get("mode", "PAPER").upper() != "LIVE":
        positions = _collect_positions_from_registry(registry)
        if positions:
            state["positions"] = positions
    state["last_heartbeat_ts"] = _utcnow_iso()
    store.save_checkpoint(state)
    store.append_log(
        {
            "kind": "heartbeat",
            "engines": engines,
            "pnl": pnl,
        }
    )


def _preflight_check_token(kite: KiteConnect) -> bool:
    """
    Try a simple profile call to verify that api_key/access_token pair is valid.
    """
    try:
        profile = kite.profile()
        user_id = profile.get("user_id") or profile.get("USER_ID", "")
        log.info("Kite preflight OK. User id=%s", user_id)
        return True
    except kite_exceptions.TokenException as exc:
        log.error("Kite preflight failed, token likely invalid: %s", exc)
        return False
    except Exception as exc:  # noqa: BLE001
        log.error("Kite preflight failed with unexpected error: %s", exc, exc_info=True)
        return False


def _resolve_engine_selection(choice: str) -> List[EngineKind]:
    if choice == "all":
        return ["fno", "options", "equity"]
    if choice == "none":
        return []
    return [choice]  # argparse restricts values


def _ensure_token_files_available() -> None:
    try:
        access_token, _public_token, login_ts, _token_key = read_tokens()
    except Exception as exc:  # noqa: BLE001
        log.error("Unable to read Kite tokens: %s", exc)
        log.error("Run `%s` to refresh credentials.", LOGIN_HINT)
        raise SystemExit(1) from exc

    if not access_token:
        log.error("No stored Kite token found in secrets/kite_tokens.env.")
        log.error("Run `%s` to refresh credentials.", LOGIN_HINT)
        raise SystemExit(1)

    if login_ts:
        log.info("Last Kite login timestamp from tokens file: %s", login_ts)


def _build_kite_client(force_login: bool) -> KiteConnect:
    """
    Return a Kite client, optionally forcing an interactive login beforehand.
    """
    if force_login:
        log.info("Running interactive Kite login (forced by --login)...")
        try:
            interactive_login_files()
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001
            log.error("Interactive login failed: %s", exc, exc_info=True)
            raise SystemExit(1) from exc
    else:
        _ensure_token_files_available()
        log.info(
            "Reusing existing Kite token from secrets/kite_tokens.env (%s)",
            describe_creds_for_logs(),
        )

    try:
        kite = make_kite_client_from_files()
    except Exception as exc:  # noqa: BLE001
        log.error("Unable to build Kite client from stored credentials: %s", exc)
        log.error("Run `%s` to refresh credentials.", LOGIN_HINT)
        raise SystemExit(1) from exc

    if not _preflight_check_token(kite):
        if force_login:
            log.error(
                "Freshly generated Kite token failed preflight. Please rerun `%s`.",
                LOGIN_HINT,
            )
        else:
            log.error(
                "Stored Kite token invalid/expired. Run `%s` to refresh tokens.",
                LOGIN_HINT,
            )
        raise SystemExit(1)

    return kite


def _extract_universe_overrides(
    universe: Optional[Dict[str, Any]]
) -> tuple[Optional[List[str]], Optional[Dict[str, str]]]:
    if not isinstance(universe, dict):
        return None, None
    logicals = [str(sym).strip().upper() for sym in universe.get("fno", []) if sym]
    meta = universe.get("meta") or {}
    symbol_map: Dict[str, str] = {}
    for logical in logicals:
        info = meta.get(logical) or {}
        tradingsymbol = info.get("tradingsymbol")
        if tradingsymbol:
            symbol_map[logical] = str(tradingsymbol).strip().upper()
    return (logicals or None, symbol_map or None)


def start_engines_from_config(
    config_path: str = "configs/dev.yaml",
    engines: Sequence[EngineKind] | None = None,
    cfg: AppConfig | None = None,
    kite: KiteConnect | None = None,
    runtime_universe: Optional[Dict[str, Any]] = None,
) -> Dict[EngineKind, Dict[str, Any]]:
    """
    Start the requested engines in daemon threads using the provided config.

    Returns a dict keyed by engine kind containing {"engine": obj, "thread": thread}.
    """
    desired = tuple(dict.fromkeys(engines or ("fno", "options", "equity")))
    cfg_obj = cfg or load_config(config_path)
    registry: Dict[EngineKind, Dict[str, Any]] = {}

    logical_override, symbol_map_override = _extract_universe_overrides(runtime_universe)

    for kind in desired:
        engine = None
        if kind == "fno":
            journal_store = JournalStateStore(mode="paper")
            checkpoint_store = StateStore(checkpoint_path=journal_store.checkpoint_path)
            engine = PaperEngine(
                cfg_obj,
                journal_store=journal_store,
                checkpoint_store=checkpoint_store,
                kite=kite,
                logical_universe_override=logical_override,
                symbol_map_override=symbol_map_override,
            )
        elif kind == "options":
            engine = OptionsPaperEngine(
                cfg_obj,
                kite=kite,
                logical_underlyings_override=logical_override,
                underlying_futs_override=symbol_map_override,
            )
        elif kind == "equity":
            engine = EquityPaperEngine(cfg_obj, kite=kite)
        else:
            logger.warning("Unknown engine type requested: %s", kind)
            continue

        thread = _start_engine_thread(engine, f"engine-{kind}")
        registry[kind] = {"engine": engine, "thread": thread}
        logger.info("Started %s engine in background thread.", kind)

    if not registry:
        logger.error("No engines started. Selection=%s", desired)
    return registry


def main() -> None:
    parser = argparse.ArgumentParser(description="Unified daily runbook for algo trading (paper mode).")
    parser.add_argument(
        "--config",
        default="configs/dev.yaml",
        help="Path to YAML config file (default: configs/dev.yaml).",
    )
    parser.add_argument(
        "--engines",
        choices=["none", "all", "fno", "equity", "options"],
        default="all",
        help="Which engines to run (default: all). Use 'none' with --login to refresh tokens only.",
    )
    parser.add_argument(
        "--login",
        action="store_true",
        help="Perform interactive Kite login before starting engines.",
    )

    args = parser.parse_args()

    cfg = load_config(args.config)
    setup_logging(cfg.logging)
    install_engine_json_logger()
    runtime_state, state_from_checkpoint = _load_or_init_runtime_state(cfg)
    desired_mode = _mode_from_config(cfg)
    runtime_state["mode"] = desired_mode

    logger.info("Runbook starting with config=%s, engines=%s", args.config, args.engines)

    selected_engines = _resolve_engine_selection(args.engines)

    if not args.login and not selected_engines:
        logger.info("No login requested and --engines none provided. Nothing to do.")
        return

    kite = _build_kite_client(force_login=args.login)

    if not selected_engines:
        logger.info("Login/preflight completed; not starting engines (--engines none).")
        return

    if desired_mode == "LIVE":
        _reconcile_live_state(kite, runtime_state)
    elif desired_mode == "PAPER" and not state_from_checkpoint:
        _seed_paper_state_from_journal(runtime_state)

    universe_snapshot = None
    try:
        universe_snapshot = _ensure_daily_universe(kite, cfg, runtime_state)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to refresh scanner universe: %s", exc)

    # --- Daily rotation ---
    rotate_day_files()

    # --- Broker sync (if token is valid) ---
    try:
        sync_from_kite(kite)
    except Exception as e:  # noqa: BLE001
        logger.warning("[run_day] broker sync skipped: %s", e)

    try:
        bootstrap_state(cfg, "paper")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Bootstrap state refresh failed: %s", exc)

    try:
        engine_handles = start_engines_from_config(
            config_path=args.config,
            engines=selected_engines,
            cfg=cfg,
            kite=kite,
            runtime_universe=universe_snapshot,
        )
    except RuntimeError as exc:
        logger.error(
            "Failed to start engines because FnO instruments could not be fetched from Kite "
            "(likely a transient network/API issue). Please check connectivity and retry. "
            "Underlying error: %s",
            exc,
        )
        sys.exit(1)
    if not engine_handles:
        logger.error("No engines selected. Nothing to run.")
        return

    threads = [
        info["thread"]
        for info in engine_handles.values()
        if isinstance(info, dict) and isinstance(info.get("thread"), threading.Thread)
    ]
    if not threads:
        logger.error("Engine threads failed to start; aborting.")
        return

    logger.info("All requested engines started. Press Ctrl+C to stop.")
    heartbeat_interval = 3.0
    last_heartbeat = 0.0
    try:
        _publish_runtime_state(engine_handles, runtime_state)
        last_heartbeat = time.time()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Unable to publish initial runtime state: %s", exc)

    def _persist_checkpoint() -> None:
        try:
            store.save_checkpoint(runtime_state)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Unable to persist runtime state checkpoint: %s", exc)

    try:
        while any(t.is_alive() for t in threads):
            time.sleep(1.0)
            now = time.time()
            if now - last_heartbeat >= heartbeat_interval:
                try:
                    _publish_runtime_state(engine_handles, runtime_state)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Heartbeat publish failed: %s", exc)
                last_heartbeat = now
    except KeyboardInterrupt:
        logger.info("Runbook interrupted by user. Engines will stop on their own loop conditions.")
    finally:
        _persist_checkpoint()


if __name__ == "__main__":
    main()
