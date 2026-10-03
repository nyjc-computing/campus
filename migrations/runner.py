"""Migration ledger runner: manage the applied-migrations state table.

Revision ID: n/a (the runner is not itself a migration)
Create Date: 2026-10-03

Phase 1 of the storage migration protocol (#27, #744): the `_migrations`
table in the auth Postgres (campus.auth-postgres) is the authoritative
record of which migrations have been applied to an environment. The doc
ledger in docs/migration-protocol.md is a human-readable mirror.

The table is created here, NOT by a migration file, to avoid the
chicken-and-egg of a migration that records migrations. It records both
storage families (Postgres DDL and Mongo backfills): every migration
runs in the campus.auth context where both secrets resolve.

Commands (run like today's migration scripts, from a context where
POSTGRESDB_URI resolves, e.g. `railway ssh` into campus.auth):

    python migrations/runner.py ensure             # create _migrations (idempotent)
    python migrations/runner.py status             # applied/pending per migration file
    python migrations/runner.py stamp 005          # record one migration as applied
    python migrations/runner.py stamp all          # record every migration as applied

`stamp` records a migration as applied WITHOUT running it — the baseline
bootstrap for environments that predate the ledger. Only `ensure` and
`stamp` write; `status` is read-only and treats a missing table as
"nothing applied".

Baseline bootstrap for dev (per the doc ledger, 2026-10-03):

    python migrations/runner.py ensure
    python migrations/runner.py stamp all
    python migrations/runner.py status             # verify: all applied

The `_migrations` DDL deliberately does not go through
PostgreSQLTable.init_from_schema: that entry point is production-blocked,
and standing up production is exactly when this runner is needed. The
ledger table is runner bookkeeping, not user schema.
"""

import argparse
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

# status states: file with/without a ledger row, and ledger rows whose
# file is gone (never reuse a number; a missing file is drift to report).
APPLIED = "applied"
PENDING = "pending"
MISSING_FILE = "missing-file"


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
    """Resolve a stamp argument to a discovered migration file.

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

    Returns (file, state) pairs sorted by revision where state is
    APPLIED (file has a ledger row), PENDING (file has no row) or
    MISSING_FILE (ledger row with no file — reported after files, with
    the recorded filename).
    """
    status: list[tuple[MigrationFile, str]] = []
    for file in files:
        state = APPLIED if file.revision in ledger_rows else PENDING
        status.append((file, state))
    for revision, row in sorted(ledger_rows.items()):
        if revision not in {f.revision for f in files}:
            status.append(
                (MigrationFile(revision=revision, filename=row.get("filename", "?")),
                 MISSING_FILE)
            )
    return status


def _get_user() -> str | None:
    """Best-effort operator identity for the applied_by column."""
    import getpass
    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001 - identity is optional metadata
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
                f'SELECT revision, filename, status, applied_at FROM "{LEDGER_TABLE}"'
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
            }
            for row in rows
        }


def ensure(conn) -> None:
    """Create the ledger table if missing. Idempotent."""
    with conn.cursor() as cursor:
        cursor.execute(LEDGER_DDL)
    conn.commit()


def stamp(conn, file: MigrationFile) -> bool:
    """Record one migration as applied without running it.

    Returns True if a row was written, False if the revision was
    already recorded (stamping is idempotent).
    """
    applied_by = _get_user()
    with conn.cursor() as cursor:
        cursor.execute(
            f'SELECT 1 FROM "{LEDGER_TABLE}" WHERE revision = %s',
            (file.revision,),
        )
        if cursor.fetchone():
            return False
        cursor.execute(
            f'INSERT INTO "{LEDGER_TABLE}" '
            f'(revision, filename, status, applied_at, applied_by) '
            f"VALUES (%s, %s, %s, %s, %s)",
            (file.revision, file.filename, APPLIED,
             datetime.now(timezone.utc), applied_by),
        )
    conn.commit()
    return True


def cmd_ensure(args, conn) -> int:
    ensure(conn)
    print(f"ledger table {LEDGER_TABLE!r} ready")
    return 0


def cmd_stamp(args, conn) -> int:
    files = discover_migration_files()
    ensure(conn)
    if args.revision == "all":
        pending = [f for f in files if f.revision not in _fetch_ledger_rows(conn)]
        if not pending:
            print("nothing to stamp: all migrations already recorded")
            return 0
        for file in pending:
            stamp(conn, file)
            print(f"stamped {file.revision} ({file.filename})")
        print(f"stamped {len(pending)} migration(s)")
        return 0

    file = resolve_revision(args.revision, files)
    if stamp(conn, file):
        print(f"stamped {file.revision} ({file.filename})")
    else:
        print(f"{file.revision} already recorded; nothing to do")
    return 0


def cmd_status(args, conn) -> int:
    files = discover_migration_files()
    rows = _fetch_ledger_rows(conn)
    status = compute_status(files, rows)
    for file, state in status:
        print(f"{file.revision}  {file.filename:<48} {state}")
    applied = sum(1 for _, state in status if state == APPLIED)
    pending = sum(1 for _, state in status if state == PENDING)
    print(f"{applied} applied, {pending} pending of {len(files)} migration file(s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="migrations/runner.py",
        description="Manage the applied-migrations ledger (#27 phase 1).",
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
    subparsers.add_parser(
        "status",
        help="diff migrations/ files against the ledger",
    )

    args = parser.parse_args(argv)
    handlers = {
        "ensure": cmd_ensure,
        "stamp": cmd_stamp,
        "status": cmd_status,
    }
    conn = _connect()
    try:
        return handlers[args.command](args, conn)
    except ValueError as e:
        # Usage errors: unknown revision, malformed migrations/ directory
        print(f"error: {e}", file=sys.stderr)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
