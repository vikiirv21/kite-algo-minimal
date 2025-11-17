#!/usr/bin/env python3
"""
HFT Architecture v3 - Example Wiring

Demonstrates how to wire together all v3 services:
- EventBus
- MarketDataService
- StrategyService
- ExecutionService
- PortfolioService
- DashboardFeed

This script shows the integration pattern without running a full trading loop.
"""

import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime, timezone

from core.market_data_engine import MarketDataEngine
from core.strategy_engine_v3 import StrategyEngineV3
from data.broker_feed import BrokerFeed
from services import (
    DashboardFeed,
    EventBus,
    ExecutionService,
    MarketDataService,
    PortfolioService,
    StrategyService,
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MockBroker:
    """Mock broker for demonstration."""
    
    def place_order(self, symbol, side, qty, order_type="MARKET", price=None):
        """Simulate order placement."""
        logger.info(f"MockBroker: Placing {order_type} {side} {qty} {symbol}")
        return {
            "order_id": f"mock-{symbol}-{datetime.now().timestamp()}",
            "status": "PLACED",
            "message": "Mock order placed successfully"
        }


def main():
    """Main demonstration function."""
    
    logger.info("=" * 70)
    logger.info("HFT Architecture v3 - Service Wiring Example")
    logger.info("=" * 70)
    
    # ========================================================================
    # Step 1: Initialize EventBus
    # ========================================================================
    logger.info("\n[Step 1] Initializing EventBus...")
    event_bus = EventBus(buffer_size=1000)
    
    # ========================================================================
    # Step 2: Initialize MarketDataService
    # ========================================================================
    logger.info("\n[Step 2] Initializing MarketDataService...")
    
    # Note: In production, you would pass real KiteConnect client
    # For demo, we use None which will gracefully handle missing data
    broker_feed = None  # BrokerFeed(kite_client) in production
    market_data_engine = None  # MarketDataEngine(kite_client, universe) in production
    
    mds = MarketDataService(
        broker_feed=broker_feed,
        market_data_engine=market_data_engine,
        cache_ttl_seconds=1.0
    )
    
    # ========================================================================
    # Step 3: Initialize StrategyEngineV3
    # ========================================================================
    logger.info("\n[Step 3] Initializing StrategyEngineV3...")
    
    # Minimal strategy config
    strategy_config = {
        "primary_tf": "5m",
        "secondary_tf": "15m",
        "strategies": [
            {"id": "ema20_50", "enabled": True},
            {"id": "trend", "enabled": True},
        ],
        "playbooks": {
            "trend_follow": {"min_trend_score": 0.7},
            "pullback": {"max_pullback_pct": 0.02},
        }
    }
    
    # Note: StrategyEngineV3 expects bus with async methods
    # For this demo, we pass None
    strategy_engine = StrategyEngineV3(cfg=strategy_config, bus=None)
    
    # ========================================================================
    # Step 4: Initialize StrategyService
    # ========================================================================
    logger.info("\n[Step 4] Initializing StrategyService...")
    
    strategy_service = StrategyService(
        strategy_engine=strategy_engine,
        market_data_service=mds,
        event_bus=event_bus,
        primary_tf="5m",
        secondary_tf="15m"
    )
    
    # ========================================================================
    # Step 5: Initialize PortfolioService
    # ========================================================================
    logger.info("\n[Step 5] Initializing PortfolioService...")
    
    portfolio_service = PortfolioService(
        initial_capital=100000.0,
        event_bus=event_bus,
        checkpoint_dir=Path("artifacts/portfolio")
    )
    
    # Subscribe to order.filled events
    event_bus.subscribe("order.filled", portfolio_service.on_fill)
    
    # ========================================================================
    # Step 6: Initialize ExecutionService
    # ========================================================================
    logger.info("\n[Step 6] Initializing ExecutionService...")
    
    mock_broker = MockBroker()
    
    execution_service = ExecutionService(
        broker=mock_broker,
        portfolio_service=portfolio_service,
        event_bus=event_bus,
        mode="paper",
        max_position_size=100
    )
    
    # ========================================================================
    # Step 7: Initialize DashboardFeed
    # ========================================================================
    logger.info("\n[Step 7] Initializing DashboardFeed...")
    
    dashboard_feed = DashboardFeed(
        event_bus=event_bus,
        max_signals=100,
        max_orders=100
    )
    
    # ========================================================================
    # Step 8: Demonstrate Trading Loop
    # ========================================================================
    logger.info("\n[Step 8] Demonstrating Trading Loop...")
    logger.info("-" * 70)
    
    # Example symbols to process
    symbols = ["RELIANCE", "TCS", "INFY"]
    
    for symbol in symbols:
        logger.info(f"\nProcessing {symbol}...")
        
        # Step 8a: Run strategy for symbol
        intent = strategy_service.run_symbol(symbol, ts=None)
        
        logger.info(f"  → Intent: {intent.action} (confidence={intent.confidence:.2f})")
        logger.info(f"  → Reason: {intent.reason}")
        
        # Step 8b: Execute if actionable
        if intent.action in ("BUY", "SELL") and intent.confidence > 0.5:
            logger.info(f"  → Executing order...")
            result = execution_service.execute(intent)
            logger.info(f"  → Result: {result.status} - {result.message}")
        else:
            logger.info(f"  → Skipping execution (not actionable)")
    
    # ========================================================================
    # Step 9: Display Dashboard Snapshot
    # ========================================================================
    logger.info("\n[Step 9] Dashboard Snapshot:")
    logger.info("-" * 70)
    
    snapshot = dashboard_feed.get_snapshot()
    
    logger.info(f"\nSignals: {len(snapshot['signals'])}")
    for signal in snapshot['signals'][-3:]:  # Last 3
        logger.info(f"  - {signal.get('symbol')}: {signal.get('action')} "
                   f"(confidence={signal.get('confidence', 0):.2f})")
    
    logger.info(f"\nOrders: {len(snapshot['orders'])}")
    for order in snapshot['orders'][-3:]:  # Last 3
        logger.info(f"  - {order.get('symbol')}: {order.get('side')} "
                   f"{order.get('qty')} @ {order.get('avg_price', 0):.2f}")
    
    logger.info(f"\nPortfolio:")
    logger.info(f"  - Cash: ₹{snapshot['portfolio']['cash']:,.2f}")
    logger.info(f"  - Equity: ₹{snapshot['portfolio']['equity']:,.2f}")
    logger.info(f"  - Realized P&L: ₹{snapshot['portfolio']['realized_pnl']:,.2f}")
    logger.info(f"  - Positions: {snapshot['portfolio']['position_count']}")
    
    logger.info(f"\nPositions:")
    for pos in snapshot['positions']:
        logger.info(f"  - {pos.get('symbol')}: {pos.get('qty')} @ "
                   f"{pos.get('avg_price', 0):.2f}")
    
    # ========================================================================
    # Step 10: Verify Event Flow
    # ========================================================================
    logger.info("\n[Step 10] Event Bus Stats:")
    logger.info("-" * 70)
    
    logger.info(f"Total subscribers: {event_bus.subscriber_count()}")
    logger.info(f"  - signals.fused: {event_bus.subscriber_count('signals.fused')}")
    logger.info(f"  - order.filled: {event_bus.subscriber_count('order.filled')}")
    logger.info(f"  - portfolio.updated: {event_bus.subscriber_count('portfolio.updated')}")
    
    recent_events = event_bus.get_recent_events(limit=10)
    logger.info(f"\nRecent events: {len(recent_events)}")
    for event in recent_events[-5:]:  # Last 5
        logger.info(f"  - {event.get('type')} @ {event.get('timestamp')}")
    
    # ========================================================================
    # Summary
    # ========================================================================
    logger.info("\n" + "=" * 70)
    logger.info("✓ All services initialized and wired successfully!")
    logger.info("=" * 70)
    
    logger.info("\nService Integration Summary:")
    logger.info("  1. EventBus: Central communication hub")
    logger.info("  2. MarketDataService: Provides price and indicator data")
    logger.info("  3. StrategyService: Evaluates strategies and generates signals")
    logger.info("  4. ExecutionService: Validates and executes orders")
    logger.info("  5. PortfolioService: Tracks positions and P&L")
    logger.info("  6. DashboardFeed: Aggregates state for monitoring")
    
    logger.info("\nNext Steps:")
    logger.info("  - Wire into run_trader.py or run_day.py")
    logger.info("  - Add real Kite API credentials")
    logger.info("  - Configure strategy parameters")
    logger.info("  - Enable live trading mode")
    
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
        sys.exit(1)
    except Exception as exc:
        logger.error("Fatal error: %s", exc, exc_info=True)
        sys.exit(1)
