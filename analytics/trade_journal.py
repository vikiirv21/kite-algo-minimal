from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Any, Dict

TRADE_JOURNAL_FIELDS = [
    "trade_id",
    "signal_id",
    "symbol",
    "strategy",
    "side",
    "session_date",
    "entry_ts",
    "exit_ts",
    "holding_bars",
    "holding_seconds",
    "entry_price",
    "exit_price",
    "size",
    "realized_pnl",
    "realized_pnl_pct",
    "r_multiple",
    "max_favorable_excursion",
    "max_adverse_excursion",
    "num_adds",
    "num_reduces",
    "exit_reason",
    "exit_detail",
    "time_of_day_bucket",
    "regime_tag",
    "quality_tag",
]


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _time_of_day_bucket(ts: datetime) -> str:
    t = ts.timetz()
    morning = time(hour=9, minute=30, tzinfo=t.tzinfo)
    close = time(hour=14, minute=30, tzinfo=t.tzinfo)
    if t <= morning:
        return "open"
    if t >= close:
        return "close"
    return "mid"


def _regime_tag(meta: Dict[str, Any]) -> str:
    regime = str(meta.get("vol_regime", "") or "").lower()
    trend = str(meta.get("trend_context", "") or "").lower()
    if regime in {"high", "volatile"}:
        return "volatile"
    if "trend" in trend:
        return "trending"
    if regime in {"low", "calm"}:
        return "calm"
    return "choppy"


def _quality_tag(r_multiple: float, max_adverse: float, planned_risk: float) -> str:
    if r_multiple >= 1.0 or (r_multiple > -0.3 and max_adverse >= -abs(planned_risk)):
        return "A"
    if -0.3 <= r_multiple <= 0.3:
        return "B"
    return "C"


def finalize_trade(trade: Dict[str, Any]) -> Dict[str, Any]:
    entry_dt = _parse_dt(trade.get("entry_ts"))
    exit_dt = _parse_dt(trade.get("exit_ts") or datetime.now(timezone.utc))
    holding_seconds = max(0, int((exit_dt - entry_dt).total_seconds()))
    side = trade.get("side") or ("LONG" if (trade.get("quantity", 0) or 0) >= 0 else "SHORT")
    realized_pnl = float(trade.get("realized_pnl") or 0.0)
    entry_price = float(trade.get("entry_price") or 0.0)
    exit_price = float(trade.get("exit_price") or 0.0)
    size = int(abs(trade.get("initial_size") or trade.get("size") or 0))
    denom = entry_price * max(1, size)
    realized_pct = realized_pnl / denom * 100.0 if denom else 0.0
    planned_risk = float(trade.get("planned_risk") or 1.0)
    r_multiple = trade.get("r_multiple")
    if r_multiple is None:
        r_multiple = realized_pnl / max(1e-6, planned_risk)
    max_fav = float(trade.get("max_favorable_excursion") or 0.0)
    max_adv = float(trade.get("max_adverse_excursion") or 0.0)
    if max_adv > 0:
        max_adv = -max_adv
    regime = _regime_tag(trade.get("meta") or {})
    quality = _quality_tag(r_multiple, max_adv, planned_risk)

    row = {
        "trade_id": trade.get("trade_id"),
        "signal_id": trade.get("signal_id"),
        "symbol": trade.get("symbol"),
        "strategy": trade.get("strategy"),
        "side": side,
        "session_date": entry_dt.date().isoformat(),
        "entry_ts": entry_dt.isoformat(),
        "exit_ts": exit_dt.isoformat(),
        "holding_bars": int(trade.get("bars_in_trade") or 0),
        "holding_seconds": holding_seconds,
        "entry_price": round(entry_price, 4),
        "exit_price": round(exit_price, 4),
        "size": size,
        "realized_pnl": round(realized_pnl, 2),
        "realized_pnl_pct": round(realized_pct, 4),
        "r_multiple": round(r_multiple, 4),
        "max_favorable_excursion": round(max_fav, 2),
        "max_adverse_excursion": round(max_adv, 2),
        "num_adds": int(trade.get("adds") or 0),
        "num_reduces": int(trade.get("reduces") or 0),
        "exit_reason": trade.get("exit_reason") or "",
        "exit_detail": trade.get("exit_detail") or "",
        "time_of_day_bucket": _time_of_day_bucket(entry_dt),
        "regime_tag": regime,
        "quality_tag": quality,
    }
    return row
