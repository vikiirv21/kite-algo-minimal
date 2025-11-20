"""
Strategy Real-Time Diagnostics Engine (SRDE)

Provides real-time visibility into strategy decision-making by capturing and
persisting diagnostic information for each signal/decision.

Features:
- Non-blocking JSONL-based persistence
- Per-symbol, per-strategy storage
- Crash-resilient (auto-creates directories)
- Never slows down trading engines (best-effort logging)

Storage Format:
    artifacts/diagnostics/<symbol>/<strategy>.jsonl

Each record contains:
{
  "ts": ISO timestamp,
  "price": float,
  "ema20": float,
  "ema50": float,
  "trend_strength": float,
  "confidence": float,
  "rr": float,                    # risk:reward
  "regime": "trend"|"low_vol"|"compression"|None,
  "risk_block": "max_loss"|"cooldown"|"slippage"|"none",
  "decision": "BUY"|"SELL"|"HOLD",
  "reason": "<text>"
}
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Base diagnostics directory
BASE_DIR = Path(__file__).resolve().parents[1]
DIAGNOSTICS_DIR = BASE_DIR / "artifacts" / "diagnostics"


def ensure_diagnostics_dir() -> Path:
    """
    Ensure the diagnostics directory exists.
    
    Creates the directory structure if it doesn't exist.
    This is crash-safe and will not fail if directory already exists.
    
    Returns:
        Path to diagnostics directory
    """
    try:
        DIAGNOSTICS_DIR.mkdir(parents=True, exist_ok=True)
        return DIAGNOSTICS_DIR
    except Exception as exc:
        logger.debug("Failed to create diagnostics directory: %s", exc)
        return DIAGNOSTICS_DIR


def path_for(symbol: str, strategy: str) -> Path:
    """
    Generate the file path for a symbol/strategy diagnostic log.
    
    Args:
        symbol: Trading symbol (e.g., "NIFTY", "BANKNIFTY", "RELIANCE")
        strategy: Strategy identifier (e.g., "EMA_20_50", "FNO_TREND")
    
    Returns:
        Path to the JSONL file for this symbol/strategy combination
    
    Example:
        path_for("NIFTY", "EMA_20_50")
        -> artifacts/diagnostics/NIFTY/EMA_20_50.jsonl
    """
    # Normalize symbol and strategy names
    symbol_clean = str(symbol).strip().upper().replace("/", "_").replace("\\", "_")
    strategy_clean = str(strategy).strip().replace("/", "_").replace("\\", "_")
    
    # Build path: diagnostics/<symbol>/<strategy>.jsonl
    symbol_dir = DIAGNOSTICS_DIR / symbol_clean
    
    # Ensure symbol directory exists
    try:
        symbol_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        logger.debug("Failed to create symbol directory %s: %s", symbol_dir, exc)
    
    return symbol_dir / f"{strategy_clean}.jsonl"


def append_diagnostic(
    symbol: str,
    strategy: str,
    record: Dict[str, Any],
) -> bool:
    """
    Append a diagnostic record to the appropriate JSONL file.
    
    This function is designed to be non-blocking and never crash the engine.
    It performs best-effort logging with comprehensive error handling.
    
    Args:
        symbol: Trading symbol
        strategy: Strategy identifier
        record: Diagnostic record dictionary
    
    Returns:
        True if write succeeded, False otherwise
    
    Record Format:
        {
          "ts": ISO timestamp (auto-added if missing),
          "price": float,
          "ema20": float | None,
          "ema50": float | None,
          "trend_strength": float | None,
          "confidence": float,
          "rr": float | None,
          "regime": str | None,
          "risk_block": str,
          "decision": "BUY"|"SELL"|"HOLD",
          "reason": str
        }
    
    Example:
        append_diagnostic(
            symbol="NIFTY",
            strategy="EMA_20_50",
            record={
                "price": 19500.0,
                "ema20": 19450.0,
                "ema50": 19400.0,
                "trend_strength": 0.85,
                "confidence": 0.75,
                "rr": 2.5,
                "regime": "trend",
                "risk_block": "none",
                "decision": "BUY",
                "reason": "Strong uptrend with EMA20 > EMA50"
            }
        )
    """
    try:
        # Ensure record has timestamp
        if "ts" not in record:
            record["ts"] = datetime.now(timezone.utc).isoformat()
        
        # Get file path
        file_path = path_for(symbol, strategy)
        
        # Write record as JSONL (append mode)
        with file_path.open("a", encoding="utf-8") as f:
            json.dump(record, f)
            f.write("\n")
        
        return True
        
    except Exception as exc:
        # Never crash the engine - just log at debug level
        logger.debug(
            "Failed to append diagnostic for %s/%s: %s",
            symbol, strategy, exc
        )
        return False


def load_diagnostics(
    symbol: str,
    strategy: str,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """
    Load diagnostic records for a symbol/strategy combination.
    
    Reads the JSONL file and returns the most recent N records.
    This is crash-safe and returns empty list if file doesn't exist.
    
    Args:
        symbol: Trading symbol
        strategy: Strategy identifier
        limit: Maximum number of records to return (default: 200)
    
    Returns:
        List of diagnostic records (most recent first)
    
    Example:
        records = load_diagnostics("NIFTY", "EMA_20_50", limit=100)
        for rec in records:
            print(f"{rec['ts']}: {rec['decision']} - {rec['reason']}")
    """
    try:
        file_path = path_for(symbol, strategy)
        
        # Return empty list if file doesn't exist
        if not file_path.exists():
            logger.debug("No diagnostics file found for %s/%s", symbol, strategy)
            return []
        
        # Read all records
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
        
        # Return most recent N records (reverse order - newest first)
        if limit > 0:
            records = records[-limit:]
        
        # Reverse so newest is first
        records.reverse()
        
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
    **extra_fields,
) -> Dict[str, Any]:
    """
    Helper function to build a diagnostic record with standard fields.
    
    This ensures consistent field names and types across all diagnostics.
    
    Args:
        price: Current price
        decision: "BUY", "SELL", or "HOLD"
        reason: Human-readable explanation
        confidence: Confidence score (0.0-1.0)
        ema20: EMA20 indicator value
        ema50: EMA50 indicator value
        trend_strength: Trend strength (0.0-1.0)
        rr: Risk/Reward ratio
        regime: Market regime ("trend", "low_vol", "compression", etc.)
        risk_block: Risk block reason ("max_loss", "cooldown", "slippage", "none")
        **extra_fields: Additional fields to include
    
    Returns:
        Diagnostic record dictionary
    """
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "price": float(price) if price is not None else 0.0,
        "ema20": float(ema20) if ema20 is not None else None,
        "ema50": float(ema50) if ema50 is not None else None,
        "trend_strength": float(trend_strength) if trend_strength is not None else None,
        "confidence": float(confidence) if confidence is not None else 0.0,
        "rr": float(rr) if rr is not None else None,
        "regime": str(regime) if regime else None,
        "risk_block": str(risk_block) if risk_block else "none",
        "decision": str(decision).upper(),
        "reason": str(reason),
    }
    
    # Add any extra fields
    record.update(extra_fields)
    
    return record


# Initialize diagnostics directory on module load
ensure_diagnostics_dir()


__all__ = [
    "ensure_diagnostics_dir",
    "path_for",
    "append_diagnostic",
    "load_diagnostics",
    "build_diagnostic_record",
]
