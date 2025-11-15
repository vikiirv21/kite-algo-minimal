from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from kiteconnect import KiteConnect

from core.kite_http import kite_request
from core.state_store import JournalStateStore

logger = logging.getLogger(__name__)


def bootstrap_state(
    cfg: Optional[Any],
    mode: str,
    *,
    kite: Optional[KiteConnect] = None,
    quotes: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build or refresh the runtime state for PAPER or LIVE mode.
    """

    normalized_mode = (mode or "paper").strip().lower()
    store = JournalStateStore(mode=normalized_mode)
    store.ensure_dirs()

    if normalized_mode == "paper":
        state = store.load_latest_checkpoint()
        if state is None:
            state = store.rebuild_from_journal(today_only=True)
        state = store.compute_unrealized(state, quotes or {})
    else:
        if kite is None:
            raise ValueError("bootstrap_state(mode='live') requires a KiteConnect client.")
        raw_positions = kite_request(kite.positions)
        raw_orders = kite_request(kite.orders)
        normalized_orders = [JournalStateStore.normalize_order(row) for row in raw_orders or []]
        store.append_orders(normalized_orders)
        state = build_state_from_kite(raw_positions, normalized_orders)
        state = store.compute_unrealized(state, quotes or {})

    _apply_config_meta(state, cfg)
    store.save_checkpoint(state)
    return state


def build_state_from_kite(
    positions_payload: Optional[Dict[str, Any]],
    orders: Optional[Iterable[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Convert Kite positions/orders payloads into the dashboard state format.
    """

    orders_list = [JournalStateStore.normalize_order(order) for order in (orders or [])]

    net_positions = []
    if isinstance(positions_payload, dict):
        net_positions = positions_payload.get("net") or positions_payload.get("day") or []
    elif isinstance(positions_payload, list):
        net_positions = positions_payload

    total_realized = 0.0
    total_unreal = 0.0
    positions: List[Dict[str, Any]] = []

    for entry in net_positions:
        symbol = entry.get("tradingsymbol") or entry.get("symbol")
        if not symbol:
            continue
        qty = int(float(entry.get("quantity") or 0))
        avg_price = _to_float(entry.get("average_price")) or 0.0
        last_price = _to_float(entry.get("last_price")) or avg_price
        realized = _to_float(entry.get("realised") or entry.get("realized")) or 0.0
        unrealized = _to_float(entry.get("unrealised") or entry.get("unrealized"))
        if unrealized is None:
            unrealized = (last_price - avg_price) * qty

        total_realized += realized
        total_unreal += unrealized

        positions.append(
            {
                "symbol": symbol,
                "quantity": qty,
                "avg_price": avg_price,
                "last_price": last_price,
                "realized_pnl": realized,
                "unrealized_pnl": unrealized,
            }
        )

    state = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "broker": {
            "orders": orders_list,
            "positions": positions,
        },
        "meta": {
            "mode": "live",
            "total_realized_pnl": total_realized,
            "total_unrealized_pnl": total_unreal,
        },
    }
    return state


def _apply_config_meta(state: Dict[str, Any], cfg: Optional[Any]) -> None:
    if cfg is None:
        return
    meta = state.setdefault("meta", {})
    trading_section = getattr(cfg, "trading", None)
    if isinstance(trading_section, dict):
        capital = trading_section.get("paper_capital")
    else:
        capital = getattr(cfg, "paper_capital", None)
    if capital is not None:
        try:
            meta["paper_capital"] = float(capital)
        except (TypeError, ValueError):
            meta["paper_capital"] = capital


def _to_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
