"""
Trade Guardian v1 - Pre-execution safety gate

Validates OrderIntent before execution to prevent:
- Stale price issues
- Oversized orders
- Excessive trading velocity
- Slippage anomalies
- PnL-based circuit breakers

CRITICAL: Guardian MUST NEVER throw exceptions. Always catch and allow trade with warning.
Guardian is DISABLED by default unless config.guardian.enabled=true.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class GuardianDecision:
    """Result of guardian validation."""
    allow: bool
    reason: Optional[str] = None


class TradeGuardian:
    """
    Pre-execution safety gate for trade validation.
    
    Performs lightweight checks before orders reach ExecutionEngine:
    - Stale price detection
    - Quantity validation
    - Trade rate limiting
    - Slippage sanity checks
    - PnL-based circuit breakers
    """
    
    def __init__(self, config: Dict[str, Any], state_store: Any, logger_instance: logging.Logger, regime_engine: Optional[Any] = None):
        """
        Initialize TradeGuardian.
        
        Args:
            config: Full application config dict
            state_store: StateStore instance for PnL checks
            logger_instance: Logger instance
            regime_engine: Optional RegimeEngine for regime-based adjustments
        """
        self.logger = logger_instance
        self.state_store = state_store
        self.regime_engine = regime_engine
        
        # Load guardian config or disable if missing
        guardian_config = config.get("guardian", {})
        self.enabled = guardian_config.get("enabled", False)
        
        if not self.enabled:
            self.logger.info("TradeGuardian: DISABLED (enabled=false in config)")
            return
        
        # Load guardian parameters with safe defaults
        self.max_order_per_second = guardian_config.get("max_order_per_second", 5)
        self.max_lot_size = guardian_config.get("max_lot_size", 50)
        self.reject_if_price_stale_secs = guardian_config.get("reject_if_price_stale_secs", 3)
        self.reject_if_slippage_pct = guardian_config.get("reject_if_slippage_pct", 2.0)
        self.max_daily_drawdown_pct = guardian_config.get("max_daily_drawdown_pct", 3.0)
        self.halt_on_pnl_drop_pct = guardian_config.get("halt_on_pnl_drop_pct", 5.0)
        
        # Internal state for rate limiting
        self._order_timestamps: list[float] = []
        
        self.logger.info(
            "TradeGuardian: ENABLED - max_order_per_second=%d, max_lot_size=%d, "
            "reject_if_price_stale_secs=%d, reject_if_slippage_pct=%.2f%%, "
            "max_daily_drawdown_pct=%.2f%%, halt_on_pnl_drop_pct=%.2f%%",
            self.max_order_per_second,
            self.max_lot_size,
            self.reject_if_price_stale_secs,
            self.reject_if_slippage_pct,
            self.max_daily_drawdown_pct,
            self.halt_on_pnl_drop_pct,
        )
        if self.regime_engine:
            self.logger.info("TradeGuardian: RegimeEngine integration enabled")
    
    def validate_pre_trade(
        self,
        intent: Any,
        market_snapshot: Optional[Dict[str, Any]] = None,
    ) -> GuardianDecision:
        """
        Validate an order intent before execution.
        
        Args:
            intent: OrderIntent with symbol, qty, side, price, etc.
            market_snapshot: Optional market data snapshot with latest price, timestamp
            
        Returns:
            GuardianDecision with allow=True/False and optional reason
        """
        # If guardian is disabled, always allow
        if not self.enabled:
            return GuardianDecision(allow=True)
        
        try:
            # Check 1: Quantity validation (max lot size)
            qty = getattr(intent, "qty", 0)
            if qty > self.max_lot_size:
                reason = (
                    f"Order quantity {qty} exceeds max_lot_size {self.max_lot_size}"
                )
                self.logger.warning("[TradeGuardian] BLOCKED: %s", reason)
                return GuardianDecision(allow=False, reason=reason)
            
            # Check 2: Trade rate limiting (orders per second)
            current_time = time.time()
            # Clean old timestamps (older than 1 second)
            self._order_timestamps = [
                ts for ts in self._order_timestamps if current_time - ts < 1.0
            ]
            
            if len(self._order_timestamps) >= self.max_order_per_second:
                reason = (
                    f"Order rate limit exceeded: {len(self._order_timestamps)} "
                    f"orders in last second (max={self.max_order_per_second})"
                )
                self.logger.warning("[TradeGuardian] BLOCKED: %s", reason)
                return GuardianDecision(allow=False, reason=reason)
            
            # Register this order timestamp
            self._order_timestamps.append(current_time)
            
            # Check 3: Stale price detection
            if market_snapshot:
                last_update_ts = market_snapshot.get("timestamp")
                if last_update_ts:
                    try:
                        # Handle various timestamp formats
                        if isinstance(last_update_ts, (int, float)):
                            age_seconds = current_time - last_update_ts
                        else:
                            # Try to parse as ISO timestamp
                            from datetime import datetime
                            dt = datetime.fromisoformat(str(last_update_ts).replace("Z", "+00:00"))
                            age_seconds = current_time - dt.timestamp()
                        
                        if age_seconds > self.reject_if_price_stale_secs:
                            reason = (
                                f"Market data is stale: {age_seconds:.1f}s old "
                                f"(threshold={self.reject_if_price_stale_secs}s)"
                            )
                            self.logger.warning("[TradeGuardian] BLOCKED: %s", reason)
                            return GuardianDecision(allow=False, reason=reason)
                    except Exception as exc:
                        self.logger.debug(
                            "TradeGuardian: Could not parse timestamp: %s", exc
                        )
            
            # Check 4: Slippage sanity check
            intent_price = getattr(intent, "price", None)
            if intent_price and market_snapshot:
                last_price = market_snapshot.get("last_price") or market_snapshot.get("ltp")
                if last_price:
                    slippage_pct = abs(intent_price - last_price) / last_price * 100.0
                    if slippage_pct > self.reject_if_slippage_pct:
                        reason = (
                            f"Excessive slippage: intent price {intent_price:.2f} vs "
                            f"last price {last_price:.2f} ({slippage_pct:.2f}% > "
                            f"{self.reject_if_slippage_pct}%)"
                        )
                        self.logger.warning("[TradeGuardian] BLOCKED: %s", reason)
                        return GuardianDecision(allow=False, reason=reason)
            
            # Check 5: PnL-based halt (drawdown check)
            try:
                state = self.state_store.load_checkpoint()
                if state:
                    equity = state.get("equity", {})
                    realized_pnl = equity.get("realized_pnl", 0.0)
                    paper_capital = equity.get("paper_capital", 100000.0)
                    
                    # Calculate drawdown percentage
                    if paper_capital > 0:
                        drawdown_pct = abs(realized_pnl) / paper_capital * 100.0
                        
                        # Check max daily drawdown
                        if drawdown_pct > self.max_daily_drawdown_pct:
                            reason = (
                                f"Daily drawdown limit exceeded: {drawdown_pct:.2f}% > "
                                f"{self.max_daily_drawdown_pct}%"
                            )
                            self.logger.warning("[TradeGuardian] BLOCKED: %s", reason)
                            return GuardianDecision(allow=False, reason=reason)
                        
                        # Check halt on PnL drop
                        pnl_drop_pct = (realized_pnl / paper_capital) * 100.0
                        if pnl_drop_pct < -self.halt_on_pnl_drop_pct:
                            reason = (
                                f"PnL drop halt triggered: {pnl_drop_pct:.2f}% < "
                                f"-{self.halt_on_pnl_drop_pct}%"
                            )
                            self.logger.warning("[TradeGuardian] BLOCKED: %s", reason)
                            return GuardianDecision(allow=False, reason=reason)
            except Exception as exc:
                self.logger.debug(
                    "TradeGuardian: Could not check PnL-based circuit breakers: %s", exc
                )
            
            # Check 6: Regime-based adjustments (if RegimeEngine available)
            if self.regime_engine:
                try:
                    symbol = getattr(intent, "symbol", None)
                    if symbol:
                        regime = self.regime_engine.snapshot(symbol)
                        
                        # In high volatility, tighten slippage tolerance
                        if regime.volatility == "high":
                            # Already checked slippage above, but can add additional logging
                            self.logger.debug(
                                "[TradeGuardian] High volatility regime for %s, extra caution advised",
                                symbol
                            )
                        
                        # In extreme volatility, we could optionally reject trades
                        # For now, we just log and allow with extra monitoring
                        
                except Exception as exc:
                    self.logger.debug(
                        "TradeGuardian: Could not check regime-based rules: %s", exc
                    )
            
            # All checks passed
            return GuardianDecision(allow=True)
            
        except Exception as exc:
            # CRITICAL: Guardian must never throw exceptions
            # Log error and allow trade to proceed
            self.logger.error(
                "TradeGuardian: Validation failed with exception, allowing trade: %s",
                exc,
                exc_info=True,
            )
            return GuardianDecision(allow=True, reason=f"Guardian exception: {exc}")
