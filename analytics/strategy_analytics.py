"""
Strategy Analytics Engine v1 (SAE v1)

Computes daily and historical performance metrics for:
- strategies
- symbols
- equity curves
- drawdowns

Unified analytics for paper trading, live trading, and backtests.
"""

from __future__ import annotations

import csv
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class StrategyAnalyticsEngine:
    """
    Strategy Analytics Engine v1 - computes performance metrics from journal data.
    """

    def __init__(
        self,
        journal_store: Any,
        state_store: Any,
        logger: logging.Logger,
        config: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize the analytics engine.

        Args:
            journal_store: JournalStateStore with order & fill logs
            state_store: StateStore for reading last checkpoint
            logger: Logger instance
            config: YAML config (analytics section optional)
        """
        self.journal_store = journal_store
        self.state_store = state_store
        self.logger = logger
        self.config = config or {}
        self.fills: List[Dict[str, Any]] = []

    def load_fills(self, today_only: bool = True) -> List[Dict[str, Any]]:
        """
        Load today's and/or historical fills into a list of dicts.

        Args:
            today_only: If True, load only today's fills. Otherwise load all historical.

        Returns:
            List of fill dictionaries with keys: timestamp, symbol, strategy, side, qty, price, pnl, etc.
        """
        fills: List[Dict[str, Any]] = []

        try:
            journal_dir = self.journal_store.journal_dir
            if not journal_dir.exists():
                self.logger.warning("Journal directory does not exist: %s", journal_dir)
                return fills

            if today_only:
                # Load only today's orders.csv
                today_path = self.journal_store.latest_journal_path_for_today()
                if today_path.exists():
                    fills.extend(self._read_csv_file(today_path))
            else:
                # Load all historical orders.csv files
                for csv_path in sorted(journal_dir.glob("*/orders.csv")):
                    fills.extend(self._read_csv_file(csv_path))

        except Exception as exc:
            self.logger.error("Failed to load fills: %s", exc, exc_info=True)

        self.fills = fills
        self.logger.info("Loaded %d fills (today_only=%s)", len(fills), today_only)
        return fills

    def _read_csv_file(self, path: Path) -> List[Dict[str, Any]]:
        """Read a CSV file and return list of dicts."""
        rows = []
        try:
            with path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    # Filter for filled orders only
                    status = (row.get("status") or "").upper()
                    if status in {"COMPLETE", "FILLED", "EXECUTED", "SUCCESS"}:
                        rows.append(dict(row))
        except Exception as exc:
            self.logger.warning("Failed reading CSV %s: %s", path, exc)
        return rows

    def compute_daily_metrics(self) -> Dict[str, Any]:
        """
        Compute daily metrics:
          - realized_pnl
          - num_trades
          - win_rate
          - loss_rate
          - avg_win
          - avg_loss
          - pnl_distribution

        Returns:
            Dictionary with daily metrics
        """
        if not self.fills:
            return {
                "realized_pnl": 0.0,
                "num_trades": 0,
                "win_rate": 0.0,
                "loss_rate": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "pnl_distribution": {"wins": 0, "losses": 0, "breakeven": 0},
                "biggest_winner": 0.0,
                "biggest_loser": 0.0,
            }

        # Group fills into trades (pair entries/exits)
        trades = self._reconstruct_trades(self.fills)
        
        realized_pnl = sum(t["pnl"] for t in trades)
        num_trades = len(trades)
        
        wins = [t["pnl"] for t in trades if t["pnl"] > 0]
        losses = [t["pnl"] for t in trades if t["pnl"] < 0]
        breakeven = [t["pnl"] for t in trades if t["pnl"] == 0]
        
        win_rate = len(wins) / num_trades if num_trades > 0 else 0.0
        loss_rate = len(losses) / num_trades if num_trades > 0 else 0.0
        
        avg_win = sum(wins) / len(wins) if wins else 0.0
        avg_loss = sum(losses) / len(losses) if losses else 0.0
        
        biggest_winner = max(wins) if wins else 0.0
        biggest_loser = min(losses) if losses else 0.0

        return {
            "realized_pnl": round(realized_pnl, 2),
            "num_trades": num_trades,
            "win_rate": round(win_rate * 100, 2),
            "loss_rate": round(loss_rate * 100, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "pnl_distribution": {
                "wins": len(wins),
                "losses": len(losses),
                "breakeven": len(breakeven),
            },
            "biggest_winner": round(biggest_winner, 2),
            "biggest_loser": round(biggest_loser, 2),
        }

    def compute_strategy_metrics(self) -> Dict[str, Dict[str, Any]]:
        """
        Return metrics per strategy:
          strategy_code: {
             'trades': int,
             'wins': int,
             'losses': int,
             'win_rate': float,
             'avg_win': float,
             'avg_loss': float,
             'profit_factor': float,
             'realized_pnl': float,
             'max_drawdown': float,
             'equity_curve': list,
          }

        Returns:
            Dictionary mapping strategy codes to their metrics
        """
        if not self.fills:
            return {}

        strategy_trades: Dict[str, List[Dict[str, Any]]] = {}
        
        # Group trades by strategy
        trades = self._reconstruct_trades(self.fills)
        for trade in trades:
            strategy = trade.get("strategy", "UNKNOWN")
            if strategy not in strategy_trades:
                strategy_trades[strategy] = []
            strategy_trades[strategy].append(trade)

        result = {}
        for strategy, trades_list in strategy_trades.items():
            result[strategy] = self._compute_metrics_for_group(trades_list, strategy)

        return result

    def compute_symbol_metrics(self) -> Dict[str, Dict[str, Any]]:
        """
        Same metrics but grouped by symbol.

        Returns:
            Dictionary mapping symbols to their metrics
        """
        if not self.fills:
            return {}

        symbol_trades: Dict[str, List[Dict[str, Any]]] = {}
        
        # Group trades by symbol
        trades = self._reconstruct_trades(self.fills)
        for trade in trades:
            symbol = trade.get("symbol", "UNKNOWN")
            if symbol not in symbol_trades:
                symbol_trades[symbol] = []
            symbol_trades[symbol].append(trade)

        result = {}
        for symbol, trades_list in symbol_trades.items():
            result[symbol] = self._compute_metrics_for_group(trades_list, symbol)

        return result

    def _compute_metrics_for_group(
        self, trades: List[Dict[str, Any]], name: str
    ) -> Dict[str, Any]:
        """Compute metrics for a group of trades."""
        if not trades:
            return {
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "profit_factor": 0.0,
                "realized_pnl": 0.0,
                "max_drawdown": 0.0,
                "equity_curve": [],
            }

        pnls = [t["pnl"] for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        
        total_wins = sum(wins)
        total_losses = abs(sum(losses))
        profit_factor = total_wins / total_losses if total_losses > 0 else 0.0
        
        win_rate = len(wins) / len(trades) if trades else 0.0
        avg_win = sum(wins) / len(wins) if wins else 0.0
        avg_loss = sum(losses) / len(losses) if losses else 0.0
        
        # Build equity curve for this group
        equity_curve = []
        cumulative = 0.0
        for trade in sorted(trades, key=lambda t: t.get("timestamp", "")):
            cumulative += trade["pnl"]
            equity_curve.append({
                "timestamp": trade.get("timestamp", ""),
                "equity": round(cumulative, 2),
            })
        
        # Compute drawdown
        dd_info = self.compute_drawdowns(equity_curve)

        return {
            "trades": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(win_rate * 100, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "profit_factor": round(profit_factor, 2),
            "realized_pnl": round(sum(pnls), 2),
            "max_drawdown": dd_info.get("max_drawdown", 0.0),
            "equity_curve": equity_curve,
        }

    def compute_equity_curve(
        self, strategy: Optional[str] = None, symbol: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Build an equity curve series from fills.

        Args:
            strategy: Filter by strategy code (optional)
            symbol: Filter by symbol (optional)

        Returns:
            List of dicts: [{'timestamp': ..., 'equity': ...}, ...]
        """
        if not self.fills:
            return []

        trades = self._reconstruct_trades(self.fills)
        
        # Filter trades if needed
        if strategy:
            trades = [t for t in trades if t.get("strategy") == strategy]
        if symbol:
            trades = [t for t in trades if t.get("symbol") == symbol]

        equity_curve = []
        cumulative = 0.0
        for trade in sorted(trades, key=lambda t: t.get("timestamp", "")):
            cumulative += trade["pnl"]
            equity_curve.append({
                "timestamp": trade.get("timestamp", ""),
                "equity": round(cumulative, 2),
            })

        return equity_curve

    def compute_drawdowns(
        self, equity_curve: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Compute:
          - max_drawdown
          - drawdown_series

        Args:
            equity_curve: List of equity points with 'equity' key

        Returns:
            Dictionary with max_drawdown and drawdown_series
        """
        if not equity_curve:
            return {"max_drawdown": 0.0, "drawdown_series": []}

        max_equity = float("-inf")
        max_drawdown = 0.0
        drawdown_series = []

        for point in equity_curve:
            equity = point.get("equity", 0.0)
            max_equity = max(max_equity, equity)
            drawdown = equity - max_equity
            max_drawdown = min(max_drawdown, drawdown)
            drawdown_series.append({
                "timestamp": point.get("timestamp", ""),
                "drawdown": round(drawdown, 2),
            })

        return {
            "max_drawdown": round(abs(max_drawdown), 2),
            "drawdown_series": drawdown_series,
        }

    def generate_dashboard_payload(self) -> Dict[str, Any]:
        """
        Combined payload:
            {
                'daily': {...},
                'strategies': {...},
                'symbols': {...},
            }

        Returns:
            Dictionary with all analytics data
        """
        return {
            "daily": self.compute_daily_metrics(),
            "strategies": self.compute_strategy_metrics(),
            "symbols": self.compute_symbol_metrics(),
        }

    def _reconstruct_trades(
        self, fills: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Reconstruct completed trades from fills by pairing entries/exits.
        
        For simplicity:
        - Group by symbol and strategy
        - Track position (cumulative qty)
        - When position closes (qty=0), compute PnL
        
        Returns:
            List of trade dicts with 'pnl', 'symbol', 'strategy', 'timestamp', etc.
        """
        trades = []
        
        # Group fills by (symbol, strategy)
        groups: Dict[tuple, List[Dict[str, Any]]] = {}
        for fill in fills:
            symbol = fill.get("symbol", "")
            strategy = fill.get("strategy", "UNKNOWN")
            key = (symbol, strategy)
            if key not in groups:
                groups[key] = []
            groups[key].append(fill)

        # Process each group
        for (symbol, strategy), group_fills in groups.items():
            # Sort by timestamp
            sorted_fills = sorted(group_fills, key=lambda f: f.get("timestamp", ""))
            
            position_qty = 0.0
            entry_price = 0.0
            entry_ts = None
            
            for fill in sorted_fills:
                side = (fill.get("side") or "").upper()
                qty = float(fill.get("quantity") or fill.get("filled_quantity") or 0)
                price = float(fill.get("price") or fill.get("average_price") or 0)
                timestamp = fill.get("timestamp", "")
                
                # Determine if this is entry or exit
                if side in {"BUY", "B"}:
                    fill_qty = qty
                elif side in {"SELL", "S"}:
                    fill_qty = -qty
                else:
                    # Unknown side, skip
                    continue
                
                # Check if we're opening or closing a position
                if position_qty == 0:
                    # Opening new position
                    position_qty = fill_qty
                    entry_price = price
                    entry_ts = timestamp
                else:
                    # Check if this closes the position
                    new_qty = position_qty + fill_qty
                    
                    if abs(new_qty) < 1e-6:  # Position closed
                        # Compute PnL
                        if position_qty > 0:
                            # Long position
                            pnl = (price - entry_price) * abs(position_qty)
                        else:
                            # Short position
                            pnl = (entry_price - price) * abs(position_qty)
                        
                        trades.append({
                            "symbol": symbol,
                            "strategy": strategy,
                            "timestamp": timestamp,
                            "entry_ts": entry_ts,
                            "exit_ts": timestamp,
                            "pnl": pnl,
                            "entry_price": entry_price,
                            "exit_price": price,
                            "qty": abs(position_qty),
                            "side": "LONG" if position_qty > 0 else "SHORT",
                        })
                        
                        # Reset position
                        position_qty = 0.0
                        entry_price = 0.0
                        entry_ts = None
                    elif (position_qty > 0 and new_qty < 0) or (position_qty < 0 and new_qty > 0):
                        # Position reversal - close old, open new
                        # First close existing
                        if position_qty > 0:
                            pnl = (price - entry_price) * abs(position_qty)
                        else:
                            pnl = (entry_price - price) * abs(position_qty)
                        
                        trades.append({
                            "symbol": symbol,
                            "strategy": strategy,
                            "timestamp": timestamp,
                            "entry_ts": entry_ts,
                            "exit_ts": timestamp,
                            "pnl": pnl,
                            "entry_price": entry_price,
                            "exit_price": price,
                            "qty": abs(position_qty),
                            "side": "LONG" if position_qty > 0 else "SHORT",
                        })
                        
                        # Open new position
                        position_qty = new_qty
                        entry_price = price
                        entry_ts = timestamp
                    else:
                        # Adding to position or partial close
                        if abs(new_qty) < abs(position_qty):
                            # Partial close
                            closed_qty = abs(fill_qty)
                            if position_qty > 0:
                                pnl = (price - entry_price) * closed_qty
                            else:
                                pnl = (entry_price - price) * closed_qty
                            
                            trades.append({
                                "symbol": symbol,
                                "strategy": strategy,
                                "timestamp": timestamp,
                                "entry_ts": entry_ts,
                                "exit_ts": timestamp,
                                "pnl": pnl,
                                "entry_price": entry_price,
                                "exit_price": price,
                                "qty": closed_qty,
                                "side": "LONG" if position_qty > 0 else "SHORT",
                            })
                            
                            position_qty = new_qty
                        else:
                            # Adding to position - update weighted average entry
                            total_cost_before = entry_price * abs(position_qty)
                            total_cost_add = price * abs(fill_qty)
                            new_qty_abs = abs(new_qty)
                            if new_qty_abs > 0:
                                entry_price = (total_cost_before + total_cost_add) / new_qty_abs
                            position_qty = new_qty

        return trades
