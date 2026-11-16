"""HTTP contract tests for per-integration upstream OAuth (#733 Phase 1).

Covers the three new surfaces from the approved #730 design:

- Connect flow (§2.3/§2.6): GET /auth/v1/google/<integration>/authorize
  starts a consent flow bound to the browser's campus session, with the
  target allowlisted against the vault CONNECT_TARGETS, the scope ask
  capped at the vault SCOPES set and consent forced. The callback
  stores the credential under the namespaced provider and binds it to
  the session user (403 on mismatch).
- Broker selector (§2.4/§2.5): POST /auth/v1/broker/<provider>/<integration>/
  releases the integration token to bridge-flagged confidential clients
  whose upstream_scopes carry a NON-EMPTY entry for the namespaced
  provider — absent entry denies even without min_scopes — capped by
  the vault SCOPES set.
- Audit: campus.integrations.connect / connect_fail carry provider,
  integration, user_id and scopes, never token values.

The identity routes are untouched; their existing contract tests are
the regression gate. No network calls happen: the Google token/userinfo
legs are patched at the OAuth2 scheme.
"""

import unittest
from unittest import mock
from urllib.parse import parse_qs, urlparse

import campus.model
from campus.common import env, schema
from campus.common.errors import api_errors
from campus.webauth.oauth2 import authorization_code as oauth2_scheme
from tests.fixtures import services
from tests.fixtures.tokens import get_basic_auth_headers

USER_ID = schema.UserID("integrations@nyjc.edu.sg")
OTHER_USER_ID = schema.UserID("someoneelse@nyjc.edu.sg")
PROFILE_CALLBACK = "https://profile.example/profile/integrations/classroom/callback"
GOOGLE_CLASSROOM_CLIENT_ID = "test-classroom-client-id"
CLASSROOM_COURSES = "https://www.googleapis.com/auth/classroom.courses.readonly"
CLASSROOM_ROSTERS = "https://www.googleapis.com/auth/classroom.rosters"
USERINFO_EMAIL = "https://www.googleapis.com/auth/userinfo.email"
USERINFO_PROFILE = "https://www.googleapis.com/auth/userinfo.profile"
# The seeded vault cap: 2 MVP scopes + the userinfo pair (a trimmed
# stand-in for the full 9-scope dev seed; the cap semantics are the same)
CLASSROOM_SCOPES = [
    CLASSROOM_COURSES,
    CLASSROOM_ROSTERS,
    USERINFO_EMAIL,
    USERINFO_PROFILE,
]
SCOPE_OUTSIDE_CAP = "https://www.googleapis.com/auth/drive"


def _seed_classroom_vault(**overrides: str) -> None:
    """Seed the google.classroom vault label (harness clears per test)."""
    from campus.auth import resources as auth_resources
    keys = {
        "CLIENT_ID": GOOGLE_CLASSROOM_CLIENT_ID,
        "CLIENT_SECRET": "test-classroom-client-secret",
        "SCOPES": " ".join(CLASSROOM_SCOPES),
        "CONNECT_TARGETS": "https://profile.example",
    }
    keys.update(overrides)
    for key, value in keys.items():
        if value is not None:
            auth_resources.vault["google.classroom"][key] = value


def _fake_exchange(
        self,
        authsession,
        code: str,
        client_id,
        client_secret: str,
) -> campus.model.OAuthToken:
    """Stand-in for the Google token exchange (no network)."""
    return campus.model.OAuthToken(
        id="classroom-access-token-1",
        expires_in=3600,
        refresh_token="classroom-refresh-token-1",
        scopes=list(CLASSROOM_SCOPES),
    )


def _fake_user_info(email: str):
    """Stand-in for the Google userinfo fetch (no network)."""
    def get_user_info(self, access_token: str) -> dict:
        return {"email": str(email), "name": "Connect Tester"}
    return get_user_info


class TestIntegrationConnectContract(unittest.TestCase):
    """Contract tests for the integration connect flow."""

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
        env.set("WORKSPACE_DOMAIN", "nyjc.edu.sg")

        assert self.app
        self.client = self.app.test_client()
        _seed_classroom_vault()
        # The blueprint's before_request constructs the identity proxy,
        # which reads the "google" label on every request
        from campus.auth import resources as auth_resources
        auth_resources.vault["google"]["CLIENT_ID"] = "test-google-client-id"
        auth_resources.vault["google"]["CLIENT_SECRET"] = "test-google-client-secret"

    def _establish_session(self, user_id: schema.UserID = USER_ID) -> None:
        """Give the test client's browser a live campus session."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = str(user_id)

    def _start_connect(self, target: str = PROFILE_CALLBACK) -> str:
        """Start the connect flow and return the OAuth state."""
        response = self.client.get(
            "/auth/v1/google/classroom/authorize",
            query_string={
                "target": f"{target}?connect_state=nonce123",
            },
        )
        assert response.status_code == 302, response.get_json()
        location = response.headers.get("Location", "")
        assert "accounts.google.com" in location, location
        return parse_qs(urlparse(location).query)["state"][0]

    def _complete_connect(
            self,
            state: str,
            userinfo_email: schema.UserID = USER_ID,
    ):
        """Hit the integration callback with the Google legs patched."""
        with mock.patch.object(
                oauth2_scheme.OAuth2AuthorizationCodeFlowScheme,
                "exchange_code_for_token",
                _fake_exchange,
        ), mock.patch.object(
            oauth2_scheme.OAuth2AuthorizationCodeFlowScheme,
            "get_user_info",
            _fake_user_info(userinfo_email),
        ):
            return self.client.get(
                "/auth/v1/google/classroom/callback",
                query_string={
                    "code": "test-auth-code",
                    "state": state,
                    "scope": " ".join(CLASSROOM_SCOPES),
                },
            )

    def test_authorize_forces_consent_and_caps_scopes(self):
        """§2.3: the connect ask is exactly the vault SCOPES cap with
        consent forced, and lands on the integration's own callback."""
        self._establish_session()
        response = self.client.get(
            "/auth/v1/google/classroom/authorize",
            query_string={"target": PROFILE_CALLBACK},
        )

        self.assertEqual(response.status_code, 302)
        location = response.headers.get("Location", "")
        self.assertIn("accounts.google.com", location)
        params = parse_qs(urlparse(location).query)
        self.assertEqual(
            sorted(params["scope"][0].split()),
            sorted(CLASSROOM_SCOPES),
        )
        self.assertEqual(params["prompt"], ["consent"])
        self.assertEqual(params["access_type"], ["offline"])
        self.assertEqual(params["include_granted_scopes"], ["true"])
        self.assertEqual(params["hd"], ["nyjc.edu.sg"])
        self.assertEqual(
            params["redirect_uri"],
            ["https://campus.test/auth/v1/google/classroom/callback"],
        )
        self.assertEqual(params["client_id"], [GOOGLE_CLASSROOM_CLIENT_ID])

    def test_authorize_requires_campus_session(self):
        """§2.3 guard 1: no campus session, no connect flow."""
        response = self.client.get(
            "/auth/v1/google/classroom/authorize",
            query_string={"target": PROFILE_CALLBACK},
        )

        self.assertEqual(response.status_code, 401)

    def test_authorize_unknown_slug_returns_404(self):
        """Unknown slugs are 404 everywhere."""
        self._establish_session()
        response = self.client.get(
            "/auth/v1/google/nope/authorize",
            query_string={"target": PROFILE_CALLBACK},
        )

        self.assertEqual(response.status_code, 404)

    def test_authorize_unconfigured_stub_returns_404(self):
        """§2.1: a registry entry with no vault client is inert."""
        self._establish_session()
        response = self.client.get(
            "/auth/v1/google/calendar/authorize",
            query_string={"target": PROFILE_CALLBACK},
        )

        self.assertEqual(response.status_code, 404)

    def test_authorize_connect_disabled_returns_404(self):
        """§2.1: empty/absent CONNECT_TARGETS disables connect,
        fail-closed."""
        self._establish_session()
        _seed_classroom_vault(CONNECT_TARGETS="")
        response = self.client.get(
            "/auth/v1/google/classroom/authorize",
            query_string={"target": PROFILE_CALLBACK},
        )

        self.assertEqual(response.status_code, 404)

    def test_authorize_rejects_unregistered_target_origin(self):
        """§2.3 guard 2: the target origin must be in CONNECT_TARGETS —
        a token-storing flow must not be an open redirector."""
        self._establish_session()
        response = self.client.get(
            "/auth/v1/google/classroom/authorize",
            query_string={"target": "https://evil.example/callback"},
        )

        self.assertEqual(response.status_code, 400)

    def test_authorize_rejects_non_https_target(self):
        """§2.3 guard 2: connect targets must be HTTPS."""
        self._establish_session()
        response = self.client.get(
            "/auth/v1/google/classroom/authorize",
            query_string={
                "target": "http://profile.example/profile/integrations/classroom/callback",
            },
        )

        self.assertEqual(response.status_code, 400)

    def test_connect_stores_credential_under_namespaced_provider(self):
        """§2.2/§2.6: a successful connect stores the credential under
        google.classroom, redirects to the target preserving its query
        params, and emits the connect audit event — without re-binding
        the session user."""
        self._establish_session()
        state = self._start_connect()

        with mock.patch(
                "campus.auth.oauth_proxy.google.proxy.get_yapper"
        ) as yapper_factory:
            response = self._complete_connect(state)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.headers.get("Location", ""),
            f"{PROFILE_CALLBACK}?connect_state=nonce123",
        )
        # The credential is custodied under the namespaced provider
        from campus.auth import resources as auth_resources
        credentials = auth_resources.credentials["google.classroom"][
            USER_ID
        ].get(GOOGLE_CLASSROOM_CLIENT_ID)
        self.assertEqual(credentials.token.id, "classroom-access-token-1")
        self.assertIsNotNone(credentials.token.refresh_token)
        # The session user is unchanged (already set by identity login)
        with self.client.session_transaction() as sess:
            self.assertEqual(sess.get("user_id"), str(USER_ID))
        # The connect audit event carries no token values
        emissions = [
            call.args
            for call in yapper_factory.return_value.emit.call_args_list
        ]
        connect_events = [
            payload for event, payload in emissions
            if event == "campus.integrations.connect"
        ]
        self.assertEqual(len(connect_events), 1)
        self.assertEqual(
            connect_events[0],
            {
                "provider": "google.classroom",
                "integration": "classroom",
                "user_id": str(USER_ID),
                "scopes": list(CLASSROOM_SCOPES),
            },
        )

    def test_connect_identity_mismatch_denied_and_audited(self):
        """§2.3: the consenting Google account must be the session user;
        a mismatch stores nothing and emits connect_fail."""
        self._establish_session(user_id=OTHER_USER_ID)
        state = self._start_connect()

        with mock.patch(
                "campus.auth.oauth_proxy.google.proxy.get_yapper"
        ) as yapper_factory:
            response = self._complete_connect(state)

        self.assertEqual(response.status_code, 403)
        from campus.auth import resources as auth_resources
        with self.assertRaises(api_errors.NotFoundError):
            auth_resources.credentials["google.classroom"][USER_ID].get(
                GOOGLE_CLASSROOM_CLIENT_ID
            )
        emissions = [
            call.args[1]
            for call in yapper_factory.return_value.emit.call_args_list
            if call.args[0] == "campus.integrations.connect_fail"
        ]
        self.assertEqual(len(emissions), 1)
        self.assertEqual(emissions[0]["integration"], "classroom")
        self.assertEqual(emissions[0]["user_id"], str(OTHER_USER_ID))
        self.assertEqual(emissions[0]["google_user"], str(USER_ID))

    def test_connect_without_session_user_denied(self):
        """§2.3: a lost campus session mid-flow cannot store a
        credential (the OAuth session survives, the binding fails)."""
        self._establish_session()
        state = self._start_connect()
        with self.client.session_transaction() as sess:
            sess.pop("user_id")

        with mock.patch(
                "campus.auth.oauth_proxy.google.proxy.get_yapper"
        ) as yapper_factory:
            response = self._complete_connect(state)

        self.assertEqual(response.status_code, 403)
        emissions = [
            call.args[1]
            for call in yapper_factory.return_value.emit.call_args_list
            if call.args[0] == "campus.integrations.connect_fail"
        ]
        self.assertEqual(len(emissions), 1)
        self.assertIsNone(emissions[0]["user_id"])

    def test_connect_google_error_renders_error_page(self):
        """A Google-side error (e.g. denied consent) errors the page —
        the app's callback never fires."""
        self._establish_session()
        self._start_connect()

        response = self.client.get(
            "/auth/v1/google/classroom/callback",
            query_string={"error": "access_denied"},
        )

        self.assertEqual(response.status_code, 400)


class TestIntegrationBrokerContract(unittest.TestCase):
    """Contract tests for the integration broker release route."""

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
        self.auth_headers = get_basic_auth_headers(
            env.CLIENT_ID, env.CLIENT_SECRET
        )
        _seed_classroom_vault()

        from campus.auth import resources as auth_resources
        # The user's stored classroom credential (as the connect flow
        # would keep it), keyed under the integration's Google client
        auth_resources.credentials["google.classroom"][USER_ID].update(
            client_id=GOOGLE_CLASSROOM_CLIENT_ID,
            token=campus.model.OAuthToken(
                id="classroom-access-token-1",
                expires_in=3600,
                refresh_token="classroom-refresh-token-1",
                scopes=list(CLASSROOM_SCOPES),
            ),
        )

    def _new_bridge_client(
            self,
            upstream_scopes: dict[str, list[str]],
            name: str = "integration-broker-client",
            token_bridge: bool = True,
    ) -> str:
        """Create a campus client + campus bearer for the user."""
        payload = {
            "name": name,
            "description": name,
            "token_bridge": token_bridge,
            "upstream_scopes": upstream_scopes,
        }
        response = self.client.post(
            "/auth/v1/clients/",
            json=payload,
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 200)
        client_id = response.get_json()["id"]

        from campus.auth import resources as auth_resources
        token_id = f"campus-bearer-{client_id[-8:]}"
        auth_resources.credentials["campus"][USER_ID].update(
            client_id=client_id,
            token=campus.model.OAuthToken(
                id=token_id, expires_in=3600, scopes=["read"],
            ),
        )
        return token_id

    def _release(
            self,
            bearer: str,
            path: str = "/auth/v1/broker/google/classroom/",
            json_body: dict | None = None,
    ):
        headers = {"Authorization": f"Bearer {bearer}"}
        return self.client.post(path, json=json_body or {}, headers=headers)

    def test_release_returns_namespaced_minimal_token(self):
        """§2.4: happy path mirrors the identity response shape, keyed
        by the namespaced provider, with no refresh token."""
        bearer = self._new_bridge_client(
            {"google.classroom": [CLASSROOM_COURSES, CLASSROOM_ROSTERS]},
        )

        with self.assertNoLogs(
                "campus.auth.routes.broker", level="WARNING"
        ):
            response = self._release(bearer)

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["provider"], "google.classroom")
        self.assertEqual(data["user_id"], str(USER_ID))
        self.assertEqual(data["access_token"], "classroom-access-token-1")
        self.assertEqual(data["token_type"], "Bearer")
        self.assertGreater(data["expires_in"], 0)
        self.assertIn(CLASSROOM_COURSES, data["scope"])
        self.assertNotIn("refresh_token", data)
        self.assertNotIn("provider_fields", data)

    def test_release_emits_broker_release_with_integration(self):
        """§2.4: release audit events name the integration."""
        bearer = self._new_bridge_client(
            {"google.classroom": [CLASSROOM_COURSES, CLASSROOM_ROSTERS]},
        )

        with mock.patch(
                "campus.auth.routes.broker.get_yapper"
        ) as yapper_factory:
            self._release(bearer)

        emissions = [
            call.args[1]
            for call in yapper_factory.return_value.emit.call_args_list
            if call.args[0] == "campus.broker.release"
        ]
        self.assertEqual(len(emissions), 1)
        self.assertEqual(emissions[0]["provider"], "google.classroom")
        self.assertEqual(emissions[0]["integration"], "classroom")

    def test_release_without_allowlist_entry_denied(self):
        """§2.5 amended rule: an absent (or empty) upstream_scopes entry
        for the integration denies even a min_scopes-less release."""
        bearer = self._new_bridge_client(
            {"google": [CLASSROOM_ROSTERS]},
            name="no-integration-entry-client",
        )

        with mock.patch(
                "campus.auth.routes.broker.get_yapper"
        ) as yapper_factory:
            response = self._release(bearer)

        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "AUTH_INVALID_SCOPE")
        deny_events = [
            call.args[1]
            for call in yapper_factory.return_value.emit.call_args_list
            if call.args[0] == "campus.broker.deny"
        ]
        self.assertEqual(len(deny_events), 1)
        self.assertEqual(deny_events[0]["provider"], "google.classroom")
        self.assertEqual(deny_events[0]["integration"], "classroom")

    def test_release_min_scopes_beyond_allowlist_rejected(self):
        """§2.4: min_scopes outside the client's allowlist entry fail
        with AUTH_INVALID_SCOPE."""
        bearer = self._new_bridge_client(
            {"google.classroom": [CLASSROOM_COURSES, CLASSROOM_ROSTERS]},
        )

        # userinfo.profile is in the vault cap but not this client's
        # allowlist entry
        response = self._release(
            bearer,
            json_body={"min_scopes": [USERINFO_PROFILE]},
        )

        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "AUTH_INVALID_SCOPE")

    def test_release_min_scopes_beyond_vault_cap_rejected(self):
        """§2.5: the vault SCOPES set caps every ask, independent of the
        client allowlist — a configuration error, not re-consent."""
        bearer = self._new_bridge_client(
            {
                "google.classroom": [
                    CLASSROOM_COURSES,
                    CLASSROOM_ROSTERS,
                    SCOPE_OUTSIDE_CAP,
                ],
            },
            name="overwide-allowlist-client",
        )

        response = self._release(
            bearer,
            json_body={"min_scopes": [SCOPE_OUTSIDE_CAP]},
        )

        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "AUTH_INVALID_SCOPE")

    def test_release_unknown_slug_returns_404(self):
        """§2.4: unknown integrations are 404."""
        bearer = self._new_bridge_client(
            {"google.classroom": [CLASSROOM_ROSTERS]},
        )

        response = self._release(bearer, path="/auth/v1/broker/google/nope/")

        self.assertEqual(response.status_code, 404)

    def test_release_base_provider_mismatch_returns_404(self):
        """§2.1: the slug must belong to the named base provider."""
        bearer = self._new_bridge_client(
            {"google.classroom": [CLASSROOM_ROSTERS]},
        )

        response = self._release(
            bearer,
            path="/auth/v1/broker/github/classroom/",
        )

        self.assertEqual(response.status_code, 404)

    def test_release_unconfigured_stub_returns_404(self):
        """§2.1: calendar has no vault client, so it cannot release."""
        bearer = self._new_bridge_client(
            {"google.calendar": ["https://www.googleapis.com/auth/calendar"]},
            name="calendar-release-client",
        )

        response = self._release(
            bearer,
            path="/auth/v1/broker/google/calendar/",
        )

        self.assertEqual(response.status_code, 404)

    def test_release_without_credential_hints_at_connect_flow(self):
        """§2.4: a missing credential is a 404 whose hint points at the
        connect flow, not the deprecated upstream_scope login path."""
        bearer = self._new_bridge_client(
            {"google.classroom": [CLASSROOM_ROSTERS]},
        )

        from campus.auth import resources as auth_resources
        other_user = schema.UserID("neverconnected@nyjc.edu.sg")
        auth_resources.credentials["campus"][other_user].update(
            client_id=self._client_id_of(bearer),
            token=campus.model.OAuthToken(
                id="campus-neverconnected-bearer",
                expires_in=3600,
                scopes=["read"],
            ),
        )

        response = self._release("campus-neverconnected-bearer")

        self.assertEqual(response.status_code, 404)
        self.assertIn("connect", str(response.get_json()))

    def _client_id_of(self, bearer: str) -> str:
        from campus.auth import resources as auth_resources
        credentials = auth_resources.credentials["campus"].get(bearer)
        return credentials.client_id

    def test_release_grant_miss_denied_with_missing_list(self):
        """§2.4: a grant that does not cover min_scopes is 403 with
        missing_scopes (C3b)."""
        bearer = self._new_bridge_client(
            {"google.classroom": [CLASSROOM_COURSES, CLASSROOM_ROSTERS]},
        )

        from campus.auth import resources as auth_resources
        auth_resources.credentials["google.classroom"][USER_ID].update(
            client_id=GOOGLE_CLASSROOM_CLIENT_ID,
            token=campus.model.OAuthToken(
                id="classroom-partial-token",
                expires_in=3600,
                scopes=[CLASSROOM_COURSES, USERINFO_EMAIL],
            ),
        )

        response = self._release(
            bearer,
            json_body={"min_scopes": [CLASSROOM_ROSTERS]},
        )

        self.assertEqual(response.status_code, 403)
        data = response.get_json()
        self.assertIn("classroom.rosters", str(data))

    def test_release_expired_token_is_silently_refreshed(self):
        """B2: Campus refreshes from its stored refresh token via the
        integration's own client; the refresh token never leaves."""
        bearer = self._new_bridge_client(
            {"google.classroom": [CLASSROOM_COURSES, CLASSROOM_ROSTERS]},
        )

        from campus.auth import resources as auth_resources
        auth_resources.credentials["google.classroom"][USER_ID].update(
            client_id=GOOGLE_CLASSROOM_CLIENT_ID,
            token=campus.model.OAuthToken(
                id="classroom-expired-token",
                expires_in=-3600,
                refresh_token="classroom-refresh-token-1",
                scopes=list(CLASSROOM_SCOPES),
            ),
        )

        def fake_refresh(self, auth_token, **kwargs):
            return campus.model.OAuthToken(
                id="classroom-access-token-2",
                expires_in=3600,
                refresh_token="classroom-refresh-token-2",
                scopes=list(auth_token.scopes),
            )

        with mock.patch.object(
                oauth2_scheme.OAuth2AuthorizationCodeFlowScheme,
                "refresh_token",
                fake_refresh,
        ):
            response = self._release(bearer)

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["access_token"], "classroom-access-token-2")
        stored = auth_resources.credentials["google.classroom"][
            USER_ID
        ].get(GOOGLE_CLASSROOM_CLIENT_ID)
        self.assertEqual(stored.token.id, "classroom-access-token-2")

    def test_release_requires_bridge_flag(self):
        """C1: a confidential client without the bridge flag is denied
        on the integration route too."""
        bearer = self._new_bridge_client(
            {"google.classroom": [CLASSROOM_ROSTERS]},
            name="unflagged-integration-client",
            token_bridge=False,
        )

        response = self._release(bearer)

        self.assertEqual(response.status_code, 403)
