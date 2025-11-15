from __future__ import annotations

import argparse
import csv
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Sequence, Set

from core.config import AppConfig, load_config
from core.history_loader import _default_history_path as history_path  # type: ignore import
from core.history_loader import _resolve_instrument_token  # type: ignore import
from core.kite_env import load_kite_env, make_kite_client_from_env
from core.logging_utils import setup_logging
from core.kite_http import kite_request
from core.universe import fno_underlyings, load_equity_universe as load_equity_universe_csv
from data.instruments import resolve_fno_symbols


logger = logging.getLogger(__name__)

INTERVALS: Sequence[str] = ("5minute", "15minute", "60minute", "day")
RATE_LIMIT_SEC = 0.3


def parse_date(value: str) -> datetime:
    try:
        dt = datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:  # pragma: no cover - CLI validation
        raise SystemExit(f"Invalid --date format ({value}). Expected YYYY-MM-DD.") from exc
    return dt


def expand_engines(raw: str) -> Set[str]:
    if not raw:
        return {"fno", "options", "equity"}
    raw = raw.strip().lower()
    if raw == "all":
        return {"fno", "options", "equity"}
    parts = [part.strip() for part in raw.split(",") if part.strip()]
    valid = {"fno", "options", "equity"}
    engines = set()
    for part in parts:
        if part not in valid:
            raise SystemExit(f"Unknown engine '{part}'. Valid choices: fno, options, equity, all")
        engines.add(part)
    if not engines:
        engines = {"fno", "options", "equity"}
    return engines


def compute_fno_universe(cfg: AppConfig) -> List[str]:
    cfg_list = [str(sym).strip().upper() for sym in cfg.trading.get("fno_universe", []) if sym]
    return cfg_list or fno_underlyings()


def compute_option_underlyings(cfg: AppConfig) -> List[str]:
    cfg_list = [str(sym).strip().upper() for sym in cfg.trading.get("options_underlyings", []) if sym]
    if cfg_list:
        return cfg_list
    return compute_fno_universe(cfg)


def compute_equity_universe(cfg: AppConfig) -> List[str]:
    cfg_list = [str(sym).strip().upper() for sym in cfg.trading.get("equity_universe", []) if sym]
    if cfg_list:
        return cfg_list
    return load_equity_universe_csv()


def history_contains_date(path: Path, date_str: str) -> bool:
    if not path.exists():
        return False
    try:
        with path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ts = (row.get("timestamp") or "").strip()
                if ts.startswith(date_str):
                    return True
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed reading %s (%s); assuming missing date.", path, exc)
        return False
    return False


def write_history(path: Path, rows: List[Dict[str, float | str]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["timestamp", "open", "high", "low", "close", "volume"]
    existing: List[Dict[str, str]] = []
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("timestamp"):
                        existing.append(row)
        except Exception as exc:
            logger.warning("Failed to read existing history %s (%s); rewriting.", path, exc)
            existing = []

    combined = {row["timestamp"]: row for row in existing if "timestamp" in row}
    for row in rows:
        combined[str(row["timestamp"])] = {
            "timestamp": str(row["timestamp"]),
            "open": f"{float(row['open']):.6f}",
            "high": f"{float(row['high']):.6f}",
            "low": f"{float(row['low']):.6f}",
            "close": f"{float(row['close']):.6f}",
            "volume": f"{float(row['volume']):.6f}",
        }

    ordered = [combined[key] for key in sorted(combined.keys())]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(ordered)


def fetch_history(
    kite,
    symbol: str,
    interval: str,
    start: datetime,
    end: datetime,
) -> List[Dict[str, float | str]]:
    token = _resolve_instrument_token(kite, symbol)
    candles = kite_request(
        kite.historical_data,
        instrument_token=token,
        from_date=start,
        to_date=end,
        interval=interval,
        continuous=False,
        oi=False,
    )
    rows: List[Dict[str, float | str]] = []
    for candle in candles or []:
        ts = candle.get("date")
        timestamp = ts.isoformat() if isinstance(ts, datetime) else str(ts)
        rows.append(
            {
                "timestamp": timestamp,
                "open": float(candle.get("open", 0.0)),
                "high": float(candle.get("high", 0.0)),
                "low": float(candle.get("low", 0.0)),
                "close": float(candle.get("close", 0.0)),
                "volume": float(candle.get("volume", 0.0)),
            }
        )
    return rows


def symbols_for_engines(engines: Set[str], cfg: AppConfig, kite_client: KiteClient) -> Set[str]:
    symbols: Set[str] = set()
    if "fno" in engines or "options" in engines:
        logicals = compute_fno_universe(cfg)
        resolved = resolve_fno_symbols(logicals, kite_client=kite_client)
        symbols.update(resolved.values())
    if "equity" in engines:
        equities = compute_equity_universe(cfg)
        symbols.update(equities)
    return symbols


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill historical OHLCV for replay.")
    parser.add_argument("--date", required=True, help="Trading date (YYYY-MM-DD).")
    parser.add_argument(
        "--engines",
        default="all",
        help="Subset of engines: fno,options,equity,all (comma separated). Default: all.",
    )
    parser.add_argument(
        "--config",
        default="configs/dev.yaml",
        help="Path to YAML config (default: configs/dev.yaml).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force refetch even if data for the date already exists.",
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    setup_logging(cfg.logging)

    date_anchor = parse_date(args.date)
    date_str = date_anchor.strftime("%Y-%m-%d")
    engines = expand_engines(args.engines)

    logger.info("=== Historical backfill === date=%s engines=%s", date_str, ",".join(sorted(engines)))

    kite_env = load_kite_env()
    if not kite_env.access_token:
        logger.error("No KITE_ACCESS_TOKEN found. Run scripts.login_kite or scripts.run_day --login first.")
        raise SystemExit(1)
    kite = make_kite_client_from_env(kite_env)

    symbols = symbols_for_engines(engines, cfg, kite)
    if not symbols:
        logger.warning("No symbols resolved for engines=%s; nothing to backfill.", engines)
        return

    start_dt = date_anchor
    end_dt = date_anchor + timedelta(days=1)

    for symbol in sorted(symbols):
        for interval in INTERVALS:
            path = history_path(symbol, interval)
            if not args.force and history_contains_date(path, date_str):
                logger.info("[SKIP] %s %s already has data for %s", symbol, interval, date_str)
                continue
            rows = fetch_history(kite, symbol, interval, start_dt, end_dt)
            if not rows:
                logger.warning("[MISS] No data returned for %s interval=%s", symbol, interval)
                continue
            write_history(path, rows)
            logger.info("[BACKFILL] %s %s (%d bars)", symbol, interval, len(rows))
            time.sleep(RATE_LIMIT_SEC)


if __name__ == "__main__":
    main()
