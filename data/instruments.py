from __future__ import annotations

import logging
from datetime import date
from typing import Dict, List, Sequence

from broker.kite_client import KiteClient
from core.kite_http import kite_request
from kiteconnect import KiteConnect

logger = logging.getLogger(__name__)


# Global cache for instruments and token index
_instrument_cache = None
_token_index = {}  # dict[(exchange, tradingsymbol)] = token


def _pick_nearest_expiry(contracts: Sequence[dict]) -> dict | None:
    """
    Given a list of instrument dicts (all same underlying), pick the one with
    the nearest expiry >= today. If none are >= today, pick the earliest expiry.
    """
    if not contracts:
        return None

    today = date.today()

    future = [c for c in contracts if isinstance(c.get("expiry"), date) and c["expiry"] >= today]
    if future:
        return sorted(future, key=lambda c: c["expiry"])[0]

    dated = [c for c in contracts if isinstance(c.get("expiry"), date)]
    if dated:
        return sorted(dated, key=lambda c: c["expiry"])[0]

    # Fallback: just return the first
    return contracts[0]


def resolve_fno_symbols(
    logical_names: List[str],
    kite_client: KiteClient | None = None,
) -> Dict[str, str]:
    """
    Resolve logical names like ["NIFTY", "BANKNIFTY"] to actual NFO FUT tradingsymbols.

    - Fetches instruments("NFO") from Kite.
    - Filters to segment == "NFO-FUT".
    - Groups by instrument["name"].
    - Picks nearest expiry for each requested logical name.
    """
    kite_client = kite_client or KiteClient()
    kite = kite_client.api

    logger.info("Fetching NFO instruments from Kite to resolve FnO symbols...")
    instruments = kite_request(kite.instruments, "NFO")

    by_name: Dict[str, List[dict]] = {}
    for inst in instruments:
        if inst.get("segment") != "NFO-FUT":
            continue
        name = inst.get("name")
        if not name:
            continue
        by_name.setdefault(name.upper(), []).append(inst)

    result: Dict[str, str] = {}
    for logical in logical_names:
        key = logical.upper()
        contracts = by_name.get(key, [])
        chosen = _pick_nearest_expiry(contracts)
        if not chosen:
            logger.warning("No FUT contract found in NFO for logical name=%s", logical)
            continue
        ts = chosen.get("tradingsymbol")
        if not ts:
            logger.warning("Chosen contract for %s has no tradingsymbol: %s", logical, chosen)
            continue
        result[logical] = ts
        logger.info("Resolved %s -> %s (expiry=%s)", logical, ts, chosen.get("expiry"))

    return result


def ensure_instruments_loaded(kite_client: KiteClient | None = None):
    """
    Load and cache all instruments from Kite API.
    Builds a token index for fast lookup by (exchange, tradingsymbol).
    """
    global _instrument_cache, _token_index
    if _instrument_cache is not None:
        return

    kite_client = kite_client or KiteClient()
    kite = kite_client.api

    logger.info("Loading all instruments from Kite API to build token index...")
    
    # Fetch instruments for NSE and NFO exchanges
    all_instruments = []
    for exchange in ["NSE", "NFO"]:
        try:
            instruments = kite_request(kite.instruments, exchange)
            all_instruments.extend(instruments)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to fetch instruments for exchange=%s: %s", exchange, exc)

    _instrument_cache = all_instruments
    logger.info("Loaded %d total instruments from Kite API", len(all_instruments))

    # Build token index
    for inst in all_instruments:
        ex = inst.get("exchange")
        ts = inst.get("tradingsymbol")
        token = inst.get("instrument_token")
        if ex and ts and token:
            _token_index[(ex, ts)] = token

    logger.info("Built token index with %d entries", len(_token_index))


def get_instrument_token(exchange: str, tradingsymbol: str) -> int | None:
    """
    Look up instrument token by exchange and tradingsymbol.
    Loads instruments from Kite API on first call.
    
    Args:
        exchange: Exchange name (e.g., "NSE", "NFO")
        tradingsymbol: Trading symbol (e.g., "RELIANCE", "NIFTY25NOVFUT")
    
    Returns:
        Instrument token as integer, or None if not found
    """
    ensure_instruments_loaded()
    return _token_index.get((exchange, tradingsymbol))
