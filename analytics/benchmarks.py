"""
Benchmarks Module

Provides functions to load and filter benchmark data from JSON files.
Benchmarks track index prices (NIFTY, BANKNIFTY, FINNIFTY) over time.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Artifact directory for benchmark data
ARTIFACT_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "benchmarks"


def _load_all_benchmarks() -> List[Dict[str, Any]]:
    """
    Load all benchmark data from JSON files in the artifacts/benchmarks directory.
    
    Returns:
        List of benchmark datapoints, each containing:
        - ts: ISO timestamp
        - nifty: NIFTY index price
        - banknifty: BANKNIFTY index price
        - finnifty: FINNIFTY index price
    """
    if not ARTIFACT_DIR.exists():
        logger.warning("Benchmarks directory does not exist: %s", ARTIFACT_DIR)
        return []
    
    all_benchmarks: List[Dict[str, Any]] = []
    
    try:
        # Load all *.json files in the directory
        for json_file in sorted(ARTIFACT_DIR.glob("*.json")):
            try:
                with json_file.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                
                # Support both single object and array formats
                if isinstance(data, list):
                    all_benchmarks.extend(data)
                elif isinstance(data, dict):
                    all_benchmarks.append(data)
                else:
                    logger.warning("Unexpected data format in %s", json_file)
            except Exception as exc:
                logger.warning("Failed to load benchmark file %s: %s", json_file, exc)
                continue
    except Exception as exc:
        logger.error("Failed to load benchmarks from %s: %s", ARTIFACT_DIR, exc)
        return []
    
    # Sort by timestamp
    try:
        all_benchmarks.sort(key=lambda x: x.get("ts", ""))
    except Exception as exc:
        logger.warning("Failed to sort benchmarks: %s", exc)
    
    return all_benchmarks


def get_benchmarks(days: int = 1) -> List[Dict[str, Any]]:
    """
    Get benchmark datapoints for the last N days.
    
    Args:
        days: Number of days to look back (default: 1)
        
    Returns:
        List of benchmark datapoints within the time window, sorted by timestamp.
    """
    if days <= 0:
        return []
    
    all_benchmarks = _load_all_benchmarks()
    
    if not all_benchmarks:
        return []
    
    # Calculate cutoff timestamp
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    
    # Filter benchmarks within the time window
    filtered = []
    for benchmark in all_benchmarks:
        ts_str = benchmark.get("ts", "")
        if not ts_str:
            continue
        
        try:
            # Parse timestamp (handle both with and without timezone)
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            
            # Ensure timezone-aware
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            
            if ts >= cutoff:
                filtered.append(benchmark)
        except Exception as exc:
            logger.debug("Failed to parse timestamp %s: %s", ts_str, exc)
            continue
    
    return filtered
