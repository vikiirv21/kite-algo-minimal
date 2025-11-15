from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class Regime(str, Enum):
    TRENDING = "TRENDING"
    CHOPPY = "CHOPPY"
    VOLATILE = "VOLATILE"
    FLAT = "FLAT"
    UNKNOWN = "UNKNOWN"


@dataclass
class RegimeSnapshot:
    regime: Regime
    score: float
    reasons: List[str] = field(default_factory=list)


@dataclass
class SignalQualityResult:
    accept: bool
    hard_block: bool
    score: float
    adjusted_risk_mult: float
    reasons: List[str] = field(default_factory=list)


def detect_regime_from_indicators(ind: Dict[str, Any]) -> RegimeSnapshot:
    """
    Regime detector built from basic indicators.

    Expects (if available) keys in `ind`:
      - ema_fast, ema_slow, ema_htf (higher timeframe)
      - atr, atr_pct
      - close
      - rsi
      - vwap
      - range_pct (recent high/low compression)
      - realized_vol (e.g. std dev of returns)
    All are optional; we degrade gracefully.
    """

    reasons: List[str] = []
    score = 0.0

    ema_fast = float(ind.get("ema_fast") or 0.0)
    ema_slow = float(ind.get("ema_slow") or 0.0)
    ema_htf = ind.get("ema_htf")
    atr_pct = ind.get("atr_pct")  # ATR / price * 100
    rsi = ind.get("rsi")
    range_pct = ind.get("range_pct")
    realized_vol = ind.get("realized_vol")

    # EMA alignment = trendiness
    ema_diff = abs(ema_fast - ema_slow)
    ema_base = abs(ema_slow) or 1.0
    ema_slope_score = ema_diff / ema_base

    if ema_slope_score > 0.01:
        score += 0.4
        reasons.append(f"EMA alignment strong (score={ema_slope_score:.3f})")
    elif ema_slope_score > 0.003:
        score += 0.2
        reasons.append(f"EMA alignment moderate (score={ema_slope_score:.3f})")
    else:
        reasons.append(f"EMA alignment weak (score={ema_slope_score:.3f})")

    # Higher timeframe EMA confirmation
    if ema_htf is not None:
        if (ema_fast > ema_slow > ema_htf) or (ema_fast < ema_slow < ema_htf):
            score += 0.2
            reasons.append("HTF EMA aligned with LTF trend")
        else:
            score -= 0.1
            reasons.append("HTF EMA not aligned")

    # ATR / realized vol for volatility regime
    vol_score = 0.0
    if atr_pct is not None:
        if atr_pct < 0.2:
            vol_score = -0.1
            reasons.append(f"Very low ATR% ({atr_pct:.2f}) -> FLAT risk")
        elif atr_pct < 0.6:
            vol_score = 0.0
            reasons.append(f"Moderate ATR% ({atr_pct:.2f})")
        elif atr_pct < 1.5:
            vol_score = 0.1
            reasons.append(f"Good ATR% ({atr_pct:.2f}) -> tradable")
        else:
            vol_score = -0.1
            reasons.append(f"High ATR% ({atr_pct:.2f}) -> VOLATILE")
    score += vol_score

    if realized_vol is not None:
        if realized_vol > 2.5:
            reasons.append(f"High realized vol ({realized_vol:.2f})")
            score -= 0.05

    # Range compression: when too tight -> chop / flat
    if range_pct is not None:
        if range_pct < 0.4:
            score -= 0.15
            reasons.append(f"Range very tight ({range_pct:.2f}%) -> CHOP/FLAT")
        elif range_pct > 1.5:
            score += 0.05
            reasons.append(f"Decent range ({range_pct:.2f}%)")

    # RSI guide: avoid extreme ends for trend entries
    if rsi is not None:
        if 35 <= rsi <= 65:
            score += 0.1
            reasons.append(f"RSI in neutral/trend zone ({rsi:.1f})")
        elif rsi < 25 or rsi > 75:
            score -= 0.1
            reasons.append(f"RSI extreme ({rsi:.1f}) -> mean reversion risk")

    # Decide regime from score + vol
    regime = Regime.UNKNOWN
    if score >= 0.4:
        regime = Regime.TRENDING
    elif score >= 0.2:
        regime = Regime.VOLATILE
    elif score <= -0.1 and (atr_pct is not None and atr_pct < 0.25):
        regime = Regime.FLAT
    elif score <= 0.0:
        regime = Regime.CHOPPY

    return RegimeSnapshot(regime=regime, score=score, reasons=reasons)


def evaluate_signal_quality(
    signal: Dict[str, Any],
    indicators: Dict[str, Any],
    ctx: Dict[str, Any],
) -> SignalQualityResult:
    """
    Score & filter a raw strategy signal.

    `signal` expected keys:
      - symbol (str)
      - side ("BUY"/"SELL")
      - strategy (str)
      - entry_price (float)
      - ts (datetime-like or str)

    `indicators`:
      whatever detect_regime_from_indicators expects +:
      - spread_pct
      - wick_ratio
      - htf_trend_ok (bool)
      - vwap_distance_pct
      - time_of_day (float 0-1 or minutes from open)

    `ctx`:
      - symbol_loss_streak (int)
      - strategy_loss_streak (int)
      - symbol_cooldown_bars_remaining (int)
      - daily_loss_pct (float)
      - daily_trades (int)
      - max_daily_trades (int)
      - risk_budget_ok (bool)
    """

    reasons: List[str] = []
    regime_snapshot: RegimeSnapshot = ctx.get("regime_snapshot") or detect_regime_from_indicators(indicators)

    score = 0.0
    hard_block = False
    adjusted_risk_mult = 1.0

    # 1) regime gate
    if regime_snapshot.regime in (Regime.FLAT, Regime.CHOPPY):
        # We don't hard-block, but down-weight
        adjusted_risk_mult *= 0.3
        reasons.append(f"Regime={regime_snapshot.regime.value}, low conviction")

    if regime_snapshot.regime == Regime.TRENDING:
        score += 0.3
        reasons.append("Trending regime -> favorable for EMA trend")

    # 2) spread & microstructure
    spread_pct = float(indicators.get("spread_pct") or 0.0)
    if spread_pct > 0.25:
        hard_block = True
        reasons.append(f"Hard block: spread too high ({spread_pct:.2f}%)")
    elif spread_pct > 0.15:
        adjusted_risk_mult *= 0.5
        reasons.append(f"Spread elevated ({spread_pct:.2f}%), reducing risk")

    # 3) candle quality
    wick_ratio = indicators.get("wick_ratio")
    if wick_ratio is not None:
        # large wick -> rejection / volatility
        if wick_ratio > 0.6:
            adjusted_risk_mult *= 0.5
            reasons.append(f"Large wick candle (ratio={wick_ratio:.2f}), cautious")

    # 4) VWAP + HTF alignment
    if indicators.get("htf_trend_ok") is False:
        adjusted_risk_mult *= 0.3
        reasons.append("HTF trend disagrees -> low conviction")

    vwap_distance_pct = indicators.get("vwap_distance_pct")
    if vwap_distance_pct is not None:
        if abs(vwap_distance_pct) > 1.2:
            adjusted_risk_mult *= 0.5
            reasons.append(f"Price far from VWAP ({vwap_distance_pct:.2f}%), riskier")

    # 5) symbol + strategy loss streaks
    sym_ls = int(ctx.get("symbol_loss_streak") or 0)
    strat_ls = int(ctx.get("strategy_loss_streak") or 0)
    cooldown_bars = int(ctx.get("symbol_cooldown_bars_remaining") or 0)

    if cooldown_bars > 0:
        hard_block = True
        reasons.append(f"Hard block: symbol cooldown active ({cooldown_bars} bars left)")

    if sym_ls >= 2:
        adjusted_risk_mult *= 0.2
        reasons.append(f"Symbol loss streak={sym_ls}, reducing size")

    if sym_ls >= 3:
        hard_block = True
        reasons.append(f"Hard block: symbol loss streak={sym_ls}")

    if strat_ls >= 3:
        hard_block = True
        reasons.append(f"Hard block: strategy loss streak={strat_ls}")

    # 6) daily risk budget & trade count
    if ctx.get("risk_budget_ok") is False:
        hard_block = True
        reasons.append("Hard block: daily risk budget exceeded")

    max_daily_trades = int(ctx.get("max_daily_trades") or 40)
    if int(ctx.get("daily_trades") or 0) >= max_daily_trades:
        hard_block = True
        reasons.append(f"Hard block: daily trade cap reached ({max_daily_trades})")

    daily_loss_pct = float(ctx.get("daily_loss_pct") or 0.0)
    if daily_loss_pct <= -2.0:
        hard_block = True
        reasons.append(f"Hard block: daily loss {daily_loss_pct:.2f}% below -2%")

    # Aggregate final score
    # Base from regime
    score += regime_snapshot.score
    # Adjust penalty for heavy downscaled risk
    if adjusted_risk_mult < 0.5:
        score -= 0.1
    if adjusted_risk_mult < 0.3:
        score -= 0.1

    # Clamp values
    adjusted_risk_mult = max(0.0, min(1.0, adjusted_risk_mult))
    score = max(-1.0, min(1.0, score))

    # Final accept decision
    accept = not hard_block and adjusted_risk_mult > 0.0 and score > -0.4

    if not accept and not hard_block:
        reasons.append("Soft reject: low score or zero risk after adjustments")

    return SignalQualityResult(
        accept=accept,
        hard_block=hard_block,
        score=score,
        adjusted_risk_mult=adjusted_risk_mult,
        reasons=reasons,
    )
