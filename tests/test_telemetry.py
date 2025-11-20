"""
Test suite for core.telemetry module.

Tests:
- EngineTelemetryReporter creation and JSON writing
- Heartbeat updates
- Mark stopped
- Telemetry directory creation
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from core.telemetry import (
    EngineTelemetry,
    EngineTelemetryReporter,
    ensure_telemetry_dir,
    TELEMETRY_DIR,
)


def test_ensure_telemetry_dir():
    """Test that telemetry directory is created."""
    # Use a temporary directory for testing
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch('core.telemetry.TELEMETRY_DIR', Path(tmpdir) / "telemetry"):
            ensure_telemetry_dir()
            assert (Path(tmpdir) / "telemetry").exists()
            assert (Path(tmpdir) / "telemetry").is_dir()


def test_engine_telemetry_dataclass():
    """Test EngineTelemetry dataclass."""
    telemetry = EngineTelemetry(
        name="test_engine",
        mode="paper",
        pid=12345,
        status="running",
        started_at="2025-01-01T00:00:00",
        last_heartbeat="2025-01-01T00:00:00",
        loop_tick=42,
        universe_size=10,
        open_positions=3,
    )
    
    # Test to_dict conversion
    data = telemetry.to_dict()
    assert data["name"] == "test_engine"
    assert data["mode"] == "paper"
    assert data["pid"] == 12345
    assert data["status"] == "running"
    assert data["loop_tick"] == 42
    assert data["universe_size"] == 10
    assert data["open_positions"] == 3
    assert data["last_error"] is None


def test_engine_telemetry_reporter_creation():
    """Test EngineTelemetryReporter initialization."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch('core.telemetry.TELEMETRY_DIR', Path(tmpdir)):
            reporter = EngineTelemetryReporter(name="fno", mode="paper")
            
            # Check attributes
            assert reporter.name == "fno"
            assert reporter.mode == "paper"
            assert reporter.pid == os.getpid()
            
            # Check JSON file was created
            telemetry_file = Path(tmpdir) / "fno_engine.json"
            assert telemetry_file.exists()
            
            # Check JSON content
            with telemetry_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            
            assert data["name"] == "fno"
            assert data["mode"] == "paper"
            assert data["pid"] == os.getpid()
            assert data["status"] == "starting"
            assert "started_at" in data
            assert "last_heartbeat" in data


def test_engine_telemetry_reporter_heartbeat():
    """Test EngineTelemetryReporter heartbeat updates."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch('core.telemetry.TELEMETRY_DIR', Path(tmpdir)):
            reporter = EngineTelemetryReporter(name="equity", mode="paper")
            
            # Update with heartbeat
            reporter.heartbeat(
                loop_tick=100,
                universe_size=25,
                open_positions=5,
                status="running",
            )
            
            # Check updated JSON
            telemetry_file = Path(tmpdir) / "equity_engine.json"
            with telemetry_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            
            assert data["loop_tick"] == 100
            assert data["universe_size"] == 25
            assert data["open_positions"] == 5
            assert data["status"] == "running"
            assert data["last_error"] is None


def test_engine_telemetry_reporter_error():
    """Test EngineTelemetryReporter error status."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch('core.telemetry.TELEMETRY_DIR', Path(tmpdir)):
            reporter = EngineTelemetryReporter(name="options", mode="paper")
            
            # Update with error
            reporter.heartbeat(
                status="error",
                last_error="Test error message",
            )
            
            # Check updated JSON
            telemetry_file = Path(tmpdir) / "options_engine.json"
            with telemetry_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            
            assert data["status"] == "error"
            assert data["last_error"] == "Test error message"


def test_engine_telemetry_reporter_mark_stopped():
    """Test EngineTelemetryReporter mark_stopped."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch('core.telemetry.TELEMETRY_DIR', Path(tmpdir)):
            reporter = EngineTelemetryReporter(name="fno", mode="paper")
            
            # Mark as stopped
            reporter.mark_stopped()
            
            # Check updated JSON
            telemetry_file = Path(tmpdir) / "fno_engine.json"
            with telemetry_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            
            assert data["status"] == "stopped"


def test_partial_heartbeat_updates():
    """Test that partial heartbeat updates only modify specified fields."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch('core.telemetry.TELEMETRY_DIR', Path(tmpdir)):
            reporter = EngineTelemetryReporter(name="test", mode="paper")
            
            # Initial heartbeat with all fields
            reporter.heartbeat(
                loop_tick=10,
                universe_size=5,
                open_positions=2,
                status="running",
            )
            
            # Partial update - only loop_tick
            reporter.heartbeat(loop_tick=20)
            
            # Check that other fields are preserved
            telemetry_file = Path(tmpdir) / "test_engine.json"
            with telemetry_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            
            assert data["loop_tick"] == 20
            assert data["universe_size"] == 5  # Preserved
            assert data["open_positions"] == 2  # Preserved
            assert data["status"] == "running"  # Preserved


def test_multiple_engines():
    """Test that multiple engines can report independently."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch('core.telemetry.TELEMETRY_DIR', Path(tmpdir)):
            # Create multiple reporters
            fno_reporter = EngineTelemetryReporter(name="fno", mode="paper")
            equity_reporter = EngineTelemetryReporter(name="equity", mode="paper")
            options_reporter = EngineTelemetryReporter(name="options", mode="paper")
            
            # Update each independently
            fno_reporter.heartbeat(loop_tick=10, status="running")
            equity_reporter.heartbeat(loop_tick=20, status="running")
            options_reporter.heartbeat(loop_tick=30, status="running")
            
            # Check that all files exist and have correct data
            fno_file = Path(tmpdir) / "fno_engine.json"
            equity_file = Path(tmpdir) / "equity_engine.json"
            options_file = Path(tmpdir) / "options_engine.json"
            
            assert fno_file.exists()
            assert equity_file.exists()
            assert options_file.exists()
            
            with fno_file.open("r", encoding="utf-8") as f:
                fno_data = json.load(f)
            with equity_file.open("r", encoding="utf-8") as f:
                equity_data = json.load(f)
            with options_file.open("r", encoding="utf-8") as f:
                options_data = json.load(f)
            
            assert fno_data["name"] == "fno"
            assert fno_data["loop_tick"] == 10
            assert equity_data["name"] == "equity"
            assert equity_data["loop_tick"] == 20
            assert options_data["name"] == "options"
            assert options_data["loop_tick"] == 30


if __name__ == "__main__":
    # Run tests
    test_ensure_telemetry_dir()
    test_engine_telemetry_dataclass()
    test_engine_telemetry_reporter_creation()
    test_engine_telemetry_reporter_heartbeat()
    test_engine_telemetry_reporter_error()
    test_engine_telemetry_reporter_mark_stopped()
    test_partial_heartbeat_updates()
    test_multiple_engines()
    print("All tests passed!")
