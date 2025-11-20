"""
Strategy Real-Time Diagnostics Engine (SRDE)

Provides persistent, non-blocking diagnostic logging for strategy decisions.
Diagnostics help explain WHY a strategy gave BUY/SELL/HOLD signals.

Features:
- JSONL-based storage for crash resilience
- Per-symbol, per-strategy file organization
- Non-blocking writes (best-effort)
- Automatic directory creation
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Base directory for all diagnostics
BASE_DIR = Path(__file__).resolve().parents[1]
DIAGNOSTICS_DIR = BASE_DIR / "artifacts" / "diagnostics"


def ensure_diagnostics_dir() -> Path:
    """
    Ensure the base diagnostics directory exists.
    
    Returns:
        Path to diagnostics directory
    """
    try:
        DIAGNOSTICS_DIR.mkdir(parents=True, exist_ok=True)
        return DIAGNOSTICS_DIR
    except Exception as exc:
        logger.warning("Failed to create diagnostics directory: %s", exc)
        return DIAGNOSTICS_DIR


def path_for(symbol: str, strategy: str) -> Path:
    """
    Get the file path for a symbol-strategy combination.
    
    Creates nested directory structure: artifacts/diagnostics/<symbol>/<strategy>.jsonl
    
    Args:
        symbol: Trading symbol (e.g., "NIFTY", "BANKNIFTY")
        strategy: Strategy identifier (e.g., "EMA_20_50", "RSI_MACD")
    
    Returns:
        Path to JSONL file for this symbol-strategy pair
    """
    # Sanitize symbol and strategy names (remove invalid chars)
    safe_symbol = "".join(c for c in symbol if c.isalnum() or c in "_-")
    safe_strategy = "".join(c for c in strategy if c.isalnum() or c in "_-")
    
    # Create symbol subdirectory
    symbol_dir = DIAGNOSTICS_DIR / safe_symbol
    try:
        symbol_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        logger.debug("Failed to create symbol directory %s: %s", symbol_dir, exc)
    
    return symbol_dir / f"{safe_strategy}.jsonl"


def append_diagnostic(
    symbol: str,
    strategy: str,
    record: Dict[str, Any]
) -> bool:
    """
    Append a diagnostic record to the symbol-strategy JSONL file.
    
    This is a non-blocking, best-effort operation that should never
    crash or slow down the trading engine.
    
    Args:
        symbol: Trading symbol
        strategy: Strategy identifier
        record: Diagnostic record dict containing:
            - ts: ISO timestamp
            - price: float
            - ema20, ema50: float (optional)
            - trend_strength: float (optional)
            - confidence: float
            - rr: float (risk:reward, optional)
            - regime: str ("trend"|"low_vol"|"compression"|None)
            - risk_block: str ("max_loss"|"cooldown"|"slippage"|"none")
            - decision: str ("BUY"|"SELL"|"HOLD")
            - reason: str
    
    Returns:
        True if write succeeded, False otherwise
    """
    try:
        # Ensure base directory exists
        ensure_diagnostics_dir()
        
        # Get file path
        file_path = path_for(symbol, strategy)
        
        # Ensure timestamp is present
        if "ts" not in record:
            record["ts"] = datetime.now(timezone.utc).isoformat()
        
        # Append to JSONL file
        with file_path.open("a", encoding="utf-8") as f:
            json.dump(record, f)
            f.write("\n")
        
        return True
        
    except Exception as exc:
        # Log at debug level to avoid noise
        logger.debug(
            "Failed to append diagnostic for %s/%s: %s",
            symbol, strategy, exc
        )
        return False


def load_diagnostics(
    symbol: str,
    strategy: str,
    limit: int = 200
) -> List[Dict[str, Any]]:
    """
    Load the most recent diagnostic records for a symbol-strategy pair.
    
    Args:
        symbol: Trading symbol
        strategy: Strategy identifier
        limit: Maximum number of records to return (most recent first)
    
    Returns:
        List of diagnostic records (most recent first)
    """
    try:
        file_path = path_for(symbol, strategy)
        
        if not file_path.exists():
            logger.debug("No diagnostics file found for %s/%s", symbol, strategy)
            return []
        
        # Read all lines from the file
        records = []
        with file_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    records.append(record)
                except json.JSONDecodeError as exc:
                    logger.debug("Failed to parse diagnostic line: %s", exc)
                    continue
        
        # Return most recent records first
        records = records[-limit:] if len(records) > limit else records
        records.reverse()  # Most recent first
        
        return records
        
    except Exception as exc:
        logger.warning(
            "Failed to load diagnostics for %s/%s: %s",
            symbol, strategy, exc
        )
        return []


def build_diagnostic_record(
    price: float,
    decision: str,
    reason: str,
    confidence: float = 0.0,
    ema20: Optional[float] = None,
    ema50: Optional[float] = None,
    trend_strength: Optional[float] = None,
    rr: Optional[float] = None,
    regime: Optional[str] = None,
    risk_block: str = "none",
    **extra_fields
) -> Dict[str, Any]:
    """
    Build a standardized diagnostic record.
    
    Helper function to create consistent diagnostic records across engines.
    
    Args:
        price: Current price
        decision: Trading decision ("BUY"|"SELL"|"HOLD")
        reason: Explanation for the decision
        confidence: Confidence score (0.0 to 1.0)
        ema20: EMA 20 value (optional)
        ema50: EMA 50 value (optional)
        trend_strength: Trend strength indicator (optional)
        rr: Risk:reward ratio (optional)
        regime: Market regime ("trend"|"low_vol"|"compression"|None)
        risk_block: Risk block reason ("max_loss"|"cooldown"|"slippage"|"none")
        **extra_fields: Additional fields to include in the record
    
    Returns:
        Diagnostic record dict
    """
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "price": price,
        "decision": decision.upper(),
        "reason": reason,
        "confidence": confidence,
        "risk_block": risk_block,
    }
    
    # Add optional fields if provided
    if ema20 is not None:
        record["ema20"] = ema20
    if ema50 is not None:
        record["ema50"] = ema50
    if trend_strength is not None:
        record["trend_strength"] = trend_strength
    if rr is not None:
        record["rr"] = rr
    if regime is not None:
        record["regime"] = regime
    
    # Add any extra fields
    record.update(extra_fields)
    
    return record


__all__ = [
    "ensure_diagnostics_dir",
    "path_for",
    "append_diagnostic",
    "load_diagnostics",
    "build_diagnostic_record",
]
