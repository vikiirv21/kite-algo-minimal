from __future__ import annotations

import csv
import json
import logging
import re
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Deque, Dict, Iterable, List, Optional, Tuple

from core.strategy_registry import STRATEGY_REGISTRY

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = BASE_DIR / "artifacts"

# Shared runtime checkpoint/log paths used by dashboards + orchestrators
RUNTIME_BASE_DIR = ARTIFACTS_DIR
RUNTIME_CHECKPOINT_PATH = RUNTIME_BASE_DIR / "checkpoints" / "runtime_state_latest.json"
RUNTIME_LOG_PATH = RUNTIME_BASE_DIR / "logs" / "events.jsonl"
RUNTIME_BASE_DIR.mkdir(parents=True, exist_ok=True)
RUNTIME_CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
RUNTIME_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def _utcnow_iso() -> str:
    return datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def make_fresh_state_from_config(cfg: Any) -> Dict[str, Any]:
    """
    Build a minimal canonical runtime state structure from AppConfig or dict.
    """
    trading_section: Dict[str, Any] = {}
    raw_trading = getattr(cfg, "trading", None)
    if isinstance(raw_trading, dict):
        trading_section = dict(raw_trading)
    elif raw_trading is not None:
        trading_section = dict(getattr(raw_trading, "__dict__", {}))

    mode_value = trading_section.get("mode") or getattr(cfg, "mode", "PAPER")
    session_info = trading_section.get("session")
    if not isinstance(session_info, dict):
        session_info = {}

    paper_capital = _safe_float(trading_section.get("paper_capital") or trading_section.get("capital"), 0.0)

    strategies = {}
    for strategy_code, strategy_info in STRATEGY_REGISTRY.items():
        if strategy_info.enabled:
            strategies[strategy_code] = {
                "day_pnl": 0.0,
                "open_trades": 0,
                "win_trades": 0,
                "loss_trades": 0,
                "entry_count": 0,
                "exit_count": 0,
                "last_signal_ts": None,
            }

    return {
        "mode": str(mode_value or "PAPER").upper(),
        "session": session_info,
        "equity": {
            "paper_capital": paper_capital,
            "cash": paper_capital,
            "realized_pnl": 0.0,
            "unrealized_pnl": 0.0,
            "day_pnl": 0.0,
            "total_notional": 0.0,
            "free_notional": paper_capital,
        },
        "positions": [],
        "open_orders": [],
        "strategies": strategies,
        "engines": {},
        "pnl": {},
        "summary": {},
        "universe": {},
        "last_heartbeat_ts": None,
        "last_broker_sync_ts": None,
        "risk": {
            "mode": trading_section.get("risk", {}).get("mode", "paper"),
            "trading_halted": False,
            "halt_reason": None,
            "last_decision_ts": None,
        },
    }


class StateStore:
    """
    Minimal JSON checkpoint/log tail helper shared between engines and dashboard.
    """

    def __init__(
        self,
        *,
        checkpoint_path: Optional[Path] = None,
        log_path: Optional[Path] = None,
    ) -> None:
        self.checkpoint_path = checkpoint_path or RUNTIME_CHECKPOINT_PATH
        self.log_path = log_path or RUNTIME_LOG_PATH

    def atomic_write_json(self, path: Path, data: Dict[str, Any]) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        path.parent.mkdir(parents=True, exist_ok=True)
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, default=str)
        tmp.replace(path)

    def save_checkpoint(self, state: Dict[str, Any]) -> None:
        payload = {
            **state,
            "ts": datetime.utcnow().isoformat() + "Z",
        }
        self.atomic_write_json(self.checkpoint_path, payload)

    def load_checkpoint(self) -> Optional[Dict[str, Any]]:
        if not self.checkpoint_path.is_file():
            return None
        with self.checkpoint_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def append_log(self, event: Dict[str, Any]) -> None:
        payload = {
            **event,
            "ts": datetime.utcnow().isoformat() + "Z",
        }
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, default=str) + "\n")

    def tail_logs(self, limit: int = 200) -> List[Dict[str, Any]]:
        if not self.log_path.is_file():
            return []
        lines = self.log_path.read_text(encoding="utf-8").splitlines()
        result: List[Dict[str, Any]] = []
        for raw in lines[-max(limit, 0) :]:
            if not raw.strip():
                continue
            try:
                result.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
        return result

FILLED_STATUSES = {"COMPLETE", "FILLED", "EXECUTED", "PARTLY FILLED", "PARTIAL", "SUCCESS"}
BUY_SIDES = {"BUY", "B", "COVER", "EXIT SHORT"}
SELL_SIDES = {"SELL", "S", "SHORT", "EXIT LONG"}
DEFAULT_STRATEGY_METRICS = {
    "day_pnl": 0.0,
    "open_trades": 0,
    "win_trades": 0,
    "loss_trades": 0,
    "entry_count": 0,
    "exit_count": 0,
    "last_signal_ts": None,
}

DEFAULT_ORDER_FIELDS: Tuple[str, ...] = (
    "timestamp",
    "order_id",
    "symbol",
    "tradingsymbol",
    "transaction_type",
    "side",
    "quantity",
    "filled_quantity",
    "price",
    "average_price",
    "status",
    "exchange",
    "product",
    "variety",
    "parent_order_id",
    "tag",
)

JOURNAL_EXTRA_FIELDS: Tuple[str, ...] = (
    "tf",
    "profile",
    "strategy",
    "parent_signal_timestamp",
    "underlying",
    "extra",
    "pnl",
    "realized_pnl",
    "r",
    "r_multiple",
    "trade_id",
    "signal_id",
    "entry_price",
    "exit_price",
    "realized_pnl_pct",
    "exit_reason",
    "exit_detail",
)

JOURNAL_FIELD_ORDER: List[str] = list(dict.fromkeys(DEFAULT_ORDER_FIELDS + JOURNAL_EXTRA_FIELDS))

EQUITY_SNAPSHOT_FIELDS: Tuple[str, ...] = (
    "timestamp",
    "equity",
    "paper_capital",
    "total_realized_pnl",
    "total_unrealized_pnl",
)


class JournalStateStore:
    """
    Filesystem-backed helper responsible for journaling orders and building checkpoints.
    """

    def __init__(self, *, artifacts_dir: Optional[Path] = None, mode: str = "paper") -> None:
        self.mode = (mode or "paper").strip().lower()
        self.artifacts_dir = artifacts_dir or ARTIFACTS_DIR
        self.checkpoints_dir = self.artifacts_dir / "checkpoints"
        self.snapshots_dir = self.artifacts_dir / "snapshots"
        self.journal_dir = self.artifacts_dir / "journal"
        self.state_path = self.artifacts_dir / f"{self.mode}_state.json"
        self.checkpoint_path = self.checkpoints_dir / f"{self.mode}_state_latest.json"
        self.snapshots_csv_path = self.artifacts_dir / "snapshots.csv"
        self.journal_index_path = self.journal_dir / "index.json"
        self.ensure_dirs()
        self._order_ids = self._load_order_index()

    # --- directory helpers -------------------------------------------------
    def ensure_dirs(self) -> None:
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.journal_dir.mkdir(parents=True, exist_ok=True)

    # --- serialization helpers --------------------------------------------
    @staticmethod
    def atomic_write_json(path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        tmp_path.replace(path)

    def load_latest_checkpoint(self) -> Optional[Dict[str, Any]]:
        if not self.checkpoint_path.exists():
            return None
        try:
            return json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load checkpoint %s (%s); ignoring.", self.checkpoint_path, exc)
            return None

    def save_checkpoint(self, state: Dict[str, Any]) -> None:
        timestamp = state.get("timestamp") or datetime.now(timezone.utc).isoformat()
        state = dict(state)
        state["timestamp"] = timestamp
        state.setdefault("meta", {})["mode"] = self.mode
        self.atomic_write_json(self.checkpoint_path, state)
        self.atomic_write_json(self.state_path, state)
        snapshot_name = f"positions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        snapshot_path = self.snapshots_dir / snapshot_name
        positions = state.get("broker", {}).get("positions", [])
        self.atomic_write_json(snapshot_path, positions)
        meta = state.get("meta") or {}
        logger.info(
            "State checkpoint saved (%s) equity=%.2f realized=%.2f unrealized=%.2f",
            self.checkpoint_path,
            float(meta.get("equity") or 0.0),
            float(meta.get("total_realized_pnl") or 0.0),
            float(meta.get("total_unrealized_pnl") or 0.0),
        )

    # --- journal helpers ---------------------------------------------------
    def latest_journal_path_for_today(self) -> Path:
        today = datetime.now().strftime("%Y-%m-%d")
        day_dir = self.journal_dir / today
        day_dir.mkdir(parents=True, exist_ok=True)
        return day_dir / "orders.csv"

    def append_orders(self, rows: List[Dict[str, Any]]) -> Optional[Path]:
        if not rows:
            return None
        path = self.latest_journal_path_for_today()
        file_exists = path.exists()
        desired_fields = list(dict.fromkeys(JOURNAL_FIELD_ORDER + tuple(rows[0].keys())))

        fieldnames: List[str]
        write_header = not file_exists
        if file_exists:
            with path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.reader(handle)
                header = next(reader, None)
            fieldnames = header or desired_fields
            write_header = header is None
            missing = [field for field in desired_fields if field not in fieldnames]
            if missing:
                with path.open("r", encoding="utf-8", newline="") as handle:
                    existing_rows = list(csv.DictReader(handle))
                fieldnames = list(dict.fromkeys(fieldnames + desired_fields))
                with path.open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
                    writer.writeheader()
                    for row in existing_rows:
                        writer.writerow(row)
                write_header = False
        else:
            fieldnames = desired_fields

        normalized_rows: List[Dict[str, Any]] = []
        dirty_index = False
        for raw in rows:
            normal = self.normalize_order(raw)
            order_id = normal.get("order_id")
            if order_id and order_id in self._order_ids:
                continue
            normalized_rows.append(normal)
            if order_id:
                self._order_ids.add(order_id)
                dirty_index = True

        if not normalized_rows:
            return path

        with path.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
            if write_header:
                writer.writeheader()
            for row in normalized_rows:
                writer.writerow(row)

        if dirty_index:
            self._persist_order_index()
        logger.info("Appended %d orders to %s", len(normalized_rows), path)
        return path

    def _load_order_index(self) -> set[str]:
        if not self.journal_index_path.exists():
            return set()
        try:
            data = json.loads(self.journal_index_path.read_text(encoding="utf-8"))
            values = data.get("order_ids", [])
            return {str(item) for item in values if item}
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to read journal index %s (%s); starting fresh.", self.journal_index_path, exc)
            return set()

    def _persist_order_index(self) -> None:
        data = {"order_ids": sorted(self._order_ids)}
        self.atomic_write_json(self.journal_index_path, data)

    # --- rebuild helpers ---------------------------------------------------
    def rebuild_from_journal(self, today_only: bool = True) -> Dict[str, Any]:
        files: List[Path] = []
        if today_only:
            path = self.latest_journal_path_for_today()
            if path.exists():
                files.append(path)
        else:
            files = sorted(self.journal_dir.glob("*/orders.csv"))

        orders: List[Dict[str, Any]] = []
        for path in files:
            try:
                with path.open("r", encoding="utf-8", newline="") as handle:
                    reader = csv.DictReader(handle)
                    for row in reader:
                        orders.append(dict(row))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed reading journal %s (%s)", path, exc)

        if not orders:
            return self._empty_state()

        state = self._build_state_from_orders(orders)
        logger.info(
            "Rebuilt state from %d journaled orders (today_only=%s).",
            len(orders),
            today_only,
        )
        return state

    def _build_state_from_orders(self, orders: List[Dict[str, Any]]) -> Dict[str, Any]:
        trades_by_symbol: Dict[str, List[Dict[str, float]]] = {}
        realized_by_symbol: Dict[str, float] = {}

        for order in orders:
            symbol = order.get("symbol") or order.get("tradingsymbol")
            if not symbol:
                continue
            status = (order.get("status") or "").upper()
            if status not in FILLED_STATUSES:
                continue

            qty = self._extract_quantity(order)
            if qty == 0:
                continue
            price = self._to_float(order.get("average_price") or order.get("price") or 0.0) or 0.0
            side = (order.get("side") or order.get("transaction_type") or "").upper()
            signed_qty = qty if side in BUY_SIDES else -qty
            bucket = trades_by_symbol.setdefault(symbol, [])
            bucket.append({"qty": signed_qty, "price": price})

        positions: List[Dict[str, Any]] = []
        total_realized = 0.0
        for symbol, trades in trades_by_symbol.items():
            open_lots, realized = fifo_pair(trades)
            realized_by_symbol[symbol] = realized
            total_realized += realized
            qty = sum(lot["qty"] for lot in open_lots)
            if qty == 0:
                continue
            avg_price = 0.0
            if qty != 0:
                numerator = sum(lot["qty"] * lot["price"] for lot in open_lots)
                avg_price = numerator / qty if qty else 0.0
            positions.append(
                {
                    "symbol": symbol,
                    "quantity": qty,
                    "avg_price": avg_price,
                    "realized_pnl": realized,
                    "last_price": avg_price,
                    "unrealized_pnl": 0.0,
                }
            )

        state = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "broker": {
                "orders": orders,
                "positions": positions,
            },
            "meta": {
                "mode": self.mode,
                "total_realized_pnl": total_realized,
            },
        }
        return state

    # --- analytics helpers -------------------------------------------------
    def compute_unrealized(self, state: Dict[str, Any], quotes: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        quotes = quotes or {}
        positions = state.get("broker", {}).get("positions", [])
        total_unreal = 0.0
        total_notional = 0.0

        for pos in positions:
            symbol = pos.get("symbol") or ""
            qty = float(pos.get("quantity") or 0.0)
            avg = self._to_float(pos.get("avg_price")) or 0.0
            last = self._quote_last_price(symbol, quotes)
            if last is None:
                last = self._to_float(pos.get("last_price")) or avg
            unreal = (last - avg) * qty
            pos["last_price"] = last
            pos["unrealized_pnl"] = unreal
            total_unreal += unreal
            total_notional += abs(qty * last)

        meta = state.setdefault("meta", {})
        meta["total_unrealized_pnl"] = total_unreal
        meta["total_notional"] = total_notional
        base_equity = self._to_float(meta.get("paper_capital")) or 0.0
        meta["equity"] = base_equity + total_unreal + self._to_float(meta.get("total_realized_pnl") or 0.0)
        return state

    def append_equity_snapshot(self, state: Dict[str, Any]) -> Path:
        """
        Append a CSV row with equity metrics for dashboard consumption.
        """
        timestamp = state.get("timestamp") or datetime.now(timezone.utc).isoformat()
        meta = state.get("meta") or {}
        row = {
            "timestamp": timestamp,
            "equity": self._to_float(meta.get("equity")) or 0.0,
            "paper_capital": self._to_float(meta.get("paper_capital")) or 0.0,
            "total_realized_pnl": self._to_float(meta.get("total_realized_pnl")) or 0.0,
            "total_unrealized_pnl": self._to_float(meta.get("total_unrealized_pnl")) or 0.0,
        }
        file_exists = self.snapshots_csv_path.exists()
        with self.snapshots_csv_path.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=EQUITY_SNAPSHOT_FIELDS)
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)
        return self.snapshots_csv_path

    # --- static helpers ----------------------------------------------------
    @staticmethod
    def normalize_order(order: Dict[str, Any]) -> Dict[str, Any]:
        ts = order.get("timestamp") or order.get("exchange_timestamp") or datetime.now(timezone.utc).isoformat()
        symbol = order.get("symbol") or order.get("tradingsymbol") or order.get("instrument") or ""
        order_id = (
            order.get("order_id")
            or order.get("orderid")
            or order.get("id")
            or order.get("kite_order_id")
        )
        side = (order.get("transaction_type") or order.get("side") or "").upper()
        qty = (
            order.get("filled_quantity")
            or order.get("filled_qty")
            or order.get("quantity")
            or order.get("qty")
            or 0
        )
        avg_price = order.get("average_price") or order.get("avg_price") or order.get("price")
        normalized = {
            "timestamp": ts,
            "order_id": order_id,
            "symbol": symbol,
            "tradingsymbol": order.get("tradingsymbol") or symbol,
            "side": side,
            "transaction_type": order.get("transaction_type") or side,
            "quantity": qty,
            "filled_quantity": order.get("filled_quantity") or qty,
            "price": order.get("price"),
            "average_price": avg_price,
            "status": order.get("status"),
            "exchange": order.get("exchange"),
            "product": order.get("product"),
            "variety": order.get("variety"),
            "parent_order_id": order.get("parent_order_id"),
            "tag": order.get("tag"),
        }
        for key, value in order.items():
            if key not in normalized:
                normalized[key] = value
        return normalized

    @staticmethod
    def _empty_state() -> Dict[str, Any]:
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "broker": {"orders": [], "positions": []},
            "meta": {"mode": "paper", "total_realized_pnl": 0.0, "total_unrealized_pnl": 0.0},
        }

    @staticmethod
    def _extract_quantity(order: Dict[str, Any]) -> int:
        for key in ("filled_quantity", "filled_qty", "quantity", "qty"):
            value = order.get(key)
            if value in (None, ""):
                continue
            try:
                qty = int(float(value))
                if qty != 0:
                    return abs(qty)
            except (TypeError, ValueError):
                continue
        return 0

    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _extract_base(symbol: str) -> str:
        match = re.match(r"^[A-Z]+", (symbol or "").upper())
        return match.group(0) if match else symbol

    def _quote_last_price(self, symbol: str, quotes: Dict[str, Any]) -> Optional[float]:
        if not symbol:
            return None
        entry = quotes.get(symbol)
        if isinstance(entry, dict):
            return self._to_float(entry.get("last_price") or entry.get("last"))
        base = self._extract_base(symbol)
        entry = quotes.get(base)
        if isinstance(entry, dict):
            return self._to_float(entry.get("last_price") or entry.get("last"))
        return None


def fifo_pair(trades: Iterable[Dict[str, float]]) -> Tuple[List[Dict[str, float]], float]:
    """
    Pair trades FIFO style to compute realized PnL.

    Args:
        trades: iterable of {"qty": signed_quantity, "price": fill_price}

    Returns:
        (open_lots, realized_pnl)
    """

    open_lots: Deque[Dict[str, float]] = deque()
    realized = 0.0

    for trade in trades:
        qty = float(trade.get("qty") or 0.0)
        price = float(trade.get("price") or 0.0)
        if qty == 0:
            continue

        if qty > 0:
            qty_remaining = qty
            while open_lots and qty_remaining > 0 and open_lots[0]["qty"] < 0:
                lot = open_lots[0]
                match_qty = min(qty_remaining, abs(lot["qty"]))
                realized += (lot["price"] - price) * match_qty
                lot["qty"] += match_qty
                qty_remaining -= match_qty
                if lot["qty"] == 0:
                    open_lots.popleft()
            if qty_remaining > 0:
                open_lots.append({"qty": qty_remaining, "price": price})
        else:
            qty_remaining = abs(qty)
            while open_lots and qty_remaining > 0 and open_lots[0]["qty"] > 0:
                lot = open_lots[0]
                match_qty = min(qty_remaining, lot["qty"])
                realized += (price - lot["price"]) * match_qty
                lot["qty"] -= match_qty
                qty_remaining -= match_qty
                if lot["qty"] == 0:
                    open_lots.popleft()
            if qty_remaining > 0:
                open_lots.append({"qty": -qty_remaining, "price": price})

    return list(open_lots), realized


store = StateStore()


def save_checkpoint(state: Dict[str, Any]) -> None:
    """
    Module-level helper to persist the shared runtime state.
    """
    store.save_checkpoint(state)


def load_checkpoint() -> Optional[Dict[str, Any]]:
    """
    Module-level helper to read the shared runtime state checkpoint.
    """
    return store.load_checkpoint()


def _strategy_metrics_template() -> Dict[str, Any]:
    return dict(DEFAULT_STRATEGY_METRICS)


def _ensure_strategy_metrics_entry(state: Dict[str, Any], strategy_code: str) -> Dict[str, Any]:
    strategies = state.setdefault("strategies", {})
    metrics = strategies.get(strategy_code)
    if not isinstance(metrics, dict):
        metrics = _strategy_metrics_template()
        strategies[strategy_code] = metrics
    return metrics


def _load_or_init_runtime_state_for_metrics() -> Dict[str, Any]:
    state = store.load_checkpoint()
    if isinstance(state, dict):
        return state
    placeholder = SimpleNamespace(trading={}, mode="PAPER")
    return make_fresh_state_from_config(placeholder)


def record_strategy_signal(strategy_code: Optional[str], *, timestamp: Optional[str] = None) -> None:
    if not strategy_code:
        return
    state = _load_or_init_runtime_state_for_metrics()
    metrics = _ensure_strategy_metrics_entry(state, strategy_code)
    metrics["last_signal_ts"] = timestamp or _utcnow_iso()
    store.save_checkpoint(state)


def record_strategy_fill(
    strategy_code: Optional[str],
    *,
    entry: bool = False,
    exit: bool = False,
    pnl_delta: float = 0.0,
    closed_trade: bool = False,
    timestamp: Optional[str] = None,
) -> None:
    if not strategy_code:
        return
    state = _load_or_init_runtime_state_for_metrics()
    metrics = _ensure_strategy_metrics_entry(state, strategy_code)
    if entry:
        metrics["entry_count"] = metrics.get("entry_count", 0) + 1
        metrics["open_trades"] = max(0, metrics.get("open_trades", 0)) + 1
    if exit:
        metrics["exit_count"] = metrics.get("exit_count", 0) + 1
        if pnl_delta > 0:
            metrics["win_trades"] = metrics.get("win_trades", 0) + 1
        elif pnl_delta < 0:
            metrics["loss_trades"] = metrics.get("loss_trades", 0) + 1
        if closed_trade:
            metrics["open_trades"] = max(0, metrics.get("open_trades", 0) - 1)
    if exit:
        metrics["day_pnl"] = _safe_float(metrics.get("day_pnl"), 0.0) + float(pnl_delta)
    metrics["last_signal_ts"] = timestamp or _utcnow_iso()
    store.save_checkpoint(state)
