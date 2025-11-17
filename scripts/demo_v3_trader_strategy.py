#!/usr/bin/env python3
"""
End-to-End Demo: Trader -> Strategy Flow

This script demonstrates the complete v3 architecture flow:
1. Start EventBus
2. Start StrategyService 
3. Start TraderFnoService (publishes fake bars)
4. TraderFnoService generates bar events
5. TraderFnoService publishes eval requests to StrategyService
6. StrategyService processes requests and emits signals
7. Print all signals received

This validates the full pipeline works end-to-end.
"""

import sys
import time
import logging
from pathlib import Path
from threading import Thread

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.common.event_bus import InMemoryEventBus, Event
from services.strategy.service_strategy import StrategyService, ServiceConfig as StrategyConfig
from services.trader_fno.service_trader_fno import TraderFnoService, ServiceConfig as TraderFnoConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)


def run_service_thread(service):
    """Run service in a separate thread."""
    try:
        service.run_forever()
    except Exception as e:
        logger.error(f"Service thread error: {e}", exc_info=True)


def main():
    """Run the end-to-end demo."""
    logger.info("=" * 60)
    logger.info("V3 ARCHITECTURE END-TO-END DEMO")
    logger.info("=" * 60)
    
    # Track signals received
    signals_received = []
    
    def signal_monitor(event: Event):
        """Monitor all signals published."""
        logger.info(f"SIGNAL RECEIVED: {event.type}")
        logger.info(f"  Symbol: {event.payload.get('symbol')}")
        logger.info(f"  Action: {event.payload.get('action')}")
        logger.info(f"  Price: {event.payload.get('price')}")
        logger.info(f"  Asset Class: {event.payload.get('asset_class')}")
        signals_received.append(event.payload)
    
    # Step 1: Create and start EventBus
    logger.info("\nStep 1: Starting InMemoryEventBus...")
    bus = InMemoryEventBus(max_queue_size=1000)
    bus.start()
    logger.info("✓ EventBus started")
    
    # Subscribe to all signals for monitoring
    bus.subscribe("signals.*", signal_monitor)
    logger.info("✓ Subscribed to signals.* for monitoring")
    
    # Step 2: Start StrategyService
    logger.info("\nStep 2: Starting StrategyService...")
    strategy_config = StrategyConfig(
        name="strategy",
        enabled=True,
        history_lookback=200,
        strategies=[],
        timeframe="5m"
    )
    strategy_service = StrategyService(event_bus=bus, config=strategy_config)
    strategy_thread = Thread(
        target=run_service_thread, 
        args=(strategy_service,), 
        daemon=True
    )
    strategy_thread.start()
    logger.info("✓ StrategyService started")
    
    # Step 3: Start TraderFnoService
    logger.info("\nStep 3: Starting TraderFnoService...")
    trader_config = TraderFnoConfig(
        name="trader_fno",
        enabled=True,
        symbols=["NIFTY", "BANKNIFTY"]
    )
    trader_service = TraderFnoService(event_bus=bus, config=trader_config)
    trader_thread = Thread(
        target=run_service_thread,
        args=(trader_service,),
        daemon=True
    )
    trader_thread.start()
    logger.info("✓ TraderFnoService started")
    
    # Step 4: Let services run for a bit
    logger.info("\nStep 4: Running pipeline for 15 seconds...")
    logger.info("(TraderFnoService will generate fake bars and eval requests)")
    logger.info("(StrategyService will process requests and emit signals)")
    
    try:
        for i in range(15):
            time.sleep(1)
            if i % 5 == 0:
                logger.info(f"  ... {i} seconds elapsed, {len(signals_received)} signals received")
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    
    # Step 5: Shutdown
    logger.info("\nStep 5: Shutting down services...")
    strategy_service.running = False
    trader_service.running = False
    bus.stop()
    logger.info("✓ Services stopped")
    
    # Step 6: Summary
    logger.info("\n" + "=" * 60)
    logger.info("DEMO SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Total signals received: {len(signals_received)}")
    
    if signals_received:
        logger.info("\nSignal breakdown by symbol:")
        symbol_counts = {}
        for signal in signals_received:
            symbol = signal.get('symbol', 'UNKNOWN')
            symbol_counts[symbol] = symbol_counts.get(symbol, 0) + 1
        
        for symbol, count in symbol_counts.items():
            logger.info(f"  {symbol}: {count} signals")
    
    logger.info("\n✓ End-to-end pipeline working correctly!")
    logger.info("=" * 60)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
