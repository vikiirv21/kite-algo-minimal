"""
Paper Account Manager for reset rule based on daily PnL performance.

This module manages paper trading account lifecycle, including:
- Reading daily metrics from analytics artifacts
- Determining if account should be reset based on drawdown thresholds
- Resetting paper account state to configured starting capital
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class PaperAccountManager:
    """
    Manages paper trading account lifecycle and reset rules.
    
    Reads metrics from artifacts/analytics/ to determine if the account
    should be reset based on yesterday's performance vs. max_drawdown_reset.
    """
    
    def __init__(
        self,
        artifacts_dir: Path,
        starting_capital: float,
        max_drawdown_reset: float,
    ):
        """
        Initialize the PaperAccountManager.
        
        Args:
            artifacts_dir: Path to artifacts directory containing analytics/
            starting_capital: Starting capital for paper account (e.g., 500000)
            max_drawdown_reset: Max drawdown threshold for reset (e.g., 50000)
        """
        self.artifacts_dir = Path(artifacts_dir)
        self.analytics_dir = self.artifacts_dir / "analytics"
        self.starting_capital = float(starting_capital)
        self.max_drawdown_reset = float(max_drawdown_reset)
        
        # Ensure analytics directory exists
        self.analytics_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(
            "PaperAccountManager initialized: starting_capital=%.2f, max_drawdown_reset=%.2f, analytics_dir=%s",
            self.starting_capital,
            self.max_drawdown_reset,
            self.analytics_dir,
        )
    
    def should_reset_for_today(self, check_date: Optional[date] = None) -> bool:
        """
        Determine if the paper account should be reset for today.
        
        Checks yesterday's overall.net_pnl from metrics files.
        If net_pnl <= -max_drawdown_reset, returns True to trigger reset.
        
        Args:
            check_date: Date to check for (default: today)
        
        Returns:
            True if account should be reset, False otherwise
        """
        if check_date is None:
            check_date = date.today()
        
        # Get yesterday's date
        yesterday = check_date - timedelta(days=1)
        
        # Try to load yesterday's metrics
        metrics = self._load_metrics_for_date(yesterday)
        
        if metrics is None:
            logger.info("No metrics found for %s, no reset needed", yesterday.isoformat())
            return False
        
        # Extract net PnL from metrics
        overall = metrics.get("overall", {})
        net_pnl = float(overall.get("net_pnl", 0.0))
        
        # Check if loss exceeds threshold
        if net_pnl <= -self.max_drawdown_reset:
            logger.warning(
                "Reset threshold exceeded: net_pnl=%.2f <= -%.2f (max_drawdown_reset)",
                net_pnl,
                self.max_drawdown_reset,
            )
            return True
        
        logger.info(
            "No reset needed: net_pnl=%.2f > -%.2f (max_drawdown_reset)",
            net_pnl,
            self.max_drawdown_reset,
        )
        return False
    
    def _load_metrics_for_date(self, target_date: date) -> Optional[Dict[str, Any]]:
        """
        Load metrics for a specific date.
        
        Tries multiple file patterns:
        1. YYYY-MM-DD-metrics.json
        2. runtime_metrics.json (if from today, check asof timestamp)
        
        Args:
            target_date: Date to load metrics for
        
        Returns:
            Metrics dict or None if not found
        """
        # Try date-specific metrics file first
        date_metrics_path = self.analytics_dir / f"{target_date.isoformat()}-metrics.json"
        if date_metrics_path.exists():
            try:
                with date_metrics_path.open("r", encoding="utf-8") as f:
                    metrics = json.load(f)
                logger.info("Loaded metrics from %s", date_metrics_path)
                return metrics
            except Exception as exc:
                logger.warning("Failed to load metrics from %s: %s", date_metrics_path, exc)
        
        # Try runtime_metrics.json if target is today or yesterday
        runtime_metrics_path = self.analytics_dir / "runtime_metrics.json"
        if runtime_metrics_path.exists():
            try:
                with runtime_metrics_path.open("r", encoding="utf-8") as f:
                    metrics = json.load(f)
                
                # Check if metrics are from target date
                asof = metrics.get("asof")
                if asof:
                    try:
                        asof_dt = datetime.fromisoformat(asof.replace("Z", "+00:00"))
                        asof_date = asof_dt.date()
                        if asof_date == target_date:
                            logger.info("Loaded metrics from runtime_metrics.json (asof=%s)", asof)
                            return metrics
                    except Exception:
                        pass
            except Exception as exc:
                logger.warning("Failed to load runtime_metrics.json: %s", exc)
        
        logger.debug("No metrics found for %s", target_date.isoformat())
        return None
    
    def reset_paper_account(
        self,
        checkpoint_path: Path,
        reason: str = "drawdown_threshold",
    ) -> None:
        """
        Reset the paper account to starting capital.
        
        This method:
        1. Resets equity to starting_capital
        2. Clears all positions
        3. Resets realized/unrealized PnL to zero
        4. Archives old checkpoint (optional)
        
        Args:
            checkpoint_path: Path to paper state checkpoint file
            reason: Reason for reset (for logging)
        """
        logger.warning(
            "Resetting paper account: reason=%s, starting_capital=%.2f",
            reason,
            self.starting_capital,
        )
        
        # Archive old checkpoint if it exists
        if checkpoint_path.exists():
            archive_path = checkpoint_path.with_suffix(
                f".{datetime.now().strftime('%Y%m%d_%H%M%S')}.archived.json"
            )
            try:
                import shutil
                shutil.copy2(checkpoint_path, archive_path)
                logger.info("Archived old checkpoint to %s", archive_path)
            except Exception as exc:
                logger.warning("Failed to archive checkpoint: %s", exc)
        
        # Create fresh checkpoint state
        reset_state = {
            "timestamp": datetime.now().isoformat(),
            "mode": "paper",
            "reset_reason": reason,
            "equity": {
                "starting_capital": self.starting_capital,
                "current_equity": self.starting_capital,
                "realized_pnl": 0.0,
                "unrealized_pnl": 0.0,
                "paper_capital": self.starting_capital,
                "total_notional": 0.0,
                "free_notional": self.starting_capital,
                "max_drawdown": 0.0,
                "max_equity": self.starting_capital,
                "min_equity": self.starting_capital,
            },
            "pnl": {
                "day_pnl": 0.0,
                "realized": 0.0,
                "unrealized": 0.0,
            },
            "positions": [],
            "broker": {
                "positions": [],
                "cash": self.starting_capital,
            },
            "summary": {
                "date": date.today().isoformat(),
                "realized_pnl": 0.0,
                "num_trades": 0,
                "win_trades": 0,
                "loss_trades": 0,
                "win_rate": 0.0,
                "largest_win": 0.0,
                "largest_loss": 0.0,
                "avg_r": 0.0,
            },
        }
        
        # Write reset state to checkpoint
        try:
            with checkpoint_path.open("w", encoding="utf-8") as f:
                json.dump(reset_state, f, indent=2, default=str)
            logger.info("Paper account reset completed: checkpoint=%s", checkpoint_path)
        except Exception as exc:
            logger.error("Failed to write reset checkpoint: %s", exc, exc_info=True)
            raise
    
    def clear_stale_checkpoints(self, checkpoints_dir: Path, keep_days: int = 7) -> None:
        """
        Archive or clear stale checkpoints older than keep_days.
        
        Args:
            checkpoints_dir: Directory containing checkpoint files
            keep_days: Number of days to keep checkpoints
        """
        if not checkpoints_dir.exists():
            return
        
        cutoff_date = datetime.now() - timedelta(days=keep_days)
        
        for checkpoint_file in checkpoints_dir.glob("*.json"):
            # Skip archived files
            if ".archived." in checkpoint_file.name:
                continue
            
            try:
                mtime = datetime.fromtimestamp(checkpoint_file.stat().st_mtime)
                if mtime < cutoff_date:
                    archive_name = f"{checkpoint_file.stem}.{mtime.strftime('%Y%m%d')}.archived.json"
                    archive_path = checkpoint_file.parent / archive_name
                    checkpoint_file.rename(archive_path)
                    logger.info("Archived stale checkpoint: %s -> %s", checkpoint_file.name, archive_name)
            except Exception as exc:
                logger.warning("Failed to archive checkpoint %s: %s", checkpoint_file.name, exc)
