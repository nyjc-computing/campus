"""Unit tests for campus.common.devops.load_dotenv.

These tests verify that .env values are loaded into os.environ so that
env.get(), env.contains(), env.require() and attribute access all see
them consistently (issue #679).

Test Principles:
- Test interface contracts, not implementation
- Run against a temporary .env so the real working directory is untouched
- Keep tests independent and focused
"""

import os
import tempfile
import unittest

from campus.common import env
from campus.common.devops import load_dotenv

DOTENV_VAR = "CAMPUS_TEST_DOTENV_VAR"
DOTENV_QUOTED_VAR = "CAMPUS_TEST_DOTENV_QUOTED_VAR"


class TestLoadDotenv(unittest.TestCase):
    """load_dotenv() should write .env values to os.environ."""

    def setUp(self):
        """Run each test in a temp directory with a known .env file."""
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._orig_cwd = os.getcwd()
        self.addCleanup(os.chdir, self._orig_cwd)
        os.chdir(self._tmp.name)
        self.addCleanup(os.environ.pop, DOTENV_VAR, None)
        self.addCleanup(os.environ.pop, DOTENV_QUOTED_VAR, None)

    def _write_dotenv(self, content: str) -> None:
        with open(".env", "w") as f:
            f.write(content)

    def test_returns_false_when_no_env_file(self):
        """No .env in the working directory returns False and sets nothing."""
        self.assertFalse(load_dotenv())
        self.assertFalse(env.contains(DOTENV_VAR))

    def test_loads_values_into_os_environ(self):
        """Parsed .env values are visible to os.environ and env accessors."""
        self._write_dotenv(
            "# comment line\n"
            f"{DOTENV_VAR} = hello\n"
            "\n"
            f'{DOTENV_QUOTED_VAR} = "quoted value"\n'
        )
        self.assertTrue(load_dotenv())
        self.assertEqual(os.environ[DOTENV_VAR], "hello")
        self.assertEqual(env.get(DOTENV_VAR), "hello")
        self.assertEqual(env.get(DOTENV_QUOTED_VAR), "quoted value")
        self.assertTrue(env.contains(DOTENV_VAR))
        # Attribute access must agree with get() (no module-__dict__ shortcut)
        self.assertEqual(getattr(env, DOTENV_VAR), "hello")

    def test_require_sees_loaded_values(self):
        """env.require() succeeds for variables loaded from .env."""
        self._write_dotenv(f"{DOTENV_VAR}=hello\n")
        self.assertTrue(load_dotenv())
        env.require(DOTENV_VAR)

    def test_does_not_override_existing_environ(self):
        """Pre-existing environment variables take precedence over .env."""
        os.environ[DOTENV_VAR] = "from-environ"
        self._write_dotenv(f"{DOTENV_VAR}=from-dotenv\n")
        self.assertTrue(load_dotenv())
        self.assertEqual(os.environ[DOTENV_VAR], "from-environ")
        self.assertEqual(env.get(DOTENV_VAR), "from-environ")


if __name__ == "__main__":
    unittest.main()
