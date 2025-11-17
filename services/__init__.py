"""
Architecture v3 Services Package

Service-oriented, event-driven trading system components.
Each service is a standalone component that communicates via EventBus.

Available Services:
- EventBus: In-process event bus for service communication
- MarketDataService: Unified market data access with caching
- StrategyService: Strategy evaluation and signal fusion
- ExecutionService: Order validation and broker routing
- PortfolioService: Position tracking and PnL management
- DashboardFeed: State aggregation for dashboard
"""

from services.event_bus import EventBus
from services.market_data_service import MarketDataService
from services.strategy_service_v3 import StrategyService
from services.execution_service import ExecutionService, OrderResult
from services.portfolio_service import PortfolioService
from services.dashboard_feed import DashboardFeed

__all__ = [
    "EventBus",
    "MarketDataService",
    "StrategyService",
    "ExecutionService",
    "OrderResult",
    "PortfolioService",
    "DashboardFeed",
]
