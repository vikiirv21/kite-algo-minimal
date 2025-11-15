from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
import uuid

from broker.paper_broker import PaperBroker
from core.universe import INDEX_BASES

SIGNAL_HEADERS = [
    "timestamp",
    "signal_id",
    "logical",
    "symbol",
    "price",
    "signal",
    "tf",
    "reason",
    "profile",
    "mode",
    "confidence",
    "trend_context",
    "vol_regime",
    "htf_trend",
    "playbook",
    "setup_type",
    "ema20",
    "ema50",
    "ema100",
    "ema200",
    "rsi14",
    "atr",
    "adx14",
    "adx",
    "vwap",
    "rel_volume",
    "vol_spike",
    "strategy",
]
ORDER_HEADERS = [
    "timestamp",
    "symbol",
    "side",
    "quantity",
    "price",
    "status",
    "tf",
    "profile",
    "strategy",
    "parent_signal_timestamp",
    "underlying",
    "extra",
]

def infer_underlying(symbol: str) -> str:
    s = (symbol or "").upper()
    for base in INDEX_BASES:
        if s.startswith(base):
            return base
    for eq in ("RELIANCE", "TCS", "INFY"):
        if s.startswith(eq):
            return eq
    return s[:10] or "UNKNOWN"

IST = timezone(timedelta(hours=5, minutes=30))

@dataclass
class SignalLogPayload:
    timestamp: str
    logical: str
    symbol: str
    price: float
    signal: str
    tf: str
    reason: str
    profile: str
    mode: str | None = None
    confidence: float | None = None
    trend_context: str | None = None
    vol_regime: str | None = None
    htf_trend: str | None = None
    playbook: str | None = None
    setup_type: str | None = None
    ema20: Optional[float] = None
    ema50: Optional[float] = None
    ema100: Optional[float] = None
    ema200: Optional[float] = None
    rsi14: Optional[float] = None
    atr: Optional[float] = None
    adx14: Optional[float] = None
    adx: Optional[float] = None
    vwap: Optional[float] = None
    rel_volume: Optional[float] = None
    vol_spike: Optional[bool] = None
    strategy: Optional[str] = None


@dataclass
class OrderRecord:
    timestamp: str
    symbol: str
    side: str
    quantity: int
    price: float
    status: str
    tf: str
    profile: str
    strategy: str
    parent_signal_timestamp: str
    underlying: str
    extra: Dict[str, Any] = field(default_factory=dict)


class TradeRecorder:
    """
    Lightweight recorder for:

    - Signals: every decision made by a strategy.
    - Orders: every order placed (paper or live).
    - State snapshots: full PaperBroker state (positions + orders)
      plus portfolio meta (capital, P&L, notional).

    Files:

    - artifacts/signals.csv
    - artifacts/orders.csv
    - artifacts/paper_state.json
    """

    def __init__(self, base_dir: Optional[str] = None) -> None:
        base_dir = base_dir or os.path.dirname(os.path.dirname(__file__))
        self.artifacts_dir = os.path.join(base_dir, "artifacts")
        os.makedirs(self.artifacts_dir, exist_ok=True)

        self.signals_path = os.path.join(self.artifacts_dir, "signals.csv")
        self.orders_path = os.path.join(self.artifacts_dir, "orders.csv")
        self.state_path = os.path.join(self.artifacts_dir, "paper_state.json")

        # Ensure CSVs have headers if freshly created
        self._ensure_csv_headers(self.signals_path, SIGNAL_HEADERS)
        self._ensure_csv_headers(self.orders_path, ORDER_HEADERS)

    @staticmethod
    def _ensure_csv_headers(path: str, headers: List[str]) -> None:
        if not os.path.exists(path):
            with open(path, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(headers)
            return

        with open(path, "r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            rows = list(reader)

        if not rows:
            with open(path, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(headers)
            return

        existing = rows[0]
        data_rows = rows[1:]
        if existing == headers:
            return

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            if not data_rows:
                return
            for row in data_rows:
                if len(row) < len(headers):
                    row = row + [""] * (len(headers) - len(row))
                elif len(row) > len(headers):
                    row = row[: len(headers)]
                writer.writerow(row)

    @staticmethod
    def _now_iso() -> str:
        return datetime.utcnow().isoformat()

    @staticmethod
    def _now_ist_iso() -> str:
        return datetime.now(IST).isoformat()

    def log_signal(
        self,
        *,
        logical: str,
        symbol: str,
        price: float,
        signal: str,
        tf: str,
        reason: str,
        profile: str,
        mode: str | None = None,
        confidence: float | None = None,
        trend_context: str | None = None,
        vol_regime: str | None = None,
        htf_trend: str | None = None,
        playbook: str | None = None,
        setup_type: str | None = None,
        ema20: float | None = None,
        ema50: float | None = None,
        ema100: float | None = None,
        ema200: float | None = None,
        rsi14: float | None = None,
        atr: float | None = None,
        adx14: float | None = None,
        adx: float | None = None,
        vwap: float | None = None,
        rel_volume: float | None = None,
        vol_spike: bool | None = None,
        strategy: str | None = None,
        signal_id: Optional[str] = None,
    ) -> str:
        signal_id = signal_id or str(uuid.uuid4())
        payload = SignalLogPayload(
            timestamp=self._now_ist_iso(),
            logical=logical,
            symbol=symbol,
            price=float(price),
            signal=signal,
            tf=tf,
            reason=reason,
            profile=profile,
            mode=mode,
            confidence=confidence,
            trend_context=trend_context,
            vol_regime=vol_regime,
            htf_trend=htf_trend,
            playbook=playbook,
            setup_type=setup_type,
            ema20=ema20,
            ema50=ema50,
            ema100=ema100,
            ema200=ema200,
            rsi14=rsi14,
            atr=atr,
            adx14=adx14,
            adx=adx,
            vwap=vwap,
            rel_volume=rel_volume,
            vol_spike=vol_spike,
            strategy=strategy,
        )

        def _value(val: Any) -> Any:
            return "" if val is None else val

        row = {
            "timestamp": payload.timestamp,
            "signal_id": signal_id,
            "logical": payload.logical,
            "symbol": payload.symbol,
            "price": payload.price,
            "signal": payload.signal,
            "tf": payload.tf,
            "reason": payload.reason,
            "profile": payload.profile,
            "mode": _value(payload.mode),
            "confidence": _value(
                round(payload.confidence, 4) if isinstance(payload.confidence, (int, float)) else payload.confidence
            ),
            "trend_context": _value(payload.trend_context),
            "vol_regime": _value(payload.vol_regime),
            "htf_trend": _value(payload.htf_trend),
            "playbook": _value(payload.playbook),
            "setup_type": _value(payload.setup_type),
            "ema20": _value(payload.ema20),
            "ema50": _value(payload.ema50),
            "ema100": _value(payload.ema100),
            "ema200": _value(payload.ema200),
            "rsi14": _value(payload.rsi14),
            "atr": _value(payload.atr),
            "adx14": _value(payload.adx14),
            "adx": _value(payload.adx if payload.adx is not None else payload.adx14),
            "vwap": _value(payload.vwap),
            "rel_volume": _value(payload.rel_volume),
            "vol_spike": "" if payload.vol_spike is None else int(bool(payload.vol_spike)),
            "strategy": _value(payload.strategy),
        }

        with open(self.signals_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=SIGNAL_HEADERS)
            writer.writerow(row)
        return signal_id

    def record_signal(self, logical: str, symbol: str, price: float, signal: str) -> str:
        return self.log_signal(
            logical=logical,
            symbol=symbol,
            price=price,
            signal=signal,
            tf="",
            reason="legacy",
            profile="INTRADAY",
            signal_id=str(uuid.uuid4()),
        )

    def record_order(
        self,
        *,
        symbol: str,
        side: str,
        quantity: int,
        price: float,
        status: str = "",
        tf: str = "",
        profile: str = "",
        strategy: str = "",
        parent_signal_timestamp: str = "",
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        rec = OrderRecord(
            timestamp=self._now_iso(),
            symbol=symbol,
            side=side.upper(),
            quantity=int(quantity),
            price=float(price),
            status=(status or "FILLED").upper(),
            tf=tf or "",
            profile=profile or "",
            strategy=strategy or "",
            parent_signal_timestamp=parent_signal_timestamp or "",
            underlying=infer_underlying(symbol),
            extra=extra or {},
        )
        with open(self.orders_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                rec.timestamp,
                rec.symbol,
                rec.side,
                rec.quantity,
                rec.price,
                rec.status,
                rec.tf,
                rec.profile,
                rec.strategy,
                rec.parent_signal_timestamp,
                rec.underlying,
                json.dumps(rec.extra, ensure_ascii=False),
            ])

    def snapshot_paper_state(
        self,
        broker: PaperBroker,
        last_prices: Optional[Dict[str, float]] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Write a full snapshot of PaperBroker state into paper_state.json.

        Includes:
        - positions and orders (from PaperBroker)
        - optional last_prices per symbol and unrealized P&L per position
        - optional meta: capital, realized/unrealized P&L, equity, notional
        """
        state = broker.to_state_dict(last_prices=last_prices or {})
        payload: Dict[str, Any] = {
            "timestamp": self._now_iso(),
            "broker": state,
        }
        if meta:
            payload["meta"] = meta

        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
