"""
Market Data Engine v2

A robust market data engine that serves as the single source of truth for:
- Real-time ticks (live or replay)
- Candle building across multiple timeframes
- Historical data replay for backtesting
- Strategy triggers via event callbacks

Key Features:
- Supports both LIVE and REPLAY modes
- Multi-timeframe candle building (1m, 3m, 5m, 15m, etc.)
- Rolling window storage for efficient access
- Event-driven architecture with callbacks
- Data validation and anomaly detection
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import json
import time
import threading

logger = logging.getLogger(__name__)

# Timeframe to minutes mapping
TIMEFRAME_MINUTES = {
    "1m": 1,
    "3m": 3,
    "5m": 5,
    "10m": 10,
    "15m": 15,
    "30m": 30,
    "60m": 60,
    "1h": 60,
}


class Candle:
    """Represents a OHLCV candle for a specific timeframe."""
    
    def __init__(
        self,
        symbol: str,
        timeframe: str,
        open_time: datetime,
        open_price: float = 0.0,
        high: float = 0.0,
        low: float = 0.0,
        close: float = 0.0,
        volume: float = 0.0,
    ):
        self.symbol = symbol
        self.timeframe = timeframe
        self.open_time = open_time
        self.close_time = self._compute_close_time(open_time, timeframe)
        self.open = open_price
        self.high = high
        self.low = low
        self.close = close
        self.volume = volume
        self.tick_count = 0
        self.is_closed = False
        self.anomaly = False
        
    def _compute_close_time(self, open_time: datetime, timeframe: str) -> datetime:
        """Compute candle close time based on open time and timeframe."""
        minutes = TIMEFRAME_MINUTES.get(timeframe, 1)
        return open_time + timedelta(minutes=minutes)
    
    def update_tick(self, tick: Dict[str, Any]) -> None:
        """Update candle with new tick data."""
        if self.is_closed:
            return
            
        ltp = float(tick.get("ltp", 0.0))
        if ltp <= 0:
            return
            
        # Initialize on first tick
        if self.tick_count == 0:
            self.open = ltp
            self.high = ltp
            self.low = ltp
            self.close = ltp
        else:
            self.high = max(self.high, ltp)
            self.low = min(self.low, ltp) if self.low > 0 else ltp
            self.close = ltp
            
        self.volume += tick.get("volume", 0.0)
        self.tick_count += 1
        
    def finalize(self) -> None:
        """Mark candle as closed."""
        self.is_closed = True
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert candle to dictionary."""
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "open_time": self.open_time.isoformat() if isinstance(self.open_time, datetime) else self.open_time,
            "close_time": self.close_time.isoformat() if isinstance(self.close_time, datetime) else self.close_time,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "tick_count": self.tick_count,
            "is_closed": self.is_closed,
            "anomaly": self.anomaly,
        }


class MarketDataEngineV2:
    """
    Market Data Engine v2
    
    Single source of truth for market data in both PAPER and LIVE modes.
    Handles tick ingestion, candle building, and data replay.
    """
    
    def __init__(
        self,
        config: Dict[str, Any],
        broker: Optional[Any] = None,
        logger_instance: Optional[logging.Logger] = None,
    ):
        """
        Initialize Market Data Engine v2.
        
        Args:
            config: Configuration dict with data_feed, symbols, timeframes
            broker: Broker adapter (e.g., KiteBroker) for websocket + historical API
            logger_instance: Logger instance
        """
        self.config = config
        self.broker = broker
        self.logger = logger_instance or logger
        
        # Data feed mode: "kite" (live), "replay" (historical), "mock" (testing)
        data_config = config.get("data", {})
        self.feed_mode = data_config.get("feed", "kite")
        self.is_running = False
        
        # Subscribed symbols and timeframes
        self.symbols: List[str] = []
        self.timeframes: List[str] = data_config.get("timeframes", ["1m", "5m"])
        
        # Latest ticks per symbol
        self.latest_ticks: Dict[str, Dict[str, Any]] = {}
        self.last_tick_time: Dict[str, datetime] = {}
        
        # Current candles: {symbol: {timeframe: Candle}}
        self.current_candles: Dict[str, Dict[str, Candle]] = defaultdict(dict)
        
        # Historical candles: {symbol: {timeframe: deque}}
        self.candle_history: Dict[str, Dict[str, deque]] = defaultdict(lambda: defaultdict(lambda: deque(maxlen=500)))
        
        # Event callbacks
        self.on_candle_open_handlers: List[Callable] = []
        self.on_candle_update_handlers: List[Callable] = []
        self.on_candle_close_handlers: List[Callable] = []
        
        # Replay state
        self.replay_thread: Optional[threading.Thread] = None
        self.replay_speed = 1.0
        
        # Statistics
        self.stats = {
            "ticks_received": 0,
            "ticks_ignored": 0,
            "candles_created": 0,
            "candles_closed": 0,
            "anomalies_detected": 0,
        }
        
        self.logger.info(
            "MarketDataEngineV2 initialized: feed_mode=%s timeframes=%s",
            self.feed_mode,
            self.timeframes,
        )
        
    def start(self) -> None:
        """Start the market data engine according to configured feed mode."""
        if self.is_running:
            self.logger.warning("MDE v2 already running")
            return
            
        self.is_running = True
        self.logger.info("Starting MDE v2 in mode: %s", self.feed_mode)
        
        if self.feed_mode == "kite" and self.broker:
            # Live mode: broker should call on_tick() when it receives websocket data
            # No explicit action needed here - broker integration happens externally
            self.logger.info("MDE v2 started in LIVE mode - awaiting ticks from broker")
        elif self.feed_mode == "replay":
            # Replay mode: will be started via start_replay()
            self.logger.info("MDE v2 started in REPLAY mode - use start_replay() to begin")
        else:
            self.logger.info("MDE v2 started in %s mode", self.feed_mode)
            
    def stop(self) -> None:
        """Cleanly stop the market data engine."""
        self.logger.info("Stopping MDE v2")
        self.is_running = False
        
        # Stop replay thread if running
        if self.replay_thread and self.replay_thread.is_alive():
            self.replay_thread.join(timeout=2.0)
            
        # Finalize any open candles
        self._finalize_all_open_candles()
        
        self.logger.info(
            "MDE v2 stopped. Stats: %s",
            self.stats,
        )
        
    def subscribe_symbols(self, symbols: List[str]) -> None:
        """
        Subscribe to a list of symbols.
        
        Args:
            symbols: List of symbol names
        """
        self.symbols = [s.upper() for s in symbols]
        self.logger.info("Subscribed to %d symbols: %s", len(self.symbols), self.symbols)
        
    def set_timeframes(self, timeframes: List[str]) -> None:
        """
        Set active timeframes for candle building.
        
        Args:
            timeframes: List of timeframe strings (e.g., ['1m', '5m', '15m'])
        """
        # Validate timeframes
        valid_tf = []
        for tf in timeframes:
            if tf in TIMEFRAME_MINUTES:
                valid_tf.append(tf)
            else:
                self.logger.warning("Ignoring invalid timeframe: %s", tf)
                
        self.timeframes = valid_tf
        self.logger.info("Active timeframes: %s", self.timeframes)
        
    def on_tick(self, tick: Dict[str, Any]) -> None:
        """
        Process incoming tick data.
        
        Expected tick format:
        {
            'symbol': 'NIFTY25NOVFUT',
            'ltp': 23850.0,
            'bid': 23845.0,
            'ask': 23855.0,
            'volume': 12345,
            'ts_exchange': datetime(...),
            'ts_local': datetime(...),
        }
        
        Args:
            tick: Normalized tick dictionary
        """
        if not self.is_running:
            return
            
        self.stats["ticks_received"] += 1
        
        # Extract and validate tick data
        symbol = tick.get("symbol", "").upper()
        if not symbol:
            self.stats["ticks_ignored"] += 1
            return
            
        ltp = tick.get("ltp")
        if ltp is None or ltp <= 0:
            self.logger.debug("Ignoring tick with invalid LTP: %s", tick)
            self.stats["ticks_ignored"] += 1
            return
            
        # Get timestamp
        ts = tick.get("ts_exchange") or tick.get("ts_local") or datetime.now(timezone.utc)
        if not isinstance(ts, datetime):
            try:
                ts = datetime.fromisoformat(str(ts))
            except (ValueError, TypeError):
                ts = datetime.now(timezone.utc)
                
        # Ensure timezone awareness
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
            
        # Check for stale ticks (ignore ticks older than last tick)
        last_ts = self.last_tick_time.get(symbol)
        if last_ts and ts < last_ts:
            self.logger.debug(
                "Ignoring stale tick for %s: ts=%s < last_ts=%s",
                symbol,
                ts,
                last_ts,
            )
            self.stats["ticks_ignored"] += 1
            return
            
        # Check for price anomalies
        last_tick = self.latest_ticks.get(symbol)
        if last_tick:
            last_ltp = last_tick.get("ltp", 0.0)
            if last_ltp > 0:
                change_pct = abs(ltp - last_ltp) / last_ltp
                if change_pct > 0.05:  # > 5% jump
                    self.logger.warning(
                        "Large price jump detected for %s: %.2f -> %.2f (%.2f%%)",
                        symbol,
                        last_ltp,
                        ltp,
                        change_pct * 100,
                    )
                    tick["anomaly"] = True
                    self.stats["anomalies_detected"] += 1
                    
        # Store latest tick
        self.latest_ticks[symbol] = tick
        self.last_tick_time[symbol] = ts
        
        # Update candles for all timeframes
        self._update_candles(symbol, tick, ts)
        
    def get_latest_tick(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get the latest tick for a symbol.
        
        Args:
            symbol: Symbol name
            
        Returns:
            Latest tick dict or None
        """
        return self.latest_ticks.get(symbol.upper())
        
    def get_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get recent candles for a symbol and timeframe.
        
        Args:
            symbol: Symbol name
            timeframe: Timeframe string (e.g., '5m')
            limit: Maximum number of candles to return
            
        Returns:
            List of candle dictionaries (oldest to newest)
        """
        symbol = symbol.upper()
        history = self.candle_history.get(symbol, {}).get(timeframe, deque())
        
        # Convert deque to list and apply limit
        candles = list(history)[-limit:]
        return [c.to_dict() for c in candles]
        
    def start_replay(
        self,
        data_source: str,
        speed: float = 1.0,
    ) -> None:
        """
        Start replay from historical data source.
        
        Args:
            data_source: Path to CSV or data directory
            speed: Replay speed (1.0 = real-time, 10.0 = 10x faster)
        """
        if self.feed_mode != "replay":
            self.logger.warning("start_replay() called but feed_mode is not 'replay'")
            return
            
        self.replay_speed = speed
        self.logger.info(
            "Starting replay from %s at %.1fx speed",
            data_source,
            speed,
        )
        
        # Launch replay in background thread
        self.replay_thread = threading.Thread(
            target=self._run_replay,
            args=(data_source,),
            daemon=True,
        )
        self.replay_thread.start()
        
    def is_live(self) -> bool:
        """Check if engine is using live feed."""
        return self.feed_mode == "kite"
        
    def _update_candles(
        self,
        symbol: str,
        tick: Dict[str, Any],
        ts: datetime,
    ) -> None:
        """Update or create candles for all active timeframes."""
        for timeframe in self.timeframes:
            self._update_candle_for_timeframe(symbol, timeframe, tick, ts)
            
    def _update_candle_for_timeframe(
        self,
        symbol: str,
        timeframe: str,
        tick: Dict[str, Any],
        ts: datetime,
    ) -> None:
        """Update or create candle for a specific timeframe."""
        # Get or create current candle
        current = self.current_candles[symbol].get(timeframe)
        
        # Determine if we need a new candle
        if current is None:
            # First candle for this symbol/timeframe
            open_time = self._floor_to_timeframe(ts, timeframe)
            current = Candle(symbol, timeframe, open_time)
            self.current_candles[symbol][timeframe] = current
            self.stats["candles_created"] += 1
            self._fire_candle_open(symbol, timeframe, current)
            self.logger.debug(
                "Created new candle: %s %s at %s",
                symbol,
                timeframe,
                open_time,
            )
        elif ts >= current.close_time:
            # Close current candle and open new one
            self._finalize_candle(symbol, timeframe, current)
            
            # Create new candle
            open_time = self._floor_to_timeframe(ts, timeframe)
            current = Candle(symbol, timeframe, open_time)
            self.current_candles[symbol][timeframe] = current
            self.stats["candles_created"] += 1
            self._fire_candle_open(symbol, timeframe, current)
            self.logger.debug(
                "Rolled to new candle: %s %s at %s",
                symbol,
                timeframe,
                open_time,
            )
            
        # Update current candle with tick
        if tick.get("anomaly"):
            current.anomaly = True
            
        current.update_tick(tick)
        self._fire_candle_update(symbol, timeframe, current)
        
    def _finalize_candle(
        self,
        symbol: str,
        timeframe: str,
        candle: Candle,
    ) -> None:
        """Finalize and store a completed candle."""
        candle.finalize()
        self.stats["candles_closed"] += 1
        
        # Add to history
        self.candle_history[symbol][timeframe].append(candle)
        
        # Fire close event
        self._fire_candle_close(symbol, timeframe, candle)
        
        self.logger.debug(
            "Closed candle: %s %s OHLC=[%.2f, %.2f, %.2f, %.2f] ticks=%d",
            symbol,
            timeframe,
            candle.open,
            candle.high,
            candle.low,
            candle.close,
            candle.tick_count,
        )
        
    def _finalize_all_open_candles(self) -> None:
        """Finalize all currently open candles."""
        for symbol, tf_candles in self.current_candles.items():
            for timeframe, candle in tf_candles.items():
                if not candle.is_closed:
                    self._finalize_candle(symbol, timeframe, candle)
                    
    def _floor_to_timeframe(
        self,
        ts: datetime,
        timeframe: str,
    ) -> datetime:
        """Floor timestamp to the start of the timeframe period."""
        minutes = TIMEFRAME_MINUTES.get(timeframe, 1)
        
        # Floor to the minute
        floored = ts.replace(second=0, microsecond=0)
        
        # Floor to timeframe boundary
        minute = floored.minute
        floored_minute = (minute // minutes) * minutes
        floored = floored.replace(minute=floored_minute)
        
        return floored
        
    def _fire_candle_open(
        self,
        symbol: str,
        timeframe: str,
        candle: Candle,
    ) -> None:
        """Fire candle open event to all registered handlers."""
        for handler in self.on_candle_open_handlers:
            try:
                handler(symbol, timeframe, candle.to_dict())
            except Exception as exc:
                self.logger.exception(
                    "Error in candle_open handler: %s",
                    exc,
                )
                
    def _fire_candle_update(
        self,
        symbol: str,
        timeframe: str,
        candle: Candle,
    ) -> None:
        """Fire candle update event to all registered handlers."""
        for handler in self.on_candle_update_handlers:
            try:
                handler(symbol, timeframe, candle.to_dict())
            except Exception as exc:
                self.logger.exception(
                    "Error in candle_update handler: %s",
                    exc,
                )
                
    def _fire_candle_close(
        self,
        symbol: str,
        timeframe: str,
        candle: Candle,
    ) -> None:
        """Fire candle close event to all registered handlers."""
        for handler in self.on_candle_close_handlers:
            try:
                handler(symbol, timeframe, candle.to_dict())
            except Exception as exc:
                self.logger.exception(
                    "Error in candle_close handler: %s",
                    exc,
                )
                
    def _run_replay(self, data_source: str) -> None:
        """Run replay from historical data (runs in background thread)."""
        self.logger.info("Replay thread started")
        
        # TODO: Implement CSV/historical data replay
        # This is a placeholder for the replay logic
        # In a full implementation, this would:
        # 1. Load data from CSV or historical cache
        # 2. Feed ticks at the specified replay_speed
        # 3. Call on_tick() for each historical tick
        
        self.logger.warning("Replay implementation is a placeholder - no data fed")
        
    def get_stats(self) -> Dict[str, Any]:
        """Get engine statistics."""
        return dict(self.stats)
