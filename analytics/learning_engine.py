from __future__ import annotations

import csv
import json
from collections import defaultdict, Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple, Optional


def _parse_float(value: Any) -> float:
    if value in (None, "", "null"):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _max_drawdown(pnls: Iterable[float]) -> float:
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for pnl in pnls:
        cum += pnl
        peak = max(peak, cum)
        drawdown = peak - cum
        max_dd = max(max_dd, drawdown)
    return max_dd


def compute_strategy_tuning(
    orders_paths: List[Path],
    trade_paths: Optional[List[Path]] = None,
    lookback_days: int = 5,
) -> Dict[str, Dict[str, Any]]:
    trade_rows = _read_trade_rows(trade_paths or [])
    if trade_rows:
        return _compute_from_trades(trade_rows)
    metrics: Dict[Tuple[str, str], Dict[str, Any]] = defaultdict(
        lambda: {
            "num_trades": 0,
            "win_trades": 0,
            "loss_trades": 0,
            "pnl_samples": [],
            "pnl_pct_samples": [],
            "r_sum": 0.0,
            "r_count": 0,
        }
    )

    for path in orders_paths:
        if not path or not path.exists():
            continue
        try:
            with path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    symbol = (row.get("symbol") or row.get("tradingsymbol") or "").strip().upper()
                    strategy = (row.get("strategy") or "").strip()
                    if not symbol or not strategy:
                        continue
                    key = (symbol, strategy)
                    pnl = _parse_float(row.get("pnl") or row.get("realized_pnl"))
                    qty = abs(int(float(row.get("quantity") or row.get("filled_quantity") or 0)))
                    entry = _parse_float(row.get("average_price") or row.get("price"))
                    metrics[key]["num_trades"] += 1
                    if pnl > 0:
                        metrics[key]["win_trades"] += 1
                    elif pnl < 0:
                        metrics[key]["loss_trades"] += 1
                    metrics[key]["pnl_samples"].append(pnl)
                    if entry > 0 and qty > 0:
                        pnl_pct = (pnl / (entry * qty)) * 100.0
                        metrics[key]["pnl_pct_samples"].append(pnl_pct)
                    r_multiple = _parse_float(row.get("r_multiple") or row.get("r"))
                    if r_multiple != 0.0:
                        metrics[key]["r_sum"] += r_multiple
                        metrics[key]["r_count"] += 1
        except Exception:
            continue

    tuning: Dict[str, Dict[str, Any]] = {}
    for (symbol, strategy), data in metrics.items():
        num_trades = data["num_trades"]
        if num_trades == 0:
            continue
        win_rate = data["win_trades"] / max(1, num_trades)
        avg_r = data["r_sum"] / data["r_count"] if data["r_count"] else 0.0
        avg_pnl = sum(data["pnl_samples"]) / num_trades
        avg_pnl_pct = sum(data["pnl_pct_samples"]) / len(data["pnl_pct_samples"]) if data["pnl_pct_samples"] else 0.0
        max_dd = _max_drawdown(data["pnl_samples"])

        status = "active"
        risk_multiplier = 1.0
        if num_trades < 20:
            status = "insufficient_data"
        elif win_rate < 0.4 and avg_r <= 0:
            status = "disabled"
            risk_multiplier = 0.0
        elif win_rate > 0.6 and avg_r > 0:
            status = "boost"
            risk_multiplier = min(1.5, 1.0 + max(0.0, win_rate - 0.5))

        key = f"{symbol}|{strategy}"
        tuning[key] = {
            "symbol": symbol,
            "strategy": strategy,
            "num_trades": num_trades,
            "win_rate": round(win_rate, 4),
            "avg_r": round(avg_r, 4),
            "avg_pnl": round(avg_pnl, 2),
            "avg_pnl_pct": round(avg_pnl_pct, 4),
            "max_drawdown": round(max_dd, 2),
            "status": status,
            "risk_multiplier": round(risk_multiplier, 4),
        }
    return tuning


def _read_trade_rows(paths: List[Path]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for path in paths:
        if not path or not path.exists():
            continue
        try:
            with path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                rows.extend(reader)
        except Exception:
            continue
    return rows


def _compute_from_trades(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    aggregates: Dict[Tuple[str, str], Dict[str, Any]] = defaultdict(
        lambda: {
            "num_trades": 0,
            "win_trades": 0,
            "loss_trades": 0,
            "pnl_sum": 0.0,
            "pnl_pct_sum": 0.0,
            "r_sum": 0.0,
            "quality_counts": Counter(),
            "regime_counts": Counter(),
            "time_bucket_counts": Counter(),
        }
    )
    for row in rows:
        symbol = (row.get("symbol") or "").strip().upper()
        strategy = (row.get("strategy") or "").strip()
        if not symbol or not strategy:
            continue
        key = (symbol, strategy)
        realized = _parse_float(row.get("realized_pnl"))
        r_mult = _parse_float(row.get("r_multiple"))
        realized_pct = _parse_float(row.get("realized_pnl_pct"))
        quality = (row.get("quality_tag") or "").upper()
        regime = (row.get("regime_tag") or "").lower()
        bucket = (row.get("time_of_day_bucket") or "").lower()
        aggregates[key]["num_trades"] += 1
        if realized > 0:
            aggregates[key]["win_trades"] += 1
        elif realized < 0:
            aggregates[key]["loss_trades"] += 1
        aggregates[key]["pnl_sum"] += realized
        aggregates[key]["pnl_pct_sum"] += realized_pct
        aggregates[key]["r_sum"] += r_mult
        aggregates[key]["quality_counts"][quality] += 1
        aggregates[key]["regime_counts"][regime] += 1
        aggregates[key]["time_bucket_counts"][bucket] += 1

    tuning: Dict[str, Dict[str, Any]] = {}
    for (symbol, strategy), data in aggregates.items():
        trades = data["num_trades"]
        if trades == 0:
            continue
        win_rate = data["win_trades"] / max(1, trades)
        avg_r = data["r_sum"] / trades if trades else 0.0
        avg_pnl = data["pnl_sum"] / trades
        avg_pct = data["pnl_pct_sum"] / trades
        quality_counts: Counter = data["quality_counts"]
        regime_counts: Counter = data["regime_counts"]
        time_counts: Counter = data["time_bucket_counts"]
        quality_a = quality_counts.get("A", 0) / trades
        quality_c = quality_counts.get("C", 0) / trades
        bad_regime = (
            (regime_counts.get("choppy", 0) + regime_counts.get("volatile", 0)) / trades
        )
        status = "active"
        risk_multiplier = 1.0
        if trades < 20:
            status = "insufficient_data"
        elif win_rate < 0.4 and avg_r <= 0:
            status = "disabled"
            risk_multiplier = 0.0
        elif win_rate > 0.6 and avg_r > 0:
            status = "boost"
            risk_multiplier = min(1.5, 1.0 + max(0.0, win_rate - 0.5))
        key = f"{symbol}|{strategy}"
        tuning[key] = {
            "symbol": symbol,
            "strategy": strategy,
            "num_trades": trades,
            "win_rate": round(win_rate, 4),
            "avg_r": round(avg_r, 4),
            "avg_pnl": round(avg_pnl, 2),
            "avg_pnl_pct": round(avg_pct, 4),
            "quality_A_frac": round(quality_a, 4),
            "quality_C_frac": round(quality_c, 4),
            "bad_regime_frac": round(bad_regime, 4),
            "time_bucket_open_frac": round(time_counts.get("open", 0) / trades, 4),
            "time_bucket_mid_frac": round(time_counts.get("mid", 0) / trades, 4),
            "time_bucket_close_frac": round(time_counts.get("close", 0) / trades, 4),
            "status": status,
            "risk_multiplier": round(risk_multiplier, 4),
        }
    return tuning


def write_tuning_json(tuning: Dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(tuning, indent=2, sort_keys=True), encoding="utf-8")


def load_tuning(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
