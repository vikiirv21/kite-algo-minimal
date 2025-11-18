"""
Shared engine bootstrap utilities for multi-process architecture.

This module extracts common initialization logic from scripts/run_day.py
to be reused by individual engine entry points (apps/run_*_paper.py).
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from kiteconnect import KiteConnect, exceptions as kite_exceptions

from core.config import AppConfig, load_config
from core.kite_env import make_kite_client_from_files, read_tokens
from core.logging_utils import setup_logging
from core.json_log import install_engine_json_logger
from core.scanner import MarketScanner
from data.instruments import resolve_fno_symbols

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[1]

LOGIN_HINT = "python -m scripts.run_day --login --engines none"


def setup_engine_logging(cfg: AppConfig) -> None:
    """
    Setup logging for an engine process.
    
    Args:
        cfg: Application configuration
    """
    setup_logging(cfg.logging)
    install_engine_json_logger()
    logger.info("Engine logging initialized")


def ensure_token_files_available() -> None:
    """
    Verify that Kite token files exist and are readable.
    
    Raises:
        SystemExit: If tokens are not available
    """
    try:
        access_token, _public_token, login_ts, _token_key = read_tokens()
    except Exception as exc:
        logger.error("Unable to read Kite tokens: %s", exc)
        logger.error("Run `%s` to refresh credentials.", LOGIN_HINT)
        raise SystemExit(1) from exc

    if not access_token:
        logger.error("No stored Kite token found in secrets/kite_tokens.env.")
        logger.error("Run `%s` to refresh credentials.", LOGIN_HINT)
        raise SystemExit(1)

    if login_ts:
        logger.info("Last Kite login timestamp from tokens file: %s", login_ts)


def preflight_check_token(kite: KiteConnect) -> bool:
    """
    Try a simple profile call to verify that api_key/access_token pair is valid.
    
    Args:
        kite: KiteConnect client
        
    Returns:
        True if token is valid, False otherwise
    """
    try:
        profile = kite.profile()
        user_id = profile.get("user_id") or profile.get("USER_ID", "")
        logger.info("Kite preflight OK. User id=%s", user_id)
        return True
    except kite_exceptions.TokenException as exc:
        logger.error("Kite preflight failed, token likely invalid: %s", exc)
        return False
    except Exception as exc:
        logger.error("Kite preflight failed with unexpected error: %s", exc, exc_info=True)
        return False


def build_kite_client() -> KiteConnect:
    """
    Build and return a KiteConnect client from stored credentials.
    
    Returns:
        KiteConnect client instance
        
    Raises:
        SystemExit: If client cannot be built or token is invalid
    """
    ensure_token_files_available()
    
    try:
        kite = make_kite_client_from_files()
    except Exception as exc:
        logger.error("Unable to build Kite client from stored credentials: %s", exc)
        logger.error("Run `%s` to refresh credentials.", LOGIN_HINT)
        raise SystemExit(1) from exc

    if not preflight_check_token(kite):
        logger.error(
            "Stored Kite token invalid/expired. Run `%s` to refresh tokens.",
            LOGIN_HINT,
        )
        raise SystemExit(1)

    return kite


def resolve_fno_universe(
    cfg: AppConfig,
    kite: Optional[KiteConnect] = None,
    universe_snapshot: Optional[Dict[str, Any]] = None,
) -> Tuple[List[str], Dict[str, str]]:
    """
    Resolve FnO universe from config and optionally from scanner snapshot.
    
    Args:
        cfg: Application configuration
        kite: Optional KiteConnect client (needed if universe_snapshot not provided)
        universe_snapshot: Optional pre-loaded universe snapshot from scanner
        
    Returns:
        Tuple of (logical_universe, symbol_map)
        - logical_universe: List of logical symbols (e.g., ["NIFTY", "BANKNIFTY"])
        - symbol_map: Dict mapping logical -> tradingsymbol (e.g., {"NIFTY": "NIFTY25DECFUT"})
    """
    trading = cfg.trading or {}
    config_universe = trading.get("fno_universe", [])
    
    # Use universe snapshot if provided
    if universe_snapshot and isinstance(universe_snapshot, dict):
        logicals = [str(sym).strip().upper() for sym in universe_snapshot.get("fno", []) if sym]
        meta = universe_snapshot.get("meta") or {}
        symbol_map: Dict[str, str] = {}
        for logical in logicals:
            info = meta.get(logical) or {}
            tradingsymbol = info.get("tradingsymbol")
            if tradingsymbol:
                symbol_map[logical] = str(tradingsymbol).strip().upper()
        
        if logicals:
            logger.info(
                "Using FnO universe from scanner snapshot: %s",
                ", ".join(logicals),
            )
            return logicals, symbol_map
    
    # Fallback to config universe
    if config_universe:
        logicals = [str(sym).strip().upper() for sym in config_universe if sym]
        logger.info(
            "Using FnO universe from config: %s",
            ", ".join(logicals),
        )
        
        # Resolve trading symbols if kite client available
        symbol_map = {}
        if kite and logicals:
            try:
                symbol_map = resolve_fno_symbols(kite, logicals)
                logger.info("Resolved %d FnO trading symbols", len(symbol_map))
            except Exception as exc:
                logger.warning("Failed to resolve FnO symbols: %s", exc)
        
        return logicals, symbol_map
    
    # Default fallback
    default_logicals = ["NIFTY", "BANKNIFTY", "FINNIFTY"]
    logger.warning(
        "No FnO universe in config or scanner, using defaults: %s",
        ", ".join(default_logicals),
    )
    return default_logicals, {}


def resolve_equity_universe(
    cfg: AppConfig,
    kite: Optional[KiteConnect] = None,
    universe_snapshot: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """
    Resolve equity universe from config, scanner snapshot, or CSV file.
    
    Args:
        cfg: Application configuration
        kite: Optional KiteConnect client (for price filtering)
        universe_snapshot: Optional pre-loaded universe snapshot from scanner
        
    Returns:
        List of equity symbols to trade
    """
    from core.universe import load_equity_universe
    
    # Check scanner snapshot first
    if universe_snapshot and isinstance(universe_snapshot, dict):
        equity_list = universe_snapshot.get("equity_universe", [])
        if equity_list:
            symbols = [str(sym).strip().upper() for sym in equity_list if sym]
            logger.info(
                "Using equity universe from scanner snapshot: %d symbols",
                len(symbols),
            )
            return symbols
    
    # Check config for equity_universe
    trading = cfg.trading or {}
    config_universe = trading.get("equity_universe", [])
    
    if config_universe:
        symbols = [str(sym).strip().upper() for sym in config_universe if sym]
        logger.info(
            "Using equity universe from config: %d symbols",
            len(symbols),
        )
        return symbols
    
    # Fallback to CSV file (config/universe_equity.csv)
    try:
        symbols = load_equity_universe()
        logger.info(
            "Using equity universe from CSV file: %d symbols",
            len(symbols),
        )
        return symbols
    except Exception as exc:
        logger.warning("Failed to load equity universe from CSV: %s", exc)
        # Return empty list - let the caller decide how to handle
        return []


def resolve_options_universe(
    cfg: AppConfig,
    kite: Optional[KiteConnect] = None,
    universe_snapshot: Optional[Dict[str, Any]] = None,
) -> Tuple[List[str], Dict[str, str]]:
    """
    Resolve options universe (logical underlyings and their FUT symbols).
    
    Args:
        cfg: Application configuration
        kite: Optional KiteConnect client (for resolving FUT symbols)
        universe_snapshot: Optional pre-loaded universe snapshot from scanner
        
    Returns:
        Tuple of (logical_underlyings, underlying_futs_map)
        - logical_underlyings: List of logical index names (e.g., ["NIFTY", "BANKNIFTY"])
        - underlying_futs_map: Dict mapping logical -> FUT tradingsymbol
    """
    trading = cfg.trading or {}
    config_underlyings = trading.get("options_underlyings", [])
    
    # Use universe snapshot if provided
    if universe_snapshot and isinstance(universe_snapshot, dict):
        logicals = [str(sym).strip().upper() for sym in universe_snapshot.get("fno", []) if sym]
        meta = universe_snapshot.get("meta") or {}
        underlying_futs: Dict[str, str] = {}
        for logical in logicals:
            info = meta.get(logical) or {}
            tradingsymbol = info.get("tradingsymbol")
            if tradingsymbol:
                underlying_futs[logical] = str(tradingsymbol).strip().upper()
        
        if logicals:
            logger.info(
                "Using options universe from scanner snapshot: %s",
                ", ".join(logicals),
            )
            return logicals, underlying_futs
    
    # Fallback to config
    if config_underlyings:
        logicals = [str(sym).strip().upper() for sym in config_underlyings if sym]
        logger.info(
            "Using options universe from config: %s",
            ", ".join(logicals),
        )
        
        # Resolve FUT symbols if kite available
        underlying_futs = {}
        if kite and logicals:
            try:
                underlying_futs = resolve_fno_symbols(kite, logicals)
                logger.info("Resolved %d option underlying FUTs", len(underlying_futs))
            except Exception as exc:
                logger.warning("Failed to resolve option underlying FUTs: %s", exc)
        
        return logicals, underlying_futs
    
    # Default fallback
    default_logicals = ["NIFTY", "BANKNIFTY", "FINNIFTY"]
    logger.warning(
        "No options underlyings in config or scanner, using defaults: %s",
        ", ".join(default_logicals),
    )
    return default_logicals, {}


def load_scanner_universe(
    cfg: AppConfig,
    kite: Optional[KiteConnect] = None,
) -> Optional[Dict[str, Any]]:
    """
    Load today's scanner universe snapshot if available.
    
    Args:
        cfg: Application configuration
        kite: Optional KiteConnect client (for scanning if needed)
        
    Returns:
        Universe snapshot dict or None if not available
    """
    if not kite:
        logger.info("No Kite client provided, skipping scanner universe load")
        return None
    
    try:
        scanner = MarketScanner(kite, cfg)
        data = scanner.load_today()
        
        if data:
            logger.info("Loaded today's scanner universe snapshot")
            return data
        else:
            logger.info("No scanner universe snapshot available for today")
            return None
    except Exception as exc:
        logger.warning("Failed to load scanner universe: %s", exc)
        return None
