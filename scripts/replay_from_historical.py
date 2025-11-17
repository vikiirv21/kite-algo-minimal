from __future__ import annotations

if __name__ == "__main__" and __package__ is None:
    import sys
    from pathlib import Path
    
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

import argparse
import logging
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Tuple

from analytics.trade_recorder import ORDER_HEADERS, SIGNAL_HEADERS, TradeRecorder
from core.config import AppConfig, load_config
from core.history_loader import load_history
from core.logging_utils import setup_logging
from core.modes import TradingMode
from core.universe import fno_underlyings, load_equity_universe as load_equity_universe_csv
from engine.equity_paper_engine import EquityPaperEngine
from engine.options_paper_engine import OptionsPaperEngine
from engine.paper_engine import PaperEngine


LOGGER = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parents[1]
LIVE_ARTIFACTS_DIR = (BASE_DIR / "artifacts").resolve()
DEFAULT_INTERVAL = "5minute"


class ReplayDataFeed:
    """Lightweight data feed that serves prepared prices to the engines."""

    def __init__(self) -> None:
        self._prices: Dict[str, float] = {}

    def bulk_set(self, mapping: Mapping[str, float]) -> None:
        for symbol, price in mapping.items():
            self._prices[symbol] = float(price)

    def get_ltp(self, symbol: str, exchange: str | None = None) -> float:  # noqa: ARG002
        if symbol not in self._prices:
            raise KeyError(f"No replay price available for {symbol}")
        return self._prices[symbol]


class StaticOptionUniverse:
    """Replay-friendly option resolver that always returns the provided CE/PE symbols."""

    def __init__(self, mapping: Mapping[str, Dict[str, str]]) -> None:
        self._mapping = {k.upper(): {"CE": v["CE"], "PE": v["PE"]} for k, v in mapping.items()}

    def resolve_atm_for_many(self, spots: Mapping[str, float]) -> Dict[str, Dict[str, str]]:
        del spots
        return {logical: alias.copy() for logical, alias in self._mapping.items()}


@dataclass
class ReplaySeries:
    timestamp: datetime
    close: float


def parse_replay_date(raw: str) -> Tuple[str, date]:
    try:
        dt = datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError as exc:  # pragma: no cover - CLI validation
        raise SystemExit(f"Invalid --date format ({raw}). Expected YYYY-MM-DD.") from exc
    return raw, dt


def ensure_replay_dir(date_str: str) -> Path:
    replay_dir = (LIVE_ARTIFACTS_DIR / f"replay_{date_str}").resolve()
    if replay_dir == LIVE_ARTIFACTS_DIR:
        raise RuntimeError("Replay artifacts dir must not be the same as live artifacts dir.")
    replay_dir.mkdir(parents=True, exist_ok=True)
    return replay_dir


def reset_replay_outputs(target_dir: Path) -> None:
    for name in ("signals.csv", "orders.csv", "paper_state.json"):
        path = target_dir / name
        if path.exists():
            path.unlink()


def configure_recorder(recorder: TradeRecorder, target_dir: Path) -> None:
    recorder.artifacts_dir = str(target_dir)
    recorder.signals_path = str(target_dir / "signals.csv")
    recorder.orders_path = str(target_dir / "orders.csv")
    recorder.state_path = str(target_dir / "paper_state.json")
    recorder._ensure_csv_headers(recorder.signals_path, SIGNAL_HEADERS)
    recorder._ensure_csv_headers(recorder.orders_path, ORDER_HEADERS)


def configure_engine(engine, target_dir: Path) -> None:
    engine.artifacts_dir = target_dir
    engine.state_path = target_dir / "paper_state.json"
    recorder = TradeRecorder()
    configure_recorder(recorder, target_dir)
    engine.recorder = recorder
    engine.meta_enabled = False
    engine.meta_engine = None
    engine.multi_tf_engine = None
    engine._last_meta_decisions = {}


def load_daily_bars(symbol: str, replay_date: date, interval: str = DEFAULT_INTERVAL) -> List[ReplaySeries]:
    df = load_history(symbol, interval)
    if df.empty or "timestamp" not in df.columns:
        return []
    df = df[df["timestamp"].dt.date == replay_date].copy()
    if df.empty:
        return []
    rows: List[ReplaySeries] = []
    for _, row in df.iterrows():
        ts = row["timestamp"]
        if not isinstance(ts, datetime):
            continue
        close = float(row.get("close", 0.0))
        if close <= 0:
            continue
        rows.append(ReplaySeries(timestamp=ts.to_pydatetime(), close=close))
    return rows


def load_series_for_symbols(symbols: Iterable[str], replay_date: date) -> Dict[str, List[ReplaySeries]]:
    output: Dict[str, List[ReplaySeries]] = {}
    for symbol in symbols:
        series = load_daily_bars(symbol, replay_date)
        if not series:
            LOGGER.warning("No replay history for %s on %s; skipping.", symbol, replay_date.isoformat())
            continue
        output[symbol] = sorted(series, key=lambda item: item.timestamp)
    return output


def iter_replay_steps(series_map: Dict[str, List[ReplaySeries]]) -> List[Tuple[datetime, Dict[str, float]]]:
    if not series_map:
        return []
    first_points = [rows[0].timestamp for rows in series_map.values() if rows]
    if not first_points:
        return []
    start_ts = max(first_points)
    all_ts = {
        bar.timestamp
        for rows in series_map.values()
        for bar in rows
        if bar.timestamp >= start_ts
    }
    timeline = sorted(all_ts)

    pointers = {sym: 0 for sym in series_map}
    current_prices: Dict[str, float | None] = {sym: None for sym in series_map}
    steps: List[Tuple[datetime, Dict[str, float]]] = []

    for ts in timeline:
        ready = True
        price_snapshot: Dict[str, float] = {}
        for sym, rows in series_map.items():
            idx = pointers[sym]
            while idx < len(rows) and rows[idx].timestamp <= ts:
                current_prices[sym] = rows[idx].close
                idx += 1
            pointers[sym] = idx
            if current_prices[sym] is None:
                ready = False
            else:
                price_snapshot[sym] = float(current_prices[sym])
        if ready:
            steps.append((ts, price_snapshot))
    return steps


def build_symbol_map(logicals: List[str], overrides: Mapping[str, str]) -> Dict[str, str]:
    mapped: Dict[str, str] = {}
    override_norm = {k.upper(): str(v).strip().upper() for k, v in overrides.items()}
    for logical in logicals:
        key = logical.upper()
        mapped[key] = override_norm.get(key, key)
    return mapped


def filter_symbol_map(symbol_map: Dict[str, str], series_map: Dict[str, List[ReplaySeries]]) -> Dict[str, str]:
    return {logical: symbol for logical, symbol in symbol_map.items() if symbol in series_map}


def build_option_alias(logicals: Iterable[str]) -> Dict[str, Dict[str, str]]:
    return {
        logical.upper(): {
            "CE": f"{logical.upper()}_REPLAY_CE",
            "PE": f"{logical.upper()}_REPLAY_PE",
        }
        for logical in logicals
    }


def run_replay_loop(
    engine_name: str,
    engine,
    feed: ReplayDataFeed,
    symbol_series: Dict[str, List[ReplaySeries]],
    option_alias: Optional[Dict[str, Dict[str, str]]] = None,
) -> None:
    steps = iter_replay_steps(symbol_series)
    if not steps:
        LOGGER.warning("[%s] No replay steps available.", engine_name.upper())
        return

    LOGGER.info("[%s] Starting replay with %d steps", engine_name.upper(), len(steps))
    fut_to_logical = {}
    if engine_name == "options":
        fut_to_logical = {value: key for key, value in getattr(engine, "underlying_futs", {}).items()}

    for idx, (ts, price_map) in enumerate(steps, start=1):
        feed.bulk_set(price_map)
        if option_alias:
            synthetic_prices: Dict[str, float] = {}
            for fut_symbol, price in price_map.items():
                logical = fut_to_logical.get(fut_symbol.upper())
                if not logical:
                    continue
                aliases = option_alias.get(logical.upper(), {})
                for opt_symbol in aliases.values():
                    synthetic_prices[opt_symbol] = price
            if synthetic_prices:
                feed.bulk_set(synthetic_prices)
        engine._loop_once()  # type: ignore[attr-defined]
        if idx % 25 == 0 or idx == len(steps):
            LOGGER.info("[%s] Replay progress %d/%d ts=%s", engine_name.upper(), idx, len(steps), ts.isoformat())

    meta = engine._compute_portfolio_meta()  # type: ignore[attr-defined]
    engine.recorder.snapshot_paper_state(engine.paper_broker, last_prices=engine.last_prices, meta=meta)
    LOGGER.info("[%s] Replay complete.", engine_name.upper())


def compute_fno_universe(cfg: AppConfig) -> List[str]:
    cfg_fno = cfg.trading.get("fno_universe", []) or []
    logicals = [str(sym).strip().upper() for sym in cfg_fno if sym]
    return logicals or fno_underlyings()


def compute_option_universe(cfg: AppConfig) -> List[str]:
    cfg_opts = cfg.trading.get("options_underlyings", []) or []
    logicals = [str(sym).strip().upper() for sym in cfg_opts if sym]
    if logicals:
        return logicals
    return compute_fno_universe(cfg)


def compute_equity_universe(cfg: AppConfig) -> List[str]:
    replay_list = [str(sym).strip().upper() for sym in cfg.trading.get("replay_equity_universe", []) or [] if sym]
    if replay_list:
        return replay_list
    cfg_list = [str(sym).strip().upper() for sym in cfg.trading.get("equity_universe", []) or [] if sym]
    if cfg_list:
        return cfg_list
    return load_equity_universe_csv()


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay engines from cached historical data.")
    parser.add_argument("--date", required=True, help="Trading date to replay (YYYY-MM-DD).")
    parser.add_argument("--engines", choices=["fno", "options", "equity", "both", "all"], default="fno")
    parser.add_argument("--config", default="configs/dev.yaml", help="Path to YAML config.")
    args = parser.parse_args()

    date_str, replay_date = parse_replay_date(args.date)
    replay_artifacts = ensure_replay_dir(date_str)
    LOGGER.info("=== REPLAY MODE === date=%s artifacts=%s", date_str, replay_artifacts)
    reset_replay_outputs(replay_artifacts)

    cfg = load_config(args.config)
    setup_logging(cfg.logging)

    engine_keys = (
        ["fno", "options", "equity"]
        if args.engines == "all"
        else ["fno", "options"]
        if args.engines == "both"
        else [args.engines]
    )

    # Pre-compute overrides from config for reproducibility.
    fno_logicals = compute_fno_universe(cfg)
    option_logicals = compute_option_universe(cfg)
    equity_universe = compute_equity_universe(cfg)

    fno_overrides = cfg.trading.get("replay_fno_symbols", {}) or {}
    option_overrides = cfg.trading.get("replay_options_symbols", {}) or {}
    equity_overrides_raw = cfg.trading.get("replay_equity_symbols", {}) or {}
    equity_overrides = {str(k).strip().upper(): str(v).strip().upper() for k, v in equity_overrides_raw.items()}

    fno_symbol_map = build_symbol_map(fno_logicals, fno_overrides)
    option_symbol_map = build_symbol_map(option_logicals, option_overrides or fno_symbol_map)

    for key in engine_keys:
        try:
            if key == "fno":
                series_map_all = load_series_for_symbols(fno_symbol_map.values(), replay_date)
                filtered_map = filter_symbol_map(fno_symbol_map, series_map_all)
                if not filtered_map:
                    LOGGER.warning("[FNO] No symbols with history for %s.", replay_date.isoformat())
                    continue
                feed = ReplayDataFeed()
                engine = PaperEngine(
                    cfg,
                    trading_mode=TradingMode.REPLAY,
                    artifacts_dir=replay_artifacts,
                    kite_client=None,
                    data_feed=feed,
                    logical_universe_override=list(filtered_map.keys()),
                    symbol_map_override=filtered_map,
                )
                configure_engine(engine, replay_artifacts)
                subset_series = {symbol: series_map_all[symbol] for symbol in filtered_map.values()}
                run_replay_loop("fno", engine, feed, subset_series)

            elif key == "options":
                series_map_all = load_series_for_symbols(option_symbol_map.values(), replay_date)
                filtered_map = filter_symbol_map(option_symbol_map, series_map_all)
                if not filtered_map:
                    LOGGER.warning("[OPTIONS] No underlying futures history for %s.", replay_date.isoformat())
                    continue
                option_alias = build_option_alias(filtered_map.keys())
                feed = ReplayDataFeed()
                engine = OptionsPaperEngine(
                    cfg,
                    trading_mode=TradingMode.REPLAY,
                    artifacts_dir=replay_artifacts,
                    kite_client=None,
                    data_feed=feed,
                    logical_underlyings_override=list(filtered_map.keys()),
                    underlying_futs_override=filtered_map,
                    option_universe_override=StaticOptionUniverse(option_alias),
                )
                configure_engine(engine, replay_artifacts)
                subset_series = {symbol: series_map_all[symbol] for symbol in filtered_map.values()}
                run_replay_loop("options", engine, feed, subset_series, option_alias=option_alias)

            elif key == "equity":
                replay_symbols = [equity_overrides.get(sym, sym).upper() for sym in equity_universe]
                series_map_all = load_series_for_symbols(replay_symbols, replay_date)
                filtered_symbols = [sym for sym in replay_symbols if sym in series_map_all]
                if not filtered_symbols:
                    LOGGER.warning("[EQUITY] No equity history for %s.", replay_date.isoformat())
                    continue
                feed = ReplayDataFeed()
                engine = EquityPaperEngine(
                    cfg,
                    trading_mode=TradingMode.REPLAY,
                    artifacts_dir=replay_artifacts,
                    kite_client=None,
                    data_feed=feed,
                    equity_universe_override=filtered_symbols,
                )
                configure_engine(engine, replay_artifacts)
                subset_series = {symbol: series_map_all[symbol] for symbol in filtered_symbols}
                run_replay_loop("equity", engine, feed, subset_series)
        except Exception:  # noqa: BLE001
            LOGGER.exception("Replay failed for engine=%s", key)
            raise

    LOGGER.info("Replay finished. Inspect outputs under %s", replay_artifacts)


if __name__ == "__main__":
    main()
