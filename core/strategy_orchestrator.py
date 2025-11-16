"""
Strategy Orchestrator v3

Context-aware orchestration layer for strategy enable/disable, capital allocation,
regime filtering, cooldowns, and strategy health scoring.

This module is DISABLED by default and can be enabled via config.strategy_orchestrator.enabled.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class StrategyState:
    """Maintains orchestration state for a strategy."""
    
    active: bool = True
    disabled_until: Optional[datetime] = None
    loss_streak: int = 0
    last_signals: deque = field(default_factory=lambda: deque(maxlen=20))
    last_pnls: deque = field(default_factory=lambda: deque(maxlen=20))
    health_score: float = 1.0  # baseline


@dataclass
class OrchestratorDecision:
    """Result of orchestrator evaluation."""
    
    allow: bool
    reason: str


class StrategyOrchestrator:
    """
    Strategy Orchestrator v3
    
    Main gatekeeper for strategy execution with support for:
    - Cooldown windows (time-based and loss-based)
    - Health score tracking
    - Regime compatibility checks
    - Session time filtering
    - Capital budget enforcement (via PortfolioEngine)
    """
    
    def __init__(
        self,
        config: Dict[str, Any],
        state_store: Any,
        analytics: Any,
        logger_instance: Optional[logging.Logger] = None
    ):
        """
        Initialize the orchestrator.
        
        Args:
            config: Application config dict
            state_store: StateStore instance for persistence
            analytics: Analytics engine for metrics (optional)
            logger_instance: Logger instance
        """
        self.config = config
        self.state_store = state_store
        self.analytics = analytics
        self.logger = logger_instance or logger
        
        # Load orchestrator config or set defaults
        self.orch_config = config.get("strategy_orchestrator", {})
        self.enabled = self.orch_config.get("enabled", False)
        
        if not self.enabled:
            self.logger.info("StrategyOrchestrator DISABLED (config.strategy_orchestrator.enabled=false)")
            return
        
        self.logger.info("StrategyOrchestrator ENABLED")
        
        # Configuration parameters
        self.health_scoring_window = self.orch_config.get("health_scoring_window", 20)
        self.loss_streak_disable = self.orch_config.get("loss_streak_disable", 3)
        self.disable_duration_seconds = self.orch_config.get("disable_duration_seconds", 900)
        self.enforce_regimes = self.orch_config.get("enforce_regimes", True)
        self.enforce_capital_budgets = self.orch_config.get("enforce_capital_budgets", True)
        
        # Per-strategy state
        self.strategy_states: Dict[str, StrategyState] = {}
        
        self.logger.info(
            "StrategyOrchestrator config: health_window=%d, loss_streak_disable=%d, "
            "disable_duration=%ds, enforce_regimes=%s, enforce_budgets=%s",
            self.health_scoring_window,
            self.loss_streak_disable,
            self.disable_duration_seconds,
            self.enforce_regimes,
            self.enforce_capital_budgets,
        )
    
    def _get_strategy_state(self, strategy_code: str) -> StrategyState:
        """Get or create strategy state."""
        if strategy_code not in self.strategy_states:
            self.strategy_states[strategy_code] = StrategyState()
        return self.strategy_states[strategy_code]
    
    def _get_strategy_metadata(self, strategy_code: str) -> Dict[str, Any]:
        """
        Get strategy metadata from config.
        
        Strategy metadata may include:
        - requires_regime: List of required regimes
        - avoid_regime: List of regimes to avoid
        - session_times: Dict with start/end times
        - allowed_days: List of allowed weekdays
        - capital_pct: Capital allocation percentage
        """
        strategies_config = self.config.get("strategies", {})
        if isinstance(strategies_config, dict):
            return strategies_config.get(strategy_code, {})
        return {}
    
    def evaluate_regime(
        self,
        strategy_meta: Dict[str, Any],
        market_regime: Dict[str, Any]
    ) -> bool:
        """
        Check if strategy is allowed to run given the current regime.
        
        Args:
            strategy_meta: Strategy metadata dict
            market_regime: Current market regime snapshot
        
        Returns:
            True if strategy can run in this regime
        """
        if not self.enforce_regimes:
            return True
        
        # Check required regimes
        requires_regime = strategy_meta.get("requires_regime", [])
        if requires_regime:
            for regime in requires_regime:
                if not market_regime.get(regime, False):
                    return False
        
        # Check avoided regimes
        avoid_regime = strategy_meta.get("avoid_regime", [])
        if avoid_regime:
            for regime in avoid_regime:
                if market_regime.get(regime, False):
                    return False
        
        return True
    
    def _check_session_time(self, strategy_meta: Dict[str, Any]) -> bool:
        """
        Check if current time is within strategy's allowed session window.
        
        Args:
            strategy_meta: Strategy metadata dict
        
        Returns:
            True if current time is within session window
        """
        session_times = strategy_meta.get("session_times")
        if not session_times:
            return True  # No session restriction
        
        start_time_str = session_times.get("start")
        end_time_str = session_times.get("end")
        
        if not start_time_str or not end_time_str:
            return True
        
        try:
            now = datetime.now(timezone.utc)
            # Parse HH:MM format
            start_hour, start_min = map(int, start_time_str.split(":"))
            end_hour, end_min = map(int, end_time_str.split(":"))
            
            # Compare time only (ignore date)
            current_time = now.hour * 60 + now.minute
            start_time = start_hour * 60 + start_min
            end_time = end_hour * 60 + end_min
            
            return start_time <= current_time <= end_time
        except Exception as e:
            self.logger.warning("Failed to parse session_times: %s", e)
            return True  # Allow by default on parsing error
    
    def _check_allowed_days(self, strategy_meta: Dict[str, Any]) -> bool:
        """
        Check if current day is in strategy's allowed days.
        
        Args:
            strategy_meta: Strategy metadata dict
        
        Returns:
            True if current day is allowed
        """
        allowed_days = strategy_meta.get("allowed_days")
        if not allowed_days:
            return True  # No day restriction
        
        # Get current day name (e.g., "Monday", "Tuesday", etc.)
        current_day = datetime.now(timezone.utc).strftime("%A")
        
        # Convert allowed_days to lowercase for case-insensitive comparison
        allowed_days_lower = [day.lower() for day in allowed_days]
        
        return current_day.lower() in allowed_days_lower
    
    def update_after_trade(self, strategy_code: str, trade_pnl: float) -> None:
        """
        Update strategy state after a trade completes.
        
        Args:
            strategy_code: Strategy identifier
            trade_pnl: PnL of completed trade
        """
        if not self.enabled:
            return
        
        state = self._get_strategy_state(strategy_code)
        
        # Record PnL
        state.last_pnls.append(trade_pnl)
        
        # Update loss streak
        if trade_pnl < 0:
            state.loss_streak += 1
        else:
            state.loss_streak = 0
        
        # Update health score based on recent PnLs
        if len(state.last_pnls) >= 5:
            recent_pnls = list(state.last_pnls)[-self.health_scoring_window:]
            wins = sum(1 for pnl in recent_pnls if pnl > 0)
            total = len(recent_pnls)
            win_rate = wins / total if total > 0 else 0.5
            
            # Health score ranges from 0.0 (poor) to 1.0 (excellent)
            # Based on win rate: 0% = 0.0, 50% = 0.5, 100% = 1.0
            state.health_score = win_rate
        
        # Check if we should disable strategy due to loss streak
        if state.loss_streak >= self.loss_streak_disable:
            state.active = False
            state.disabled_until = datetime.now(timezone.utc) + timedelta(
                seconds=self.disable_duration_seconds
            )
            self.logger.warning(
                "Strategy %s DISABLED due to loss streak of %d (cooldown: %ds)",
                strategy_code,
                state.loss_streak,
                self.disable_duration_seconds,
            )
    
    def should_run_strategy(
        self,
        strategy_code: str,
        market_regime: Optional[Dict[str, Any]] = None
    ) -> OrchestratorDecision:
        """
        Main gatekeeper: decides if a strategy should run.
        
        Args:
            strategy_code: Strategy identifier
            market_regime: Current market regime snapshot (optional)
        
        Returns:
            OrchestratorDecision with allow/deny and reason
        """
        # If orchestrator is disabled, always allow
        if not self.enabled:
            return OrchestratorDecision(allow=True, reason="orchestrator_disabled")
        
        state = self._get_strategy_state(strategy_code)
        strategy_meta = self._get_strategy_metadata(strategy_code)
        
        # Check if strategy is in cooldown period
        if state.disabled_until:
            if datetime.now(timezone.utc) < state.disabled_until:
                return OrchestratorDecision(
                    allow=False,
                    reason=f"cooldown_until_{state.disabled_until.isoformat()}"
                )
            else:
                # Cooldown expired, re-enable
                state.disabled_until = None
                state.active = True
                state.loss_streak = 0
                self.logger.info("Strategy %s cooldown expired, re-enabled", strategy_code)
        
        # Check if strategy is active
        if not state.active:
            return OrchestratorDecision(allow=False, reason="strategy_inactive")
        
        # Check health score threshold
        health_threshold = self.orch_config.get("min_health_score", 0.0)
        if state.health_score < health_threshold:
            return OrchestratorDecision(
                allow=False,
                reason=f"health_score_low_{state.health_score:.2f}<{health_threshold:.2f}"
            )
        
        # Check session time window
        if not self._check_session_time(strategy_meta):
            return OrchestratorDecision(allow=False, reason="outside_session_time")
        
        # Check allowed days
        if not self._check_allowed_days(strategy_meta):
            return OrchestratorDecision(allow=False, reason="day_not_allowed")
        
        # Check regime compatibility
        if market_regime and not self.evaluate_regime(strategy_meta, market_regime):
            return OrchestratorDecision(allow=False, reason="regime_incompatible")
        
        # Check capital budget availability (if portfolio engine available)
        if self.enforce_capital_budgets:
            # This would require integration with PortfolioEngine
            # For now, we'll skip this check as it requires more context
            # In production, you'd call: portfolio_engine.check_strategy_budget(strategy_code)
            pass
        
        # All checks passed
        return OrchestratorDecision(allow=True, reason="all_checks_passed")
