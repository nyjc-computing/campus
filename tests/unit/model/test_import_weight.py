import subprocess
import sys
import unittest


class TestModelImportWeight(unittest.TestCase):
    """Guard the flask-free import contract of campus.model (#968).

    Importing campus.model must not drag in the Flask stack: the only
    flask usage in the model layer is render_template_string inside the
    emailotp template, which imports lazily at call time. Assertions run
    in a subprocess because this test process itself imports flask.
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

    def test_otp_template_renders_under_app_context(self):
        """Test that the lazy flask import still renders OTP templates."""
        code = (
            "import flask\n"
            "from campus.model.emailotp import template\n"
            "with flask.Flask(__name__).app_context():\n"
            "    print(template.body('svc', '123456'))\n"
        )
        rendered = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        self.assertIn("123456", rendered)
        self.assertIn("svc", rendered)
