"""campus.bootstrap — the shared startup storage-init policy (#1103).

run_init_storage must skip in production (the storage layer blocks
init_from_model there; campus.audit's first prod boot crash-looped on
an unguarded call, #1100), run self-healing init anywhere else, and
never let a failed init abort service startup.
"""

import os
import unittest

from campus import bootstrap
from campus.common import env


class TestRunInitStorage(unittest.TestCase):
    """Behavior contract of the one true init-storage guard."""

    def setUp(self) -> None:
        self._original_env = env.ENV

    def tearDown(self) -> None:
        env.set("ENV", self._original_env)

    def test_production_skips_init_fn(self) -> None:
        """ENV=production: the init callable never runs, nothing raises."""
        calls: list[int] = []
        env.set("ENV", env.PRODUCTION)
        bootstrap.run_init_storage(
            lambda: calls.append(1),
            what="the widget table",
            recovery="python scripts/init_storage.py --service api",
        )
        self.assertEqual(calls, [])

    def test_development_runs_init_fn(self) -> None:
        """Outside production the init callable runs exactly once."""
        calls: list[int] = []
        env.set("ENV", env.DEVELOPMENT)
        bootstrap.run_init_storage(
            lambda: calls.append(1),
            what="the widget table",
            recovery="python scripts/init_storage.py --service api",
        )
        self.assertEqual(calls, [1])

    def test_init_failure_is_logged_not_raised(self) -> None:
        """A failed init logs loudly with the recovery path and returns.

        Startup must survive one broken resource: other resources,
        seeding and blueprint registration still run, and the missing
        table surfaces at request time with its own error.
        """
        env.set("ENV", env.DEVELOPMENT)

        def broken() -> None:
            raise RuntimeError("storage backend unreachable")

        with self.assertLogs("campus.bootstrap", level="ERROR") as captured:
            bootstrap.run_init_storage(
                broken,
                what="the widget table",
                recovery="python scripts/init_storage.py --service api",
            )
        self.assertTrue(
            any("Failed to initialize the widget table" in line
                and "python scripts/init_storage.py --service api" in line
                for line in captured.output),
            captured.output,
        )


if __name__ == "__main__":
    unittest.main()


class TestValidateRequiredEnv(unittest.TestCase):
    """Boot-time required-var validation (#1108): production fails
    loudly on missing/empty vars; anywhere else it never blocks."""

    def setUp(self) -> None:
        self._original_env = env.ENV

    def tearDown(self) -> None:
        env.set("ENV", self._original_env)

    def test_production_missing_vars_raise(self) -> None:
        env.set("ENV", env.PRODUCTION)
        with self.assertRaises(OSError) as caught:
            bootstrap.validate_required_env(
                "campus.auth", ("CLIENT_ID", "CLIENT_SECRET"))
        message = str(caught.exception)
        self.assertIn("campus.auth", message)
        self.assertIn("CLIENT_ID", message)
        self.assertIn("CLIENT_SECRET", message)
        self.assertIn("#1108", message)

    def test_production_empty_var_counts_as_missing(self) -> None:
        # an unquoted Railway reference resolves EMPTY (playbook §7.7)
        env.set("ENV", env.PRODUCTION)
        original = os.environ.get("PUBLIC_URL")
        env.set("PUBLIC_URL", "")
        try:
            with self.assertRaises(OSError) as caught:
                bootstrap.validate_required_env(
                    "campus.api", ("PUBLIC_URL",))
            self.assertIn("PUBLIC_URL", str(caught.exception))
        finally:
            if original is None:
                env.delete("PUBLIC_URL")
            else:
                env.set("PUBLIC_URL", original)

    def test_production_all_set_passes(self) -> None:
        env.set("ENV", env.PRODUCTION)
        originals = {var: os.environ.get(var)
                     for var in ("CLIENT_ID", "MONGODB_URI")}
        env.set("CLIENT_ID", "uid-client-test")
        env.set("MONGODB_URI", "mongodb://test")
        try:
            bootstrap.validate_required_env(
                "campus.auth", ("CLIENT_ID", "MONGODB_URI"))
        finally:
            for var, original in originals.items():
                if original is None:
                    env.delete(var)
                else:
                    env.set(var, original)

    def test_development_never_raises(self) -> None:
        env.set("ENV", env.DEVELOPMENT)
        bootstrap.validate_required_env(
            "campus.auth", ("DEFINITELY_NOT_SET_VAR_XYZ",))

    def test_every_declared_var_exists_in_production_ground_truth(
            self) -> None:
        # Pins the declaration keys against the 2026-11-17 prod
        # standup (docs/prod-rollout.md §2): every var in the matrix
        # is one prod actually sets, so the enforcement can never
        # crash-loop a correctly-configured deployment.
        from campus.bootstrap import REQUIRED_ENV_VARS
        self.assertEqual(
            REQUIRED_ENV_VARS["campus.auth"],
            ("CLIENT_ID", "CLIENT_SECRET", "SECRET_KEY",
             "MONGODB_URI", "POSTGRESDB_URI", "AUDIT_API_KEY",
             "AUTH_SUPER_ADMIN", "AUTH_OPERATOR_CLIENT_IDS",
             "WORKSPACE_DOMAIN", "PUBLIC_URL"),
        )
        self.assertEqual(
            REQUIRED_ENV_VARS["campus.api"],
            ("CLIENT_ID", "CLIENT_SECRET", "MONGODB_URI",
             "POSTGRESDB_URI", "BUCKET_ENDPOINT", "BUCKET_NAME",
             "BUCKET_REGION", "BUCKET_ACCESS_KEY_ID",
             "BUCKET_SECRET_ACCESS_KEY", "AUDIT_API_KEY",
             "PUBLIC_URL"),
        )
        self.assertEqual(
            REQUIRED_ENV_VARS["campus.audit"],
            ("POSTGRESDB_URI", "AUDIT_OPERATOR_API_KEY",
             "SECRET_KEY", "PUBLIC_URL"),
        )
