from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from kiteconnect import KiteConnect

from core.kite_http import kite_request

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = BASE_DIR / "artifacts"
SCANNER_DIR = ARTIFACTS_DIR / "scanner"
SCANNER_DIR.mkdir(parents=True, exist_ok=True)
UNIVERSE_PATH = SCANNER_DIR / "universe.json"


@dataclass
class UniverseEntry:
    symbol: str
    tradingsymbol: str
    token: int
    exchange: str
    segment: str
    lot_size: Optional[int] = None
    tick_size: Optional[float] = None
    instrument_type: Optional[str] = None
    expiry: Optional[str] = None
    strike: Optional[float] = None
    option_type: Optional[str] = None


def load_universe(path: Optional[Path] = None) -> Dict[str, Any]:
    target = path or UNIVERSE_PATH
    if not target.exists():
        return {"symbols": [], "meta": {}}
    try:
        with target.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            return {"symbols": [], "meta": {}}
        return data
    except json.JSONDecodeError as exc:
        logger.warning("Universe file %s is invalid JSON: %s", target, exc)
        return {"symbols": [], "meta": {}}


def save_universe(universe: Dict[str, Any], path: Optional[Path] = None) -> Path:
    target = path or UNIVERSE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        json.dump(universe, handle, indent=2, default=str)
    return target


def refresh_universe_from_kite(kite: KiteConnect, *, exchanges: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Fetch the current instrument universe from Kite and persist it.
    """
    exchanges = exchanges or ["NFO"]
    entries: List[UniverseEntry] = []
    meta: Dict[str, Dict[str, Any]] = {}
    symbols: List[str] = []

    for exchange in exchanges:
        try:
            instruments = kite_request(kite.instruments, exchange)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to download instruments for %s: %s", exchange, exc)
            continue

        for inst in instruments or []:
            tradingsymbol = inst.get("tradingsymbol")
            if not tradingsymbol:
                continue
            token = inst.get("instrument_token")
            if token in (None, "", 0):
                continue
            symbol = str(tradingsymbol).upper()
            entry = UniverseEntry(
                symbol=symbol,
                tradingsymbol=symbol,
                token=int(token),
                exchange=str(inst.get("exchange") or exchange),
                segment=str(inst.get("segment") or exchange),
                lot_size=_try_int(inst.get("lot_size")),
                tick_size=_try_float(inst.get("tick_size")),
                instrument_type=inst.get("instrument_type"),
                expiry=_format_date(inst.get("expiry")),
                strike=_try_float(inst.get("strike")),
                option_type=inst.get("option_type"),
            )
            entries.append(entry)
            meta[symbol] = asdict(entry)
            symbols.append(symbol)

    universe_payload = {
        "symbols": sorted(set(symbols)),
        "meta": meta,
        "refreshed_at": datetime.utcnow().isoformat() + "Z",
    }
    save_universe(universe_payload)
    logger.info("Universe refreshed with %d instruments", len(entries))
    return universe_payload


def _try_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _try_int(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _format_date(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        return value.isoformat()
    except AttributeError:
        return None
