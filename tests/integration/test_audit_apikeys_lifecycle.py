"""Integration tests for Audit API Key Lifecycle.

These tests verify end-to-end API key lifecycle operations:
1. Create API key
2. Use API key for authentication
3. Update API key
4. Revoke API key
5. Verify revoked key cannot be used

Tests verify real database operations, authentication, and authorization.

File: tests/integration/test_audit_apikeys_lifecycle.py
Issue: #541
"""

import unittest
from typing import ClassVar

from campus.common import schema
from campus.common.utils import secret, uid
import campus.storage

from tests.fixtures import services
from tests.integration.base import IsolatedIntegrationTestCase


class TestAuditAPIKeyLifecycle(IsolatedIntegrationTestCase):
    """Integration tests for complete API key lifecycle.

    Tests create → authenticate → update → revoke workflow.
    Uses real database and authentication (no mocks).
    """

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
        try:
            apikeys_storage.delete_matching({})
        except campus.storage.errors.NoChangesAppliedError:
            pass  # Table is already empty, which is fine

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

    # Lifecycle Step 1: Create API Key
    def test_01_create_api_key_returns_key_value_once(self):
        """Test that API key creation returns the key value exactly once.

        This verifies:
        - POST /audit/v1/apikeys returns 201
        - Response includes plaintext api_key (only shown once)
        - Response includes key metadata (id, name, owner, scopes)
        - Key is stored with hash (not plaintext)
        """
        # Create admin key for authentication
        admin_key, _ = self._create_admin_api_key()
        auth_headers = self._get_auth_headers(admin_key)

        # Create new API key
        response = self.client.post(
            "/audit/v1/apikeys/",
            json={
                "name": "Test Lifecycle Key",
                "owner_id": "test-user",
                "scopes": ["read", "write"],
                "rate_limit": 100,
            },
            headers=auth_headers
        )

        # Verify response
        self.assertEqual(response.status_code, 201)
        data = response.get_json()

        # Should return plaintext key (only time it's shown)
        self.assertIn("api_key", data)
        self.assertIsInstance(data["api_key"], str)
        self.assertGreater(len(data["api_key"], 20)  # Should be substantial length

        # Should return metadata
        self.assertIn("id", data)
        self.assertIn("name", data)
        self.assertIn("owner_id", data)
        self.assertIn("scopes", data)
        self.assertIn("created_at", data)

        # Verify key_hash is NOT exposed
        self.assertNotIn("key_hash", data)

        # Store for next test
        self.created_key_id = data["id"]
        self.created_key_value = data["api_key"]

    def test_02_created_key_stored_with_hash_not_plaintext(self):
        """Test that created key is stored with hash, not plaintext value.

        This verifies security: plaintext key is never stored.
        """
        # Use key from previous test
        api_key_id = self.created_key_id
        api_key_value = self.created_key_value

        # Query storage directly
        apikeys_storage = campus.storage.tables.get_db("apikeys")
        record = apikeys_storage.get_by_id(api_key_id)

        # Verify key_hash exists
        self.assertIn("key_hash", record)
        self.assertIsInstance(record["key_hash"], str)

        # Verify hash matches the key value
        expected_hash = secret.hash_api_key(api_key_value)
        self.assertEqual(record["key_hash"], expected_hash)

        # Verify plaintext key is NOT in storage
        self.assertNotIn("api_key", record)

    # Lifecycle Step 2: Use API Key for Authentication
    def test_03_created_key_can_authenticate_requests(self):
        """Test that created API key can authenticate requests.

        This verifies:
        - API key works for Bearer authentication
        - Authenticated requests succeed
        - Key verification updates last_used timestamp
        """
        api_key_id = self.created_key_id
        api_key_value = self.created_key_value

        # Get initial last_used value (should be None)
        apikeys_storage = campus.storage.tables.get_db("apikeys")
        key_record = apikeys_storage.get_by_id(api_key_id)
        initial_last_used = key_record.get("last_used")
        self.assertIsNone(initial_last_used)

        # Make authenticated request
        auth_headers = self._get_auth_headers(api_key_value)
        response = self.client.get(
            "/audit/v1/health",
            headers=auth_headers
        )

        # Verify request succeeds
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data.get("status"), "ok")

        # Verify last_used was updated
        updated_record = apikeys_storage.get_by_id(api_key_id)
        self.assertIsNotNone(updated_record.get("last_used"))
        self.assertNotEqual(updated_record.get("last_used"), initial_last_used)

    def test_04_wrong_key_value_fails_authentication(self):
        """Test that wrong API key value fails authentication.

        This verifies authentication security.
        """
        # Make request with wrong key
        wrong_key = secret.generate_audit_api_key()
        auth_headers = self._get_auth_headers(wrong_key)

        response = self.client.get(
            "/audit/v1/health",
            headers=auth_headers
        )

        # Should fail with 401
        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertIn("error", data)

    # Lifecycle Step 3: Update API Key
    def test_05_update_api_key_modifies_stored_values(self):
        """Test that API key can be updated with new values.

        This verifies:
        - PATCH /audit/v1/apikeys/<id> updates mutable fields
        - Updates are persisted to storage
        - Non-mutable fields (id, created_at) cannot be changed
        """
        api_key_id = self.created_key_id
        api_key_value = self.created_key_value

        # Update the key
        auth_headers = self._get_auth_headers(api_key_value)
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
        data = response.get_json()

        # Verify fields were updated
        self.assertEqual(data["name"], "Updated Lifecycle Key")
        self.assertEqual(data["scopes"], ["admin", "read"])
        self.assertEqual(data["rate_limit"], 200)

        # Verify immutable fields didn't change
        self.assertEqual(data["id"], api_key_id)

        # Verify updates persisted to storage
        apikeys_storage = campus.storage.tables.get_db("apikeys")
        record = apikeys_storage.get_by_id(api_key_id)
        self.assertEqual(record["name"], "Updated Lifecycle Key")
        self.assertEqual(record["scopes"], ["admin", "read"])
        self.assertEqual(record["rate_limit"], 200)

    # Lifecycle Step 4: Revoke API Key
    def test_06_revoke_api_key_marks_as_revoked(self):
        """Test that API key revocation works correctly.

        This verifies:
        - DELETE /audit/v1/apikeys/<id> sets revoked_at timestamp
        - Revoked key cannot be used for authentication
        - Revoke is idempotent (safe to call multiple times)
        """
        api_key_id = self.created_key_id
        api_key_value = self.created_key_value

        # Revoke the key
        auth_headers = self._get_auth_headers(api_key_value)
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

        # Test idempotence: revoke again
        response2 = self.client.delete(
            f"/audit/v1/apikeys/{api_key_id}/",
            headers=auth_headers
        )
        # Should also succeed (idempotent)
        self.assertIn(response2.status_code, [204, 404])

    def test_07_revoked_key_cannot_authenticate(self):
        """Test that revoked API key cannot authenticate new requests.

        This verifies security: revoked keys are immediately invalid.
        """
        api_key_id = self.created_key_id
        api_key_value = self.created_key_value

        # Try to use revoked key
        auth_headers = self._get_auth_headers(api_key_value)
        response = self.client.get(
            "/audit/v1/health",
            headers=auth_headers
        )

        # Should fail with 401
        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertIn("error", data)

    def test_08_revoked_key_still_exists_in_storage(self):
        """Test that revoked keys are kept in storage for audit trail.

        This verifies:
        - Revoked keys are not deleted from storage
        - GET /audit/v1/apikeys/<id> still works for revoked keys
        - Keys are preserved for audit/compliance purposes
        """
        api_key_id = self.created_key_id

        # Create a fresh admin key (since our test key is revoked)
        admin_key, _ = self._create_admin_api_key()
        auth_headers = self._get_auth_headers(admin_key)

        # Get revoked key details
        response = self.client.get(
            f"/audit/v1/apikeys/{api_key_id}/",
            headers=auth_headers
        )

        # Should still exist (not deleted)
        self.assertEqual(response.status_code, 200)
        data = response.get_json()

        # Should show as revoked
        self.assertEqual(data["id"], api_key_id)
        self.assertIsNotNone(data.get("revoked_at"))

        # Verify it's still in storage
        apikeys_storage = campus.storage.tables.get_db("apikeys")
        record = apikeys_storage.get_by_id(api_key_id)
        self.assertIsNotNone(record)
        self.assertIsNotNone(record.get("revoked_at"))


if __name__ == "__main__":
    unittest.main()
