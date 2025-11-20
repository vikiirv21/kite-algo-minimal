"""
Market Data Engine v2

Unified market data engine that provides:
- Consistent multi-timeframe candles to all engines (FnO, Options, Equity)
- Proper instrument token resolution
- Live Kite feed and replay/backtest support
- Telemetry API for data health monitoring

Key Features:
- Supports both "kite" (live) and "replay" modes
- Multi-timeframe candle building (1m, 5m, etc.)
- Instrument token mapping with fallback
- Data health monitoring and staleness detection
- Minimal logging with deduplication
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
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


class MarketDataEngineV2:
    """
    Market Data Engine v2
    
    Unified market data engine providing consistent multi-timeframe candles
    to all engines (FnO, Options, Equity).
    """
    
    def __init__(
        self,
        cfg: Dict[str, Any],
        kite: Optional[Any],
        universe: List[str],
        meta: Optional[Dict[str, Any]] = None,
        logger_instance: Optional[logging.Logger] = None,
    ):
        """
        Initialize Market Data Engine v2.
        
        Args:
            cfg: Config dict from config["data"]
            kite: KiteConnect instance
            universe: List of tradingsymbols to track
            meta: Optional meta dict from scanner (with instrument_token, lot_size etc.)
            logger_instance: Logger instance
        """
        self.cfg = cfg
        self.kite = kite
        self.logger = logger_instance or logger
        
        # Data feed mode: "kite" (live), "replay" (historical)
        self.feed_mode = cfg.get("feed", "kite")
        self.is_running = False
        
        # Universe and metadata
        self.universe = [s.upper() for s in universe]
        self.meta = meta or {}
        
        # Timeframes to build candles for
        self.timeframes: List[str] = cfg.get("timeframes", ["1m", "5m"])
        
        # Track symbols with missing tokens (log warning once)
        self._warned_missing: set[str] = set()
        
        # Build symbol->token mapping
        self.symbol_tokens: Dict[str, int] = self._build_symbol_tokens()
        
        # LTP tracking: {symbol: price}
        self.ltp: Dict[str, float] = {}
        self.ltp_timestamp: Dict[str, datetime] = {}
        
        # Candle storage: {(symbol, timeframe): deque[dict]}
        max_history = cfg.get("history_lookback", 500)
        self.candles: Dict[tuple[str, str], deque] = defaultdict(lambda: deque(maxlen=max_history))
        
        # Current (incomplete) candles being built: {(symbol, timeframe): dict}
        self.current_bars: Dict[tuple[str, str], dict] = {}
        
        # Replay state
        self.replay_thread: Optional[threading.Thread] = None
        self.replay_speed = cfg.get("replay_speed", 1.0)
        
        # Candle close event handlers
        self.on_candle_close_handlers: List[Any] = []
        
        self.logger.info(
            "MarketDataEngineV2 initialized: feed=%s, timeframes=%s, symbols=%d, tokens_resolved=%d",
            self.feed_mode,
            self.timeframes,
            len(self.universe),
            len(self.symbol_tokens),
        )
    
    def _build_symbol_tokens(self) -> Dict[str, int]:
        """Build mapping of symbol -> instrument_token."""
        from data.instruments import resolve_instrument_token, load_instrument_token_map
        
        # Load the global instrument token map (cached)
        load_instrument_token_map(self.kite)
        
        tokens: Dict[str, int] = {}
        
        for symbol in self.universe:
            symbol_upper = symbol.upper()
            
            # First try meta from scanner
            if symbol_upper in self.meta:
                meta_entry = self.meta[symbol_upper]
                if isinstance(meta_entry, dict):
                    token = meta_entry.get("instrument_token")
                    if token:
                        tokens[symbol_upper] = int(token)
                        continue
            
            # Fallback to instrument token map
            token = resolve_instrument_token(symbol_upper)
            if token:
                tokens[symbol_upper] = int(token)
            else:
                # Log warning once per symbol
                if symbol_upper not in self._warned_missing:
                    self.logger.warning("MDEv2: No instrument token for %s; symbol will be skipped", symbol_upper)
                    self._warned_missing.add(symbol_upper)
        
        return tokens
    
    def register_on_candle_close(self, handler) -> None:
        """
        Register a handler to be called when a candle closes.
        
        Args:
            handler: Callable with signature (symbol: str, timeframe: str, candle: dict)
        """
        if handler not in self.on_candle_close_handlers:
            self.on_candle_close_handlers.append(handler)
            self.logger.info("Registered candle close handler: %s", handler.__name__)
    
    def start(self) -> None:
        """Start the market data engine."""
        if self.is_running:
            self.logger.warning("MDE v2 already running")
            return
        
        self.is_running = True
        self.logger.info("MDE v2 started in %s mode", self.feed_mode)
        
        if self.feed_mode == "kite":
            # Live mode: websocket integration happens externally
            # Engine will receive ticks via on_tick_batch()
            pass
        elif self.feed_mode == "replay":
            # Replay mode: would start replay thread here
            pass
    
    def stop(self) -> None:
        """Stop the market data engine."""
        self.logger.info("MDE v2 stopped")
        self.is_running = False
        
        if self.replay_thread and self.replay_thread.is_alive():
            self.replay_thread.join(timeout=2.0)
    
    def on_tick_batch(self, ticks: List[Dict[str, Any]]) -> None:
        """
        Process batch of ticks from websocket.
        
        Expected tick format:
        {
            'instrument_token': 12345678,
            'last_price': 23850.0,
            'timestamp': datetime(...)
        }
        """
        if not self.is_running:
            return
        
        for tick in ticks:
            token = tick.get("instrument_token")
            ltp = tick.get("last_price")
            ts = tick.get("timestamp") or tick.get("exchange_timestamp") or datetime.now(timezone.utc)
            
            if not token or not ltp:
                continue
            
            # Map token -> symbol
            symbol = self._token_to_symbol(token)
            if not symbol:
                continue
            
            # Ensure timezone-aware timestamp
            if isinstance(ts, datetime) and ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            
            # Update LTP
            self.ltp[symbol] = float(ltp)
            self.ltp_timestamp[symbol] = ts
            
            # Update candles for all timeframes
            for timeframe in self.timeframes:
                self._update_candle(symbol, timeframe, float(ltp), ts)
    
    def _token_to_symbol(self, token: int) -> Optional[str]:
        """Map instrument token to symbol."""
        for symbol, sym_token in self.symbol_tokens.items():
            if sym_token == token:
                return symbol
        return None
    
    def _update_candle(self, symbol: str, timeframe: str, price: float, ts: datetime) -> None:
        """Update or create candle for symbol/timeframe."""
        key = (symbol, timeframe)
        
        # Calculate bar start time (aligned to timeframe)
        bar_start = self._floor_to_timeframe(ts, timeframe)
        
        # Get or create current bar
        current = self.current_bars.get(key)
        
        if current is None or current.get("ts") != bar_start.isoformat():
            # Close previous bar if exists
            if current is not None:
                self._close_bar(key, current)
            
            # Create new bar
            current = {
                "ts": bar_start.isoformat(),
                "o": price,
                "h": price,
                "l": price,
                "c": price,
                "v": 0.0,
            }
            self.current_bars[key] = current
        else:
            # Update current bar
            current["h"] = max(current["h"], price)
            current["l"] = min(current["l"], price)
            current["c"] = price
    
    def _close_bar(self, key: tuple[str, str], bar: dict) -> None:
        """Close and store a completed bar."""
        self.candles[key].append(bar)
        
        # Invoke candle close handlers
        symbol, timeframe = key
        for handler in self.on_candle_close_handlers:
            try:
                handler(symbol, timeframe, bar)
            except Exception as exc:
                self.logger.error(
                    "Error in candle close handler %s for %s/%s: %s",
                    getattr(handler, "__name__", "unknown"),
                    symbol,
                    timeframe,
                    exc,
                    exc_info=True
                )
    
    def _floor_to_timeframe(self, ts: datetime, timeframe: str) -> datetime:
        """Floor timestamp to the start of the timeframe period."""
        minutes = TIMEFRAME_MINUTES.get(timeframe, 1)
        
        # Floor to the minute
        floored = ts.replace(second=0, microsecond=0)
        
        # Floor to timeframe boundary
        minute = floored.minute
        floored_minute = (minute // minutes) * minutes
        floored = floored.replace(minute=floored_minute)
        
        return floored
    
    def get_ltp(self, symbol: str) -> Optional[float]:
        """Get latest LTP for symbol."""
        return self.ltp.get(symbol.upper())
    
    def get_latest_bar(self, symbol: str, timeframe: str) -> Optional[dict]:
        """
        Get latest candle for symbol/timeframe.
        
        Returns:
            dict with keys: ts, o, h, l, c, v
        """
        key = (symbol.upper(), timeframe)
        history = self.candles.get(key)
        if history:
            return history[-1] if history else None
        return None
    
    def get_history(self, symbol: str, timeframe: str, limit: int) -> List[dict]:
        """
        Get last N candles for symbol/timeframe.
        
        Returns:
            List of dicts with keys: ts, o, h, l, c, v (newest last)
        """
        key = (symbol.upper(), timeframe)
        history = self.candles.get(key, deque())
        
        # Return last N candles
        candles_list = list(history)
        return candles_list[-limit:] if limit < len(candles_list) else candles_list
    
    def get_health_snapshot(self, now: Optional[datetime] = None) -> List[dict]:
        """
        Get health snapshot for all symbol/timeframe combinations.
        
        Returns:
            List of dicts with:
            - symbol: str
            - timeframe: str
            - last_update_ts: str (ISO format)
            - staleness_sec: float
            - num_bars: int
            - is_stale: bool
        """
        if now is None:
            now = datetime.now(timezone.utc)
        
        health = []
        
        for symbol in self.universe:
            for timeframe in self.timeframes:
                key = (symbol, timeframe)
                
                # Get last update timestamp
                last_ts = self.ltp_timestamp.get(symbol)
                last_update_str = last_ts.isoformat() if last_ts else None
                
                # Calculate staleness
                staleness_sec = 0.0
                is_stale = False
                
                if last_ts:
                    staleness_sec = (now - last_ts).total_seconds()
                    
                    # Staleness threshold: 2x the bar duration
                    bar_minutes = TIMEFRAME_MINUTES.get(timeframe, 1)
                    threshold_sec = bar_minutes * 60 * 2
                    is_stale = staleness_sec > threshold_sec
                else:
                    is_stale = True
                
                # Get number of bars
                history = self.candles.get(key, deque())
                num_bars = len(history)
                
                health.append({
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "last_update_ts": last_update_str,
                    "staleness_sec": staleness_sec,
                    "num_bars": num_bars,
                    "is_stale": is_stale,
                })
        
        return health
