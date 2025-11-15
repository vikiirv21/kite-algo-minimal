from __future__ import annotations

from dataclasses import dataclass
from datetime import time as dtime
from typing import Any, Dict, Iterable, Optional, Tuple

from core.market_session import now_ist


@dataclass
class ATRConfig:
    enabled: bool = True
    lookback: int = 14
    sl_r_multiple: float = 1.0
    tp_r_multiple: float = 2.0
    hard_sl_pct_cap: float = 0.03
    hard_tp_pct_cap: float = 0.06
    min_atr_value: float = 0.5
    per_product: Dict[str, Dict[str, float]] | None = None


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def compute_atr_from_ohlc(rows: Iterable[Dict[str, Any]], period: int) -> Optional[float]:
    rows = list(rows)
    if len(rows) < max(1, period + 1):
        return None

    true_ranges: list[float] = []
    prev_close = None
    for row in rows[-(period + 1) :]:
        high = _safe_float(row.get("high"))
        low = _safe_float(row.get("low"))
        close = _safe_float(row.get("close"))
        if prev_close is None:
            tr = high - low
        else:
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close),
            )
        true_ranges.append(tr)
        prev_close = close

    if not true_ranges:
        return None
    return sum(true_ranges[-period:]) / float(period)


def _apply_caps(
    entry_price: float,
    raw_sl: float,
    raw_tp: float,
    max_sl_pct: float,
    max_tp_pct: float,
    side: str,
) -> Tuple[float, float]:
    side = (side or "").upper()
    if side not in {"BUY", "SELL"} or entry_price <= 0:
        return raw_sl, raw_tp

    if max_sl_pct and max_sl_pct > 0:
        max_sl_dist = entry_price * max_sl_pct
        if side == "BUY":
            raw_sl = max(raw_sl, entry_price - max_sl_dist)
        else:
            raw_sl = min(raw_sl, entry_price + max_sl_dist)

    if max_tp_pct and max_tp_pct > 0:
        max_tp_dist = entry_price * max_tp_pct
        if side == "BUY":
            raw_tp = min(raw_tp, entry_price + max_tp_dist)
        else:
            raw_tp = max(raw_tp, entry_price - max_tp_dist)

    return raw_sl, raw_tp


def compute_sl_tp_from_atr(
    *,
    symbol: str,
    product_type: str,
    side: str,
    entry_price: float,
    atr_value: Optional[float],
    cfg: ATRConfig,
) -> Dict[str, Any]:
    side = (side or "").upper()
    if side not in {"BUY", "SELL"} or entry_price <= 0:
        return {
            "sl_price": None,
            "tp_price": None,
            "atr_used": atr_value,
            "method": "disabled",
        }

    sl_r = cfg.sl_r_multiple
    tp_r = cfg.tp_r_multiple

    if cfg.per_product and product_type:
        override = cfg.per_product.get(product_type.upper())
        if override:
            sl_r = float(override.get("sl_r_multiple", sl_r))
            tp_r = float(override.get("tp_r_multiple", tp_r))

    if not atr_value or atr_value < cfg.min_atr_value:
        sl_dist = entry_price * (cfg.hard_sl_pct_cap or 0.01)
        tp_dist = entry_price * (cfg.hard_tp_pct_cap or 0.02)
        if side == "BUY":
            sl_price = entry_price - sl_dist
            tp_price = entry_price + tp_dist
        else:
            sl_price = entry_price + sl_dist
            tp_price = entry_price - tp_dist
        sl_price, tp_price = _apply_caps(
            entry_price,
            sl_price,
            tp_price,
            cfg.hard_sl_pct_cap,
            cfg.hard_tp_pct_cap,
            side,
        )
        return {
            "sl_price": sl_price,
            "tp_price": tp_price,
            "atr_used": None,
            "method": "pct_fallback",
        }

    sl_dist = atr_value * sl_r
    tp_dist = atr_value * tp_r

    if side == "BUY":
        sl_price = entry_price - sl_dist
        tp_price = entry_price + tp_dist
    else:
        sl_price = entry_price + sl_dist
        tp_price = entry_price - tp_dist

    sl_price, tp_price = _apply_caps(
        entry_price,
        sl_price,
        tp_price,
        cfg.hard_sl_pct_cap,
        cfg.hard_tp_pct_cap,
        side,
    )

    return {
        "sl_price": sl_price,
        "tp_price": tp_price,
        "atr_used": atr_value,
        "method": "atr",
    }


@dataclass
class TimeFilterConfig:
    enabled: bool = True
    allow_sessions: list[dict] | None = None
    block_expiry_scalps_after: Optional[str] = None
    min_time: Optional[str] = None
    max_time: Optional[str] = None


def _parse_hhmm(text: Optional[str]) -> Optional[dtime]:
    if not text:
        return None
    try:
        hh, mm = text.split(":", 1)
        return dtime(int(hh), int(mm))
    except Exception:
        return None


def is_entry_time_allowed(
    cfg: TimeFilterConfig,
    *,
    symbol: str,
    strategy_id: str | None = None,
    is_expiry_instrument: bool = False,
) -> tuple[bool, Optional[str]]:
    if not cfg.enabled:
        return True, None

    now = now_ist()
    now_t = now.time()

    min_t = _parse_hhmm(cfg.min_time)
    max_t = _parse_hhmm(cfg.max_time)
    if min_t and now_t < min_t:
        return False, f"before_min_time:{min_t.strftime('%H:%M')}"
    if max_t and now_t > max_t:
        return False, f"after_max_time:{max_t.strftime('%H:%M')}"

    sessions = cfg.allow_sessions or []
    if sessions:
        in_any = False
        for sess in sessions:
            s = _parse_hhmm(sess.get("start"))
            e = _parse_hhmm(sess.get("end"))
            if not s or not e:
                continue
            if s <= now_t <= e:
                in_any = True
                break
        if not in_any:
            return False, "outside_allowed_sessions"

    cutoff = _parse_hhmm(cfg.block_expiry_scalps_after)
    if cutoff and is_expiry_instrument and now_t > cutoff:
        return False, "expiry_block_after_cutoff"

    return True, None
