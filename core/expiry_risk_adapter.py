"""
Expiry Risk Adapter

Adjusts risk parameters based on expiry timing to reduce exposure during
volatile expiry periods, particularly on expiry day and in the final hour.

Key Features:
- Scales down risk on expiry days (default 0.8x, last hour 0.6x)
- Scales down risk on expiry week but not expiry day (default 0.9x)
- Blocks new option entries after configured time on expiry day (default 15:00 IST)
- Provides structured reasons for all risk decisions
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from core.expiry_calendar import get_session_time_ist, is_expiry_day, is_expiry_week, get_time_to_expiry_minutes

logger = logging.getLogger(__name__)


@dataclass
class ExpiryRiskConfig:
    """Configuration for expiry-aware risk adjustments."""
    
    enabled: bool = True
    
    # Risk scale multipliers
    expiry_day_risk_scale: float = 0.8
    expiry_last_hour_risk_scale: float = 0.6
    expiry_week_risk_scale: float = 0.9
    
    # Time-based blocks
    block_new_option_entries_after_ist: str = "15:00"  # IST time string "HH:MM"
    expiry_day_last_hour_threshold_minutes: int = 60  # Minutes before close for "last hour"
    
    @classmethod
    def from_config(cls, cfg: Dict[str, Any]) -> ExpiryRiskConfig:
        """
        Load ExpiryRiskConfig from configuration dictionary.
        
        Args:
            cfg: Configuration dict with expiry_risk section
            
        Returns:
            ExpiryRiskConfig instance
        """
        expiry_risk_section = cfg.get("expiry_risk", {})
        
        return cls(
            enabled=expiry_risk_section.get("enabled", True),
            expiry_day_risk_scale=float(expiry_risk_section.get("expiry_day_risk_scale", 0.8)),
            expiry_last_hour_risk_scale=float(expiry_risk_section.get("expiry_last_hour_risk_scale", 0.6)),
            expiry_week_risk_scale=float(expiry_risk_section.get("expiry_week_risk_scale", 0.9)),
            block_new_option_entries_after_ist=expiry_risk_section.get("block_new_option_entries_after_ist", "15:00"),
            expiry_day_last_hour_threshold_minutes=int(expiry_risk_section.get("expiry_day_last_hour_threshold_minutes", 60)),
        )


@dataclass
class ExpiryRiskDecision:
    """Decision from expiry risk adapter."""
    
    risk_scale: float = 1.0  # Multiplier for risk (1.0 = no change)
    allow_new_entry: bool = True  # Whether new entries are allowed
    reason: str = ""  # Reason for the decision
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "risk_scale": self.risk_scale,
            "allow_new_entry": self.allow_new_entry,
            "reason": self.reason,
        }


class ExpiryRiskAdapter:
    """
    Adapter for adjusting risk parameters based on expiry timing.
    
    This adapter is designed to be called before placing new orders to ensure
    appropriate risk management during expiry periods.
    """
    
    def __init__(self, config: ExpiryRiskConfig):
        """
        Initialize the expiry risk adapter.
        
        Args:
            config: ExpiryRiskConfig instance
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
    
    def _parse_time_ist(self, time_str: str) -> tuple[int, int]:
        """
        Parse IST time string to (hour, minute).
        
        Args:
            time_str: Time string in "HH:MM" format
            
        Returns:
            Tuple of (hour, minute)
        """
        try:
            parts = time_str.split(":")
            return int(parts[0]), int(parts[1])
        except (ValueError, IndexError) as exc:
            self.logger.warning("Failed to parse time string '%s': %s", time_str, exc)
            return 15, 0  # Default to 15:00
    
    def evaluate(
        self,
        symbol: str,
        dt: datetime | None = None,
        is_option: bool = False,
        is_new_entry: bool = True,
    ) -> ExpiryRiskDecision:
        """
        Evaluate risk adjustments for a trading decision.
        
        Args:
            symbol: Underlying symbol (NIFTY, BANKNIFTY, FINNIFTY)
            dt: Current datetime (default: now in IST)
            is_option: Whether this is an options trade
            is_new_entry: Whether this is a new entry (vs. exit)
            
        Returns:
            ExpiryRiskDecision with risk_scale, allow_new_entry, and reason
        """
        # If disabled, always return default (no adjustment)
        if not self.config.enabled:
            return ExpiryRiskDecision(
                risk_scale=1.0,
                allow_new_entry=True,
                reason="expiry_risk_disabled"
            )
        
        # Exits are always allowed regardless of expiry timing
        if not is_new_entry:
            return ExpiryRiskDecision(
                risk_scale=1.0,
                allow_new_entry=True,
                reason="exit_always_allowed"
            )
        
        try:
            # Check expiry status
            is_exp_day = is_expiry_day(symbol, dt)
            is_exp_week = is_expiry_week(symbol, dt)
            session_time = get_session_time_ist(dt)
            time_to_exp = get_time_to_expiry_minutes(symbol, dt)
            
            # Expiry day logic
            if is_exp_day:
                # Check if we're in the last hour
                is_last_hour = (
                    time_to_exp is not None 
                    and time_to_exp <= self.config.expiry_day_last_hour_threshold_minutes
                )
                
                # Block new option entries after configured time
                if is_option:
                    block_hour, block_minute = self._parse_time_ist(self.config.block_new_option_entries_after_ist)
                    session_parts = session_time.split(":")
                    current_hour = int(session_parts[0])
                    current_minute = int(session_parts[1])
                    
                    # Compare times
                    current_time_minutes = current_hour * 60 + current_minute
                    block_time_minutes = block_hour * 60 + block_minute
                    
                    if current_time_minutes >= block_time_minutes:
                        return ExpiryRiskDecision(
                            risk_scale=0.0,
                            allow_new_entry=False,
                            reason=f"expiry_day_block_new_option_entries_after_{self.config.block_new_option_entries_after_ist}"
                        )
                
                # Apply appropriate risk scale
                if is_last_hour:
                    return ExpiryRiskDecision(
                        risk_scale=self.config.expiry_last_hour_risk_scale,
                        allow_new_entry=True,
                        reason=f"expiry_day_last_hour_risk_scale_{self.config.expiry_last_hour_risk_scale}"
                    )
                else:
                    return ExpiryRiskDecision(
                        risk_scale=self.config.expiry_day_risk_scale,
                        allow_new_entry=True,
                        reason=f"expiry_day_risk_scale_{self.config.expiry_day_risk_scale}"
                    )
            
            # Expiry week (but not expiry day) logic
            if is_exp_week:
                return ExpiryRiskDecision(
                    risk_scale=self.config.expiry_week_risk_scale,
                    allow_new_entry=True,
                    reason=f"expiry_week_risk_scale_{self.config.expiry_week_risk_scale}"
                )
            
            # No expiry-related adjustments
            return ExpiryRiskDecision(
                risk_scale=1.0,
                allow_new_entry=True,
                reason="no_expiry_adjustment"
            )
            
        except Exception as exc:
            self.logger.warning("Expiry risk evaluation failed for %s: %s. Using safe defaults.", symbol, exc)
            # On error, use safe defaults (no scaling, allow trades)
            return ExpiryRiskDecision(
                risk_scale=1.0,
                allow_new_entry=True,
                reason=f"expiry_risk_error_{type(exc).__name__}"
            )
    
    def log_decision(self, symbol: str, decision: ExpiryRiskDecision) -> None:
        """
        Log an expiry risk decision.
        
        Args:
            symbol: Symbol the decision applies to
            decision: ExpiryRiskDecision instance
        """
        if decision.risk_scale != 1.0 or not decision.allow_new_entry:
            self.logger.info(
                "Expiry risk adjustment for %s: risk_scale=%.2f, allow_new_entry=%s, reason=%s",
                symbol, decision.risk_scale, decision.allow_new_entry, decision.reason
            )


def create_expiry_risk_adapter_from_config(cfg: Dict[str, Any]) -> ExpiryRiskAdapter:
    """
    Create an ExpiryRiskAdapter from configuration.
    
    Args:
        cfg: Full configuration dictionary
        
    Returns:
        ExpiryRiskAdapter instance
    """
    risk_config = ExpiryRiskConfig.from_config(cfg)
    return ExpiryRiskAdapter(risk_config)
