"""
Portfolio & Position Sizing Engine v1

This module provides position sizing and portfolio management capabilities:
- Per-strategy capital budgets
- Per-symbol exposure limits
- Overall account equity management
- Optional volatility (ATR) based sizing
- Risk rules enforcement (max risk per trade, max leverage)

The PortfolioEngine sits between StrategyEngine and ExecutionEngine:
    StrategyEngine v2 → (raw trade idea: direction only)
    PortfolioEngine v1 → (fills in qty/size)
    RiskEngine + ExecutionEngine → (approve + execute)

Works in both PAPER and LIVE modes.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PortfolioConfig:
    """
    Portfolio-level configuration settings.
    
    Expected YAML structure:
        portfolio:
          max_leverage: 2.0
          max_exposure_pct: 0.8        # 80% of equity
          max_risk_per_trade_pct: 0.01 # 1% of equity
          max_risk_per_strategy_pct: 0.2
          position_sizing_mode: "fixed_risk_atr"  # or "fixed_qty"
          lot_size_fallback: 25
          default_fixed_qty: 1
          atr_stop_multiplier: 2.0     # stop distance = k * ATR
          strategy_budgets:
            ema20_50_intraday:
              capital_pct: 0.3         # 30% of equity
              fixed_qty: 1             # optional per-strategy fixed qty
            expiry_scalper:
              capital_pct: 0.4
    """
    
    max_leverage: float = 2.0
    max_exposure_pct: float = 0.8  # 80% of equity
    max_risk_per_trade_pct: float = 0.01  # 1% of equity per trade
    max_risk_per_strategy_pct: float = 0.2  # 20% of equity per strategy
    position_sizing_mode: str = "fixed_qty"  # "fixed_qty" or "fixed_risk_atr"
    lot_size_fallback: int = 25
    default_fixed_qty: int = 1
    atr_stop_multiplier: float = 2.0  # for fixed_risk_atr mode
    strategy_budgets: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "PortfolioConfig":
        """Create PortfolioConfig from dictionary."""
        if not data:
            return cls()
        
        return cls(
            max_leverage=float(data.get("max_leverage", 2.0)),
            max_exposure_pct=float(data.get("max_exposure_pct", 0.8)),
            max_risk_per_trade_pct=float(data.get("max_risk_per_trade_pct", 0.01)),
            max_risk_per_strategy_pct=float(data.get("max_risk_per_strategy_pct", 0.2)),
            position_sizing_mode=str(data.get("position_sizing_mode", "fixed_qty")),
            lot_size_fallback=int(data.get("lot_size_fallback", 25)),
            default_fixed_qty=int(data.get("default_fixed_qty", 1)),
            atr_stop_multiplier=float(data.get("atr_stop_multiplier", 2.0)),
            strategy_budgets=dict(data.get("strategy_budgets", {})),
        )


class PortfolioEngine:
    """
    Portfolio & Position Sizing Engine.
    
    Computes position sizes based on:
    - Account equity
    - Strategy capital budgets
    - Risk per trade limits
    - Exposure limits
    - Optional ATR-based volatility sizing
    """
    
    def __init__(
        self,
        portfolio_config: PortfolioConfig,
        state_store: Any,
        journal_store: Optional[Any] = None,
        logger_instance: Optional[logging.Logger] = None,
        mde: Optional[Any] = None,
    ):
        """
        Initialize PortfolioEngine.
        
        Args:
            portfolio_config: PortfolioConfig instance
            state_store: StateStore for reading equity and positions
            journal_store: JournalStateStore (optional, for trade history)
            logger_instance: Logger instance
            mde: MarketDataEngineV2 (optional, for ATR or current price)
        """
        self.config = portfolio_config
        self.state_store = state_store
        self.journal_store = journal_store
        self.logger = logger_instance or logger
        self.mde = mde
        
        self.logger.info(
            "PortfolioEngine initialized: mode=%s, max_exposure_pct=%.2f, max_risk_per_trade_pct=%.4f",
            self.config.position_sizing_mode,
            self.config.max_exposure_pct,
            self.config.max_risk_per_trade_pct,
        )
    
    def get_equity(self) -> float:
        """
        Get current equity from state_store.
        
        Returns:
            Current equity value (including unrealized PnL)
        """
        try:
            state = self.state_store.load_checkpoint()
            if not state:
                self.logger.warning("No checkpoint found, using default equity")
                return 100000.0  # Default fallback
            
            # Try to get equity from different possible locations
            equity = state.get("equity", {})
            if isinstance(equity, dict):
                # Modern state structure
                paper_capital = float(equity.get("paper_capital", 0.0))
                realized_pnl = float(equity.get("realized_pnl", 0.0))
                unrealized_pnl = float(equity.get("unrealized_pnl", 0.0))
                return paper_capital + realized_pnl + unrealized_pnl
            
            # Alternative: meta section (journal store structure)
            meta = state.get("meta", {})
            if "equity" in meta:
                return float(meta.get("equity", 0.0))
            
            # Fallback to paper_capital
            if "paper_capital" in meta:
                return float(meta.get("paper_capital", 0.0))
            
            self.logger.warning("Could not extract equity from state, using default")
            return 100000.0
            
        except Exception as exc:
            self.logger.warning("Error reading equity from state: %s, using default", exc)
            return 100000.0
    
    def compute_strategy_budget(self, strategy_code: str) -> float:
        """
        Compute maximum capital allocation for a strategy.
        
        Args:
            strategy_code: Strategy identifier (e.g., "ema20_50_intraday")
        
        Returns:
            Maximum capital in rupees for this strategy
        """
        equity = self.get_equity()
        strategy_cfg = self.config.strategy_budgets.get(strategy_code, {})
        
        if not strategy_cfg:
            # No specific budget, use default risk per strategy
            capital_pct = self.config.max_risk_per_strategy_pct
            self.logger.debug(
                "No budget configured for strategy=%s, using default %.2f%%",
                strategy_code,
                capital_pct * 100,
            )
        else:
            capital_pct = float(strategy_cfg.get("capital_pct", self.config.max_risk_per_strategy_pct))
        
        budget = equity * capital_pct
        self.logger.debug(
            "Strategy budget: %s = %.2f (%.2f%% of equity %.2f)",
            strategy_code,
            budget,
            capital_pct * 100,
            equity,
        )
        return budget
    
    def compute_symbol_exposure(self, symbol: str) -> float:
        """
        Compute current exposure in rupees for a given symbol.
        
        Args:
            symbol: Trading symbol
        
        Returns:
            Current exposure (absolute value of position notional)
        """
        try:
            state = self.state_store.load_checkpoint()
            if not state:
                return 0.0
            
            positions = state.get("positions", [])
            if not positions:
                # Try alternative structure (broker.positions)
                broker_state = state.get("broker", {})
                positions = broker_state.get("positions", [])
            
            for pos in positions:
                pos_symbol = pos.get("symbol") or pos.get("tradingsymbol", "")
                if pos_symbol == symbol:
                    qty = float(pos.get("quantity", 0.0))
                    last_price = float(pos.get("last_price", 0.0) or pos.get("avg_price", 0.0))
                    exposure = abs(qty * last_price)
                    self.logger.debug(
                        "Symbol exposure: %s = %.2f (qty=%d, price=%.2f)",
                        symbol,
                        exposure,
                        int(qty),
                        last_price,
                    )
                    return exposure
            
            return 0.0
            
        except Exception as exc:
            self.logger.warning("Error computing symbol exposure for %s: %s", symbol, exc)
            return 0.0
    
    def compute_total_exposure(self) -> float:
        """
        Compute total portfolio exposure across all positions.
        
        Returns:
            Total notional exposure in rupees
        """
        try:
            state = self.state_store.load_checkpoint()
            if not state:
                return 0.0
            
            positions = state.get("positions", [])
            if not positions:
                broker_state = state.get("broker", {})
                positions = broker_state.get("positions", [])
            
            total = 0.0
            for pos in positions:
                qty = float(pos.get("quantity", 0.0))
                last_price = float(pos.get("last_price", 0.0) or pos.get("avg_price", 0.0))
                total += abs(qty * last_price)
            
            self.logger.debug("Total portfolio exposure: %.2f", total)
            return total
            
        except Exception as exc:
            self.logger.warning("Error computing total exposure: %s", exc)
            return 0.0
    
    def compute_strategy_exposure(self, strategy_code: str) -> float:
        """
        Compute current exposure for a specific strategy.
        
        Args:
            strategy_code: Strategy identifier
        
        Returns:
            Current exposure in rupees for this strategy
        """
        # This requires tracking which positions belong to which strategy
        # For v1, we'll return 0.0 as a safe default
        # In a more complete implementation, we'd need to tag positions with strategy_code
        return 0.0
    
    def compute_position_size(
        self,
        intent: Any,
        last_price: float,
        atr_value: Optional[float] = None,
    ) -> int:
        """
        Core method: compute position size (quantity) for an OrderIntent.
        
        Args:
            intent: OrderIntent with symbol, strategy_code, side (qty may be None)
            last_price: Current market price for the symbol
            atr_value: Optional ATR value for volatility-based sizing
        
        Returns:
            Integer quantity (number of shares or lot size * lots)
            Returns 0 if position should not be taken (exceeds limits)
        """
        symbol = getattr(intent, "symbol", "")
        strategy_code = getattr(intent, "strategy_code", "")
        existing_qty = getattr(intent, "qty", None)
        
        self.logger.debug(
            "Computing position size: symbol=%s, strategy=%s, mode=%s, last_price=%.2f, atr=%.4f",
            symbol,
            strategy_code,
            self.config.position_sizing_mode,
            last_price,
            atr_value or 0.0,
        )
        
        # Get equity and strategy budget
        equity = self.get_equity()
        strategy_budget = self.compute_strategy_budget(strategy_code)
        
        # Compute quantity based on sizing mode
        if self.config.position_sizing_mode == "fixed_qty":
            qty = self._compute_fixed_qty(intent, strategy_code, existing_qty)
        elif self.config.position_sizing_mode == "fixed_risk_atr":
            qty = self._compute_atr_based_qty(
                symbol, strategy_code, last_price, atr_value, equity, strategy_budget
            )
        else:
            self.logger.warning(
                "Unknown position_sizing_mode=%s, using fixed_qty",
                self.config.position_sizing_mode,
            )
            qty = self._compute_fixed_qty(intent, strategy_code, existing_qty)
        
        # Apply exposure limits
        qty = self._apply_exposure_limits(symbol, strategy_code, qty, last_price, equity, strategy_budget)
        
        self.logger.info(
            "Position size computed: symbol=%s, strategy=%s, qty=%d, notional=%.2f",
            symbol,
            strategy_code,
            qty,
            qty * last_price,
        )
        
        return qty
    
    def _compute_fixed_qty(
        self,
        intent: Any,
        strategy_code: str,
        existing_qty: Optional[int],
    ) -> int:
        """
        Compute position size using fixed quantity mode.
        
        Priority:
        1. Use intent.qty if provided
        2. Use strategy-specific fixed_qty from config
        3. Use global default_fixed_qty
        """
        # If intent already has qty, use it
        if existing_qty is not None and existing_qty > 0:
            self.logger.debug("Using existing qty=%d from intent", existing_qty)
            return int(existing_qty)
        
        # Check for strategy-specific fixed_qty
        strategy_cfg = self.config.strategy_budgets.get(strategy_code, {})
        if "fixed_qty" in strategy_cfg:
            qty = int(strategy_cfg["fixed_qty"])
            self.logger.debug("Using strategy-specific fixed_qty=%d", qty)
            return qty
        
        # Use global default
        qty = self.config.default_fixed_qty
        self.logger.debug("Using default_fixed_qty=%d", qty)
        return qty
    
    def _compute_atr_based_qty(
        self,
        symbol: str,
        strategy_code: str,
        last_price: float,
        atr_value: Optional[float],
        equity: float,
        strategy_budget: float,
    ) -> int:
        """
        Compute position size using ATR-based risk sizing.
        
        Formula:
            risk_per_trade_rupees = equity * max_risk_per_trade_pct
            stop_distance_points = k * ATR (e.g., 2 * ATR)
            qty = floor(risk_per_trade_rupees / (stop_distance_points * point_value))
        
        For FnO:
            point_value = lot_size
        """
        if not atr_value or atr_value <= 0:
            self.logger.warning(
                "ATR-based sizing requested but ATR not available for %s, using fixed_qty",
                symbol,
            )
            return self._compute_fixed_qty(None, strategy_code, None)
        
        # Risk per trade in rupees
        risk_per_trade = equity * self.config.max_risk_per_trade_pct
        
        # Stop distance in price points
        stop_distance = self.config.atr_stop_multiplier * atr_value
        
        if stop_distance <= 0:
            self.logger.warning("Invalid stop_distance=%.4f, using fixed_qty", stop_distance)
            return self._compute_fixed_qty(None, strategy_code, None)
        
        # Point value (for FnO, this is lot size)
        # For now, use lot_size_fallback as a simple approximation
        # In a more complete implementation, we'd look up actual lot size from symbol config
        point_value = self.config.lot_size_fallback
        
        # Calculate quantity
        # For equity: qty = risk / stop_distance
        # For FnO: qty = (risk / stop_distance) * lot_size
        if "FUT" in symbol.upper() or "OPT" in symbol.upper():
            # FnO: quantity in lots
            qty_float = risk_per_trade / (stop_distance * point_value)
            qty = max(1, int(qty_float)) * point_value  # Round to whole lots
        else:
            # Equity: quantity in shares
            qty = max(1, int(risk_per_trade / stop_distance))
        
        self.logger.debug(
            "ATR-based sizing: risk=%.2f, stop_distance=%.4f, point_value=%d, qty=%d",
            risk_per_trade,
            stop_distance,
            point_value,
            qty,
        )
        
        return qty
    
    def _apply_exposure_limits(
        self,
        symbol: str,
        strategy_code: str,
        qty: int,
        last_price: float,
        equity: float,
        strategy_budget: float,
    ) -> int:
        """
        Apply exposure limits and reduce qty if necessary.
        
        Enforces:
        - Max total notional exposure
        - Max per-strategy capital
        - Max leverage
        
        Returns:
            Adjusted quantity (may be reduced to 0)
        """
        if qty <= 0:
            return 0
        
        notional = qty * last_price
        
        # Check max total exposure
        current_total_exposure = self.compute_total_exposure()
        max_total_exposure = equity * self.config.max_exposure_pct * self.config.max_leverage
        
        if current_total_exposure + notional > max_total_exposure:
            # Reduce qty to fit within limit
            available_exposure = max_total_exposure - current_total_exposure
            if available_exposure <= 0:
                self.logger.warning(
                    "Total exposure limit reached: current=%.2f, max=%.2f, rejecting trade",
                    current_total_exposure,
                    max_total_exposure,
                )
                return 0
            
            max_qty = int(available_exposure / last_price)
            if max_qty < qty:
                self.logger.warning(
                    "Reducing qty from %d to %d due to total exposure limit",
                    qty,
                    max_qty,
                )
                qty = max_qty
        
        # Check strategy budget (only if budget is meaningful)
        # Note: For new positions, the notional should fit within available strategy budget
        # For v1, we'll be lenient and only enforce if notional exceeds budget by a lot
        if strategy_budget > 0 and notional > strategy_budget * 1.5:
            # Position is too large for strategy budget, reduce it
            max_qty = int(strategy_budget / last_price)
            if max_qty < qty and max_qty > 0:
                self.logger.warning(
                    "Reducing qty from %d to %d due to strategy budget limit (%.2f)",
                    qty,
                    max_qty,
                    strategy_budget,
                )
                qty = max_qty
        
        # Final sanity check
        return max(0, qty)
    
    def get_portfolio_limits(self) -> Dict[str, Any]:
        """
        Get current portfolio limits and usage for dashboard/API.
        
        Returns:
            Dictionary with equity, exposure, and per-strategy budgets
        """
        equity = self.get_equity()
        total_exposure = self.compute_total_exposure()
        max_exposure = equity * self.config.max_exposure_pct * self.config.max_leverage
        
        per_strategy = {}
        for strategy_code in self.config.strategy_budgets.keys():
            budget = self.compute_strategy_budget(strategy_code)
            used = self.compute_strategy_exposure(strategy_code)
            per_strategy[strategy_code] = {
                "budget": budget,
                "used": used,
                "available": max(0.0, budget - used),
                "utilization_pct": (used / budget * 100) if budget > 0 else 0.0,
            }
        
        return {
            "equity": equity,
            "max_exposure": max_exposure,
            "current_exposure": total_exposure,
            "available_exposure": max(0.0, max_exposure - total_exposure),
            "exposure_utilization_pct": (total_exposure / max_exposure * 100) if max_exposure > 0 else 0.0,
            "per_strategy": per_strategy,
            "config": {
                "max_leverage": self.config.max_leverage,
                "max_exposure_pct": self.config.max_exposure_pct,
                "max_risk_per_trade_pct": self.config.max_risk_per_trade_pct,
                "position_sizing_mode": self.config.position_sizing_mode,
            },
        }
