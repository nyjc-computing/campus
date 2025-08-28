"""campus.common.utils.utc_time.py

This module provides time-related utilities for the authentication service, and
is meant to replace all usage of the Python `time` module in those modules.

All timestamps are handled in UTC to avoid timezone issues.
"""

from datetime import UTC, datetime, timedelta


def now() -> datetime:
    """Get the current time in UTC."""
    return datetime.now(UTC)

def after(time: datetime | None = None, **delta) -> datetime:
    """Create an expiry timestamp at a given delta after time.

    If time is not specified, defaults to the current time.

    Keyword arguments:
    - **delta: follows that of timedelta
    """
    time = time or now()
    if delta:
        return time + timedelta(**delta)
    else:
        return time

def is_expired(ts: datetime | float, *, from_time: datetime | None = None, threshold: float | int = 1) -> bool:
    """Check if a timestamp has expired (within threshold)"""
    # Convert to float timestamp
    ts = ts.timestamp() if isinstance(ts, datetime) else ts
    from_time = from_time or now()
    return -threshold < from_time.timestamp() - ts < threshold

def from_rfc3339(dtstr: str) -> datetime:
    """Parse an RFC3339 formatted string into a datetime object."""
    return datetime.fromisoformat(dtstr)

def to_rfc3339(dt: datetime) -> str:
    """Convert a datetime object to an RFC3339 formatted string."""
    return dt.isoformat()
