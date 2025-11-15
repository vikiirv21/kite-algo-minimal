from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from analytics.multi_timeframe_engine import (
    ALL_TIMEFRAMES,
    MultiTimeframeEngine,
    TimeframeSnapshot,
    TF_15M,
    TF_1D,
    TF_1H,
    TF_1M,
    TF_1W,
    TF_5M,
)

STYLE_INTRADAY = "intraday"
STYLE_SWING = "swing"
STYLE_POSITIONAL = "positional"


@dataclass
class MetaDecision:
    symbol: str
    style: str
    timeframe: str
    strategy_name: str
    confidence: float
    reason: str


class MetaStrategyEngine:
    """
    Lightweight meta engine that consumes multi-timeframe snapshots and decides
    whether we should trade a symbol, on which timeframe, and which strategy
    archetype best fits current structure.
    """

    def __init__(
        self,
        multi_engine: MultiTimeframeEngine,
        strategy_registry: Optional[Dict[str, Dict[str, object]]] = None,
        config: Optional[Dict[str, object]] = None,
    ) -> None:
        self.multi_engine = multi_engine
        self.config = config or {}
        self.strategy_registry = strategy_registry or self._default_registry()

        self.symbol_focus = [str(s).upper() for s in self.config.get("symbols_focus", []) if s]
        if not self.symbol_focus:
            self.symbol_focus = ["BANKNIFTY", "NIFTY", "FINNIFTY"]

        self.allow_equity_satellites = bool(self.config.get("allow_equity_satellites", True))
        self.max_active_symbols = int(self.config.get("max_active_symbols", 5))
        self.cost_per_trade_pct = float(self.config.get("cost_per_trade_pct", 0.0004))
        self.allow_fallback = bool(self.config.get("fallback_intraday_when_no_decision", False))
        self.cache_ttl = int(self.config.get("decision_cache_ttl_sec", 60))

        self._decision_cache: Dict[str, Optional[MetaDecision]] = {}
        self._decision_ts: Dict[str, float] = {}

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _default_registry() -> Dict[str, Dict[str, object]]:
        return {
            STYLE_INTRADAY: {
                "strategy_name": "FnoIntradayTrendStrategy",
                "timeframes": (TF_5M, TF_15M, TF_1H),
            },
            STYLE_SWING: {
                "strategy_name": "MeanReversionIntradayStrategy",
                "timeframes": (TF_15M, TF_1H, TF_1D),
            },
            STYLE_POSITIONAL: {
                "strategy_name": "EquityIntradaySimpleStrategy",
                "timeframes": (TF_1D, TF_1W, TF_1M),
            },
        }

    @staticmethod
    def _score_alignment(snaps: List[TimeframeSnapshot], frames: Sequence[str]) -> Tuple[float, str, float]:
        candidates = [s for s in snaps if s.timeframe in frames]
        if not candidates:
            return 0.0, "insufficient_data", 0.0

        trends = [s.trend for s in candidates]
        momenta = [s.momentum_score for s in candidates]
        vols = [s.volatility for s in candidates]

        if all(t == "up" for t in trends):
            direction = 1.0
        elif all(t == "down" for t in trends):
            direction = -1.0
        else:
            direction = 0.0

        avg_momentum = sum(momenta) / len(momenta)
        avg_vol = sum(vols) / len(vols) if vols else 0.0
        score = direction * avg_momentum
        return score, "aligned" if direction != 0 else "choppy", avg_vol

    def _select_decision(self, symbol: str, snaps: List[TimeframeSnapshot]) -> Optional[MetaDecision]:
        intraday_score, intraday_state, intraday_vol = self._score_alignment(
            snaps, self.strategy_registry[STYLE_INTRADAY]["timeframes"]
        )
        swing_score, swing_state, swing_vol = self._score_alignment(
            snaps, self.strategy_registry[STYLE_SWING]["timeframes"]
        )
        positional_score, positional_state, positional_vol = self._score_alignment(
            snaps, self.strategy_registry[STYLE_POSITIONAL]["timeframes"]
        )

        candidates = [
            (STYLE_INTRADAY, intraday_score, intraday_state, intraday_vol),
            (STYLE_SWING, swing_score, swing_state, swing_vol),
            (STYLE_POSITIONAL, positional_score, positional_state, positional_vol),
        ]

        best_style = None
        best_score = 0.0
        best_state = ""
        best_vol = 0.0
        for style, score, state, vol in candidates:
            if abs(score) > abs(best_score) and abs(score) > self.cost_per_trade_pct:
                best_style = style
                best_score = score
                best_state = state
                best_vol = vol

        if not best_style:
            return None

        registry_entry = self.strategy_registry.get(best_style, {})
        timeframes = registry_entry.get("timeframes", ALL_TIMEFRAMES)
        primary_tf = timeframes[-1] if isinstance(timeframes, (list, tuple)) else TF_1H
        strategy_name = str(registry_entry.get("strategy_name", "FnoIntradayTrendStrategy"))

        direction = "long" if best_score > 0 else "short"
        confidence = min(1.0, abs(best_score) * 5)
        reason = (
            f"{best_style} alignment {direction} "
            f"(momentum={best_score:.4f}, vol={best_vol:.4f}, state={best_state})"
        )

        return MetaDecision(
            symbol=symbol,
            style=best_style,
            timeframe=primary_tf,
            strategy_name=strategy_name,
            confidence=confidence,
            reason=reason,
        )

    def _sorted_symbols(self, symbols: Iterable[str]) -> List[str]:
        symbols_upper = [s.upper() for s in symbols if s]
        if not self.symbol_focus:
            return symbols_upper

        def priority(sym: str) -> Tuple[int, str]:
            for idx, token in enumerate(self.symbol_focus):
                if token in sym:
                    return idx, sym
            return len(self.symbol_focus), sym

        filtered = symbols_upper
        if not self.allow_equity_satellites:
            filtered = [s for s in symbols_upper if any(token in s for token in self.symbol_focus)]

        return sorted(filtered, key=priority)

    # ------------------------------------------------------------------ public
    def decide_for_symbol(self, symbol: str) -> Optional[MetaDecision]:
        if not symbol:
            return None
        sym = symbol.upper()
        now = time.time()

        cached = self._decision_cache.get(sym)
        ts = self._decision_ts.get(sym, 0.0)
        if cached is not None and now - ts <= self.cache_ttl:
            return cached

        snapshots = self.multi_engine.get_all(sym)
        decision = self._select_decision(sym, snapshots)
        self._decision_cache[sym] = decision
        self._decision_ts[sym] = now
        return decision

    def decide_for_universe(self, symbols: Iterable[str]) -> List[MetaDecision]:
        ordered = self._sorted_symbols(symbols)
        results: List[MetaDecision] = []
        for sym in ordered:
            decision = self.decide_for_symbol(sym)
            if decision:
                results.append(decision)
            if len(results) >= self.max_active_symbols:
                break
        return results
