"""HTTP contract tests for the Google login prompt policy (#844).

The identity authorize endpoint (/auth/v1/google/authorize) must send
Google prompt=select_account by default: a browser that still holds a
Google session after logging out of a campus app would otherwise be
silently re-authenticated as the previous user on the next app's
login. An explicit prompt query param still overrides, and the
integration connect flow keeps its own forced prompt=consent (covered
in test_integrations.py).
"""

import unittest
from urllib.parse import parse_qs, urlparse

from tests.fixtures import services

APP_TARGET = "https://prompt.example.com/finalize_login"


class TestGoogleLoginPromptContract(unittest.TestCase):
    """HTTP contract tests for the identity login prompt default."""

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager()
        cls.manager.initialize()
        cls.app = cls.manager.auth_app

    @classmethod
    def tearDownClass(cls):
        cls.manager.cleanup()

    def setUp(self):
        self.manager.clear_test_data()

        assert self.app
        self.client = self.app.test_client()

        # The Google proxy loads its OAuth client from the vault on
        # every request; the harness does not seed the "google" label,
        # so seed test credentials here (no network calls happen — the
        # endpoint only builds the authorization redirect).
        from campus.auth import resources as auth_resources
        auth_resources.vault["google"]["CLIENT_ID"] = "test-google-client-id"
        auth_resources.vault["google"]["CLIENT_SECRET"] = "test-google-client-secret"

    def test_google_authorize_defaults_to_select_account(self):
        """#844: identity login always stops at Google's account chooser."""
        response = self.client.get(
            "/auth/v1/google/authorize",
            query_string={"target": APP_TARGET},
        )

        self.assertEqual(response.status_code, 302)
        params = parse_qs(urlparse(response.headers["Location"]).query)
        self.assertEqual(params["prompt"], ["select_account"])

    def test_google_authorize_explicit_prompt_overrides(self):
        """An explicit prompt query param overrides the default."""
        response = self.client.get(
            "/auth/v1/google/authorize",
            query_string={"target": APP_TARGET, "prompt": "login"},
        )

        self.assertEqual(response.status_code, 302)
        params = parse_qs(urlparse(response.headers["Location"]).query)
        self.assertEqual(params["prompt"], ["login"])
