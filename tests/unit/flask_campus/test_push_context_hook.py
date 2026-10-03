"""Unit tests for the app-wide push_context hook's static-endpoint skip.

OAuthLoginManager.init_app registers campus.auth.push_context on the
whole app, so every request — stylesheets and scripts included — paid
the upstream auth lookup even though static assets never read g.user
(#689). Static endpoints (app-level and blueprint-level) now skip it.
"""

import unittest

import flask

from campus.flask_campus.login_manager import OAuthLoginManager


class _FakeAuth:
    def __init__(self):
        self.pushed: list[str] = []

    def push_context(self):
        self.pushed.append(flask.request.path)


class _FakeCampus:
    def __init__(self):
        self.auth = _FakeAuth()


class TestPushContextHook(unittest.TestCase):
    """Static asset requests stay out of the auth path."""

    def setUp(self):
        self.app = flask.Flask(__name__)
        self.app.secret_key = "test-secret"
        self.campus = _FakeCampus()
        manager = OAuthLoginManager(
            campus_client=self.campus  # type: ignore[arg-type]
        )
        manager.init_app(self.app)

        @self.app.get("/")
        def index():
            return "ok"

    def test_skips_app_static_assets(self):
        client = self.app.test_client()
        # The asset itself may 404 (harness has no static folder); the
        # point is that no auth lookup runs for the request.
        client.get("/static/style.css")
        self.assertEqual(self.campus.auth.pushed, [])

    def test_skips_blueprint_static_assets(self):
        admin_bp = flask.Blueprint("admin", __name__, static_folder="static")

        @admin_bp.get("/")
        def admin_home():
            return "ok"

        self.app.register_blueprint(admin_bp, url_prefix="/admin")
        client = self.app.test_client()
        client.get("/admin/static/style.css")
        self.assertEqual(self.campus.auth.pushed, [])

    def test_pushes_for_regular_routes(self):
        client = self.app.test_client()
        client.get("/")
        self.assertEqual(self.campus.auth.pushed, ["/"])


if __name__ == "__main__":
    unittest.main()
