"""HTTP contract tests for campus.auth credentials endpoints.

These tests verify the HTTP interface contract for credentials operations.
They test status codes, response formats, and authentication behavior.

Credentials Endpoints Reference:
- GET    /credentials/{provider}/            - List credentials or get by token_id
- GET    /credentials/{provider}/{user_id}   - Get credentials for user
- POST   /credentials/{provider}/{user_id}   - Create new credentials
- PATCH  /credentials/{provider}/{user_id}   - Update credentials
- DELETE /credentials/{provider}/{user_id}   - Delete credentials
"""

import unittest

import campus.model
from campus.common import env, schema
from tests.fixtures import services
from tests.fixtures.tokens import (
    create_test_client_credentials,
    create_test_token,
    get_basic_auth_headers,
    get_bearer_auth_headers,
)


class TestAuthCredentialsContract(unittest.TestCase):
    """HTTP contract tests for /auth/v1/credentials/ endpoints."""

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager()
        cls.manager.initialize()
        cls.app = cls.manager.auth_app

        # Create a test user with bearer token
        cls.test_user_id = schema.UserID("contract.test@campus.test")
        cls.bearer_token = create_test_token(cls.test_user_id)

    @classmethod
    def tearDownClass(cls):
        cls.manager.cleanup()

    def setUp(self):
        self.client = self.app.test_client()
        # Use the default test client for Basic Auth. The credentials
        # API is operator-only (#854): the operator manages credential
        # records, user bearers authenticate nothing here.
        self.basic_auth_headers = get_basic_auth_headers(env.CLIENT_ID, env.CLIENT_SECRET)

    def test_list_credentials_requires_auth(self):
        """GET /credentials/{provider}/ without auth returns 401."""
        response = self.client.get("/auth/v1/credentials/campus/")

        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertIn("error", data)
        self.assertIn("code", data["error"])
        self.assertEqual(data["error"]["code"], "UNAUTHORIZED")

    def test_list_credentials_with_auth(self):
        """GET /credentials/{provider}/ returns list of credentials."""
        response = self.client.get(
            "/auth/v1/credentials/campus/",
            headers=self.basic_auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("credentials", data)
        self.assertIsInstance(data["credentials"], list)

    def test_get_credentials_by_token_id(self):
        """GET /credentials/{provider}/?token_id=X returns specific credentials."""
        response = self.client.get(
            f"/auth/v1/credentials/campus/?token_id={self.bearer_token}",
            headers=self.basic_auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        # Credentials resource is returned directly (unwrapped)
        self.assertIn("id", data)
        self.assertIn("provider", data)

    def test_get_credentials_by_user_id(self):
        """GET /credentials/{provider}/{user_id} returns user credentials."""
        response = self.client.get(
            f"/auth/v1/credentials/campus/{self.test_user_id}/",
            headers=self.basic_auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        # Credentials resource is returned directly (unwrapped)
        self.assertIn("id", data)
        self.assertIn("provider", data)
        self.assertIn("user_id", data)

    def test_get_credentials_missing_user_returns_404(self):
        """GET /credentials/{provider}/nonexistent returns 404."""
        response = self.client.get(
            "/auth/v1/credentials/campus/nonexistent@campus.test/",
            headers=self.basic_auth_headers
        )

        self.assertEqual(response.status_code, 404)

    def test_create_credentials(self):
        """POST /credentials/{provider}/{user_id} creates new credentials."""
        new_user_id = schema.UserID("new.user@campus.test")

        response = self.client.post(
            f"/auth/v1/credentials/campus/{new_user_id}/",
            json={
                "scopes": ["read", "write"],
                "expires_in": 3600
            },
            headers=self.basic_auth_headers
        )

        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        # POST returns the token resource directly
        self.assertIn("id", data)
        self.assertIn("scope", data)

    def test_create_credentials_missing_fields_returns_422(self):
        """POST /credentials/{provider}/{user_id} without required fields returns 422.

        Missing request fields raise the structured ValidationError
        (422 VALIDATION_FAILED) from unpack_into, per the error-handling
        convention introduced by #347.
        """
        response = self.client.post(
            f"/auth/v1/credentials/campus/{self.test_user_id}/",
            json={},  # Missing scopes and expires_in
            headers=self.basic_auth_headers
        )

        self.assertEqual(response.status_code, 422)
        data = response.get_json()
        self.assertIn("error", data)
        self.assertEqual(data["error"]["code"], "VALIDATION_FAILED")

    def test_update_credentials(self):
        """PATCH /credentials/{provider}/{user_id} updates credentials."""

        response = self.client.patch(
            f"/auth/v1/credentials/campus/{self.test_user_id}/",
            json={
                "token": {
                    "id": self.bearer_token,
                    "scopes": ["read", "write", "admin"],
                    "expires_in": 7200
                }
            },
            headers=self.basic_auth_headers
        )

        self.assertEqual(response.status_code, 200)

    def test_create_credentials_expiry_seconds_returns_422(self):
        """POST with the removed expiry_seconds key returns 422 (#648
        item 2: the deprecation window closed; only expires_in is
        accepted)."""
        response = self.client.post(
            f"/auth/v1/credentials/campus/{self.test_user_id}/",
            json={
                "scopes": ["read"],
                "expiry_seconds": 3600
            },
            headers=self.basic_auth_headers
        )

        self.assertEqual(response.status_code, 422)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "VALIDATION_FAILED")

    def test_create_credentials_missing_expiry_returns_422(self):
        """POST without expires_in/expiry_seconds returns 422."""
        response = self.client.post(
            f"/auth/v1/credentials/campus/{self.test_user_id}/",
            json={"scopes": ["read"]},
            headers=self.basic_auth_headers
        )

        self.assertEqual(response.status_code, 422)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "VALIDATION_FAILED")

    def test_update_credentials_accepts_resource_emission(self):
        """PATCH accepts a token resource as emitted by OAuthToken.to_resource().

        Regression test for #655: since #650 the token resource carries
        the RFC 6749 `scope` string alongside `scopes`; validating the
        PATCH body with OAuthToken(**token) rejected the model's own
        output with 422 VALIDATION_FAILED.
        """
        token = campus.model.OAuthToken(
            id=self.bearer_token,
            expires_in=7200,
            scopes=["read", "write", "admin"],
        )

        response = self.client.patch(
            f"/auth/v1/credentials/campus/{self.test_user_id}/",
            json={"token": token.to_resource()},
            headers=self.basic_auth_headers
        )

        self.assertEqual(response.status_code, 200)

    def test_update_credentials_scope_only_token(self):
        """PATCH accepts a token carrying only the RFC 6749 `scope` string.

        When the #648 deprecation window closes, token resources will
        emit `scope` without the `scopes` alias; the validation path
        must already accept that shape (#655).
        """
        response = self.client.patch(
            f"/auth/v1/credentials/campus/{self.test_user_id}/",
            json={
                "token": {
                    "id": self.bearer_token,
                    "scope": "read write",
                    "expires_in": 7200,
                }
            },
            headers=self.basic_auth_headers
        )

        self.assertEqual(response.status_code, 200)

    def test_update_credentials_invalid_token_returns_422(self):
        """PATCH /credentials/{provider}/{user_id} with an invalid token
        object returns 422, not 500.

        Regression test for #325: a malformed token payload used to
        surface as an unhandled error (500).
        """
        response = self.client.patch(
            f"/auth/v1/credentials/campus/{self.test_user_id}/",
            json={"token": {}},  # No expires_at or expiry_seconds
            headers=self.basic_auth_headers
        )

        self.assertEqual(response.status_code, 422)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "VALIDATION_FAILED")
        fields = {e["field"] for e in data["error"]["errors"]}
        self.assertIn("token", fields)

    def test_delete_credentials(self):
        """DELETE /credentials/{provider}/{user_id} deletes credentials.

        The credentials API is operator-only (#854), so the operator
        client deletes the record; the temp user's bearer is then used
        only to verify the credential no longer authenticates.
        """
        # Create a temporary user with credentials
        from tests.fixtures.tokens import create_test_token
        temp_user_id = schema.UserID("temp.user@campus.test")
        temp_token = create_test_token(temp_user_id)
        temp_headers = get_bearer_auth_headers(temp_token)

        # Delete the credentials as the operator
        response = self.client.delete(
            f"/auth/v1/credentials/campus/{temp_user_id}/",
            json={},
            headers=self.basic_auth_headers
        )

        self.assertEqual(response.status_code, 200)

        # Verify they're gone: the deleted credential no longer
        # authenticates, so the request is rejected as 401 invalid_token
        # (RFC 6750 §3.1, #729) rather than a resource 404.
        get_response = self.client.get(
            f"/auth/v1/credentials/campus/{temp_user_id}/",
            headers=temp_headers
        )
        self.assertEqual(get_response.status_code, 401)


class TestCredentialsRedaction(unittest.TestCase):
    """Redacted credential reads and the ?include=token opt-in (#1055).

    Reads return token metadata only — never the raw token material:
    a campus-provider record's token id IS the access token, so an
    unredacted list was a bulk-download of every live token. The
    opt-in exists for the rare legitimate full read of ONE record:
    operator principal or super-admin root, never on the list, never
    to designated admin users.
    """

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager()
        cls.manager.initialize()
        cls.app = cls.manager.auth_app

        cls.test_user_id = schema.UserID("redaction.test@campus.test")
        cls.bearer_token = create_test_token(cls.test_user_id)

    @classmethod
    def tearDownClass(cls):
        cls.manager.cleanup()

    def setUp(self):
        self.client = self.app.test_client()
        self.basic_auth_headers = get_basic_auth_headers(
            env.CLIENT_ID, env.CLIENT_SECRET
        )

    def _grant_and_mint(self, user_id: str, level: str) -> dict:
        """Grant a credentials vocabulary row and mint a scoped token."""
        from campus.auth.resources.grant import grants as grants_store

        grants_store.grant("user", user_id, "credentials", level=level)
        token = create_test_token(
            schema.UserID(user_id),
            scopes=[f"credentials:{level}"],
            grant_vault_access=False,
        )
        return get_bearer_auth_headers(token)

    def test_list_credentials_are_redacted(self):
        """GET /credentials/campus/ returns metadata, no token material."""
        response = self.client.get(
            "/auth/v1/credentials/campus/",
            headers=self.basic_auth_headers,
        )

        self.assertEqual(response.status_code, 200)
        records = response.get_json()["credentials"]
        self.assertGreaterEqual(len(records), 1)
        record = next(
            r for r in records if r["user_id"] == str(self.test_user_id)
        )
        token = record["token"]
        # Metadata identifies the credential...
        self.assertIn("expires_at", token)
        self.assertIn("scope", token)
        self.assertEqual(token["token_type"], "Bearer")
        # ...without releasing material: id IS the access token.
        self.assertNotIn("id", token)
        self.assertNotIn("access_token", token)
        self.assertNotIn("refresh_token", record["token"])

    def test_get_by_user_redacted_by_default(self):
        """GET /credentials/campus/{user}/ is redacted by default."""
        response = self.client.get(
            f"/auth/v1/credentials/campus/{self.test_user_id}/",
            headers=self.basic_auth_headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(
            "id", response.get_json()["token"],
            "raw access token leaked on a default read",
        )

    def test_get_by_user_include_token_opt_in(self):
        """?include=token on a per-record read returns the full token."""
        response = self.client.get(
            f"/auth/v1/credentials/campus/{self.test_user_id}/",
            query_string={"include": "token"},
            headers=self.basic_auth_headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json()["token"]["id"], self.bearer_token
        )

    def test_list_ignores_include_token(self):
        """The list never releases raw tokens, opt-in or not (#1055)."""
        response = self.client.get(
            "/auth/v1/credentials/campus/",
            query_string={"include": "token"},
            headers=self.basic_auth_headers,
        )

        self.assertEqual(response.status_code, 200)
        for record in response.get_json()["credentials"]:
            self.assertNotIn("id", record["token"])

    def test_include_token_denied_for_designated_user(self):
        """A designated credentials:read user gets metadata only."""
        headers = self._grant_and_mint(
            "authz.1055.creds.reader@campus.test", "read"
        )

        response = self.client.get(
            f"/auth/v1/credentials/campus/{self.test_user_id}/",
            query_string={"include": "token"},
            headers=headers,
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn(
            "operator-principal power",
            response.get_json()["error"]["message"],
        )

    def test_designated_user_reads_redacted_metadata(self):
        """A designated credentials:read user lists redacted records."""
        headers = self._grant_and_mint(
            "authz.1055.creds.reader2@campus.test", "read"
        )

        response = self.client.get(
            "/auth/v1/credentials/campus/",
            headers=headers,
        )

        self.assertEqual(response.status_code, 200)
        for record in response.get_json()["credentials"]:
            self.assertNotIn("id", record["token"])

    def test_disconnect_arbitrary_client_record(self):
        """DELETE with a body client_id removes another record (#1055)."""
        from campus.auth.resources import credentials as creds_resource

        other_user_id = schema.UserID("disconnect.test@campus.test")
        other_id, _other_secret = create_test_client_credentials(
            name="1055-disconnect-target",
            description="Credential owner for #1055",
        )
        creds_resource["campus"][other_user_id].new(
            client_id=other_id,
            scopes=["read"],
            expires_in=3600,
        )

        # unpack_request sources DELETE parameters from the JSON
        # body — the same shape the SDK's User.delete already sends.
        response = self.client.delete(
            f"/auth/v1/credentials/campus/{other_user_id}/",
            json={"client_id": other_id},
            headers=self.basic_auth_headers,
        )
        self.assertEqual(response.status_code, 200)

        from campus.common.errors import api_errors
        with self.assertRaises(api_errors.NotFoundError):
            creds_resource["campus"][other_user_id].get(other_id)

    def test_designated_read_user_cannot_disconnect(self):
        """credentials:read does not authorize disconnects."""
        from campus.auth.resources import credentials as creds_resource

        other_user_id = schema.UserID("ro.disconnect.test@campus.test")
        creds_resource["campus"][other_user_id].new(
            client_id=env.CLIENT_ID,
            scopes=["read"],
            expires_in=3600,
        )
        headers = self._grant_and_mint(
            "authz.1055.creds.reader3@campus.test", "read"
        )

        response = self.client.delete(
            f"/auth/v1/credentials/campus/{other_user_id}/",
            headers=headers,
        )

        self.assertEqual(response.status_code, 403)


if __name__ == '__main__':
    unittest.main()
