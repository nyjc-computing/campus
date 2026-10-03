"""Test the migration ledger runner (#27 phase 1, #744).

Covers the pure logic (file discovery, revision resolution, ledger
diffing) and the stamp/ensure DB paths via a fake connection — no live
database.

Note: this file lives under storage/ rather than a migrations/ test
package because a tests/unit/migrations package would shadow the
repo-root migrations/ directory under unittest discovery.
"""

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch


def _pg_error(pgcode: str) -> Exception:
    """Build a psycopg2.Error carrying a SQLSTATE code.

    pgcode is a read-only C getset on psycopg2.Error, so it is supplied
    as a class attribute on a per-call subclass.
    """
    import psycopg2
    error_cls = type("FakePgError", (psycopg2.Error,), {"pgcode": pgcode})
    return error_cls(f"pg error {pgcode}")


class FakeCursor:
    """Records executed statements; programmable fetches and errors."""

    def __init__(self, fetchone_results=None, fetchall_rows=None,
                 execute_error=None):
        self.executed = []  # (sql, params) pairs in call order
        self._fetchone_results = list(fetchone_results or [])
        self._fetchall_rows = list(fetchall_rows or [])
        self._execute_error = execute_error

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        if self._execute_error is not None:
            raise self._execute_error

    def fetchone(self):
        if self._fetchone_results:
            return self._fetchone_results.pop(0)
        return None

    def fetchall(self):
        return list(self._fetchall_rows)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class FakeConn:
    """Minimal connection: one shared cursor, commit/rollback counters."""

    def __init__(self, cursor=None):
        self.cursor_obj = cursor or FakeCursor()
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        pass


def _make_files(*specs):
    """Build MigrationFile instances from (revision, filename) tuples."""
    from migrations.runner import MigrationFile
    return [MigrationFile(revision=rev, filename=name) for rev, name in specs]


class TestDiscoverMigrationFiles(unittest.TestCase):
    """File discovery: convention filter, ordering, duplicate guard."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.dir = Path(self.tmpdir.name)

    def _write(self, *names):
        for name in names:
            (self.dir / name).write_text("", encoding="utf-8")

    def _discover(self):
        from migrations.runner import discover_migration_files
        return discover_migration_files(self.dir)

    def test_discovers_and_sorts_by_revision(self):
        self._write("003_add_api_traces_table.py", "001_add_assignments_table.py",
                    "002_add_submissions_table.py")
        files = self._discover()
        self.assertEqual([f.revision for f in files], ["001", "002", "003"])
        self.assertEqual(files[2].filename, "003_add_api_traces_table.py")

    def test_ignores_non_migration_entries(self):
        self._write("runner.py", "_init.py", "README.md",
                    "0012_too_many_digits.py", "01_two_digits.py",
                    "001_Bad-Uppercase.py")
        self.assertEqual(self._discover(), [])

    def test_duplicate_revision_raises(self):
        self._write("001_add_assignments_table.py", "001_add_other_table.py")
        with self.assertRaises(ValueError):
            self._discover()

    def test_empty_directory(self):
        self.assertEqual(self._discover(), [])


class TestResolveRevision(unittest.TestCase):
    """stamp arguments resolve to exactly one discovered file."""

    FILES = _make_files(
        ("005", "005_backfill_scope_string.py"),
        ("009", "009_create_app_credentials.py"),
    )

    def test_bare_revision(self):
        from migrations.runner import resolve_revision
        self.assertEqual(resolve_revision("005", self.FILES).filename,
                         "005_backfill_scope_string.py")

    def test_unpadded_revision(self):
        from migrations.runner import resolve_revision
        self.assertEqual(resolve_revision("5", self.FILES).revision, "005")

    def test_filename_with_suffix(self):
        from migrations.runner import resolve_revision
        self.assertEqual(
            resolve_revision("009_create_app_credentials.py", self.FILES).revision,
            "009",
        )

    def test_filename_stem(self):
        from migrations.runner import resolve_revision
        self.assertEqual(
            resolve_revision("005_backfill_scope_string", self.FILES).revision,
            "005",
        )

    def test_unknown_revision_raises(self):
        from migrations.runner import resolve_revision
        with self.assertRaises(ValueError):
            resolve_revision("999", self.FILES)

    def test_all_is_not_a_revision(self):
        from migrations.runner import resolve_revision
        with self.assertRaises(ValueError):
            resolve_revision("all", self.FILES)


class TestComputeStatus(unittest.TestCase):
    """Diff of discovered files vs ledger rows."""

    FILES = _make_files(
        ("003", "003_add_api_traces_table.py"),
        ("004", "004_add_vault_clients_public_columns.py"),
        ("005", "005_backfill_scope_string.py"),
    )

    def test_applied_and_pending(self):
        from migrations.runner import APPLIED, PENDING, compute_status
        rows = {"003": {"filename": "003_add_api_traces_table.py"},
                "004": {"filename": "004_add_vault_clients_public_columns.py"}}
        status = compute_status(self.FILES, rows)
        self.assertEqual(status, [
            (self.FILES[0], APPLIED),
            (self.FILES[1], APPLIED),
            (self.FILES[2], PENDING),
        ])

    def test_ledger_row_without_file_is_missing(self):
        from migrations.runner import MISSING_FILE, compute_status
        rows = {"002": {"filename": "002_add_submissions_table.py"}}
        status = compute_status([], rows)
        self.assertEqual(len(status), 1)
        file, state = status[0]
        self.assertEqual(state, MISSING_FILE)
        self.assertEqual(file.revision, "002")
        self.assertEqual(file.filename, "002_add_submissions_table.py")

    def test_empty_ledger_means_all_pending(self):
        from migrations.runner import PENDING, compute_status
        status = compute_status(self.FILES, {})
        self.assertEqual([state for _, state in status], [PENDING] * 3)


class TestEnsure(unittest.TestCase):
    """ensure creates the ledger table idempotently."""

    def test_executes_create_if_not_exists_with_full_schema(self):
        from migrations.runner import LEDGER_TABLE, ensure
        conn = FakeConn()
        ensure(conn)
        self.assertEqual(conn.commits, 1)
        (sql, _), = conn.cursor_obj.executed
        self.assertIn("CREATE TABLE IF NOT EXISTS", sql)
        self.assertIn(f'"{LEDGER_TABLE}"', sql)
        for column in ("revision", "filename", "status", "applied_at",
                       "applied_by", "duration_ms", "error", "file_hash"):
            self.assertIn(f'"{column}"', sql)


class TestStamp(unittest.TestCase):
    """stamp records a migration as applied without running it."""

    FILE = _make_files(("005", "005_backfill_scope_string.py"))[0]

    def test_inserts_applied_row(self):
        import getpass

        from migrations.runner import stamp
        conn = FakeConn(FakeCursor(fetchone_results=[None]))
        self.assertTrue(stamp(conn, self.FILE))
        self.assertEqual(conn.commits, 1)
        inserts = [(sql, params) for sql, params in conn.cursor_obj.executed
                   if "INSERT INTO" in sql]
        self.assertEqual(len(inserts), 1)
        (_, params), = inserts
        self.assertEqual(params[0], "005")
        self.assertEqual(params[1], "005_backfill_scope_string.py")
        self.assertEqual(params[2], "applied")
        self.assertIsInstance(params[3], datetime)
        self.assertIsNotNone(params[3].tzinfo)
        self.assertEqual(params[4], getpass.getuser())

    def test_skips_already_recorded_revision(self):
        from migrations.runner import stamp
        conn = FakeConn(FakeCursor(fetchone_results=[(1,)]))
        self.assertFalse(stamp(conn, self.FILE))
        self.assertEqual(conn.commits, 0)
        self.assertFalse(
            any("INSERT INTO" in sql for sql, _ in conn.cursor_obj.executed))


class TestFetchLedgerRows(unittest.TestCase):
    """Reading the ledger, tolerating a missing table."""

    def test_rows_keyed_by_revision(self):
        from migrations.runner import _fetch_ledger_rows
        rows = [
            ("003", "003_add_api_traces_table.py", "applied", datetime(2026, 10, 1)),
            ("005", "005_backfill_scope_string.py", "applied", datetime(2026, 9, 30)),
        ]
        conn = FakeConn(FakeCursor(fetchall_rows=rows))
        ledger = _fetch_ledger_rows(conn)
        self.assertEqual(sorted(ledger), ["003", "005"])
        self.assertEqual(ledger["005"]["filename"], "005_backfill_scope_string.py")
        self.assertEqual(ledger["005"]["status"], "applied")

    def test_missing_table_returns_empty(self):
        from migrations.runner import _fetch_ledger_rows
        conn = FakeConn(FakeCursor(execute_error=_pg_error("42P01")))
        self.assertEqual(_fetch_ledger_rows(conn), {})
        self.assertEqual(conn.rollbacks, 1)

    def test_other_pg_errors_propagate(self):
        import psycopg2

        from migrations.runner import _fetch_ledger_rows
        conn = FakeConn(FakeCursor(execute_error=_pg_error("08001")))
        with self.assertRaises(psycopg2.Error):
            _fetch_ledger_rows(conn)


class TestMain(unittest.TestCase):
    """CLI-level smoke tests with a faked connection."""

    FILES = _make_files(
        ("003", "003_add_api_traces_table.py"),
        ("005", "005_backfill_scope_string.py"),
    )

    def _run(self, argv, conn):
        import contextlib
        import io

        from migrations.runner import main
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch("migrations.runner._connect", return_value=conn), \
                patch("migrations.runner.discover_migration_files",
                      return_value=self.FILES), \
                contextlib.redirect_stdout(stdout), \
                contextlib.redirect_stderr(stderr):
            exit_code = main(argv)
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def test_status_reports_applied_and_pending(self):
        cursor = FakeCursor(fetchall_rows=[
            ("003", "003_add_api_traces_table.py", "applied", datetime(2026, 10, 1)),
        ])
        exit_code, stdout, _ = self._run(["status"], FakeConn(cursor))
        self.assertEqual(exit_code, 0)
        self.assertIn("003_add_api_traces_table.py", stdout)
        self.assertIn("applied", stdout)
        self.assertIn("005_backfill_scope_string.py", stdout)
        self.assertIn("pending", stdout)
        self.assertIn("1 applied, 1 pending of 2 migration file(s)", stdout)

    def test_status_on_fresh_database_all_pending(self):
        cursor = FakeCursor(execute_error=_pg_error("42P01"))
        exit_code, stdout, _ = self._run(["status"], FakeConn(cursor))
        self.assertEqual(exit_code, 0)
        self.assertIn("0 applied, 2 pending", stdout)

    def test_ensure_creates_table(self):
        conn = FakeConn()
        exit_code, stdout, _ = self._run(["ensure"], conn)
        self.assertEqual(exit_code, 0)
        self.assertIn("CREATE TABLE IF NOT EXISTS",
                      conn.cursor_obj.executed[0][0])
        self.assertIn("ready", stdout)

    def test_stamp_all_stamps_only_unrecorded(self):
        # ledger already has 003; only 005 should be inserted
        cursor = FakeCursor(fetchall_rows=[
            ("003", "003_add_api_traces_table.py", "applied", datetime(2026, 10, 1)),
        ])
        conn = FakeConn(cursor)
        exit_code, stdout, _ = self._run(["stamp", "all"], conn)
        self.assertEqual(exit_code, 0)
        inserts = [(sql, params) for sql, params in cursor.executed
                   if "INSERT INTO" in sql]
        self.assertEqual(len(inserts), 1)
        (_, params), = inserts
        self.assertEqual(params[0], "005")
        self.assertIn("stamped 1 migration(s)", stdout)

    def test_stamp_all_when_fully_applied(self):
        cursor = FakeCursor(fetchall_rows=[
            ("003", "003_add_api_traces_table.py", "applied", datetime(2026, 10, 1)),
            ("005", "005_backfill_scope_string.py", "applied", datetime(2026, 9, 30)),
        ])
        exit_code, stdout, _ = self._run(["stamp", "all"], FakeConn(cursor))
        self.assertEqual(exit_code, 0)
        self.assertIn("nothing to stamp", stdout)

    def test_stamp_unknown_revision_fails_cleanly(self):
        conn = FakeConn()
        exit_code, _, stderr = self._run(["stamp", "999"], conn)
        self.assertEqual(exit_code, 1)
        self.assertIn("error: Unknown migration '999'", stderr)

    def test_stamp_single_revision(self):
        cursor = FakeCursor(fetchone_results=[None])
        conn = FakeConn(cursor)
        exit_code, stdout, _ = self._run(
            ["stamp", "005_backfill_scope_string"], conn)
        self.assertEqual(exit_code, 0)
        inserts = [(sql, params) for sql, params in cursor.executed
                   if "INSERT INTO" in sql]
        self.assertEqual(len(inserts), 1)
        self.assertEqual(inserts[0][1][0], "005")
        self.assertIn("stamped 005", stdout)


if __name__ == "__main__":
    unittest.main()
