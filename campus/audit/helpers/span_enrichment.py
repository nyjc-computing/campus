"""campus.audit.helpers.span_enrichment

Stamps campus.audit adds to a span as it is ingested (#1243, #1244).

Two facts about a request are known only at the edges, so the audit
service records them itself instead of trusting the producer:

- ``tags.producer_id``: the API key that delivered the span. The ingest
  request is authenticated with the producer's own key, so this is the
  one attribution a producer cannot get wrong. Before it existed, a
  stored span did not say which service produced it; only the path
  prefix hinted at it.
- ``tags.queue_ms``: milliseconds between the request's arrival and the
  span's ``started_at``. The arrival time rides in ``X-Request-Start``,
  which Railway's edge sets on every public request. It is the only
  view of the time a request waited before a worker picked it up.

Both live in the free-form ``tags`` dict (zero migrations), so every
read surface shows them without a model change.
"""

__all__ = [
    "PRODUCER_TAG",
    "QUEUE_TAG",
    "parse_request_start",
    "queue_ms",
    "stamp",
]

import datetime
import math
import typing

import campus.model as model

PRODUCER_TAG = "producer_id"
QUEUE_TAG = "queue_ms"

REQUEST_START_HEADER = "x-request-start"

# Epoch seconds at or above this are really epoch milliseconds: 1e11
# seconds is the year 5138, 1e11 milliseconds is 1973.
_MILLISECOND_FLOOR = 1e11

# A wait longer than an hour in either direction is clock skew or a
# client-supplied stamp, not queueing, and would poison averages.
_MAX_QUEUE_MS = 3_600_000.0


def parse_request_start(value: typing.Any) -> float | None:
    """Parse an X-Request-Start value into epoch seconds.

    Two forms are in use. Railway's edge sends bare epoch milliseconds
    (``1795515478341``); the gateway stamp that PR #1242 added and
    #1250 removed sent Heroku-style ``t=<seconds.milliseconds>``
    (``t=1795515478.341``). Stored spans carry both, so the unit is
    decided by magnitude and the ``t=`` prefix is optional.

    Args:
        value: Raw header value (anything non-string yields None)

    Returns:
        Epoch seconds, or None when the value is absent, not a number,
        not finite, or not positive.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text[:2].lower() == "t=":
        text = text[2:]
    try:
        seconds = float(text)
    except ValueError:
        return None
    if not math.isfinite(seconds) or seconds <= 0:
        return None
    if seconds >= _MILLISECOND_FLOOR:
        seconds /= 1000.0
    return seconds


def queue_ms(
    started_at: typing.Any,
    request_headers: typing.Mapping[str, typing.Any] | None,
) -> float | None:
    """Milliseconds between a request's arrival and its span's start.

    The result is signed: a negative value means the producer's clock
    ran behind the edge's.

    Args:
        started_at: The span's start (a schema.DateTime or ISO 8601 string)
        request_headers: The span's request headers, any key case

    Returns:
        The wait in milliseconds rounded to 3 decimals, or None when the
        headers carry no usable X-Request-Start, the start does not
        parse, or the wait exceeds an hour either way.
    """
    arrival = parse_request_start(_header(request_headers, REQUEST_START_HEADER))
    if arrival is None:
        return None
    to_datetime = getattr(started_at, "to_datetime", None)
    try:
        if callable(to_datetime):
            started = typing.cast(datetime.datetime, to_datetime())
        else:
            started = datetime.datetime.fromisoformat(str(started_at))
    except (TypeError, ValueError, OverflowError, OSError):
        return None
    elapsed = (started.timestamp() - arrival) * 1000.0
    if abs(elapsed) > _MAX_QUEUE_MS:
        return None
    return round(elapsed, 3)


def stamp(span: model.TraceSpan, *, producer_id: str | None = None) -> dict:
    """Build a span's storage row with the server-side stamps applied.

    Both stamps are the audit service's own assertion, so a value the
    producer supplied under either tag is dropped before the real one
    is written.

    Args:
        span: The span about to be stored
        producer_id: The API key that delivered the span, or None for
            the audit service's own events

    Returns:
        The storage row (``span.to_storage()``) with ``tags`` extended
    """
    row = span.to_storage()
    tags = dict(row.get("tags") or {})
    tags.pop(PRODUCER_TAG, None)
    tags.pop(QUEUE_TAG, None)
    if producer_id:
        tags[PRODUCER_TAG] = producer_id
    wait = queue_ms(row.get("started_at"), row.get("request_headers"))
    if wait is not None:
        tags[QUEUE_TAG] = wait
    row["tags"] = tags
    return row


def _header(
    headers: typing.Mapping[str, typing.Any] | None,
    name: str,
) -> typing.Any:
    """Case-insensitive header lookup; None when absent."""
    if not headers:
        return None
    for key, value in headers.items():
        if isinstance(key, str) and key.lower() == name:
            return value
    return None
