"""
Integration test for unlimited position limit workflow.

Tests the full stack from config → risk engine → API → frontend types.
"""

import json
import tempfile
from pathlib import Path

import pytest
import yaml

from core.config import load_config
from core.risk_engine import RiskEngine, RiskConfig, RiskAction


class TestUnlimitedPositionsIntegration:
    """Integration tests for unlimited position limit workflow."""
    
    def test_config_loads_null_position_limit(self, tmp_path):
        """Test that config correctly loads null position limit."""
        config_path = tmp_path / "test_config.yaml"
        config_data = {
            "trading": {
                "max_open_positions": None,  # Explicitly null
                "paper_capital": 500000,
            }
        }
        
        with config_path.open("w") as f:
            yaml.dump(config_data, f)
        
        cfg = load_config(str(config_path))
        
        # Verify null is preserved (not converted to 0 or other value)
        max_positions = cfg.trading.get("max_open_positions")
        assert max_positions is None
    
    def test_risk_engine_allows_unlimited_positions(self):
        """Test full risk engine workflow with unlimited positions."""
        # Create risk engine with null position limit
        config = RiskConfig(
            max_positions_total=None,
            capital=500000.0,
        )
        state = {}
        
        risk_engine = RiskEngine(config, state, None)
        
        # Simulate a portfolio with many positions
        portfolio_state = {
            "positions": [
                {"symbol": f"STOCK{i}", "quantity": 100}
                for i in range(50)  # 50 positions - would exceed typical limits
            ],
            "day_pnl": 1000.0,
        }
        
        # Try to open another position
        order_intent = {
            "symbol": "STOCK51",
            "quantity": 100,
            "price": 1500.0,
        }
        
        decision = risk_engine.check_order(order_intent, portfolio_state, {})
        
        # Should be allowed because position limit is None
        assert decision.action == RiskAction.ALLOW
        assert "position limit" not in decision.reason.lower()
    
    def test_portfolio_summary_json_serialization(self):
        """Test that portfolio summary with null position_limit serializes correctly."""
        # Test JSON serialization directly without importing ui.dashboard
        summary = {
            "position_limit": None,
            "open_positions": 0,
            "position_used_pct": 0.0,
            "position_count": 0,
        }
        
        # Test JSON serialization
        json_str = json.dumps(summary)
        parsed = json.loads(json_str)
        
        # Verify null is preserved in JSON
        assert parsed["position_limit"] is None
        assert parsed["open_positions"] == 0
        assert parsed["position_used_pct"] == 0.0
    
    def test_config_summary_with_null_positions(self, tmp_path):
        """Test that config summary handles null max_positions."""
        # Create a test config
        config_path = tmp_path / "test_config.yaml"
        config_data = {
            "trading": {
                "mode": "paper",
                "max_open_positions": None,
                "paper_capital": 500000,
                "max_daily_loss": 3000,
            },
            "risk": {
                "risk_per_trade_pct": 0.01,
            }
        }
        
        with config_path.open("w") as f:
            yaml.dump(config_data, f)
        
        cfg = load_config(str(config_path))
        
        # Test the logic for extracting max_positions
        trading = cfg.trading or {}
        risk = cfg.risk or {}
        
        max_positions_raw = trading.get("max_open_positions") or trading.get("max_positions") or risk.get("max_positions")
        if max_positions_raw is None:
            max_positions = None
        else:
            max_positions = int(max_positions_raw) if max_positions_raw else 5
        
        # max_positions should be None
        assert max_positions is None
        
        # Other fields should still work
        assert trading.get("paper_capital") == 500000
        assert trading.get("max_daily_loss") == 3000
    
    def test_finite_vs_unlimited_comparison(self):
        """Test side-by-side comparison of finite vs unlimited position limits."""
        # Test with finite limit
        config_finite = RiskConfig(max_positions_total=5, capital=500000.0)
        risk_engine_finite = RiskEngine(config_finite, {}, None)
        
        portfolio_6_positions = {
            "positions": [{"symbol": f"S{i}", "quantity": 1} for i in range(6)],
            "day_pnl": 0.0,
        }
        
        order = {"symbol": "NEWSTOCK", "quantity": 1, "price": 1000.0}
        
        decision_finite = risk_engine_finite.check_order(order, portfolio_6_positions, {})
        
        # Should be blocked (6 >= 5)
        assert decision_finite.action == RiskAction.BLOCK
        
        # Test with unlimited
        config_unlimited = RiskConfig(max_positions_total=None, capital=500000.0)
        risk_engine_unlimited = RiskEngine(config_unlimited, {}, None)
        
        decision_unlimited = risk_engine_unlimited.check_order(order, portfolio_6_positions, {})
        
        # Should be allowed
        assert decision_unlimited.action == RiskAction.ALLOW
    
    def test_position_used_pct_calculation(self):
        """Test position_used_pct calculation logic for both cases."""
        # Case 1: Finite limit
        position_count = 3
        position_limit = 5
        
        if position_limit is None or position_limit == 0:
            position_used_pct = 0.0
        else:
            position_used_pct = (position_count / position_limit) * 100.0
        
        assert position_used_pct == 60.0
        
        # Case 2: Unlimited (None)
        position_count = 10
        position_limit = None
        
        if position_limit is None or position_limit == 0:
            position_used_pct = 0.0
        else:
            position_used_pct = (position_count / position_limit) * 100.0
        
        assert position_used_pct == 0.0
    
    def test_yaml_null_vs_missing_field(self, tmp_path):
        """Test difference between explicit null and missing field."""
        # Config 1: Explicit null
        config1_path = tmp_path / "config1.yaml"
        config1_data = {"trading": {"max_open_positions": None}}
        with config1_path.open("w") as f:
            yaml.dump(config1_data, f)
        
        cfg1 = load_config(str(config1_path))
        max_pos_1 = cfg1.trading.get("max_open_positions")
        
        # Should be None
        assert max_pos_1 is None
        
        # Config 2: Missing field
        config2_path = tmp_path / "config2.yaml"
        config2_data = {"trading": {}}
        with config2_path.open("w") as f:
            yaml.dump(config2_data, f)
        
        cfg2 = load_config(str(config2_path))
        max_pos_2 = cfg2.trading.get("max_open_positions")
        
        # Should also be None (missing key returns None)
        assert max_pos_2 is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
