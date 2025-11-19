#!/usr/bin/env python3
"""
Integration test for ExecutionEngineV3 Step 1 with paper_engine.

This script tests the minimal integration by:
1. Creating a minimal config
2. Mocking necessary components
3. Testing signal flow through paper_engine to ExecutionEngineV3
"""

import sys
import logging
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timezone
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from execution.engine_v3 import ExecutionEngineV3, ExecutionContext
from engine.execution_v3_integration import create_execution_engine_v3, convert_to_order_intent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_integration():
    """Test ExecutionEngineV3 integration."""
    
    print("=" * 60)
    print("ExecutionEngineV3 Step 1 Integration Test")
    print("=" * 60)
    
    # Create config
    config = {
        "execution": {
            "engine": "v3",
            "default_quantity": 1,
        },
        "trading": {
            "default_quantity": 1,
            "default_product": "MIS",
        }
    }
    
    # Create mocks
    state_store = Mock()
    state_store.load_checkpoint = Mock(return_value={})
    state_store.save_checkpoint = Mock()
    
    trade_recorder = Mock()
    trade_recorder.log_order = Mock()
    
    broker_feed = Mock()
    broker_feed.get_ltp = Mock(return_value=19500.0)
    
    # Test 1: Create ExecutionEngineV3 via integration helper
    print("\n[Test 1] Creating ExecutionEngineV3 via integration helper...")
    engine = create_execution_engine_v3(
        config=config,
        market_data_engine=broker_feed,
        trade_recorder=trade_recorder,
        state_store=state_store
    )
    
    assert engine is not None, "Engine should be created"
    assert isinstance(engine, ExecutionEngineV3), "Should be ExecutionEngineV3 instance"
    print("✓ ExecutionEngineV3 created successfully")
    
    # Test 2: Convert signal to OrderIntent + ExecutionContext
    print("\n[Test 2] Converting signal to OrderIntent + ExecutionContext...")
    intent, context = convert_to_order_intent(
        symbol="NIFTY24DECFUT",
        signal="BUY",
        qty=1,
        price=19500.0,
        strategy_code="EMA_20_50",
        logical_symbol="NIFTY",
        product="MIS",
        mode="paper",
        timeframe="5m",
        exchange="NFO"
    )
    
    assert intent.signal == "BUY", "Intent should have BUY signal"
    assert context.symbol == "NIFTY24DECFUT", "Context should have symbol"
    assert context.logical_symbol == "NIFTY", "Context should have logical_symbol"
    print("✓ Intent and context created successfully")
    
    # Test 3: Process signal through engine
    print("\n[Test 3] Processing BUY signal...")
    result = engine.process_signal("NIFTY24DECFUT", intent, context)
    
    assert result is not None, "Result should not be None"
    assert result.status == "FILLED", f"Status should be FILLED, got {result.status}"
    assert result.side == "BUY", f"Side should be BUY, got {result.side}"
    assert result.price == 19500.0, f"Price should be 19500.0, got {result.price}"
    print(f"✓ Order executed: {result.order_id}")
    print(f"  Symbol: {result.symbol}, Side: {result.side}, Qty: {result.qty}, Price: {result.price}")
    
    # Verify state was updated
    assert state_store.save_checkpoint.called, "State should be saved"
    print("✓ State store updated")
    
    # Verify order was logged
    assert trade_recorder.log_order.called, "Order should be logged"
    print("✓ Order logged to trade recorder")
    
    # Test 4: Process SELL signal
    print("\n[Test 4] Processing SELL signal...")
    state_store.save_checkpoint.reset_mock()
    trade_recorder.log_order.reset_mock()
    
    intent, context = convert_to_order_intent(
        symbol="NIFTY24DECFUT",
        signal="SELL",
        qty=1,
        price=19600.0,
        strategy_code="EMA_20_50",
        logical_symbol="NIFTY",
        product="MIS",
        mode="paper",
        timeframe="5m",
    )
    
    result = engine.process_signal("NIFTY24DECFUT", intent, context)
    assert result.status == "FILLED", "SELL should be FILLED"
    assert result.side == "SELL", "Side should be SELL"
    print(f"✓ SELL order executed: {result.order_id}")
    
    # Test 5: Process HOLD signal
    print("\n[Test 5] Processing HOLD signal...")
    state_store.save_checkpoint.reset_mock()
    
    intent, context = convert_to_order_intent(
        symbol="NIFTY24DECFUT",
        signal="HOLD",
        qty=1,
        price=19500.0,
        strategy_code="EMA_20_50",
        logical_symbol="NIFTY",
    )
    
    result = engine.process_signal("NIFTY24DECFUT", intent, context)
    assert result is None, "HOLD should return None"
    assert not state_store.save_checkpoint.called, "State should not be saved for HOLD"
    print("✓ HOLD signal ignored correctly")
    
    # Test 6: Missing LTP rejection
    print("\n[Test 6] Testing missing LTP rejection...")
    broker_feed.get_ltp = Mock(return_value=None)
    
    intent, context = convert_to_order_intent(
        symbol="NIFTY24DECFUT",
        signal="BUY",
        qty=1,
        price=19500.0,
        strategy_code="EMA_20_50",
        logical_symbol="NIFTY",
    )
    
    result = engine.process_signal("NIFTY24DECFUT", intent, context)
    assert result.status == "REJECTED", "Should be REJECTED when LTP is missing"
    assert result.reason == "ltp_missing", "Reason should be ltp_missing"
    print("✓ Missing LTP handled correctly (REJECTED)")
    
    # Test 7: Position update
    print("\n[Test 7] Testing position update with unrealized PnL...")
    state_store.load_checkpoint = Mock(return_value={
        "positions": {
            "NIFTY24DECFUT": {
                "quantity": 1,
                "avg_price": 19500.0,
                "realized_pnl": 0.0,
                "unrealized_pnl": 0.0
            }
        }
    })
    state_store.save_checkpoint.reset_mock()
    
    tick_prices = {"NIFTY24DECFUT": 19600.0}
    engine.update_positions(tick_prices)
    
    assert state_store.save_checkpoint.called, "State should be saved after position update"
    saved_state = state_store.save_checkpoint.call_args[0][0]
    position = saved_state["positions"]["NIFTY24DECFUT"]
    assert position["unrealized_pnl"] == 100.0, f"Unrealized PnL should be 100.0, got {position['unrealized_pnl']}"
    print(f"✓ Position updated: unrealized PnL = {position['unrealized_pnl']}")
    
    # Summary
    print("\n" + "=" * 60)
    print("✓ All integration tests PASSED!")
    print("=" * 60)
    print("\nExecutionEngineV3 Step 1 is ready for use:")
    print("- Simple market fills at LTP")
    print("- Basic position tracking")
    print("- State and journal updates")
    print("- Toggleable via execution.engine: v3")
    print("=" * 60)


if __name__ == "__main__":
    try:
        test_integration()
    except Exception as e:
        logger.error(f"Integration test failed: {e}", exc_info=True)
        sys.exit(1)
