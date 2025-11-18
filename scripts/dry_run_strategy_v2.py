#!/usr/bin/env python3
"""
Dry run test for StrategyEngineV2.

Loads config, constructs StrategyEngineV2, feeds synthetic candle and indicators,
and prints the returned OrderIntent and debug payload.
"""

import sys
from pathlib import Path

# Add parent directory to path
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

import logging
import yaml
from core.strategy_engine_v2 import StrategyEngineV2

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def load_config():
    """Load dev.yaml config."""
    config_path = BASE_DIR / "configs" / "dev.yaml"
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def main():
    """Main dry run."""
    logger.info("=" * 60)
    logger.info("StrategyEngineV2 Dry Run Test")
    logger.info("=" * 60)
    
    # Load config
    logger.info("Loading config from configs/dev.yaml")
    cfg = load_config()
    
    # Create StrategyEngineV2 from config
    logger.info("Creating StrategyEngineV2 from config")
    try:
        engine = StrategyEngineV2.from_config(cfg, logger)
        logger.info("StrategyEngineV2 created successfully")
    except Exception as exc:
        logger.error("Failed to create StrategyEngineV2: %s", exc, exc_info=True)
        return 1
    
    # Create synthetic candle and indicators for NIFTY
    logger.info("\nPreparing synthetic market data for NIFTY")
    
    candle = {
        "open": 18500.0,
        "high": 18550.0,
        "low": 18480.0,
        "close": 18530.0,
        "volume": 1000000,
    }
    
    indicators = {
        "ema20": 18520.0,
        "ema50": 18480.0,
        "ema100": 18450.0,
        "ema200": 18400.0,
        "rsi14": 62.5,
        "atr14": 45.0,
        "trend": "up",
    }
    
    logger.info("Candle: %s", candle)
    logger.info("Indicators: %s", indicators)
    
    # Call evaluate
    logger.info("\nCalling engine.evaluate()")
    try:
        intent, debug = engine.evaluate(
            logical="NIFTY",
            symbol="NIFTY24DECFUT",
            timeframe="5m",
            candle=candle,
            indicators=indicators,
            mode="PAPER",
            profile="INTRADAY",
            context={"test": True},
        )
        
        logger.info("\n" + "=" * 60)
        logger.info("RESULT")
        logger.info("=" * 60)
        
        logger.info("\nOrderIntent:")
        logger.info("  signal: %s", intent.signal)
        logger.info("  side: %s", intent.side)
        logger.info("  logical: %s", intent.logical)
        logger.info("  symbol: %s", intent.symbol)
        logger.info("  timeframe: %s", intent.timeframe)
        logger.info("  strategy_id: %s", intent.strategy_id)
        logger.info("  confidence: %.2f", intent.confidence)
        logger.info("  reason: %s", intent.reason)
        logger.info("  exit_reason: %s", intent.exit_reason)
        logger.info("  extra: %s", intent.extra)
        
        logger.info("\nDebug Payload:")
        for key, value in debug.items():
            if key == "indicators":
                logger.info("  indicators:")
                for ind_key, ind_val in value.items():
                    logger.info("    %s: %s", ind_key, ind_val)
            elif key == "candle":
                logger.info("  candle: %s", value)
            else:
                logger.info("  %s: %s", key, value)
        
        logger.info("\n" + "=" * 60)
        logger.info("Dry run completed successfully")
        logger.info("=" * 60)
        
        return 0
        
    except Exception as exc:
        logger.error("\nFailed to evaluate: %s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
