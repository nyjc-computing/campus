"""campus.tests.integration.auth.test_super_admin_login_block

Integration tests for the 2026-11-24 superadmin-hardcode decision: the
hardcoded production super-admin identity (campus-admin@WORKSPACE_DOMAIN)
may not log in outside production. On ENV=development every identity
acceptance point refuses it with 403 — and creates nothing:

- the Google consent callback (the one hop every login flow shares,
  #903): no user row, no Google credential, no campus cookie;
- verify_login: defense in depth for a campus cookie minted before
  the callback-side block deployed — no code is bound;
- the device-flow bind (page POST fallback and the JSON endpoint):
  no device code is authorized.

The allow path on production is covered at unit level
(tests/unit/auth/test_super_admin_identity.py): a full production
login flow in-process would need the whole app re-env'ed for a single
case the guard expressses with one comparison.

IMPORTANT: Lazy imports are required to avoid storage initialization
before test mode is configured (see AGENTS.md - Storage Initialization
Order).
"""

import unittest
from unittest import mock

import flask

from campus.common.errors import api_errors
from tests.integration.base import IntegrationTestCase

SUPER_ADMIN = "campus-admin@nyjc.edu.sg"


class SuperAdminLoginBlockTestCase(IntegrationTestCase):
    """Harness: fresh service manager per class, schema auto-init."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.app = cls.service_manager.auth_app

    def _dev_env(self):
        """Pin the login block's environment explicitly.

        The block is a development-environment policy; the harness may
        leave ENV unset (which resolves to development) — patching pins
        that resolution against harness drift.
        """
        return mock.patch.dict(
            "os.environ",
            {"ENV": "development", "WORKSPACE_DOMAIN": "nyjc.edu.sg"},
        )


class TestConsentCallbackBlocksSuperAdmin(SuperAdminLoginBlockTestCase):
    """The shared Google callback refuses the super-admin identity."""

    def test_callback_rejects_and_creates_nothing(self):
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
            "email": SUPER_ADMIN,
            "name": "Campus Admin",
        }
        with (
            self._dev_env(),
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
            with self.assertRaises(api_errors.ForbiddenError):
                proxy.handle_consent_callback(
                    state=str(authsession.id),
                    code="google-code",
                    scope="read",
                )
            # The block lands before the campus cookie is set.
            self.assertIsNone(flask.session.get("user_id"))

        # Nothing was created: no users row, no Google credential.
        with (
            self._dev_env(),
            self.assertRaises(api_errors.NotFoundError),
        ):
            resources.user[SUPER_ADMIN].get()
        with (
            self._dev_env(),
            self.assertRaises(api_errors.NotFoundError),
        ):
            resources.credentials["google"][SUPER_ADMIN].get(
                "google-client-id"
            )


class TestVerifyLoginBlocksSuperAdmin(SuperAdminLoginBlockTestCase):
    """verify_login refuses a (stale) super-admin campus cookie."""

    def test_verify_login_returns_403(self):
        from campus.auth import resources

        authsession = resources.session["campus"].new(
            expiry_seconds=600,
            client_id="some-client-id",
            redirect_uri="https://cli.test/cb",
            scopes=["read"],
            target="https://cli.test/cb",
        )
        with self._dev_env(), self.app.test_client() as client:
            with client.session_transaction() as sess:
                sess["user_id"] = SUPER_ADMIN
            response = client.get(
                f"/auth/v1/verify_login?state={authsession.id}"
            )
        self.assertEqual(response.status_code, 403)


class TestDeviceBindBlocksSuperAdmin(SuperAdminLoginBlockTestCase):
    """The device-flow bind refuses the super-admin identity."""

    def test_device_authorize_endpoint_returns_403(self):
        from campus.auth import resources

        dc = resources.device_code.create(
            client_id="some-client-id",
            scopes=["read"],
        )
        with self._dev_env(), self.app.test_client() as client:
            response = client.post(
                "/auth/v1/oauth/device/authorize",
                json={"user_code": dc.user_code, "user_id": SUPER_ADMIN},
            )
        self.assertEqual(response.status_code, 403)
        # The device code stays pending and unbound.
        row = resources.device_code.get_by_user_code(dc.user_code)
        self.assertEqual(row.state, "pending")
        self.assertIsNone(row.user_id)

    def test_device_page_fallback_binds_nothing(self):
        from campus.auth import resources

        dc = resources.device_code.create(
            client_id="some-client-id",
            scopes=["read"],
        )
        with self._dev_env(), self.app.test_client() as client:
            with client.session_transaction() as sess:
                sess["user_id"] = SUPER_ADMIN
            response = client.post(
                "/auth/v1/oauth/device",
                data={"user_code": dc.user_code},
            )
        self.assertEqual(response.status_code, 403)
        row = resources.device_code.get_by_user_code(dc.user_code)
        self.assertEqual(row.state, "pending")
        self.assertIsNone(row.user_id)


if __name__ == "__main__":
    unittest.main()
