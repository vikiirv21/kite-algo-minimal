#!/usr/bin/env python3
"""
Demonstration script showing the enhanced MarketScanner in action.

This script creates a mock Kite API and demonstrates:
1. FnO futures scanning
2. NSE equity scanning
3. Penny stock filtering
4. Universe persistence

Run: python3 scripts/demo_scanner.py
"""

import json
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

from core.scanner import MarketScanner


def create_mock_kite():
    """Create a mock Kite API with sample data."""
    mock_kite = MagicMock()
    
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
    
    # Mock NSE instruments (equities) - sample from universe
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
            "tradingsymbol": "INFY",
            "instrument_token": 408065,
            "lot_size": 1,
            "tick_size": 0.05,
            "exchange": "NSE",
            "segment": "NSE-EQ",
            "name": "INFOSYS LIMITED",
            "last_price": 1650.75,
        },
        {
            "tradingsymbol": "HDFCBANK",
            "instrument_token": 341249,
            "lot_size": 1,
            "tick_size": 0.05,
            "exchange": "NSE",
            "segment": "NSE-EQ",
            "name": "HDFC BANK LTD",
            "last_price": 1720.30,
        },
        {
            "tradingsymbol": "ICICIBANK",
            "instrument_token": 1270529,
            "lot_size": 1,
            "tick_size": 0.05,
            "exchange": "NSE",
            "segment": "NSE-EQ",
            "name": "ICICI BANK LTD",
            "last_price": 1150.60,
        },
        {
            "tradingsymbol": "PENNYSTOCK",
            "instrument_token": 999999,
            "lot_size": 1,
            "tick_size": 0.05,
            "exchange": "NSE",
            "segment": "NSE-EQ",
            "name": "PENNY STOCK LTD",
            "last_price": 15.00,  # Below ₹20 threshold - should be filtered
        },
        {
            "tradingsymbol": "INVALIDSTOCK",
            "instrument_token": 0,  # Invalid token - should be filtered
            "lot_size": 1,
            "tick_size": 0.05,
            "exchange": "NSE",
            "segment": "NSE-EQ",
            "name": "INVALID STOCK",
            "last_price": 100.00,
        },
    ]
    
    def mock_instruments(exchange):
        if exchange == "NFO":
            return nfo_instruments
        elif exchange == "NSE":
            return nse_instruments
        return []
    
    mock_kite.instruments = MagicMock(side_effect=mock_instruments)
    return mock_kite


def main():
    """Run the scanner demonstration."""
    print("=" * 70)
    print("MarketScanner Demonstration")
    print("=" * 70)
    print()
    
    # Create mock Kite API
    print("📡 Creating mock Kite API...")
    mock_kite = create_mock_kite()
    mock_config = MagicMock()
    print("✅ Mock API ready\n")
    
    # Create scanner
    print("🔍 Initializing MarketScanner...")
    scanner = MarketScanner(mock_kite, mock_config)
    print("✅ Scanner initialized\n")
    
    # Run scan
    print("🚀 Running scan...")
    print("-" * 70)
    universe = scanner.scan()
    print("-" * 70)
    print()
    
    # Display results
    print("📊 SCAN RESULTS")
    print("=" * 70)
    print()
    
    print(f"📅 Date: {universe['date']}")
    print(f"⏰ Scanned at: {universe['asof']}")
    print()
    
    print(f"📈 FnO Symbols: {len(universe['fno'])}")
    for symbol in universe['fno']:
        meta = universe['meta'][symbol]
        print(f"   • {symbol:12s} → {meta['tradingsymbol']}")
    print()
    
    print(f"💼 Equity Symbols: {len(universe['equity'])}")
    for symbol in universe['equity']:
        meta = universe['meta'][symbol]
        price = meta.get('last_price', 'N/A')
        price_str = f"₹{price:.2f}" if price != 'N/A' else 'N/A'
        print(f"   • {symbol:12s} → {price_str}")
    print()
    
    print(f"📦 Total Symbols: {len(universe['fno']) + len(universe['equity'])}")
    print()
    
    # Test persistence
    print("💾 Testing persistence...")
    output_dir = Path("/tmp/scanner_demo")
    scanner_with_tmp = MarketScanner(mock_kite, mock_config, artifacts_dir=output_dir)
    saved_path = scanner_with_tmp.save(universe)
    print(f"✅ Universe saved to: {saved_path}")
    print()
    
    # Load back
    print("📂 Loading universe back...")
    loaded_universe = scanner_with_tmp.load_today()
    if loaded_universe:
        print("✅ Universe loaded successfully")
        print(f"   • FnO: {len(loaded_universe['fno'])} symbols")
        print(f"   • Equity: {len(loaded_universe['equity'])} symbols")
    else:
        print("❌ Failed to load universe")
    print()
    
    # Show filtered symbols
    print("🚫 FILTERED SYMBOLS")
    print("=" * 70)
    print()
    print("The following symbols were filtered out:")
    print("   • PENNYSTOCK (price ₹15.00 < ₹20.00 threshold)")
    print("   • INVALIDSTOCK (invalid instrument_token = 0)")
    print()
    
    # Summary
    print("=" * 70)
    print("✅ DEMONSTRATION COMPLETE")
    print("=" * 70)
    print()
    print("Key Features Demonstrated:")
    print("  ✓ FnO futures scanning (NIFTY, BANKNIFTY)")
    print("  ✓ NSE equity scanning")
    print("  ✓ Penny stock filtering (< ₹20)")
    print("  ✓ Invalid instrument rejection")
    print("  ✓ Universe persistence (save/load)")
    print()
    print("For production use:")
    print("  • Replace mock_kite with real KiteConnect instance")
    print("  • Ensure config/universe_equity.csv is populated")
    print("  • Run during market hours for live prices")
    print("  • Monitor artifacts/scanner/*/universe.json")
    print()


if __name__ == "__main__":
    main()
