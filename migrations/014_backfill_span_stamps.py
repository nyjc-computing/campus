"""Backfill the ingest stamps onto stored audit spans.

Revision ID: 014
Create Date: 2026-11-25

TARGET_DB is "audit": the spans table belongs to the audit service.

campus.audit now stamps every span it stores with ``tags.queue_ms``
(the wait between the request's arrival and the span's start, read
from ``X-Request-Start``) and producer spans with ``tags.producer_id``
(the API key that delivered them) — campus#1243, campus#1244. Spans
stored before that carry neither. This migration adds them to existing
rows in place:

- ``producer_id`` is recovered from the ``audit.traces.ingest`` event
  rows campus.audit used to write for every successful ingest. Each
  carries the delivering key in its ``api_key_id`` column and the batch
  it delivered in ``request_body.spans``. An environment that never had
  audit events on has no such rows, and its spans get no producer stamp.
- ``queue_ms`` is computed from each span's own request headers and
  ``started_at``.

A span that already carries a stamp is left alone, so the migration is
idempotent: safe to re-run, and safe to run before the service that
writes the stamps has deployed.

The arrival-header parsing below is a frozen copy of
``campus.audit.helpers.span_enrichment``. Migrations are self-contained
and do not import service modules (docs/migration-protocol.md, "File
conventions").

Run from a context where the audit service's POSTGRESDB_URI resolves:

    python migrations/014_backfill_span_stamps.py            # dry run
    python migrations/014_backfill_span_stamps.py --apply    # write

or through the runner, which applies pending audit migrations:

    python migrations/runner.py apply --db audit
"""

import argparse
import datetime
import math
import typing

from campus.storage import get_table, gt

TARGET_DB = "audit"

# Keyset-paginated by id: the ids are random, which gives a stable total
# order, and a row inserted mid-run cannot shift the window.
BATCH_SIZE = 500

INGEST_PATH = "/audit/v1/traces/"
INGEST_EVENT = "audit.traces.ingest"
DELIVERED_STATUSES = (200, 201, 207)

PRODUCER_TAG = "producer_id"
QUEUE_TAG = "queue_ms"

# Epoch seconds at or above this are really epoch milliseconds: 1e11
# seconds is the year 5138, 1e11 milliseconds is 1973.
_MILLISECOND_FLOOR = 1e11

# A wait longer than an hour in either direction is clock skew or a
# client-supplied stamp, not queueing.
_MAX_QUEUE_MS = 3_600_000.0


def _parse_request_start(value: typing.Any) -> float | None:
    """Epoch seconds from an X-Request-Start value, or None.

    Railway's edge sends bare epoch milliseconds; the gateway stamp that
    PR #1242 added and #1250 removed sent ``t=<seconds.milliseconds>``.
    Stored spans carry both, so the unit follows the magnitude.
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
    return seconds / 1000.0 if seconds >= _MILLISECOND_FLOOR else seconds


def _queue_ms(row: dict) -> float | None:
    """Milliseconds between the request's arrival and the span's start."""
    headers = row.get("request_headers")
    arrival = None
    if isinstance(headers, dict):
        arrival = next(
            (
                value for key, value in headers.items()
                if isinstance(key, str) and key.lower() == "x-request-start"
            ),
            None,
        )
    arrival = _parse_request_start(arrival)
    if arrival is None:
        return None
    try:
        started = datetime.datetime.fromisoformat(str(row.get("started_at")))
    except (TypeError, ValueError, OverflowError, OSError):
        return None
    elapsed = (started.timestamp() - arrival) * 1000.0
    if abs(elapsed) > _MAX_QUEUE_MS:
        return None
    return round(elapsed, 3)


def _producer_map(spans, *, batch_size: int = BATCH_SIZE) -> dict[str, str]:
    """Map span id to the API key that delivered it.

    Reads the historical ``audit.traces.ingest`` event rows: a rejected
    ingest references spans that were never stored, so only delivered
    statuses count.
    """
    mapping: dict[str, str] = {}
    after: str | None = None
    while True:
        query: dict[str, typing.Any] = {"path": INGEST_PATH}
        if after is not None:
            query["id"] = gt(after)
        rows = spans.get_matching(
            query, order_by="id", ascending=True, limit=batch_size
        )
        if not rows:
            return mapping
        for row in rows:
            after = row["id"]
            if row.get("status_code") not in DELIVERED_STATUSES:
                continue
            if (row.get("tags") or {}).get("event_type") != INGEST_EVENT:
                continue
            producer = row.get("api_key_id")
            body = row.get("request_body")
            batch = body.get("spans") if isinstance(body, dict) else None
            if not producer or not isinstance(batch, list):
                continue
            for span in batch:
                if isinstance(span, dict) and span.get("span_id"):
                    mapping.setdefault(span["span_id"], producer)


def _missing_stamps(row: dict, producers: dict[str, str]) -> dict | None:
    """The tags this row lacks, or None when it has everything it can get."""
    tags = row.get("tags") or {}
    missing: dict[str, typing.Any] = {}
    if PRODUCER_TAG not in tags and row.get("id") in producers:
        missing[PRODUCER_TAG] = producers[row["id"]]
    if QUEUE_TAG not in tags:
        wait = _queue_ms(row)
        if wait is not None:
            missing[QUEUE_TAG] = wait
    return missing or None


def backfill(
    spans,
    producers: dict[str, str],
    *,
    apply: bool,
    limit: int | None = None,
    batch_size: int = BATCH_SIZE,
) -> dict[str, int]:
    """Add the missing stamps to every stored span.

    Args:
        spans: The spans table
        producers: Span id to delivering API key, from _producer_map
        apply: Write the changes; otherwise only count them
        limit: Stop after scanning this many spans, for a cautious first run
        batch_size: Rows fetched per query

    Returns:
        Counts: scanned, producer_stamped, queue_stamped, unchanged
    """
    counts = {
        "scanned": 0,
        "producer_stamped": 0,
        "queue_stamped": 0,
        "unchanged": 0,
    }
    after: str | None = None
    while limit is None or counts["scanned"] < limit:
        rows = spans.get_matching(
            {} if after is None else {"id": gt(after)},
            order_by="id",
            ascending=True,
            limit=batch_size,
        )
        if not rows:
            break
        for row in rows:
            after = row["id"]
            if limit is not None and counts["scanned"] >= limit:
                break
            counts["scanned"] += 1
            missing = _missing_stamps(row, producers)
            if not missing:
                counts["unchanged"] += 1
                continue
            if apply:
                spans.update_by_id(row["id"], {
                    "tags": {**(row.get("tags") or {}), **missing},
                })
            counts["producer_stamped"] += int(PRODUCER_TAG in missing)
            counts["queue_stamped"] += int(QUEUE_TAG in missing)
    return counts


def _report(producers: dict[str, str], counts: dict[str, int], apply: bool) -> None:
    """Print what a run found and, for a dry run, that nothing was written."""
    verb = "stamped" if apply else "to stamp"
    print(f"ingest events: {len(producers)} delivered spans recovered")
    print(
        f"spans: {counts['scanned']} scanned, "
        f"{counts['producer_stamped']} {verb} with producer_id, "
        f"{counts['queue_stamped']} {verb} with queue_ms, "
        f"{counts['unchanged']} already stamped or not stampable"
    )
    if not apply:
        print("dry run: no changes written (pass --apply to write)")


def upgrade(apply: bool = False) -> None:
    """Add ``tags.producer_id`` and ``tags.queue_ms`` to existing spans."""
    spans = get_table("spans")
    producers = _producer_map(spans)
    counts = backfill(spans, producers, apply=apply)
    _report(producers, counts, apply)


def downgrade() -> None:
    """Remove both stamps from every span. Idempotent.

    Both are derived values, so a re-run of upgrade() recreates them —
    ``producer_id`` only where the historical ingest events still exist.
    """
    spans = get_table("spans")
    removed = 0
    after: str | None = None
    while True:
        rows = spans.get_matching(
            {} if after is None else {"id": gt(after)},
            order_by="id",
            ascending=True,
            limit=BATCH_SIZE,
        )
        if not rows:
            break
        for row in rows:
            after = row["id"]
            tags = dict(row.get("tags") or {})
            if PRODUCER_TAG not in tags and QUEUE_TAG not in tags:
                continue
            tags.pop(PRODUCER_TAG, None)
            tags.pop(QUEUE_TAG, None)
            spans.update_by_id(row["id"], {"tags": tags})
            removed += 1
    print(f"spans: {removed} unstamped")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Backfill tags.producer_id and tags.queue_ms onto stored "
                    "audit spans (campus#1243, campus#1244).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write changes (default: dry run)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="stop after scanning this many spans",
    )
    args = parser.parse_args()
    spans = get_table("spans")
    producers = _producer_map(spans)
    counts = backfill(spans, producers, apply=args.apply, limit=args.limit)
    _report(producers, counts, args.apply)
