"""
Tests for the Market Session Orchestrator v1
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = BASE_DIR / "artifacts"
REPORTS_DIR = ARTIFACTS_DIR / "reports" / "daily"


class TestSessionOrchestrator:
    """Tests for run_session.py script"""
    
    def test_dry_run_mode(self):
        """Test that dry-run mode completes pre-checks without starting engines"""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.run_session",
                "--mode", "paper",
                "--config", "configs/dev.yaml",
                "--dry-run",
            ],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        # Should exit cleanly
        assert result.returncode == 0, f"Dry run failed: {result.stderr}"
        
        # Logging goes to stderr
        output = result.stderr
        
        # Should mention pre-market checks
        assert "PRE-MARKET CHECKS" in output
        
        # Should mention dry run completion
        assert "Dry run mode" in output
        assert "Pre-checks completed" in output
        
        # Should NOT start engines
        assert "Starting engines" not in output
    
    def test_help_flag(self):
        """Test that --help flag works"""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.run_session",
                "--help",
            ],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        assert result.returncode == 0
        assert "Market Session Orchestrator" in result.stdout
        assert "--mode" in result.stdout
        assert "--config" in result.stdout
        assert "--dry-run" in result.stdout
        assert "--no-backtest" in result.stdout
        assert "--no-analytics" in result.stdout
    
    def test_report_generation(self):
        """Test daily report generation function"""
        from scripts.run_session import generate_daily_report
        
        # Create mock analytics data
        today = datetime.now().strftime("%Y-%m-%d")
        analytics_dir = ARTIFACTS_DIR / "analytics" / "daily"
        analytics_dir.mkdir(parents=True, exist_ok=True)
        
        mock_analytics = {
            "date": today,
            "mode": "paper",
            "daily_metrics": {
                "realized_pnl": 500.0,
                "num_trades": 10,
                "win_rate": 60.0,
                "biggest_winner": 200.0,
                "biggest_loser": -100.0,
            },
            "strategy_metrics": {
                "test_strategy": {
                    "trades": 10,
                    "realized_pnl": 500.0,
                    "win_rate": 60.0,
                }
            }
        }
        
        analytics_file = analytics_dir / f"{today}.json"
        with analytics_file.open("w") as f:
            json.dump(mock_analytics, f)
        
        # Generate report
        result = generate_daily_report("paper", "configs/dev.yaml", today)
        
        # Check result
        assert result is True
        
        # Check JSON report exists
        json_report = REPORTS_DIR / f"{today}.json"
        assert json_report.exists()
        
        with json_report.open("r") as f:
            report_data = json.load(f)
        
        assert report_data["date"] == today
        assert report_data["mode"] == "PAPER"
        assert report_data["summary"]["realized_pnl"] == 500.0
        assert report_data["summary"]["num_trades"] == 10
        
        # Check Markdown report exists
        md_report = REPORTS_DIR / f"{today}.md"
        assert md_report.exists()
        
        with md_report.open("r") as f:
            md_content = f.read()
        
        assert f"# Daily Report — {today}" in md_content
        assert "Mode: PAPER" in md_content
        assert "Realized PnL: +500.00" in md_content
        assert "Trades: 10" in md_content
        assert "test_strategy" in md_content
    
    def test_config_validation(self):
        """Test config validation function"""
        from scripts.run_session import check_config_validity
        
        # Should pass with valid config
        result = check_config_validity("configs/dev.yaml")
        assert result is True
    
    def test_secrets_check(self):
        """Test secrets file validation"""
        from scripts.run_session import check_secrets_files
        
        # Should check for kite.env and kite_tokens.env
        result = check_secrets_files()
        # May pass or fail depending on environment, but shouldn't crash
        assert isinstance(result, bool)
    
    def test_market_time_helpers(self):
        """Test market time helper functions"""
        from scripts.run_session import is_market_open, get_session_config
        
        # Get session config
        session_config = get_session_config("configs/dev.yaml")
        assert "market_open_ist" in session_config
        assert "market_close_ist" in session_config
        
        # Test is_market_open (should return boolean)
        result = is_market_open(session_config)
        assert isinstance(result, bool)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
