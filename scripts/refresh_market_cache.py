#!/usr/bin/env python3
"""
Refresh Market Data Cache Script

Purpose: Warm the market data cache at the start of the trading day (or on-demand).
This script fetches and caches historical candle data for all configured symbols
to ensure strategies have access to up-to-date data immediately.

Usage:
    python scripts/refresh_market_cache.py [--config path/to/config.yaml] [--timeframe 5m]
"""

import argparse
import logging
import sys
from pathlib import Path

# Add parent directory to path for imports
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from core.config import load_config
from core.kite_env import make_kite_client_from_env
from core.market_data_engine import MarketDataEngine
from core.universe import fno_underlyings, load_equity_universe
from core.universe_builder import load_universe
from data.instruments import resolve_fno_symbols
from types import SimpleNamespace

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Refresh market data cache for configured symbols"
    )
    parser.add_argument(
        "--config",
        type=str,
        default="configs/dev.yaml",
        help="Path to configuration YAML file (default: configs/dev.yaml)"
    )
    parser.add_argument(
        "--timeframe",
        type=str,
        default="5m",
        help="Timeframe for cache refresh (default: 5m)"
    )
    parser.add_argument(
        "--count",
        type=int,
        default=200,
        help="Number of candles to fetch (default: 200)"
    )
    parser.add_argument(
        "--symbols",
        type=str,
        nargs="+",
        help="Specific symbols to refresh (optional, defaults to configured universe)"
    )
    return parser.parse_args()


def get_symbols_from_config(cfg):
    """Extract symbols from configuration."""
    symbols = []
    
    # FnO universe
    fno_universe = cfg.trading.get("fno_universe", []) or []
    if isinstance(fno_universe, str):
        fno_universe = [fno_universe]
    
    logical_universe = [str(sym).strip().upper() for sym in fno_universe if sym]
    if not logical_universe:
        logical_universe = fno_underlyings()
    
    symbols.extend(logical_universe)
    
    # Equity universe
    equity_universe = load_equity_universe()
    symbols.extend(equity_universe)
    
    return list(set(symbols))


def main():
    """Main entry point."""
    args = parse_args()
    
    # Load configuration
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = (BASE_DIR / config_path).resolve()
    
    if not config_path.exists():
        logger.error("Configuration file not found: %s", config_path)
        sys.exit(1)
    
    logger.info("Loading configuration from %s", config_path)
    cfg = load_config(str(config_path))
    
    # Create Kite client
    try:
        kite = make_kite_client_from_env()
        logger.info("Kite client created successfully")
    except Exception as exc:
        logger.error("Failed to create Kite client: %s", exc)
        sys.exit(1)
    
    # Get symbols to refresh
    if args.symbols:
        symbols = [s.upper() for s in args.symbols]
        logger.info("Refreshing cache for specified symbols: %s", symbols)
    else:
        symbols = get_symbols_from_config(cfg)
        logger.info("Refreshing cache for %d symbols from config", len(symbols))
    
    # Resolve FnO symbols to tradingsymbols
    fno_logicals = [s for s in symbols if s in fno_underlyings()]
    if fno_logicals:
        logger.info("Resolving FnO symbols: %s", fno_logicals)
        shim = SimpleNamespace(api=kite)
        symbol_map = resolve_fno_symbols(fno_logicals, kite_client=shim)
        # Replace logical names with actual tradingsymbols
        symbols = [symbol_map.get(s, s) for s in symbols]
    
    # Load universe for token resolution
    universe_snapshot = load_universe()
    
    # Create market data engine
    artifacts_dir = BASE_DIR / "artifacts"
    cache_dir = artifacts_dir / "market_data"
    mde = MarketDataEngine(kite, universe_snapshot, cache_dir=cache_dir)
    logger.info("Market data engine initialized with cache_dir=%s", cache_dir)
    
    # Refresh cache for each symbol
    success_count = 0
    fail_count = 0
    
    for symbol in symbols:
        try:
            logger.info("Refreshing cache for %s (timeframe=%s, count=%d)", 
                       symbol, args.timeframe, args.count)
            mde.update_cache(symbol, args.timeframe, count=args.count)
            success_count += 1
            logger.info("✓ Cache refreshed for %s", symbol)
        except Exception as exc:
            logger.warning("✗ Failed to refresh cache for %s: %s", symbol, exc)
            fail_count += 1
    
    # Summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("Cache refresh complete")
    logger.info("  Success: %d symbols", success_count)
    logger.info("  Failed:  %d symbols", fail_count)
    logger.info("  Total:   %d symbols", len(symbols))
    logger.info("=" * 60)
    
    if fail_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
