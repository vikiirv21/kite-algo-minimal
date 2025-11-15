#!/usr/bin/env python3
"""
Backtest Runner v1 - Clean implementation using MarketDataEngine.replay()

This script runs backtests using historical candle data from MarketDataEngine,
integrating with StrategyEngine and RiskEngine to simulate trades.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from dataclasses import asdict
from datetime import datetime, date, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

# Add parent directory to path
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from broker.backtest_broker import BacktestBroker
from core.config import AppConfig, load_config
from core.market_data_engine import MarketDataEngine
from core.risk_engine import RiskAction, RiskEngine, build_risk_config
from core.state_store import make_fresh_state_from_config
from core.strategy_engine import StrategyRunner
from core.strategy_registry import STRATEGY_REGISTRY
from core.universe_builder import load_universe
from data.instruments import resolve_fno_symbols
from types import SimpleNamespace

# Strategy Engine v2 support (optional)
try:
    from core.strategy_engine_v2 import StrategyEngineV2, StrategyState
    from strategies.ema20_50_intraday_v2 import EMA2050IntradayV2
    STRATEGY_ENGINE_V2_AVAILABLE = True
except ImportError:
    STRATEGY_ENGINE_V2_AVAILABLE = False
    StrategyEngineV2 = None
    StrategyState = None

logger = logging.getLogger(__name__)

ARTIFACTS_DIR = BASE_DIR / "artifacts"
BACKTEST_DIR = ARTIFACTS_DIR / "backtests"
BACKTEST_DIR.mkdir(parents=True, exist_ok=True)


class BacktestEngine:
    """
    Backtest engine that replays historical candles and simulates trading.
    """

    def __init__(
        self,
        *,
        cfg: AppConfig,
        capital: float,
        symbol: str,
        logical_name: str,
        strategy_code: str,
        default_qty: int,
        market_data_engine: MarketDataEngine,
    ) -> None:
        self.cfg = cfg
        self.capital = capital
        self.symbol = symbol.upper()
        self.logical_name = logical_name
        self.strategy_code = strategy_code
        self.default_qty = max(1, default_qty)
        self.market_data_engine = market_data_engine

        # Initialize state
        self.state = make_fresh_state_from_config(cfg)
        self.state["mode"] = "BACKTEST"
        
        # Initialize broker
        self.broker = BacktestBroker(starting_cash=capital)
        
        # Determine if we should use Strategy Engine v2
        strategy_engine_config = cfg.raw.get("strategy_engine", {})
        use_v2 = (
            strategy_engine_config.get("version", 1) == 2 
            and STRATEGY_ENGINE_V2_AVAILABLE
            and strategy_code.endswith("_v2")
        )
        
        if use_v2:
            # Initialize Strategy Engine v2
            logger.info("Backtest using Strategy Engine v2")
            v2_config = {
                "history_lookback": strategy_engine_config.get("window_size", 200),
                "strategies": [strategy_code],
                "timeframe": "5m",  # Will be overridden by run() call
            }
            self.strategy_engine_v2 = StrategyEngineV2(
                v2_config,
                market_data_engine,
                risk_engine=None,
                logger_instance=logger
            )
            self.strategy_engine_v2.set_paper_engine(self)
            
            # Register v2 strategy
            if strategy_code == "ema20_50_intraday_v2":
                state = StrategyState()
                strategy_config = {
                    "name": strategy_code,
                    "timeframe": "5m",
                    "ema_fast": 20,
                    "ema_slow": 50,
                }
                strategy = EMA2050IntradayV2(strategy_config, state)
                self.strategy_engine_v2.register_strategy(strategy_code, strategy)
            
            self.strategy_runner = None
        else:
            # Initialize Strategy Engine v1
            logger.info("Backtest using Strategy Engine v1")
            self.strategy_runner = StrategyRunner(
                None,
                self,
                allowed_strategies=[strategy_code],
                market_data_engine=market_data_engine,
            )
            self.strategy_engine_v2 = None
        
        # Initialize risk engine
        risk_cfg_dict = cfg.risk or {}
        self.risk_engine = RiskEngine(risk_cfg_dict, self.state, logger)
        
        # Tracking
        self.current_timestamp: Optional[datetime] = None
        self.logical_alias = {self.symbol: self.logical_name}

    def run(
        self,
        *,
        timeframe: str,
        from_date: str,
        to_date: str,
    ) -> None:
        """
        Run backtest by replaying candles from MarketDataEngine.
        
        Args:
            timeframe: Candle timeframe (e.g., "1m", "5m", "15m")
            from_date: Start date in ISO format (YYYY-MM-DD)
            to_date: End date in ISO format (YYYY-MM-DD)
        """
        logger.info(
            "Starting backtest: %s on %s (%s) from %s to %s",
            self.strategy_code,
            self.symbol,
            timeframe,
            from_date,
            to_date,
        )
        
        # Convert dates to ISO timestamps for replay
        start_ts = f"{from_date}T00:00:00+00:00"
        end_ts = f"{to_date}T23:59:59+00:00"
        
        # Record initial equity
        start_dt = datetime.fromisoformat(start_ts)
        self.broker.record_equity_snapshot(start_dt)
        
        # Replay candles
        candle_count = 0
        try:
            for candle in self.market_data_engine.replay(
                self.symbol, timeframe, start_ts, end_ts
            ):
                candle_count += 1
                self._process_candle(candle)
        except Exception as exc:
            logger.exception("Error during backtest replay: %s", exc)
            raise
        
        logger.info(
            "Backtest complete: processed %d candles, %d trades",
            candle_count,
            len(self.broker.trades),
        )

    def _process_candle(self, candle: Dict[str, Any]) -> None:
        """Process a single candle by updating prices and running strategies."""
        try:
            # Parse timestamp
            ts_str = candle.get("ts")
            if not ts_str:
                return
            
            ts = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
            self.current_timestamp = ts
            
            # Extract price
            close_price = float(candle.get("close", 0.0))
            if close_price <= 0:
                return
            
            # Update broker with current price
            self.broker.update_mark(self.symbol, close_price)
            
            # Record equity snapshot
            self.broker.record_equity_snapshot(ts)
            
            # Create tick for strategy
            ticks = {self.symbol: {"close": close_price}}
            
            # Run strategies (v1 or v2)
            if self.strategy_engine_v2:
                # Use Strategy Engine v2
                self.strategy_engine_v2.run([self.symbol], timeframe)
            elif self.strategy_runner:
                # Use Strategy Engine v1
                self.strategy_runner.run(ticks)
            
        except Exception as exc:
            logger.warning("Error processing candle at %s: %s", candle.get("ts"), exc)

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
        **kwargs: Any,
    ) -> None:
        """
        Handle trading signal from strategy.
        Called by StrategyRunner when a strategy generates a signal.
        """
        if signal not in ("BUY", "SELL"):
            return
        
        if price <= 0 or self.current_timestamp is None:
            return
        
        quantity = self.default_qty
        strategy_code_value = strategy_code or self.strategy_code
        
        # Create order intent
        order_intent = {
            "symbol": symbol,
            "side": signal,
            "price": price,
            "quantity": quantity,
            "logical": logical or self.logical_name,
        }
        
        # Get portfolio and strategy state for risk check
        portfolio_state = self._get_portfolio_state()
        strategy_state = self._get_strategy_state(strategy_code_value)
        
        # Risk engine check
        decision = self.risk_engine.check_order(
            order_intent,
            portfolio_state,
            strategy_state,
        )
        
        if decision.action == RiskAction.HALT_SESSION:
            logger.warning("Risk engine halted session: %s", decision.reason)
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
        
        # Execute order
        try:
            fill = self.broker.execute_order(
                timestamp=self.current_timestamp,
                symbol=symbol,
                side=signal,
                quantity=quantity,
                price=price,
                strategy=strategy_code_value,
            )
            
            # Update strategy metrics
            self._record_fill(strategy_code_value, fill.realized_pnl)
            
            logger.debug(
                "Order filled: %s %d x %s @ %.2f (pnl: %.2f)",
                signal,
                quantity,
                symbol,
                price,
                fill.realized_pnl,
            )
        except Exception as exc:
            logger.warning("Failed to execute order: %s", exc)

    def _get_portfolio_state(self) -> Dict[str, float]:
        """Get current portfolio state for risk engine."""
        state = self.broker.portfolio_state()
        state["capital"] = self.capital
        return state

    def _get_strategy_state(self, code: str) -> Dict[str, Any]:
        """Get strategy metrics from state."""
        strategies = self.state.get("strategies") or {}
        entry = strategies.get(code)
        if isinstance(entry, dict):
            return entry
        return {}

    def _record_fill(self, strategy_code: str, realized_pnl: float) -> None:
        """Record fill in strategy metrics."""
        strategies = self.state.setdefault("strategies", {})
        metrics = strategies.setdefault(
            strategy_code,
            {"day_pnl": 0.0, "entry_count": 0, "exit_count": 0, "open_trades": 0},
        )
        metrics["day_pnl"] = metrics.get("day_pnl", 0.0) + realized_pnl

    def build_result(
        self,
        *,
        timeframe: str,
        from_date: str,
        to_date: str,
    ) -> Dict[str, Any]:
        """Build backtest result summary."""
        equity_points = self.broker.equity_series()
        
        # Calculate metrics
        peak = max(
            (pt.get("equity", 0.0) for pt in equity_points),
            default=self.capital
        )
        max_drawdown = self.broker.max_drawdown()
        max_drawdown_pct = (max_drawdown / peak * 100.0) if peak else 0.0
        
        # Trade statistics
        trades = [asdict(trade) for trade in getattr(self.broker, "trades", [])]
        total_pnl = sum(float(trade.get("pnl", 0.0)) for trade in trades)
        wins = sum(1 for trade in trades if float(trade.get("pnl", 0.0)) > 0)
        losses = sum(1 for trade in trades if float(trade.get("pnl", 0.0)) < 0)
        total_trades = len(trades)
        win_rate = (wins / total_trades * 100.0) if total_trades else 0.0
        
        # Equity curve
        equity_curve = [
            [point.get("ts"), float(point.get("equity", 0.0))]
            for point in equity_points
        ]
        
        # Summary
        summary = {
            "total_pnl": round(total_pnl, 2),
            "win_rate": round(win_rate, 2),
            "total_trades": total_trades,
            "wins": wins,
            "losses": losses,
            "max_drawdown": round(max_drawdown, 2),
            "max_drawdown_pct": round(max_drawdown_pct, 2),
            "final_equity": round(self.broker.cash + sum(
                pos.last_price * pos.quantity
                for pos in self.broker.positions.values()
            ), 2),
        }
        
        # Configuration
        config_payload = {
            "symbol": self.symbol,
            "logical_name": self.logical_name,
            "timeframe": timeframe,
            "from": from_date,
            "to": to_date,
            "capital": self.capital,
            "strategy": self.strategy_code,
        }
        
        return {
            "strategy": self.strategy_code,
            "config": config_payload,
            "summary": summary,
            "equity_curve": equity_curve,
            "trades": trades,
        }


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Backtest Runner v1 - Run strategy backtests using MarketDataEngine"
    )
    parser.add_argument(
        "--config",
        default="configs/dev.yaml",
        help="Path to config YAML file (default: configs/dev.yaml)",
    )
    parser.add_argument(
        "--strategy",
        required=True,
        help="Strategy code from core.strategy_registry (e.g., 'ema20_50_intraday')",
    )
    parser.add_argument(
        "--symbol",
        required=True,
        help="Logical symbol (e.g., 'NIFTY', 'BANKNIFTY')",
    )
    parser.add_argument(
        "--from",
        dest="from_date",
        required=True,
        help="Start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--to",
        dest="to_date",
        required=True,
        help="End date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--timeframe",
        default=None,
        help="Candle timeframe (e.g., '1m', '5m', '15m'). Defaults to strategy's default timeframe",
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=1_000_000.0,
        help="Starting capital (default: 1,000,000)",
    )
    parser.add_argument(
        "--qty",
        type=int,
        default=1,
        help="Default order quantity per trade (default: 1)",
    )
    return parser.parse_args()


def resolve_symbol(logical: str, kite_client: Optional[Any] = None) -> str:
    """
    Resolve logical symbol to tradingsymbol using universe snapshot or FnO resolver.
    
    Args:
        logical: Logical symbol like "NIFTY" or "BANKNIFTY"
        kite_client: Optional Kite client for FnO resolution
        
    Returns:
        Resolved tradingsymbol
    """
    # Try to load from universe snapshot first
    universe = load_universe()
    if isinstance(universe, dict):
        meta = universe.get("meta") or {}
        if logical.upper() in meta:
            entry = meta[logical.upper()]
            if isinstance(entry, dict):
                tradingsymbol = entry.get("tradingsymbol")
                if tradingsymbol:
                    logger.info(
                        "Resolved %s -> %s from universe snapshot",
                        logical,
                        tradingsymbol,
                    )
                    return tradingsymbol.upper()
    
    # Fallback: try FnO resolution if client available
    if kite_client:
        try:
            shim = SimpleNamespace(api=kite_client)
            symbol_map = resolve_fno_symbols([logical.upper()], kite_client=shim)
            if logical.upper() in symbol_map:
                resolved = symbol_map[logical.upper()]
                logger.info("Resolved %s -> %s via FnO resolver", logical, resolved)
                return resolved.upper()
        except Exception as exc:
            logger.warning("FnO resolution failed: %s", exc)
    
    # Fallback: return as-is
    logger.info("Using logical symbol as-is: %s", logical)
    return logical.upper()


def write_csv(path: Path, rows: Sequence[dict], fieldnames: Sequence[str]) -> None:
    """Write rows to CSV file."""
    rows = list(rows)
    if not rows:
        return
    
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> None:
    """Main entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    
    args = parse_args()
    
    # Validate strategy
    if args.strategy not in STRATEGY_REGISTRY:
        logger.error(
            "Strategy '%s' not found in registry. Available: %s",
            args.strategy,
            ", ".join(STRATEGY_REGISTRY.keys()),
        )
        sys.exit(1)
    
    strategy_info = STRATEGY_REGISTRY[args.strategy]
    
    # Determine timeframe
    timeframe = args.timeframe or strategy_info.timeframe
    
    # Load configuration
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = (BASE_DIR / config_path).resolve()
    
    if not config_path.exists():
        logger.error("Config file not found: %s", config_path)
        sys.exit(1)
    
    cfg = load_config(str(config_path))
    
    # Resolve symbol (without Kite client for now - uses universe snapshot)
    resolved_symbol = resolve_symbol(args.symbol, kite_client=None)
    
    # Initialize MarketDataEngine
    universe_snapshot = load_universe()
    cache_dir = ARTIFACTS_DIR / "market_data"
    mde = MarketDataEngine(None, universe_snapshot, cache_dir=cache_dir)
    
    logger.info(
        "Initialized MarketDataEngine with cache_dir=%s",
        cache_dir,
    )
    
    # Create backtest engine
    engine = BacktestEngine(
        cfg=cfg,
        capital=args.capital,
        symbol=resolved_symbol,
        logical_name=args.symbol,
        strategy_code=args.strategy,
        default_qty=args.qty,
        market_data_engine=mde,
    )
    
    # Run backtest
    try:
        engine.run(
            timeframe=timeframe,
            from_date=args.from_date,
            to_date=args.to_date,
        )
    except Exception as exc:
        logger.exception("Backtest failed: %s", exc)
        sys.exit(1)
    
    # Build results
    result = engine.build_result(
        timeframe=timeframe,
        from_date=args.from_date,
        to_date=args.to_date,
    )
    
    # Create run ID
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    run_id = f"{args.strategy}_{args.symbol}_{timeframe}_{args.from_date}_{args.to_date}_{timestamp}"
    
    # Create output directory
    run_dir = BACKTEST_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    
    # Write result.json
    result_path = run_dir / "result.json"
    result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    
    # Write orders.csv
    write_csv(
        run_dir / "orders.csv",
        [asdict(order) for order in engine.broker.orders],
        ["ts", "symbol", "side", "quantity", "price", "strategy", "status"],
    )
    
    # Write fills.csv
    write_csv(
        run_dir / "fills.csv",
        [asdict(fill) for fill in engine.broker.fills],
        ["ts", "symbol", "side", "quantity", "price", "realized_pnl", "strategy"],
    )
    
    # Write trades.csv
    if engine.broker.trades:
        write_csv(
            run_dir / "trades.csv",
            [asdict(trade) for trade in engine.broker.trades],
            ["timestamp", "symbol", "side", "qty", "entry_price", "exit_price", "pnl", "holding_time", "strategy_code"],
        )
    
    # Print summary
    summary = result["summary"]
    logger.info("")
    logger.info("=" * 70)
    logger.info("BACKTEST RESULTS")
    logger.info("=" * 70)
    logger.info("Run ID:           %s", run_id)
    logger.info("Strategy:         %s", args.strategy)
    logger.info("Symbol:           %s (%s)", resolved_symbol, args.symbol)
    logger.info("Timeframe:        %s", timeframe)
    logger.info("Period:           %s to %s", args.from_date, args.to_date)
    logger.info("-" * 70)
    logger.info("Starting Capital: ₹%,.2f", args.capital)
    logger.info("Final Equity:     ₹%,.2f", summary["final_equity"])
    logger.info("Total P&L:        ₹%,.2f", summary["total_pnl"])
    logger.info("Max Drawdown:     ₹%,.2f (%.2f%%)", summary["max_drawdown"], summary["max_drawdown_pct"])
    logger.info("-" * 70)
    logger.info("Total Trades:     %d", summary["total_trades"])
    logger.info("Wins:             %d", summary["wins"])
    logger.info("Losses:           %d", summary["losses"])
    logger.info("Win Rate:         %.2f%%", summary["win_rate"])
    logger.info("=" * 70)
    logger.info("Results saved to: %s", run_dir)
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
