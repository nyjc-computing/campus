"""time.py
Time Utilities Module

This module provides time-related utilities for the authentication service, and
is meant to replace all usage of the Python `time` module in those modules.

All timestamps are handled in UTC to avoid timezone issues.
"""

from datetime import UTC, datetime, timedelta


def now() -> datetime:
    """Get the current time in UTC."""
    return datetime.now(UTC)

def after(**kwargs) -> datetime:
    """Create an expiry timestamp at a given time from now.

    Keyword arguments:
    - follows that of timedelta
    """
    if kwargs:
        return now() + timedelta(**kwargs)
    else:
        return now()

def is_expired(ts: datetime | float, threshold: float | int = 1) -> bool:
    """Check if a timestamp has expired (within threshold)"""
    # Convert to float timestamp
    ts = ts.timestamp() if isinstance(ts, datetime) else ts
    return -threshold < now().timestamp() - ts < threshold

def from_rfc3339(dtstr: str) -> datetime:
    """Parse an RFC3339 formatted string into a datetime object."""
    return datetime.fromisoformat(dtstr)

def to_rfc3339(dt: datetime) -> str:
    """Convert a datetime object to an RFC3339 formatted string."""
    return dt.isoformat()
