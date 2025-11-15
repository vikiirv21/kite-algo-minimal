"""Strategy framework glue that runs enabled strategies for each tick."""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
import logging
from typing import Any, Dict, Iterable, Optional

from strategies.base import Decision
from strategies.fno_intraday_trend import FnoIntradayTrendStrategy
from strategies.mean_reversion_intraday import MeanReversionIntradayStrategy

from core.state_store import record_strategy_signal
from core.strategy_registry import STRATEGY_REGISTRY, StrategyInfo

logger = logging.getLogger(__name__)


class BaseStrategy(ABC):
    """Abstract wrapper around concrete strategy implementations."""

    def __init__(self, strategy_info: StrategyInfo) -> None:
        self.strategy_info = strategy_info

    @abstractmethod
    def generate_signal(self, symbol: str, bar: Dict[str, float]) -> Optional[Decision]:
        """Return the latest Decision (or HOLD) for the provided bar."""


class EMA2050IntradayStrategy(BaseStrategy):
    """Wrapper around the FnO EMA trend strategy."""

    def __init__(self, strategy_info: StrategyInfo) -> None:
        super().__init__(strategy_info)
        self.strategy = FnoIntradayTrendStrategy(timeframe=strategy_info.timeframe)

    def generate_signal(self, symbol: str, bar: Dict[str, float]) -> Decision:
        return self.strategy.on_bar(symbol, bar)


class ExpiryScalperStrategy(BaseStrategy):
    """
    Lightweight wrapper that uses the mean-reversion strategy as a placeholder
    for expiry scalping logic.
    """

    def __init__(self, strategy_info: StrategyInfo) -> None:
        super().__init__(strategy_info)
        self.strategy = MeanReversionIntradayStrategy(timeframe=strategy_info.timeframe)

    def generate_signal(self, symbol: str, bar: Dict[str, float]) -> Decision:
        return self.strategy.on_bar(symbol, bar)


class StrategyRunner:
    """Dispatch enabled strategies over the latest market ticks."""

    def __init__(
        self,
        _state_store: Any,
        paper_engine: Any,
        *,
        allowed_strategies: Optional[Iterable[str]] = None,
        market_data_engine: Optional[Any] = None,
    ) -> None:
        # state_store retained for backward compatibility (unused now)
        self.paper_engine = paper_engine
        self.market_data_engine = market_data_engine
        self.allowed_strategies = {code.strip(): True for code in (allowed_strategies or []) if code}
        self.strategies: Dict[str, BaseStrategy] = {}
        self._load_strategies()

    def _load_strategies(self) -> None:
        """Instantiate all enabled strategies declared in the registry."""
        for strategy_code, strategy_info in STRATEGY_REGISTRY.items():
            if not strategy_info.enabled:
                continue
            if self.allowed_strategies and strategy_code not in self.allowed_strategies:
                continue
            if strategy_code == "ema20_50_intraday":
                self.strategies[strategy_code] = EMA2050IntradayStrategy(strategy_info)
            elif strategy_code == "expiry_scalper":
                self.strategies[strategy_code] = ExpiryScalperStrategy(strategy_info)
            else:
                logger.debug("Strategy %s is enabled but has no runner.", strategy_code)

    def run(self, ticks: Dict[str, Dict[str, float]]) -> None:
        """Run every enabled strategy for each incoming tick snapshot."""
        if not self.strategies or not ticks:
            return

        timestamp = datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()
        for strategy_code, strategy in self.strategies.items():
            for symbol, bar in ticks.items():
                price = _extract_price(bar)
                if price <= 0:
                    continue
                try:
                    decision = strategy.generate_signal(symbol, bar)
                except Exception as exc:  # noqa: BLE001
                    logger.exception(
                        "Strategy %s failed for %s: %s", strategy_code, symbol, exc
                    )
                    continue
                normalized = _normalize_decision(decision)
                if normalized is None:
                    continue
                action = normalized.action.upper()
                if action not in {"BUY", "SELL", "EXIT"}:
                    continue
                record_strategy_signal(strategy_code, timestamp=timestamp)
                logical_name = getattr(self.paper_engine, "logical_alias", {}).get(
                    symbol, symbol
                )
                self.paper_engine._handle_signal(
                    symbol,
                    action,
                    price,
                    logical=logical_name,
                    tf=strategy.strategy_info.timeframe,
                    strategy_name=strategy.strategy_info.name,
                    strategy_code=strategy_code,
                    confidence=normalized.confidence,
                    reason=normalized.reason,
                )


def _normalize_decision(result: Any) -> Optional[Decision]:
    if result is None:
        return None
    if isinstance(result, Decision):
        return result
    if isinstance(result, str):
        return Decision(action=result.upper())
    action = getattr(result, "action", None)
    if isinstance(action, str):
        reason = getattr(result, "reason", "")
        confidence = getattr(result, "confidence", 0.0)
        return Decision(action=action.upper(), reason=reason, confidence=confidence)
    return None


def _extract_price(bar: Dict[str, float]) -> float:
    try:
        return float(bar.get("close", 0.0))
    except (TypeError, ValueError):
        return 0.0
