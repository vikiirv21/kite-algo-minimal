"""
Dashboard Logs API Router

Provides endpoints for tailing engine log files from the paper trading session.
Maps engine names to their corresponding log file paths and returns the last N lines.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)

router = APIRouter()

# Base directory for artifacts
BASE_DIR = Path(__file__).resolve().parents[1]
ARTIFACTS_ROOT = BASE_DIR / "artifacts"
LOGS_DIR = ARTIFACTS_ROOT / "logs"

# Engine to log file mapping
ENGINE_LOG_MAP = {
    "fno": "fno_paper.log",
    "equity": "equity_paper.log",
    "options": "options_paper.log",
}


def tail_file(file_path: Path, lines: int = 200) -> list[str]:
    """
    Read the last N lines from a file.
    
    Args:
        file_path: Path to the log file
        lines: Number of lines to return from the end
        
    Returns:
        List of log lines (without trailing newlines)
    """
    if not file_path.exists():
        return []
    
    try:
        with file_path.open("r", encoding="utf-8", errors="ignore") as f:
            all_lines = f.readlines()
        
        # Filter out empty lines and get last N
        non_empty = [line.rstrip("\n") for line in all_lines if line.strip()]
        return non_empty[-lines:] if lines > 0 else non_empty
    except Exception as exc:
        logger.exception("Failed to tail file %s: %s", file_path, exc)
        return []


@router.get("/api/logs/tail")
async def tail_engine_logs(
    engine: str = Query(..., description="Engine name: fno, equity, or options"),
    lines: int = Query(200, ge=1, le=1000, description="Number of lines to return (1-1000)")
) -> dict[str, Any]:
    """
    Tail engine log files and return the last N lines.
    
    Args:
        engine: Engine name (fno, equity, options)
        lines: Number of lines to return (default 200, max 1000)
        
    Returns:
        JSON response with:
        - engine: The engine name
        - lines: List of log line strings
        - count: Number of lines returned
        - file: The log file path (relative)
        - exists: Whether the file exists
        - warning: Warning message if file doesn't exist
    """
    # Validate engine name
    engine_lower = engine.lower().strip()
    if engine_lower not in ENGINE_LOG_MAP:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid engine name. Must be one of: {', '.join(ENGINE_LOG_MAP.keys())}"
        )
    
    # Get log file path
    log_filename = ENGINE_LOG_MAP[engine_lower]
    log_path = LOGS_DIR / log_filename
    
    # Check if file exists
    if not log_path.exists():
        logger.warning("Log file not found: %s", log_path)
        return {
            "engine": engine_lower,
            "lines": [],
            "count": 0,
            "file": str(log_path.relative_to(BASE_DIR)),
            "exists": False,
            "warning": f"Log file {log_filename} does not exist. Engine may not be running.",
        }
    
    # Tail the file
    log_lines = tail_file(log_path, lines)
    
    return {
        "engine": engine_lower,
        "lines": log_lines,
        "count": len(log_lines),
        "file": str(log_path.relative_to(BASE_DIR)),
        "exists": True,
        "warning": None,
    }
