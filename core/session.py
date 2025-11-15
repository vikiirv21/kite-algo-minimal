"""
Market session helpers for NSE F&O.

For now:
- Only handles regular NSE F&O session (09:15–15:30 IST).
- Simple time-based checks using local system time.

Later:
- Can be extended with official holiday calendar.
- Can add "no-new-positions" window near close (e.g. after 15:20).
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Tuple


# NSE F&O regular session times (approx, local system time assumed to be IST)
SESSION_START = time(hour=9, minute=15)
SESSION_END = time(hour=15, minute=30)

# Optional "no new positions" window near close (only exits allowed).
NO_NEW_POSITIONS_AFTER = time(hour=15, minute=20)


def _time_in_range(start: time, end: time, now: time) -> bool:
    """Return True if now is in the [start, end] range."""
    if start <= end:
        return start <= now <= end
    # Not expected for NSE, but handle overnight ranges generically
    return start <= now or now <= end


def is_market_open(now: datetime | None = None) -> bool:
    """
    Return True if we are inside the regular NSE F&O session.

    NOTE: This does not yet check holidays. It is purely a time-of-day guard.
    """
    now = now or datetime.now()
    t = now.time()
    return _time_in_range(SESSION_START, SESSION_END, t)


def can_open_new_positions(now: datetime | None = None) -> bool:
    """
    Return True if it is still acceptable to open NEW positions.

    For now:
    - We allow new positions only until NO_NEW_POSITIONS_AFTER (<= 15:20).
    - After that time, engines may still close / reduce positions, but
      should avoid opening fresh exposure.
    """
    now = now or datetime.now()
    t = now.time()
    if not is_market_open(now):
        return False
    return t <= NO_NEW_POSITIONS_AFTER


def session_status(now: datetime | None = None) -> Tuple[bool, bool]:
    """
    Convenience helper.

    Returns:
        (market_open, can_open_new_positions)
    """
    now = now or datetime.now()
    return is_market_open(now), can_open_new_positions(now)
