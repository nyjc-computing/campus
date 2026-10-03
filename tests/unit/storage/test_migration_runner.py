"""Test the migration runner (#27 phases 1+2, #744 #745).

Covers the pure logic (file discovery, revision resolution, ledger
diffing, apply targeting), the stamp/ensure DB paths via a fake
connection, and the apply loop with real (temp-dir) migration files —
no live database.

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


def _row(revision, filename, status="applied"):
    """Ledger fetch row (revision, filename, status, applied_at)."""
    return (revision, filename, status, datetime(2026, 10, 3))


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
    """stamp/apply arguments resolve to exactly one discovered file."""

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
        rows = {
            "003": {"filename": "003_add_api_traces_table.py", "status": APPLIED},
            "004": {"filename": "004_add_vault_clients_public_columns.py",
                    "status": APPLIED},
        }
        status = compute_status(self.FILES, rows)
        self.assertEqual(status, [
            (self.FILES[0], APPLIED),
            (self.FILES[1], APPLIED),
            (self.FILES[2], PENDING),
        ])

    def test_failed_and_historical_reported_verbatim(self):
        from migrations.runner import FAILED, HISTORICAL, PENDING, compute_status
        rows = {
            "003": {"filename": "003_add_api_traces_table.py", "status": FAILED},
            "004": {"filename": "004_add_vault_clients_public_columns.py",
                    "status": HISTORICAL},
        }
        status = compute_status(self.FILES, rows)
        self.assertEqual([state for _, state in status],
                         [FAILED, HISTORICAL, PENDING])

    def test_ledger_row_without_file_is_missing(self):
        from migrations.runner import MISSING_FILE, compute_status
        rows = {"002": {"filename": "002_add_submissions_table.py",
                        "status": "applied"}}
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


class TestFormatSummary(unittest.TestCase):
    """One-line status counts in fixed order, zeros omitted."""

    def test_applied_and_pending(self):
        from migrations.runner import APPLIED, PENDING, _format_summary
        files = _make_files(("001", "001_a.py"), ("002", "002_b.py"))
        summary = _format_summary([(files[0], APPLIED), (files[1], PENDING)])
        self.assertEqual(summary, "1 applied, 1 pending of 2 migration file(s)")

    def test_mixed_states_omitting_zeros(self):
        from migrations.runner import APPLIED, FAILED, HISTORICAL, MISSING_FILE, PENDING, _format_summary

        files = _make_files(("001", "001_a.py"), ("002", "002_b.py"),
                            ("003", "003_c.py"), ("004", "004_d.py"))
        gone = _missing("009", "009_gone.py")
        status = [
            (files[0], APPLIED),
            (files[1], FAILED),
            (files[2], HISTORICAL),
            (files[3], PENDING),
            (gone, MISSING_FILE),
        ]
        summary = _format_summary(status)
        self.assertEqual(
            summary,
            "1 applied, 1 pending, 1 failed, 1 historical, 1 missing-file "
            "of 4 migration file(s)",
        )


def _missing(revision, filename):
    from migrations.runner import MigrationFile
    return MigrationFile(revision=revision, filename=filename)


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

    def setUp(self):
        # _upsert_row reads applied_by from getpass; freeze it
        self.user_patcher = patch(
            "migrations.runner._get_user", return_value="operator")
        self.user_patcher.start()
        self.addCleanup(self.user_patcher.stop)

    def _inserts(self, conn):
        return [(sql, params) for sql, params in conn.cursor_obj.executed
                if "INSERT INTO" in sql]

    def test_upserts_applied_row(self):
        from migrations.runner import stamp
        conn = FakeConn(FakeCursor(fetchone_results=[None]))
        self.assertTrue(stamp(conn, self.FILE))
        self.assertEqual(conn.commits, 1)
        (_, params), = self._inserts(conn)
        self.assertEqual(params[0], "005")
        self.assertEqual(params[1], "005_backfill_scope_string.py")
        self.assertEqual(params[2], "applied")
        self.assertIsInstance(params[3], datetime)
        self.assertIsNotNone(params[3].tzinfo)
        self.assertEqual(params[4], "operator")
        self.assertIsNone(params[5])
        (sql, _), = self._inserts(conn)
        self.assertIn("ON CONFLICT (revision) DO UPDATE", sql)

    def test_upserts_failure_row_with_error(self):
        from migrations.runner import _upsert_row
        conn = FakeConn()
        _upsert_row(conn, self.FILE, "failed", error="RuntimeError: boom")
        (_, params), = self._inserts(conn)
        self.assertEqual(params[2], "failed")
        self.assertEqual(params[5], "RuntimeError: boom")

    def test_skips_already_recorded_same_status(self):
        from migrations.runner import stamp
        conn = FakeConn(FakeCursor(fetchone_results=[("applied",)]))
        self.assertFalse(stamp(conn, self.FILE))
        self.assertEqual(self._inserts(conn), [])
        self.assertEqual(conn.commits, 0)

    def test_updates_differing_status(self):
        from migrations.runner import HISTORICAL, stamp
        conn = FakeConn(FakeCursor(fetchone_results=[("applied",)]))
        self.assertTrue(stamp(conn, self.FILE, HISTORICAL))
        (_, params), = self._inserts(conn)
        self.assertEqual(params[2], "historical")


class TestPendingForApply(unittest.TestCase):
    """apply targets: not applied and not historical, in order, bounded."""

    FILES = _make_files(
        ("003", "003_add_api_traces_table.py"),
        ("004", "004_add_vault_clients_public_columns.py"),
        ("005", "005_backfill_scope_string.py"),
        ("006", "006_add_client_allowed_scopes.py"),
    )

    def _rows(self, **overrides):
        from migrations.runner import APPLIED, HISTORICAL
        rows = {
            "003": {"status": APPLIED},
            "004": {"status": HISTORICAL},
        }
        rows.update(overrides)
        return rows

    def test_skips_applied_and_historical_includes_rest_in_order(self):
        from migrations.runner import pending_for_apply
        targets = pending_for_apply(self.FILES, self._rows())
        self.assertEqual([f.revision for f in targets], ["005", "006"])

    def test_failed_revision_is_retryable(self):
        from migrations.runner import FAILED, pending_for_apply
        rows = self._rows(**{"005": {"status": FAILED}})
        targets = pending_for_apply(self.FILES, rows)
        self.assertEqual([f.revision for f in targets], ["005", "006"])

    def test_up_to_bound(self):
        from migrations.runner import pending_for_apply
        bound = self.FILES[2]  # 005
        targets = pending_for_apply(self.FILES, self._rows(), bound)
        self.assertEqual([f.revision for f in targets], ["005"])

    def test_up_to_bound_excludes_higher_revisions(self):
        from migrations.runner import pending_for_apply
        bound = self.FILES[0]  # 003, already applied
        targets = pending_for_apply(self.FILES, self._rows(), bound)
        self.assertEqual(targets, [])

    def test_fresh_ledger_runs_everything(self):
        from migrations.runner import pending_for_apply
        targets = pending_for_apply(self.FILES, {})
        self.assertEqual([f.revision for f in targets],
                         ["003", "004", "005", "006"])


class TestLoadAndRunUpgrade(unittest.TestCase):
    """Module loading and the apply-mode adapter for upgrade()."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.dir = Path(self.tmpdir.name)
        self.marker = self.dir / "called.txt"

    def _write(self, name, source):
        (self.dir / name).write_text(source, encoding="utf-8")

    def _load(self, revision, filename):
        from migrations.runner import MigrationFile, load_migration
        file = MigrationFile(revision=revision, filename=filename)
        return load_migration(file, self.dir)

    def _run(self, revision, filename):
        from migrations.runner import MigrationFile, run_upgrade
        module = self._load(revision, filename)
        run_upgrade(module, MigrationFile(revision=revision, filename=filename))

    def test_bare_upgrade_called(self):
        self._write("001_plain.py", (
            "def upgrade():\n"
            f"    open({str(self.marker)!r}, 'a').write('bare\\n')\n"
        ))
        self._run("001", "001_plain.py")
        self.assertEqual(self.marker.read_text(), "bare\n")

    def test_apply_flag_migration_runs_in_apply_mode(self):
        # 005 pattern: upgrade(apply=False) dry-runs by default
        self._write("002_applyflag.py", (
            "def upgrade(apply=False):\n"
            f"    open({str(self.marker)!r}, 'a').write(f'apply={{apply}}\\n')\n"
        ))
        self._run("002", "002_applyflag.py")
        self.assertEqual(self.marker.read_text(), "apply=True\n")

    def test_missing_upgrade_raises(self):
        self._write("003_noupgrade.py", "other = 1\n")
        with self.assertRaises(ValueError):
            self._run("003", "003_noupgrade.py")


class TestFetchLedgerRows(unittest.TestCase):
    """Reading the ledger, tolerating a missing table."""

    def test_rows_keyed_by_revision(self):
        from migrations.runner import _fetch_ledger_rows
        rows = [
            _row("003", "003_add_api_traces_table.py"),
            _row("005", "005_backfill_scope_string.py"),
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

    def _run(self, argv, conn, files=None, migrations_dir=None):
        import contextlib
        import io

        from migrations.runner import main
        stdout, stderr = io.StringIO(), io.StringIO()
        patches = [
            patch("migrations.runner._connect", return_value=conn),
            patch("migrations.runner.discover_migration_files",
                  return_value=files or self.FILES),
        ]
        if migrations_dir is not None:
            patches.append(
                patch("migrations.runner.MIGRATIONS_DIR", migrations_dir))
        with contextlib.ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            stack.enter_context(contextlib.redirect_stdout(stdout))
            stack.enter_context(contextlib.redirect_stderr(stderr))
            exit_code = main(argv)
        return exit_code, stdout.getvalue(), stderr.getvalue()

    # ---- status ----

    def test_status_reports_applied_and_pending(self):
        cursor = FakeCursor(fetchall_rows=[_row("003", "003_add_api_traces_table.py")])
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
        self.assertIn("2 pending of 2 migration file(s)", stdout)

    def test_status_shows_historical_and_failed(self):
        cursor = FakeCursor(fetchall_rows=[
            _row("003", "003_add_api_traces_table.py"),
            _row("005", "005_backfill_scope_string.py", status="historical"),
        ])
        exit_code, stdout, _ = self._run(["status"], FakeConn(cursor))
        self.assertEqual(exit_code, 0)
        self.assertIn("historical", stdout)
        self.assertIn("1 applied, 1 historical of 2 migration file(s)", stdout)

    # ---- ensure / stamp ----

    def test_ensure_creates_table(self):
        conn = FakeConn()
        exit_code, stdout, _ = self._run(["ensure"], conn)
        self.assertEqual(exit_code, 0)
        self.assertIn("CREATE TABLE IF NOT EXISTS",
                      conn.cursor_obj.executed[0][0])
        self.assertIn("ready", stdout)

    def test_stamp_all_stamps_only_unrecorded(self):
        # ledger already has 003; only 005 should be written
        cursor = FakeCursor(
            fetchall_rows=[_row("003", "003_add_api_traces_table.py")],
            fetchone_results=[None],
        )
        conn = FakeConn(cursor)
        exit_code, stdout, _ = self._run(["stamp", "all"], conn)
        self.assertEqual(exit_code, 0)
        inserts = [(sql, params) for sql, params in cursor.executed
                   if "INSERT INTO" in sql]
        self.assertEqual(len(inserts), 1)
        self.assertEqual(inserts[0][1][0], "005")
        self.assertIn("stamped 1 migration(s) as applied", stdout)

    def test_stamp_all_when_fully_applied(self):
        cursor = FakeCursor(fetchall_rows=[
            _row("003", "003_add_api_traces_table.py"),
            _row("005", "005_backfill_scope_string.py"),
        ])
        exit_code, stdout, _ = self._run(["stamp", "all"], FakeConn(cursor))
        self.assertEqual(exit_code, 0)
        self.assertIn("nothing to stamp", stdout)

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

    def test_stamp_as_historical(self):
        cursor = FakeCursor(fetchone_results=[None])
        conn = FakeConn(cursor)
        exit_code, stdout, _ = self._run(
            ["stamp", "005", "--as", "historical"], conn)
        self.assertEqual(exit_code, 0)
        inserts = [(sql, params) for sql, params in cursor.executed
                   if "INSERT INTO" in sql]
        self.assertEqual(inserts[0][1][2], "historical")
        self.assertIn("stamped 005 as historical", stdout)

    def test_stamp_unknown_revision_fails_cleanly(self):
        conn = FakeConn()
        exit_code, _, stderr = self._run(["stamp", "999"], conn)
        self.assertEqual(exit_code, 1)
        self.assertIn("error: Unknown migration '999'", stderr)


class TestApply(unittest.TestCase):
    """apply: ordering, pending detection, failure path, --up-to bound.

    Uses real migration files in a temp dir (loaded via importlib by the
    runner) and a fake DB connection.
    """

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.dir = Path(self.tmpdir.name)
        self.marker = self.dir / "called.txt"

    def _write_migration(self, name, body):
        (self.dir / name).write_text(
            f"def upgrade{body}\n", encoding="utf-8")

    def _files(self, *specs):
        from migrations.runner import MigrationFile
        return [MigrationFile(revision=rev, filename=name)
                for rev, name in specs]

    def _run_apply(self, argv, files, fetchall_rows=None,
                   fetchone_results=None):
        """Run apply via main() with the temp dir as MIGRATIONS_DIR."""
        import contextlib
        import io

        from migrations.runner import main
        cursor = FakeCursor(fetchall_rows=fetchall_rows or [],
                            fetchone_results=fetchone_results or [])
        conn = FakeConn(cursor)
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch("migrations.runner._connect", return_value=conn), \
                patch("migrations.runner.discover_migration_files",
                      return_value=files), \
                patch("migrations.runner.MIGRATIONS_DIR", self.dir), \
                contextlib.redirect_stdout(stdout), \
                contextlib.redirect_stderr(stderr):
            exit_code = main(["apply", *argv])
        return exit_code, stdout.getvalue(), stderr.getvalue(), conn, cursor

    def test_runs_pending_in_revision_order(self):
        self._write_migration("001_a.py", "():\n    pass\n")
        self._write_migration("002_b.py", "():\n    pass\n")
        files = self._files(("001", "001_a.py"), ("002", "002_b.py"))
        exit_code, stdout, _, conn, cursor = self._run_apply([], files)
        self.assertEqual(exit_code, 0)
        self.assertLess(stdout.index("applying 001"),
                        stdout.index("applying 002"))
        self.assertIn("applied 2 migration(s)", stdout)
        inserts = [(sql, params) for sql, params in cursor.executed
                   if "INSERT INTO" in sql]
        self.assertEqual([params[0] for _, params in inserts], ["001", "002"])
        self.assertEqual([params[2] for _, params in inserts],
                         ["applied", "applied"])
        self.assertEqual(conn.commits, 3)  # ensure + one per migration row

    def test_skips_applied_and_historical(self):
        from migrations.runner import APPLIED, HISTORICAL
        self._write_migration("003_c.py", "():\n    pass\n")
        self._write_migration("004_d.py", "():\n    pass\n")
        files = self._files(("003", "003_c.py"), ("004", "004_d.py"))
        rows = [
            _row("003", "003_c.py", status=APPLIED),
            _row("004", "004_d.py", status=HISTORICAL),
        ]
        exit_code, stdout, _, _, cursor = self._run_apply([], files, rows)
        self.assertEqual(exit_code, 0)
        self.assertIn("up to date", stdout)
        self.assertNotIn("applying", stdout)
        self.assertFalse(
            any("INSERT INTO" in sql for sql, _ in cursor.executed))

    def test_retries_failed_revision(self):
        from migrations.runner import FAILED
        self._write_migration("005_e.py", "():\n    pass\n")
        files = self._files(("005", "005_e.py"))
        rows = [_row("005", "005_e.py", status=FAILED)]
        exit_code, stdout, _, _, cursor = self._run_apply([], files, rows)
        self.assertEqual(exit_code, 0)
        self.assertIn("applying 005", stdout)
        inserts = [(sql, params) for sql, params in cursor.executed
                   if "INSERT INTO" in sql]
        self.assertEqual(inserts[0][1][2], "applied")
        self.assertIsNone(inserts[0][1][5])  # error cleared on success

    def test_failure_records_row_and_stops(self):
        self._write_migration("001_a.py", "():\n    pass\n")
        self._write_migration("002_bad.py", "():\n    raise RuntimeError('boom')\n")
        self._write_migration("003_c.py", "():\n    pass\n")
        files = self._files(("001", "001_a.py"), ("002", "002_bad.py"),
                            ("003", "003_c.py"))
        exit_code, stdout, stderr, _, cursor = self._run_apply([], files)
        self.assertEqual(exit_code, 1)
        # 001 ran and recorded; 002 failed and recorded; 003 never attempted
        self.assertIn("applying 001", stdout)
        self.assertLess(stdout.index("applied 001"),
                        stdout.index("applying 002"))
        self.assertNotIn("applying 003", stdout)
        inserts = [(sql, params) for sql, params in cursor.executed
                   if "INSERT INTO" in sql]
        self.assertEqual([params[0] for _, params in inserts], ["001", "002"])
        self.assertEqual(inserts[1][1][2], "failed")
        self.assertIn("RuntimeError: boom", inserts[1][1][5])
        self.assertIn("FAILED 002", stderr)
        self.assertIn("1 later migration(s) not run", stderr)

    def test_up_to_bound_stops_after_revision(self):
        self._write_migration("001_a.py", "():\n    pass\n")
        self._write_migration("002_b.py", "():\n    pass\n")
        files = self._files(("001", "001_a.py"), ("002", "002_b.py"))
        exit_code, stdout, _, _, cursor = self._run_apply(
            ["--up-to", "001"], files)
        self.assertEqual(exit_code, 0)
        self.assertIn("applying 001", stdout)
        self.assertNotIn("applying 002", stdout)
        self.assertIn("applied 1 migration(s)", stdout)

    def test_up_to_unknown_revision_fails_cleanly(self):
        files = self._files(("001", "001_a.py"))
        exit_code, _, stderr, _, _ = self._run_apply(
            ["--up-to", "999"], files)
        self.assertEqual(exit_code, 1)
        self.assertIn("error: Unknown migration '999'", stderr)

    def test_up_to_already_applied_is_noop(self):
        from migrations.runner import APPLIED
        files = self._files(("001", "001_a.py"))
        rows = [_row("001", "001_a.py", status=APPLIED)]
        exit_code, stdout, _, _, _ = self._run_apply(
            ["--up-to", "001"], files, rows)
        self.assertEqual(exit_code, 0)
        self.assertIn("up to date", stdout)

    def test_missing_upgrade_recorded_as_failure(self):
        (self.dir / "001_bad.py").write_text("other = 1\n", encoding="utf-8")
        files = self._files(("001", "001_bad.py"))
        exit_code, _, stderr, _, cursor = self._run_apply([], files)
        self.assertEqual(exit_code, 1)
        inserts = [(sql, params) for sql, params in cursor.executed
                   if "INSERT INTO" in sql]
        self.assertEqual(inserts[0][1][2], "failed")
        self.assertIn("has no upgrade()", inserts[0][1][5])
        self.assertIn("FAILED 001", stderr)

    def test_module_top_level_exception_counts_as_failure(self):
        (self.dir / "001_bad.py").write_text(
            "raise ValueError('import-time boom')\n", encoding="utf-8")
        files = self._files(("001", "001_bad.py"))
        exit_code, _, stderr, _, cursor = self._run_apply([], files)
        self.assertEqual(exit_code, 1)
        inserts = [(sql, params) for sql, params in cursor.executed
                   if "INSERT INTO" in sql]
        self.assertEqual(inserts[0][1][2], "failed")
        self.assertIn("import-time boom", inserts[0][1][5])


if __name__ == "__main__":
    unittest.main()
