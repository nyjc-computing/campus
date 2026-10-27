import subprocess
import sys
import unittest


class TestModelImportWeight(unittest.TestCase):
    """Guard the flask-free import contract of campus.model (#968, #970).

    Importing campus.model must not drag in the Flask stack. The emailotp
    template rendering (the last flask usage in the model layer, lazy
    since #968) moved to campus.api.emailotp_templates, so the model
    layer is flask-free even at call time. Assertions run in a
    subprocess because this test process itself imports flask.
    """

    def _modules_loaded_by(self, stmt: str) -> set[str]:
        result = subprocess.run(
            [sys.executable, "-c", stmt],
            capture_output=True,
            text=True,
            check=True,
        )
        return set(result.stdout.strip().split(","))

    def test_import_model_is_flask_free(self):
        """Test that importing campus.model loads neither flask nor jinja2."""
        loaded = self._modules_loaded_by(
            "import campus.model, sys; print(','.join(sorted(sys.modules)))"
        )
        self.assertNotIn("flask", loaded)
        self.assertNotIn("jinja2", loaded)

    def test_emailotp_template_module_is_gone(self):
        """Test that campus.model.emailotp no longer exposes a template module.

        Asserted via attribute access, not import: an import succeeds as
        an empty namespace package whenever a leftover directory exists
        on the path (untracked __pycache__), which says nothing about
        the package.
        """
        code = (
            "import campus.model.emailotp, sys\n"
            "try:\n"
            "    campus.model.emailotp.template\n"
            "except AttributeError:\n"
            "    print('gone')\n"
            "else:\n"
            "    print('present')"
        )
        stdout = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        self.assertEqual(stdout, "gone")
