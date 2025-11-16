#!/usr/bin/env python3
"""
Backtest Runner v3 - CLI for running offline backtests.

This script runs backtests using BacktestEngineV3, which reuses core components
from live/paper trading (StrategyEngine, PortfolioEngine, RiskEngine, etc.)

Usage:
    python -m scripts.run_backtest_v3 --config configs/dev.yaml --bt-config configs/backtest.dev.yaml
    python -m scripts.run_backtest_v3 --config configs/dev.yaml --symbols NIFTY,BANKNIFTY --start 2025-01-01 --end 2025-01-05
    python -m scripts.run_backtest_v3 --config configs/dev.yaml --strategies ema20_50_intraday_v2 --data-source csv
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Add parent directory to path
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from backtest.engine_v3 import BacktestConfig, BacktestEngineV3
from core.config import load_config
from core.logging_utils import setup_logging

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Backtest Engine v3 - Offline backtesting with core component reuse"
    )
    
    # Config files
    parser.add_argument(
        "--config",
        type=str,
        required=True,
        help="Main trading config YAML file (e.g., configs/dev.yaml)",
    )
    parser.add_argument(
        "--bt-config",
        type=str,
        help="Backtest-specific config YAML file (optional)",
    )
    
    # Backtest parameters (can override config file)
    parser.add_argument(
        "--symbols",
        type=str,
        help="Comma-separated list of symbols (e.g., NIFTY,BANKNIFTY)",
    )
    parser.add_argument(
        "--strategies",
        type=str,
        help="Comma-separated list of strategy codes (e.g., ema20_50_intraday_v2)",
    )
    parser.add_argument(
        "--start",
        type=str,
        required=True,
        help="Start date in YYYY-MM-DD format",
    )
    parser.add_argument(
        "--end",
        type=str,
        required=True,
        help="End date in YYYY-MM-DD format",
    )
    parser.add_argument(
        "--data-source",
        type=str,
        default="csv",
        choices=["csv", "hdf", "kite_historical"],
        help="Data source for historical data (default: csv)",
    )
    parser.add_argument(
        "--timeframe",
        type=str,
        default="5m",
        choices=["1m", "5m", "15m", "1h", "1d"],
        help="Bar timeframe (default: 5m)",
    )
    parser.add_argument(
        "--initial-equity",
        type=float,
        help="Initial capital (default: from config or 100000)",
    )
    parser.add_argument(
        "--position-sizing",
        type=str,
        default="fixed_qty",
        choices=["fixed_qty", "fixed_risk_atr"],
        help="Position sizing mode (default: fixed_qty)",
    )
    parser.add_argument(
        "--enable-guardian",
        action="store_true",
        help="Enable TradeGuardian pre-execution checks",
    )
    
    # Logging
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )
    
    return parser.parse_args()


def load_backtest_config(
    main_config_path: str,
    bt_config_path: str | None,
    args: argparse.Namespace,
) -> tuple[dict, BacktestConfig]:
    """
    Load and merge backtest configuration.
    
    Args:
        main_config_path: Path to main config YAML
        bt_config_path: Path to backtest config YAML (optional)
        args: Parsed command line arguments
        
    Returns:
        Tuple of (main_config_dict, BacktestConfig)
    """
    # Load main config
    main_config = load_config(main_config_path)
    main_config_dict = main_config.raw if hasattr(main_config, "raw") else {}
    
    # Load backtest config if provided
    bt_config_dict = {}
    if bt_config_path:
        bt_config_obj = load_config(bt_config_path)
        bt_config_dict = bt_config_obj.raw if hasattr(bt_config_obj, "raw") else {}
    
    # Extract backtest section from main config or bt config
    backtest_section = bt_config_dict.get("backtest", {})
    if not backtest_section:
        backtest_section = main_config_dict.get("backtest", {})
    
    # Build symbols list
    symbols = []
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    elif backtest_section.get("symbols"):
        symbols = backtest_section["symbols"]
    elif main_config_dict.get("trading", {}).get("fno_universe"):
        symbols = main_config_dict["trading"]["fno_universe"]
    else:
        symbols = ["NIFTY", "BANKNIFTY"]  # Default
    
    # Build strategies list
    strategies = []
    if args.strategies:
        strategies = [s.strip() for s in args.strategies.split(",")]
    elif backtest_section.get("strategies"):
        strategies = backtest_section["strategies"]
    elif main_config_dict.get("strategy_engine", {}).get("strategies_v2"):
        strategies = main_config_dict["strategy_engine"]["strategies_v2"]
    else:
        strategies = ["ema20_50_intraday_v2"]  # Default
    
    # Determine initial equity
    initial_equity = args.initial_equity
    if initial_equity is None:
        initial_equity = backtest_section.get("initial_equity")
    if initial_equity is None:
        initial_equity = main_config_dict.get("trading", {}).get("paper_capital", 100000.0)
    
    # Build BacktestConfig
    bt_config = BacktestConfig(
        symbols=symbols,
        strategies=strategies,
        start_date=args.start,
        end_date=args.end,
        data_source=args.data_source,
        timeframe=args.timeframe,
        initial_equity=float(initial_equity),
        position_sizing_mode=args.position_sizing,
        portfolio_config=main_config_dict.get("portfolio"),
        risk_config=main_config_dict.get("risk"),
        regime_config=main_config_dict.get("regime"),
        enable_guardian=args.enable_guardian,
    )
    
    return main_config_dict, bt_config


def main():
    """Main entry point."""
    args = parse_args()
    
    # Setup logging
    setup_logging(level=args.log_level)
    
    logger.info("=" * 80)
    logger.info("Backtest Engine v3 - Offline Backtesting")
    logger.info("=" * 80)
    
    # Load configuration
    try:
        main_config, bt_config = load_backtest_config(
            args.config,
            args.bt_config,
            args,
        )
    except Exception as e:
        logger.error("Failed to load configuration: %s", e, exc_info=True)
        return 1
    
    # Log configuration
    logger.info("Backtest Configuration:")
    logger.info("  Symbols: %s", bt_config.symbols)
    logger.info("  Strategies: %s", bt_config.strategies)
    logger.info("  Date Range: %s to %s", bt_config.start_date, bt_config.end_date)
    logger.info("  Data Source: %s", bt_config.data_source)
    logger.info("  Timeframe: %s", bt_config.timeframe)
    logger.info("  Initial Equity: %.2f", bt_config.initial_equity)
    logger.info("  Position Sizing: %s", bt_config.position_sizing_mode)
    logger.info("  Guardian Enabled: %s", bt_config.enable_guardian)
    
    # Initialize backtest engine
    try:
        engine = BacktestEngineV3(
            bt_config=bt_config,
            config=main_config,
            logger_instance=logger,
        )
    except Exception as e:
        logger.error("Failed to initialize backtest engine: %s", e, exc_info=True)
        return 1
    
    # Run backtest
    try:
        logger.info("Starting backtest...")
        result = engine.run()
        
        # Log results
        logger.info("=" * 80)
        logger.info("Backtest Complete!")
        logger.info("=" * 80)
        logger.info("Run ID: %s", result.run_id)
        logger.info("Results Directory: %s", engine.backtest_dir)
        logger.info("")
        logger.info("Overall Metrics:")
        for key, value in result.overall_metrics.items():
            if isinstance(value, float):
                logger.info("  %s: %.2f", key, value)
            else:
                logger.info("  %s: %s", key, value)
        logger.info("")
        logger.info("Files Generated:")
        logger.info("  - config.json")
        logger.info("  - summary.json")
        logger.info("  - trades.csv")
        logger.info("  - equity_curve.json")
        logger.info("=" * 80)
        
        return 0
        
    except Exception as e:
        logger.error("Backtest failed: %s", e, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
