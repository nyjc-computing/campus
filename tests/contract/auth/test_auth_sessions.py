"""HTTP contract tests for campus.auth sessions endpoints.

These tests verify the HTTP interface contract for session management operations.
They test status codes, response formats, and authentication behavior.

NOTE: ALL /sessions/ endpoints require authentication (Basic or Bearer).
This is enforced via before_request hook in the auth blueprint.

Since #1055 the per-id routes (GET/PATCH/DELETE) additionally require
authorization: the session-owning client or the operator; other
principals are denied.

Sessions Endpoints Reference:
- POST   /sessions/sweep                           - Sweep expired sessions (requires auth)
- POST   /sessions/{provider}/authorization_code   - Get session by auth code (requires auth)
- POST   /sessions/{provider}/                     - Create new provider session (requires auth)
- GET    /sessions/{provider}/{session_id}/        - Get session (owner or operator, #1055)
- PATCH  /sessions/{provider}/{session_id}/        - Update session (owner or operator, #1055)
- DELETE /sessions/{provider}/{session_id}/        - Finalize/delete session (owner or operator, #1055)
"""

import unittest

from campus.common import env
from tests.fixtures import services
from tests.fixtures.tokens import get_basic_auth_headers


class TestAuthSessionsContract(unittest.TestCase):
    """HTTP contract tests for /auth/v1/sessions/ endpoints."""

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager()
        cls.manager.initialize()
        cls.app = cls.manager.auth_app

    @classmethod
    def tearDownClass(cls):
        cls.manager.cleanup()

    def setUp(self):
        # Clear test data - no manual resource initialization needed
        self.manager.clear_test_data()

        assert self.app
        self.client = self.app.test_client()
        self.auth_headers = get_basic_auth_headers(env.CLIENT_ID, env.CLIENT_SECRET)
        self.test_provider = "campus"
        self.test_redirect_uri = "https://example.com/callback"

    def test_sweep_sessions_requires_auth(self):
        """POST /sessions/sweep without auth returns 401."""
        response = self.client.post("/auth/v1/sessions/sweep")

        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertIn("error", data)
        self.assertIn("code", data["error"])

    def test_sweep_sessions_with_auth(self):
        """POST /sessions/sweep with auth returns sweep count."""
        response = self.client.post(
            "/auth/v1/sessions/sweep",
            json={},
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("swept_count", data)
        self.assertIsInstance(data["swept_count"], int)

    def test_sweep_sessions_with_time(self):
        """POST /sessions/sweep with at_time parameter."""

        response = self.client.post(
            "/auth/v1/sessions/sweep",
            json={"at_time": None},  # None defaults to now
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("swept_count", data)

    def test_create_provider_session(self):
        """POST /sessions/{provider}/ creates a new auth session."""
        response = self.client.post(
            f"/auth/v1/sessions/{self.test_provider}/",
            json={
                "client_id": env.CLIENT_ID,
                "redirect_uri": self.test_redirect_uri,
                "scopes": ["read", "write"]
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("id", data)
        self.assertIn("expires_at", data)
        self.assertEqual(data["provider"], self.test_provider)

    def test_create_provider_session_with_user_id(self):
        """POST /sessions/{provider}/ with user_id creates user-bound session."""
        from campus.common import schema

        user_id = schema.UserID("test.user@example.com")
        response = self.client.post(
            f"/auth/v1/sessions/{self.test_provider}/",
            json={
                "client_id": env.CLIENT_ID,
                "redirect_uri": self.test_redirect_uri,
                "user_id": str(user_id),
                "scopes": ["read"]
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("id", data)
        self.assertEqual(data["user_id"], str(user_id))

    def test_create_provider_session_missing_redirect_uri(self):
        """POST /sessions/{provider}/ without redirect_uri returns error."""
        response = self.client.post(
            f"/auth/v1/sessions/{self.test_provider}/",
            json={
                "client_id": env.CLIENT_ID,
                "scopes": ["read"]
            },
            headers=self.auth_headers
        )

        # Missing required parameter returns error
        self.assertIn(response.status_code, (400, 422))

    def test_get_provider_session(self):
        """GET /sessions/{provider}/{session_id}/ returns session details."""
        # First create a session
        create_response = self.client.post(
            f"/auth/v1/sessions/{self.test_provider}/",
            json={
                "client_id": env.CLIENT_ID,
                "redirect_uri": self.test_redirect_uri,
                "scopes": ["read"]
            },
            headers=self.auth_headers
        )
        session_id = create_response.get_json()["id"]

        # Get the session
        response = self.client.get(
            f"/auth/v1/sessions/{self.test_provider}/{session_id}/",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["id"], session_id)
        self.assertEqual(data["provider"], self.test_provider)

    def test_get_missing_session_returns_error(self):
        """GET /sessions/{provider}/{session_id}/ for non-existent session returns error."""
        response = self.client.get(
            f"/auth/v1/sessions/{self.test_provider}/does_not_exist/",
            headers=self.auth_headers
        )

        self.assertIn(response.status_code, (404, 400))

    def test_update_provider_session_user_id(self):
        """PATCH /sessions/{provider}/{session_id}/ updates user_id."""
        # First create a session
        create_response = self.client.post(
            f"/auth/v1/sessions/{self.test_provider}/",
            json={
                "client_id": env.CLIENT_ID,
                "redirect_uri": self.test_redirect_uri,
                "scopes": ["read"]
            },
            headers=self.auth_headers
        )
        session_id = create_response.get_json()["id"]

        # Update the session with user_id
        from campus.common import schema
        user_id = schema.UserID("updated.user@example.com")
        response = self.client.patch(
            f"/auth/v1/sessions/{self.test_provider}/{session_id}/",
            json={"user_id": str(user_id)},
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)

    def test_update_provider_session_no_updates(self):
        """PATCH /sessions/{provider}/{session_id}/ without updates succeeds."""
        # First create a session
        create_response = self.client.post(
            f"/auth/v1/sessions/{self.test_provider}/",
            json={
                "client_id": env.CLIENT_ID,
                "redirect_uri": self.test_redirect_uri,
                "scopes": ["read"]
            },
            headers=self.auth_headers
        )
        session_id = create_response.get_json()["id"]

        # Update with empty body
        response = self.client.patch(
            f"/auth/v1/sessions/{self.test_provider}/{session_id}/",
            json={},
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)

    def test_delete_provider_session(self):
        """DELETE /sessions/{provider}/{session_id}/ finalizes the session."""
        # First create a session with a target
        target_uri = "https://example.com/target"
        create_response = self.client.post(
            f"/auth/v1/sessions/{self.test_provider}/",
            json={
                "client_id": env.CLIENT_ID,
                "redirect_uri": self.test_redirect_uri,
                "scopes": ["read"],
                "target": target_uri
            },
            headers=self.auth_headers
        )
        session_id = create_response.get_json()["id"]

        # Finalize the session
        response = self.client.delete(
            f"/auth/v1/sessions/{self.test_provider}/{session_id}/",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("target", data)
        self.assertEqual(data["target"], target_uri)

    def test_delete_provider_session_no_target(self):
        """DELETE /sessions/{provider}/{session_id}/ with no target returns null target."""
        # First create a session without a target
        create_response = self.client.post(
            f"/auth/v1/sessions/{self.test_provider}/",
            json={
                "client_id": env.CLIENT_ID,
                "redirect_uri": self.test_redirect_uri,
                "scopes": ["read"]
            },
            headers=self.auth_headers
        )
        session_id = create_response.get_json()["id"]

        # Finalize the session
        response = self.client.delete(
            f"/auth/v1/sessions/{self.test_provider}/{session_id}/",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        # Target may be None or not present
        self.assertIn("target", data)

    def test_get_session_by_authorization_code(self):
        """POST /sessions/{provider}/authorization_code retrieves session by code."""
        # First create a session
        create_response = self.client.post(
            f"/auth/v1/sessions/{self.test_provider}/",
            json={
                "client_id": env.CLIENT_ID,
                "redirect_uri": self.test_redirect_uri,
                "scopes": ["read"]
            },
            headers=self.auth_headers
        )
        session_data = create_response.get_json()
        auth_code = session_data.get("authorization_code")

        # Get session by authorization code
        # Note: authorization_code endpoint has no trailing slash in route
        response = self.client.post(
            f"/auth/v1/sessions/{self.test_provider}/authorization_code",
            json={"code": auth_code},
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("id", data)
        self.assertEqual(data["id"], session_data["id"])

    def test_get_session_by_invalid_authorization_code(self):
        """POST /sessions/{provider}/authorization_code with invalid code returns 400."""
        response = self.client.post(
            # No trailing slash, per the route definition
            f"/auth/v1/sessions/{self.test_provider}/authorization_code",
            json={"code": "invalid_auth_code_12345"},
            headers=self.auth_headers
        )

        # A failed code exchange is a bad request, not an auth failure: the
        # caller is authenticated, the input code is invalid. RFC 6749 5.2
        # puts access_denied in the 400 token-error response, and the route
        # raises auth_errors.AccessDeniedError (status_code 400) for it (#623).
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertIn("error", data)


class TestSessionUserEmbedding(unittest.TestCase):
    """Session reads and finalization embed the user record for the
    session-owning client or the operator (#879); other principals get
    no user data.

    flask_campus apps hydrate the signed-in user from these responses
    instead of the operator-gated GET /users/{id}.
    """

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager()
        cls.manager.initialize()
        cls.app = cls.manager.auth_app

    @classmethod
    def tearDownClass(cls):
        cls.manager.cleanup()

    def setUp(self):
        # Clear test data - no manual resource initialization needed
        self.manager.clear_test_data()

        assert self.app
        self.client = self.app.test_client()
        self.auth_headers = get_basic_auth_headers(env.CLIENT_ID, env.CLIENT_SECRET)
        self.provider = "campus"

    def _create_user(self, user_id: str) -> None:
        """Insert a user record directly (storage-level, as in the
        users contract tests)."""
        from contextlib import suppress

        from campus.auth.resources.user import user_storage

        with suppress(Exception):
            user_storage.delete_by_id(user_id)
        user_storage.insert_one({
            "id": user_id,
            "created_at": "2024-01-01T00:00:00+00:00",
            "email": user_id,
            "name": "Session User",
            "activated_at": None,
        })

    def _create_session(self, user_id: str | None = None) -> str:
        """Create a session owned by the main test client."""
        body = {
            "client_id": env.CLIENT_ID,
            "redirect_uri": "https://example.com/callback",
            "scopes": ["read"],
        }
        if user_id is not None:
            body["user_id"] = user_id
        resp = self.client.post(
            f"/auth/v1/sessions/{self.provider}/",
            json=body,
            headers=self.auth_headers,
        )
        assert resp.status_code == 200, resp.get_json()
        return resp.get_json()["id"]

    def _create_other_client(self) -> "tuple[str, str]":
        """Create a fresh non-owner, non-operator client.

        Returns (client_id, client_secret); the secret is only ever
        revealed at rotation time, so this is the one chance to hold it.
        """
        resp = self.client.post(
            "/auth/v1/clients/",
            json={"name": "other-app", "description": "not the owner"},
            headers=self.auth_headers,
        )
        other_id = resp.get_json()["id"]
        resp = self.client.post(
            f"/auth/v1/clients/{other_id}/revoke",
            json={},
            headers=self.auth_headers,
        )
        assert resp.status_code == 200, resp.get_json()
        return other_id, resp.get_json()["secret"]

    def _other_client_headers(self, other_id: str, other_secret: str) -> dict:
        """Basic headers for the given non-owner client."""
        return get_basic_auth_headers(other_id, other_secret)

    def test_get_embeds_user_for_owning_client(self):
        """GET /sessions/{p}/{id}/ embeds the user for the owning client."""
        user_id = "session.user@example.com"
        self._create_user(user_id)
        session_id = self._create_session(user_id)

        response = self.client.get(
            f"/auth/v1/sessions/{self.provider}/{session_id}/",
            headers=self.auth_headers,
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["user"]["id"], user_id)
        self.assertEqual(data["user"]["email"], user_id)
        self.assertEqual(data["user"]["name"], "Session User")

    def test_get_denied_for_other_client(self):
        """GET /sessions/{p}/{id}/ denies a non-owner client (#1055).

        Before #1055 any authenticated client could read any session
        it learned the id of (embedded user withheld by #879 only);
        the per-id routes are now gated to the owning client and the
        operator (require_session_access).
        """
        user_id = "session.user2@example.com"
        self._create_user(user_id)
        session_id = self._create_session(user_id)
        other_id, other_secret = self._create_other_client()

        response = self.client.get(
            f"/auth/v1/sessions/{self.provider}/{session_id}/",
            headers=self._other_client_headers(other_id, other_secret),
        )

        self.assertEqual(response.status_code, 403)
        data = response.get_json()
        self.assertIn("error", data)

    def test_get_embeds_user_for_operator_of_foreign_session(self):
        """The operator sees the embedded user on another client's session."""
        other_id, other_secret = self._create_other_client()
        resp = self.client.post(
            f"/auth/v1/sessions/{self.provider}/",
            json={
                "client_id": other_id,
                "redirect_uri": "https://example.com/callback",
            },
            headers=self._other_client_headers(other_id, other_secret),
        )
        self.assertEqual(resp.status_code, 200)
        session_id = resp.get_json()["id"]
        user_id = "session.user3@example.com"
        self._create_user(user_id)
        # Bind the user to the session via PATCH (operator allowed).
        patch = self.client.patch(
            f"/auth/v1/sessions/{self.provider}/{session_id}/",
            json={"user_id": user_id},
            headers=self.auth_headers,
        )
        self.assertEqual(patch.status_code, 200)

        response = self.client.get(
            f"/auth/v1/sessions/{self.provider}/{session_id}/",
            headers=self.auth_headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["user"]["id"], user_id)

    def test_get_without_user_record_returns_null_user(self):
        """A missing user record degrades to a null embed, not a 500."""
        user_id = "ghost.user@example.com"
        session_id = self._create_session(user_id)

        response = self.client.get(
            f"/auth/v1/sessions/{self.provider}/{session_id}/",
            headers=self.auth_headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.get_json().get("user"))

    def test_finalize_embeds_user_for_owning_client(self):
        """DELETE /sessions/{p}/{id}/ carries target and the user (#879)."""
        user_id = "session.finalize@example.com"
        self._create_user(user_id)
        session_id = self._create_session(user_id)

        response = self.client.delete(
            f"/auth/v1/sessions/{self.provider}/{session_id}/",
            headers=self.auth_headers,
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("target", data)
        self.assertEqual(data["user"]["id"], user_id)

    def test_finalize_denied_for_other_client(self):
        """DELETE /sessions/{p}/{id}/ denies a non-owner client (#1055).

        Finalizing deletes the session, so a non-owner DELETE would be
        a silent revoke of another app's login flow; gated to the
        owning client and the operator since #1055.
        """
        user_id = "session.finalize2@example.com"
        self._create_user(user_id)
        session_id = self._create_session(user_id)

        other_id, other_secret = self._create_other_client()
        response = self.client.delete(
            f"/auth/v1/sessions/{self.provider}/{session_id}/",
            headers=self._other_client_headers(other_id, other_secret),
        )

        self.assertEqual(response.status_code, 403)
        data = response.get_json()
        self.assertIn("error", data)

        # The denial must not have consumed the session: the owner can
        # still finalize it.
        owner_response = self.client.delete(
            f"/auth/v1/sessions/{self.provider}/{session_id}/",
            headers=self.auth_headers,
        )
        self.assertEqual(owner_response.status_code, 200)

    def test_user_bearer_denied_on_per_id_routes(self):
        """User bearers are denied on the per-id session routes (#1055).

        A user principal is never a session's owning client (#854);
        the super-admin root passes, and designated admin users join
        via the management-scope vocabulary.
        """
        from campus.common import schema
        from tests.fixtures.tokens import create_test_token, get_bearer_auth_headers

        user_id = "session.userbearer@example.com"
        self._create_user(user_id)
        session_id = self._create_session(user_id)
        token = create_test_token(
            schema.UserID(user_id), grant_vault_access=False
        )
        headers = get_bearer_auth_headers(token)
        base = f"/auth/v1/sessions/{self.provider}/{session_id}/"

        get_response = self.client.get(base, headers=headers)
        self.assertEqual(get_response.status_code, 403)

        patch_response = self.client.patch(
            base, json={"user_id": user_id}, headers=headers
        )
        self.assertEqual(patch_response.status_code, 403)

        delete_response = self.client.delete(base, headers=headers)
        self.assertEqual(delete_response.status_code, 403)


class TestSessionsAdminSurface(unittest.TestCase):
    """GET /sessions/ and the designated-admin legs of the per-id
    routes (#1055).

    The list is operator/designated-admin only and carries session
    metadata only — no authorization_code, no user embeds. The
    owning client keeps its full flow record on per-id reads; every
    other authorized principal (operator, designated admin) sees
    metadata. A designated user needs BOTH legs: a sessions:* grant
    row (#883) AND a token carrying the scope (#865).
    """

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
        self.auth_headers = get_basic_auth_headers(env.CLIENT_ID, env.CLIENT_SECRET)
        self.provider = "campus"

    def _create_session(self, client_id: str | None = None) -> str:
        """Create a session for the operator (default) or another client.

        Foreign clients carry no requested scopes: fresh clients have
        an empty allowed_scopes allowlist, and invariant A1/A6 rejects
        any scope outside it.
        """
        body = {
            "client_id": client_id or env.CLIENT_ID,
            "redirect_uri": "https://example.com/callback",
        }
        if client_id is None:
            body["scopes"] = ["read"]
        resp = self.client.post(
            f"/auth/v1/sessions/{self.provider}/",
            json=body,
            headers=self.auth_headers,
        )
        assert resp.status_code == 200, resp.get_json()
        return resp.get_json()["id"]

    def _grant_and_mint(self, user_id: str, level: str) -> dict:
        """Grant a sessions vocabulary row and mint a scoped token.

        Returns Bearer headers for the designated user.
        """
        from campus.auth.resources.grant import grants as grants_store
        from campus.common import schema
        from tests.fixtures.tokens import (
            create_test_token,
            get_bearer_auth_headers,
        )

        grants_store.grant("user", user_id, "sessions", level=level)
        token = create_test_token(
            schema.UserID(user_id),
            scopes=[f"sessions:{level}"],
            grant_vault_access=False,
        )
        return get_bearer_auth_headers(token)

    def test_list_sessions_for_operator(self):
        """GET /sessions/ lists sessions for the operator, metadata only."""
        session_id = self._create_session()

        response = self.client.get(
            "/auth/v1/sessions/", headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertGreaterEqual(data["total"], 1)
        record = next(
            s for s in data["sessions"] if s["id"] == session_id
        )
        self.assertEqual(record["provider"], self.provider)
        self.assertEqual(record["client_id"], env.CLIENT_ID)
        self.assertIn("created_at", record)
        self.assertIn("expires_at", record)
        self.assertNotIn("authorization_code", record)
        self.assertNotIn("user", record)

    def test_list_sessions_filters(self):
        """GET /sessions/?client_id=... scopes the listing."""
        from tests.fixtures.tokens import create_test_client_credentials

        other_id, _other_secret = create_test_client_credentials(
            name="1055-filter-client",
            description="Filter target for #1055",
        )
        self._create_session()
        other_session_id = self._create_session(client_id=other_id)

        response = self.client.get(
            "/auth/v1/sessions/",
            query_string={"client_id": other_id},
            headers=self.auth_headers,
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["sessions"][0]["id"], other_session_id)

        by_provider = self.client.get(
            "/auth/v1/sessions/",
            query_string={"provider": self.provider},
            headers=self.auth_headers,
        )
        self.assertEqual(by_provider.status_code, 200)
        self.assertGreaterEqual(by_provider.get_json()["total"], 2)

    def test_list_sessions_pagination(self):
        """GET /sessions/?limit=&offset= pages the listing."""
        self._create_session()
        self._create_session()

        page = self.client.get(
            "/auth/v1/sessions/",
            query_string={"limit": 1, "offset": 0},
            headers=self.auth_headers,
        )
        self.assertEqual(page.status_code, 200)
        self.assertEqual(len(page.get_json()["sessions"]), 1)
        self.assertEqual(page.get_json()["total"], 2)

        second = self.client.get(
            "/auth/v1/sessions/",
            query_string={"limit": 1, "offset": 1},
            headers=self.auth_headers,
        )
        self.assertEqual(second.status_code, 200)
        self.assertEqual(len(second.get_json()["sessions"]), 1)
        self.assertNotEqual(
            page.get_json()["sessions"][0]["id"],
            second.get_json()["sessions"][0]["id"],
        )

    def test_list_sessions_denied_for_client_principal(self):
        """A non-operator client may not enumerate sessions (#1055)."""
        from tests.fixtures.tokens import create_test_client_credentials

        other_id, other_secret = create_test_client_credentials(
            name="1055-list-denied",
            description="Non-operator client for #1055",
        )
        headers = get_basic_auth_headers(other_id, other_secret)

        response = self.client.get("/auth/v1/sessions/", headers=headers)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.get_json()["error"]["code"], "FORBIDDEN"
        )

    def test_list_sessions_denied_for_undesignated_user(self):
        """Scope without a grant row confers nothing (#854 regression)."""
        from campus.common import schema
        from tests.fixtures.tokens import (
            create_test_token,
            get_bearer_auth_headers,
        )

        token = create_test_token(
            schema.UserID("authz.1055.scopeless@campus.test"),
            scopes=["sessions:read"],
            grant_vault_access=False,
        )
        headers = get_bearer_auth_headers(token)

        response = self.client.get("/auth/v1/sessions/", headers=headers)

        self.assertEqual(response.status_code, 403)
        self.assertIn(
            "No access grant designates",
            response.get_json()["error"]["message"],
        )

    def test_list_sessions_for_designated_user(self):
        """A designated user with sessions:read grant AND scope lists."""
        headers = self._grant_and_mint(
            "authz.1055.reader@campus.test", "read"
        )

        response = self.client.get("/auth/v1/sessions/", headers=headers)

        self.assertEqual(response.status_code, 200)
        self.assertIn("sessions", response.get_json())

    def test_get_metadata_view_for_designated_user(self):
        """Per-id GET for a designated user: metadata, no flow secrets."""
        session_id = self._create_session()
        headers = self._grant_and_mint(
            "authz.1055.reader2@campus.test", "read"
        )

        response = self.client.get(
            f"/auth/v1/sessions/{self.provider}/{session_id}/",
            headers=headers,
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["id"], session_id)
        self.assertNotIn("authorization_code", data)
        self.assertIsNone(data.get("user"))

    def test_get_full_record_for_owning_client(self):
        """The owning client keeps its full flow record on GET."""
        session_id = self._create_session()

        response = self.client.get(
            f"/auth/v1/sessions/{self.provider}/{session_id}/",
            headers=self.auth_headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "authorization_code", response.get_json()
        )

    def test_finalize_by_operator_is_metadata_revocation(self):
        """Operator DELETE of a foreign session: metadata + target."""
        from tests.fixtures.tokens import create_test_client_credentials

        other_id, _other_secret = create_test_client_credentials(
            name="1055-revoke-target",
            description="Session owner for #1055 revoke test",
        )
        session_id = self._create_session(client_id=other_id)

        response = self.client.delete(
            f"/auth/v1/sessions/{self.provider}/{session_id}/",
            headers=self.auth_headers,
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("target", data)
        self.assertNotIn("authorization_code", data)

        # The session is gone (revoke deletes, same as finalize).
        follow_up = self.client.get(
            f"/auth/v1/sessions/{self.provider}/{session_id}/",
            headers=self.auth_headers,
        )
        self.assertEqual(follow_up.status_code, 404)

    def test_sessions_admin_grant_row_rejected(self):
        """sessions:admin rows are rejected as inert (#1055).

        Nothing sits above revoke, so the vocabulary is grantable up
        to write; grant administration for it stays operator-only.
        """
        response = self.client.post(
            "/auth/v1/grants/",
            json={
                "grantee_type": "user",
                "grantee_id": "authz.1055.admin@campus.test",
                "resource_type": "sessions",
                "level": "admin",
            },
            headers=self.auth_headers,
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn(
            "nothing to govern",
            response.get_json()["error"]["message"],
        )

    def test_sessions_grant_rows_administered_via_grants_api(self):
        """The operator grants sessions levels over HTTP (#1055)."""
        user_id = "authz.1055.http.grant@campus.test"
        grant_response = self.client.post(
            "/auth/v1/grants/",
            json={
                "grantee_type": "user",
                "grantee_id": user_id,
                "resource_type": "sessions",
                "level": "read",
            },
            headers=self.auth_headers,
        )
        self.assertEqual(grant_response.status_code, 201)

        list_response = self.client.get(
            "/auth/v1/grants/",
            query_string={
                "resource_type": "sessions",
                "grantee_id": user_id,
            },
            headers=self.auth_headers,
        )
        self.assertEqual(list_response.status_code, 200)
        rows = list_response.get_json()["grants"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["level"], "read")


if __name__ == '__main__':
    unittest.main()
