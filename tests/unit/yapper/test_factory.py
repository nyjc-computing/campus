"""Factory tests for campus.yapper.create() (#970 phase 2).

yapper is self-contained: it resolves its event database URI from an
argument, a caller-provided callable, or the environment — and it must
never import campus.auth (that lazy import was the yapper<->auth cycle;
the AST contract test in tests/unit/test_package_boundaries.py guards
it statically). These assertions run in subprocesses so the surrounding
test process cannot mask missing or extra imports, and so environment
variables (STORAGE_MODE, YAPPERDB_URI) are controlled per test.
"""

import os
import subprocess
import sys
import tempfile
import unittest


class TestCreateUriResolution(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".sqlite", prefix="yapperfactory_")
        os.close(fd)
        self.db_path = self.db_path.replace("\\", "/")

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _run(self, code: str, **env_overrides) -> str:
        env = dict(os.environ)
        env.update(
            CLIENT_ID="test-client",
            CLIENT_SECRET="test-secret",
            ENV="testing",
        )
        # The outer process (test harness) may set these; isolate.
        env.pop("YAPPERDB_URI", None)
        env.pop("STORAGE_MODE", None)
        env.pop("DEPLOY", None)
        env.update(env_overrides)
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=True,
            env=env,
        )
        return result.stdout.strip()

    def test_explicit_db_uri_wins(self):
        """Test that db_uri argument configures SQLite in test mode."""
        out = self._run(
            "import campus.yapper, sys\n"
            f"y = campus.yapper.create(db_uri=r'{self.db_path}')\n"
            "print(type(y).__name__, 'campus.auth' in sys.modules)\n",
            STORAGE_MODE="1",
        )
        backend, auth_loaded = out.split()
        self.assertEqual(backend, "SQLiteYapper")
        self.assertEqual(auth_loaded, "False")

    def test_provider_is_used(self):
        """Test that db_uri_provider supplies the URI and campus.auth stays unimported."""
        out = self._run(
            "import campus.yapper, sys, os\n"
            f"y = campus.yapper.create(db_uri_provider=lambda: r'{self.db_path}')\n"
            "print(type(y).__name__, 'campus.auth' in sys.modules,"
            " os.path.getsize(r'" + self.db_path + "') > 0)\n",
            STORAGE_MODE="1",
        )
        backend, auth_loaded, db_initialized = out.split()
        self.assertEqual(backend, "SQLiteYapper")
        self.assertEqual(auth_loaded, "False")
        self.assertEqual(db_initialized, "True")

    def test_env_fallback_for_bare_create(self):
        """Test that bare create() (api routes) falls back to YAPPERDB_URI env."""
        out = self._run(
            "import campus.yapper, sys\n"
            "y = campus.yapper.create()\n"
            "print(type(y).__name__, 'campus.auth' in sys.modules)\n",
            STORAGE_MODE="1",
            YAPPERDB_URI=self.db_path,
        )
        backend, auth_loaded = out.split()
        self.assertEqual(backend, "SQLiteYapper")
        self.assertEqual(auth_loaded, "False")

    def test_test_mode_without_uri_raises_before_network(self):
        """Test that test mode with no URI raises instead of contacting the remote vault."""
        code = (
            "import campus.yapper\n"
            "campus.yapper.create()\n"
        )
        env = dict(os.environ)
        env.update(
            CLIENT_ID="test-client",
            CLIENT_SECRET="test-secret",
            ENV="testing",
            STORAGE_MODE="1",
        )
        env.pop("YAPPERDB_URI", None)
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("STORAGE_MODE=1", result.stderr)
        self.assertNotIn("campus.auth", result.stderr)
