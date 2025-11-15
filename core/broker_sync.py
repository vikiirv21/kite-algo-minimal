"""Broker synchronization and daily rotation helpers."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from kiteconnect import KiteConnect

BASE_DIR = Path(__file__).resolve().parents[1]
ARTIFACTS = BASE_DIR / "artifacts"
ARTIFACTS.mkdir(parents=True, exist_ok=True)
HISTORY = ARTIFACTS / "history"
STATE_PATH = ARTIFACTS / "paper_state.json"
ORDERS_PATH = ARTIFACTS / "orders.csv"
SIGNALS_PATH = ARTIFACTS / "signals.csv"


def rotate_day_files(today: str | None = None) -> None:
    """
    Moves yesterday's artifacts into history/<date>/.
    Creates new clean csv/json files for today.
    """
    HISTORY.mkdir(exist_ok=True)
    if today is None:
        today = datetime.now().strftime("%Y-%m-%d")

    today_dir = HISTORY / today
    today_dir.mkdir(exist_ok=True)

    for p in [ORDERS_PATH, SIGNALS_PATH, STATE_PATH]:
        if p.exists():
            target = today_dir / p.name.replace(".", f"_{today}.")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, target)
            if p.suffix == ".csv":
                header = (
                    "timestamp,symbol,side,quantity,price,status,tf,profile,"
                    "strategy,parent_signal_timestamp,underlying,extra\n"
                )
                p.write_text(header, encoding="utf-8")


def sync_from_kite(kite: KiteConnect, state_path: Path = STATE_PATH) -> None:
    """
    Fetches live positions and orders from Kite,
    merges into local paper_state.json.
    """
    try:
        positions = kite.positions()
        orders = kite.orders()
    except Exception as exc:  # noqa: BLE001
        print(f"[broker_sync] Failed to fetch from Kite: {exc}")
        return

    state: dict = {}
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            state = {}

    state.setdefault("broker", {})
    state["broker"]["positions"] = positions.get("net", [])
    state["broker"]["orders"] = orders
    state["meta"] = state.get("meta", {})
    state["meta"]["last_broker_sync"] = datetime.now().isoformat()

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"[broker_sync] Synced {len(positions.get('net', []))} positions "
        f"and {len(orders)} orders from Kite."
    )
