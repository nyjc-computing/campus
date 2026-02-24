"""campus.common.utils.utc_time.py

This module provides time-related utilities for the authentication service, and
is meant to replace all usage of the Python `time` module in those modules.

All timestamps are handled in UTC to avoid timezone issues.
"""

from functools import singledispatch
from datetime import UTC, date, datetime, time, timedelta
from typing import cast

DAY_SECONDS = 86400


def now() -> datetime:
    """Get the current time in UTC."""
    return datetime.now(UTC)


def today() -> date:
    """Get the current date in UTC."""
    return now().date()


@singledispatch
def after(_dt=None, **delta):
    """Create an expiry timestamp at a given timedelta.

    If time is not specified, defaults to the current time.

    Keyword arguments:
    - **delta: follows that of timedelta
    """
    # Handle cases where _dt is an unsupported type or None
    if _dt is None:
        _dt = now()
    elif not isinstance(_dt, (datetime, date, time)):
        raise TypeError(f"Unsupported type for after: {_dt}")
    if not delta:
        return _dt
    return after(_dt, **delta)

@after.register
def _(dt: datetime, **delta) -> datetime:
    """Create an expiry timestamp at a given delta after time.

    Keyword arguments:
    - **delta: follows that of timedelta
    """
    return dt + timedelta(**delta)

@after.register
def _(d: date, **delta) -> date:
    """Create an expiry date at a given delta after date."""
    dt = datetime(d.year, d.month, d.day, tzinfo=UTC)
    return cast(datetime, after(dt, **delta)).date()

@after.register
def _(t: time, **delta) -> time:
    """Create an expiry time at a given delta after time."""
    dt = datetime(1970, 1, 1, t.hour, t.minute, t.second, tzinfo=UTC)
    return cast(datetime, after(dt, **delta)).time()


def is_expired(ts: datetime | float, *, at_time: datetime | None = None, threshold: float | int = 1) -> bool:
    """Check if a timestamp has expired (within threshold)"""
    # Convert to float timestamp
    ts = ts.timestamp() if isinstance(ts, datetime) else ts
    at_ts = (at_time or now()).timestamp()
    # A timestamp is considered expired when the difference between the
    # reference time (`at_time` or now) and the timestamp is greater
    # than the provided threshold (i.e. more than `threshold` seconds in
    # the past).
    return (at_ts - ts) > threshold


def from_rfc3339(dtstr: str) -> datetime:
    """Parse an RFC3339 formatted string into a datetime object."""
    return datetime.fromisoformat(dtstr)


def to_rfc3339(d_t: date | datetime | time) -> str:
    """Convert a datetime object to an RFC3339 formatted string."""
    return d_t.isoformat()


def from_timestamp(ts: int) -> datetime:
    """Create a datetime object from a UTC timestamp."""
    return datetime.fromtimestamp(ts, tz=UTC)


def to_timestamp(dt: datetime) -> int:
    """Convert a datetime object to a UTC timestamp."""
    return int(dt.timestamp())
