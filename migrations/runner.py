"""Migration runner: applied-migrations ledger + migration execution.

Revision ID: n/a (the runner is not itself a migration)
Create Date: 2026-10-03

Applied state is tracked in a `_migrations` table **per service
database** (#1104): schema is per-DB since the #970 split gave auth,
api and audit their own Postgres/Mongo services, so each service DB
carries its own ledger recording the migrations that target it. A
migration declares its target with a module-level `TARGET_DB` constant
("auth" | "api" | "audit", default "auth"); the runner scopes every
command to one DB with `--db` and connects through the POSTGRESDB_URI
of the context it runs in — run it inside the target service's context
(`railway ssh -s campus.api`) so the ledger lands in that service's
DB. The doc ledger in docs/migration-protocol.md is the human-readable
mirror. The table is created here, NOT by a migration file, to avoid
the chicken-and-egg of a migration that records migrations. It records
both storage families (Postgres DDL and Mongo backfills) targeting the
scoped service.

Commands (run like today's migration scripts, from a context where the
target service's POSTGRESDB_URI resolves, e.g. `railway ssh` into that
service):

    python migrations/runner.py ensure                  # create _migrations (idempotent)
    python migrations/runner.py status                  # applied/pending per migration file
    python migrations/runner.py stamp 005               # record one migration as applied
    python migrations/runner.py stamp all               # record every migration as applied
    python migrations/runner.py stamp 001 --as historical   # record as never-applicable
    python migrations/runner.py apply                   # run pending migrations in order
    python migrations/runner.py apply --up-to 008       # run pending migrations up to 008
    python migrations/runner.py apply --allow-hash-mismatch
        # run anyway after the hash guard flagged an edited, applied file

Append `--db api` / `--db audit` to any command to scope it to that
service's migrations and ledger (default: auth — every pre-#1104
migration targeted the shared auth context, so the default keeps the
historical invocations working verbatim).

Ledger statuses:

- `applied` — upgrade() ran (or the row was stamped for a baseline)
- `failed` — upgrade() raised; the error text is recorded; the next
  `apply` retries it (stop-on-failure blocks everything after it)
- `historical` — recorded as never applicable to this environment
  (e.g. a migration that predates the current topology whose tables do
  not exist here); `apply` never runs it

`apply` runs one migration at a time in numeric revision order. Each
migration manages its own transactionality (per the protocol doc every
migration must be idempotent); the runner guarantees the ledger reflects
exactly what completed — the row is written only after upgrade()
returns, and a failure row is written before the runner stops.

Apply exclusion (#1166): the run takes a session-level Postgres advisory
lock on the ledger connection for its whole duration, so concurrent
applies (a management-route apply racing the break-glass job, or two
operator shells) cannot interleave — a second apply polls briefly, then
refuses without writing anything. Programmatic callers may pass a
`should_cancel` predicate to main(); it is checked between migrations
(one migration = the atomic unit, so abort never interrupts a running
one), cancelled revisions stay pending, and the next apply resumes.
Migrations guarded by `@block_env(PRODUCTION)` follow the documented
per-process override for deliberate production runs:
`ENV=development python migrations/runner.py apply`.

Baseline bootstrap for dev (per the doc ledger, 2026-10-03): 003–009
stamped applied; 001–002 stamped `--as historical` (their tables are
absent from both dev Postgres databases). The per-DB ledgers api/audit
baseline at first scope run (stamp that DB's applied revisions; see
the protocol doc).

Execution audit (#27 phase 3, #746): every run records who ran it, how
long it took and a sha256 of the migration file — `applied_by`,
`duration_ms` (NULL for stamped rows, which run nothing) and
`file_hash`. `apply` runs a hash guard first: an already-applied
revision whose file hash no longer matches the ledger means the file
was edited after it was applied, and the run is refused;
`--allow-hash-mismatch` proceeds with a warning for conscious
recovery. Rows stamped before phase 3 (e.g. the dev baseline) carry a
NULL file_hash and are not guarded. Mongo rewrite migrations take a
document backup before writing — see migrations/_backup.py and the
protocol doc's backup conventions.

Startup visibility (#27 phase 4, #747): production-style boots call
warn_if_pending() from main.create_app — one WARNING line naming every
revision targeting THAT service's DB which the service's own ledger
does not record as applied or historical (the #1104 scoping: api/audit
boots used to find no ledger at all and warn about nothing). The check
is fail-open (an unreachable ledger never blocks boot) and never runs
anything: migrations stay manual, never auto-run from Campus apps.

The `_migrations` DDL deliberately does not go through
PostgreSQLTable.init_from_schema: that entry point is production-blocked,
and standing up production is exactly when this runner is needed. The
ledger table is runner bookkeeping, not user schema.
"""

import argparse
import ast
import hashlib
import logging
import re
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from campus.common import env

logger = logging.getLogger(__name__)

LEDGER_TABLE = "_migrations"

# Per-migration target DBs (#1104): the service whose database a
# migration writes. Every migration declares TARGET_DB; "auth" is the
# default so pre-#1104 files without the constant keep their historical
# meaning (the shared auth context).
KNOWN_TARGET_DBS = ("auth", "api", "audit")
DEFAULT_TARGET_DB = "auth"

# env.DEPLOY value -> runner DB scope, for warn_if_pending.
DEPLOY_TO_TARGET_DB = {
    "campus.auth": "auth",
    "campus.api": "api",
    "campus.audit": "audit",
}

# Full schema defined up front (#744): phase-3 audit columns are nullable
# so later phases fill them without DDL changes.
LEDGER_DDL = f"""
CREATE TABLE IF NOT EXISTS "{LEDGER_TABLE}" (
    "revision" TEXT PRIMARY KEY,
    "filename" TEXT NOT NULL,
    "status" TEXT NOT NULL,
    "applied_at" TIMESTAMPTZ,
    "applied_by" TEXT,
    "duration_ms" NUMERIC,
    "error" TEXT,
    "file_hash" TEXT
);
"""

# Postgres SQLSTATE for "table does not exist" — status treats it as an
# empty ledger so a fresh environment needs no ensure first.
UNDEFINED_TABLE_SQLSTATE = "42P01"

MIGRATION_FILE_RE = re.compile(r"^(\d{3})_[a-z0-9_]+\.py$")

MIGRATIONS_DIR = Path(__file__).resolve().parent

# Ledger statuses. APPLIED/FAILED/HISTORICAL are stored values; PENDING
# and MISSING_FILE are computed states for the status diff (a file with
# no ledger row is pending; a ledger row with no file is drift).
APPLIED = "applied"
FAILED = "failed"
HISTORICAL = "historical"
PENDING = "pending"
MISSING_FILE = "missing-file"

# apply() runs a file only when its ledger status is absent, failed
# (retry) or pending; applied and historical files are skipped.
APPLY_RUNNABLE = (APPLIED, FAILED, HISTORICAL)

# Session-level advisory lock guarding apply (#1166): one fixed key
# agreed by every context, so a management-route apply, the break-glass
# job and a manual shell run cannot interleave on the same service DB.
# ("migr" as a big-endian byte value; arbitrary but stable.)
ADVISORY_LOCK_KEY = 0x6D696772

# How long apply polls for the advisory lock before refusing (#1166).
APPLY_LOCK_WAIT_SECONDS = 30.0

# #747: production-style environments — where startup init_from_model
# is blocked, so only the runner can have brought the schema up to
# date — log a startup WARNING when migrations are outstanding.
# Non-production boots are unchanged: dev self-heals schema via
# init_from_model. Literal, not env.PRODUCTION, to keep this module
# importable without the campus package (campus.common is imported
# lazily in warn_if_pending).
PENDING_WARN_ENVS = ("production",)

# #1167: fail-closed production boot gate — set on production app
# services only; unset on dev/test, where boot behavior is unchanged.
MIGRATIONS_ENFORCED_ENVVAR = "MIGRATIONS_ENFORCED"


@dataclass(frozen=True)
class MigrationFile:
    """A migration file discovered in migrations/."""

    revision: str  # NNN numeric prefix, e.g. "003"
    filename: str  # full filename, e.g. "003_add_api_traces_table.py"
    # The service DB this migration writes (#1104); "auth" for
    # pre-#1104 files without a TARGET_DB constant.
    target_db: str = DEFAULT_TARGET_DB


def _read_target_db(path: Path) -> str:
    """Read a migration's TARGET_DB declaration without importing it.

    Importing a migration module executes its top-level code (storage
    imports), which status/ensure must not require — so the constant is
    parsed out of the AST instead. Files without the constant default
    to "auth" (the historical shared context); an unknown value is a
    malformed repo state and raises, like a duplicate revision.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if (isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "TARGET_DB"
                and isinstance(node.value, ast.Constant)):
            value = node.value.value
            if value not in KNOWN_TARGET_DBS:
                raise ValueError(
                    f"{path.name}: TARGET_DB {value!r} is not one of "
                    f"{', '.join(KNOWN_TARGET_DBS)}"
                )
            return value
    return DEFAULT_TARGET_DB


def discover_migration_files(migrations_dir: Path = MIGRATIONS_DIR) -> list[MigrationFile]:
    """Return migration files in the directory, sorted by revision.

    Only files matching the NNN_slug.py convention are migrations; other
    entries (runner.py, _backup.py, READMEs) are ignored. Duplicate
    revisions are a malformed repo state and raise ValueError.
    """
    files: list[MigrationFile] = []
    seen: dict[str, str] = {}
    for path in sorted(migrations_dir.iterdir()):
        match = MIGRATION_FILE_RE.match(path.name)
        if not match:
            continue
        if match.group(1) in seen:
            raise ValueError(
                f"Duplicate migration revision {match.group(1)!r}: "
                f"{seen[match.group(1)]} and {path.name}"
            )
        seen[match.group(1)] = path.name
        files.append(MigrationFile(
            revision=match.group(1),
            filename=path.name,
            target_db=_read_target_db(path),
        ))
    return files


def filter_files_by_db(files: list[MigrationFile],
                       db: str) -> list[MigrationFile]:
    """The migrations targeting `db` (#1104 scope)."""
    return [f for f in files if f.target_db == db]


def known_revisions(files: list[MigrationFile]) -> set[str]:
    """Every revision present on disk, across all target DBs.

    compute_status uses this to tell "ledger row for a revision that
    targets ANOTHER db" (normal with #1104's per-DB ledgers — the auth
    ledger carries api/audit-era rows) apart from "row whose file is
    gone" (real drift).
    """
    return {f.revision for f in files}


def resolve_revision(arg: str, files: list[MigrationFile]) -> MigrationFile:
    """Resolve a stamp/apply argument to a discovered migration file.

    Accepts the bare revision ("005", "5"), the filename
    ("005_backfill_scope_string.py") or its stem. Raises ValueError for
    anything that does not match exactly one discovered file.
    """
    by_revision = {f.revision: f for f in files}
    by_stem = {Path(f.filename).stem: f for f in files}
    candidate = arg.removesuffix(".py")
    if candidate in by_stem:
        return by_stem[candidate]
    if arg.isdigit():
        candidate = arg.zfill(3)
        if candidate in by_revision:
            return by_revision[candidate]
    known = ", ".join(f.revision for f in files)
    raise ValueError(f"Unknown migration {arg!r} (known revisions: {known})")


def resolve_scoped_revision(arg: str, all_files: list[MigrationFile],
                            db: str) -> MigrationFile:
    """Resolve a stamp/apply argument within one DB's scope (#1104).

    A revision that exists but targets ANOTHER db gets an actionable
    error (name the right --db) instead of "unknown migration" — the
    likely cause is running the runner in the wrong service's context,
    which would write the row into the wrong ledger.
    """
    scoped = filter_files_by_db(all_files, db)
    try:
        return resolve_revision(arg, scoped)
    except ValueError:
        pass
    try:
        file = resolve_revision(arg, all_files)
    except ValueError:
        known = ", ".join(f.revision for f in scoped)
        raise ValueError(
            f"Unknown migration {arg!r} (known {db} revisions: {known})"
        ) from None
    raise ValueError(
        f"revision {file.revision} targets {file.target_db}, not {db} — "
        f"re-run with --db {file.target_db} in that service's context"
    ) from None


def compute_status(
    files: list[MigrationFile],
    ledger_rows: dict[str, dict],
    known_revisions: set[str] | None = None,
) -> list[tuple[MigrationFile, str]]:
    """Diff discovered files against ledger rows.

    Returns (file, state) pairs sorted by revision. A file's state is
    its ledger status (APPLIED, FAILED, HISTORICAL) or PENDING when no
    row exists. Ledger rows whose file is gone are reported after files
    with state MISSING_FILE (never reuse a number; a missing file is
    drift to report). With `known_revisions` set (all revisions on
    disk, across target DBs), a row for a revision that exists but
    targets ANOTHER db is skipped rather than reported — with #1104's
    per-DB ledgers the auth ledger legitimately carries rows for
    api/audit revisions that aren't in the auth scope.
    """
    status: list[tuple[MigrationFile, str]] = []
    for file in files:
        row = ledger_rows.get(file.revision)
        state = row["status"] if row else PENDING
        status.append((file, state))
    skip = known_revisions or {f.revision for f in files}
    for revision, row in sorted(ledger_rows.items()):
        if revision not in skip:
            status.append(
                (MigrationFile(revision=revision, filename=row.get("filename", "?")),
                 MISSING_FILE)
            )
    return status


def _format_summary(status: list[tuple[MigrationFile, str]]) -> str:
    """One-line counts in fixed order, omitting zero states."""
    order = (APPLIED, PENDING, FAILED, HISTORICAL, MISSING_FILE)
    counts = dict.fromkeys(order, 0)
    for _, state in status:
        counts[state] = counts.get(state, 0) + 1
    parts = [f"{counts[state]} {state}" for state in order if counts[state]]
    total = sum(1 for _, state in status if state != MISSING_FILE)
    return f"{', '.join(parts)} of {total} migration file(s)"


def _get_user() -> str | None:
    """Best-effort operator identity for the applied_by column."""
    import getpass
    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001 - identity is optional metadata
        return None


def _file_hash(path: Path) -> str | None:
    """sha256 hexdigest of a migration file; None if it cannot be read."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _connect():
    """Open a connection to the service Postgres of this context.

    Same resolution path as the storage backends: POSTGRESDB_URI from
    the environment, or the registered getsecret (vault) fallback.
    Which DB that IS depends on where the runner runs (#1104): the
    auth context resolves the auth DB, `railway ssh -s campus.api`
    resolves the api DB — run the runner in the target service's
    context so its ledger records the run.
    """
    import psycopg2
    return psycopg2.connect(env.getsecret("POSTGRESDB_URI"))


def _fetch_ledger_rows(conn) -> dict[str, dict]:
    """Return ledger rows keyed by revision; empty if table missing."""
    import psycopg2

    with conn.cursor() as cursor:
        try:
            cursor.execute(
                f'SELECT revision, filename, status, applied_at, file_hash '
                f'FROM "{LEDGER_TABLE}"'
            )
        except psycopg2.Error as e:
            if getattr(e, "pgcode", None) == UNDEFINED_TABLE_SQLSTATE:
                conn.rollback()
                return {}
            raise
        rows = cursor.fetchall()
        return {
            row[0]: {
                "revision": row[0],
                "filename": row[1],
                "status": row[2],
                "applied_at": row[3],
                "file_hash": row[4],
            }
            for row in rows
        }


def ensure(conn) -> None:
    """Create the ledger table if missing. Idempotent."""
    with conn.cursor() as cursor:
        cursor.execute(LEDGER_DDL)
    conn.commit()


def _acquire_apply_lock(conn,
                        wait_seconds: float | None = None) -> bool:
    """Take the session-level advisory lock guarding apply (#1166).

    Polls pg_try_advisory_lock on the ledger connection for up to
    wait_seconds (APPLY_LOCK_WAIT_SECONDS by default), then gives up
    WITHOUT writing anything: a held lock means another apply is
    mid-flight (management route, break-glass job or another shell)
    and the run must not interleave with it. The lock lives for the
    connection's lifetime — released by _release_apply_lock, or
    implicitly when the connection closes.
    """
    if wait_seconds is None:
        wait_seconds = APPLY_LOCK_WAIT_SECONDS
    deadline = time.monotonic() + wait_seconds
    while True:
        with conn.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)",
                           (ADVISORY_LOCK_KEY,))
            row = cursor.fetchone()
        conn.commit()
        held = bool(row and row[0])
        if held:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.5)


def _release_apply_lock(conn) -> None:
    """Release the apply advisory lock; the session close also would."""
    with conn.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_unlock(%s)", (ADVISORY_LOCK_KEY,))
    conn.commit()


def _upsert_row(conn, file: MigrationFile, status: str,
                error: str | None = None,
                duration_ms: int | None = None) -> None:
    """Write one ledger row, replacing any existing row for the revision.

    The upsert is what makes a post-failure retry converge: the success
    write clears the error column and the failed status of the attempt
    it supersedes. Every write records the operator (applied_by) and
    the file's sha256 at write time (#746 execution audit); duration_ms
    is the wall time of an actual run — NULL for stamped rows.
    """
    applied_by = _get_user()
    file_hash = _file_hash(MIGRATIONS_DIR / file.filename)
    with conn.cursor() as cursor:
        cursor.execute(
            f'INSERT INTO "{LEDGER_TABLE}" '
            f'(revision, filename, status, applied_at, applied_by, error, '
            f"duration_ms, file_hash) "
            f"VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
            f"ON CONFLICT (revision) DO UPDATE SET "
            f"filename = EXCLUDED.filename, "
            f"status = EXCLUDED.status, "
            f"applied_at = EXCLUDED.applied_at, "
            f"applied_by = EXCLUDED.applied_by, "
            f"error = EXCLUDED.error, "
            f"duration_ms = EXCLUDED.duration_ms, "
            f"file_hash = EXCLUDED.file_hash",
            (file.revision, file.filename, status,
             datetime.now(timezone.utc), applied_by, error,
             duration_ms, file_hash),
        )
    conn.commit()


def stamp(conn, file: MigrationFile, status: str = APPLIED) -> bool:
    """Record a migration as applied without running it.

    Returns True if a row was written, False if the revision was
    already recorded with the same status (stamping is idempotent). A
    revision recorded with a DIFFERENT status is updated — stamp is the
    operator's tool for correcting the ledger (e.g. marking a stamped
    revision historical, or overriding a failure after manual repair).
    """
    with conn.cursor() as cursor:
        cursor.execute(
            f'SELECT status FROM "{LEDGER_TABLE}" WHERE revision = %s',
            (file.revision,),
        )
        row = cursor.fetchone()
        if row and row[0] == status:
            return False
    _upsert_row(conn, file, status)
    return True


def load_migration(file: MigrationFile, migrations_dir: Path | None = None):
    """Load a migration module from its file.

    Importing the module runs its top-level code (campus.storage
    imports etc.), which is why the runner must be invoked from a
    context where the storage secrets resolve — same as running the
    migration script directly.
    """
    import importlib.util
    path = (migrations_dir or MIGRATIONS_DIR) / file.filename
    spec = importlib.util.spec_from_file_location(
        f"campus_migration_{file.revision}", path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_upgrade(module, file: MigrationFile) -> None:
    """Call the migration's upgrade().

    Data migrations following the dry-run-by-default convention take an
    `apply` flag (005_backfill_scope_string is the pattern); the runner
    always executes in apply mode.
    """
    import inspect
    upgrade = getattr(module, "upgrade", None)
    if not callable(upgrade):
        raise ValueError(f"{file.filename} has no upgrade()")
    if "apply" in inspect.signature(upgrade).parameters:
        upgrade(apply=True)
    else:
        upgrade()


def pending_for_apply(
    files: list[MigrationFile],
    ledger_rows: dict[str, dict],
    up_to: MigrationFile | None = None,
) -> list[MigrationFile]:
    """Files apply() should run: not recorded as applied or historical.

    Failed revisions are included (the next apply retries them).
    Result is in revision order; with up_to set, only revisions at or
    below the bound (zero-padded, so lexicographic order is numeric).
    """
    targets = [
        f for f in files
        if ledger_rows.get(f.revision, {}).get("status") not in (APPLIED, HISTORICAL)
    ]
    if up_to is not None:
        targets = [f for f in targets if f.revision <= up_to.revision]
    return targets


def hash_mismatches(
    files: list[MigrationFile],
    ledger_rows: dict[str, dict],
) -> list[tuple[MigrationFile, str, str]]:
    """Applied files whose current sha256 differs from the ledger row.

    The hash guard's scan (#746): a mismatch means a migration file was
    edited after it was applied — the protocol's immutability rule,
    enforced. Rows without a stored hash (stamped before phase 3) and
    revisions whose file is gone are not guarded. Returns (file,
    stored_hash, current_hash) tuples.
    """
    mismatches = []
    for file in files:
        row = ledger_rows.get(file.revision)
        if not row or row.get("status") != APPLIED:
            continue
        stored = row.get("file_hash")
        if not stored:
            continue
        current = _file_hash(MIGRATIONS_DIR / file.filename)
        if current is not None and current != stored:
            mismatches.append((file, stored, current))
    return mismatches


def warn_if_pending(env_name: str | None = None,
                    migrations_dir: Path | None = None,
                    db: str | None = None) -> list[str]:
    """Log a WARNING when migrations are outstanding; never raise (#747).

    Called at app startup (main.create_app) in production-style
    environments — the ones where startup init_from_model is blocked, so
    only the runner can have brought the schema up to date. Any revision
    targeting this service's DB (#1104 scope: derived from env.DEPLOY,
    or pass `db` explicitly) that the service's own ledger does not
    record as applied or historical (pending, failed, or a ledger row
    whose file is gone) is named in one WARNING line. Unlike the CLI
    commands this uses logging, not print: it runs inside the app,
    where stdout is no one's console.

    Fail-open by design: an unresolvable POSTGRESDB_URI, a missing
    ledger table, a malformed migrations/ directory — any error is
    logged at debug and swallowed. A pending migration never blocks
    boot, and nothing here ever runs one. Outside PENDING_WARN_ENVS the
    check returns before touching the database, so dev/test boots are
    unchanged.

    Returns the outstanding revisions (empty when clean, skipped, or on
    error).
    """
    if env_name is None:
        from campus.common import env
        env_name = env.ENV
    if env_name not in PENDING_WARN_ENVS:
        return []
    if db is None:
        from campus.common import env
        # DEPLOY is set on every deployed service; absent contexts
        # (tests, ad-hoc scripts) fall back to the historical auth
        # scope.
        db = DEPLOY_TO_TARGET_DB.get(env.get("DEPLOY", "") or "",
                                     DEFAULT_TARGET_DB)
    try:
        all_files = discover_migration_files(migrations_dir or MIGRATIONS_DIR)
        files = filter_files_by_db(all_files, db)
        conn = _connect()
        try:
            rows = _fetch_ledger_rows(conn)
        finally:
            conn.close()
        outstanding = [
            (file, state) for file, state in
            compute_status(files, rows,
                           known_revisions={f.revision for f in all_files})
            if state not in (APPLIED, HISTORICAL)
        ]
        if outstanding:
            logger.warning(
                "%s migration(s) targeting %s not recorded applied at "
                "startup: %s — run `python migrations/runner.py --db %s "
                "status` / `apply` in this service's context out-of-band; "
                "startup proceeding (apps never auto-run migrations)",
                len(outstanding), db,
                ", ".join(f"{file.filename} [{state}]"
                          for file, state in outstanding),
                db,
            )
        return [file.revision for file, _ in outstanding]
    except Exception as e:  # noqa: BLE001 - fail-open: boot must not depend on the ledger
        logger.debug(
            "migration pending-check skipped: %s: %s", type(e).__name__, e
        )
        return []


def boot_gate() -> list[str]:
    """Startup pending-check; refuses to boot when enforced (#1167).

    main.create_app calls this instead of warn_if_pending() directly.
    The #747 warning behavior is unchanged: production-style boots log
    one WARNING naming outstanding revisions targeting this service's
    DB; dev/test boots return before touching the database. When
    MIGRATIONS_ENFORCED is set (production app services) AND the
    outstanding list is non-empty, raise RuntimeError naming them: the
    boot fails, the healthcheck never passes, and Railway keeps the
    previous deployment live — an out-of-order release merge
    self-heals once the pending migrations are applied and the service
    is redeployed. The gate never runs anything (apps never auto-run
    migrations), and ledger failures stay fail-open via
    warn_if_pending: an unreachable ledger can warn, never block boot
    on its own. With the var unset (dev/test) the raise is unreachable.

    Returns the outstanding revisions ([] outside production-style
    envs, when clean, or when the ledger is unreachable).
    """
    outstanding = warn_if_pending()
    if not outstanding:
        return outstanding
    from campus.common import env
    if not env.get(MIGRATIONS_ENFORCED_ENVVAR, ""):
        return outstanding
    raise RuntimeError(
        f"{len(outstanding)} pending migration(s) targeting this "
        f"service DB ({', '.join(outstanding)}) and "
        f"{MIGRATIONS_ENFORCED_ENVVAR} is set — refusing to boot over "
        "out-of-date schema (#1167): apply the pending migrations "
        "(campus-admin Migrations view, or the break-glass job) and "
        "redeploy; unsetting the var is a superadmin break-glass "
        "action, not a fix"
    )


def cmd_ensure(args, conn) -> int:
    ensure(conn)
    print(f"ledger table {LEDGER_TABLE!r} ready "
          f"(scope: {args.db} migrations in this service's DB)")
    return 0


def cmd_stamp(args, conn) -> int:
    all_files = discover_migration_files()
    files = filter_files_by_db(all_files, args.db)
    ensure(conn)
    status = args.as_status
    if args.revision == "all":
        rows = _fetch_ledger_rows(conn)
        pending = [
            f for f in files
            if rows.get(f.revision, {}).get("status") != status
        ]
        if not pending:
            print(f"nothing to stamp: all {args.db} migrations "
                  f"already recorded as {status}")
            return 0
        for file in pending:
            stamp(conn, file, status)
            print(f"stamped {file.revision} as {status} ({file.filename})")
        print(f"stamped {len(pending)} migration(s) as {status}")
        return 0

    file = resolve_scoped_revision(args.revision, all_files, args.db)
    if stamp(conn, file, status):
        print(f"stamped {file.revision} as {status} ({file.filename})")
    else:
        print(f"{file.revision} already recorded as {status}; nothing to do")
    return 0


def cmd_status(args, conn) -> int:
    all_files = discover_migration_files()
    files = filter_files_by_db(all_files, args.db)
    rows = _fetch_ledger_rows(conn)
    status = compute_status(files, rows,
                            known_revisions={f.revision for f in all_files})
    print(f"scope: {args.db} (migrations targeting {args.db}, ledger in "
          "this service's DB)")
    for file, state in status:
        print(f"{file.revision}  {file.filename:<48} {state}")
    print(_format_summary(status))
    return 0


def cmd_apply(args, conn,
              should_cancel: Callable[[], bool] | None = None) -> int:
    all_files = discover_migration_files()
    files = filter_files_by_db(all_files, args.db)
    ensure(conn)
    if not _acquire_apply_lock(conn):
        print(
            "error: another migration apply holds the advisory lock "
            f"(waited {APPLY_LOCK_WAIT_SECONDS:.0f}s) — a run is already "
            "in flight (management route, break-glass job or another "
            "shell); nothing was written — retry once it finishes",
            file=sys.stderr,
        )
        return 1
    try:
        return _apply_locked(args, conn, all_files, files, should_cancel)
    finally:
        _release_apply_lock(conn)


def _apply_locked(args, conn, all_files, files,
                  should_cancel: Callable[[], bool] | None = None) -> int:
    """The apply loop proper; the caller holds the advisory lock (#1166)."""
    rows = _fetch_ledger_rows(conn)

    mismatches = hash_mismatches(files, rows)
    if mismatches:
        for file, stored, current in mismatches:
            print(
                f"hash guard: {file.revision} ({file.filename}) changed "
                f"since it was applied — ledger {stored[:12]}…, file "
                f"{current[:12]}…",
                file=sys.stderr,
            )
        if not args.allow_hash_mismatch:
            print(
                "error: refusing to apply — a migration file was edited "
                "after it was applied (fix forward with a new migration, "
                "or pass --allow-hash-mismatch to proceed anyway)",
                file=sys.stderr,
            )
            return 1
        print(
            f"WARNING: continuing despite {len(mismatches)} edited "
            f"migration file(s) (--allow-hash-mismatch)",
            file=sys.stderr,
        )

    up_to = (resolve_scoped_revision(args.up_to, all_files, args.db)
             if args.up_to else None)
    targets = pending_for_apply(files, rows, up_to)
    if not targets:
        print("up to date: nothing to apply")
        return 0

    for index, file in enumerate(targets):
        if should_cancel is not None and should_cancel():
            print(
                f"cancelled: {index} of {len(targets)} applied, "
                f"{len(targets) - index} left pending — ledger unchanged; "
                "re-run apply to resume",
                file=sys.stderr,
                flush=True,
            )
            return 1
        print(f"applying {file.revision} ({file.filename})...", flush=True)
        started = time.perf_counter()
        try:
            module = load_migration(file)
            run_upgrade(module, file)
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
            duration_ms = round((time.perf_counter() - started) * 1000)
            _upsert_row(conn, file, FAILED, error=error,
                        duration_ms=duration_ms)
            print(
                f"FAILED {file.revision}: {error}\n"
                f"recorded failure and stopped — "
                f"{len(targets) - index - 1} later migration(s) not run",
                file=sys.stderr,
                flush=True,
            )
            return 1
        else:
            duration_ms = round((time.perf_counter() - started) * 1000)
            _upsert_row(conn, file, APPLIED, duration_ms=duration_ms)
            print(f"applied {file.revision} ({duration_ms} ms)",
                  flush=True)
    print(f"applied {len(targets)} migration(s)")
    return 0


def main(argv: list[str] | None = None,
         should_cancel: Callable[[], bool] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="migrations/runner.py",
        description="Applied-migrations ledger and migration runner (#27).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_db_argument(sub: argparse.ArgumentParser) -> None:
        # #1104: scope the command to one service's migrations; the
        # ledger read/written is the one in the context's POSTGRESDB_URI,
        # so run the runner in the target service's context
        # (`railway ssh -s campus.<db>`).
        sub.add_argument(
            "--db",
            choices=KNOWN_TARGET_DBS,
            default=DEFAULT_TARGET_DB,
            help="migrations whose TARGET_DB is this service (default: "
                 "auth, the historical shared context); run in that "
                 "service's context so its ledger is used",
        )

    ensure_parser = subparsers.add_parser(
        "ensure",
        help="create the _migrations ledger table (idempotent)",
    )
    add_db_argument(ensure_parser)
    stamp_parser = subparsers.add_parser(
        "stamp",
        help="record a migration as applied without running it",
    )
    add_db_argument(stamp_parser)
    stamp_parser.add_argument(
        "revision",
        metavar="rev|all",
        help="migration revision (e.g. 005), filename, or 'all'",
    )
    stamp_parser.add_argument(
        "--as",
        dest="as_status",
        choices=(APPLIED, HISTORICAL),
        default=APPLIED,
        help="status to record (default: applied; historical = "
             "never applicable to this environment, apply skips it)",
    )
    apply_parser = subparsers.add_parser(
        "apply",
        help="run pending migrations in revision order",
    )
    add_db_argument(apply_parser)
    apply_parser.add_argument(
        "--up-to",
        dest="up_to",
        metavar="REV",
        help="apply only revisions at or below this one (e.g. 008)",
    )
    apply_parser.add_argument(
        "--allow-hash-mismatch",
        dest="allow_hash_mismatch",
        action="store_true",
        help="apply even when an applied migration file's hash no longer "
             "matches the ledger (edited file); warn instead of refusing",
    )
    status_parser = subparsers.add_parser(
        "status",
        help="diff migrations/ files against the ledger",
    )
    add_db_argument(status_parser)

    args = parser.parse_args(argv)
    handlers = {
        "ensure": cmd_ensure,
        "stamp": cmd_stamp,
        "status": cmd_status,
    }
    conn = _connect()
    try:
        if args.command == "apply":
            # apply alone takes the cancel hook (#1166); the other
            # commands are single-statement ledger operations with
            # nothing to abort.
            return cmd_apply(args, conn, should_cancel)
        return handlers[args.command](args, conn)
    except ValueError as e:
        # Usage errors: unknown revision, malformed migrations/ directory
        print(f"error: {e}", file=sys.stderr)
        return 1
    except OSError as e:
        # POSTGRESDB_URI unresolvable in this context
        print(f"error: {e}", file=sys.stderr)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
