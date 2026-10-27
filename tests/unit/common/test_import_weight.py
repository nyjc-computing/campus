import subprocess
import sys
import unittest


class TestCommonImportWeight(unittest.TestCase):
    """Guard the lazy-import contract of the campus.common namespace (#967).

    Importing campus.common must not drag in requests (via the lazy http
    submodule) or bcrypt (reachable only through http's import of
    utils.secret). The assertions run in a subprocess because this test
    process may legitimately have those modules loaded by other imports.
    """

    def _modules_loaded_by(self, stmt: str) -> set[str]:
        result = subprocess.run(
            [sys.executable, "-c", stmt],
            capture_output=True,
            text=True,
            check=True,
        )
        return set(result.stdout.strip().split(","))

    def test_import_common_is_lean(self):
        """Test that importing campus.common loads neither requests nor bcrypt."""
        loaded = self._modules_loaded_by(
            "import campus.common, sys; print(','.join(sorted(sys.modules)))"
        )
        self.assertNotIn("requests", loaded)
        self.assertNotIn("bcrypt", loaded)

    def test_lazy_http_getattr(self):
        """Test that `from campus.common import http` still resolves the module."""
        code = (
            "from campus.common import http;"
            "import sys;"
            "print(http.__name__, 'requests' in sys.modules)"
        )
        stdout = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        module_name, requests_loaded = stdout.split()
        self.assertEqual(module_name, "campus.common.http")
        self.assertEqual(requests_loaded, "True")
