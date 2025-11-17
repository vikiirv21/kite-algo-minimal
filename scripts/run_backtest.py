from __future__ import annotations

if __name__ == "__main__" and __package__ is None:
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).resolve().parents[1]))

import argparse
import csv
import json
import logging
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from broker.backtest_broker import BacktestBroker
from core.config import AppConfig, load_config
from core.risk_engine import RiskAction, RiskEngine
from core.state_store import make_fresh_state_from_config
from core.strategy_engine import StrategyRunner
from core.strategy_registry import STRATEGY_REGISTRY
from data.backtest_data import LocalCSVHistoricalSource

logger = logging.getLogger("scripts.run_backtest")

BASE_DIR = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = BASE_DIR / "artifacts"
BACKTEST_DIR = ARTIFACTS_DIR / "backtests"
BACKTEST_DIR.mkdir(parents=True, exist_ok=True)


class BacktestSession:
    def __init__(
        self,
        *,
        cfg: AppConfig,
        capital: float,
        symbols: Sequence[str],
        logical_alias: Dict[str, str],
        strategies: Sequence[str],
        default_qty: int,
    ) -> None:
        self.cfg = cfg
        self.capital = capital
        self.symbols = list({sym.upper() for sym in symbols})
        self.logical_alias = {k.upper(): v for k, v in logical_alias.items()}
        self.state = make_fresh_state_from_config(cfg)
        self.state["mode"] = "BACKTEST"
        self.state["universe"] = {"symbols": self.symbols, "meta": self.logical_alias}
        self.broker = BacktestBroker(starting_cash=capital)
        self.strategy_codes = list(strategies) or _enabled_strategy_codes()
        if not self.strategy_codes:
            self.strategy_codes = ["ema20_50_intraday"]
        self.default_strategy_code = self.strategy_codes[0]
        self.strategy_runner = StrategyRunner(
            None, self, allowed_strategies=self.strategy_codes
        )
        self.default_qty = max(1, default_qty)
        self.current_timestamp: Optional[datetime] = None
        trading_cfg = getattr(cfg, "trading", {}) or {}
        risk_cfg = {
            "capital": capital,
            "per_trade_risk_pct": trading_cfg.get("risk_per_trade_pct", 0.0),
            "max_daily_loss_abs": trading_cfg.get("max_daily_loss"),
            "max_daily_loss_pct": trading_cfg.get("max_daily_loss_pct"),
            "max_positions_total": trading_cfg.get("max_positions_total"),
            "max_positions_per_symbol": trading_cfg.get("max_positions_per_symbol"),
            "min_seconds_between_entries": trading_cfg.get("min_seconds_between_entries"),
        }
        self.risk_engine = RiskEngine(risk_cfg, self.state, logger)

    def on_candle(self, ts: datetime, price_map: Dict[str, Dict[str, float]]) -> None:
        self.current_timestamp = ts
        ticks: Dict[str, Dict[str, float]] = {}
        for symbol, candle in price_map.items():
            price = float(candle.get("close") or 0.0)
            if price <= 0:
                continue
            symbol_upper = symbol.upper()
            self.broker.update_mark(symbol_upper, price)
            ticks[symbol_upper] = {"close": price}
        if ticks:
            self.broker.record_equity_snapshot(ts)
            self.strategy_runner.run(ticks)

    def _portfolio_state(self) -> Dict[str, float]:
        state = self.broker.portfolio_state()
        state["capital"] = self.capital
        return state

    def _strategy_state(self, code: str) -> Dict[str, float]:
        strategies = self.state.get("strategies") or {}
        entry = strategies.get(code)
        if isinstance(entry, dict):
            return entry
        return {}

    def _handle_signal(
        self,
        symbol: str,
        signal: str,
        price: float,
        logical: Optional[str] = None,
        *,
        tf: str = "",
        profile: str = "",
        signal_timestamp: str = "",
        mode: str = "",
        strategy_name: Optional[str] = None,
        strategy_code: Optional[str] = None,
        confidence: Optional[float] = None,
        playbook: str = "",
        reason: str = "",
    ) -> None:
        if signal not in ("BUY", "SELL"):
            return
        if price <= 0 or self.current_timestamp is None:
            return

        logical_name = logical or self.logical_alias.get(symbol, symbol)
        strategy_code_value = strategy_code or self.default_strategy_code
        quantity = self.default_qty

        order_intent = {
            "symbol": symbol,
            "side": signal,
            "price": price,
            "quantity": quantity,
            "logical": logical_name,
        }
        decision = self.risk_engine.check_order(
            order_intent,
            self._portfolio_state(),
            self._strategy_state(strategy_code_value),
        )
        if decision.action == RiskAction.HALT_SESSION:
            logger.warning("Backtest risk engine halted session: %s", decision.reason)
            return
        if decision.action == RiskAction.BLOCK:
            logger.debug(
                "Order blocked by risk engine (%s %s): %s",
                signal,
                symbol,
                decision.reason,
            )
            return
        if decision.action == RiskAction.REDUCE and decision.adjusted_qty:
            quantity = decision.adjusted_qty
            if quantity <= 0:
                return

        fill = self.broker.execute_order(
            timestamp=self.current_timestamp,
            symbol=symbol,
            side=signal,
            quantity=quantity,
            price=price,
            strategy=strategy_code_value,
        )
        self._record_fill(strategy_code_value, fill.realized_pnl)

    def _record_fill(self, strategy_code: str, realized_pnl: float) -> None:
        strategies = self.state.setdefault("strategies", {})
        metrics = strategies.setdefault(
            strategy_code,
            {"day_pnl": 0.0, "entry_count": 0, "exit_count": 0, "open_trades": 0},
        )
        metrics["day_pnl"] = metrics.get("day_pnl", 0.0) + realized_pnl

    def update_aliases(self, mapping: Dict[str, str]) -> None:
        for sym, logical in mapping.items():
            self.logical_alias[sym.upper()] = logical

    def build_result(
        self,
        *,
        strategy_code: str,
        start: date,
        end: date,
        config_meta: Dict[str, Any],
    ) -> Dict[str, Any]:
        equity_points = self.broker.equity_series()
        if not equity_points:
            self.broker.record_equity_snapshot(datetime.combine(start, datetime.min.time()))
            equity_points = self.broker.equity_series()

        peak = max((pt.get("equity", 0.0) for pt in equity_points), default=self.capital)
        max_drawdown = self.broker.max_drawdown()
        max_drawdown_pct = (max_drawdown / peak * 100.0) if peak else 0.0

        trades = [asdict(trade) for trade in getattr(self.broker, "trades", [])]
        total_pnl = sum(float(trade.get("pnl", 0.0)) for trade in trades)
        wins = sum(1 for trade in trades if float(trade.get("pnl", 0.0)) > 0)
        losses = sum(1 for trade in trades if float(trade.get("pnl", 0.0)) < 0)
        total_trades = len(trades)
        win_rate = (wins / total_trades * 100.0) if total_trades else 0.0

        equity_curve = [
            [point.get("ts"), float(point.get("equity", 0.0))]
            for point in equity_points
        ]

        summary = {
            "total_pnl": total_pnl,
            "win_rate": win_rate,
            "total_trades": total_trades,
            "wins": wins,
            "losses": losses,
            "max_drawdown": max_drawdown,
            "max_drawdown_pct": max_drawdown_pct,
        }

        config_payload = {
            "from": start.isoformat(),
            "to": end.isoformat(),
            "capital": self.capital,
            "symbols": sorted(self.symbols),
            **config_meta,
        }

        return {
            "strategy": strategy_code,
            "config": config_payload,
            "summary": summary,
            "equity_curve": equity_curve,
            "trades": trades,
        }


def _enabled_strategy_codes() -> List[str]:
    return [code for code, info in STRATEGY_REGISTRY.items() if info.enabled]


def _parse_codes(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def _daterange(start: date, end: date) -> Iterable[date]:
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


def _load_scanner(day: date) -> Optional[Dict[str, Any]]:
    path = ARTIFACTS_DIR / "scanner" / day.isoformat() / "universe.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to read scanner universe %s: %s", path, exc)
        return None


def _resolve_symbols(
    scanner_payload: Optional[Dict[str, Any]], requested: Sequence[str]
) -> tuple[List[str], Dict[str, str]]:
    logical_alias: Dict[str, str] = {}
    symbols: List[str] = []
    meta = {}
    if isinstance(scanner_payload, dict):
        meta = scanner_payload.get("meta") or {}
    requested_clean = [sym.strip().upper() for sym in requested if sym.strip()]

    if requested_clean:
        for logical in requested_clean:
            candidate = meta.get(logical, {})
            tradingsymbol = candidate.get("tradingsymbol") or logical
            symbols.append(tradingsymbol.upper())
            logical_alias[tradingsymbol.upper()] = logical
    elif isinstance(scanner_payload, dict):
        for logical in scanner_payload.get("fno", []):
            entry = meta.get(logical, {})
            tradingsymbol = entry.get("tradingsymbol") or logical
            symbols.append(tradingsymbol.upper())
            logical_alias[tradingsymbol.upper()] = logical
    symbols = list(dict.fromkeys(symbols))
    if not logical_alias:
        logical_alias = {sym: sym for sym in symbols}
    return symbols, logical_alias


def _write_csv(path: Path, rows: Iterable[dict], fieldnames: Sequence[str]) -> None:
    rows = list(rows)
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backtest / Replay engine runner.")
    parser.add_argument("--config", default="configs/dev.yaml", help="Path to config file.")
    parser.add_argument("--from-date", required=True, help="Start date (YYYY-MM-DD).")
    parser.add_argument("--to-date", required=True, help="End date (YYYY-MM-DD).")
    parser.add_argument(
        "--symbols",
        default="",
        help="Comma separated logical symbols to backtest (defaults to scanner universe).",
    )
    parser.add_argument(
        "--strategies",
        default="",
        help="Comma separated strategy codes to run (defaults to enabled registry entries).",
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=1_000_000.0,
        help="Starting capital for the backtest.",
    )
    parser.add_argument(
        "--qty",
        type=int,
        default=1,
        help="Default order quantity per trade.",
    )
    parser.add_argument(
        "--data-root",
        default=None,
        help="Optional override for historical data root.",
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    args = parse_args()
    cfg = load_config(args.config)
    start = datetime.strptime(args.from_date, "%Y-%m-%d").date()
    end = datetime.strptime(args.to_date, "%Y-%m-%d").date()
    requested_symbols = _parse_codes(args.symbols)
    requested_strategies = _parse_codes(args.strategies)
    if not requested_strategies:
        requested_strategies = _enabled_strategy_codes()
    if len(requested_strategies) != 1:
        logger.error(
            "Backtest runner expects exactly one strategy (got: %s).",
            ", ".join(requested_strategies),
        )
        return
    strategy_code = requested_strategies[0]
    data_source = LocalCSVHistoricalSource(args.data_root)

    day_configs: List[Dict[str, Any]] = []
    union_symbols: Dict[str, str] = {}
    for day in _daterange(start, end):
        scanner_payload = _load_scanner(day)
        symbols, logical_alias = _resolve_symbols(scanner_payload, requested_symbols)
        if not symbols:
            logger.warning("No symbols resolved for %s; skipping.", day)
            continue
        for sym in symbols:
            union_symbols[sym] = logical_alias.get(sym, sym)
        day_configs.append({"day": day, "symbols": symbols, "alias": logical_alias})

    if not day_configs:
        logger.error("No days in the requested range produced symbols to backtest.")
        return

    session = BacktestSession(
        cfg=cfg,
        capital=args.capital,
        symbols=list(union_symbols.keys()),
        logical_alias=union_symbols,
        strategies=[strategy_code],
        default_qty=args.qty,
    )
    session.broker.record_equity_snapshot(datetime.combine(start, datetime.min.time()))

    for cfg_day in day_configs:
        session.update_aliases(cfg_day["alias"])
        had_data = False
        for ts, price_map in data_source.iter_day(cfg_day["symbols"], cfg_day["day"]):
            had_data = True
            session.on_candle(ts, price_map)
        if not had_data:
            logger.warning("No historical data available for %s.", cfg_day["day"])

    config_meta = {
        "config_path": args.config,
    }
    result = session.build_result(
        strategy_code=strategy_code,
        start=start,
        end=end,
        config_meta=config_meta,
    )

    run_id = datetime.utcnow().strftime("%Y-%m-%d_%H%M")
    run_dir = BACKTEST_DIR / strategy_code / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    result_path = run_dir / "result.json"
    result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    _write_csv(
        run_dir / "orders.csv",
        (asdict(order) for order in session.broker.orders),
        ["ts", "symbol", "side", "quantity", "price", "strategy", "status"],
    )
    _write_csv(
        run_dir / "fills.csv",
        (asdict(fill) for fill in session.broker.fills),
        ["ts", "symbol", "side", "quantity", "price", "realized_pnl", "strategy"],
    )

    logger.info("Backtest result written to %s", result_path)


if __name__ == "__main__":
    main()
