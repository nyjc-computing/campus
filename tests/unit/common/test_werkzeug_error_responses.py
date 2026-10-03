"""Test werkzeug HTTPException response handling (#700).

Wrong-method and other client-error requests must surface with their own
status code, error code, and Campus error envelope — not as
500 INTERNAL_ERROR via the generic exception handler.
"""

import os
import unittest

# Set consistent test environment
os.environ["ENV"] = "development"

import flask
import werkzeug.exceptions

from campus.common.errors import handlers


def make_app() -> flask.Flask:
    """Create a Flask app wired with the Campus error handlers."""
    app = flask.Flask(__name__)
    handlers.init_app(app)

    @app.get("/only-get")
    def only_get():
        return {}

    @app.get("/abort-bad-request")
    def abort_bad_request():
        flask.abort(400)

    @app.get("/raise-internal")
    def raise_internal():
        raise werkzeug.exceptions.InternalServerError()

    return app


class TestWerkzeugErrorResponses(unittest.TestCase):
    """werkzeug HTTPExceptions must map to their own status codes."""

    def setUp(self):
        self.client = make_app().test_client()

    def test_wrong_method_returns_405_with_allow_header(self):
        """405 must carry its own status code and an Allow header (#700)."""
        resp = self.client.post("/only-get")
        self.assertEqual(resp.status_code, 405)
        self.assertIn("GET", resp.headers.get("Allow", ""))
        body = resp.get_json()
        self.assertEqual(body["error"]["code"], "METHOD_NOT_ALLOWED")
        self.assertIn("message", body["error"])
        self.assertIn("request_id", body["error"])

    def test_bad_request_returns_400_envelope(self):
        """400 must not be re-raised into the generic 500 handler."""
        resp = self.client.get("/abort-bad-request")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json()["error"]["code"], "BAD_REQUEST")

    def test_not_found_returns_empty_body_404(self):
        """404s remain the existing bare-object response (too numerous)."""
        resp = self.client.get("/no-such-route")
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.get_json(), {})

    def test_internal_server_error_returns_internal_error_envelope(self):
        """InternalServerError keeps the INTERNAL_ERROR envelope."""
        resp = self.client.get("/raise-internal")
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.get_json()["error"]["code"], "INTERNAL_ERROR")


if __name__ == "__main__":
    unittest.main()
