"""
Integration tests for RegimeEngine with Strategy Orchestrator, PortfolioEngine, and TradeGuardian
"""

from unittest.mock import Mock, MagicMock
import pytest

from core.regime_engine import RegimeEngine, RegimeSnapshot
from core.strategy_engine_v2 import StrategyEngineV2, BaseStrategy, StrategyState
from core.portfolio_engine import PortfolioEngine, PortfolioConfig
from core.trade_guardian import TradeGuardian


class TestRegimeEngineIntegrationWithStrategyEngine:
    """Test RegimeEngine integration with StrategyEngineV2."""
    
    def test_strategy_engine_with_regime_engine(self):
        """Test that StrategyEngineV2 uses RegimeEngine data."""
        config = {
            "history_lookback": 200,
            "strategies": []
        }
        
        # Mock MDE
        mde = Mock()
        mde.get_window = Mock(return_value=[
            {"open": 100, "high": 101, "low": 99, "close": 100, "volume": 1000}
            for _ in range(100)
        ])
        
        # Mock RegimeEngine
        regime_engine = Mock()
        mock_snapshot = RegimeSnapshot(
            trend="up",
            volatility="high",
            structure="breakout",
            velocity=0.5,
            atr=2.0,
            slope=0.3,
            timestamp=Mock()
        )
        regime_engine.snapshot = Mock(return_value=mock_snapshot)
        
        # Create StrategyEngineV2 with RegimeEngine
        engine = StrategyEngineV2(
            config=config,
            market_data_engine=mde,
            regime_engine=regime_engine
        )
        
        # Mock strategy
        mock_strategy = Mock(spec=BaseStrategy)
        mock_strategy.generate_signal = Mock(return_value=None)
        mock_strategy.get_pending_intents = Mock(return_value=[])
        
        engine.register_strategy("test_strategy", mock_strategy)
        
        # Run strategy
        intents = engine.run_strategy("test_strategy", "NIFTY", "5m")
        
        # Verify regime engine was called
        regime_engine.snapshot.assert_called_once_with("NIFTY")
        
        # Verify strategy received regime data in indicators
        call_args = mock_strategy.generate_signal.call_args
        indicators = call_args[0][2]  # Third argument is indicators dict
        
        assert "regime_trend" in indicators
        assert indicators["regime_trend"] == "up"
        assert "regime_volatility" in indicators
        assert indicators["regime_volatility"] == "high"
        assert "regime_structure" in indicators
        assert indicators["regime_structure"] == "breakout"
    
    def test_strategy_engine_without_regime_engine(self):
        """Test that StrategyEngineV2 works without RegimeEngine."""
        config = {
            "history_lookback": 200,
            "strategies": []
        }
        
        # Mock MDE
        mde = Mock()
        mde.get_window = Mock(return_value=[
            {"open": 100, "high": 101, "low": 99, "close": 100, "volume": 1000}
            for _ in range(100)
        ])
        
        # Create StrategyEngineV2 WITHOUT RegimeEngine
        engine = StrategyEngineV2(
            config=config,
            market_data_engine=mde,
            regime_engine=None
        )
        
        # Mock strategy
        mock_strategy = Mock(spec=BaseStrategy)
        mock_strategy.generate_signal = Mock(return_value=None)
        mock_strategy.get_pending_intents = Mock(return_value=[])
        
        engine.register_strategy("test_strategy", mock_strategy)
        
        # Run strategy - should work fine without regime engine
        intents = engine.run_strategy("test_strategy", "NIFTY", "5m")
        
        # Verify strategy received indicators but no regime data
        call_args = mock_strategy.generate_signal.call_args
        indicators = call_args[0][2]
        
        assert "regime_trend" not in indicators
        assert "regime_volatility" not in indicators
    
    def test_strategy_engine_regime_error_handling(self):
        """Test that strategy engine handles regime engine errors gracefully."""
        config = {
            "history_lookback": 200,
            "strategies": []
        }
        
        # Mock MDE
        mde = Mock()
        mde.get_window = Mock(return_value=[
            {"open": 100, "high": 101, "low": 99, "close": 100, "volume": 1000}
            for _ in range(100)
        ])
        
        # Mock RegimeEngine that throws error
        regime_engine = Mock()
        regime_engine.snapshot = Mock(side_effect=Exception("Regime error"))
        
        # Create StrategyEngineV2 with failing RegimeEngine
        engine = StrategyEngineV2(
            config=config,
            market_data_engine=mde,
            regime_engine=regime_engine
        )
        
        # Mock strategy
        mock_strategy = Mock(spec=BaseStrategy)
        mock_strategy.generate_signal = Mock(return_value=None)
        mock_strategy.get_pending_intents = Mock(return_value=[])
        
        engine.register_strategy("test_strategy", mock_strategy)
        
        # Run strategy - should not crash
        intents = engine.run_strategy("test_strategy", "NIFTY", "5m")
        
        # Should have called strategy even though regime failed
        assert mock_strategy.generate_signal.called


class TestRegimeEngineIntegrationWithPortfolioEngine:
    """Test RegimeEngine integration with PortfolioEngine."""
    
    def test_portfolio_high_volatility_reduction(self):
        """Test that high volatility reduces position size."""
        config_dict = {
            "position_sizing_mode": "fixed_qty",
            "default_fixed_qty": 10
        }
        
        portfolio_config = PortfolioConfig.from_dict(config_dict)
        state_store = Mock()
        state_store.load_checkpoint = Mock(return_value={
            "equity": {"paper_capital": 100000, "realized_pnl": 0, "unrealized_pnl": 0}
        })
        
        # Mock RegimeEngine with high volatility
        regime_engine = Mock()
        high_vol_snapshot = RegimeSnapshot(
            trend="up",
            volatility="high",
            structure="none",
            velocity=0.5,
            atr=5.0,
            slope=0.3,
            timestamp=Mock()
        )
        regime_engine.snapshot = Mock(return_value=high_vol_snapshot)
        
        # Create PortfolioEngine with RegimeEngine
        engine = PortfolioEngine(
            portfolio_config=portfolio_config,
            state_store=state_store,
            regime_engine=regime_engine
        )
        
        # Mock intent
        intent = Mock()
        intent.symbol = "NIFTY"
        intent.strategy_code = "test_strategy"
        intent.qty = None
        
        # Compute position size
        qty = engine.compute_position_size(intent, last_price=100.0)
        
        # Should be reduced from 10 due to high volatility
        # Adjustment: 10 * 0.6 = 6
        assert qty == 6
        assert regime_engine.snapshot.called
    
    def test_portfolio_low_volatility_increase(self):
        """Test that low volatility increases position size."""
        config_dict = {
            "position_sizing_mode": "fixed_qty",
            "default_fixed_qty": 10
        }
        
        portfolio_config = PortfolioConfig.from_dict(config_dict)
        state_store = Mock()
        state_store.load_checkpoint = Mock(return_value={
            "equity": {"paper_capital": 100000, "realized_pnl": 0, "unrealized_pnl": 0}
        })
        
        # Mock RegimeEngine with low volatility
        regime_engine = Mock()
        low_vol_snapshot = RegimeSnapshot(
            trend="up",
            volatility="low",
            structure="none",
            velocity=0.2,
            atr=0.5,
            slope=0.1,
            timestamp=Mock()
        )
        regime_engine.snapshot = Mock(return_value=low_vol_snapshot)
        
        # Create PortfolioEngine with RegimeEngine
        engine = PortfolioEngine(
            portfolio_config=portfolio_config,
            state_store=state_store,
            regime_engine=regime_engine
        )
        
        # Mock intent
        intent = Mock()
        intent.symbol = "NIFTY"
        intent.strategy_code = "test_strategy"
        intent.qty = None
        
        # Compute position size
        qty = engine.compute_position_size(intent, last_price=100.0)
        
        # Should be increased from 10 due to low volatility
        # Adjustment: 10 * 1.15 = 11.5 -> 11
        assert qty == 11
    
    def test_portfolio_breakout_structure_boost(self):
        """Test that breakout structure boosts position size."""
        config_dict = {
            "position_sizing_mode": "fixed_qty",
            "default_fixed_qty": 10
        }
        
        portfolio_config = PortfolioConfig.from_dict(config_dict)
        state_store = Mock()
        state_store.load_checkpoint = Mock(return_value={
            "equity": {"paper_capital": 100000, "realized_pnl": 0, "unrealized_pnl": 0}
        })
        
        # Mock RegimeEngine with breakout structure
        regime_engine = Mock()
        breakout_snapshot = RegimeSnapshot(
            trend="up",
            volatility="medium",
            structure="breakout",
            velocity=0.5,
            atr=2.0,
            slope=0.3,
            timestamp=Mock()
        )
        regime_engine.snapshot = Mock(return_value=breakout_snapshot)
        
        # Create PortfolioEngine with RegimeEngine
        engine = PortfolioEngine(
            portfolio_config=portfolio_config,
            state_store=state_store,
            regime_engine=regime_engine
        )
        
        # Mock intent
        intent = Mock()
        intent.symbol = "NIFTY"
        intent.strategy_code = "test_strategy"
        intent.qty = None
        
        # Compute position size
        qty = engine.compute_position_size(intent, last_price=100.0)
        
        # Should be increased from 10 due to breakout
        # Adjustment: 10 * 1.1 = 11
        assert qty == 11
    
    def test_portfolio_without_regime_engine(self):
        """Test that PortfolioEngine works without RegimeEngine."""
        config_dict = {
            "position_sizing_mode": "fixed_qty",
            "default_fixed_qty": 10
        }
        
        portfolio_config = PortfolioConfig.from_dict(config_dict)
        state_store = Mock()
        state_store.load_checkpoint = Mock(return_value={
            "equity": {"paper_capital": 100000, "realized_pnl": 0, "unrealized_pnl": 0}
        })
        
        # Create PortfolioEngine WITHOUT RegimeEngine
        engine = PortfolioEngine(
            portfolio_config=portfolio_config,
            state_store=state_store,
            regime_engine=None
        )
        
        # Mock intent
        intent = Mock()
        intent.symbol = "NIFTY"
        intent.strategy_code = "test_strategy"
        intent.qty = None
        
        # Compute position size
        qty = engine.compute_position_size(intent, last_price=100.0)
        
        # Should use base qty without adjustments
        assert qty == 10


class TestRegimeEngineIntegrationWithGuardian:
    """Test RegimeEngine integration with TradeGuardian."""
    
    def test_guardian_with_regime_engine(self):
        """Test that TradeGuardian works with RegimeEngine."""
        config = {
            "guardian": {
                "enabled": True,
                "max_order_per_second": 5,
                "max_lot_size": 50
            }
        }
        
        state_store = Mock()
        state_store.load_checkpoint = Mock(return_value={})
        
        # Mock RegimeEngine
        regime_engine = Mock()
        high_vol_snapshot = RegimeSnapshot(
            trend="up",
            volatility="high",
            structure="none",
            velocity=0.5,
            atr=5.0,
            slope=0.3,
            timestamp=Mock()
        )
        regime_engine.snapshot = Mock(return_value=high_vol_snapshot)
        
        # Create TradeGuardian with RegimeEngine
        import logging
        guardian = TradeGuardian(
            config=config,
            state_store=state_store,
            logger_instance=logging.getLogger(),
            regime_engine=regime_engine
        )
        
        # Mock intent
        intent = Mock()
        intent.symbol = "NIFTY"
        intent.qty = 10
        intent.price = 100.0
        
        # Validate trade
        decision = guardian.validate_pre_trade(intent)
        
        # Should allow but with regime awareness
        assert decision.allow is True
        # Regime engine should have been called
        assert regime_engine.snapshot.called
    
    def test_guardian_without_regime_engine(self):
        """Test that TradeGuardian works without RegimeEngine."""
        config = {
            "guardian": {
                "enabled": True,
                "max_order_per_second": 5,
                "max_lot_size": 50
            }
        }
        
        state_store = Mock()
        state_store.load_checkpoint = Mock(return_value={})
        
        # Create TradeGuardian WITHOUT RegimeEngine
        import logging
        guardian = TradeGuardian(
            config=config,
            state_store=state_store,
            logger_instance=logging.getLogger(),
            regime_engine=None
        )
        
        # Mock intent
        intent = Mock()
        intent.symbol = "NIFTY"
        intent.qty = 10
        intent.price = 100.0
        
        # Validate trade - should work without regime engine
        decision = guardian.validate_pre_trade(intent)
        
        # Should allow
        assert decision.allow is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
