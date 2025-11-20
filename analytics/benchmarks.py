"""
Benchmarks Module

Provides functions to load and append benchmark data.
Benchmarks track index prices (NIFTY, BANKNIFTY, FINNIFTY) over time.
"""

from __future__ import annotations
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any
import json
import logging

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "benchmarks"


def ensure_benchmarks_dir() -> None:
    """Create benchmarks directory if it doesn't exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def benchmarks_file_for_date(d: datetime) -> Path:
    """
    Get the path to the benchmarks JSONL file for a specific date.
    One file per trading day.
    
    Args:
        d: Date to get file for
        
    Returns:
        Path to the JSONL file for that date
    """
    return DATA_DIR / f"benchmarks_{d.date().isoformat()}.jsonl"


def append_benchmark_snapshot(
    ts: datetime,
    nifty: float | None,
    banknifty: float | None,
    finnifty: float | None,
) -> None:
    """
    Append a single snapshot to today's JSONL file.
    This is called by a recorder script that runs during market hours.
    
    Args:
        ts: Timestamp of snapshot
        nifty: NIFTY index price (or None if not available)
        banknifty: BANKNIFTY index price (or None if not available)
        finnifty: FINNIFTY index price (or None if not available)
    """
    ensure_benchmarks_dir()
    record = {
        "ts": ts.isoformat(),
        "nifty": nifty,
        "banknifty": banknifty,
        "finnifty": finnifty,
    }
    path = benchmarks_file_for_date(ts)
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        logger.exception("Failed to append benchmark snapshot")


def load_benchmarks(days: int = 1) -> List[Dict[str, Any]]:
    """
    Load up to 'days' worth of benchmark data, merged into one list,
    sorted by timestamp ascending.
    If files do not exist, return [].
    
    Args:
        days: Number of days to look back (default: 1, max: 10)
        
    Returns:
        List of benchmark datapoints within the time window, sorted by timestamp.
    """
    ensure_benchmarks_dir()
    days = max(1, min(days, 10))  # cap at 10 days
    now = datetime.now()
    all_records: List[Dict[str, Any]] = []

    for i in range(days):
        d = now.date() - timedelta(days=i)
        path = DATA_DIR / f"benchmarks_{d.isoformat()}.jsonl"
        if not path.exists():
            continue
        try:
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        all_records.append(rec)
                    except json.JSONDecodeError:
                        logger.warning("Skipping invalid benchmark line in %s", path)
        except Exception:
            logger.exception("Failed to read benchmarks file %s", path)

    # sort by ts if present
    def key_fn(r: Dict[str, Any]):
        return r.get("ts", "")

    all_records.sort(key=key_fn)
    return all_records


# Legacy alias for backward compatibility
def get_benchmarks(days: int = 1) -> List[Dict[str, Any]]:
    """
    Legacy alias for load_benchmarks().
    
    Args:
        days: Number of days to look back (default: 1)
        
    Returns:
        List of benchmark datapoints within the time window, sorted by timestamp.
    """
    return load_benchmarks(days=days)
