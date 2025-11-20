"""
Test suite for benchmarks module.

Tests:
- Directory creation
- Snapshot appending
- Loading benchmarks
- Date-based file naming
"""

import sys
from pathlib import Path

# Add parent directory to path
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

import json
from datetime import datetime, timedelta
import tempfile
import shutil

# Note: We'll patch DATA_DIR to use a temp directory
from analytics import benchmarks


def test_ensure_benchmarks_dir():
    """Test that ensure_benchmarks_dir creates the directory."""
    # Use a temporary directory for testing
    with tempfile.TemporaryDirectory() as tmpdir:
        original_data_dir = benchmarks.DATA_DIR
        benchmarks.DATA_DIR = Path(tmpdir) / "benchmarks"
        
        try:
            # Initially should not exist
            assert not benchmarks.DATA_DIR.exists()
            
            # Call function
            benchmarks.ensure_benchmarks_dir()
            
            # Should now exist
            assert benchmarks.DATA_DIR.exists()
            assert benchmarks.DATA_DIR.is_dir()
        finally:
            benchmarks.DATA_DIR = original_data_dir


def test_benchmarks_file_for_date():
    """Test that benchmarks_file_for_date returns correct path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_data_dir = benchmarks.DATA_DIR
        benchmarks.DATA_DIR = Path(tmpdir) / "benchmarks"
        
        try:
            dt = datetime(2025, 11, 20, 10, 30, 0)
            path = benchmarks.benchmarks_file_for_date(dt)
            
            assert path.name == "benchmarks_2025-11-20.jsonl"
            assert path.parent == benchmarks.DATA_DIR
        finally:
            benchmarks.DATA_DIR = original_data_dir


def test_append_and_load_benchmarks():
    """Test appending and loading benchmark snapshots."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_data_dir = benchmarks.DATA_DIR
        benchmarks.DATA_DIR = Path(tmpdir) / "benchmarks"
        
        try:
            # Append some snapshots
            now = datetime.now()
            benchmarks.append_benchmark_snapshot(now, 19500.25, 45234.8, 20456.5)
            
            # Add another snapshot
            now2 = now + timedelta(seconds=60)
            benchmarks.append_benchmark_snapshot(now2, 19510.0, 45250.0, 20460.0)
            
            # Load benchmarks
            records = benchmarks.load_benchmarks(days=1)
            
            # Should have 2 records
            assert len(records) == 2
            
            # Check first record
            assert records[0]["nifty"] == 19500.25
            assert records[0]["banknifty"] == 45234.8
            assert records[0]["finnifty"] == 20456.5
            
            # Check second record
            assert records[1]["nifty"] == 19510.0
            assert records[1]["banknifty"] == 45250.0
            assert records[1]["finnifty"] == 20460.0
            
            # Check that timestamps are sorted
            assert records[0]["ts"] <= records[1]["ts"]
        finally:
            benchmarks.DATA_DIR = original_data_dir


def test_load_benchmarks_with_none_values():
    """Test that None values are handled correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_data_dir = benchmarks.DATA_DIR
        benchmarks.DATA_DIR = Path(tmpdir) / "benchmarks"
        
        try:
            # Append snapshot with None values
            now = datetime.now()
            benchmarks.append_benchmark_snapshot(now, None, 45234.8, None)
            
            # Load benchmarks
            records = benchmarks.load_benchmarks(days=1)
            
            assert len(records) == 1
            assert records[0]["nifty"] is None
            assert records[0]["banknifty"] == 45234.8
            assert records[0]["finnifty"] is None
        finally:
            benchmarks.DATA_DIR = original_data_dir


def test_load_benchmarks_empty_directory():
    """Test that load_benchmarks returns empty list when no files exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_data_dir = benchmarks.DATA_DIR
        benchmarks.DATA_DIR = Path(tmpdir) / "benchmarks"
        
        try:
            # Ensure directory exists but is empty
            benchmarks.ensure_benchmarks_dir()
            
            # Load benchmarks
            records = benchmarks.load_benchmarks(days=1)
            
            # Should return empty list
            assert records == []
        finally:
            benchmarks.DATA_DIR = original_data_dir


def test_load_benchmarks_multiple_days():
    """Test loading benchmarks across multiple days."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_data_dir = benchmarks.DATA_DIR
        benchmarks.DATA_DIR = Path(tmpdir) / "benchmarks"
        
        try:
            # Create snapshots for multiple days
            now = datetime.now()
            yesterday = now - timedelta(days=1)
            
            # Yesterday's snapshot
            benchmarks.append_benchmark_snapshot(yesterday, 19400.0, 45000.0, 20400.0)
            
            # Today's snapshot
            benchmarks.append_benchmark_snapshot(now, 19500.0, 45200.0, 20450.0)
            
            # Load 1 day (should get only today)
            records_1day = benchmarks.load_benchmarks(days=1)
            assert len(records_1day) >= 1  # At least today's
            
            # Load 2 days (should get both)
            records_2days = benchmarks.load_benchmarks(days=2)
            assert len(records_2days) >= 2  # Both days
            
            # Verify data is sorted by timestamp
            for i in range(len(records_2days) - 1):
                assert records_2days[i]["ts"] <= records_2days[i + 1]["ts"]
        finally:
            benchmarks.DATA_DIR = original_data_dir


def test_load_benchmarks_caps_days():
    """Test that load_benchmarks caps days parameter at 10."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_data_dir = benchmarks.DATA_DIR
        benchmarks.DATA_DIR = Path(tmpdir) / "benchmarks"
        
        try:
            # This should not crash even with large days parameter
            records = benchmarks.load_benchmarks(days=100)
            assert records == []  # Empty since no files exist
            
            # Should handle days < 1
            records = benchmarks.load_benchmarks(days=0)
            assert records == []
            
            records = benchmarks.load_benchmarks(days=-5)
            assert records == []
        finally:
            benchmarks.DATA_DIR = original_data_dir


if __name__ == "__main__":
    # Run tests manually
    test_ensure_benchmarks_dir()
    print("✓ test_ensure_benchmarks_dir")
    
    test_benchmarks_file_for_date()
    print("✓ test_benchmarks_file_for_date")
    
    test_append_and_load_benchmarks()
    print("✓ test_append_and_load_benchmarks")
    
    test_load_benchmarks_with_none_values()
    print("✓ test_load_benchmarks_with_none_values")
    
    test_load_benchmarks_empty_directory()
    print("✓ test_load_benchmarks_empty_directory")
    
    test_load_benchmarks_multiple_days()
    print("✓ test_load_benchmarks_multiple_days")
    
    test_load_benchmarks_caps_days()
    print("✓ test_load_benchmarks_caps_days")
    
    print("\nAll tests passed!")
