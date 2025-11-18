"""
Unit tests for analytics/risk_service.py module.
"""

import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone

import pytest
import yaml

from analytics.risk_service import (
    RiskLimits,
    load_risk_limits,
    save_risk_limits,
    compute_breaches,
    compute_var,
)


class TestRiskLimits:
    """Test RiskLimits dataclass."""
    
    def test_risk_limits_creation(self):
        """Test creating a RiskLimits instance."""
        limits = RiskLimits(
            max_daily_loss_rupees=5000.0,
            max_daily_drawdown_pct=0.02,
            max_trades_per_day=100,
            max_trades_per_symbol_per_day=5,
            max_loss_streak=5,
        )
        
        assert limits.max_daily_loss_rupees == 5000.0
        assert limits.max_daily_drawdown_pct == 0.02
        assert limits.max_trades_per_day == 100
        assert limits.max_trades_per_symbol_per_day == 5
        assert limits.max_loss_streak == 5


class TestLoadRiskLimits:
    """Test load_risk_limits function."""
    
    def test_load_from_base_config_only(self, tmp_path):
        """Test loading limits from base config without overrides."""
        # Create base config
        config_path = tmp_path / "dev.yaml"
        config = {
            "trading": {
                "max_daily_loss": 3000.0,
            },
            "execution": {
                "circuit_breakers": {
                    "max_daily_loss_rupees": 5000.0,
                    "max_daily_drawdown_pct": 0.02,
                    "max_trades_per_day": 100,
                    "max_loss_streak": 5,
                }
            },
            "risk": {
                "quality": {
                    "max_trades_per_symbol_per_day": 5,
                }
            }
        }
        
        with config_path.open("w") as f:
            yaml.dump(config, f)
        
        # Load limits
        overrides_path = tmp_path / "risk_overrides.yaml"
        limits, metadata = load_risk_limits(
            config_path=config_path,
            overrides_path=overrides_path,
        )
        
        # Verify
        assert limits.max_daily_loss_rupees == 5000.0
        assert limits.max_daily_drawdown_pct == 0.02
        assert limits.max_trades_per_day == 100
        assert limits.max_trades_per_symbol_per_day == 5
        assert limits.max_loss_streak == 5
        assert metadata["updated_at"] is None  # No overrides file
    
    def test_load_with_overrides(self, tmp_path):
        """Test loading limits with overrides."""
        # Create base config
        config_path = tmp_path / "dev.yaml"
        config = {
            "execution": {
                "circuit_breakers": {
                    "max_daily_loss_rupees": 5000.0,
                    "max_daily_drawdown_pct": 0.02,
                    "max_trades_per_day": 100,
                    "max_loss_streak": 5,
                    "max_trades_per_symbol_per_day": 5,
                }
            }
        }
        
        with config_path.open("w") as f:
            yaml.dump(config, f)
        
        # Create overrides
        overrides_path = tmp_path / "risk_overrides.yaml"
        overrides = {
            "max_daily_loss_rupees": 6000.0,
            "max_trades_per_day": 120,
        }
        
        with overrides_path.open("w") as f:
            yaml.dump(overrides, f)
        
        # Load limits
        limits, metadata = load_risk_limits(
            config_path=config_path,
            overrides_path=overrides_path,
        )
        
        # Verify - overrides should be applied
        assert limits.max_daily_loss_rupees == 6000.0  # Overridden
        assert limits.max_daily_drawdown_pct == 0.02  # From base
        assert limits.max_trades_per_day == 120  # Overridden
        assert limits.max_loss_streak == 5  # From base
        assert metadata["updated_at"] is not None  # Has overrides file
    
    def test_load_missing_base_config(self, tmp_path):
        """Test loading when base config doesn't exist."""
        config_path = tmp_path / "nonexistent.yaml"
        overrides_path = tmp_path / "risk_overrides.yaml"
        
        # Should use defaults without error
        limits, metadata = load_risk_limits(
            config_path=config_path,
            overrides_path=overrides_path,
        )
        
        # Should have default values
        assert limits.max_daily_loss_rupees == 5000.0
        assert limits.max_daily_drawdown_pct == 0.02


class TestSaveRiskLimits:
    """Test save_risk_limits function."""
    
    def test_save_new_overrides(self, tmp_path):
        """Test saving overrides when file doesn't exist."""
        # Setup base config
        config_path = tmp_path / "dev.yaml"
        config = {
            "execution": {
                "circuit_breakers": {
                    "max_daily_loss_rupees": 5000.0,
                    "max_daily_drawdown_pct": 0.02,
                    "max_trades_per_day": 100,
                    "max_loss_streak": 5,
                    "max_trades_per_symbol_per_day": 5,
                }
            }
        }
        
        with config_path.open("w") as f:
            yaml.dump(config, f)
        
        # Save patch
        overrides_path = tmp_path / "risk_overrides.yaml"
        patch = {
            "max_daily_loss_rupees": 6000.0,
            "max_trades_per_day": 120,
        }
        
        # Monkey-patch the module constants for this test
        import analytics.risk_service as rs
        original_config_path = rs.DEFAULT_CONFIG_PATH
        original_overrides_path = rs.DEFAULT_OVERRIDES_PATH
        
        try:
            rs.DEFAULT_CONFIG_PATH = config_path
            rs.DEFAULT_OVERRIDES_PATH = overrides_path
            
            updated_limits = save_risk_limits(patch, overrides_path=overrides_path)
            
            # Verify updated limits
            assert updated_limits.max_daily_loss_rupees == 6000.0
            assert updated_limits.max_trades_per_day == 120
            
            # Verify file was created
            assert overrides_path.exists()
            
            # Verify file contents
            with overrides_path.open("r") as f:
                saved_data = yaml.safe_load(f)
            
            assert saved_data["max_daily_loss_rupees"] == 6000.0
            assert saved_data["max_trades_per_day"] == 120
        finally:
            rs.DEFAULT_CONFIG_PATH = original_config_path
            rs.DEFAULT_OVERRIDES_PATH = original_overrides_path
    
    def test_save_merge_with_existing(self, tmp_path):
        """Test saving when overrides file already exists."""
        # Setup base config
        config_path = tmp_path / "dev.yaml"
        config = {
            "execution": {
                "circuit_breakers": {
                    "max_daily_loss_rupees": 5000.0,
                    "max_daily_drawdown_pct": 0.02,
                    "max_trades_per_day": 100,
                    "max_loss_streak": 5,
                    "max_trades_per_symbol_per_day": 5,
                }
            }
        }
        
        with config_path.open("w") as f:
            yaml.dump(config, f)
        
        # Create existing overrides
        overrides_path = tmp_path / "risk_overrides.yaml"
        existing = {
            "max_daily_loss_rupees": 6000.0,
        }
        
        with overrides_path.open("w") as f:
            yaml.dump(existing, f)
        
        # Save new patch
        patch = {
            "max_trades_per_day": 120,
        }
        
        # Monkey-patch module constants
        import analytics.risk_service as rs
        original_config_path = rs.DEFAULT_CONFIG_PATH
        original_overrides_path = rs.DEFAULT_OVERRIDES_PATH
        
        try:
            rs.DEFAULT_CONFIG_PATH = config_path
            rs.DEFAULT_OVERRIDES_PATH = overrides_path
            
            updated_limits = save_risk_limits(patch, overrides_path=overrides_path)
            
            # Should have both existing and new overrides
            assert updated_limits.max_daily_loss_rupees == 6000.0  # Existing
            assert updated_limits.max_trades_per_day == 120  # New
            
            # Verify file contents
            with overrides_path.open("r") as f:
                saved_data = yaml.safe_load(f)
            
            assert saved_data["max_daily_loss_rupees"] == 6000.0
            assert saved_data["max_trades_per_day"] == 120
        finally:
            rs.DEFAULT_CONFIG_PATH = original_config_path
            rs.DEFAULT_OVERRIDES_PATH = original_overrides_path


class TestComputeBreaches:
    """Test compute_breaches function."""
    
    def test_no_breaches(self, tmp_path, monkeypatch):
        """Test when no limits are breached."""
        # Create runtime metrics with no breaches
        runtime_metrics = {
            "asof": "2025-11-18T10:00:00+00:00",
            "equity": {
                "realized_pnl": 500.0,  # Positive
                "max_drawdown": -0.005,  # -0.5%
            },
            "overall": {
                "total_trades": 10,
                "loss_streak": 1,
            },
            "per_symbol": {
                "NIFTY25DECFUT": {
                    "total_trades": 3,
                }
            }
        }
        
        # Setup runtime metrics file
        analytics_dir = tmp_path / "analytics"
        analytics_dir.mkdir()
        metrics_path = analytics_dir / "runtime_metrics.json"
        
        with metrics_path.open("w") as f:
            json.dump(runtime_metrics, f)
        
        # Monkey-patch paths
        import analytics.risk_service as rs
        monkeypatch.setattr(rs, "RUNTIME_METRICS_PATH", metrics_path)
        
        # Test
        limits = RiskLimits(
            max_daily_loss_rupees=5000.0,
            max_daily_drawdown_pct=0.02,
            max_trades_per_day=100,
            max_trades_per_symbol_per_day=5,
            max_loss_streak=5,
        )
        
        breaches = compute_breaches(limits)
        
        # Should have no breaches
        assert len(breaches) == 0
    
    def test_daily_loss_breach(self, tmp_path, monkeypatch):
        """Test daily loss breach detection."""
        runtime_metrics = {
            "asof": "2025-11-18T10:00:00+00:00",
            "equity": {
                "realized_pnl": -5500.0,  # Exceeds limit
                "max_drawdown": -0.01,
            },
            "overall": {
                "total_trades": 10,
                "loss_streak": 1,
            },
            "per_symbol": {}
        }
        
        analytics_dir = tmp_path / "analytics"
        analytics_dir.mkdir()
        metrics_path = analytics_dir / "runtime_metrics.json"
        
        with metrics_path.open("w") as f:
            json.dump(runtime_metrics, f)
        
        import analytics.risk_service as rs
        monkeypatch.setattr(rs, "RUNTIME_METRICS_PATH", metrics_path)
        
        limits = RiskLimits(
            max_daily_loss_rupees=5000.0,
            max_daily_drawdown_pct=0.02,
            max_trades_per_day=100,
            max_trades_per_symbol_per_day=5,
            max_loss_streak=5,
        )
        
        breaches = compute_breaches(limits)
        
        # Should have daily loss breach
        assert len(breaches) >= 1
        loss_breach = next(b for b in breaches if b["code"] == "MAX_DAILY_LOSS")
        assert loss_breach["severity"] == "critical"
        assert loss_breach["metric"]["current"] == 5500.0
        assert loss_breach["metric"]["limit"] == 5000.0
    
    def test_multiple_breaches(self, tmp_path, monkeypatch):
        """Test multiple simultaneous breaches."""
        runtime_metrics = {
            "asof": "2025-11-18T10:00:00+00:00",
            "equity": {
                "realized_pnl": -5500.0,  # Breach 1: daily loss
                "max_drawdown": -0.025,  # Breach 2: drawdown (2.5%)
            },
            "overall": {
                "total_trades": 105,  # Breach 3: total trades
                "loss_streak": 6,  # Breach 4: loss streak
            },
            "per_symbol": {
                "NIFTY25DECFUT": {
                    "total_trades": 6,  # Breach 5: per-symbol trades
                }
            }
        }
        
        analytics_dir = tmp_path / "analytics"
        analytics_dir.mkdir()
        metrics_path = analytics_dir / "runtime_metrics.json"
        
        with metrics_path.open("w") as f:
            json.dump(runtime_metrics, f)
        
        import analytics.risk_service as rs
        monkeypatch.setattr(rs, "RUNTIME_METRICS_PATH", metrics_path)
        
        limits = RiskLimits(
            max_daily_loss_rupees=5000.0,
            max_daily_drawdown_pct=0.02,
            max_trades_per_day=100,
            max_trades_per_symbol_per_day=5,
            max_loss_streak=5,
        )
        
        breaches = compute_breaches(limits)
        
        # Should have 5 breaches
        assert len(breaches) == 5
        
        breach_codes = {b["code"] for b in breaches}
        expected_codes = {
            "MAX_DAILY_LOSS",
            "MAX_DRAWDOWN",
            "MAX_TRADES_PER_DAY",
            "MAX_TRADES_PER_SYMBOL",
            "MAX_LOSS_STREAK",
        }
        assert breach_codes == expected_codes


class TestComputeVar:
    """Test compute_var function."""
    
    def test_var_calculation(self, tmp_path, monkeypatch):
        """Test basic VaR calculation."""
        # Create daily metrics
        analytics_dir = tmp_path / "analytics"
        daily_dir = analytics_dir / "daily"
        daily_dir.mkdir(parents=True)
        
        # Create 30 days of metrics with varying PnL
        pnls = [-2000, -1500, -1000, -500, 0, 100, 200, 300, 400, 500] * 3
        
        for i, pnl in enumerate(pnls):
            metrics_file = daily_dir / f"2025-11-{i+1:02d}-metrics.json"
            metrics = {
                "equity": {
                    "realized_pnl": float(pnl),
                    "starting_capital": 500000.0,
                }
            }
            with metrics_file.open("w") as f:
                json.dump(metrics, f)
        
        # Also create runtime metrics for capital
        runtime_metrics = {
            "equity": {
                "starting_capital": 500000.0,
            }
        }
        runtime_path = analytics_dir / "runtime_metrics.json"
        with runtime_path.open("w") as f:
            json.dump(runtime_metrics, f)
        
        # Monkey-patch paths
        import analytics.risk_service as rs
        monkeypatch.setattr(rs, "DAILY_METRICS_DIR", daily_dir)
        monkeypatch.setattr(rs, "RUNTIME_METRICS_PATH", runtime_path)
        
        # Compute VaR
        var_result = compute_var(days=30, confidence=0.95)
        
        # Verify
        assert var_result["days"] == 30
        assert var_result["confidence"] == 0.95
        assert var_result["method"] == "historical"
        assert var_result["sample_size"] == 30
        assert var_result["var_rupees"] > 0  # Should be positive
        assert var_result["var_pct"] > 0
    
    def test_var_no_data(self, tmp_path, monkeypatch):
        """Test VaR when no data is available."""
        analytics_dir = tmp_path / "analytics"
        daily_dir = analytics_dir / "daily"
        daily_dir.mkdir(parents=True)
        
        import analytics.risk_service as rs
        monkeypatch.setattr(rs, "DAILY_METRICS_DIR", daily_dir)
        
        var_result = compute_var(days=30, confidence=0.95)
        
        # Should return zeros
        assert var_result["var_rupees"] == 0.0
        assert var_result["var_pct"] == 0.0
        assert var_result["sample_size"] == 0
    
    def test_var_different_confidence(self, tmp_path, monkeypatch):
        """Test VaR with different confidence levels."""
        analytics_dir = tmp_path / "analytics"
        daily_dir = analytics_dir / "daily"
        daily_dir.mkdir(parents=True)
        
        # Create 30 days of losses
        pnls = list(range(-3000, 0, 100))  # 30 daily losses
        
        for i, pnl in enumerate(pnls):
            metrics_file = daily_dir / f"2025-11-{i+1:02d}-metrics.json"
            metrics = {"equity": {"realized_pnl": float(pnl)}}
            with metrics_file.open("w") as f:
                json.dump(metrics, f)
        
        import analytics.risk_service as rs
        monkeypatch.setattr(rs, "DAILY_METRICS_DIR", daily_dir)
        
        # 99% VaR should be higher than 95% VaR
        var_95 = compute_var(days=30, confidence=0.95)
        var_99 = compute_var(days=30, confidence=0.99)
        
        assert var_99["var_rupees"] >= var_95["var_rupees"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
