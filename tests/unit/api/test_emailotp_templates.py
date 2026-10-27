"""Tests for campus.api.emailotp_templates (#970).

The OTP email rendering moved here from campus.model.emailotp.template
so the model layer stays Flask-free even at call time. Rendered output
is exercised through flask.render_template_string under an app context,
the same way the emailotp route consumes it.
"""

import subprocess
import sys
import unittest


class TestEmailotpTemplates(unittest.TestCase):
    def test_body_renders_under_app_context(self):
        """Test that body() renders service and OTP through the template."""
        code = (
            "import flask\n"
            "from campus.api import emailotp_templates as template\n"
            "with flask.Flask(__name__).app_context():\n"
            "    print(template.subject('svc', '123456'))\n"
            "    print(template.body('svc', '123456'))\n"
            "    print(template.html_body('svc', '123456'))\n"
        )
        rendered = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        self.assertIn("Svc: Your OTP is 123456", rendered)
        self.assertIn("123456", rendered)
