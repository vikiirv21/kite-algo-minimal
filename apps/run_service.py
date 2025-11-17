"""
Service Launcher for Architecture v3

Simple launcher script to run individual v3 services.

Usage:
    python -m apps.run_service marketdata
    python -m apps.run_service trader_fno
    python -m apps.run_service strategy
    python -m apps.run_service risk_portfolio
    python -m apps.run_service execution
    python -m apps.run_service journal
    python -m apps.run_service trader_options
    python -m apps.run_service trader_equity

Each service runs independently with its own EventBus instance.
"""

from __future__ import annotations

import argparse
import logging
import sys

from pathlib import Path
import yaml

from services.common.event_bus import InMemoryEventBus
from services.marketdata.service_marketdata import MarketDataService, ServiceConfig as MarketDataConfig
from services.trader_fno.service_trader_fno import TraderFnoService, ServiceConfig as TraderFnoConfig
from services.trader_options.service_trader_options import TraderOptionsService, ServiceConfig as TraderOptionsConfig
from services.trader_equity.service_trader_equity import TraderEquityService, ServiceConfig as TraderEquityConfig
from services.strategy.service_strategy import StrategyService, ServiceConfig as StrategyConfig
from services.risk_portfolio.service_risk_portfolio import RiskPortfolioService, ServiceConfig as RiskPortfolioConfig
from services.execution.service_execution import ExecutionService, ServiceConfig as ExecutionConfig
from services.journal.service_journal import JournalService, ServiceConfig as JournalConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)


SERVICE_REGISTRY = {
    "marketdata": (MarketDataService, MarketDataConfig),
    "trader_fno": (TraderFnoService, TraderFnoConfig),
    "trader_options": (TraderOptionsService, TraderOptionsConfig),
    "trader_equity": (TraderEquityService, TraderEquityConfig),
    "strategy": (StrategyService, StrategyConfig),
    "risk_portfolio": (RiskPortfolioService, RiskPortfolioConfig),
    "execution": (ExecutionService, ExecutionConfig),
    "exec": (ExecutionService, ExecutionConfig),  # Alias for execution
    "journal": (JournalService, JournalConfig),
}


def main() -> int:
    """
    Main entry point for service launcher.
    
    Returns:
        Exit code (0 for success, 1 for error)
    """
    parser = argparse.ArgumentParser(
        description="Launch an Architecture v3 service",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Available services:
  marketdata      - Real-time market data distribution
  trader_fno      - FnO futures trading
  trader_options  - Options trading
  trader_equity   - Equity cash trading
  strategy        - Strategy signal generation
  risk_portfolio  - Risk management and portfolio tracking
  execution       - Order execution
  journal         - Trading event logging

Examples:
  python -m apps.run_service marketdata
  python -m apps.run_service strategy
        """
    )
    
    parser.add_argument(
        "service_name",
        choices=list(SERVICE_REGISTRY.keys()),
        help="Name of the service to run"
    )
    
    parser.add_argument(
        "--mode",
        choices=["paper", "live"],
        default="paper",
        help="Trading mode for execution service (default: paper)"
    )
    
    parser.add_argument(
        "--config",
        default="configs/dev.yaml",
        help="Path to configuration file (default: configs/dev.yaml)"
    )
    
    args = parser.parse_args()
    
    service_name = args.service_name
    
    if service_name not in SERVICE_REGISTRY:
        logger.error(f"Unknown service: {service_name}")
        logger.info(f"Available services: {', '.join(SERVICE_REGISTRY.keys())}")
        return 1
    
    # Get service class and config class
    service_class, config_class = SERVICE_REGISTRY[service_name]
    
    logger.info(f"Initializing service: {service_name}")
    
    # Create event bus
    event_bus = InMemoryEventBus(max_queue_size=1000)
    event_bus.start()
    
    # Load configuration from file if needed
    app_cfg = {}
    config_path = Path(args.config)
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                app_cfg = yaml.safe_load(f) or {}
            logger.info(f"Loaded configuration from {config_path}")
        except Exception as e:
            logger.warning(f"Failed to load config from {config_path}: {e}")
    
    # Special handling for execution service
    if service_name in ("execution", "exec"):
        # Get mode from command line or config
        mode = args.mode
        if mode is None:
            mode = app_cfg.get("trading", {}).get("mode", "paper")
        
        # Get execution config with slippage
        exec_cfg = app_cfg.get("execution", {})
        exec_cfg["slippage_bps"] = exec_cfg.get("slippage_bps", 5.0)
        exec_cfg["mode"] = mode
        
        logger.info(f"Execution service mode: {mode}")
        service = ExecutionService(bus=event_bus, cfg=exec_cfg, mode=mode)
    else:
        # Create standard service config
        config = config_class(name=service_name, enabled=True)
        # Instantiate service
        service = service_class(event_bus=event_bus, config=config)
    
    try:
        # Run service forever
        logger.info(f"Starting service: {service_name}")
        service.run_forever()
    except KeyboardInterrupt:
        logger.info(f"Service {service_name} interrupted by user")
    except Exception as e:
        logger.error(f"Service {service_name} failed: {e}", exc_info=True)
        return 1
    finally:
        # Cleanup
        event_bus.stop()
        logger.info(f"Service {service_name} shutdown complete")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
