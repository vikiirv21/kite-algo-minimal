"""
Risk Engine
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Any, Dict, Optional


class RiskAction(Enum):
    ALLOW = auto()
    BLOCK = auto()
    REDUCE = auto()
    HALT_SESSION = auto()


@dataclass
class RiskDecision:
    action: RiskAction
    reason: str
    adjusted_qty: Optional[int] = None
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RiskConfig:
    mode: str = "default"
    capital: float = 0.0
    per_trade_risk_pct: float = 0.0

    max_daily_loss_abs: Optional[float] = None
    max_daily_loss_pct: Optional[float] = None

    max_positions_total: Optional[int] = None
    max_positions_per_symbol: Optional[int] = None
    max_trades_per_symbol_per_day: Optional[int] = None
    min_seconds_between_entries: Optional[int] = None

    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RiskConfig":
        field_names = {f.name for f in cls.__dataclass_fields__.values()}
        kwargs = {}
        extra = {}

        for k, v in data.items():
            if k in field_names:
                kwargs[k] = v
            else:
                extra[k] = v

        cfg = cls(**kwargs)
        cfg.extra = extra
        return cfg


class TradeContext:
    def __init__(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)

    def get(self, key: str, default=None):
        return getattr(self, key, default)


def build_risk_config(raw: dict) -> RiskConfig:
    if raw is None:
        return RiskConfig()
    if isinstance(raw, RiskConfig):
        return raw
    if not isinstance(raw, dict):
        return RiskConfig()
    return RiskConfig.from_dict(raw)


def compute_exit_decision(ctx: TradeContext) -> RiskDecision:
    """
    Backward-compatible helper. Currently all exits are always allowed.
    Codex-generated paper_engine may expect this.
    """
    return RiskDecision(
        action=RiskAction.ALLOW,
        reason="Exit always allowed"
    )


logger = logging.getLogger(__name__)



class RiskEngine:
    def __init__(self, config: Any, state: dict, logger_instance: logging.Logger):
        if isinstance(config, RiskConfig):
            self.config_obj = config
            config_map = asdict(config)
            extra = config.extra or {}
            for key, value in extra.items():
                config_map.setdefault(key, value)
            self.config = config_map
        else:
            self.config_obj = None
            self.config = dict(config or {})
        self.state = state
        self.logger = logger_instance
        self.last_trade_ts: Dict[str, datetime] = {}

    def check_order(
        self, order_intent: dict, portfolio_state: dict, strategy_state: dict
    ) -> RiskDecision:
        if self._check_halt():
            return RiskDecision(
                action=RiskAction.HALT_SESSION, reason="Trading is halted"
            )

        decision = self._check_daily_loss(portfolio_state)
        if decision.action != RiskAction.ALLOW:
            return decision

        decision = self._check_position_limits(order_intent, portfolio_state)
        if decision.action != RiskAction.ALLOW:
            return decision

        decision = self._check_throttle(order_intent)
        if decision.action != RiskAction.ALLOW:
            return decision

        decision = self._check_per_trade_risk(order_intent, portfolio_state)
        if decision.action != RiskAction.ALLOW:
            return decision

        return RiskDecision(action=RiskAction.ALLOW, reason="All checks passed")

    def _check_halt(self) -> bool:
        return self.state.get("risk", {}).get("trading_halted", False)

    def _check_daily_loss(self, portfolio_state: dict) -> RiskDecision:
        day_pnl = portfolio_state.get("day_pnl", 0.0)
        max_daily_loss_abs = self.config.get("max_daily_loss_abs")
        max_daily_loss_pct = self.config.get("max_daily_loss_pct")
        capital = self.config.get("capital", 0)

        if max_daily_loss_abs is not None and day_pnl <= -max_daily_loss_abs:
            self._halt(f"Daily loss limit of {max_daily_loss_abs} reached")
            return RiskDecision(
                action=RiskAction.HALT_SESSION,
                reason=f"Daily loss limit reached: {day_pnl} <= {-max_daily_loss_abs}",
            )

        if (
            max_daily_loss_pct is not None
            and capital > 0
            and (day_pnl / capital) <= -max_daily_loss_pct
        ):
            self._halt(f"Daily loss limit of {max_daily_loss_pct * 100}% reached")
            return RiskDecision(
                action=RiskAction.HALT_SESSION,
                reason=f"Daily loss percentage reached: {day_pnl / capital * 100}% <= {-max_daily_loss_pct * 100}%",
            )

        return RiskDecision(action=RiskAction.ALLOW, reason="")

    def _check_per_trade_risk(
        self, order_intent: dict, portfolio_state: dict
    ) -> RiskDecision:
        per_trade_risk_pct = self.config.get("per_trade_risk_pct")
        capital = self.config.get("capital", 0)
        if not per_trade_risk_pct or capital <= 0:
            return RiskDecision(action=RiskAction.ALLOW, reason="")

        price = order_intent.get("price", 0)
        qty = order_intent.get("quantity", 0)
        notional = price * qty
        risk_amount = capital * per_trade_risk_pct

        if notional > risk_amount:
            adjusted_qty = int(risk_amount / price)
            if adjusted_qty < 1:
                return RiskDecision(
                    action=RiskAction.BLOCK,
                    reason=f"Per-trade risk exceeded: notional {notional} > risk amount {risk_amount}",
                )
            return RiskDecision(
                action=RiskAction.REDUCE,
                reason=f"Per-trade risk exceeded: reducing qty to {adjusted_qty}",
                adjusted_qty=adjusted_qty,
            )

        return RiskDecision(action=RiskAction.ALLOW, reason="")

    def _check_position_limits(
        self, order_intent: dict, portfolio_state: dict
    ) -> RiskDecision:
        max_positions_total = self.config.get("max_positions_total")
        max_positions_per_symbol = self.config.get("max_positions_per_symbol")
        symbol = order_intent.get("symbol")
        positions = portfolio_state.get("positions", [])

        if (
            max_positions_total is not None
            and len(positions) >= max_positions_total
        ):
            return RiskDecision(
                action=RiskAction.BLOCK,
                reason=f"Total position limit reached: {len(positions)} >= {max_positions_total}",
            )

        if symbol and max_positions_per_symbol is not None:
            symbol_positions = [p for p in positions if p.get("symbol") == symbol]
            if len(symbol_positions) >= max_positions_per_symbol:
                return RiskDecision(
                    action=RiskAction.BLOCK,
                    reason=f"Per-symbol position limit reached for {symbol}: {len(symbol_positions)} >= {max_positions_per_symbol}",
                )

        return RiskDecision(action=RiskAction.ALLOW, reason="")

    def _check_throttle(self, order_intent: dict) -> RiskDecision:
        min_seconds_between_entries = self.config.get("min_seconds_between_entries")
        symbol = order_intent.get("symbol")
        if not min_seconds_between_entries or not symbol:
            return RiskDecision(action=RiskAction.ALLOW, reason="")

        now = datetime.now()
        last_trade = self.last_trade_ts.get(symbol)
        if last_trade:
            if (now - last_trade).total_seconds() < min_seconds_between_entries:
                return RiskDecision(
                    action=RiskAction.BLOCK,
                    reason=f"Throttling trade for {symbol}: {(now - last_trade).total_seconds()}s < {min_seconds_between_entries}s",
                )

        self.last_trade_ts[symbol] = now
        return RiskDecision(action=RiskAction.ALLOW, reason="")

    def _halt(self, reason: str) -> None:
        self.logger.warning(f"Halting trading session: {reason}")
        if "risk" not in self.state:
            self.state["risk"] = {}
        self.state["risk"]["trading_halted"] = True
        self.state["risk"]["halt_reason"] = reason
        self.state["risk"]["last_decision_ts"] = datetime.now().isoformat()
