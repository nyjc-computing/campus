"""campus.tests.integration.auth.test_first_login_provisioning

Regression tests for the post-#897 login-flow findings:

- #903: a first-time sign-in through the shared Google consent
  callback (the one hop every login flow passes) must provision the
  users record — tokens alone are not enough. The live failure: the
  device flow minted credentials for campus-admin@nyjc.edu.sg while
  the users table never gained a row, so the super-admin gate failed
  closed until break-glass provisioning.
- #904: the device page's JavaScript fetches absolute endpoint URLs —
  under the path-form route (/device/<code>) a relative ./users/me
  resolved to /device/users/me (404), rendering the "not logged in"
  error while the session was perfectly valid.

IMPORTANT: Lazy imports are required to avoid storage initialization
before test mode is configured (see AGENTS.md - Storage Initialization
Order).
"""

import unittest
from unittest import mock

import flask

from tests.integration.base import IntegrationTestCase

NEW_USER = "first.login@nyjc.edu.sg"


class FirstLoginProvisioningTestCase(IntegrationTestCase):
    """Harness: fresh service manager per class, schema auto-init."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.app = cls.service_manager.auth_app


class TestConsentCallbackProvisionsUser(FirstLoginProvisioningTestCase):
    """#903: handle_consent_callback provisions the users record."""

    def test_first_consent_creates_user_row(self):
        import campus.model
        from campus.auth import resources
        from campus.auth.oauth_proxy.google import get_proxy

        # The proxy reads its client registration from the vault —
        # seed before get_proxy().
        resources.vault["google"]["CLIENT_ID"] = "google-client-id"
        resources.vault["google"]["CLIENT_SECRET"] = "google-secret"
        proxy = get_proxy()

        authsession = resources.session["google"].new(
            expiry_seconds=600,
            client_id="google-client-id",
            redirect_uri="https://cli.test/cb",
            scopes=["read"],
            target="https://cli.test/cb",
        )

        fake_token = campus.model.OAuthToken(
            id="fake-access-token",
            refresh_token="fake-refresh",
            scopes=["read"],
            expires_in=3600,
        )
        userinfo = {
            "email": NEW_USER,
            "name": "First Login",
        }
        with (
            mock.patch.dict(
                "os.environ", {"WORKSPACE_DOMAIN": "nyjc.edu.sg"}
            ),
            mock.patch.object(
                proxy._oauth2,
                "exchange_code_for_token",
                return_value=fake_token,
            ),
            mock.patch.object(
                proxy._oauth2,
                "get_user_info",
                return_value=userinfo,
            ),
            self.app.test_request_context(),
        ):
            flask.session[proxy._session_key] = str(authsession.id)
            proxy.handle_consent_callback(
                state=str(authsession.id),
                code="google-code",
                scope="read",
            )

        # The provisioned record exists, keyed by the full email.
        row = resources.user[NEW_USER].get()
        self.assertEqual(str(row.email), NEW_USER)
        self.assertEqual(row.name, "First Login")


class TestDevicePageAbsoluteFetchUrls(FirstLoginProvisioningTestCase):
    """#904: the device page fetches absolute endpoint URLs."""

    def test_path_form_page_uses_absolute_fetch_urls(self):
        from campus.auth.resources.user import UsersResource
        UsersResource.init_storage()

        with self.app.test_client() as client:
            with client.session_transaction() as sess:
                sess["user_id"] = "someone@nyjc.edu.sg"
            response = client.get("/auth/v1/oauth/device/ABCD-EFGH")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertNotIn(
            "fetch('./users/me'", body,
            "relative fetch regressed: breaks under /device/<code>",
        )
        self.assertNotIn(
            "fetch('./device/authorize'", body,
            "relative fetch regressed: breaks under /device/<code>",
        )
        self.assertIn("/auth/v1/oauth/users/me", body)
        self.assertIn("/auth/v1/oauth/device/authorize", body)


if __name__ == "__main__":
    unittest.main()
