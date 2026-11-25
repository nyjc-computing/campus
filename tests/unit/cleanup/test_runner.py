"""Unit tests for the cleanup run orchestration (campus.cleanup.run).

One ledger row per run, the advisory-lock skip, per-scope env wiring,
and the exit-code contract — against a fake ledger connection and
stub jobs. No real database.
"""

import os
import unittest
from unittest.mock import patch


class FakeCursor:
    """Records executed statements; programmable fetches."""

    def __init__(self, fetchone_results=None):
        self.executed = []
        self._fetchone_results = list(fetchone_results or [])

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        if self._fetchone_results:
            return self._fetchone_results.pop(0)
        return None

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class FakeConn:
    """Minimal ledger connection: one shared cursor."""

    def __init__(self, cursor=None):
        self.cursor_obj = cursor or FakeCursor()
        self.commits = 0

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.commits += 1

    def close(self):
        pass


def _stub_job(name, scope, *, rows=0, error=None):
    """A Job whose callable records the process env it ran under."""
    from campus.cleanup import Job

    calls = []

    def sweep():
        calls.append({
            "POSTGRESDB_URI": os.environ.get("POSTGRESDB_URI"),
            "MONGODB_URI": os.environ.get("MONGODB_URI"),
            "MONGODB_NAME": os.environ.get("MONGODB_NAME"),
        })
        if error is not None:
            raise error
        return rows

    return Job(name=name, scope=scope, sweep=sweep), calls


class TestRun(unittest.TestCase):
    """run(): ledger lifecycle, lock skip, env wiring, exit codes."""

    def _conn(self, lock_available=True):
        # one lock poll per run; the release uses no fetchone
        return FakeConn(FakeCursor(fetchone_results=[(lock_available,)]))

    def _wire_fake_scopes(self):
        """Swap SCOPES for a test-local mapping with fake source vars.

        Keeps scope-env tests from reading (or leaving behind) the real
        CLEANUP_JOB_* variables; test_scope_env_wiring overrides this
        with the real mapping.
        """
        from campus import cleanup

        fake = {
            "audit": {"POSTGRESDB_URI": "TEST_CLEANUP_AUDIT_PG"},
            "auth": {
                "POSTGRESDB_URI": "TEST_CLEANUP_AUTH_PG",
                "MONGODB_URI": "TEST_CLEANUP_AUTH_MONGO",
                "MONGODB_NAME": "TEST_CLEANUP_AUTH_NAME",
            },
        }
        sources = {source for mapping in fake.values()
                   for source in mapping.values()}
        for source in sources:
            os.environ[source] = "wire-test-value"
        old_scopes = cleanup.SCOPES
        cleanup.SCOPES = fake

        def _restore():
            cleanup.SCOPES = old_scopes
            for source in sources:
                os.environ.pop(source, None)
            for var in ("POSTGRESDB_URI", "MONGODB_URI", "MONGODB_NAME"):
                os.environ.pop(var, None)

        self.addCleanup(_restore)

    def test_success_writes_one_ledger_row(self):
        from campus.cleanup import run

        self._wire_fake_scopes()
        job_a, calls_a = _stub_job("t.a", "audit", rows=3)
        job_b, calls_b = _stub_job("t.b", "auth", rows=5)
        conn = self._conn()
        exit_code = run(
            ledger_conn=conn, job_list=(job_a, job_b))
        self.assertEqual(exit_code, 0)
        self.assertEqual(len(calls_a), 1)
        self.assertEqual(len(calls_b), 1)
        inserts = [(sql, params) for sql, params in conn.cursor_obj.executed
                   if "INSERT INTO" in sql]
        updates = [(sql, params) for sql, params in conn.cursor_obj.executed
                   if "UPDATE" in sql]
        self.assertEqual(len(inserts), 1)
        self.assertEqual(inserts[0][1][2], "running")
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0][1][1], "success")
        # jobs detail + total rows affected land on the ledger row
        self.assertEqual(updates[0][1][3], 8)
        self.assertIsNone(updates[0][1][4])  # error column stays NULL

    def test_job_failure_continues_and_exits_nonzero(self):
        from campus.cleanup import run

        self._wire_fake_scopes()
        job_bad, calls_bad = _stub_job(
            "t.bad", "audit", error=RuntimeError("boom"))
        job_good, calls_good = _stub_job("t.good", "audit", rows=1)
        conn = self._conn()
        exit_code = run(
            ledger_conn=conn, job_list=(job_bad, job_good))
        self.assertEqual(exit_code, 1)
        # the failing job did not stop the later one
        self.assertEqual(len(calls_bad), 1)
        self.assertEqual(len(calls_good), 1)
        updates = [(sql, params) for sql, params in conn.cursor_obj.executed
                   if "UPDATE" in sql]
        self.assertEqual(updates[0][1][1], "failed")
        self.assertIn("boom", updates[0][1][4])

    def test_lock_busy_skips_cleanly(self):
        from campus.cleanup import run

        job, calls = _stub_job("t.a", "audit", rows=1)
        conn = self._conn(lock_available=False)
        with patch("campus.cleanup.LOCK_WAIT_SECONDS", 0.1):
            exit_code = run(ledger_conn=conn, job_list=(job,))
        self.assertEqual(exit_code, 0)  # a skip is a success, not a failure
        self.assertEqual(calls, [])  # nothing ran
        inserts = [(sql, params) for sql, params in conn.cursor_obj.executed
                   if "INSERT INTO" in sql]
        self.assertEqual(inserts, [])  # no ledger row for a skipped run

    def test_unknown_job_name_raises_before_connecting(self):
        from campus.cleanup import run

        job, _ = _stub_job("t.a", "audit")
        with self.assertRaises(ValueError) as caught:
            run(selected=("nope",), ledger_conn=None, job_list=(job,))
        self.assertIn("nope", str(caught.exception))

    def test_unknown_scope_raises(self):
        from campus.cleanup import run

        job, _ = _stub_job("t.bad", "not-a-scope")
        with self.assertRaises(ValueError):
            run(ledger_conn=self._conn(), job_list=(job,))

    def test_scope_env_wiring(self):
        """Jobs run with the storage env pointed at their scope's
        service databases; undeclared vars are dropped."""
        from campus.cleanup import run

        job_audit, calls_audit = _stub_job("t.audit", "audit")
        job_auth, calls_auth = _stub_job("t.auth", "auth")
        conn = self._conn()
        audit_uri = "postgres://audit-test"
        auth_pg = "postgres://auth-test"
        auth_mongo = "mongodb://auth-test"
        auth_name = "campus_auth"
        os.environ["CLEANUP_JOB_AUDIT_POSTGRESDB_URI"] = audit_uri
        os.environ["CLEANUP_JOB_AUTH_POSTGRESDB_URI"] = auth_pg
        os.environ["CLEANUP_JOB_AUTH_MONGODB_URI"] = auth_mongo
        os.environ["CLEANUP_JOB_AUTH_MONGODB_NAME"] = auth_name
        try:
            exit_code = run(
                ledger_conn=conn, job_list=(job_audit, job_auth))
        finally:
            for var in ("CLEANUP_JOB_AUDIT_POSTGRESDB_URI",
                        "CLEANUP_JOB_AUTH_POSTGRESDB_URI",
                        "CLEANUP_JOB_AUTH_MONGODB_URI",
                        "CLEANUP_JOB_AUTH_MONGODB_NAME",
                        "POSTGRESDB_URI", "MONGODB_URI", "MONGODB_NAME"):
                os.environ.pop(var, None)
        self.assertEqual(exit_code, 0)
        self.assertEqual(calls_audit[0]["POSTGRESDB_URI"], audit_uri)
        # the audit scope drops the Mongo env: it declares no Mongo
        self.assertIsNone(calls_audit[0]["MONGODB_URI"])
        self.assertIsNone(calls_audit[0]["MONGODB_NAME"])
        self.assertEqual(calls_auth[0]["POSTGRESDB_URI"], auth_pg)
        self.assertEqual(calls_auth[0]["MONGODB_URI"], auth_mongo)
        # the Mongo backend resolves the database name separately
        self.assertEqual(calls_auth[0]["MONGODB_NAME"], auth_name)

    def test_empty_selection_is_a_success(self):
        from campus.cleanup import run

        job, calls = _stub_job("t.a", "audit")
        exit_code = run(selected=[], ledger_conn=None, job_list=(job,))
        self.assertEqual(exit_code, 0)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
