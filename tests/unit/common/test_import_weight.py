import subprocess
import sys
import unittest


class TestCommonImportWeight(unittest.TestCase):
    """Guard the lean-import contract of the campus.common namespace (#967).

    Importing campus.common must not drag in requests or bcrypt: after
    the http client moved to campus.audit.http (#970), nothing in the
    namespace's eager import chain pulls a third-party module any more.
    Assertions run in a subprocess because this test process may
    legitimately have those modules loaded by other imports.
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

    def test_common_http_is_gone(self):
        """Test that campus.common no longer exposes an http module (#970).

        Asserted via attribute access, not `import campus.common.http`:
        an import succeeds as an empty namespace package whenever a
        leftover campus/common/http directory exists on the path (e.g.
        untracked __pycache__), which says nothing about the package.
        """
        code = "import campus.common, sys\n" \
               "try:\n" \
               "    campus.common.http\n" \
               "except AttributeError:\n" \
               "    print('gone')\n" \
               "else:\n" \
               "    print('present')"
        stdout = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        self.assertEqual(stdout, "gone")
