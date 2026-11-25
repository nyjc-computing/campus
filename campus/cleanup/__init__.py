"""campus.cleanup — the fleet's one scheduled deployment.

Railway cron starts this deployment on a schedule; it runs every
registered cleanup job and exits. It is the ONLY scheduled thing in
the fleet: an inbound request wakes a serverless deployment and
resets its idle timer, so the app services (campus.auth, campus.api,
campus.audit) never host or trigger periodic work — scheduled cleanup
lives here, next to them in the repo, sharing their layers (#1249,
#1253).

The job implementations live in campus.cleanup.jobs and reuse the
resource layer and the storage API (no raw drivers, no HTTP). The
storage layer resolves one POSTGRESDB_URI and one MONGODB_URI per
process, so the runner points those at one service's databases at a
time — exactly how migrations/prod_job.py selects a service's DB —
and every job imports its resource module lazily inside the call.

One run writes one row in the `cleanup_runs` ledger (audit Postgres:
the audit scope is this deployment's ledger home) and holds a
session-level Postgres advisory lock for its duration, so cron ticks,
`railway cron run` triggers and manual runs never overlap; a run that
finds the lock held skips without writing anything and exits 0 (the
holder covers the work; the next scheduled run sweeps again).

Exit codes: 0 — every job ran, or nothing was selected; 1 — at least
one job raised (its error is in the ledger row and the service log),
so the deployment goes CRASHED and the failure is visible.

Railway setup, the variable matrix and the manual-run recipe:
docs/cleanup-deployment.md.
"""

import logging
import os
import time
import typing
from dataclasses import dataclass
from datetime import datetime, timezone

from campus.common import env
from campus.common.utils import uid

from . import jobs

logger = logging.getLogger(__name__)

LEDGER_TABLE = "cleanup_runs"

# Session-level advisory lock guarding one run ("clean" as a
# big-endian byte value; arbitrary but stable — the migration
# runner's apply lock uses its own "migr" key, so the two never
# contend).
ADVISORY_LOCK_KEY = 0x636C65616E

# How long a run polls for the advisory lock before skipping.
LOCK_WAIT_SECONDS = 30.0

# Full ledger schema defined up front; phase columns are nullable so a
# run in flight can be inserted before its outcomes exist (the
# migration runner's _migrations precedent).
LEDGER_DDL = f"""
CREATE TABLE IF NOT EXISTS "{LEDGER_TABLE}" (
    "id" TEXT PRIMARY KEY,
    "started_at" TIMESTAMPTZ NOT NULL,
    "finished_at" TIMESTAMPTZ,
    "status" TEXT NOT NULL,
    "triggered_by" TEXT,
    "jobs" JSONB,
    "rows_affected" INTEGER,
    "error" TEXT,
    "duration_ms" INTEGER
);
"""

# Scope -> the process env the storage layer resolves per connection.
# Values are the CLEANUP_JOB_* variables set on the deployment (Railway
# references to each service's databases). Scopes run in this dict's
# order; every scope a selected job needs is wired before any of its
# jobs run.
SCOPES: dict[str, dict[str, str]] = {
    "audit": {"POSTGRESDB_URI": "CLEANUP_JOB_AUDIT_POSTGRESDB_URI"},
    "auth": {
        "POSTGRESDB_URI": "CLEANUP_JOB_AUTH_POSTGRESDB_URI",
        "MONGODB_URI": "CLEANUP_JOB_AUTH_MONGODB_URI",
    },
}


@dataclass(frozen=True)
class Job:
    """One registered cleanup: its ledger name, scope and callable.

    The callable takes no arguments (job functions carry their own
    defaults) and returns the number of rows it deleted.
    """

    name: str
    scope: str
    sweep: typing.Callable[[], int]


JOBS: tuple[Job, ...] = (
    Job("audit.rate_limit_buckets", "audit", jobs.sweep_rate_limit_buckets),
    Job("auth.auth_sessions", "auth", jobs.sweep_auth_sessions),
    Job("auth.device_codes", "auth", jobs.sweep_device_codes),
)


def run(
        *,
        selected: typing.Sequence[str] | None = None,
        triggered_by: str = "cron",
        ledger_conn=None,
        job_list: tuple[Job, ...] | None = None,
) -> int:
    """Run the selected jobs once, ledger- and lock-guarded.

    Args:
        selected: job names to run; None runs every registered job. An
            unknown name raises ValueError (a typo'd --job must fail
            loudly, not silently skip).
        triggered_by: ledger attribution ("cron", or e.g.
            "manual:<operator>" for a hand-run).
        ledger_conn: injectable ledger connection (tests); defaults to
            a real connection to the audit Postgres.
        job_list: injectable job registry (tests); defaults to JOBS.

    Returns:
        0 when every selected job ran (including a lock-skip or an
        empty selection); 1 when at least one job raised.
    """
    registry = job_list or JOBS
    chosen = [job for job in registry
              if selected is None or job.name in selected]
    if selected is not None:
        unknown = set(selected) - {job.name for job in registry}
        if unknown:
            raise ValueError(
                f"unknown cleanup job(s): {', '.join(sorted(unknown))} — "
                "`python -m campus.cleanup --list` names the registered jobs"
            )
    unknown_scopes = {job.scope for job in chosen} - set(SCOPES)
    if unknown_scopes:
        raise ValueError(
            f"job scope(s) without a variable mapping: "
            f"{', '.join(sorted(unknown_scopes))} — add them to "
            "campus.cleanup.SCOPES and the deployment's variable matrix"
        )
    if not chosen:
        logger.info("no cleanup jobs selected — nothing to do")
        return 0

    own_conn = ledger_conn is None
    conn = ledger_conn if ledger_conn is not None else _connect_ledger()
    try:
        _ensure_ledger(conn)
        if not _acquire_lock(conn):
            logger.warning(
                "another cleanup run holds the advisory lock (waited "
                "%.0fs) — skipping without writing anything; the "
                "holder covers the work and the next run sweeps again",
                LOCK_WAIT_SECONDS,
            )
            return 0
        try:
            return _run_locked(conn, chosen, triggered_by)
        finally:
            _release_lock(conn)
    finally:
        if own_conn:
            conn.close()


def _connect_ledger():
    """Open the ledger connection (audit Postgres of this context)."""
    import psycopg2
    return psycopg2.connect(env.getsecret(
        SCOPES["audit"]["POSTGRESDB_URI"]))


def _ensure_ledger(conn) -> None:
    """Create the ledger table if missing. Idempotent."""
    with conn.cursor() as cursor:
        cursor.execute(LEDGER_DDL)
    conn.commit()


def _acquire_lock(conn, wait_seconds: float | None = None) -> bool:
    """Take the session-level advisory lock; poll, then give up False."""
    if wait_seconds is None:
        wait_seconds = LOCK_WAIT_SECONDS
    deadline = time.monotonic() + wait_seconds
    while True:
        with conn.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)",
                           (ADVISORY_LOCK_KEY,))
            row = cursor.fetchone()
        conn.commit()
        if row and row[0]:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.5)


def _release_lock(conn) -> None:
    """Release the advisory lock; the session close also would."""
    with conn.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_unlock(%s)", (ADVISORY_LOCK_KEY,))
    conn.commit()


def _apply_scope_env(scope: str) -> None:
    """Point the storage layer at one service's databases.

    Mirrors migrations/prod_job.py (#1104): copy each declared
    CLEANUP_JOB_* variable onto the name the storage layer resolves,
    and drop undeclared ones so a scope never sees a previous scope's
    databases. Resource modules import lazily inside the job
    functions, so the binding happens after this swap.
    """
    declared = SCOPES[scope]
    for var, source in declared.items():
        value = env.getsecret(source)
        if not value:
            raise OSError(
                f"{source} is not set — the cleanup deployment cannot "
                f"reach the {scope} service's database "
                "(docs/cleanup-deployment.md has the variable matrix)"
            )
        os.environ[var] = value
    for var in ("POSTGRESDB_URI", "MONGODB_URI"):
        if var not in declared:
            os.environ.pop(var, None)


def _run_locked(conn, chosen: list[Job], triggered_by: str) -> int:
    """The run proper; the caller holds the advisory lock."""
    from psycopg2.extras import Json

    run_id = uid.generate_uid()
    started_at = datetime.now(timezone.utc)
    start_counter = time.perf_counter()
    with conn.cursor() as cursor:
        cursor.execute(
            f'INSERT INTO "{LEDGER_TABLE}" '
            f'(id, started_at, status, triggered_by) '
            f"VALUES (%s, %s, %s, %s)",
            (run_id, started_at, "running", triggered_by),
        )
    conn.commit()

    entries: list[dict] = []
    scopes_in_order = [
        scope for scope in SCOPES
        if any(job.scope == scope for job in chosen)
    ]
    try:
        for scope in scopes_in_order:
            _apply_scope_env(scope)
            for job in (job for job in chosen if job.scope == scope):
                job_started = time.perf_counter()
                try:
                    rows = job.sweep()
                except Exception as e:  # noqa: BLE001 - recorded, run continues
                    entries.append({
                        "name": job.name,
                        "scope": scope,
                        "error": f"{type(e).__name__}: {e}",
                        "duration_ms": _ms_since(job_started),
                    })
                    logger.exception("cleanup job %s failed", job.name)
                else:
                    entries.append({
                        "name": job.name,
                        "scope": scope,
                        "rows_affected": rows,
                        "duration_ms": _ms_since(job_started),
                    })
                    logger.info("cleanup job %s: %d row(s) affected",
                                job.name, rows)

        failed = [entry for entry in entries if "error" in entry]
        status = "failed" if failed else "success"
        error = "; ".join(
            f"{entry['name']}: {entry['error']}" for entry in failed
        ) or None
        with conn.cursor() as cursor:
            cursor.execute(
                f'UPDATE "{LEDGER_TABLE}" SET '
                f"finished_at = %s, status = %s, jobs = %s, "
                f"rows_affected = %s, error = %s, duration_ms = %s "
                f"WHERE id = %s",
                (
                    datetime.now(timezone.utc),
                    status,
                    Json(entries),
                    sum(entry.get("rows_affected", 0) for entry in entries),
                    error,
                    _ms_since(start_counter),
                    run_id,
                ),
            )
        conn.commit()
        if failed:
            logger.error(
                "cleanup run %s finished with %d failed job(s) — see the "
                "ledger row for the errors", run_id, len(failed),
            )
        else:
            logger.info("cleanup run %s finished: %d job(s), %d row(s)",
                        run_id, len(entries),
                        sum(entry.get("rows_affected", 0) for entry in entries))
        return 1 if failed else 0
    except Exception as e:
        # The run itself broke (a scope variable missing, the ledger
        # write failed): leave the row loud, then surface the error.
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f'UPDATE "{LEDGER_TABLE}" SET '
                    f"finished_at = %s, status = %s, jobs = %s, "
                    f"error = %s, duration_ms = %s WHERE id = %s",
                    (
                        datetime.now(timezone.utc),
                        "failed",
                        Json(entries),
                        f"{type(e).__name__}: {e}",
                        _ms_since(start_counter),
                        run_id,
                    ),
                )
            conn.commit()
        except Exception:  # noqa: BLE001 - the original error matters more
            logger.exception("could not record the failed cleanup run")
        raise


def _ms_since(counter: float) -> int:
    return round((time.perf_counter() - counter) * 1000)
