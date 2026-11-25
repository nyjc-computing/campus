"""campus.cleanup.jobs — the cleanup implementations the deployment runs.

One function per job: idempotent, chunked (keyset-paginated by id,
BATCH_SIZE rows per query), and catching up naturally from the expiry
predicate — anything still expired at the next run is swept then.
"Nothing to do" is a success: a job returns 0 and the run is recorded
as successful.

Every function imports its resource module lazily, INSIDE the call.
The storage layer resolves POSTGRESDB_URI / MONGODB_URI per process,
and this deployment points those at one service's databases at a time
(campus.cleanup.SCOPES); a module-level import would bind whichever
scope imported first for the whole process.

Deletion rules (#1253): jobs delete only the expired or stale rows
named here. `credentials` rows and the `tokens` documents they point
to are never touched by any job.
"""

import logging
import time
import typing

import campus.storage
from campus.common import schema

logger = logging.getLogger(__name__)

# Rows per get_matching query. Id-keyset pagination keeps a chunk
# stable while earlier chunks are deleted, and ids are random, so the
# order is stable under concurrent inserts (migrations/014's
# reasoning).
BATCH_SIZE = 500


def sweep_rate_limit_buckets(
        *,
        now: float | None = None,
        batch_size: int = BATCH_SIZE,
) -> int:
    """Delete stale ingest rate-limit buckets (audit Postgres).

    A bucket is stale when nothing has consumed from it for
    BUCKET_TTL_SECONDS: refill brings it back to full, so deleting it
    cannot change a limit decision. This used to run inline on every
    ingest (campus.audit.resources.ratelimit._maybe_cleanup, at most
    once per hour); scheduled cleanup runs here instead — nothing on
    the request path but the limit check itself (#1249).

    Returns the number of buckets deleted.
    """
    from campus.audit.resources import ratelimit
    if now is None:
        now = time.time()
    cutoff = now - ratelimit.BUCKET_TTL_SECONDS
    storage = ratelimit.bucket_storage
    deleted = 0
    after: str | None = None
    while True:
        query: dict[str, typing.Any] = {
            "last_refill": campus.storage.lt(cutoff),
        }
        if after is not None:
            query["id"] = campus.storage.gt(after)
        rows = storage.get_matching(
            query, order_by="id", ascending=True, limit=batch_size
        )
        if not rows:
            return deleted
        for row in rows:
            after = row["id"]
            try:
                storage.delete_by_id(row["id"])
            except campus.storage.errors.NotFoundError:
                continue  # raced away between fetch and delete
            deleted += 1


def sweep_auth_sessions(
        *,
        at_time: schema.DateTime | None = None,
        batch_size: int = BATCH_SIZE,
) -> int:
    """Delete expired auth sessions (auth Mongo).

    Expiry is decided by the model predicate
    (``AuthSession.is_expired``) — the same one the live-session
    checks use — so the sweep can never delete a session the app
    would consider live. A chunked rewrite of
    ``AuthSessionsResource.sweep`` (fetch-all-then-filter), whose
    only other caller, POST /auth/v1/sessions/sweep, delegates here.
    The collection is resolved through the storage API directly:
    ``campus.auth.resources`` shadows its submodules with singleton
    instances, so the resource module's storage handle is not
    reachable as an attribute.

    Returns the number of sessions deleted.
    """
    import campus.model as model
    storage = campus.storage.get_collection("auth_sessions")
    return _sweep_expired(
        storage,
        model.AuthSession,
        at_time=at_time,
        batch_size=batch_size,
    )


def sweep_device_codes(
        *,
        at_time: schema.DateTime | None = None,
        batch_size: int = BATCH_SIZE,
) -> int:
    """Delete expired device codes (auth Mongo).

    A chunked rewrite of ``DeviceCodeResource.sweep`` — until the
    cleanup deployment existed, nothing called it and expired codes
    accumulated forever (#1253). Resolved through the storage API
    directly, as sweep_auth_sessions does.

    Returns the number of device codes deleted.
    """
    import campus.model as model
    storage = campus.storage.get_collection("device_codes")
    return _sweep_expired(
        storage,
        model.DeviceCode,
        at_time=at_time,
        batch_size=batch_size,
    )


def _sweep_expired(
        storage,
        model_cls,
        *,
        at_time: schema.DateTime | None,
        batch_size: int,
) -> int:
    """Keyset-paginated sweep of rows a model's is_expired() retires."""
    deleted = 0
    after: str | None = None
    while True:
        query: dict[str, typing.Any] = {}
        if after is not None:
            query["id"] = campus.storage.gt(after)
        rows = storage.get_matching(
            query, order_by="id", ascending=True, limit=batch_size
        )
        if not rows:
            return deleted
        for record in rows:
            after = record["id"]
            instance = model_cls.from_storage(record)
            if instance.is_expired(at_time=at_time):
                try:
                    storage.delete_by_id(instance.id)
                except campus.storage.errors.NotFoundError:
                    continue  # raced away between fetch and delete
                deleted += 1
