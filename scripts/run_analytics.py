"""
Run Strategy Analytics Engine v1

Computes daily and historical performance metrics and saves them to:
    artifacts/analytics/daily/YYYY-MM-DD.json

Usage:
    python -m scripts.run_analytics
    python -m scripts.run_analytics --historical  # Load all historical data
    python -m scripts.run_analytics --mode live   # Use live mode journal
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime
from pathlib import Path

from analytics.strategy_analytics import StrategyAnalyticsEngine
from core.config import load_config
from core.logging_utils import setup_logging
from core.state_store import JournalStateStore, StateStore

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = BASE_DIR / "artifacts"
ANALYTICS_DIR = ARTIFACTS_DIR / "analytics"
DAILY_DIR = ANALYTICS_DIR / "daily"


def ensure_dirs():
    """Ensure analytics directories exist."""
    ANALYTICS_DIR.mkdir(parents=True, exist_ok=True)
    DAILY_DIR.mkdir(parents=True, exist_ok=True)


def run_analytics(mode: str = "paper", historical: bool = False):
    """
    Run analytics engine and save results.

    Args:
        mode: Trading mode ("paper" or "live")
        historical: If True, load all historical data instead of just today
    """
    logger.info("Starting Strategy Analytics Engine v1")
    logger.info("Mode: %s, Historical: %s", mode, historical)

    # Load config
    try:
        config_path = BASE_DIR / "configs" / "dev.yaml"
        if not config_path.exists():
            config_path = BASE_DIR / "config" / "dev.yaml"
        
        config = load_config(str(config_path)) if config_path.exists() else {}
        logger.info("Config loaded from: %s", config_path)
    except Exception as exc:
        logger.warning("Failed to load config: %s", exc)
        config = {}

    # Initialize stores
    journal_store = JournalStateStore(mode=mode)
    state_store = StateStore()

    # Ensure output directories exist
    ensure_dirs()

    # Instantiate analytics engine
    engine = StrategyAnalyticsEngine(
        journal_store=journal_store,
        state_store=state_store,
        logger=logger,
        config=config,
    )

    # Load fills
    logger.info("Loading fills...")
    engine.load_fills(today_only=not historical)

    # Compute metrics
    logger.info("Computing metrics...")
    daily_metrics = engine.compute_daily_metrics()
    strategy_metrics = engine.compute_strategy_metrics()
    symbol_metrics = engine.compute_symbol_metrics()

    # Build full payload
    payload = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "mode": mode,
        "historical": historical,
        "daily_metrics": daily_metrics,
        "strategy_metrics": strategy_metrics,
        "symbol_metrics": symbol_metrics,
        "generated_at": datetime.now().isoformat(),
    }

    # Save to file
    today = datetime.now().strftime("%Y-%m-%d")
    output_file = DAILY_DIR / f"{today}.json"
    
    try:
        with output_file.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)
        logger.info("Analytics saved to: %s", output_file)
    except Exception as exc:
        logger.error("Failed to save analytics: %s", exc)

    # Print summary to console
    print("\n" + "=" * 60)
    print("STRATEGY ANALYTICS SUMMARY")
    print("=" * 60)
    print(f"Date: {today}")
    print(f"Mode: {mode}")
    print(f"Daily PnL: {daily_metrics['realized_pnl']:+.2f}")
    print(f"Trades: {daily_metrics['num_trades']}")
    
    if daily_metrics['num_trades'] > 0:
        print(f"Win Rate: {daily_metrics['win_rate']:.1f}%")
        print(f"Biggest Winner: {daily_metrics['biggest_winner']:+.2f}")
        print(f"Biggest Loser: {daily_metrics['biggest_loser']:+.2f}")
        print(f"Avg Win: {daily_metrics['avg_win']:+.2f}")
        print(f"Avg Loss: {daily_metrics['avg_loss']:+.2f}")
        
        print(f"\nDistribution:")
        print(f"  Wins: {daily_metrics['pnl_distribution']['wins']}")
        print(f"  Losses: {daily_metrics['pnl_distribution']['losses']}")
        print(f"  Breakeven: {daily_metrics['pnl_distribution']['breakeven']}")
    
    if strategy_metrics:
        print(f"\nStrategies: {len(strategy_metrics)}")
        for strategy_code, metrics in strategy_metrics.items():
            print(f"  {strategy_code}: {metrics['trades']} trades, PnL: {metrics['realized_pnl']:+.2f}")
    
    if symbol_metrics:
        print(f"\nSymbols: {len(symbol_metrics)}")
        top_symbols = sorted(
            symbol_metrics.items(),
            key=lambda x: x[1]['realized_pnl'],
            reverse=True
        )[:5]
        for symbol, metrics in top_symbols:
            print(f"  {symbol}: {metrics['trades']} trades, PnL: {metrics['realized_pnl']:+.2f}")
    
    print("=" * 60)
    print(f"Full report: {output_file}")
    print("=" * 60 + "\n")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run Strategy Analytics Engine v1"
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="paper",
        choices=["paper", "live"],
        help="Trading mode (default: paper)",
    )
    parser.add_argument(
        "--historical",
        action="store_true",
        help="Load all historical data instead of just today",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Setup logging
    log_level_name = "DEBUG" if args.verbose else "INFO"
    setup_logging({"level": log_level_name, "directory": "logs", "file_prefix": "analytics"})

    # Run analytics
    try:
        run_analytics(mode=args.mode, historical=args.historical)
    except Exception as exc:
        logger.error("Analytics failed: %s", exc, exc_info=True)
        raise


if __name__ == "__main__":
    main()
