from __future__ import annotations

import argparse
import logging
import sys
import threading
from typing import Tuple

import uvicorn
from kiteconnect import KiteConnect, exceptions as kite_exceptions

from core.broker_sync import rotate_day_files, sync_from_kite
from core.config import load_config
from core.kite_env import load_kite_env, make_kite_client_from_env
from core.logging_utils import setup_logging
from core.json_log import install_engine_json_logger
from scripts.live_quotes import run_live_quotes_service
from scripts.run_day import EngineKind, start_engines_from_config
from apps.dashboard import app as dashboard_app

log = logging.getLogger(__name__)
DEFAULT_CONFIG = "configs/dev.yaml"
ALL_ENGINES: Tuple[EngineKind, ...] = ("fno", "options", "equity")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start engines, live quotes streamer, and dashboard in one process."
    )
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG,
        help=f"Path to YAML config file (default: {DEFAULT_CONFIG}).",
    )
    parser.add_argument(
        "--dashboard-host",
        default="127.0.0.1",
        help="Dashboard bind host (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--dashboard-port",
        type=int,
        default=8000,
        help="Dashboard port (default: 8000).",
    )
    return parser.parse_args()


def _preflight_token(kite: KiteConnect) -> bool:
    try:
        profile = kite.profile()
        user_id = profile.get("user_id") or profile.get("USER_ID")
        log.info("Kite preflight OK. User id=%s", user_id)
        return True
    except kite_exceptions.TokenException as exc:
        log.error("Kite preflight failed, token likely invalid: %s", exc)
        return False
    except Exception as exc:  # noqa: BLE001
        log.error("Kite preflight failed with unexpected error: %s", exc, exc_info=True)
        return False


def main() -> None:
    args = _parse_args()
    cfg = load_config(args.config)
    setup_logging(cfg.logging)
    install_engine_json_logger()

    env = load_kite_env()
    if not env.access_token:
        print(
            "Kite access token missing. Run 'python -m scripts.run_day --login --engines all' to login first.",
            file=sys.stderr,
        )
        sys.exit(1)

    kite = make_kite_client_from_env(env)
    if not _preflight_token(kite):
        print(
            "Stored Kite token invalid or expired. Please run:\n"
            "  python -m scripts.run_day --login --engines all",
            file=sys.stderr,
        )
        sys.exit(1)

    rotate_day_files()
    try:
        sync_from_kite(kite)
    except Exception as exc:  # noqa: BLE001
        log.warning("[run_all] broker sync skipped: %s", exc)

    engine_handles = start_engines_from_config(
        config_path=args.config,
        engines=ALL_ENGINES,
        cfg=cfg,
    )
    if not engine_handles:
        log.error("Failed to start trading engines; aborting.")
        sys.exit(1)

    quotes_stop = threading.Event()

    uvicorn_config = uvicorn.Config(
        dashboard_app,
        host=args.dashboard_host,
        port=args.dashboard_port,
        log_config=None,
    )
    server = uvicorn.Server(uvicorn_config)

    def _quotes_worker() -> None:
        try:
            run_live_quotes_service(env, stop_event=quotes_stop)
        except RuntimeError as exc:
            log.error("Live quotes streamer exited: %s", exc)
            quotes_stop.set()
            server.should_exit = True
        except Exception:  # noqa: BLE001
            log.exception("Live quotes streamer crashed.")
            quotes_stop.set()
            server.should_exit = True

    quotes_thread = threading.Thread(target=_quotes_worker, name="live-quotes", daemon=True)
    quotes_thread.start()

    log.info(
        "All engines started. Dashboard running on http://%s:%s",
        args.dashboard_host,
        args.dashboard_port,
    )

    try:
        server.run()
    except KeyboardInterrupt:
        log.info("KeyboardInterrupt received. Stopping services...")
    finally:
        quotes_stop.set()
        quotes_thread.join(timeout=5.0)
        log.info("run_all shutdown complete.")


if __name__ == "__main__":
    main()
