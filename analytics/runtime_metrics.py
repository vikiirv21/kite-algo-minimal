"""
Runtime Metrics Tracker

Tracks live equity, PnL, per-symbol PnL, per-strategy PnL, and equity curve
for the unified analytics system.

This module provides real-time performance tracking that can be integrated
into trading engines (paper and live) to compute and persist metrics during
runtime.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class EquitySnapshot:
    """Single equity snapshot at a point in time."""
    timestamp: str
    equity: float
    realized_pnl: float
    unrealized_pnl: float


@dataclass
class RuntimeMetrics:
    """Container for all runtime metrics."""
    asof: str
    mode: str
    starting_capital: float
    current_equity: float
    realized_pnl: float
    unrealized_pnl: float
    daily_pnl: float
    max_equity: float
    min_equity: float
    max_drawdown: float
    pnl_per_symbol: Dict[str, float] = field(default_factory=dict)
    pnl_per_strategy: Dict[str, float] = field(default_factory=dict)
    equity_curve: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


class RuntimeMetricsTracker:
    """
    Track runtime metrics for live equity, PnL, and performance analytics.
    
    This tracker is thread-safe and can be safely called from multiple
    engine threads. It maintains a rolling window of equity snapshots
    and computes per-symbol and per-strategy PnL.
    
    Features:
    - Thread-safe updates
    - Rolling equity curve (configurable window size)
    - Per-symbol and per-strategy PnL tracking
    - Automatic JSON persistence
    - Safe loading with fallback to defaults
    """
    
    def __init__(
        self,
        starting_capital: float,
        mode: str = "paper",
        artifacts_dir: Optional[Path] = None,
        equity_curve_maxlen: int = 500,
    ):
        """
        Initialize RuntimeMetricsTracker.
        
        Args:
            starting_capital: Starting capital/equity
            mode: Trading mode ("paper" or "live")
            artifacts_dir: Directory for artifacts (defaults to ./artifacts)
            equity_curve_maxlen: Maximum equity curve snapshots to keep (default: 500)
        """
        self.starting_capital = starting_capital
        self.mode = mode
        self.equity_curve_maxlen = equity_curve_maxlen
        
        # Set up artifacts directory
        if artifacts_dir is None:
            artifacts_dir = Path(__file__).resolve().parents[1] / "artifacts"
        self.artifacts_dir = Path(artifacts_dir)
        self.analytics_dir = self.artifacts_dir / "analytics"
        self.analytics_dir.mkdir(parents=True, exist_ok=True)
        self.metrics_path = self.analytics_dir / "runtime_metrics.json"
        
        # Thread safety
        self._lock = threading.RLock()
        
        # Metrics state
        self.realized_pnl: float = 0.0
        self.unrealized_pnl: float = 0.0
        self.daily_pnl: float = 0.0
        self.max_equity: float = starting_capital
        self.min_equity: float = starting_capital
        self.max_drawdown: float = 0.0
        
        # Per-symbol and per-strategy tracking
        self.pnl_per_symbol: Dict[str, float] = defaultdict(float)
        self.pnl_per_strategy: Dict[str, float] = defaultdict(float)
        
        # Rolling equity curve
        self.equity_curve: deque = deque(maxlen=equity_curve_maxlen)
        
        # Track last snapshot time for rate limiting
        self._last_snapshot_time = 0.0
        
        logger.info(
            "RuntimeMetricsTracker initialized: capital=%.2f, mode=%s, curve_maxlen=%d",
            starting_capital,
            mode,
            equity_curve_maxlen,
        )
    
    @property
    def current_equity(self) -> float:
        """Calculate current equity (capital + realized PnL + unrealized PnL)."""
        return self.starting_capital + self.realized_pnl + self.unrealized_pnl
    
    def update_after_fill(
        self,
        symbol: str,
        strategy: str,
        realized_pnl: float,
        fill_price: float,
        qty: int,
        side: str,
    ) -> None:
        """
        Update metrics after an order fill.
        
        Args:
            symbol: Trading symbol
            strategy: Strategy identifier
            realized_pnl: Realized PnL from this fill
            fill_price: Fill price
            qty: Quantity filled
            side: Order side (BUY/SELL)
        """
        with self._lock:
            # Update realized PnL
            self.realized_pnl += realized_pnl
            self.daily_pnl += realized_pnl
            
            # Update per-symbol PnL
            self.pnl_per_symbol[symbol] += realized_pnl
            
            # Update per-strategy PnL
            self.pnl_per_strategy[strategy] += realized_pnl
            
            # Update equity metrics
            current_equity = self.current_equity
            self.max_equity = max(self.max_equity, current_equity)
            self.min_equity = min(self.min_equity, current_equity)
            
            # Update max drawdown
            if self.max_equity > 0:
                drawdown = (self.max_equity - current_equity) / self.max_equity
                self.max_drawdown = max(self.max_drawdown, drawdown)
            
            logger.debug(
                "Fill: symbol=%s, strategy=%s, pnl=%.2f, equity=%.2f",
                symbol,
                strategy,
                realized_pnl,
                current_equity,
            )
    
    def update_unrealized_pnl(
        self,
        total_unrealized: float,
        positions: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Update unrealized PnL from current positions.
        
        Args:
            total_unrealized: Total unrealized PnL across all positions
            positions: Optional dict of positions with per-position PnL
        """
        with self._lock:
            self.unrealized_pnl = total_unrealized
            
            # Update equity metrics
            current_equity = self.current_equity
            self.max_equity = max(self.max_equity, current_equity)
            self.min_equity = min(self.min_equity, current_equity)
            
            # Update max drawdown
            if self.max_equity > 0:
                drawdown = (self.max_equity - current_equity) / self.max_equity
                self.max_drawdown = max(self.max_drawdown, drawdown)
            
            logger.debug(
                "Unrealized PnL updated: total=%.2f, equity=%.2f",
                total_unrealized,
                current_equity,
            )
    
    def update_symbol_pnl(self, symbol: str, pnl_delta: float) -> None:
        """
        Update per-symbol PnL.
        
        Args:
            symbol: Trading symbol
            pnl_delta: Change in PnL for this symbol
        """
        with self._lock:
            self.pnl_per_symbol[symbol] += pnl_delta
    
    def update_strategy_pnl(self, strategy: str, pnl_delta: float) -> None:
        """
        Update per-strategy PnL.
        
        Args:
            strategy: Strategy identifier
            pnl_delta: Change in PnL for this strategy
        """
        with self._lock:
            self.pnl_per_strategy[strategy] += pnl_delta
    
    def push_equity_snapshot(
        self,
        min_interval_sec: float = 5.0,
    ) -> bool:
        """
        Push current equity snapshot to the rolling curve.
        
        Args:
            min_interval_sec: Minimum seconds between snapshots (default: 5.0)
            
        Returns:
            True if snapshot was pushed, False if rate-limited
        """
        now = time.time()
        
        with self._lock:
            # Rate limit snapshots
            if now - self._last_snapshot_time < min_interval_sec:
                return False
            
            self._last_snapshot_time = now
            
            # Create snapshot
            snapshot = EquitySnapshot(
                timestamp=datetime.now(timezone.utc).isoformat(),
                equity=self.current_equity,
                realized_pnl=self.realized_pnl,
                unrealized_pnl=self.unrealized_pnl,
            )
            
            # Add to rolling curve
            self.equity_curve.append(asdict(snapshot))
            
            logger.debug(
                "Equity snapshot pushed: equity=%.2f, realized=%.2f, unrealized=%.2f",
                snapshot.equity,
                snapshot.realized_pnl,
                snapshot.unrealized_pnl,
            )
            
            return True
    
    def get_metrics(self) -> RuntimeMetrics:
        """
        Get current runtime metrics snapshot.
        
        Returns:
            RuntimeMetrics instance with current state
        """
        with self._lock:
            return RuntimeMetrics(
                asof=datetime.now(timezone.utc).isoformat(),
                mode=self.mode,
                starting_capital=self.starting_capital,
                current_equity=self.current_equity,
                realized_pnl=self.realized_pnl,
                unrealized_pnl=self.unrealized_pnl,
                daily_pnl=self.daily_pnl,
                max_equity=self.max_equity,
                min_equity=self.min_equity,
                max_drawdown=self.max_drawdown,
                pnl_per_symbol=dict(self.pnl_per_symbol),
                pnl_per_strategy=dict(self.pnl_per_strategy),
                equity_curve=list(self.equity_curve),
            )
    
    def save(self) -> bool:
        """
        Save current metrics to JSON file.
        
        Returns:
            True if save successful, False otherwise
        """
        try:
            metrics = self.get_metrics()
            with self._lock:
                with open(self.metrics_path, "w", encoding="utf-8") as f:
                    json.dump(metrics.to_dict(), f, indent=2)
                logger.debug("Metrics saved to %s", self.metrics_path)
                return True
        except Exception as exc:
            logger.error("Failed to save metrics: %s", exc)
            return False
    
    def reset_daily_pnl(self) -> None:
        """Reset daily PnL counter (call at start of new trading day)."""
        with self._lock:
            self.daily_pnl = 0.0
            logger.info("Daily PnL reset")


def load_runtime_metrics(
    metrics_path: Optional[Path] = None,
    default_mode: str = "paper",
    default_capital: float = 500_000.0,
) -> Dict[str, Any]:
    """
    Safely load runtime metrics from JSON file.
    
    This is a safe loader that never crashes - returns sensible defaults
    if the file doesn't exist or contains invalid data.
    
    Args:
        metrics_path: Path to runtime_metrics.json (defaults to standard location)
        default_mode: Default trading mode if not in file
        default_capital: Default starting capital if not in file
        
    Returns:
        Dict with runtime metrics (never None, always valid structure)
    """
    # Default structure
    default_metrics = {
        "asof": datetime.now(timezone.utc).isoformat(),
        "mode": default_mode,
        "starting_capital": default_capital,
        "current_equity": default_capital,
        "realized_pnl": 0.0,
        "unrealized_pnl": 0.0,
        "daily_pnl": 0.0,
        "max_equity": default_capital,
        "min_equity": default_capital,
        "max_drawdown": 0.0,
        "pnl_per_symbol": {},
        "pnl_per_strategy": {},
        "equity_curve": [],
    }
    
    # Determine path
    if metrics_path is None:
        base_dir = Path(__file__).resolve().parents[1]
        metrics_path = base_dir / "artifacts" / "analytics" / "runtime_metrics.json"
    
    # Check if file exists
    if not metrics_path.exists():
        logger.debug("Metrics file not found: %s, using defaults", metrics_path)
        return default_metrics
    
    # Try to load
    try:
        with open(metrics_path, "r", encoding="utf-8") as f:
            metrics = json.load(f)
        
        # Validate and fill in missing fields
        for key, default_value in default_metrics.items():
            if key not in metrics:
                metrics[key] = default_value
        
        logger.debug("Loaded metrics from %s", metrics_path)
        return metrics
    
    except Exception as exc:
        logger.warning("Failed to load metrics from %s: %s", metrics_path, exc)
        return default_metrics
