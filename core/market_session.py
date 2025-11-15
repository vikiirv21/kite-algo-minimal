from __future__ import annotations

from datetime import datetime, date, time, timedelta
from typing import Optional, Set


# IST offset from UTC: +5:30
IST_OFFSET = timedelta(hours=5, minutes=30)


def now_ist() -> datetime:
    """
    Return current time in India Standard Time (IST), computed from UTC.

    This avoids needing external timezone libraries and is sufficient
    for deciding regular NSE/BSE session open/close.
    """
    return datetime.utcnow() + IST_OFFSET


def _holiday_dates() -> Set[date]:
    """
    Placeholder for Indian market holidays.

    For now this returns an empty set. You can extend this with concrete
    NSE holiday dates for the current year, e.g.:

        return {
            date(2025, 1, 26),  # Republic Day (if trading holiday)
            ...
        }

    The rest of the code will automatically respect anything added here.
    """
    return set()


def is_holiday(now: Optional[datetime] = None) -> bool:
    """
    Return True if 'now' (IST) falls on a configured trading holiday.
    """
    if now is None:
        now = now_ist()
    holidays = _holiday_dates()
    return now.date() in holidays


def is_market_open(now: Optional[datetime] = None) -> bool:
    """
    Basic check for Indian cash / derivatives regular session:

        - Monday to Friday (weekday 0-4)
        - 09:00 <= time <= 15:30 IST
        - Not a configured holiday

    This is intentionally simple but good enough for paper/live gating.
    """
    if now is None:
        now = now_ist()

    # Weekend check
    if now.weekday() >= 5:  # 5=Saturday, 6=Sunday
        return False

    # Holiday hook
    if is_holiday(now):
        return False

    t = now.time()
    start = time(9, 0)      # 09:00 IST
    end = time(15, 30)      # 15:30 IST

    return start <= t <= end
