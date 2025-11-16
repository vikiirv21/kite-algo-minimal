"""
Historical Data Loader for Backtest Engine v3.

Provides offline historical bar data from various sources:
- CSV files
- HDF5 files (future)
- Kite historical API (future)
"""

from __future__ import annotations

import csv
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

logger = logging.getLogger(__name__)


class HistoricalDataLoader:
    """
    Historical data loader for backtesting.
    
    Loads and iterates through historical OHLCV bar data from various sources.
    """
    
    def __init__(
        self,
        data_source: str,
        timeframe: str,
        symbols: List[str],
        config: Dict[str, Any],
        logger_instance: Optional[logging.Logger] = None,
    ):
        """
        Initialize the historical data loader.
        
        Args:
            data_source: Data source type ('csv', 'hdf', 'kite_historical')
            timeframe: Timeframe for bars ('1m', '5m', '15m', '1h', '1d')
            symbols: List of symbols to load
            config: Full application config dict
            logger_instance: Optional logger instance
        """
        self.data_source = data_source.lower()
        self.timeframe = timeframe
        self.symbols = symbols
        self.config = config
        self.logger = logger_instance or logger
        
        # Determine data directory from config
        base_dir = Path(__file__).resolve().parents[1]
        self.artifacts_dir = base_dir / "artifacts"
        self.market_data_dir = self.artifacts_dir / "market_data"
        
        self.logger.info(
            "HistoricalDataLoader initialized: source=%s, timeframe=%s, symbols=%s",
            data_source,
            timeframe,
            symbols,
        )
    
    def iter_bars(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> Iterator[Dict[str, Any]]:
        """
        Iterate through historical bars for a symbol.
        
        Args:
            symbol: Trading symbol
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            
        Yields:
            Bar dictionaries with keys:
                - timestamp: datetime object
                - open: float
                - high: float
                - low: float
                - close: float
                - volume: float
        """
        if self.data_source == "csv":
            yield from self._iter_bars_csv(symbol, start_date, end_date)
        elif self.data_source == "hdf":
            raise NotImplementedError("HDF5 data source not yet implemented")
        elif self.data_source == "kite_historical":
            raise NotImplementedError("Kite historical API not yet implemented")
        else:
            raise ValueError(f"Unknown data source: {self.data_source}")
    
    def _iter_bars_csv(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> Iterator[Dict[str, Any]]:
        """
        Load bars from CSV files.
        
        Expected CSV format:
            timestamp,open,high,low,close,volume
            2025-01-01T09:15:00+00:00,100.0,105.0,99.0,102.0,1000
            
        File naming convention:
            artifacts/market_data/{symbol}_{YYYY-MM-DD}_{timeframe}.csv
            OR
            artifacts/market_data/{symbol}_{timeframe}.csv (all historical data)
        """
        # Parse date range
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end_dt = end_dt.replace(hour=23, minute=59, second=59)
        
        # Try different CSV file patterns
        csv_files = self._find_csv_files(symbol)
        
        if not csv_files:
            self.logger.warning(
                "No CSV files found for symbol=%s in %s",
                symbol,
                self.market_data_dir,
            )
            return
        
        # Load and yield bars
        bars_loaded = 0
        for csv_path in csv_files:
            self.logger.debug("Loading bars from %s", csv_path)
            
            try:
                with csv_path.open("r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    
                    for row in reader:
                        # Parse timestamp
                        timestamp = self._parse_timestamp(row.get("timestamp", ""))
                        if timestamp is None:
                            continue
                        
                        # Filter by date range
                        if timestamp < start_dt or timestamp > end_dt:
                            continue
                        
                        # Parse OHLCV
                        try:
                            bar = {
                                "timestamp": timestamp,
                                "open": float(row.get("open", 0)),
                                "high": float(row.get("high", 0)),
                                "low": float(row.get("low", 0)),
                                "close": float(row.get("close", 0)),
                                "volume": float(row.get("volume", 0)),
                            }
                            bars_loaded += 1
                            yield bar
                        except (ValueError, TypeError) as e:
                            self.logger.warning("Skipping invalid bar: %s", e)
                            continue
                            
            except Exception as e:
                self.logger.error("Error reading CSV file %s: %s", csv_path, e)
                continue
        
        self.logger.info("Loaded %d bars for %s", bars_loaded, symbol)
    
    def _find_csv_files(self, symbol: str) -> List[Path]:
        """
        Find CSV files for a symbol.
        
        Looks for files matching:
        - {symbol}_{timeframe}.csv
        - {symbol}_*_{timeframe}.csv
        """
        csv_files = []
        
        if not self.market_data_dir.exists():
            self.logger.warning("Market data directory does not exist: %s", self.market_data_dir)
            return csv_files
        
        # Pattern 1: symbol_timeframe.csv
        pattern1 = f"{symbol}_{self.timeframe}.csv"
        path1 = self.market_data_dir / pattern1
        if path1.exists():
            csv_files.append(path1)
        
        # Pattern 2: symbol_*_timeframe.csv (date-specific files)
        for path in sorted(self.market_data_dir.glob(f"{symbol}_*_{self.timeframe}.csv")):
            if path not in csv_files:
                csv_files.append(path)
        
        return csv_files
    
    def _parse_timestamp(self, ts_str: str) -> Optional[datetime]:
        """
        Parse timestamp from various formats.
        
        Supports:
        - ISO 8601: 2025-01-01T09:15:00+00:00
        - ISO 8601 with Z: 2025-01-01T09:15:00Z
        - Simple: 2025-01-01 09:15:00
        """
        if not ts_str:
            return None
        
        try:
            # Try ISO 8601 with timezone
            if "+" in ts_str or ts_str.endswith("Z"):
                return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            
            # Try simple format
            return datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            pass
        
        # Try additional formats
        formats = [
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S.%f",
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(ts_str, fmt).replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue
        
        self.logger.warning("Failed to parse timestamp: %s", ts_str)
        return None
