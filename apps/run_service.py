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
    
    # Create service config
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
