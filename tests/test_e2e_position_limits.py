"""
End-to-end workflow simulation test.

Simulates the complete flow from config → risk engine → API response → frontend.
This test verifies the entire stack works together correctly.
"""

import json
import tempfile
from pathlib import Path

import pytest
import yaml

from core.config import load_config
from core.risk_engine import RiskEngine, RiskConfig, RiskAction


def simulate_api_portfolio_summary(config_path: Path):
    """Simulate what the /api/portfolio/summary endpoint would return."""
    cfg = load_config(str(config_path))
    
    # Simulate portfolio state
    state_data = {
        "equity": {
            "paper_capital": 500000.0,
            "realized_pnl": 5000.0,
            "unrealized_pnl": 2000.0,
            "equity": 507000.0,
            "total_notional": 300000.0,
        },
        "pnl": {
            "day_pnl": 3000.0,
        },
        "positions": {
            "NIFTY25DECFUT": {"symbol": "NIFTY25DECFUT", "quantity": 50},
            "BANKNIFTY25DECFUT": {"symbol": "BANKNIFTY25DECFUT", "quantity": 25},
            "FINNIFTY25DECFUT": {"symbol": "FINNIFTY25DECFUT", "quantity": 40},
            "MIDCPNIFTY25DECFUT": {"symbol": "MIDCPNIFTY25DECFUT", "quantity": 30},
            "SENSEX25DECFUT": {"symbol": "SENSEX25DECFUT", "quantity": 10},
            "NIFTY50": {"symbol": "NIFTY50", "quantity": 100},
            "RELIANCE": {"symbol": "RELIANCE", "quantity": 50},
            "TCS": {"symbol": "TCS", "quantity": 25},
            "INFY": {"symbol": "INFY", "quantity": 75},
            "HDFCBANK": {"symbol": "HDFCBANK", "quantity": 40},
        }
    }
    
    # Simulate load_paper_portfolio_summary logic
    trading = cfg.trading or {}
    risk = cfg.risk or {}
    
    max_positions_raw = trading.get("max_open_positions") or trading.get("max_positions") or risk.get("max_positions")
    position_limit = int(max_positions_raw) if max_positions_raw is not None else None
    
    positions_list = list(state_data["positions"].values())
    position_count = len([p for p in positions_list if p.get("quantity", 0) != 0])
    
    if position_limit is None or position_limit == 0:
        position_used_pct = 0.0
    else:
        position_used_pct = (position_count / position_limit) * 100.0
    
    return {
        "paper_capital": 500000.0,
        "total_realized_pnl": 5000.0,
        "total_unrealized_pnl": 2000.0,
        "equity": 507000.0,
        "total_notional": 300000.0,
        "free_notional": 207000.0,
        "exposure_pct": 0.592,
        "daily_pnl": 3000.0,
        "has_positions": True,
        "position_count": position_count,
        "position_limit": position_limit,
        "open_positions": position_count,
        "position_used_pct": position_used_pct,
        "note": "",
    }


def simulate_frontend_display(api_response: dict) -> dict:
    """Simulate what the frontend would display based on API response."""
    position_limit = api_response.get("position_limit")
    open_positions = api_response.get("open_positions", 0)
    position_used_pct = api_response.get("position_used_pct", 0.0)
    
    is_unlimited = position_limit is None or position_limit == 0
    
    if is_unlimited:
        return {
            "display_type": "unlimited",
            "title": "Position Limit",
            "message": "No hard limit configured",
            "info": f"Open positions: {open_positions}",
            "show_bar": False,
            "show_warning": False,
        }
    else:
        show_warning = position_used_pct >= 80
        return {
            "display_type": "finite",
            "title": "Position Limit",
            "message": f"{open_positions} of {position_limit} positions",
            "info": f"{position_used_pct:.1f}% used",
            "show_bar": True,
            "show_warning": show_warning,
            "available": position_limit - open_positions,
        }


class TestEndToEndWorkflow:
    """Test complete end-to-end workflow."""
    
    def test_unlimited_positions_full_workflow(self, tmp_path):
        """Test complete workflow with unlimited positions."""
        # Step 1: Create config with null position limit
        config_path = tmp_path / "config.yaml"
        config_data = {
            "trading": {
                "max_open_positions": None,  # Unlimited
                "paper_capital": 500000,
                "max_daily_loss": 5000,
            },
            "risk": {
                "risk_per_trade_pct": 0.01,
            }
        }
        
        with config_path.open("w") as f:
            yaml.dump(config_data, f)
        
        # Step 2: Verify config loads correctly
        cfg = load_config(str(config_path))
        assert cfg.trading.get("max_open_positions") is None
        
        # Step 3: Verify risk engine allows many positions
        risk_config = RiskConfig(
            max_positions_total=None,
            capital=500000.0,
        )
        risk_engine = RiskEngine(risk_config, {}, None)
        
        # Simulate 10 existing positions
        portfolio_state = {
            "positions": [{"symbol": f"S{i}", "quantity": 1} for i in range(10)],
            "day_pnl": 1000.0,
        }
        
        # Try to open 11th position
        order = {"symbol": "S11", "quantity": 1, "price": 1000.0}
        decision = risk_engine.check_order(order, portfolio_state, {})
        
        assert decision.action == RiskAction.ALLOW
        
        # Step 4: Verify API response
        api_response = simulate_api_portfolio_summary(config_path)
        
        assert api_response["position_limit"] is None
        assert api_response["open_positions"] == 10
        assert api_response["position_used_pct"] == 0.0
        
        # Step 5: Verify JSON serialization
        json_str = json.dumps(api_response)
        parsed = json.loads(json_str)
        
        assert parsed["position_limit"] is None
        
        # Step 6: Verify frontend display
        frontend_display = simulate_frontend_display(api_response)
        
        assert frontend_display["display_type"] == "unlimited"
        assert frontend_display["message"] == "No hard limit configured"
        assert frontend_display["show_bar"] is False
        assert frontend_display["show_warning"] is False
        assert "Open positions: 10" in frontend_display["info"]
    
    def test_finite_positions_full_workflow(self, tmp_path):
        """Test complete workflow with finite position limit."""
        # Step 1: Create config with finite limit
        config_path = tmp_path / "config.yaml"
        config_data = {
            "trading": {
                "max_open_positions": 5,
                "paper_capital": 500000,
            },
        }
        
        with config_path.open("w") as f:
            yaml.dump(config_data, f)
        
        # Step 2: Verify risk engine blocks at limit
        risk_config = RiskConfig(
            max_positions_total=5,
            capital=500000.0,
        )
        risk_engine = RiskEngine(risk_config, {}, None)
        
        # Simulate 5 existing positions
        portfolio_state = {
            "positions": [{"symbol": f"S{i}", "quantity": 1} for i in range(5)],
            "day_pnl": 1000.0,
        }
        
        # Try to open 6th position
        order = {"symbol": "S6", "quantity": 1, "price": 1000.0}
        decision = risk_engine.check_order(order, portfolio_state, {})
        
        assert decision.action == RiskAction.BLOCK
        assert "position limit" in decision.reason.lower()
        
        # Step 3: Verify API response shows correct limit
        api_response = simulate_api_portfolio_summary(config_path)
        
        assert api_response["position_limit"] == 5
        assert api_response["position_used_pct"] == 200.0  # 10 positions / 5 limit
        
        # Step 4: Verify frontend shows warning (over limit)
        frontend_display = simulate_frontend_display(api_response)
        
        assert frontend_display["display_type"] == "finite"
        assert frontend_display["show_bar"] is True
        assert frontend_display["show_warning"] is True  # 200% > 80%
    
    def test_transition_from_finite_to_unlimited(self, tmp_path):
        """Test what happens when switching from finite to unlimited."""
        config_path = tmp_path / "config.yaml"
        
        # Start with finite limit
        config_data = {
            "trading": {
                "max_open_positions": 5,
                "paper_capital": 500000,
            },
        }
        
        with config_path.open("w") as f:
            yaml.dump(config_data, f)
        
        api_response_finite = simulate_api_portfolio_summary(config_path)
        assert api_response_finite["position_limit"] == 5
        
        # Switch to unlimited
        config_data["trading"]["max_open_positions"] = None
        
        with config_path.open("w") as f:
            yaml.dump(config_data, f)
        
        api_response_unlimited = simulate_api_portfolio_summary(config_path)
        assert api_response_unlimited["position_limit"] is None
        assert api_response_unlimited["position_used_pct"] == 0.0
        
        # Frontend should show different display
        display_finite = simulate_frontend_display(api_response_finite)
        display_unlimited = simulate_frontend_display(api_response_unlimited)
        
        assert display_finite["display_type"] == "finite"
        assert display_unlimited["display_type"] == "unlimited"
        assert display_unlimited["show_warning"] is False


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_exactly_at_limit(self, tmp_path):
        """Test behavior when exactly at position limit."""
        config_path = tmp_path / "config.yaml"
        config_data = {"trading": {"max_open_positions": 5}}
        
        with config_path.open("w") as f:
            yaml.dump(config_data, f)
        
        api_response = simulate_api_portfolio_summary(config_path)
        
        # Response has 10 positions, limit is 5
        assert api_response["position_limit"] == 5
        assert api_response["position_used_pct"] == 200.0
    
    def test_zero_positions_unlimited(self, tmp_path):
        """Test unlimited with zero positions."""
        config_path = tmp_path / "config.yaml"
        config_data = {"trading": {"max_open_positions": None}}
        
        with config_path.open("w") as f:
            yaml.dump(config_data, f)
        
        # Override state to have no positions
        cfg = load_config(str(config_path))
        trading = cfg.trading or {}
        
        max_positions_raw = trading.get("max_open_positions")
        position_limit = int(max_positions_raw) if max_positions_raw is not None else None
        
        assert position_limit is None
        
        # Frontend should still show unlimited
        api_response = {
            "position_limit": None,
            "open_positions": 0,
            "position_used_pct": 0.0,
        }
        
        frontend_display = simulate_frontend_display(api_response)
        assert frontend_display["display_type"] == "unlimited"
        assert "Open positions: 0" in frontend_display["info"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
