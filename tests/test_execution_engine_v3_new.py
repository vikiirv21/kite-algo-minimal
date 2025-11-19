"""
Test ExecutionEngine V3 functionality.
"""

import pytest
from datetime import datetime, timezone
from execution.engine_v3 import (
    ExecutionEngineV3,
    OrderBuilder,
    FillEngine,
    StopLossManager,
    TakeProfitManager,
    TrailingStopManager,
    TimeStopManager,
    TradeLifecycleManager,
    OrderState,
    Order,
)


@pytest.fixture
def config():
    """Test configuration."""
    return {
        "execution": {
            "engine": "v3",
            "fill_mode": "mid",
            "slippage_bps": 5,
            "enable_partial_exit": True,
            "partial_exit_pct": 0.5,
            "enable_trailing": True,
            "trail_step_r": 0.5,
            "enable_time_stop": True,
            "time_stop_bars": 20,
        }
    }


@pytest.fixture
def order_builder(config):
    """Create OrderBuilder instance."""
    return OrderBuilder(config)


@pytest.fixture
def fill_engine(config):
    """Create FillEngine instance."""
    return FillEngine(config)


@pytest.fixture
def sl_manager(config):
    """Create StopLossManager instance."""
    return StopLossManager(config)


@pytest.fixture
def tp_manager(config):
    """Create TakeProfitManager instance."""
    return TakeProfitManager(config)


@pytest.fixture
def trailing_manager(config):
    """Create TrailingStopManager instance."""
    return TrailingStopManager(config)


@pytest.fixture
def time_stop_manager(config):
    """Create TimeStopManager instance."""
    return TimeStopManager(config)


@pytest.fixture
def lifecycle_manager(config):
    """Create TradeLifecycleManager instance."""
    return TradeLifecycleManager(config)


class TestOrderBuilder:
    """Test OrderBuilder functionality."""
    
    def test_build_basic_order(self, order_builder):
        """Test building a basic order."""
        order = order_builder.build_order(
            symbol="NIFTY25JAN26000CE",
            qty=50,
            side="BUY",
            strategy_id="test_strategy"
        )
        
        assert order.symbol == "NIFTY25JAN26000CE"
        assert order.qty == 50
        assert order.side == "BUY"
        assert order.strategy_id == "test_strategy"
        assert order.state == OrderState.CREATED
        assert order.order_id.startswith("V3-")
    
    def test_build_order_with_sl_tp(self, order_builder):
        """Test building an order with SL/TP."""
        order = order_builder.build_order(
            symbol="NIFTY25JAN26000CE",
            qty=50,
            side="BUY",
            sl_price=100.0,
            tp_price=150.0,
            strategy_id="test_strategy"
        )
        
        assert order.sl_price == 100.0
        assert order.tp_price == 150.0
    
    def test_build_order_with_time_stop(self, order_builder):
        """Test building an order with time stop."""
        order = order_builder.build_order(
            symbol="NIFTY25JAN26000CE",
            qty=50,
            side="BUY",
            time_stop_bars=10,
            strategy_id="test_strategy"
        )
        
        assert order.time_stop_bars == 10


class TestFillEngine:
    """Test FillEngine functionality."""
    
    def test_determine_fill_price_ltp_mode(self, fill_engine, order_builder):
        """Test fill price determination in LTP mode."""
        order = order_builder.build_order(
            symbol="NIFTY25JAN26000CE",
            qty=50,
            side="BUY",
            strategy_id="test_strategy"
        )
        
        ltp = 100.0
        fill_price = fill_engine.determine_fill_price(order, ltp)
        
        # Should have slippage applied (5 bps = 0.05%)
        expected = ltp * 1.0005
        assert abs(fill_price - expected) < 0.01
    
    def test_determine_fill_price_mid_mode(self, config, order_builder):
        """Test fill price determination in mid mode."""
        config["execution"]["fill_mode"] = "mid"
        fill_engine = FillEngine(config)
        
        order = order_builder.build_order(
            symbol="NIFTY25JAN26000CE",
            qty=50,
            side="BUY",
            strategy_id="test_strategy"
        )
        
        ltp = 100.0
        bid = 99.5
        ask = 100.5
        fill_price = fill_engine.determine_fill_price(order, ltp, bid, ask)
        
        # Should use mid price: (99.5 + 100.5) / 2 = 100.0
        # Plus slippage for BUY: 100.0 * 1.0005 = 100.05
        expected = 100.0 * 1.0005
        assert abs(fill_price - expected) < 0.01
    
    def test_fill_order(self, fill_engine, order_builder):
        """Test filling an order."""
        order = order_builder.build_order(
            symbol="NIFTY25JAN26000CE",
            qty=50,
            side="BUY",
            strategy_id="test_strategy"
        )
        
        ltp = 100.0
        filled_order = fill_engine.fill_order(order, ltp)
        
        assert filled_order.state == OrderState.FILLED
        assert filled_order.fill_price is not None
        assert filled_order.entry_price == filled_order.fill_price
        assert filled_order.fill_timestamp is not None


class TestStopLossManager:
    """Test StopLossManager functionality."""
    
    def test_check_stop_loss_not_breached(self, sl_manager, order_builder):
        """Test SL check when not breached."""
        order = order_builder.build_order(
            symbol="NIFTY25JAN26000CE",
            qty=50,
            side="BUY",
            sl_price=95.0,
            strategy_id="test_strategy"
        )
        order.entry_price = 100.0
        
        breached, action = sl_manager.check_stop_loss(order, 98.0)
        assert not breached
        assert action is None
    
    def test_check_stop_loss_breached_long(self, sl_manager, order_builder):
        """Test SL breach for long position."""
        order = order_builder.build_order(
            symbol="NIFTY25JAN26000CE",
            qty=50,
            side="BUY",
            sl_price=95.0,
            strategy_id="test_strategy"
        )
        order.entry_price = 100.0
        order.state = OrderState.ACTIVE
        
        breached, action = sl_manager.check_stop_loss(order, 94.0)
        assert breached
        assert action == "partial"  # First time breached, partial exit
    
    def test_check_stop_loss_breached_short(self, sl_manager, order_builder):
        """Test SL breach for short position."""
        order = order_builder.build_order(
            symbol="NIFTY25JAN26000CE",
            qty=50,
            side="SELL",
            sl_price=105.0,
            strategy_id="test_strategy"
        )
        order.entry_price = 100.0
        order.state = OrderState.ACTIVE
        
        breached, action = sl_manager.check_stop_loss(order, 106.0)
        assert breached
        assert action == "partial"
    
    def test_execute_partial_stop_loss(self, sl_manager, order_builder):
        """Test partial SL execution."""
        order = order_builder.build_order(
            symbol="NIFTY25JAN26000CE",
            qty=50,
            side="BUY",
            sl_price=95.0,
            strategy_id="test_strategy"
        )
        order.entry_price = 100.0
        order.state = OrderState.ACTIVE
        
        updated_order = sl_manager.execute_stop_loss(order, 94.0, "partial")
        
        assert updated_order.partial_exit_executed
        assert updated_order.qty == 25  # 50% of 50 = 25 remaining
        assert updated_order.state == OrderState.ACTIVE
        assert updated_order.realized_pnl < 0  # Loss on exited portion
    
    def test_execute_full_stop_loss(self, sl_manager, order_builder):
        """Test full SL execution."""
        order = order_builder.build_order(
            symbol="NIFTY25JAN26000CE",
            qty=50,
            side="BUY",
            sl_price=95.0,
            strategy_id="test_strategy"
        )
        order.entry_price = 100.0
        order.state = OrderState.ACTIVE
        
        updated_order = sl_manager.execute_stop_loss(order, 94.0, "full")
        
        assert updated_order.state == OrderState.CLOSED
        assert updated_order.realized_pnl < 0  # Loss


class TestTakeProfitManager:
    """Test TakeProfitManager functionality."""
    
    def test_check_take_profit_not_hit(self, tp_manager, order_builder):
        """Test TP check when not hit."""
        order = order_builder.build_order(
            symbol="NIFTY25JAN26000CE",
            qty=50,
            side="BUY",
            tp_price=110.0,
            strategy_id="test_strategy"
        )
        order.entry_price = 100.0
        
        hit = tp_manager.check_take_profit(order, 105.0)
        assert not hit
    
    def test_check_take_profit_hit_long(self, tp_manager, order_builder):
        """Test TP hit for long position."""
        order = order_builder.build_order(
            symbol="NIFTY25JAN26000CE",
            qty=50,
            side="BUY",
            tp_price=110.0,
            strategy_id="test_strategy"
        )
        order.entry_price = 100.0
        
        hit = tp_manager.check_take_profit(order, 111.0)
        assert hit
    
    def test_execute_take_profit(self, tp_manager, order_builder):
        """Test TP execution."""
        order = order_builder.build_order(
            symbol="NIFTY25JAN26000CE",
            qty=50,
            side="BUY",
            tp_price=110.0,
            strategy_id="test_strategy"
        )
        order.entry_price = 100.0
        order.state = OrderState.ACTIVE
        
        updated_order = tp_manager.execute_take_profit(order, 111.0)
        
        assert updated_order.state == OrderState.CLOSED
        assert updated_order.realized_pnl > 0  # Profit


class TestTrailingStopManager:
    """Test TrailingStopManager functionality."""
    
    def test_update_trailing_stop_long(self, trailing_manager, order_builder):
        """Test trailing stop update for long position."""
        order = order_builder.build_order(
            symbol="NIFTY25JAN26000CE",
            qty=50,
            side="BUY",
            sl_price=95.0,
            strategy_id="test_strategy"
        )
        order.entry_price = 100.0
        order.state = OrderState.ACTIVE
        order.partial_exit_executed = True  # Enable trailing
        order.trailing_sl_active = True
        
        # Price moves up
        updated_order = trailing_manager.update_trailing_stop(order, 110.0)
        
        # SL should be raised
        assert updated_order.sl_price > 95.0
        assert updated_order.highest_price == 110.0


class TestTimeStopManager:
    """Test TimeStopManager functionality."""
    
    def test_check_time_stop_not_reached(self, time_stop_manager, order_builder):
        """Test time stop when not reached."""
        order = order_builder.build_order(
            symbol="NIFTY25JAN26000CE",
            qty=50,
            side="BUY",
            time_stop_bars=20,
            strategy_id="test_strategy"
        )
        order.bars_held = 10
        
        reached = time_stop_manager.check_time_stop(order)
        assert not reached
    
    def test_check_time_stop_reached(self, time_stop_manager, order_builder):
        """Test time stop when reached."""
        order = order_builder.build_order(
            symbol="NIFTY25JAN26000CE",
            qty=50,
            side="BUY",
            time_stop_bars=20,
            strategy_id="test_strategy"
        )
        order.bars_held = 20
        
        reached = time_stop_manager.check_time_stop(order)
        assert reached
    
    def test_execute_time_stop(self, time_stop_manager, order_builder):
        """Test time stop execution."""
        order = order_builder.build_order(
            symbol="NIFTY25JAN26000CE",
            qty=50,
            side="BUY",
            strategy_id="test_strategy"
        )
        order.entry_price = 100.0
        order.state = OrderState.ACTIVE
        order.bars_held = 20
        
        updated_order = time_stop_manager.execute_time_stop(order, 102.0)
        
        assert updated_order.state == OrderState.CLOSED
        assert updated_order.realized_pnl > 0  # Small profit


class TestTradeLifecycleManager:
    """Test TradeLifecycleManager functionality."""
    
    def test_transition_state(self, lifecycle_manager, order_builder):
        """Test state transition."""
        order = order_builder.build_order(
            symbol="NIFTY25JAN26000CE",
            qty=50,
            side="BUY",
            strategy_id="test_strategy"
        )
        
        updated_order = lifecycle_manager.transition_state(
            order, OrderState.SUBMITTED, "order submitted"
        )
        
        assert updated_order.state == OrderState.SUBMITTED
        assert len(updated_order.events) > 0
    
    def test_can_transition_valid(self, lifecycle_manager, order_builder):
        """Test valid state transition check."""
        order = order_builder.build_order(
            symbol="NIFTY25JAN26000CE",
            qty=50,
            side="BUY",
            strategy_id="test_strategy"
        )
        order.state = OrderState.CREATED
        
        can_transition = lifecycle_manager.can_transition(order, OrderState.SUBMITTED)
        assert can_transition
    
    def test_can_transition_invalid(self, lifecycle_manager, order_builder):
        """Test invalid state transition check."""
        order = order_builder.build_order(
            symbol="NIFTY25JAN26000CE",
            qty=50,
            side="BUY",
            strategy_id="test_strategy"
        )
        order.state = OrderState.CREATED
        
        can_transition = lifecycle_manager.can_transition(order, OrderState.CLOSED)
        assert not can_transition


class TestExecutionEngineV3:
    """Test ExecutionEngineV3 functionality."""
    
    def test_initialization(self, config):
        """Test engine initialization."""
        engine = ExecutionEngineV3(config)
        
        assert engine.order_builder is not None
        assert engine.fill_engine is not None
        assert engine.sl_manager is not None
        assert engine.tp_manager is not None
        assert engine.trailing_manager is not None
        assert engine.time_stop_manager is not None
        assert engine.lifecycle_manager is not None
        assert len(engine.active_orders) == 0
    
    def test_get_metrics(self, config):
        """Test getting metrics."""
        engine = ExecutionEngineV3(config)
        
        metrics = engine.get_metrics()
        
        assert "total_orders" in metrics
        assert "active_positions" in metrics
        assert "realized_pnl" in metrics
        assert "unrealized_pnl" in metrics
        assert metrics["total_orders"] == 0
    
    def test_get_positions(self, config):
        """Test getting positions."""
        engine = ExecutionEngineV3(config)
        
        positions = engine.get_positions()
        
        assert isinstance(positions, list)
        assert len(positions) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
