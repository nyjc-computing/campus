"""Unit tests for the shared migration management blueprint (#1169).

Drives migrations/routes.py — the per-service /admin/migrations
surface — with an injected fake gate and a faked runner, so the route
contract (status payload shape, apply 202 + background thread, abort
between migrations, rollback refusal while running) is verified
without a database or HTTP authentication. The per-service gates are
covered separately (the auth gate matrix lives in
tests/integration/auth/test_migrations_routes.py).

IMPORTANT: Lazy imports are required to avoid storage initialization
before test mode is configured (see AGENTS.md - Storage Initialization
Order).
"""

import json
import os
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path
from unittest import mock

import flask

from campus.common.errors import api_errors


def _migration_source(target_db: str = "auth", rollback: str | None = None,
                      docstring: str | None = None) -> str:
    """The text of a minimal migration file for metadata parsing."""
    doc = docstring or "First line of the summary.\n\nLonger description."
    lines = [
        f'"""{doc}"""',
        "",
        f'TARGET_DB = "{target_db}"',
    ]
    if rollback:
        lines.append(f'ROLLBACK_SUPPORTED = "{rollback}"')
    return "\n".join(lines)


class BlueprintContractTestCase(unittest.TestCase):
    """The route contract over an injected fake gate and faked runner."""

    REVISIONS = ("010", "011")

    def setUp(self):
        """A fresh app with the shared blueprint and a recording gate.

        The runner is faked at its edges: file discovery reads a real
        temp migrations/ dir (metadata parsing exercises real files),
        the ledger fetch returns canned rows, and main() is a
        controllable fake.
        """
        import campus.common.errors
        from migrations import routes as migration_routes

        self.migrations_dir = Path(tempfile.mkdtemp(prefix="mig-routes-"))
        (self.migrations_dir / "010_created.py").write_text(
            _migration_source("auth"), encoding="utf-8"
        )
        (self.migrations_dir / "011_next.py").write_text(
            _migration_source("api", rollback="backup",
                              docstring="Backup-rollback migration."),
            encoding="utf-8",
        )
        self.files = [
            mock.Mock(revision="010", filename="010_created.py",
                      target_db="auth"),
            mock.Mock(revision="011", filename="011_next.py",
                      target_db="api"),
        ]
        self.history = [{
            # JSON-friendly, exactly what _fetch_history_rows returns
            # (iso strings for timestamps, ints for durations).
            "revision": "010",
            "filename": "010_created.py",
            "status": "applied",
            "applied_at": "2026-11-18T12:00:00",
            "applied_by": "operator",
            "duration_ms": 1234,
            "error": None,
            "file_hash": "a" * 64,
        }]

        self.app = flask.Flask(__name__)
        campus.common.errors.init_app(self.app)
        self.gated_levels: list[str] = []
        self.emitted: list[tuple[str, dict]] = []
        self.service_db = "auth"

        def gate(level: str) -> None:
            self.gated_levels.append(level)

        def emit(event: str, data: dict) -> None:
            self.emitted.append((event, data))

        self.app.register_blueprint(migration_routes.create_blueprint(
            service_db=self.service_db, gate=gate, emit=emit,
        ))
        self.client = self.app.test_client()

    def tearDown(self):
        """Wait out any stray apply thread from the run-state holder."""
        self._wait_not_running()

    # -- fakes ----------------------------------------------------------

    def _fake_runner(self, main=None):
        """Patch the runner functions the blueprint reads."""
        from migrations import runner

        for name, value in (
            ("discover_migration_files",
             mock.Mock(return_value=self.files)),
            # The scope filter is what separates services' migrations
            # (#1104); the fake files carry mixed target_dbs, so the
            # filter is pinned to the identity for these tests.
            ("filter_files_by_db", lambda files, db: list(files)),
            ("resolve_scoped_revision", self._resolve_scoped),
            ("MIGRATIONS_DIR", self.migrations_dir),
        ):
            patcher = mock.patch.object(runner, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        if main is not None:
            patcher = mock.patch.object(runner, "main", main)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _resolve_scoped(self, arg, files, db):
        if arg in self.REVISIONS:
            return mock.Mock(revision=arg)
        known = ", ".join(f.revision for f in files)
        raise ValueError(
            f"Unknown migration {arg!r} (known {db} revisions: {known})"
        )

    def _fake_history(self):
        from migrations import routes as migration_routes

        patcher = mock.patch.object(
            migration_routes, "_fetch_history_rows",
            side_effect=lambda: [dict(row) for row in self.history],
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _wait_not_running(self, timeout: float = 5.0,
                          service_db: str | None = None) -> None:
        from migrations.routes import _RUN_STATE

        service_db = service_db or self.service_db
        deadline = time.monotonic() + timeout
        while _RUN_STATE.is_running(service_db):
            if time.monotonic() > deadline:
                self.fail(
                    f"apply [{service_db}] did not finish within {timeout}s"
                )
            time.sleep(0.01)

    # -- status ---------------------------------------------------------

    def test_status_gates_read_and_returns_payload(self):
        self._fake_runner()
        self._fake_history()
        response = self.client.get("/admin/migrations/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.gated_levels, ["read"])
        body = response.get_json()
        self.assertEqual(body["service"], "auth")
        self.assertEqual(body["status"], [
            {"revision": "010", "filename": "010_created.py",
             "state": "applied"},
            {"revision": "011", "filename": "011_next.py",
             "state": "pending"},
        ])
        self.assertEqual(body["history"], [{
            "revision": "010",
            "filename": "010_created.py",
            "status": "applied",
            "applied_at": "2026-11-18T12:00:00",
            "applied_by": "operator",
            "duration_ms": 1234,
            "error": None,
            "file_hash": "a" * 64,
        }])
        self.assertFalse(body["running"])

    def test_status_plan_lists_pending_with_metadata(self):
        self._fake_runner()
        self._fake_history()
        body = self.client.get("/admin/migrations/").get_json()
        self.assertEqual(len(body["plan"]), 1)
        entry = body["plan"][0]
        self.assertEqual(entry["revision"], "011")
        self.assertEqual(entry["filename"], "011_next.py")
        self.assertEqual(entry["rollback"], "backup")
        self.assertEqual(entry["summary"], "Backup-rollback migration.")
        # sha256 of the file on disk
        import hashlib

        expected = hashlib.sha256(
            (self.migrations_dir / "011_next.py").read_bytes()
        ).hexdigest()
        self.assertEqual(entry["hash"], expected)

    def test_status_running_reflects_the_holder(self):
        started = threading.Event()
        release = threading.Event()

        def fake_main(argv, should_cancel=None):
            started.set()
            release.wait(timeout=5)
            return 0

        self._fake_runner()
        self._fake_history()
        from migrations import runner

        with mock.patch.object(runner, "main", fake_main):
            response = self.client.post("/admin/migrations/apply",
                                        json={})
            self.assertEqual(response.status_code, 202)
            self.assertTrue(started.wait(timeout=5))
            status = self.client.get("/admin/migrations/").get_json()
            self.assertTrue(status["running"])
            release.set()
            self._wait_not_running()

    def test_status_gate_denial_is_a_403_envelope(self):
        def deny(level):
            raise api_errors.ForbiddenError(
                "Token lacks 'migrations:read' (#1168/#865)")

        from migrations import routes as migration_routes

        app = flask.Flask(__name__)
        import campus.common.errors

        campus.common.errors.init_app(app)
        app.register_blueprint(migration_routes.create_blueprint(
            service_db="auth", gate=deny,
        ))
        response = app.test_client().get("/admin/migrations/")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.get_json()["error"]["code"], "FORBIDDEN"
        )

    # -- apply ----------------------------------------------------------

    def test_apply_returns_202_and_runs_the_runner_in_background(self):
        calls: list[list] = []
        done = threading.Event()

        def fake_main(argv, should_cancel=None):
            calls.append(argv)
            done.set()
            return 0

        self._fake_runner(main=fake_main)
        response = self.client.post("/admin/migrations/apply", json={})
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.get_json(),
                         {"started": True, "service": "auth"})
        self.assertEqual(self.gated_levels[-1], "write")
        self.assertTrue(done.wait(timeout=5))
        self.assertEqual(calls, [["--db", "auth", "apply"]])
        self._wait_not_running()
        # Mutations emit the audit event stamped by the service wiring.
        self.assertEqual(
            [name for name, _ in self.emitted],
            ["campus.migrations.apply"],
        )

    def test_apply_up_to_passes_the_runner_bound(self):
        calls: list[list] = []
        done = threading.Event()

        def fake_main(argv, should_cancel=None):
            calls.append(argv)
            done.set()
            return 0

        self._fake_runner(main=fake_main)
        response = self.client.post("/admin/migrations/apply",
                                    json={"up_to": "011"})
        self.assertEqual(response.status_code, 202)
        self.assertTrue(done.wait(timeout=5))
        self.assertEqual(calls, [["--db", "auth", "apply",
                                  "--up-to", "011"]])
        self._wait_not_running()

    def test_apply_unknown_up_to_is_a_400(self):
        self._fake_runner(main=lambda *a, **k: self.fail(
            "runner must not run for an unknown revision"))
        response = self.client.post("/admin/migrations/apply",
                                    json={"up_to": "999"})
        self.assertEqual(response.status_code, 400)

    def test_second_apply_is_409_while_one_is_in_flight(self):
        started = threading.Event()
        release = threading.Event()

        def fake_main(argv, should_cancel=None):
            started.set()
            release.wait(timeout=5)
            return 0

        self._fake_runner(main=fake_main)
        first = self.client.post("/admin/migrations/apply", json={})
        self.assertEqual(first.status_code, 202)
        self.assertTrue(started.wait(timeout=5))
        second = self.client.post("/admin/migrations/apply", json={})
        self.assertEqual(second.status_code, 409)
        release.set()
        self._wait_not_running()

    def test_apply_scope_is_isolated_per_service(self):
        """A running auth apply does not block the api scope in-process.

        The run-state holder is keyed by runner scope: each service is
        its own process in production, and the registry follows that
        scope rather than the whole process.
        """
        started = threading.Event()
        release = threading.Event()

        def fake_main(argv, should_cancel=None):
            started.set()
            release.wait(timeout=5)
            return 0

        self._fake_runner(main=fake_main)
        first = self.client.post("/admin/migrations/apply", json={})
        self.assertEqual(first.status_code, 202)
        self.assertTrue(started.wait(timeout=5))

        import campus.common.errors
        from migrations import routes as migration_routes

        other = flask.Flask(__name__)
        campus.common.errors.init_app(other)
        other.register_blueprint(migration_routes.create_blueprint(
            service_db="api", gate=lambda level: None,
        ))
        response = other.test_client().post("/admin/migrations/apply",
                                            json={})
        self.assertEqual(response.status_code, 202)
        # Release the fake runner, then wait out BOTH scopes' applies.
        release.set()
        self._wait_not_running()
        self._wait_not_running(service_db="api")

    # -- abort ----------------------------------------------------------

    def test_abort_sets_the_cancel_event(self):
        cancelled = threading.Event()
        started = threading.Event()

        def fake_main(argv, should_cancel=None):
            started.set()
            if should_cancel is None:
                return 0
            deadline = time.monotonic() + 5
            while not should_cancel():
                if time.monotonic() > deadline:
                    return 0
                time.sleep(0.01)
            cancelled.set()
            return 1

        self._fake_runner(main=fake_main)
        self.assertEqual(
            self.client.post("/admin/migrations/apply", json={}).status_code,
            202,
        )
        self.assertTrue(started.wait(timeout=5))
        response = self.client.post("/admin/migrations/abort")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"aborting": True})
        self.assertEqual(self.gated_levels[-1], "write")
        self.assertTrue(cancelled.wait(timeout=5))
        self._wait_not_running()
        self.assertEqual(
            [name for name, _ in self.emitted][-1],
            "campus.migrations.abort",
        )

    def test_abort_with_nothing_running_is_409(self):
        self._fake_runner(main=lambda *a, **k: 0)
        response = self.client.post("/admin/migrations/abort")
        self.assertEqual(response.status_code, 409)

    # -- rollback -------------------------------------------------------

    def test_rollback_success_is_synchronous(self):
        calls: list[list] = []

        def fake_main(argv, should_cancel=None):
            calls.append(argv)
            return 0

        self._fake_runner(main=fake_main)
        response = self.client.post("/admin/migrations/rollback",
                                    json={"revision": "010"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"rolled_back": "010"})
        self.assertEqual(self.gated_levels[-1], "admin")
        self.assertEqual(calls, [["--db", "auth", "rollback", "010"]])
        self.assertEqual(
            [name for name, _ in self.emitted][-1],
            "campus.migrations.rollback",
        )

    def test_rollback_passes_from_backup_through(self):
        calls: list[list] = []

        def fake_main(argv, should_cancel=None):
            calls.append(argv)
            return 0

        self._fake_runner(main=fake_main)
        response = self.client.post(
            "/admin/migrations/rollback",
            json={"revision": "010",
                  "from_backup": "bucket://campus-backups/migrations/010/x"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(calls, [
            ["--db", "auth", "rollback", "010",
             "--from-backup", "bucket://campus-backups/migrations/010/x"],
        ])

    def test_rollback_unknown_revision_is_a_400(self):
        self._fake_runner(main=lambda *a, **k: self.fail(
            "runner must not run for an unknown revision"))
        response = self.client.post("/admin/migrations/rollback",
                                    json={"revision": "999"})
        self.assertEqual(response.status_code, 400)

    def test_rollback_runner_failure_is_a_409_with_log(self):
        def fake_main(argv, should_cancel=None):
            print("error: 010 is not recorded applied", file=__import__(
                "sys").stderr)
            return 1

        self._fake_runner(main=fake_main)
        response = self.client.post("/admin/migrations/rollback",
                                    json={"revision": "010"})
        self.assertEqual(response.status_code, 409)
        # No mutation happened, so no audit event.
        self.assertEqual(self.emitted, [])

    def test_rollback_is_refused_while_an_apply_is_running(self):
        started = threading.Event()
        release = threading.Event()

        def fake_main(argv, should_cancel=None):
            started.set()
            release.wait(timeout=5)
            return 0

        self._fake_runner(main=fake_main)
        self.assertEqual(
            self.client.post("/admin/migrations/apply", json={}).status_code,
            202,
        )
        self.assertTrue(started.wait(timeout=5))
        response = self.client.post("/admin/migrations/rollback",
                                    json={"revision": "010"})
        self.assertEqual(response.status_code, 409)
        release.set()
        self._wait_not_running()

    def test_rollback_requires_the_admin_level(self):
        """Each route consults its own vocabulary level (#1168)."""
        seen: list[str] = []

        def deny_all(level):
            seen.append(level)
            raise api_errors.ForbiddenError(f"recorded {level}")

        from migrations import routes as migration_routes

        app = flask.Flask(__name__)
        import campus.common.errors

        campus.common.errors.init_app(app)
        app.register_blueprint(migration_routes.create_blueprint(
            service_db="auth", gate=deny_all,
        ))
        client = app.test_client()
        self.assertEqual(
            client.get("/admin/migrations/").status_code, 403)
        self.assertEqual(
            client.post("/admin/migrations/apply", json={}).status_code,
            403,
        )
        self.assertEqual(
            client.post("/admin/migrations/abort").status_code,
            403,
        )
        self.assertEqual(
            client.post("/admin/migrations/rollback",
                        json={"revision": "010"}).status_code,
            403,
        )
        self.assertEqual(seen, ["read", "write", "write", "admin"])


class ServiceDbResolutionTestCase(unittest.TestCase):
    """resolve_service_db mirrors the runner's DEPLOY derivation."""

    def test_deploy_derives_the_scope(self):
        from migrations import routes as migration_routes

        for deploy, expected in (
            ("campus.auth", "auth"),
            ("campus.api", "api"),
            ("campus.audit", "audit"),
        ):
            with mock.patch.dict(os.environ, {"DEPLOY": deploy}):
                self.assertEqual(migration_routes.resolve_service_db(),
                                 expected, deploy)

    def test_missing_deploy_falls_back_to_auth(self):
        from migrations import routes as migration_routes

        env = {k: v for k, v in os.environ.items() if k != "DEPLOY"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(migration_routes.resolve_service_db(), "auth")

    def test_unknown_service_db_is_rejected_at_factory_time(self):
        from migrations import routes as migration_routes

        with self.assertRaises(ValueError):
            migration_routes.create_blueprint(
                service_db="staging", gate=lambda level: None,
            )


class LedgerFetchTestCase(unittest.TestCase):
    """_fetch_history_rows reads the ledger JSON-friendly, fail-soft."""

    class _FakeCursor:
        def __init__(self, rows, error=None):
            self._rows = rows
            self._error = error

        def execute(self, *_a, **_k):
            if self._error is not None:
                raise self._error

        def fetchall(self):
            return self._rows

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class _FakeConn:
        def __init__(self, cursor):
            self._cursor = cursor
            self.rolled_back = False
            self.closed = False

        def cursor(self):
            return self._cursor

        def rollback(self):
            self.rolled_back = True

        def close(self):
            self.closed = True

    def _undefined_table_error(self):
        """A psycopg2 error carrying the 42P01 undefined-table code.

        pgcode is a read-only descriptor on psycopg2.Error, so the
        code rides in as a subclass class attribute.
        """
        import psycopg2

        class _UndefinedTable(psycopg2.errors.UndefinedTable):
            pgcode = "42P01"

        return _UndefinedTable()

    def test_rows_are_json_friendly(self):
        import datetime
        from decimal import Decimal

        from migrations import routes as migration_routes

        rows = [(
            "010", "010_created.py", "applied",
            datetime.datetime(2026, 11, 18, 12, 0, 0),
            "operator", Decimal("88"), None, "b" * 64,
        )]
        conn = self._FakeConn(self._FakeCursor(rows))
        with mock.patch.object(migration_routes, "_connect_ledger",
                               return_value=conn):
            history = migration_routes._fetch_history_rows()
        self.assertEqual(history, [{
            "revision": "010",
            "filename": "010_created.py",
            "status": "applied",
            "applied_at": "2026-11-18T12:00:00",
            "applied_by": "operator",
            "duration_ms": 88,
            "error": None,
            "file_hash": "b" * 64,
        }])
        self.assertTrue(conn.closed)
        json.dumps(history)  # must be directly serializable

    def test_missing_ledger_table_reads_as_no_history(self):
        from migrations import routes as migration_routes

        conn = self._FakeConn(self._FakeCursor(
            [], error=self._undefined_table_error()))
        with mock.patch.object(migration_routes, "_connect_ledger",
                               return_value=conn):
            self.assertEqual(migration_routes._fetch_history_rows(), [])
        self.assertTrue(conn.rolled_back)

    def test_other_ledger_errors_propagate(self):
        from migrations import routes as migration_routes

        conn = self._FakeConn(self._FakeCursor(
            [], error=RuntimeError("connection refused")))
        with (
            mock.patch.object(migration_routes, "_connect_ledger",
                              return_value=conn),
            self.assertRaises(RuntimeError),
        ):
            migration_routes._fetch_history_rows()


class ModuleMetaTestCase(unittest.TestCase):
    """_read_module_meta parses declarations without importing."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="mig-meta-"))

    def _meta(self, source: str, name: str | None = None):
        from migrations.routes import _read_module_meta

        path = self.dir / (name or f"{uuid.uuid4().hex[:8]}_test.py")
        path.write_text(source, encoding="utf-8")
        return _read_module_meta(path)

    def test_rollback_declaration_and_summary(self):
        rollback, summary = self._meta(_migration_source(
            "api", rollback="ddl", docstring="Add the thing.\n\nMore."))
        self.assertEqual(rollback, "ddl")
        self.assertEqual(summary, "Add the thing.")

    def test_undeclared_rollback_is_none(self):
        rollback, summary = self._meta(_migration_source("auth"))
        self.assertIsNone(rollback)
        self.assertEqual(summary, "First line of the summary.")

    def test_real_migration_file_parses(self):
        """The repo's own migrations parse without importing them."""
        from migrations import runner
        from migrations.routes import _read_module_meta

        path = Path(runner.MIGRATIONS_DIR) / "010_create_access_grants.py"
        rollback, summary = _read_module_meta(path)
        self.assertIsNone(rollback)
        self.assertTrue(summary.startswith("Create access_grants table"))


class DesignationLegTestCase(unittest.TestCase):
    """The api/audit designation leg and the fail-closed gate."""

    def test_designation_true_via_injected_check(self):
        from migrations.routes import _designation_leg_holds

        queries: list[dict] = []

        def check_grant(**query):
            queries.append(query)
            return True

        self.assertTrue(_designation_leg_holds(
            "u1", "write", "api", check_grant=check_grant))
        self.assertEqual(queries, [{
            "grantee_type": "user",
            "grantee_id": "u1",
            "resource_type": "migrations",
            "resource_id": "api",
            "level": "write",
        }])

    def test_designation_false_via_injected_check(self):
        from migrations.routes import _designation_leg_holds

        self.assertFalse(_designation_leg_holds(
            "u1", "admin", "audit", check_grant=lambda **q: False))

    def test_gate_denies_non_user_principals(self):
        from migrations.routes import make_grant_check_gate

        gate = make_grant_check_gate("api", check_grant=lambda **q: True)
        with flask.Flask(__name__).test_request_context():
            flask.g.current_client = {"id": "cl_x"}
            flask.g.current_user = None
            with self.assertRaises(api_errors.ForbiddenError) as ctx:
                gate("read")
            self.assertIn("audit API keys", str(ctx.exception))

    def test_gate_capability_leg_requires_scopes(self):
        """A scopes-less context (audit API keys, or an auth deployment
        predating #1183) fails closed without consulting designation."""
        from migrations.routes import make_grant_check_gate

        def check_grant(**query):
            raise AssertionError("designation must not run while the "
                                 "capability leg already fails")

        gate = make_grant_check_gate("api", check_grant=check_grant)
        with flask.Flask(__name__).test_request_context():
            flask.g.current_user = {"id": "u1"}
            flask.g.current_scopes = []
            with self.assertRaises(api_errors.ForbiddenError) as ctx:
                gate("read")
            message = str(ctx.exception)
            self.assertIn("Token lacks 'migrations:read'", message)
            self.assertIn("#1183", message)
            self.assertIn("fails closed", message)

    def test_gate_capability_leg_checks_level_algebra(self):
        """admin implies write implies read; write does not satisfy
        admin (mirrors campus.auth.scopes, kept import-free here)."""
        from migrations.routes import make_grant_check_gate

        gate = make_grant_check_gate("api", check_grant=lambda **q: True)
        with flask.Flask(__name__).test_request_context():
            flask.g.current_user = {"id": "u1"}
            flask.g.current_scopes = ["migrations:admin"]
            gate("read")
            gate("write")
            gate("admin")
        with flask.Flask(__name__).test_request_context():
            flask.g.current_user = {"id": "u1"}
            flask.g.current_scopes = ["migrations:write"]
            gate("read")
            gate("write")
            with self.assertRaises(api_errors.ForbiddenError) as ctx:
                gate("admin")
            self.assertIn("Token lacks 'migrations:admin'",
                          str(ctx.exception))

    def test_gate_capability_leg_scopes_other_vocabulary_inert(self):
        """A users:admin scope confers nothing on the migrations gate."""
        from migrations.routes import make_grant_check_gate

        gate = make_grant_check_gate("api", check_grant=lambda **q: True)
        with flask.Flask(__name__).test_request_context():
            flask.g.current_user = {"id": "u1"}
            flask.g.current_scopes = ["users:admin"]
            with self.assertRaises(api_errors.ForbiddenError):
                gate("read")

    def test_gate_two_legs_both_required(self):
        """Scope without designation denies with the #1168 message;
        designation without scope denies with the #865 message."""
        from migrations.routes import make_grant_check_gate

        # scope held, no designation
        gate = make_grant_check_gate("api", check_grant=lambda **q: False)
        with flask.Flask(__name__).test_request_context():
            flask.g.current_user = {"id": "u1"}
            flask.g.current_scopes = ["migrations:write"]
            with self.assertRaises(api_errors.ForbiddenError) as ctx:
                gate("write")
            self.assertIn("No access grant designates this user",
                          str(ctx.exception))

        # designation would hold, scope missing
        gate = make_grant_check_gate("api", check_grant=lambda **q: True)
        with flask.Flask(__name__).test_request_context():
            flask.g.current_user = {"id": "u1"}
            flask.g.current_scopes = []
            with self.assertRaises(api_errors.ForbiddenError) as ctx:
                gate("write")
            self.assertIn("Token lacks 'migrations:write'",
                          str(ctx.exception))

    def test_gate_passes_with_scope_and_designation(self):
        """The lit-up path (#1183): both legs hold → gate passes."""
        from migrations.routes import make_grant_check_gate

        gate = make_grant_check_gate("api", check_grant=lambda **q: True)
        with flask.Flask(__name__).test_request_context():
            flask.g.current_user = {"id": "u1"}
            flask.g.current_scopes = ["migrations:write"]
            gate("write")

    def test_remote_check_caches_per_request_only(self):
        from migrations import routes as migration_routes

        calls: list[dict] = []

        class FakeGrants:
            def check(self, **query):
                calls.append(query)
                return True

        class FakeAuth:
            grants = FakeGrants()

        with flask.Flask(__name__).test_request_context():
            for _ in range(2):
                self.assertTrue(migration_routes._check_grant_remotely(
                    lambda: FakeAuth(),
                    grantee_type="user", grantee_id="u1",
                    resource_type="migrations", resource_id="api",
                    level="read",
                ))
            self.assertEqual(len(calls), 1)  # cached within the request
        with flask.Flask(__name__).test_request_context():
            self.assertTrue(migration_routes._check_grant_remotely(
                lambda: FakeAuth(),
                grantee_type="user", grantee_id="u1",
                resource_type="migrations", resource_id="api",
                level="read",
            ))
            self.assertEqual(len(calls), 2)  # fresh request, fresh check

    def test_remote_check_maps_auth_refusal_to_an_ops_hint(self):
        from campus_python import errors as client_errors

        from migrations import routes as migration_routes

        class FakeGrants:
            def check(self, **query):
                raise client_errors.AccessDeniedError(
                    error_description="not allowed")

        class FakeAuth:
            grants = FakeGrants()

        with (
            flask.Flask(__name__).test_request_context(),
            self.assertRaises(api_errors.ForbiddenError) as ctx,
        ):
            migration_routes._check_grant_remotely(
                lambda: FakeAuth(),
                grantee_type="user", grantee_id="u1",
                resource_type="migrations", resource_id="api",
                level="read",
            )
        self.assertIn("AUTH_GRANT_CHECK_CLIENT_IDS", str(ctx.exception))

    def test_remote_check_fails_closed_when_auth_is_unreachable(self):
        from migrations import routes as migration_routes

        class FakeGrants:
            def check(self, **query):
                raise ConnectionError("mesh down")

        class FakeAuth:
            grants = FakeGrants()

        with (
            flask.Flask(__name__).test_request_context(),
            self.assertRaises(api_errors.ServiceUnavailableError),
        ):
            migration_routes._check_grant_remotely(
                lambda: FakeAuth(),
                grantee_type="user", grantee_id="u1",
                resource_type="migrations", resource_id="api",
                level="read",
            )


if __name__ == "__main__":
    unittest.main()
