"""campus.common.utils.utc_time.py

This module provides time-related utilities for the authentication service, and
is meant to replace all usage of the Python `time` module in those modules.

All timestamps are handled in UTC to avoid timezone issues.
"""

from datetime import UTC, date, datetime, time, timedelta
from typing import cast, overload

DAY_SECONDS = 86400


def now() -> datetime:
    """Get the current time in UTC."""
    return datetime.now(UTC)


def today() -> date:
    """Get the current date in UTC."""
    return now().date()


@overload
def after(dt: None = None, **delta) -> datetime: ...


@overload
def after(dt: datetime, **delta) -> datetime: ...


@overload
def after(dt: date, **delta) -> date: ...


def after(dt=None, **delta):
    """Create an expiry timestamp at a given timedelta.

    If dt is not specified, defaults to the current time.

    Keyword arguments:
    - **delta: follows that of timedelta
    """
    # Handle cases where dt is an unsupported type or None
    if dt is None:
        dt = now()
    elif not isinstance(dt, (datetime, date)):
        raise TypeError(f"Unsupported type for after: {dt}")

    if not delta:
        return dt

    # Dispatch based on type
    if isinstance(dt, datetime):
        return dt + timedelta(**delta)
    elif isinstance(dt, date):
        dt_obj = datetime(dt.year, dt.month, dt.day, tzinfo=UTC)
        return cast(datetime, after(dt_obj, **delta)).date()
    else:
        raise TypeError(f"Unsupported type for after: {dt}")


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
