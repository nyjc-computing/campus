import subprocess
import sys
import unittest


class TestModelImportWeight(unittest.TestCase):
    """Guard the flask-free import contract of the campus-model dist (#970).

    Importing campus.model must not drag in the Flask stack. The emailotp
    template rendering (the last flask usage in the model layer, lazy
    since #968) moved to campus.api.emailotp_templates, and campus.model
    is now the external campus-model distribution — its own boundary
    guard bans flask outright (even lazily). This consumer-side check
    validates the wheel the suite actually installs. Assertions run in
    a subprocess because this test process itself imports flask.
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
