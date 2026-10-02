"""Integration tests for Audit API Key Lifecycle.

These tests verify end-to-end API key lifecycle operations:
1. Create API key
2. Use API key for authentication
3. Update API key
4. Revoke API key
5. Verify revoked key cannot be used

Tests verify real database operations, authentication, and authorization.
Each test is self-contained (creates its own keys) so it can run in any
order, alone or alongside the others (#570).

File: tests/integration/test_audit_apikeys_lifecycle.py
Issue: #541, #570
"""

import unittest
from contextlib import suppress

import campus.storage
from campus.common import schema
from campus.common.utils import secret, uid
from tests.integration.base import IsolatedIntegrationTestCase


class TestAuditAPIKeyLifecycle(IsolatedIntegrationTestCase):
    """Integration tests for complete API key lifecycle.

    Tests create → authenticate → update → revoke workflow.
    Uses real database and authentication (no mocks).
    """

    # A Bearer-protected endpoint: /audit/v1/health is intentionally
    # public, so auth tests exercise the apikeys blueprint (#570)
    PROTECTED_ENDPOINT = "/audit/v1/apikeys/"

    @classmethod
    def setUpClass(cls):
        """Set up services for API key lifecycle tests."""
        super().setUpClass()

        # Get the audit app
        cls.audit_app = cls.manager.audit_app

        # CRITICAL: Lazy import APIKeysResource AFTER test mode is configured
        # Importing before test mode causes PostgreSQL backend initialization
        # See AGENTS.md - Storage Initialization Order
        from campus.audit.resources.apikeys import APIKeysResource

        # Initialize apikeys storage ONCE per test class
        # CREATE TABLE IF NOT EXISTS is idempotent
        # Schema is preserved by clear_test_data() during setUp()
        APIKeysResource.init_storage()

    def setUp(self):
        """Set up test client and clear storage before each test."""
        super().setUp()  # Uses new API: clear_test_data()

        assert self.audit_app, "Audit app not initialized"
        self.client = self.audit_app.test_client()

        # Clear apikeys storage between tests for isolation
        apikeys_storage = campus.storage.tables.get_db("apikeys")
        with suppress(campus.storage.errors.NoChangesAppliedError):
            apikeys_storage.delete_matching({})

    def tearDown(self):
        """Clean up after each test."""
        super().tearDown()  # Uses new API: flush_async()

    def _create_admin_api_key(self) -> tuple[str, str]:
        """Create an admin API key for testing.

        Returns:
            Tuple of (raw_api_key, api_key_id)
        """
        # Generate API key
        raw_api_key = secret.generate_audit_api_key()
        api_key_id = uid.generate_category_uid("apikey", length=16)

        # Create key record
        api_key_record = {
            "id": api_key_id,
            "created_at": schema.DateTime.utcnow(),
            "key_hash": secret.hash_api_key(raw_api_key),
            "name": "Admin Key",
            "owner_id": "admin",
            "scopes": ["admin"],
        }

        # Insert into storage
        apikeys_storage = campus.storage.tables.get_db("apikeys")
        apikeys_storage.insert_one(api_key_record)

        return raw_api_key, api_key_id

    def _get_auth_headers(self, api_key: str) -> dict:
        """Create authentication headers from API key.

        Args:
            api_key: Raw API key value

        Returns:
            Dict with Authorization header
        """
        return {"Authorization": f"Bearer {api_key}"}

    def _create_lifecycle_key(self, **overrides) -> dict:
        """Create an API key through the audit API itself.

        Uses a fresh admin key to authenticate the POST, so the created
        state under test is exactly what the service produces.

        Returns:
            Response payload: id, api_key (plaintext, shown once),
            name, owner_id, scopes, created_at
        """
        admin_key, _ = self._create_admin_api_key()
        body = {
            "name": "Test Lifecycle Key",
            "owner_id": "test-user",
            "scopes": ["read", "write"],
            "rate_limit": 100,
        }
        body.update(overrides)
        response = self.client.post(
            "/audit/v1/apikeys/",
            json=body,
            headers=self._get_auth_headers(admin_key),
        )
        assert response.status_code == 201, (
            f"Lifecycle key creation failed: {response.status_code} "
            f"{response.get_json()}"
        )
        return response.get_json()

    def test_create_api_key_returns_key_value_once(self):
        """Test that API key creation returns the key value exactly once.

        This verifies:
        - POST /audit/v1/apikeys returns 201
        - Response includes plaintext api_key (only shown once)
        - Response includes key metadata (id, name, owner, scopes)
        - Key is stored with hash (not plaintext)
        """
        response = self.client.post(
            "/audit/v1/apikeys/",
            json={
                "name": "Test Lifecycle Key",
                "owner_id": "test-user",
                "scopes": ["read", "write"],
                "rate_limit": 100,
            },
            headers=self._get_auth_headers(self._create_admin_api_key()[0])
        )

        # Verify response
        self.assertEqual(response.status_code, 201)
        data = response.get_json()

        # Should return plaintext key (only time it's shown)
        self.assertIn("api_key", data)
        self.assertIsInstance(data["api_key"], str)
        # API keys are 32 chars (audit_v1_<22-char-base64url>)
        self.assertGreater(len(data["api_key"]), 30)

        # Should return metadata
        self.assertIn("id", data)
        self.assertIn("name", data)
        self.assertIn("owner_id", data)
        self.assertIn("scopes", data)
        self.assertIn("created_at", data)

        # Verify key_hash is NOT exposed
        self.assertNotIn("key_hash", data)

    def test_created_key_stored_with_hash_not_plaintext(self):
        """Test that created key is stored with hash, not plaintext value.

        This verifies security: plaintext key is never stored.
        """
        data = self._create_lifecycle_key()

        # Query storage directly
        apikeys_storage = campus.storage.tables.get_db("apikeys")
        record = apikeys_storage.get_by_id(data["id"])

        # Verify key_hash exists
        self.assertIn("key_hash", record)
        self.assertIsInstance(record["key_hash"], str)

        # Verify hash matches the key value
        expected_hash = secret.hash_api_key(data["api_key"])
        self.assertEqual(record["key_hash"], expected_hash)

        # Verify plaintext key is NOT in storage
        self.assertNotIn("api_key", record)

    def test_created_key_can_authenticate_requests(self):
        """Test that created API key can authenticate requests.

        This verifies:
        - API key works for Bearer authentication against a protected
          endpoint (/audit/v1/health is public and proves nothing)
        - Key verification updates last_used timestamp
        """
        data = self._create_lifecycle_key()
        api_key_id = data["id"]

        # Get initial last_used value (should be None)
        apikeys_storage = campus.storage.tables.get_db("apikeys")
        key_record = apikeys_storage.get_by_id(api_key_id)
        initial_last_used = key_record.get("last_used")
        self.assertIsNone(initial_last_used)

        # Make authenticated request against the protected endpoint
        auth_headers = self._get_auth_headers(data["api_key"])
        response = self.client.get(
            self.PROTECTED_ENDPOINT,
            headers=auth_headers
        )

        # Verify request succeeds
        self.assertEqual(response.status_code, 200)

        # Verify last_used was updated
        updated_record = apikeys_storage.get_by_id(api_key_id)
        self.assertIsNotNone(updated_record.get("last_used"))
        self.assertNotEqual(updated_record.get("last_used"), initial_last_used)

    def test_wrong_key_value_fails_authentication(self):
        """Test that wrong API key value fails authentication.

        This verifies authentication security against a protected
        endpoint (/audit/v1/health is public and accepts any request).
        """
        # Make request with a well-formed key that was never stored
        wrong_key = secret.generate_audit_api_key()
        auth_headers = self._get_auth_headers(wrong_key)

        response = self.client.get(
            self.PROTECTED_ENDPOINT,
            headers=auth_headers
        )

        # Should fail with 401
        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertIn("error", data)

    def test_update_api_key_modifies_stored_values(self):
        """Test that API key can be updated with new values.

        This verifies:
        - PATCH /audit/v1/apikeys/<id> updates mutable fields
        - Updates are persisted to storage
        - Non-mutable fields (id, created_at) cannot be changed
        """
        data = self._create_lifecycle_key()
        api_key_id = data["id"]

        # Update the key
        auth_headers = self._get_auth_headers(data["api_key"])
        response = self.client.patch(
            f"/audit/v1/apikeys/{api_key_id}/",
            json={
                "name": "Updated Lifecycle Key",
                "scopes": ["admin", "read"],
                "rate_limit": 200,
            },
            headers=auth_headers
        )

        # Verify update succeeds
        self.assertEqual(response.status_code, 200)
        updated = response.get_json()

        # Verify fields were updated
        self.assertEqual(updated["name"], "Updated Lifecycle Key")
        self.assertEqual(updated["scopes"], ["admin", "read"])
        self.assertEqual(updated["rate_limit"], 200)

        # Verify immutable fields didn't change
        self.assertEqual(updated["id"], api_key_id)

        # Verify updates persisted to storage
        apikeys_storage = campus.storage.tables.get_db("apikeys")
        record = apikeys_storage.get_by_id(api_key_id)
        self.assertEqual(record["name"], "Updated Lifecycle Key")
        self.assertEqual(record["scopes"], ["admin", "read"])
        self.assertEqual(record["rate_limit"], 200)

    def test_revoke_api_key_marks_as_revoked(self):
        """Test that API key revocation works correctly.

        This verifies:
        - DELETE /audit/v1/apikeys/<id> sets revoked_at timestamp
        - Revoke is idempotent (safe to call multiple times)
        """
        data = self._create_lifecycle_key()
        api_key_id = data["id"]

        # Revoke the key
        auth_headers = self._get_auth_headers(data["api_key"])
        response = self.client.delete(
            f"/audit/v1/apikeys/{api_key_id}/",
            headers=auth_headers
        )

        # Verify revoke succeeds
        self.assertEqual(response.status_code, 204)

        # Verify revoked_at timestamp was set
        apikeys_storage = campus.storage.tables.get_db("apikeys")
        record = apikeys_storage.get_by_id(api_key_id)
        self.assertIsNotNone(record.get("revoked_at"))

        # Test idempotence: revoke again with a still-valid key (the
        # revoked lifecycle key can no longer authenticate anything)
        admin_key, _ = self._create_admin_api_key()
        response2 = self.client.delete(
            f"/audit/v1/apikeys/{api_key_id}/",
            headers=self._get_auth_headers(admin_key)
        )
        # Should also succeed (idempotent)
        self.assertIn(response2.status_code, [204, 404])

    def test_revoked_key_cannot_authenticate(self):
        """Test that revoked API key cannot authenticate new requests.

        This verifies security: revoked keys are immediately invalid.
        """
        data = self._create_lifecycle_key()

        # Revoke the key
        auth_headers = self._get_auth_headers(data["api_key"])
        response = self.client.delete(
            f"/audit/v1/apikeys/{data['id']}/",
            headers=auth_headers
        )
        self.assertEqual(response.status_code, 204)

        # Try to use revoked key against the protected endpoint
        response = self.client.get(
            self.PROTECTED_ENDPOINT,
            headers=auth_headers
        )

        # Should fail with 401
        self.assertEqual(response.status_code, 401)
        error_data = response.get_json()
        self.assertIn("error", error_data)

    def test_revoked_key_still_exists_in_storage(self):
        """Test that revoked keys are kept in storage for audit trail.

        This verifies:
        - Revoked keys are not deleted from storage
        - GET /audit/v1/apikeys/<id> still works for revoked keys
        - Keys are preserved for audit/compliance purposes
        """
        data = self._create_lifecycle_key()
        api_key_id = data["id"]

        # Revoke the key
        revoke_response = self.client.delete(
            f"/audit/v1/apikeys/{api_key_id}/",
            headers=self._get_auth_headers(data["api_key"])
        )
        self.assertEqual(revoke_response.status_code, 204)

        # Create a fresh admin key (since our test key is revoked)
        admin_key, _ = self._create_admin_api_key()

        # Get revoked key details
        response = self.client.get(
            f"/audit/v1/apikeys/{api_key_id}/",
            headers=self._get_auth_headers(admin_key)
        )

        # Should still exist (not deleted)
        self.assertEqual(response.status_code, 200)
        revoked = response.get_json()

        # Should show as revoked
        self.assertEqual(revoked["id"], api_key_id)
        self.assertIsNotNone(revoked.get("revoked_at"))

        # Verify it's still in storage
        apikeys_storage = campus.storage.tables.get_db("apikeys")
        record = apikeys_storage.get_by_id(api_key_id)
        self.assertIsNotNone(record)
        self.assertIsNotNone(record.get("revoked_at"))


if __name__ == "__main__":
    unittest.main()
