"""Migration runner: applied-migrations ledger + migration execution.

Revision ID: n/a (the runner is not itself a migration)
Create Date: 2026-10-03

The `_migrations` table in the auth Postgres (campus.auth-postgres) is
the authoritative record of which migrations have been applied to an
environment (#27 phase 1, #744). The doc ledger in
docs/migration-protocol.md is a human-readable mirror. The table is
created here, NOT by a migration file, to avoid the chicken-and-egg of
a migration that records migrations. It records both storage families
(Postgres DDL and Mongo backfills): every migration runs in the
campus.auth context where both secrets resolve.

Commands (run like today's migration scripts, from a context where
POSTGRESDB_URI resolves, e.g. `railway ssh` into campus.auth):

    python migrations/runner.py ensure             # create _migrations (idempotent)
    python migrations/runner.py status             # applied/pending per migration file
    python migrations/runner.py stamp 005          # record one migration as applied
    python migrations/runner.py stamp all          # record every migration as applied
    python migrations/runner.py stamp 001 --as historical   # record as never-applicable
    python migrations/runner.py apply              # run pending migrations in order
    python migrations/runner.py apply --up-to 008  # run pending migrations up to 008
    python migrations/runner.py apply --allow-hash-mismatch
        # run anyway after the hash guard flagged an edited, applied file

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
Migrations guarded by `@block_env(PRODUCTION)` follow the documented
per-process override for deliberate production runs:
`ENV=development python migrations/runner.py apply`.

Baseline bootstrap for dev (per the doc ledger, 2026-10-03): 003–009
stamped applied; 001–002 stamped `--as historical` (their tables are
absent from both dev Postgres databases).

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

The `_migrations` DDL deliberately does not go through
PostgreSQLTable.init_from_schema: that entry point is production-blocked,
and standing up production is exactly when this runner is needed. The
ledger table is runner bookkeeping, not user schema.
"""

import argparse
import hashlib
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from campus.common import env

LEDGER_TABLE = "_migrations"

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


@dataclass(frozen=True)
class MigrationFile:
    """A migration file discovered in migrations/."""

    revision: str  # NNN numeric prefix, e.g. "003"
    filename: str  # full filename, e.g. "003_add_api_traces_table.py"


def discover_migration_files(migrations_dir: Path = MIGRATIONS_DIR) -> list[MigrationFile]:
    """Return migration files in the directory, sorted by revision.

    Only files matching the NNN_slug.py convention are migrations; other
    entries (runner.py, _init.py, READMEs) are ignored. Duplicate
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
        files.append(MigrationFile(revision=match.group(1), filename=path.name))
    return files


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


def compute_status(
    files: list[MigrationFile],
    ledger_rows: dict[str, dict],
) -> list[tuple[MigrationFile, str]]:
    """Diff discovered files against ledger rows.

    Returns (file, state) pairs sorted by revision. A file's state is
    its ledger status (APPLIED, FAILED, HISTORICAL) or PENDING when no
    row exists. Ledger rows whose file is gone are reported after files
    with state MISSING_FILE (never reuse a number; a missing file is
    drift to report).
    """
    status: list[tuple[MigrationFile, str]] = []
    for file in files:
        row = ledger_rows.get(file.revision)
        state = row["status"] if row else PENDING
        status.append((file, state))
    for revision, row in sorted(ledger_rows.items()):
        if revision not in {f.revision for f in files}:
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
    """Open a connection to the auth Postgres.

    Same resolution path as the storage backends: POSTGRESDB_URI from
    the environment, or the registered getsecret (vault) fallback.
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


def cmd_ensure(args, conn) -> int:
    ensure(conn)
    print(f"ledger table {LEDGER_TABLE!r} ready")
    return 0


def cmd_stamp(args, conn) -> int:
    files = discover_migration_files()
    ensure(conn)
    status = args.as_status
    if args.revision == "all":
        rows = _fetch_ledger_rows(conn)
        pending = [
            f for f in files
            if rows.get(f.revision, {}).get("status") != status
        ]
        if not pending:
            print(f"nothing to stamp: all migrations already recorded as {status}")
            return 0
        for file in pending:
            stamp(conn, file, status)
            print(f"stamped {file.revision} as {status} ({file.filename})")
        print(f"stamped {len(pending)} migration(s) as {status}")
        return 0

    file = resolve_revision(args.revision, files)
    if stamp(conn, file, status):
        print(f"stamped {file.revision} as {status} ({file.filename})")
    else:
        print(f"{file.revision} already recorded as {status}; nothing to do")
    return 0


def cmd_status(args, conn) -> int:
    files = discover_migration_files()
    rows = _fetch_ledger_rows(conn)
    status = compute_status(files, rows)
    for file, state in status:
        print(f"{file.revision}  {file.filename:<48} {state}")
    print(_format_summary(status))
    return 0


def cmd_apply(args, conn) -> int:
    files = discover_migration_files()
    ensure(conn)
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

    up_to = resolve_revision(args.up_to, files) if args.up_to else None
    targets = pending_for_apply(files, rows, up_to)
    if not targets:
        print("up to date: nothing to apply")
        return 0

    import time
    for index, file in enumerate(targets):
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="migrations/runner.py",
        description="Applied-migrations ledger and migration runner (#27).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "ensure",
        help="create the _migrations ledger table (idempotent)",
    )
    stamp_parser = subparsers.add_parser(
        "stamp",
        help="record a migration as applied without running it",
    )
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
    subparsers.add_parser(
        "status",
        help="diff migrations/ files against the ledger",
    )

    args = parser.parse_args(argv)
    handlers = {
        "ensure": cmd_ensure,
        "stamp": cmd_stamp,
        "status": cmd_status,
        "apply": cmd_apply,
    }
    conn = _connect()
    try:
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
