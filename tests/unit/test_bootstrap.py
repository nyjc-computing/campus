"""campus.bootstrap — the shared startup storage-init policy (#1103).

run_init_storage must skip in production (the storage layer blocks
init_from_model there; campus.audit's first prod boot crash-looped on
an unguarded call, #1100), run self-healing init anywhere else, and
never let a failed init abort service startup.
"""

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
