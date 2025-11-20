"""
Basic tests for ExecutionEngineV3 Step 1 implementation.

Tests the minimal functionality:
- Signal processing (BUY/SELL/HOLD)
- Market fills at LTP
- State store updates
- Trade recorder logging
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock, patch
from execution.engine_v3 import ExecutionEngineV3, ExecutionContext, ExecutionResult


class TestExecutionEngineV3Basic:
    """Test basic ExecutionEngineV3 functionality."""
    
    def setup_method(self):
        """Setup test fixtures."""
        # Mock config
        self.cfg = {
            "default_quantity": 1,
            "slippage_bps": 5,
        }
        
        # Mock state_store
        self.state_store = Mock()
        self.state_store.load_checkpoint = Mock(return_value={})
        self.state_store.save_checkpoint = Mock()
        
        # Mock trade_recorder
        self.trade_recorder = Mock()
        self.trade_recorder.log_order = Mock()
        self.trade_recorder.record_order = Mock()
        
        # Mock broker_feed
        self.broker_feed = Mock()
        self.broker_feed.get_ltp = Mock(return_value=19500.0)
        
        # Create engine instance
        self.engine = ExecutionEngineV3(
            cfg=self.cfg,
            state_store=self.state_store,
            trade_recorder=self.trade_recorder,
            broker_feed=self.broker_feed
        )
    
    def test_engine_initialization(self):
        """Test that engine initializes correctly."""
        assert self.engine is not None
        assert self.engine.default_quantity == 1
        assert self.engine._order_sequence == 0
    
    def test_process_buy_signal(self):
        """Test processing a BUY signal."""
        # Create signal object
        signal = Mock()
        signal.signal = "BUY"
        
        # Create context
        context = ExecutionContext(
            symbol="NIFTY24DECFUT",
            logical_symbol="NIFTY",
            product="MIS",
            strategy_id="EMA_20_50",
            mode="paper",
            timestamp=datetime.now(timezone.utc),
            timeframe="5m",
            exchange="NFO",
            fixed_qty=1
        )
        
        # Process signal
        result = self.engine.process_signal("NIFTY24DECFUT", signal, context)
        
        # Verify result
        assert result is not None
        assert result.status == "FILLED"
        assert result.symbol == "NIFTY24DECFUT"
        assert result.side == "BUY"
        assert result.qty == 1
        assert result.price == 19500.0
        
        # Verify state was updated
        assert self.state_store.save_checkpoint.called
        
        # Verify order was logged
        assert self.trade_recorder.log_order.called or self.trade_recorder.record_order.called
    
    def test_process_sell_signal(self):
        """Test processing a SELL signal."""
        signal = Mock()
        signal.signal = "SELL"
        
        context = ExecutionContext(
            symbol="NIFTY24DECFUT",
            logical_symbol="NIFTY",
            product="MIS",
            strategy_id="EMA_20_50",
            mode="paper",
            timestamp=datetime.now(timezone.utc),
            timeframe="5m",
            exchange="NFO",
            fixed_qty=1
        )
        
        result = self.engine.process_signal("NIFTY24DECFUT", signal, context)
        
        assert result is not None
        assert result.status == "FILLED"
        assert result.side == "SELL"
    
    def test_process_hold_signal(self):
        """Test that HOLD signals are ignored."""
        signal = Mock()
        signal.signal = "HOLD"
        
        context = ExecutionContext(
            symbol="NIFTY24DECFUT",
            logical_symbol="NIFTY",
            product="MIS",
            strategy_id="EMA_20_50",
            mode="paper",
            timestamp=datetime.now(timezone.utc),
            timeframe="5m",
        )
        
        result = self.engine.process_signal("NIFTY24DECFUT", signal, context)
        
        # HOLD should return None
        assert result is None
        
        # State and order logging should not be called
        assert not self.state_store.save_checkpoint.called
    
    def test_missing_ltp_rejection(self):
        """Test that orders are rejected when LTP is missing."""
        # Set up broker_feed to return None
        self.broker_feed.get_ltp = Mock(return_value=None)
        
        signal = Mock()
        signal.signal = "BUY"
        
        context = ExecutionContext(
            symbol="NIFTY24DECFUT",
            logical_symbol="NIFTY",
            product="MIS",
            strategy_id="EMA_20_50",
            mode="paper",
            timestamp=datetime.now(timezone.utc),
            timeframe="5m",
        )
        
        result = self.engine.process_signal("NIFTY24DECFUT", signal, context)
        
        assert result is not None
        assert result.status == "REJECTED"
        assert result.reason == "ltp_missing"
        assert result.price == 0.0
    
    def test_state_store_position_update(self):
        """Test that state store is updated correctly."""
        # Set up initial empty state
        self.state_store.load_checkpoint = Mock(return_value={"positions": {}})
        
        signal = Mock()
        signal.signal = "BUY"
        
        context = ExecutionContext(
            symbol="NIFTY24DECFUT",
            logical_symbol="NIFTY",
            product="MIS",
            strategy_id="EMA_20_50",
            mode="paper",
            timestamp=datetime.now(timezone.utc),
            timeframe="5m",
            fixed_qty=2
        )
        
        self.engine.process_signal("NIFTY24DECFUT", signal, context)
        
        # Verify save_checkpoint was called
        assert self.state_store.save_checkpoint.called
        
        # Get the saved state
        saved_state = self.state_store.save_checkpoint.call_args[0][0]
        
        # Verify position exists
        assert "positions" in saved_state
        assert "NIFTY24DECFUT" in saved_state["positions"]
        
        # Verify position details
        position = saved_state["positions"]["NIFTY24DECFUT"]
        assert position["quantity"] == 2
        assert position["avg_price"] == 19500.0
    
    def test_update_positions_unrealized_pnl(self):
        """Test that update_positions calculates unrealized PnL correctly."""
        # Set up state with an existing position
        self.state_store.load_checkpoint = Mock(return_value={
            "positions": {
                "NIFTY24DECFUT": {
                    "quantity": 1,
                    "avg_price": 19500.0,
                    "realized_pnl": 0.0,
                    "unrealized_pnl": 0.0
                }
            }
        })
        
        # Update with new price (higher than entry)
        tick_prices = {"NIFTY24DECFUT": 19600.0}
        self.engine.update_positions(tick_prices)
        
        # Verify save was called
        assert self.state_store.save_checkpoint.called
        
        # Get the saved state
        saved_state = self.state_store.save_checkpoint.call_args[0][0]
        
        # Verify unrealized PnL was calculated
        position = saved_state["positions"]["NIFTY24DECFUT"]
        assert position["unrealized_pnl"] == 100.0  # (19600 - 19500) * 1
    
    def test_order_id_generation(self):
        """Test that order IDs are unique and sequential."""
        signal = Mock()
        signal.signal = "BUY"
        
        context = ExecutionContext(
            symbol="NIFTY24DECFUT",
            logical_symbol="NIFTY",
            product="MIS",
            strategy_id="EMA_20_50",
            mode="paper",
            timestamp=datetime.now(timezone.utc),
            timeframe="5m",
        )
        
        # Execute multiple orders
        result1 = self.engine.process_signal("NIFTY24DECFUT", signal, context)
        result2 = self.engine.process_signal("NIFTY24DECFUT", signal, context)
        
        # Verify order IDs are different
        assert result1.order_id != result2.order_id
        
        # Verify order IDs contain V3 prefix
        assert "V3-" in result1.order_id
        assert "V3-" in result2.order_id


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
