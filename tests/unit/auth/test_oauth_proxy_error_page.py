"""Tests for the shared OAuth-proxy callback error page (#1127).

The proxy callbacks receive upstream error redirects as client-forgeable
query data. The error page must be clean (no raw payload echo) and
HTML-escaped (reflected-XSS surface, #1127); the full payload goes to
the server log instead (superadmin debug surface, policy §3).
"""

import unittest

import flask

from campus.auth.oauth_proxy.errors import oauth_error_response


class TestOAuthErrorPage(unittest.TestCase):
    """The callback error page must be clean and escaped (#1127)."""

    def setUp(self):
        self.app = flask.Flask(__name__)

    def _render(self, payload: dict) -> flask.Response:
        with self.app.test_request_context("/auth/v1/google/callback"):
            return oauth_error_response(payload)

    def test_returns_400_html_page(self):
        """Error callbacks render a 400 text/html page."""
        resp = self._render({"error": "access_denied"})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.mimetype, "text/html")

    def test_page_carries_error_code_and_guidance(self):
        """The page names the error code and tells the user to retry."""
        body = self._render({"error": "access_denied"}).get_data(as_text=True)
        self.assertIn("access_denied", body)
        self.assertIn("try signing in again", body)

    def test_payload_is_not_echoed(self):
        """No payload field beyond the error code reaches the page."""
        payload = {
            "error": "server_error",
            "error_description": "upstream blew up at db.internal",
            "error_uri": "https://accounts.example.com/errors/123",
            "state": "authsession_123",
            "code": "4/0Ab_5qn-leaked-authorization-code",
        }
        body = self._render(payload).get_data(as_text=True)
        for leaked in (
                "upstream blew up",
                "db.internal",
                "authsession_123",
                "4/0Ab_5qn-leaked-authorization-code",
                "All callback parameters",
        ):
            self.assertNotIn(leaked, body)

    def test_error_code_is_html_escaped(self):
        """A forged error code cannot inject markup."""
        body = self._render({"error": "<script>alert(1)</script>"}).get_data(
            as_text=True
        )
        self.assertNotIn("<script>", body)
        self.assertIn("&lt;script&gt;", body)


if __name__ == "__main__":
    unittest.main()
