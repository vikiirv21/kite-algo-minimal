"""
Equity Curve Tracker

Appends equity snapshots to a CSV file for historical equity curve tracking.
Designed to append one line every 5 seconds with timestamp, equity, realized_pnl,
and unrealized_pnl.
"""

from __future__ import annotations

import csv
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class EquityCurveWriter:
    """
    Thread-safe equity curve writer that appends snapshots to CSV.
    
    This writer appends equity snapshots to artifacts/snapshots.csv with
    timestamp, equity, realized_pnl, and unrealized_pnl columns.
    
    Features:
    - Thread-safe appending
    - Rate limiting (minimum interval between snapshots)
    - Automatic CSV header creation
    - Safe error handling (never crashes the engine)
    """
    
    def __init__(
        self,
        artifacts_dir: Optional[Path] = None,
        filename: str = "snapshots.csv",
        min_interval_sec: float = 5.0,
    ):
        """
        Initialize EquityCurveWriter.
        
        Args:
            artifacts_dir: Directory for artifacts (defaults to ./artifacts)
            filename: CSV filename (default: "snapshots.csv")
            min_interval_sec: Minimum seconds between snapshots (default: 5.0)
        """
        # Set up artifacts directory
        if artifacts_dir is None:
            artifacts_dir = Path(__file__).resolve().parents[1] / "artifacts"
        self.artifacts_dir = Path(artifacts_dir)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        
        self.csv_path = self.artifacts_dir / filename
        self.min_interval_sec = min_interval_sec
        
        # Thread safety
        self._lock = threading.RLock()
        
        # Rate limiting
        self._last_write_time = 0.0
        
        # CSV fieldnames
        self.fieldnames = ["timestamp", "equity", "realized_pnl", "unrealized_pnl"]
        
        # Initialize CSV file with header if it doesn't exist
        self._initialize_csv()
        
        logger.info(
            "EquityCurveWriter initialized: path=%s, interval=%.1fs",
            self.csv_path,
            min_interval_sec,
        )
    
    def _initialize_csv(self) -> None:
        """Initialize CSV file with header if it doesn't exist."""
        try:
            if not self.csv_path.exists():
                with open(self.csv_path, "w", encoding="utf-8", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=self.fieldnames)
                    writer.writeheader()
                logger.info("Created new equity curve CSV: %s", self.csv_path)
        except Exception as exc:
            logger.error("Failed to initialize CSV file: %s", exc)
    
    def append_snapshot(
        self,
        equity: float,
        realized_pnl: float,
        unrealized_pnl: float,
        timestamp: Optional[str] = None,
    ) -> bool:
        """
        Append an equity snapshot to the CSV file.
        
        Args:
            equity: Current equity value
            realized_pnl: Realized PnL
            unrealized_pnl: Unrealized PnL
            timestamp: Optional ISO timestamp (defaults to current time)
            
        Returns:
            True if snapshot was written, False if rate-limited or error
        """
        now = time.time()
        
        with self._lock:
            # Rate limit writes
            if now - self._last_write_time < self.min_interval_sec:
                return False
            
            try:
                # Generate timestamp if not provided
                if timestamp is None:
                    timestamp = datetime.now(timezone.utc).isoformat()
                
                # Prepare row
                row = {
                    "timestamp": timestamp,
                    "equity": f"{equity:.2f}",
                    "realized_pnl": f"{realized_pnl:.2f}",
                    "unrealized_pnl": f"{unrealized_pnl:.2f}",
                }
                
                # Append to CSV
                with open(self.csv_path, "a", encoding="utf-8", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=self.fieldnames)
                    writer.writerow(row)
                
                # Update last write time
                self._last_write_time = now
                
                logger.debug(
                    "Equity snapshot written: equity=%.2f, realized=%.2f, unrealized=%.2f",
                    equity,
                    realized_pnl,
                    unrealized_pnl,
                )
                
                return True
                
            except Exception as exc:
                logger.error("Failed to write equity snapshot: %s", exc)
                return False
    
    def read_curve(
        self,
        max_rows: Optional[int] = None,
    ) -> list[dict[str, str]]:
        """
        Read equity curve from CSV file.
        
        Args:
            max_rows: Maximum number of rows to return (None for all)
            
        Returns:
            List of dictionaries with snapshot data
        """
        try:
            if not self.csv_path.exists():
                return []
            
            with open(self.csv_path, "r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            
            # Return last N rows if max_rows specified
            if max_rows is not None and len(rows) > max_rows:
                rows = rows[-max_rows:]
            
            return rows
            
        except Exception as exc:
            logger.error("Failed to read equity curve: %s", exc)
            return []


def load_equity_curve(
    artifacts_dir: Optional[Path] = None,
    filename: str = "snapshots.csv",
    max_rows: Optional[int] = None,
) -> list[dict[str, str]]:
    """
    Safely load equity curve from CSV file.
    
    This is a safe loader that never crashes - returns empty list
    if the file doesn't exist or contains invalid data.
    
    Args:
        artifacts_dir: Directory for artifacts (defaults to ./artifacts)
        filename: CSV filename (default: "snapshots.csv")
        max_rows: Maximum number of rows to return (None for all)
        
    Returns:
        List of dictionaries with snapshot data (never None)
    """
    # Set up path
    if artifacts_dir is None:
        base_dir = Path(__file__).resolve().parents[1]
        artifacts_dir = base_dir / "artifacts"
    
    csv_path = Path(artifacts_dir) / filename
    
    # Check if file exists
    if not csv_path.exists():
        logger.debug("Equity curve file not found: %s", csv_path)
        return []
    
    # Try to load
    try:
        with open(csv_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        # Return last N rows if max_rows specified
        if max_rows is not None and len(rows) > max_rows:
            rows = rows[-max_rows:]
        
        logger.debug("Loaded %d equity curve rows from %s", len(rows), csv_path)
        return rows
        
    except Exception as exc:
        logger.warning("Failed to load equity curve from %s: %s", csv_path, exc)
        return []
