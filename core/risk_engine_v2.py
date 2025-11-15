from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, Optional


@dataclass
class RiskConfig:
    capital: float

    # Global daily risk
    max_daily_loss_pct: float = 0.02      # -2% of capital stop
    max_daily_notional_pct: float = 1.50  # 150% notional cap
    max_daily_trades: int = 40

    # Per-trade risk
    per_trade_risk_pct: float = 0.0025    # 0.25% per trade
    rr_multiple: float = 2.0              # TP = 2 * risk

    # Streak / cooldown
    max_consecutive_losses_symbol: int = 3
    max_consecutive_losses_strategy: int = 4
    cooldown_bars_after_loss: int = 10

    # Hard per-symbol loss cap as % of capital
    max_symbol_loss_pct: float = 0.01


@dataclass
class SymbolState:
    realized_pnl: float = 0.0
    notional: float = 0.0
    consecutive_losses: int = 0
    consecutive_wins: int = 0
    last_bar_index: Optional[int] = None
    cooldown_until_bar: Optional[int] = None
    disabled_for_day: bool = False
    disabled_reason: str = ""


@dataclass
class StrategyState:
    realized_pnl: float = 0.0
    consecutive_losses: int = 0
    consecutive_wins: int = 0
    disabled_for_day: bool = False
    disabled_reason: str = ""


@dataclass
class RiskState:
    trading_day: date
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    total_notional: float = 0.0
    trades_taken: int = 0
    symbols: Dict[str, SymbolState] = field(default_factory=dict)
    strategies: Dict[str, StrategyState] = field(default_factory=dict)
    hard_blocked: bool = False
    block_reason: str = ""


@dataclass
class OrderPlan:
    approve: bool
    reason: str
    qty: int = 0
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    risk_perc: float = 0.0
    notes: list[str] = field(default_factory=list)


class RiskEngine:
    """
    Stateful daily risk engine.

    You should:
      - Construct once per trading day.
      - Persist RiskState to disk via your state_store between runs.
      - Call `plan_order` before placing an order.
      - Call `on_fill` and `on_close` when trades complete.
    """

    def __init__(self, config: RiskConfig, state: Optional[RiskState] = None):
        self.config = config
        self.state = state or RiskState(trading_day=date.today())

    # ---- helpers ----

    def _get_symbol_state(self, symbol: str) -> SymbolState:
        if symbol not in self.state.symbols:
            self.state.symbols[symbol] = SymbolState()
        return self.state.symbols[symbol]

    def _get_strategy_state(self, strategy: str) -> StrategyState:
        if strategy not in self.state.strategies:
            self.state.strategies[strategy] = StrategyState()
        return self.state.strategies[strategy]

    # ---- public API ----

    def is_daily_blocked(self) -> bool:
        if self.state.hard_blocked:
            return True

        loss_pct = self.state.realized_pnl / self.config.capital * 100.0
        if loss_pct <= -self.config.max_daily_loss_pct * 100.0:
            self.state.hard_blocked = True
            self.state.block_reason = f"Daily loss {loss_pct:.2f}% <= -{self.config.max_daily_loss_pct*100:.2f}%"
            return True

        if self.state.trades_taken >= self.config.max_daily_trades:
            self.state.hard_blocked = True
            self.state.block_reason = (
                f"Daily trade cap reached ({self.state.trades_taken}/{self.config.max_daily_trades})"
            )
            return True

        notional_pct = self.state.total_notional / self.config.capital * 100.0
        if notional_pct > self.config.max_daily_notional_pct * 100.0:
            self.state.hard_blocked = True
            self.state.block_reason = (
                f"Notional {notional_pct:.2f}% > "
                f"{self.config.max_daily_notional_pct*100:.2f}% cap"
            )
            return True

        return False

    def plan_order(
        self,
        *,
        symbol: str,
        strategy: str,
        side: str,
        price: float,
        lot_size: int,
        bar_index: int,
        quality_mult: float,
    ) -> OrderPlan:
        """
        Decide quantity + SL/TP given risk limits and quality multiplier.
        """

        if self.is_daily_blocked():
            return OrderPlan(
                approve=False,
                reason=f"Daily blocked: {self.state.block_reason}",
                notes=[self.state.block_reason],
            )

        sym_state = self._get_symbol_state(symbol)
        strat_state = self._get_strategy_state(strategy)
        notes: List[str] = []

        # Symbol-level disable
        if sym_state.disabled_for_day:
            return OrderPlan(
                approve=False,
                reason=f"Symbol disabled: {sym_state.disabled_reason}",
                notes=[sym_state.disabled_reason],
            )

        if strat_state.disabled_for_day:
            return OrderPlan(
                approve=False,
                reason=f"Strategy disabled: {strat_state.disabled_reason}",
                notes=[strat_state.disabled_reason],
            )

        # Cooldown
        if sym_state.cooldown_until_bar is not None and bar_index < sym_state.cooldown_until_bar:
            return OrderPlan(
                approve=False,
                reason=f"Symbol in cooldown until bar {sym_state.cooldown_until_bar}",
                notes=[f"cooldown_until_bar={sym_state.cooldown_until_bar}"],
            )

        # Per-symbol loss cap
        symbol_loss_pct = sym_state.realized_pnl / self.config.capital * 100.0
        if symbol_loss_pct <= -self.config.max_symbol_loss_pct * 100.0:
            sym_state.disabled_for_day = True
            sym_state.disabled_reason = (
                f"Symbol loss {symbol_loss_pct:.2f}% <= -{self.config.max_symbol_loss_pct*100:.2f}%"
            )
            return OrderPlan(
                approve=False,
                reason=sym_state.disabled_reason,
                notes=[sym_state.disabled_reason],
            )

        # Consecutive losses gating
        if sym_state.consecutive_losses >= self.config.max_consecutive_losses_symbol:
            sym_state.disabled_for_day = True
            sym_state.disabled_reason = (
                f"Symbol loss streak={sym_state.consecutive_losses}, disabling for day"
            )
            return OrderPlan(
                approve=False,
                reason=sym_state.disabled_reason,
                notes=[sym_state.disabled_reason],
            )

        if strat_state.consecutive_losses >= self.config.max_consecutive_losses_strategy:
            strat_state.disabled_for_day = True
            strat_state.disabled_reason = (
                f"Strategy loss streak={strat_state.consecutive_losses}, disabling for day"
            )
            return OrderPlan(
                approve=False,
                reason=strat_state.disabled_reason,
                notes=[strat_state.disabled_reason],
            )

        # Base per-trade risk amount
        base_risk_amt = self.config.capital * self.config.per_trade_risk_pct

        # Scale with quality multiplier (0..1)
        risk_amt = base_risk_amt * max(0.0, min(1.0, quality_mult))
        if risk_amt <= 0:
            return OrderPlan(
                approve=False,
                reason="Risk amount <= 0 after quality scaling",
                notes=["quality_mult too low"],
            )

        # Assume a default SL distance (e.g. 0.5% of price) and derive qty
        sl_pct = 0.005  # 0.5%
        sl_distance = price * sl_pct
        if sl_distance <= 0:
            return OrderPlan(
                approve=False,
                reason="Invalid SL distance",
                notes=["price <= 0 or sl_distance <= 0"],
            )

        raw_qty = int(risk_amt / sl_distance / lot_size) * lot_size
        if raw_qty <= 0:
            return OrderPlan(
                approve=False,
                reason="Computed quantity <= 0",
                notes=[
                    f"risk_amt={risk_amt:.2f}",
                    f"sl_distance={sl_distance:.2f}",
                    f"lot_size={lot_size}",
                ],
            )

        notional = raw_qty * price
        projected_notional = self.state.total_notional + notional
        projected_notional_pct = projected_notional / self.config.capital * 100.0
        if projected_notional_pct > self.config.max_daily_notional_pct * 100.0:
            return OrderPlan(
                approve=False,
                reason=(
                    f"Projected notional {projected_notional_pct:.2f}% exceeds "
                    f"{self.config.max_daily_notional_pct*100:.2f}% cap"
                ),
                notes=[
                    f"projected_notional={projected_notional:.2f}",
                    f"cap={self.config.capital:.2f}",
                ],
            )

        # Compute price-based SL/TP
        if side.upper() == "BUY":
            stop_loss = price - sl_distance
            take_profit = price + sl_distance * self.config.rr_multiple
        else:
            stop_loss = price + sl_distance
            take_profit = price - sl_distance * self.config.rr_multiple

        notes.append(
            f"risk_amt={risk_amt:.2f}, sl_pct={sl_pct*100:.2f}%, rr={self.config.rr_multiple}x"
        )

        return OrderPlan(
            approve=True,
            reason="Risk OK",
            qty=raw_qty,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_perc=risk_amt / self.config.capital * 100.0,
            notes=notes,
        )

    # ---- update hooks for PnL / streaks ----

    def on_fill(
        self,
        *,
        symbol: str,
        strategy: str,
        pnl: float,
        bar_index: int,
    ) -> None:
        """
        Call this when a position is closed and realized PnL is known.
        """
        sym_state = self._get_symbol_state(symbol)
        strat_state = self._get_strategy_state(strategy)

        self.state.realized_pnl += pnl
        sym_state.realized_pnl += pnl
        strat_state.realized_pnl += pnl
        self.state.trades_taken += 1
        sym_state.last_bar_index = bar_index

        if pnl < 0:
            sym_state.consecutive_losses += 1
            sym_state.consecutive_wins = 0
            strat_state.consecutive_losses += 1
            strat_state.consecutive_wins = 0
            sym_state.cooldown_until_bar = bar_index + self.config.cooldown_bars_after_loss
        else:
            sym_state.consecutive_wins += 1
            sym_state.consecutive_losses = 0
            strat_state.consecutive_wins += 1
            strat_state.consecutive_losses = 0
            sym_state.cooldown_until_bar = None

    def on_exposure_change(self, *, symbol: str, delta_notional: float) -> None:
        """
        Call this when you open/close/resize a position.
        """
        sym_state = self._get_symbol_state(symbol)
        sym_state.notional += delta_notional
        self.state.total_notional += delta_notional

    def snapshot(self) -> Dict[str, Any]:
        """
        For dashboard / logging.
        """
        return {
            "trading_day": self.state.trading_day.isoformat(),
            "realized_pnl": self.state.realized_pnl,
            "unrealized_pnl": self.state.unrealized_pnl,
            "total_notional": self.state.total_notional,
            "trades_taken": self.state.trades_taken,
            "hard_blocked": self.state.hard_blocked,
            "block_reason": self.state.block_reason,
            "symbols": {
                sym: {
                    "realized_pnl": st.realized_pnl,
                    "notional": st.notional,
                    "consecutive_losses": st.consecutive_losses,
                    "consecutive_wins": st.consecutive_wins,
                    "cooldown_until_bar": st.cooldown_until_bar,
                    "disabled_for_day": st.disabled_for_day,
                    "disabled_reason": st.disabled_reason,
                }
                for sym, st in self.state.symbols.items()
            },
            "strategies": {
                name: {
                    "realized_pnl": st.realized_pnl,
                    "consecutive_losses": st.consecutive_losses,
                    "consecutive_wins": st.consecutive_wins,
                    "disabled_for_day": st.disabled_for_day,
                    "disabled_reason": st.disabled_reason,
                }
                for name, st in self.state.strategies.items()
            },
        }
