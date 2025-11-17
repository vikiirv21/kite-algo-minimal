"""
NIFTY 50 and NIFTY 100 stock lists for equity universe filtering.

These lists contain the actual NSE equity symbol strings as used in the
instrument master (e.g., RELIANCE, TCS, INFY).
"""

from __future__ import annotations
from typing import List


# NIFTY 50 constituent stocks (as of common reference)
NIFTY50 = [
    "ADANIPORTS", "ASIANPAINT", "AXISBANK", "BAJAJ-AUTO", "BAJFINANCE",
    "BAJAJFINSV", "BPCL", "BHARTIARTL", "BRITANNIA", "CIPLA",
    "COALINDIA", "DIVISLAB", "DRREDDY", "EICHERMOT", "GRASIM",
    "HCLTECH", "HDFCBANK", "HDFCLIFE", "HEROMOTOCO", "HINDALCO",
    "HINDUNILVR", "ICICIBANK", "ITC", "INDUSINDBK", "INFY",
    "JSWSTEEL", "KOTAKBANK", "LT", "M&M", "MARUTI",
    "NESTLEIND", "NTPC", "ONGC", "POWERGRID", "RELIANCE",
    "SBILIFE", "SBIN", "SUNPHARMA", "TCS", "TATACONSUM",
    "TATAMOTORS", "TATASTEEL", "TECHM", "TITAN", "ULTRACEMCO",
    "UPL", "WIPRO", "APOLLOHOSP", "BAJAJHLDNG", "ADANIENT"
]

# NIFTY 100 additional stocks (beyond NIFTY 50)
# These are combined with NIFTY 50 to form the full NIFTY 100
NIFTY100_ADDITIONAL = [
    "ABB", "ACC", "AMBUJACEM", "AUROPHARMA", "BANDHANBNK",
    "BANKBARODA", "BEL", "BERGEPAINT", "BIOCON", "BOSCHLTD",
    "CANBK", "CHOLAFIN", "COLPAL", "CONCOR", "DLF",
    "DABUR", "DMART", "GAIL", "GODREJCP", "HAVELLS",
    "HINDZINC", "IBULHSGFIN", "IDFCFIRSTB", "IGL", "INDIGO",
    "IOC", "LICHSGFIN", "LTTS", "LUPIN", "MARICO",
    "MOTHERSON", "MUTHOOTFIN", "NMDC", "PEL", "PETRONET",
    "PFIZER", "PIDILITIND", "PNB", "RECLTD", "SAIL",
    "SHREECEM", "SIEMENS", "SRF", "TATAPOWER", "TORNTPHARM",
    "TRENT", "VEDL", "VOLTAS", "ZEEL", "ADANIGREEN"
]

# Full NIFTY 100 = NIFTY 50 + additional stocks
NIFTY100 = NIFTY50 + NIFTY100_ADDITIONAL


def get_equity_universe_from_indices(indices: List[str]) -> List[str]:
    """
    Given a list like ["NIFTY50", "NIFTY100"], return a de-duplicated,
    sorted list of equity symbols.
    
    Args:
        indices: List of index names (e.g., ["NIFTY50", "NIFTY100"])
        
    Returns:
        De-duplicated, sorted list of equity symbols
    """
    if not indices:
        return []
    
    symbols_set = set()
    
    for index_name in indices:
        index_upper = index_name.upper().strip()
        
        if index_upper == "NIFTY50":
            symbols_set.update(NIFTY50)
        elif index_upper == "NIFTY100":
            symbols_set.update(NIFTY100)
        # Add more indices here in the future if needed
    
    # Return sorted list for consistency
    return sorted(symbols_set)
