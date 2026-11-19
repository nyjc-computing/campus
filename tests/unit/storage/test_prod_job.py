"""Test the break-glass migration job entrypoint (campus-deploy#4).

Covers the per-scope context swap (POSTGRESDB_URI/MONGODB_URI set in
turn, so each scope's ledger lands in that service's DB, #1104), the
plan/apply argv shapes, --up-to passthrough, stop-on-first-failure,
missing-variable misconfiguration, and the mode guard. The runner is
faked — no database, no secrets.
"""

import os
import unittest
from unittest.mock import patch


class TestProdJob(unittest.TestCase):
    """migrations.prod_job.main() over a faked runner."""

    def _env(self, **overrides):
        env = {
            "MIGRATE_JOB_AUTH_POSTGRESDB_URI": "pg-auth",
            "MIGRATE_JOB_API_POSTGRESDB_URI": "pg-api",
            "MIGRATE_JOB_AUDIT_POSTGRESDB_URI": "pg-audit",
        }
        env.pop("MIGRATION_BACKUP_BUCKET", None)
        env.update(overrides)
        return env

    def _run(self, fake_main, env):
        from migrations import prod_job
        with patch.dict(os.environ, env, clear=False), \
                patch("migrations.runner.main", side_effect=fake_main):
            return prod_job.main()

    def test_plan_runs_status_per_scope_with_context_swap(self):
        calls = []

        def fake_main(argv, *args, **kwargs):
            calls.append((argv, os.environ.get("POSTGRESDB_URI")))
            return 0

        code = self._run(fake_main, self._env())
        self.assertEqual(code, 0)
        self.assertEqual([c[0] for c in calls], [
            ["--db", "auth", "status"],
            ["--db", "api", "status"],
            ["--db", "audit", "status"],
        ])
        # the context was swapped per scope: each run saw its own URI,
        # and audit (the last scope) won the env
        self.assertEqual(
            [c[1] for c in calls], ["pg-auth", "pg-api", "pg-audit"])

    def test_apply_mode_passes_up_to(self):
        calls = []

        def fake_main(argv, *args, **kwargs):
            calls.append(argv)
            return 0

        code = self._run(
            fake_main,
            self._env(MIGRATE_JOB_MODE="apply", MIGRATE_JOB_UP_TO="008"))
        self.assertEqual(code, 0)
        self.assertEqual(calls, [
            ["--db", "auth", "apply", "--up-to", "008"],
            ["--db", "api", "apply", "--up-to", "008"],
            ["--db", "audit", "apply", "--up-to", "008"],
        ])

    def test_stops_on_first_failing_scope(self):
        def fake_main(argv, *args, **kwargs):
            return 1 if argv[1] == "api" else 0

        code = self._run(fake_main, self._env(MIGRATE_JOB_MODE="apply"))
        self.assertEqual(code, 1)

    def test_missing_scope_uri_is_misconfiguration(self):
        calls = []

        def fake_main(argv, *args, **kwargs):
            calls.append(argv)
            return 0

        env = self._env()
        del env["MIGRATE_JOB_API_POSTGRESDB_URI"]
        code = self._run(fake_main, env)
        self.assertEqual(code, 2)
        # auth ran (its URI was present); the job stopped before api
        self.assertEqual(calls, [["--db", "auth", "status"]])

    def test_invalid_mode_refuses_before_any_run(self):
        def fake_main(argv, *args, **kwargs):
            raise AssertionError("runner must not run for a bad mode")

        code = self._run(fake_main, self._env(MIGRATE_JOB_MODE="boom"))
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
