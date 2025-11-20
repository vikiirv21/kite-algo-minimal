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


# Global cache for instrument token mapping (tradingsymbol -> token)
_instrument_token_map: Dict[str, int] | None = None
_instrument_token_map_loaded = False


def load_instrument_token_map(
    kite: KiteConnect | None = None,
    segments: tuple[str, ...] = ("NSE", "NFO"),
) -> Dict[str, int]:
    """
    Build and cache a dict of tradingsymbol -> instrument_token for specified segments.
    
    This function fetches instruments once per segment and builds a unified mapping
    that can be used to quickly resolve instrument tokens by tradingsymbol alone
    (without needing to know the exchange).
    
    Args:
        kite: KiteConnect instance (if None, will create via KiteClient)
        segments: Tuple of exchange segments to include (default: NSE, NFO)
    
    Returns:
        Dictionary mapping tradingsymbol (uppercase) to instrument_token
    """
    global _instrument_token_map, _instrument_token_map_loaded
    
    # Return cached map if already loaded
    if _instrument_token_map_loaded and _instrument_token_map is not None:
        return _instrument_token_map
    
    # If no kite client provided and we can't create one, return empty map
    if kite is None:
        try:
            kite_client = KiteClient()
            kite = kite_client.api
        except Exception as exc:
            logger.warning("Cannot create KiteClient for instrument token map: %s", exc)
            _instrument_token_map = {}
            _instrument_token_map_loaded = True
            return _instrument_token_map
    
    logger.info("Building instrument token map for segments: %s", segments)
    
    token_map: Dict[str, int] = {}
    
    for segment in segments:
        try:
            instruments = kite_request(kite.instruments, segment)
            count = 0
            for inst in instruments:
                ts = inst.get("tradingsymbol")
                token = inst.get("instrument_token")
                if ts and token:
                    # Store with uppercase key for case-insensitive lookup
                    token_map[ts.upper()] = int(token)
                    count += 1
            logger.info("Loaded %d instruments from %s", count, segment)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to fetch instruments for segment %s: %s", segment, exc)
    
    _instrument_token_map = token_map
    _instrument_token_map_loaded = True
    
    logger.info("Instrument token map built with %d total symbols", len(token_map))
    return token_map


def resolve_instrument_token(tradingsymbol: str) -> int | None:
    """
    Resolve instrument token for a tradingsymbol.
    
    This is a convenience function that looks up the token from the cached
    instrument token map. If the map hasn't been loaded yet, it will be
    loaded on first call.
    
    Args:
        tradingsymbol: Trading symbol (e.g., "NIFTY25NOVFUT", "RELIANCE")
    
    Returns:
        Instrument token as integer, or None if not found
    """
    if not _instrument_token_map_loaded:
        load_instrument_token_map()
    
    if _instrument_token_map is None:
        return None
    
    return _instrument_token_map.get(tradingsymbol.upper())
