#!/usr/bin/env python3
"""
Benchmark Recorder Script

Periodically snapshots NIFTY / BANKNIFTY / FINNIFTY index levels to disk.
This runs during market hours and appends data to daily JSONL files.

Usage:
    python -m scripts.run_benchmark_recorder --config configs/dev.yaml --interval-seconds 60
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, time as dt_time
from pathlib import Path
from typing import Dict, Optional

import pytz

# Add parent directory to path to allow imports
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from analytics.benchmarks import append_benchmark_snapshot
from broker.auth import make_kite_client_from_env, token_is_valid
from core.config import load_config
from data.instruments import load_instrument_token_map

logger = logging.getLogger(__name__)


# Index symbol mapping: logical name -> NSE index symbol
INDEX_SYMBOLS = {
    "NIFTY": "NIFTY 50",
    "BANKNIFTY": "NIFTY BANK",
    "FINNIFTY": "NIFTY FIN SERVICE",
}


def setup_logging(level: str = "INFO") -> None:
    """Setup logging configuration."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def is_market_hours(market_open: str, market_close: str) -> bool:
    """
    Check if current IST time is within market hours.
    
    Args:
        market_open: Market open time in HH:MM format (IST)
        market_close: Market close time in HH:MM format (IST)
        
    Returns:
        True if within market hours, False otherwise
    """
    ist = pytz.timezone("Asia/Kolkata")
    now_ist = datetime.now(ist).time()
    
    try:
        open_time = dt_time.fromisoformat(market_open)
        close_time = dt_time.fromisoformat(market_close)
        return open_time <= now_ist <= close_time
    except Exception as exc:
        logger.warning("Failed to parse market hours: %s", exc)
        # Default to market hours if parsing fails
        return dt_time(9, 15) <= now_ist <= dt_time(15, 30)


def fetch_index_prices(kite) -> Dict[str, Optional[float]]:
    """
    Fetch current prices for benchmark indices.
    
    Args:
        kite: KiteConnect instance
        
    Returns:
        Dictionary with index names as keys and prices as values
        (None if fetching failed for that index)
    """
    prices = {
        "nifty": None,
        "banknifty": None,
        "finnifty": None,
    }
    
    # Build list of instrument tokens to fetch
    instrument_tokens = []
    token_map = {}  # maps token back to our key
    
    # Load instrument token map
    try:
        token_lookup = load_instrument_token_map(kite=kite, segments=("NSE",))
    except Exception as exc:
        logger.error("Failed to load instrument token map: %s", exc)
        return prices
    
    for key, symbol in INDEX_SYMBOLS.items():
        token = token_lookup.get(symbol.upper())
        if token:
            instrument_tokens.append(token)
            token_map[token] = key.lower()
        else:
            logger.warning("Could not find instrument token for %s (%s)", key, symbol)
    
    if not instrument_tokens:
        logger.error("No valid instrument tokens found for indices")
        return prices
    
    # Fetch LTP for all indices in one call
    try:
        quotes = kite.ltp([f"NSE:{token}" for token in instrument_tokens])
        
        for token, key in token_map.items():
            quote_key = f"NSE:{token}"
            if quote_key in quotes:
                ltp = quotes[quote_key].get("last_price")
                if ltp:
                    prices[key] = float(ltp)
                    logger.info("Fetched %s: %.2f", key.upper(), ltp)
            else:
                logger.warning("No quote data for %s (token=%s)", key.upper(), token)
                
    except Exception as exc:
        logger.error("Failed to fetch index prices: %s", exc)
    
    return prices


def run_recorder(
    config_path: str,
    interval_seconds: int = 60,
    max_runtime_seconds: Optional[int] = None,
) -> None:
    """
    Main recorder loop.
    
    Args:
        config_path: Path to config file
        interval_seconds: Seconds to wait between snapshots
        max_runtime_seconds: Maximum runtime in seconds (None = unlimited)
    """
    logger.info("Starting benchmark recorder")
    logger.info("Config: %s", config_path)
    logger.info("Interval: %d seconds", interval_seconds)
    logger.info("Max runtime: %s", max_runtime_seconds or "unlimited")
    
    # Load config
    try:
        config = load_config(config_path)
    except Exception as exc:
        logger.error("Failed to load config: %s", exc)
        sys.exit(1)
    
    # Get market hours from config
    session = config.raw.get("session", {})
    market_open = session.get("market_open_ist", "09:15")
    market_close = session.get("market_close_ist", "15:30")
    logger.info("Market hours (IST): %s - %s", market_open, market_close)
    
    # Initialize Kite client
    try:
        kite = make_kite_client_from_env()
        if not token_is_valid(kite):
            logger.error("Kite token is not valid. Please run login_kite script first.")
            sys.exit(1)
        logger.info("Kite client initialized successfully")
    except Exception as exc:
        logger.error("Failed to initialize Kite client: %s", exc)
        sys.exit(1)
    
    start_time = time.time()
    snapshot_count = 0
    
    try:
        while True:
            # Check max runtime
            if max_runtime_seconds and (time.time() - start_time) > max_runtime_seconds:
                logger.info("Max runtime reached, exiting")
                break
            
            # Check if we're within market hours
            if not is_market_hours(market_open, market_close):
                logger.info("Outside market hours, sleeping for %d seconds", interval_seconds)
                time.sleep(interval_seconds)
                continue
            
            # Fetch current prices
            now = datetime.now()
            prices = fetch_index_prices(kite)
            
            # Append snapshot
            try:
                append_benchmark_snapshot(
                    ts=now,
                    nifty=prices.get("nifty"),
                    banknifty=prices.get("banknifty"),
                    finnifty=prices.get("finnifty"),
                )
                snapshot_count += 1
                logger.info("Snapshot #%d recorded at %s", snapshot_count, now.isoformat())
            except Exception as exc:
                logger.error("Failed to append snapshot: %s", exc)
            
            # Sleep until next interval
            time.sleep(interval_seconds)
            
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down")
    except Exception as exc:
        logger.error("Unexpected error in recorder loop: %s", exc, exc_info=True)
    
    logger.info("Recorder stopped after %d snapshots", snapshot_count)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Record benchmark index prices to disk periodically"
    )
    parser.add_argument(
        "--config",
        type=str,
        default="configs/dev.yaml",
        help="Path to config file (default: configs/dev.yaml)",
    )
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=60,
        help="Seconds between snapshots (default: 60)",
    )
    parser.add_argument(
        "--max-runtime-seconds",
        type=int,
        default=None,
        help="Maximum runtime in seconds (default: unlimited)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )
    
    args = parser.parse_args()
    
    setup_logging(args.log_level)
    
    run_recorder(
        config_path=args.config,
        interval_seconds=args.interval_seconds,
        max_runtime_seconds=args.max_runtime_seconds,
    )


if __name__ == "__main__":
    main()
