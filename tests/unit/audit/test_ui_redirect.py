"""Unit tests for the audit UI's old-URL redirects (campus.audit.ui_redirect).

The web UI moved to the campus-admin portal; this service answers its
old page URLs with a redirect (AUDIT_UI_URL set) or a notice page
(unset), and must never shadow the versioned API under /audit/v1.

File: tests/unit/audit/test_ui_redirect.py
"""

import os
import unittest
from unittest import mock

import flask

from campus.audit import ui_redirect

PORTAL = "https://campus-admin.example.edu"


def _make_app() -> tuple[flask.Flask, object]:
    """A bare app with just the redirect blueprint."""
    app = flask.Flask(__name__)
    app.register_blueprint(ui_redirect.create_blueprint())
    return app, app.test_client()


class TestRedirectToPortal(unittest.TestCase):
    """With AUDIT_UI_URL set, old UI URLs redirect to the portal."""

    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"AUDIT_UI_URL": PORTAL})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.app, self.client = _make_app()

    def test_landing_redirects(self):
        response = self.client.get("/audit/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], f"{PORTAL}/audit/")

    def test_page_paths_are_preserved(self):
        for path in ("/audit/traces", f"/audit/traces/{'a' * 32}", "/audit/keys"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302, path)
            self.assertEqual(response.headers["Location"], f"{PORTAL}{path}")

    def test_query_strings_are_preserved(self):
        response = self.client.get("/audit/traces?journey_id=j-1")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.headers["Location"],
            f"{PORTAL}/audit/traces?journey_id=j-1",
        )

    def test_v1_paths_never_redirect(self):
        """Unknown versioned-API routes 404; machines are not bounced."""
        response = self.client.get("/audit/v1/no-such-route/")
        self.assertEqual(response.status_code, 404)


class TestNoticePage(unittest.TestCase):
    """Without AUDIT_UI_URL, old links get an explanation, not a 404."""

    def setUp(self):
        patcher = mock.patch.dict(os.environ, {}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("AUDIT_UI_URL", None)
        self.app, self.client = _make_app()

    def test_landing_serves_notice(self):
        response = self.client.get("/audit/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("campus-admin", response.get_data(as_text=True))

    def test_deep_links_serve_notice_too(self):
        response = self.client.get("/audit/traces")
        self.assertEqual(response.status_code, 200)
        self.assertIn("moved", response.get_data(as_text=True))


class TestApiNotShadowed(unittest.TestCase):
    """The redirect blueprint must not swallow /audit/v1/*."""

    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"AUDIT_UI_URL": PORTAL})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_versioned_api_route_wins_over_redirect(self):
        app = flask.Flask(__name__)
        app.config["TESTING"] = True

        v1 = flask.Blueprint('audit_v1', __name__, url_prefix='/audit/v1')

        @v1.get("/health")
        def health():
            return {"status": "ok"}, 200

        app.register_blueprint(v1)
        app.register_blueprint(ui_redirect.create_blueprint())
        client = app.test_client()

        response = client.get("/audit/v1/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "ok")

        # An unknown API route 404s; it must never redirect a machine
        # caller to a portal page.
        response = client.get("/audit/v1/no-such-route/")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
