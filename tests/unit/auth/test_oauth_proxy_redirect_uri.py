"""The oauth_proxy redirect_uri must name a route that exists (#1327).

The proxies build redirect_uri at runtime from the canonical origin.
The github and discord proxies used to build /auth/<provider>/callback
while the blueprints mount under the auth blueprint's /auth/v1 prefix:
GitHub/Discord bounced the browser to a 404 and the code exchange never
ran. Google already built the /auth/v1 path. These tests mount the
proxy blueprints the way the auth app does and require each proxy's
redirect_uri to resolve in that route map.
"""

import os
import unittest
from urllib.parse import urlparse

import flask
from werkzeug.exceptions import NotFound

from campus.auth.oauth_proxy import discord, github

PUBLIC_URL = "https://campus.test"


class TestProxyRedirectURIIsARoute(unittest.TestCase):
    """github/discord redirect_uris must resolve against the real mount."""

    def setUp(self):
        self._saved_public_url = os.environ.get("PUBLIC_URL")
        os.environ["PUBLIC_URL"] = PUBLIC_URL
        self.app = flask.Flask(__name__)
        # Mirror the auth app's mount: oauth_proxy.init_app registers
        # under a parent blueprint with the /auth/v1 prefix
        # (campus/auth/__init__.py).
        parent = flask.Blueprint("auth", __name__, url_prefix="/auth/v1")
        github.init_app(parent)
        discord.init_app(parent)
        self.app.register_blueprint(parent)
        self.adapter = self.app.url_map.bind("campus.test")

    def tearDown(self):
        if self._saved_public_url is None:
            os.environ.pop("PUBLIC_URL", None)
        else:
            os.environ["PUBLIC_URL"] = self._saved_public_url

    def _redirect_uri_path(self, module) -> str:
        return urlparse(module.proxy._get_redirect_uri()).path

    def test_github_redirect_uri_is_a_registered_route(self):
        path = self._redirect_uri_path(github)
        self.assertEqual(path, "/auth/v1/github/callback")
        self.adapter.match(path)  # NotFound if the route vanished

    def test_discord_redirect_uri_is_a_registered_route(self):
        path = self._redirect_uri_path(discord)
        self.assertEqual(path, "/auth/v1/discord/callback")
        self.adapter.match(path)  # NotFound if the route vanished

    def test_legacy_paths_are_not_routes(self):
        """The pre-#1327 paths must never come back as redirect targets."""
        with self.assertRaises(NotFound):
            self.adapter.match("/auth/github/callback")
        with self.assertRaises(NotFound):
            self.adapter.match("/auth/discord/callback")


if __name__ == "__main__":
    unittest.main()
