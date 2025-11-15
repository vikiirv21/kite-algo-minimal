from __future__ import annotations

import argparse
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Set

from analytics.multi_timeframe_scanner import INTRADAY_TF, IndicatorSnapshot, MultiTimeframeScanner
from analytics.trade_recorder import TradeRecorder
from broker.kite_client import KiteClient
from core.config import load_config
from core.history_loader import fetch_and_store_history
from core.strategy_tags import Profile
from core.universe import fno_underlyings
from core.universe_builder import (
    UniverseInstrument,
    load_equity_universe,
    load_index_deriv_universe,
)
from core.history_loader import load_history

logger = logging.getLogger(__name__)

TF_PROFILE = {
    "5m": Profile.INTRADAY.value,
    "15m": Profile.INTRADAY.value,
    "1h": Profile.INTRADAY.value,
    "1d": Profile.SWING.value,
    "1w": Profile.SWING.value,
    "1M": Profile.SWING.value,
}

BASE_INTERVALS = ("5minute", "15minute", "60minute", "day")
TRADE_STYLE_MAP = {
    "5m": "SCALP",
    "15m": "INTRADAY",
    "1h": "INTRADAY",
    "1d": "SWING",
    "1w": "POSITION",
    "1M": "POSITION",
}


def _resolve_target_set(raw: str | None) -> Set[str]:
    if not raw:
        return set()
    return {token.strip().upper() for token in raw.split(",") if token.strip()}


def _avg_daily_traded_value(symbol: str, lookback: int = 20) -> float:
    df = load_history(symbol, "day")
    tail = df.tail(lookback)
    if tail.empty:
        return 0.0
    values = tail["close"].astype(float) * tail["volume"].fillna(0)
    return float(values.mean())


def _avg_daily_volume(symbol: str, lookback: int = 10) -> float:
    df = load_history(symbol, "day")
    tail = df.tail(lookback)
    if tail.empty:
        return 0.0
    return float(tail["volume"].fillna(0).mean())


def _make_temp_instrument(symbol: str, exchange: str, underlying: str | None = None) -> UniverseInstrument:
    return UniverseInstrument(
        exchange=exchange,
        tradingsymbol=symbol.upper(),
        token=0,
        tick_size=None,
        lot_size=1,
        segment=exchange,
        underlying=underlying or symbol.upper(),
    )


def _instrument_base(inst: UniverseInstrument) -> str:
    if inst.underlying:
        return inst.underlying.upper()
    return inst.tradingsymbol.split("-")[0].split("_")[0].upper()


def _determine_signal(snapshot: IndicatorSnapshot) -> tuple[str, str]:
    ema20 = snapshot.ema20
    ema50 = snapshot.ema50
    close = snapshot.close
    rsi = snapshot.rsi14

    if ema20 and ema50:
        if close > ema20 > ema50 and (rsi is None or rsi >= 50):
            return "BUY", "BREAKOUT"
        if close < ema20 < ema50 and (rsi is None or rsi <= 50):
            return "SELL", "BREAKDOWN"

    if rsi is not None:
        if rsi <= 35:
            return "BUY", "PULLBACK"
        if rsi >= 65:
            return "SELL", "PULLBACK"

    return "HOLD", "RANGE_FADE"


def refresh_history(symbols: List[str], kite_client: KiteClient, days: int) -> None:
    kite = kite_client.api
    to_dt = datetime.utcnow()
    from_dt = to_dt - timedelta(days=days)
    for symbol in symbols:
        for interval in BASE_INTERVALS:
            try:
                fetch_and_store_history(kite, symbol, interval, from_dt, to_dt, out_path=None)
                logger.info("Fetched history %s %s", symbol, interval)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to fetch history for %s (%s): %s", symbol, interval, exc)


def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-timeframe indicator scanner.")
    parser.add_argument("--config", default="configs/dev.yaml", help="Config file path.")
    parser.add_argument(
        "--symbols",
        help="Comma separated list of symbols. Defaults to FnO + equity universe from config.",
    )
    parser.add_argument(
        "--refresh-history",
        action="store_true",
        help="Fetch latest historical data before scanning.",
    )
    parser.add_argument(
        "--history-days",
        type=int,
        default=30,
        help="Lookback window (in days) when refreshing history (default: 30).",
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    fno_symbols = [str(s).upper() for s in cfg.trading.get("fno_universe", []) if s] or fno_underlyings()
    cfg_equities = [str(s).upper() for s in cfg.trading.get("equity_universe", []) if s]

    recorder = TradeRecorder()
    scanner = MultiTimeframeScanner()

    if args.refresh_history:
        kite_client = KiteClient()
        symbols_for_history = [inst.tradingsymbol for inst in load_equity_universe()]
        symbols_for_history += [inst.tradingsymbol for inst in load_index_deriv_universe()]
        fallback = set(fno_symbols + cfg_equities)
        if not symbols_for_history:
            symbols_for_history = list(fallback)
        refresh_history(symbols_for_history, kite_client, args.history_days)

    equity_universe = load_equity_universe()
    if not equity_universe:
        equity_universe = [_make_temp_instrument(sym, "NSE") for sym in (cfg_equities or fno_symbols)]

    deriv_universe = load_index_deriv_universe()
    if not deriv_universe:
        deriv_universe = [_make_temp_instrument(sym, "NFO", underlying=sym) for sym in fno_symbols]

    min_adv = float(cfg.trading.get("min_equity_adv", 5_000_000))
    min_deriv_vol = float(cfg.trading.get("min_deriv_volume", 1000))
    targets = _resolve_target_set(args.symbols)
    if targets:
        equity_universe = [
            inst for inst in equity_universe if inst.tradingsymbol in targets or _instrument_base(inst) in targets
        ]
        deriv_universe = [
            inst for inst in deriv_universe if inst.tradingsymbol in targets or _instrument_base(inst) in targets
        ]
    if not equity_universe and not deriv_universe:
        logger.error("No instruments to scan. Check universe files or --symbols filter.")
        raise SystemExit(1)

    def process_instrument(inst: UniverseInstrument) -> None:
        symbol = inst.tradingsymbol.upper()
        snapshots = scanner.scan_symbol(symbol)
        if not snapshots:
            return
        base = _instrument_base(inst)
        for snapshot in snapshots:
            tf = snapshot.timeframe
            signal, setup = _determine_signal(snapshot)
            mode_label = TRADE_STYLE_MAP.get(tf, "SWING")
            profile = TF_PROFILE.get(tf, Profile.SWING.value)
            strategy_name = f"SCANNER_EMA_{tf}"
            logical = f"{base}|{strategy_name}_{tf}"
            vol_spike = bool(snapshot.rel_volume and snapshot.rel_volume >= 1.5)
            reason = (
                f"{setup} tf={tf} price={snapshot.close:.2f} "
                f"ema20={_fmt(snapshot.ema20)} rsi={_fmt(snapshot.rsi14)} rv={_fmt(snapshot.rel_volume)}"
            )
            trend_context = setup
            vol_regime = "HIGH" if vol_spike else ("NORMAL" if snapshot.rel_volume else "")
            recorder.log_signal(
                logical=logical,
                symbol=symbol,
                price=snapshot.close,
                signal=signal,
                tf=tf,
                reason=reason,
                profile=profile,
                mode=mode_label,
                confidence=None,
                trend_context=trend_context,
                vol_regime=vol_regime,
                htf_trend="",
                playbook=setup,
                setup_type=setup,
                ema20=snapshot.ema20,
                ema50=snapshot.ema50,
                ema100=snapshot.ema100,
                ema200=snapshot.ema200,
                rsi14=snapshot.rsi14,
                atr=snapshot.atr14,
                adx14=snapshot.adx14,
                adx=snapshot.adx14,
                vwap=snapshot.vwap if tf in INTRADAY_TF else snapshot.vwap,
                rel_volume=snapshot.rel_volume,
                vol_spike=vol_spike,
                strategy=strategy_name,
            )

    for inst in equity_universe:
        adv = _avg_daily_traded_value(inst.tradingsymbol)
        if adv < min_adv:
            continue
        process_instrument(inst)

    for inst in deriv_universe:
        volume = _avg_daily_volume(inst.tradingsymbol)
        if (inst.lot_size or 0) <= 0 or volume < min_deriv_vol:
            continue
        process_instrument(inst)


def _fmt(value: Optional[float]) -> str:
    if value is None:
        return "--"
    return f"{value:.2f}"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    main()
