from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

from kiteconnect import KiteConnect, KiteTicker, exceptions as kite_exceptions

from core.kite_http import kite_request
from core.state_store import JournalStateStore

logger = logging.getLogger(__name__)


class LiveBroker:
    """
    Lightweight live broker helper that streams order updates and maintains checkpoints.
    """

    def __init__(
        self,
        kite: KiteConnect,
        *,
        store: Optional[JournalStateStore] = None,
        auto_stream: bool = False,
        save_interval: float = 5.0,
    ) -> None:
        self.kite = kite
        self.store = store or JournalStateStore(mode="live")
        self.state = self.store.load_latest_checkpoint() or self.store.rebuild_from_journal(today_only=False)
        self._ticker: Optional[KiteTicker] = None
        self._save_interval = max(save_interval, 1.0)
        self._last_save = 0.0
        self._lock = threading.Lock()
        if auto_stream:
            self.start_order_stream()

    # ------------------------------------------------------------------ ticker
    def start_order_stream(self) -> None:
        if self._ticker:
            return
        api_key = getattr(self.kite, "api_key", None) or getattr(self.kite, "_api_key", None)
        access_token = getattr(self.kite, "access_token", None) or getattr(self.kite, "_access_token", None)
        if not api_key or not access_token:
            raise RuntimeError("LiveBroker requires an authenticated Kite client with api_key and access_token.")

        ticker = KiteTicker(api_key, access_token)
        ticker.on_order_update = self._handle_order_update
        ticker.on_error = self._handle_error

        self._ticker = ticker
        threading.Thread(target=ticker.connect, kwargs={"threaded": True}, daemon=True).start()
        logger.info("LiveBroker order stream started.")

    def stop_order_stream(self) -> None:
        ticker = self._ticker
        if ticker is None:
            return
        try:
            ticker.close()
        except Exception:  # noqa: BLE001
            pass
        self._ticker = None
        logger.info("LiveBroker order stream stopped.")

    # ------------------------------------------------------------------ events
    def _handle_order_update(self, _ws, data) -> None:
        try:
            normalized = JournalStateStore.normalize_order(data or {})
            self.store.append_orders([normalized])
            refreshed = self.store.rebuild_from_journal(today_only=True)
            refreshed = self.store.compute_unrealized(refreshed, {})
            with self._lock:
                self.state = refreshed
            self._maybe_save_checkpoint()
        except Exception as exc:  # noqa: BLE001
            logger.exception("LiveBroker order update handler failed: %s", exc)

    @staticmethod
    def _handle_error(_ws, code, reason) -> None:
        logger.error("LiveBroker ticker error code=%s reason=%s", code, reason)

    def _maybe_save_checkpoint(self) -> None:
        now = time.time()
        if now - self._last_save < self._save_interval:
            return
        with self._lock:
            state_copy = dict(self.state)
        self.store.save_checkpoint(state_copy)
        self._last_save = now

    # ------------------------------------------------------------------ margins
    def pretrade_margin_check(self, basket: Optional[List[Dict[str, Any]]]) -> Dict[str, float]:
        """
        Run a margin estimate for a proposed basket using Kite's order_margins API.
        """
        variety = getattr(self.kite, "VARIETY_REGULAR", "regular")
        basket = basket or []
        required = 0.0
        if basket:
            try:
                margins = kite_request(self.kite.order_margins, variety, basket)
            except kite_exceptions.TokenException:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning("Margin estimation failed (%s); continuing with zero requirement.", exc)
                margins = []
            for leg in margins or []:
                required += float(leg.get("total", 0.0))

        funds = kite_request(self.kite.margins, "equity")
        snapshot = funds.get("equity") if isinstance(funds, dict) and "equity" in funds else funds
        if not isinstance(snapshot, dict):
            snapshot = {}
        available = _to_float(snapshot.get("net"))
        utilised = snapshot.get("utilised") or snapshot.get("utilized") or {}
        if not isinstance(utilised, dict):
            utilised = {}
        span = _to_float(utilised.get("span"))
        exposure = _to_float(utilised.get("exposure"))
        utilized_total = sum(_to_float(value) for value in utilised.values())
        return {
            "required": required,
            "available": available,
            "utilized": utilized_total,
            "span": span if span else None,
            "exposure": exposure if exposure else None,
            "final": available - required,
        }


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
