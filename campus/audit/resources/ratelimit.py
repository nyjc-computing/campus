"""campus.audit.resources.ratelimit

Token-bucket rate limiting for audit span ingestion.

Phase 3 of the API key security epic (#538), tracked in #831. Design:
https://github.com/nyjc-computing/campus/issues/538#issuecomment-5996377544

Summary:
- Per-minute token bucket; burst capacity = the per-minute rate, refill
  at rate/60 per second. Only POST /traces/ingest is limited (v1).
- One row of state per active bucket in the rate_limit_buckets table.
- Bucket key encodes the span's identity, in priority order:
  (client_id, user_id) > user_id > client_id > producer API key
  (identity-less spans, e.g. pre-auth login hops). Device IDs are
  deliberately excluded (ephemeral, unbounded cardinality); the key
  format leaves room for a device dimension later.
- Denied batches raise RateLimitError with Retry-After and the tripped
  bucket key, so producers can trip a per-identity circuit breaker.
  429s are logged at WARN by the route and never recorded as spans.

Concurrency note: the storage tables API has no atomic
compare-and-swap, so consumption is read-decide-write with the
allow/reject decision made from the read state. This never
false-rejects; concurrent same-bucket batches can over-admit, which is
accepted by design ("the limit need not be strictly adhered to").
Row state is last-write-wins, which is correct-enough under the
relaxed adherence model and multi-worker safe.
"""

__all__ = [
    "bucket_key",
    "consume_for_spans",
    "get_rate_limit_per_minute",
    "init_storage",
]

import logging
import math
import time
import typing

import campus.storage
from campus.common import env

logger = logging.getLogger(__name__)

bucket_storage = campus.storage.tables.get_db("rate_limit_buckets")

# Default spans per minute per identity bucket. Placeholder pending
# measurement of real per-identity rates on dev; the deploy runbook
# tunes this via AUDIT_RATE_LIMIT_PER_MINUTE (#831).
DEFAULT_RATE_LIMIT_PER_MINUTE = 600

# A bucket idle for this long is deleted opportunistically. Refill
# math treats a long-idle bucket as full regardless, so this is
# hygiene only, not correctness.
BUCKET_TTL_SECONDS = 3600.0

# How often (at most) stale buckets are swept, per worker.
CLEANUP_INTERVAL_SECONDS = 3600.0

_last_cleanup = 0.0


def get_rate_limit_per_minute() -> int:
    """Read the per-minute limit from env, falling back to the default.

    An invalid value fails open (default applied, WARN logged) rather
    than breaking ingestion.
    """
    raw = env.get("AUDIT_RATE_LIMIT_PER_MINUTE")
    if not raw:
        return DEFAULT_RATE_LIMIT_PER_MINUTE
    try:
        limit = int(raw)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid AUDIT_RATE_LIMIT_PER_MINUTE=%r; using default %d",
            raw, DEFAULT_RATE_LIMIT_PER_MINUTE,
        )
        return DEFAULT_RATE_LIMIT_PER_MINUTE
    if limit < 1:
        logger.warning(
            "AUDIT_RATE_LIMIT_PER_MINUTE=%d < 1; using default %d",
            limit, DEFAULT_RATE_LIMIT_PER_MINUTE,
        )
        return DEFAULT_RATE_LIMIT_PER_MINUTE
    return limit


def bucket_key(
        client_id: str | None,
        user_id: str | None,
        api_key_id: str | None = None,
) -> str:
    """Encode a span's identity into a rate-limit bucket key.

    Priority: (client_id, user_id) pair > user_id alone > client_id
    alone > producer API key fallback (identity-less spans).

    Args:
        client_id: OAuth client tag on the span (may be None).
        user_id: User tag on the span (may be None).
        api_key_id: Authenticated producer API key (flask.g.api_key_id),
            used only when the span carries no identity.

    Returns:
        Stable string key for the rate_limit_buckets table.
    """
    if client_id and user_id:
        return f"client={client_id};user={user_id}"
    if user_id:
        return f"user={user_id}"
    if client_id:
        return f"client={client_id}"
    return f"apikey={api_key_id or 'unknown'}"


def consume_for_spans(
        spans: typing.Iterable[typing.Any],
        api_key_id: str | None = None,
) -> tuple[str | None, int]:
    """Consume one token per span before ingesting a batch.

    All-or-nothing: if any identity bucket in the batch cannot afford
    its token count, nothing is consumed and the batch is denied.

    Args:
        spans: TraceSpan model instances (duck-typed: client_id,
            user_id attributes).
        api_key_id: Authenticated producer API key for the
            identity-less fallback bucket.

    Returns:
        (tripped_bucket_key, retry_after_seconds): the key is None when
        the whole batch is allowed; retry_after is 0 unless denied.
    """
    now = time.time()
    _maybe_cleanup(now)

    bucket_counts: dict[str, int] = {}
    for span in spans:
        key = bucket_key(span.client_id, span.user_id, api_key_id)
        bucket_counts[key] = bucket_counts.get(key, 0) + 1
    if not bucket_counts:
        return None, 0

    limit = get_rate_limit_per_minute()
    return _consume_buckets(bucket_counts, limit, now)


def _consume_buckets(
        bucket_counts: dict[str, int],
        limit: int,
        now: float,
) -> tuple[str | None, int]:
    """Check every bucket, then write the decrements.

    The allow/reject decision comes from the read state, so a race can
    only over-admit, never false-reject (see module docstring).
    """
    rate_per_sec = limit / 60.0

    # Read phase: verify every bucket can afford its count.
    pending: list[tuple[str, dict | None, float, int]] = []
    for key, count in bucket_counts.items():
        row = _get_row(key)
        if row is None:
            tokens = float(limit)  # new bucket starts full
        else:
            elapsed = max(0.0, now - float(row["last_refill"]))
            tokens = min(
                float(limit),
                float(row["tokens"]) + elapsed * rate_per_sec,
            )
        if tokens + 1e-9 < count:
            if count > limit:
                # A batch larger than the bucket capacity can never
                # fit at once; ask for a full window instead of a
                # meaningless fractional wait.
                return key, 60
            retry_after = max(
                1, int(math.ceil((count - tokens) * 60.0 / limit))
            )
            return key, retry_after
        pending.append((key, row, tokens, count))

    # Write phase: apply decrements (insert missing buckets).
    try:
        for key, row, tokens, count in pending:
            new_tokens = tokens - count
            if row is None:
                try:
                    bucket_storage.insert_one({
                        "id": key,
                        "tokens": new_tokens,
                        "last_refill": now,
                    })
                except campus.storage.ConflictError:
                    # Raced with another worker's insert; fold this
                    # batch into the winner's row (last-write-wins).
                    _fold_into_existing(key, new_tokens, now)
            else:
                bucket_storage.update_by_id(key, {
                    "tokens": new_tokens,
                    "last_refill": now,
                })
    except Exception:
        # Storage failure must not fail ingestion (fail-open); the
        # next successful write re-anchors the bucket state.
        logger.exception("rate limiter write failed; allowing batch")
    return None, 0


def _fold_into_existing(key: str, new_tokens: float, now: float) -> None:
    """Merge a lost insert race into the existing row, best-effort."""
    try:
        row = _get_row(key)
        if row is None:
            return
        bucket_storage.update_by_id(key, {
            "tokens": min(float(row["tokens"]), new_tokens),
            "last_refill": now,
        })
    except Exception:
        logger.exception("rate limiter race fold failed for %s", key)


def _get_row(key: str) -> dict | None:
    """Fetch one bucket row, or None when the bucket is new."""
    rows = bucket_storage.get_matching({"id": key})
    return rows[0] if rows else None


def _maybe_cleanup(now: float) -> None:
    """Opportunistically sweep stale buckets, at most once per hour."""
    global _last_cleanup
    if now - _last_cleanup < CLEANUP_INTERVAL_SECONDS:
        return
    _last_cleanup = now
    try:
        bucket_storage.delete_matching({
            "last_refill": campus.storage.lt(now - BUCKET_TTL_SECONDS),
        })
    except Exception:
        logger.exception("rate limit bucket cleanup failed")


def init_storage() -> None:
    """Initialize the rate_limit_buckets table (idempotent)."""
    import campus.model as model

    bucket_storage.init_from_model("rate_limit_buckets", model.RateLimitBucket)
