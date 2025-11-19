"""
Expiry Calendar Module

Provides expiry-aware helpers for Indian index derivatives (FnO).
Supports NIFTY, BANKNIFTY, and FINNIFTY with weekly and monthly expiries.

Weekly expiry days:
- NIFTY: Thursday
- BANKNIFTY: Wednesday  
- FINNIFTY: Tuesday

Monthly expiry: Last Thursday of the month for all indices.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Optional

import pytz

logger = logging.getLogger(__name__)

# India timezone
IST = pytz.timezone("Asia/Kolkata")

# Weekly expiry day mappings (0=Monday, 6=Sunday)
WEEKLY_EXPIRY_DAYS = {
    "NIFTY": 3,      # Thursday
    "BANKNIFTY": 2,  # Wednesday
    "FINNIFTY": 1,   # Tuesday
}

# Symbols with weekly expiries
WEEKLY_EXPIRY_SYMBOLS = {"NIFTY", "BANKNIFTY", "FINNIFTY"}


def _get_last_thursday_of_month(year: int, month: int) -> date:
    """
    Get the last Thursday of a given month (monthly expiry date).
    
    Args:
        year: Year
        month: Month (1-12)
        
    Returns:
        Date of the last Thursday in the month
    """
    # Find the last day of the month
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    
    last_day = next_month - timedelta(days=1)
    
    # Walk backwards to find the last Thursday (weekday 3)
    while last_day.weekday() != 3:
        last_day -= timedelta(days=1)
    
    return last_day


def _get_next_weekly_expiry(symbol: str, from_dt: datetime) -> Optional[date]:
    """
    Get the next weekly expiry date for a symbol.
    
    Args:
        symbol: Underlying symbol (NIFTY, BANKNIFTY, FINNIFTY)
        from_dt: Reference datetime
        
    Returns:
        Next weekly expiry date, or None if symbol doesn't have weekly expiry
    """
    symbol_upper = symbol.upper()
    if symbol_upper not in WEEKLY_EXPIRY_DAYS:
        return None
    
    target_weekday = WEEKLY_EXPIRY_DAYS[symbol_upper]
    current_date = from_dt.date()
    
    # Find the next occurrence of the target weekday
    days_ahead = target_weekday - current_date.weekday()
    if days_ahead < 0:  # Target day already happened this week
        days_ahead += 7
    elif days_ahead == 0:  # Today is the target day
        # If market hasn't closed yet (before 15:30 IST), today is the expiry
        # Otherwise, next week
        ist_time = from_dt.astimezone(IST) if from_dt.tzinfo else IST.localize(from_dt)
        market_close_time = ist_time.replace(hour=15, minute=30, second=0, microsecond=0)
        if ist_time >= market_close_time:
            days_ahead = 7
    
    next_expiry = current_date + timedelta(days=days_ahead)
    return next_expiry


def _get_next_monthly_expiry(from_dt: datetime) -> date:
    """
    Get the next monthly expiry date (last Thursday of the month).
    
    Args:
        from_dt: Reference datetime
        
    Returns:
        Next monthly expiry date
    """
    current_date = from_dt.date()
    
    # Check if current month's expiry is still valid
    current_month_expiry = _get_last_thursday_of_month(current_date.year, current_date.month)
    
    if current_date < current_month_expiry:
        return current_month_expiry
    elif current_date == current_month_expiry:
        # If it's expiry day, check if market has closed
        ist_time = from_dt.astimezone(IST) if from_dt.tzinfo else IST.localize(from_dt)
        market_close_time = ist_time.replace(hour=15, minute=30, second=0, microsecond=0)
        if ist_time < market_close_time:
            return current_month_expiry
    
    # Move to next month
    if current_date.month == 12:
        next_year = current_date.year + 1
        next_month = 1
    else:
        next_year = current_date.year
        next_month = current_date.month + 1
    
    return _get_last_thursday_of_month(next_year, next_month)


def get_next_expiry(symbol: str, from_dt: datetime | None = None) -> date:
    """
    Get the next expiry date for a symbol.
    
    For symbols with weekly expiries, returns the nearest weekly expiry.
    Otherwise, returns the next monthly expiry.
    
    Args:
        symbol: Underlying symbol (NIFTY, BANKNIFTY, FINNIFTY, etc.)
        from_dt: Reference datetime (default: now in IST)
        
    Returns:
        Next expiry date
    """
    if from_dt is None:
        from_dt = datetime.now(IST)
    
    symbol_upper = symbol.upper()
    
    # Try weekly expiry first
    if symbol_upper in WEEKLY_EXPIRY_SYMBOLS:
        weekly_expiry = _get_next_weekly_expiry(symbol_upper, from_dt)
        if weekly_expiry:
            return weekly_expiry
    
    # Fallback to monthly expiry
    return _get_next_monthly_expiry(from_dt)


def is_expiry_day(symbol: str, dt: datetime | None = None) -> bool:
    """
    Check if the given datetime falls on an expiry day for the symbol.
    
    Args:
        symbol: Underlying symbol (NIFTY, BANKNIFTY, FINNIFTY, etc.)
        dt: Datetime to check (default: now in IST)
        
    Returns:
        True if dt is an expiry day for the symbol
    """
    if dt is None:
        dt = datetime.now(IST)
    
    try:
        next_expiry = get_next_expiry(symbol, dt)
        current_date = dt.date()
        
        # Check if today is the next expiry date
        if current_date == next_expiry:
            # Also ensure we haven't passed market close (15:30 IST)
            ist_time = dt.astimezone(IST) if dt.tzinfo else IST.localize(dt)
            market_close_time = ist_time.replace(hour=15, minute=30, second=0, microsecond=0)
            return ist_time < market_close_time
        
        return False
    except Exception as exc:
        logger.warning("Failed to check expiry day for %s: %s", symbol, exc)
        return False


def is_expiry_week(symbol: str, dt: datetime | None = None) -> bool:
    """
    Check if the given datetime falls within the same week as an expiry.
    
    Expiry week is defined as the 7-day period leading up to expiry day.
    
    Args:
        symbol: Underlying symbol (NIFTY, BANKNIFTY, FINNIFTY, etc.)
        dt: Datetime to check (default: now in IST)
        
    Returns:
        True if dt is within the expiry week
    """
    if dt is None:
        dt = datetime.now(IST)
    
    try:
        next_expiry = get_next_expiry(symbol, dt)
        current_date = dt.date()
        
        # Calculate start of expiry week (7 days before expiry, inclusive)
        week_start = next_expiry - timedelta(days=6)
        
        return week_start <= current_date <= next_expiry
    except Exception as exc:
        logger.warning("Failed to check expiry week for %s: %s", symbol, exc)
        return False


def get_time_to_expiry_minutes(symbol: str, dt: datetime | None = None) -> Optional[int]:
    """
    Get minutes remaining until market close on expiry day.
    
    Only returns a value if dt is actually on an expiry day.
    
    Args:
        symbol: Underlying symbol
        dt: Current datetime (default: now in IST)
        
    Returns:
        Minutes until market close (15:30 IST) if on expiry day, else None
    """
    if dt is None:
        dt = datetime.now(IST)
    
    if not is_expiry_day(symbol, dt):
        return None
    
    try:
        ist_time = dt.astimezone(IST) if dt.tzinfo else IST.localize(dt)
        market_close_time = ist_time.replace(hour=15, minute=30, second=0, microsecond=0)
        
        time_diff = market_close_time - ist_time
        minutes = int(time_diff.total_seconds() / 60)
        
        return max(0, minutes)  # Never negative
    except Exception as exc:
        logger.warning("Failed to calculate time to expiry for %s: %s", symbol, exc)
        return None


def get_session_time_ist(dt: datetime | None = None) -> str:
    """
    Get the current IST time in HH:MM format.
    
    Args:
        dt: Datetime to convert (default: now in IST)
        
    Returns:
        Time string in HH:MM format (IST)
    """
    if dt is None:
        dt = datetime.now(IST)
    
    try:
        ist_time = dt.astimezone(IST) if dt.tzinfo else IST.localize(dt)
        return ist_time.strftime("%H:%M")
    except Exception as exc:
        logger.warning("Failed to get session time: %s", exc)
        return "00:00"


def build_expiry_context(symbol: str, dt: datetime | None = None) -> dict:
    """
    Build a complete expiry context dictionary for a symbol.
    
    Args:
        symbol: Underlying symbol
        dt: Reference datetime (default: now in IST)
        
    Returns:
        Dictionary with expiry-related fields
    """
    if dt is None:
        dt = datetime.now(IST)
    
    try:
        next_expiry = get_next_expiry(symbol, dt)
        is_exp_day = is_expiry_day(symbol, dt)
        is_exp_week = is_expiry_week(symbol, dt)
        time_to_exp = get_time_to_expiry_minutes(symbol, dt)
        session_time = get_session_time_ist(dt)
        
        return {
            "is_expiry_day": is_exp_day,
            "is_expiry_week": is_exp_week,
            "next_expiry_dt": next_expiry.isoformat(),
            "time_to_expiry_minutes": time_to_exp,
            "session_time_ist": session_time,
        }
    except Exception as exc:
        logger.warning("Failed to build expiry context for %s: %s", symbol, exc)
        return {
            "is_expiry_day": False,
            "is_expiry_week": False,
            "next_expiry_dt": None,
            "time_to_expiry_minutes": None,
            "session_time_ist": "00:00",
        }
