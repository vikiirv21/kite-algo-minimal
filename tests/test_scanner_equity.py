"""
Test suite for MarketScanner equity integration.

Validates:
- Equity universe loading
- NSE instrument scanning
- Penny stock filtering
- Universe JSON schema
"""
import json
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest

from core.scanner import MarketScanner, PENNY_STOCK_THRESHOLD
from core.universe import load_equity_universe


class TestEquityUniverse:
    """Test equity universe configuration."""

    def test_load_equity_universe(self):
        """Verify equity universe can be loaded from CSV."""
        symbols = load_equity_universe()
        assert isinstance(symbols, list)
        assert len(symbols) > 0
        # Check expected symbols
        assert "RELIANCE" in symbols
        assert "TCS" in symbols
        assert "INFY" in symbols

    def test_equity_universe_size(self):
        """Verify expanded universe has adequate size."""
        symbols = load_equity_universe()
        # Should have significantly more than 7 stocks now
        assert len(symbols) >= 100, f"Expected >= 100 symbols, got {len(symbols)}"
        # But not unreasonably large
        assert len(symbols) <= 200, f"Expected <= 200 symbols, got {len(symbols)}"


class TestMarketScanner:
    """Test MarketScanner with equity support."""

    def test_scanner_initialization(self):
        """Verify scanner initializes correctly."""
        mock_kite = Mock()
        mock_config = Mock()
        scanner = MarketScanner(mock_kite, mock_config)
        assert scanner.kite is mock_kite
        assert scanner.config is mock_config

    def test_empty_universe_structure(self):
        """Verify empty universe has correct schema."""
        empty = MarketScanner._empty_universe()
        assert "date" in empty
        assert "asof" in empty
        assert "fno" in empty
        assert "equity" in empty
        assert "meta" in empty
        assert isinstance(empty["fno"], list)
        assert isinstance(empty["equity"], list)
        assert isinstance(empty["meta"], dict)

    def test_scan_with_mock_data(self):
        """Test scanner with mocked Kite API responses."""
        # Mock Kite API
        mock_kite = MagicMock()
        mock_config = Mock()
        
        # Mock NFO instruments (futures)
        nfo_instruments = [
            {
                "tradingsymbol": "NIFTY25NOVFUT",
                "instrument_token": 9485826,
                "lot_size": 75,
                "expiry": date(2025, 11, 25),
                "tick_size": 0.1,
                "exchange": "NFO",
                "segment": "NFO-FUT",
                "name": "NIFTY",
                "instrument_type": "FUT",
            },
            {
                "tradingsymbol": "BANKNIFTY25NOVFUT",
                "instrument_token": 9485058,
                "lot_size": 35,
                "expiry": date(2025, 11, 25),
                "tick_size": 0.2,
                "exchange": "NFO",
                "segment": "NFO-FUT",
                "name": "BANKNIFTY",
                "instrument_type": "FUT",
            },
        ]
        
        # Mock NSE instruments (equities)
        nse_instruments = [
            {
                "tradingsymbol": "RELIANCE",
                "instrument_token": 738561,
                "lot_size": 1,
                "tick_size": 0.05,
                "exchange": "NSE",
                "segment": "NSE-EQ",
                "name": "RELIANCE INDUSTRIES LTD",
                "last_price": 2500.50,
            },
            {
                "tradingsymbol": "TCS",
                "instrument_token": 2953217,
                "lot_size": 1,
                "tick_size": 0.05,
                "exchange": "NSE",
                "segment": "NSE-EQ",
                "name": "TATA CONSULTANCY SERVICES LTD",
                "last_price": 3800.25,
            },
            {
                "tradingsymbol": "PENNYSTOCK",
                "instrument_token": 999999,
                "lot_size": 1,
                "tick_size": 0.05,
                "exchange": "NSE",
                "segment": "NSE-EQ",
                "name": "PENNY STOCK LTD",
                "last_price": 15.00,  # Below threshold
            },
        ]
        
        # Configure mock to return different instruments for different exchanges
        def mock_instruments(exchange):
            if exchange == "NFO":
                return nfo_instruments
            elif exchange == "NSE":
                return nse_instruments
            return []
        
        mock_kite.instruments = MagicMock(side_effect=mock_instruments)
        
        # Create scanner
        scanner = MarketScanner(mock_kite, mock_config)
        
        # Scan
        result = scanner.scan()
        
        # Verify structure
        assert "date" in result
        assert "asof" in result
        assert "fno" in result
        assert "equity" in result
        assert "meta" in result
        
        # Verify FnO symbols
        assert "NIFTY" in result["fno"]
        assert "BANKNIFTY" in result["fno"]
        
        # Verify equity symbols (should include RELIANCE and TCS)
        # Note: Only if they're in the universe CSV
        equity_universe = load_equity_universe()
        if "RELIANCE" in equity_universe:
            assert "RELIANCE" in result["equity"]
        if "TCS" in equity_universe:
            assert "TCS" in result["equity"]
        
        # Verify penny stock is filtered out
        assert "PENNYSTOCK" not in result["equity"]

    def test_penny_stock_filtering(self):
        """Test penny stock filter logic."""
        mock_kite = MagicMock()
        mock_config = Mock()
        scanner = MarketScanner(mock_kite, mock_config)
        
        # Test valid instrument (above threshold)
        valid_inst = {
            "instrument_token": 123456,
            "segment": "NSE-EQ",
            "last_price": 100.0,
        }
        assert scanner._is_valid_equity_instrument(valid_inst, "VALID") is True
        
        # Test penny stock (below threshold)
        penny_inst = {
            "instrument_token": 123456,
            "segment": "NSE-EQ",
            "last_price": PENNY_STOCK_THRESHOLD - 1,
        }
        assert scanner._is_valid_equity_instrument(penny_inst, "PENNY") is False
        
        # Test instrument without price (should pass)
        no_price_inst = {
            "instrument_token": 123456,
            "segment": "NSE-EQ",
            "last_price": None,
        }
        assert scanner._is_valid_equity_instrument(no_price_inst, "NOPRICE") is True

    def test_invalid_instrument_filtering(self):
        """Test filtering of invalid instruments."""
        mock_kite = MagicMock()
        mock_config = Mock()
        scanner = MarketScanner(mock_kite, mock_config)
        
        # Test instrument without token
        no_token_inst = {
            "instrument_token": None,
            "segment": "NSE-EQ",
            "last_price": 100.0,
        }
        assert scanner._is_valid_equity_instrument(no_token_inst, "NOTOKEN") is False
        
        # Test instrument with zero token
        zero_token_inst = {
            "instrument_token": 0,
            "segment": "NSE-EQ",
            "last_price": 100.0,
        }
        assert scanner._is_valid_equity_instrument(zero_token_inst, "ZEROTOKEN") is False
        
        # Test non-equity segment
        wrong_segment_inst = {
            "instrument_token": 123456,
            "segment": "NFO-FUT",
            "last_price": 100.0,
        }
        assert scanner._is_valid_equity_instrument(wrong_segment_inst, "WRONGSEG") is False


class TestScannerPersistence:
    """Test scanner save/load functionality."""

    def test_universe_save_and_load(self, tmp_path):
        """Test saving and loading universe JSON."""
        mock_kite = MagicMock()
        mock_config = Mock()
        scanner = MarketScanner(mock_kite, mock_config, artifacts_dir=tmp_path)
        
        # Create test universe
        test_universe = {
            "date": date.today().isoformat(),
            "asof": "2025-11-17T10:00:00Z",
            "fno": ["NIFTY", "BANKNIFTY"],
            "equity": ["RELIANCE", "TCS", "INFY"],
            "meta": {
                "NIFTY": {
                    "tradingsymbol": "NIFTY25NOVFUT",
                    "instrument_token": 9485826,
                    "lot_size": 75,
                },
                "RELIANCE": {
                    "tradingsymbol": "RELIANCE",
                    "instrument_token": 738561,
                    "lot_size": 1,
                },
            },
        }
        
        # Save
        path = scanner.save(test_universe)
        assert path is not None
        assert path.exists()
        
        # Load
        loaded = scanner.load_today()
        assert loaded is not None
        assert loaded["date"] == test_universe["date"]
        assert loaded["fno"] == test_universe["fno"]
        assert loaded["equity"] == test_universe["equity"]
        assert "NIFTY" in loaded["meta"]
        assert "RELIANCE" in loaded["meta"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
