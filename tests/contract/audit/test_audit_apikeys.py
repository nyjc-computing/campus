"""HTTP contract tests for campus.audit API keys endpoints.

These tests verify the HTTP interface contract for the audit/apikeys service.
They test status codes, response formats, and authentication behavior.

API Keys Endpoints Reference:
- POST   /audit/v1/apikeys                    - Create API key (requires auth)
- GET    /audit/v1/apikeys                    - List API keys (requires auth)
- GET    /audit/v1/apikeys/<api_key_id>       - Get API key (requires auth)
- PATCH  /audit/v1/apikeys/<api_key_id>       - Update API key (requires auth)
- DELETE /audit/v1/apikeys/<api_key_id>       - Revoke API key (requires auth)
- POST   /audit/v1/apikeys/<api_key_id>/regenerate - Regenerate API key (requires auth)
"""

import unittest

from campus.common import schema
from campus.common.errors import api_errors
from campus.common.utils import uid, secret
import campus.storage
from tests.fixtures import services


class TestAuditAPIKeysCreateContract(unittest.TestCase):
    """HTTP contract tests for POST /audit/v1/apikeys/ endpoint."""

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager(shared=False)
        cls.manager.initialize()
        cls.app = cls.manager.audit_app

        # Initialize API keys storage
        from campus.audit.resources.apikeys import APIKeysResource
        APIKeysResource.init_storage()

        # Initialize API keys storage
        from campus.audit.resources.apikeys import APIKeysResource
        APIKeysResource.init_storage()

    @classmethod
    def tearDownClass(cls):
        cls.manager.cleanup()

    def setUp(self):
        self.manager.clear_test_data()
        assert self.app
        self.client = self.app.test_client()

        # Create a test audit API key for authentication
        from campus.audit.resources.apikeys import APIKeysResource
        from campus.common.utils import secret
        APIKeysResource.init_storage()

        # Generate and properly hash the API key
        raw_api_key = secret.generate_audit_api_key()
        api_key_id = uid.generate_category_uid("apikey", length=16)
        from campus.common import schema
        test_key_record = {
            "id": api_key_id,
            "created_at": schema.DateTime.utcnow(),
            "key_hash": secret.hash_api_key(raw_api_key),  # Store the hash
            "name": "Test Auth Key",
            "owner_id": "test-user",
            "scopes": ["admin"],
        }
        # Lazy import storage to avoid initializing before test mode
        apikeys_storage = campus.storage.tables.get_db("apikeys")
        apikeys_storage.insert_one(test_key_record)

        # Use the raw API key for authentication (will be hashed and compared)
        self.auth_headers = {"Authorization": f"Bearer {raw_api_key}"}

    def test_create_api_key_requires_authentication(self):
        """POST /audit/v1/apikeys/ requires authentication."""
        response = self.client.post(
            "/audit/v1/apikeys/",
            json={
                "name": "Test Key",
                "owner_id": "user123",
                "scopes": ["read"],
            }
        )

        self.assertEqual(response.status_code, 401)

    def test_create_api_key_success_returns_201(self):
        """POST /audit/v1/apikeys/ returns 201 on success."""
        response = self.client.post(
            "/audit/v1/apikeys/",
            json={
                "name": "Test Key",
                "owner_id": "user123",
                "scopes": ["read"],
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertIn("id", data)
        self.assertIn("api_key", data)  # Plaintext key returned once at creation
        self.assertEqual(data["name"], "Test Key")
        self.assertEqual(data["owner_id"], "user123")

    def test_create_api_key_with_optional_fields(self):
        """POST /audit/v1/apikeys/ accepts rate_limit and expires_at."""
        response = self.client.post(
            "/audit/v1/apikeys/",
            json={
                "name": "Test Key",
                "owner_id": "user123",
                "scopes": ["read", "write"],
                "rate_limit": 100,
                "expires_at": "2025-12-31T23:59:59Z",
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertEqual(data["rate_limit"], 100)
        self.assertEqual(data["expires_at"], "2025-12-31T23:59:59Z")
        self.assertEqual(data["scopes"], ["read", "write"])

    def test_create_api_key_missing_name_returns_422(self):
        """POST /audit/v1/apikeys/ without name returns 422."""
        response = self.client.post(
            "/audit/v1/apikeys/",
            json={
                "owner_id": "user123",
                "scopes": ["read"],
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 422)

    def test_create_api_key_missing_owner_id_returns_422(self):
        """POST /audit/v1/apikeys/ without owner_id returns 422."""
        response = self.client.post(
            "/audit/v1/apikeys/",
            json={
                "name": "Test Key",
                "scopes": ["read"],
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 422)

    def test_create_api_key_returns_unique_id(self):
        """POST /audit/v1/apikeys/ returns unique ID for each key."""
        response1 = self.client.post(
            "/audit/v1/apikeys/",
            json={
                "name": "Key 1",
                "owner_id": "user123",
                "scopes": ["read"],
            },
            headers=self.auth_headers
        )

        response2 = self.client.post(
            "/audit/v1/apikeys/",
            json={
                "name": "Key 2",
                "owner_id": "user123",
                "scopes": ["read"],
            },
            headers=self.auth_headers
        )

        data1 = response1.get_json()
        data2 = response2.get_json()

        self.assertNotEqual(data1["id"], data2["id"])


class TestAuditAPIKeysListContract(unittest.TestCase):
    """HTTP contract tests for GET /audit/v1/apikeys/ endpoint."""

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager(shared=False)
        cls.manager.initialize()
        cls.app = cls.manager.audit_app

        # Initialize API keys storage
        from campus.audit.resources.apikeys import APIKeysResource
        APIKeysResource.init_storage()

        # Create some test API keys
        from campus.audit.resources import apikeys
        cls.api_key1, _ = apikeys.new(
            name="Key 1",
            owner_id="user1",
            scopes="read",
        )
        cls.api_key2, _ = apikeys.new(
            name="Key 2",
            owner_id="user2",
            scopes="read,write",
        )
        cls.api_key3, _ = apikeys.new(
            name="Key 3",
            owner_id="user1",
            scopes="admin",
        )

    @classmethod
    def tearDownClass(cls):
        cls.manager.cleanup()

    def setUp(self):
        assert self.app
        self.client = self.app.test_client()

        # Create a test audit API key for authentication
        from campus.common.utils import secret
        raw_api_key = secret.generate_audit_api_key()
        api_key_id = uid.generate_category_uid("apikey", length=16)
        test_key_record = {
            "id": api_key_id,
            "created_at": schema.DateTime.utcnow(),
            "key_hash": secret.hash_api_key(raw_api_key),
            "name": "Test Auth Key",
            "owner_id": "test-user",
            "scopes": ["admin"],
        }
        # Lazy import storage to avoid initializing before test mode
        apikeys_storage = campus.storage.tables.get_db("apikeys")
        apikeys_storage.insert_one(test_key_record)

        # Use the raw API key for authentication
        self.auth_headers = {"Authorization": f"Bearer {raw_api_key}"}

    def test_list_api_keys_requires_authentication(self):
        """GET /audit/v1/apikeys/ requires authentication."""
        response = self.client.get("/audit/v1/apikeys/")

        self.assertEqual(response.status_code, 401)

    def test_list_api_keys_returns_keys(self):
        """GET /audit/v1/apikeys/ returns list of API keys."""
        response = self.client.get(
            "/audit/v1/apikeys/",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("api_keys", data)
        self.assertIn("count", data)
        self.assertIsInstance(data["api_keys"], list)
        self.assertGreaterEqual(len(data["api_keys"]), 3)

    def test_list_api_keys_excludes_key_hash(self):
        """GET /audit/v1/apikeys/ excludes key_hash from responses."""
        response = self.client.get(
            "/audit/v1/apikeys/",
            headers=self.auth_headers
        )

        data = response.get_json()
        for key in data["api_keys"]:
            self.assertNotIn("key_hash", key)

    def test_list_api_keys_with_owner_filter(self):
        """GET /audit/v1/apikeys/?owner_id=user1 filters by owner."""
        response = self.client.get(
            "/audit/v1/apikeys/?owner_id=user1",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        for key in data["api_keys"]:
            self.assertEqual(key["owner_id"], "user1")

    def test_list_api_keys_with_limit(self):
        """GET /audit/v1/apikeys/?limit=2 respects limit parameter."""
        response = self.client.get(
            "/audit/v1/apikeys/?limit=2",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertLessEqual(len(data["api_keys"]), 2)

    def test_list_api_keys_with_active_only_true(self):
        """GET /audit/v1/apikeys/?active_only=true filters out revoked keys."""
        # Revoke one key
        from campus.audit.resources import apikeys
        apikeys[self.api_key1.id].revoke()

        response = self.client.get(
            "/audit/v1/apikeys/?active_only=true",
            headers=self.auth_headers
        )

        data = response.get_json()
        # Revoked key should not appear
        for key in data["api_keys"]:
            self.assertNotEqual(key["id"], self.api_key1.id)


class TestAuditAPIKeyGetContract(unittest.TestCase):
    """HTTP contract tests for GET /audit/v1/apikeys/<api_key_id>/ endpoint."""

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager(shared=False)
        cls.manager.initialize()
        cls.app = cls.manager.audit_app

        # Initialize API keys storage
        from campus.audit.resources.apikeys import APIKeysResource
        APIKeysResource.init_storage()

        # Create a test API key
        from campus.audit.resources import apikeys
        cls.test_key, _ = apikeys.new(
            name="Test Key",
            owner_id="user123",
            scopes="read,write",
            rate_limit=100,
        )

    @classmethod
    def tearDownClass(cls):
        cls.manager.cleanup()

    def setUp(self):
        assert self.app
        self.client = self.app.test_client()

        # Create a test audit API key for authentication
        from campus.common.utils import secret
        raw_api_key = secret.generate_audit_api_key()
        api_key_id = uid.generate_category_uid("apikey", length=16)
        test_key_record = {
            "id": api_key_id,
            "created_at": schema.DateTime.utcnow(),
            "key_hash": secret.hash_api_key(raw_api_key),
            "name": "Test Auth Key",
            "owner_id": "test-user",
            "scopes": ["admin"],
        }
        # Lazy import storage to avoid initializing before test mode
        apikeys_storage = campus.storage.tables.get_db("apikeys")
        apikeys_storage.insert_one(test_key_record)

        # Use the raw API key for authentication
        self.auth_headers = {"Authorization": f"Bearer {raw_api_key}"}

    def test_get_api_key_requires_authentication(self):
        """GET /audit/v1/apikeys/<id> requires authentication."""
        response = self.client.get(f"/audit/v1/apikeys/{self.test_key.id}/")

        self.assertEqual(response.status_code, 401)

    def test_get_api_key_success(self):
        """GET /audit/v1/apikeys/<id> returns 200 with key details."""
        response = self.client.get(
            f"/audit/v1/apikeys/{self.test_key.id}/",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["id"], self.test_key.id)
        self.assertEqual(data["name"], "Test Key")
        self.assertEqual(data["owner_id"], "user123")
        self.assertEqual(data["rate_limit"], 100)

    def test_get_api_key_excludes_key_hash(self):
        """GET /audit/v1/apikeys/<id> excludes key_hash from response."""
        response = self.client.get(
            f"/audit/v1/apikeys/{self.test_key.id}/",
            headers=self.auth_headers
        )

        data = response.get_json()
        self.assertNotIn("key_hash", data)

    def test_get_api_key_not_found_returns_404(self):
        """GET /audit/v1/apikeys/<id> with non-existent key returns 404."""
        response = self.client.get(
            "/audit/v1/apikeys/doesnotexist/",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 404)


class TestAuditAPIKeyUpdateContract(unittest.TestCase):
    """HTTP contract tests for PATCH /audit/v1/apikeys/<api_key_id>/ endpoint."""

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager(shared=False)
        cls.manager.initialize()
        cls.app = cls.manager.audit_app

        # Initialize API keys storage
        from campus.audit.resources.apikeys import APIKeysResource
        APIKeysResource.init_storage()

        # Create a test API key
        from campus.audit.resources import apikeys
        cls.test_key, _ = apikeys.new(
            name="Original Name",
            owner_id="user123",
            scopes="read",
        )

    @classmethod
    def tearDownClass(cls):
        cls.manager.cleanup()

    def setUp(self):
        assert self.app
        self.client = self.app.test_client()

        # Create a test audit API key for authentication
        from campus.common.utils import secret
        raw_api_key = secret.generate_audit_api_key()
        api_key_id = uid.generate_category_uid("apikey", length=16)
        test_key_record = {
            "id": api_key_id,
            "created_at": schema.DateTime.utcnow(),
            "key_hash": secret.hash_api_key(raw_api_key),
            "name": "Test Auth Key",
            "owner_id": "test-user",
            "scopes": ["admin"],
        }
        # Lazy import storage to avoid initializing before test mode
        apikeys_storage = campus.storage.tables.get_db("apikeys")
        apikeys_storage.insert_one(test_key_record)

        # Use the raw API key for authentication
        self.auth_headers = {"Authorization": f"Bearer {raw_api_key}"}

    def test_update_api_key_requires_authentication(self):
        """PATCH /audit/v1/apikeys/<id> requires authentication."""
        response = self.client.patch(
            f"/audit/v1/apikeys/{self.test_key.id}/",
            json={"name": "Updated Name"}
        )

        self.assertEqual(response.status_code, 401)

    def test_update_api_key_name_success(self):
        """PATCH /audit/v1/apikeys/<id> can update name."""
        response = self.client.patch(
            f"/audit/v1/apikeys/{self.test_key.id}/",
            json={"name": "Updated Name"},
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["name"], "Updated Name")

    def test_update_api_key_scopes_success(self):
        """PATCH /audit/v1/apikeys/<id> can update scopes."""
        response = self.client.patch(
            f"/audit/v1/apikeys/{self.test_key.id}/",
            json={"scopes": ["read", "write", "admin"]},
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["scopes"], ["read", "write", "admin"])

    def test_update_api_key_rate_limit_success(self):
        """PATCH /audit/v1/apikeys/<id> can update rate_limit."""
        response = self.client.patch(
            f"/audit/v1/apikeys/{self.test_key.id}/",
            json={"rate_limit": 200},
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["rate_limit"], 200)

    def test_update_api_key_multiple_fields(self):
        """PATCH /audit/v1/apikeys/<id> can update multiple fields at once."""
        response = self.client.patch(
            f"/audit/v1/apikeys/{self.test_key.id}/",
            json={
                "name": "New Name",
                "scopes": ["admin"],
                "rate_limit": 500,
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["name"], "New Name")
        self.assertEqual(data["scopes"], ["admin"])
        self.assertEqual(data["rate_limit"], 500)

    def test_update_api_key_no_fields_returns_400(self):
        """PATCH /audit/v1/apikeys/<id> with no fields returns 400."""
        response = self.client.patch(
            f"/audit/v1/apikeys/{self.test_key.id}/",
            json={},
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 400)

    def test_update_api_key_not_found_returns_404(self):
        """PATCH /audit/v1/apikeys/<id> with non-existent key returns 404."""
        response = self.client.patch(
            "/audit/v1/apikeys/doesnotexist/",
            json={"name": "Updated"},
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 404)


class TestAuditAPIKeyRevokeContract(unittest.TestCase):
    """HTTP contract tests for DELETE /audit/v1/apikeys/<api_key_id>/ endpoint."""

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager(shared=False)
        cls.manager.initialize()
        cls.app = cls.manager.audit_app

        # Initialize API keys storage
        from campus.audit.resources.apikeys import APIKeysResource
        APIKeysResource.init_storage()

    @classmethod
    def tearDownClass(cls):
        cls.manager.cleanup()

    def setUp(self):
        # Create a fresh key for each test
        from campus.audit.resources import apikeys
        self.test_key, _ = apikeys.new(
            name="Test Key",
            owner_id="user123",
            scopes="read",
        )
        assert self.app
        self.client = self.app.test_client()

        # Create a test audit API key for authentication
        raw_api_key = secret.generate_audit_api_key()
        api_key_id = uid.generate_category_uid("apikey", length=16)
        test_key_record = {
            "id": api_key_id,
            "created_at": schema.DateTime.utcnow(),
            "key_hash": secret.hash_api_key(raw_api_key),
            "name": "Test Auth Key",
            "owner_id": "test-user",
            "scopes": ["admin"],
        }
        # Lazy import storage to avoid initializing before test mode
        apikeys_storage = campus.storage.tables.get_db("apikeys")
        apikeys_storage.insert_one(test_key_record)

        # Use the raw API key for authentication
        self.auth_headers = {"Authorization": f"Bearer {raw_api_key}"}

    def test_revoke_api_key_requires_authentication(self):
        """DELETE /audit/v1/apikeys/<id> requires authentication."""
        response = self.client.delete(f"/audit/v1/apikeys/{self.test_key.id}/")

        self.assertEqual(response.status_code, 401)

    def test_revoke_api_key_returns_204(self):
        """DELETE /audit/v1/apikeys/<id> returns 204 on success."""
        response = self.client.delete(
            f"/audit/v1/apikeys/{self.test_key.id}/",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 204)
        # 204 should have no body
        self.assertEqual(response.data, b"")

    def test_revoke_api_key_marks_as_revoked(self):
        """DELETE /audit/v1/apikeys/<id> actually revokes the key."""
        # Revoke the key
        self.client.delete(
            f"/audit/v1/apikeys/{self.test_key.id}/",
            headers=self.auth_headers
        )

        # Try to get it - should still exist but be revoked
        response = self.client.get(
            f"/audit/v1/apikeys/{self.test_key.id}/",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIsNotNone(data.get("revoked_at"))

    def test_revoke_api_key_not_found_returns_404(self):
        """DELETE /audit/v1/apikeys/<id> with non-existent key returns 404."""
        response = self.client.delete(
            "/audit/v1/apikeys/doesnotexist/",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 404)

    def test_revoke_api_key_idempotent(self):
        """DELETE /audit/v1/apikeys/<id> multiple times is safe."""
        # First revoke
        response1 = self.client.delete(
            f"/audit/v1/apikeys/{self.test_key.id}/",
            headers=self.auth_headers
        )
        self.assertEqual(response1.status_code, 204)

        # Second revoke should also succeed (or return 404 - both are acceptable)
        response2 = self.client.delete(
            f"/audit/v1/apikeys/{self.test_key.id}/",
            headers=self.auth_headers
        )
        self.assertIn(response2.status_code, [204, 404])


class TestAuditAPIKeyRegenerateContract(unittest.TestCase):
    """HTTP contract tests for POST /audit/v1/apikeys/<api_key_id>/regenerate endpoint."""

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager(shared=False)
        cls.manager.initialize()
        cls.app = cls.manager.audit_app

        # Initialize API keys storage
        from campus.audit.resources.apikeys import APIKeysResource
        APIKeysResource.init_storage()

    @classmethod
    def tearDownClass(cls):
        cls.manager.cleanup()

    def setUp(self):
        # Create a fresh key for each test
        from campus.audit.resources import apikeys
        self.test_key, _ = apikeys.new(
            name="Test Key",
            owner_id="user123",
            scopes="read",
        )
        assert self.app
        self.client = self.app.test_client()

        # Create a test audit API key for authentication
        raw_api_key = secret.generate_audit_api_key()
        api_key_id = uid.generate_category_uid("apikey", length=16)
        test_key_record = {
            "id": api_key_id,
            "created_at": schema.DateTime.utcnow(),
            "key_hash": secret.hash_api_key(raw_api_key),
            "name": "Test Auth Key",
            "owner_id": "test-user",
            "scopes": ["admin"],
        }
        # Lazy import storage to avoid initializing before test mode
        apikeys_storage = campus.storage.tables.get_db("apikeys")
        apikeys_storage.insert_one(test_key_record)

        # Use the raw API key for authentication
        self.auth_headers = {"Authorization": f"Bearer {raw_api_key}"}

    def test_regenerate_api_key_requires_authentication(self):
        """POST /audit/v1/apikeys/<id>/regenerate requires authentication."""
        response = self.client.post(f"/audit/v1/apikeys/{self.test_key.id}/regenerate")

        self.assertEqual(response.status_code, 401)

    def test_regenerate_api_key_returns_200(self):
        """POST /audit/v1/apikeys/<id>/regenerate returns 200 with new key."""
        response = self.client.post(
            f"/audit/v1/apikeys/{self.test_key.id}/regenerate",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("key", data)
        # New key should be returned and different from original
        self.assertIsInstance(data["key"], str)

    def test_regenerate_api_key_changes_the_value(self):
        """POST /audit/v1/apikeys/<id>/regenerate actually changes the key value."""
        # Get original key hash (we can't get the plaintext, but we can verify it changed)
        from campus.audit.resources import apikeys
        original_key = apikeys[self.test_key.id].get()
        assert original_key
        original_hash = original_key.key_hash

        # Regenerate
        response = self.client.post(
            f"/audit/v1/apikeys/{self.test_key.id}/regenerate",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)

        # Verify hash changed
        regenerated_key = apikeys[self.test_key.id].get()
        assert regenerated_key
        self.assertNotEqual(regenerated_key.key_hash, original_hash)

    def test_regenerate_api_key_not_found_returns_404(self):
        """POST /audit/v1/apikeys/<id>/regenerate with non-existent key returns 404."""
        response = self.client.post(
            "/audit/v1/apikeys/doesnotexist/regenerate",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 404)

    def test_regenerate_api_key_preserves_other_fields(self):
        """POST /audit/v1/apikeys/<id>/regenerate preserves name, scopes, etc."""
        from campus.audit.resources import apikeys

        # Regenerate
        self.client.post(
            f"/audit/v1/apikeys/{self.test_key.id}/regenerate",
            headers=self.auth_headers
        )

        # Verify other fields unchanged
        key = apikeys[self.test_key.id].get()
        assert key
        self.assertEqual(key.name, "Test Key")
        self.assertEqual(key.owner_id, "user123")
        self.assertEqual(key.scopes, ["read"])


@unittest.skip("https://github.com/nyjc-computing/campus/issues/569 - Input validation bugs")
class TestAuditAPIKeysEdgeCases(unittest.TestCase):
    """HTTP contract tests for edge cases and error conditions.

    Tests duplicate keys, invalid inputs, and boundary conditions.
    """

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager(shared=False)
        cls.manager.initialize()
        cls.app = cls.manager.audit_app

        # Initialize API keys storage
        from campus.audit.resources.apikeys import APIKeysResource
        APIKeysResource.init_storage()

    @classmethod
    def tearDownClass(cls):
        cls.manager.cleanup()

    def setUp(self):
        self.manager.clear_test_data()
        assert self.app
        self.client = self.app.test_client()

        # Create a test audit API key for authentication
        from campus.audit.resources.apikeys import APIKeysResource
        from campus.common.utils import secret
        APIKeysResource.init_storage()

        raw_api_key = secret.generate_audit_api_key()
        api_key_id = uid.generate_category_uid("apikey", length=16)
        test_key_record = {
            "id": api_key_id,
            "created_at": schema.DateTime.utcnow(),
            "key_hash": secret.hash_api_key(raw_api_key),
            "name": "Test Auth Key",
            "owner_id": "test-user",
            "scopes": ["admin"],
        }
        apikeys_storage = campus.storage.tables.get_db("apikeys")
        apikeys_storage.insert_one(test_key_record)

        self.auth_headers = {"Authorization": f"Bearer {raw_api_key}"}

    def test_create_api_key_invalid_format_returns_401(self):
        """POST /audit/v1/apikeys/ with invalid API key format returns 401."""
        response = self.client.post(
            "/audit/v1/apikeys/",
            json={
                "name": "Test Key",
                "owner_id": "user123",
                "scopes": ["read"],
            },
            headers={"Authorization": "Bearer invalid_key_format"}
        )

        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertIn("error", data)

    def test_create_api_key_expired_key_returns_401(self):
        """POST /audit/v1/apikeys/ with expired API key returns 401."""
        from campus.common.utils import secret
        import campus.storage

        # Create an expired API key
        expired_key_value = secret.generate_audit_api_key()
        expired_key_id = uid.generate_category_uid("apikey", length=16)
        from datetime import datetime, timedelta
        expired_record = {
            "id": expired_key_id,
            "created_at": schema.DateTime.utcnow(),
            "key_hash": secret.hash_api_key(expired_key_value),
            "name": "Expired Key",
            "owner_id": "test-user",
            "scopes": ["admin"],
            "expires_at": schema.DateTime.utcnow() - timedelta(days=1),  # Expired
        }
        apikeys_storage = campus.storage.tables.get_db("apikeys")
        apikeys_storage.insert_one(expired_record)

        response = self.client.post(
            "/audit/v1/apikeys/",
            json={
                "name": "Test Key",
                "owner_id": "user123",
                "scopes": ["read"],
            },
            headers={"Authorization": f"Bearer {expired_key_value}"}
        )

        # Should return 401 (expired keys are invalid)
        self.assertEqual(response.status_code, 401)

    def test_create_api_key_revoked_key_returns_401(self):
        """POST /audit/v1/apikeys/ with revoked API key returns 401."""
        from campus.common.utils import secret
        import campus.storage

        # Create a revoked API key
        revoked_key_value = secret.generate_audit_api_key()
        revoked_key_id = uid.generate_category_uid("apikey", length=16)
        revoked_record = {
            "id": revoked_key_id,
            "created_at": schema.DateTime.utcnow(),
            "key_hash": secret.hash_api_key(revoked_key_value),
            "name": "Revoked Key",
            "owner_id": "test-user",
            "scopes": ["admin"],
            "revoked_at": schema.DateTime.utcnow(),  # Revoked
        }
        apikeys_storage = campus.storage.tables.get_db("apikeys")
        apikeys_storage.insert_one(revoked_record)

        response = self.client.post(
            "/audit/v1/apikeys/",
            json={
                "name": "Test Key",
                "owner_id": "user123",
                "scopes": ["read"],
            },
            headers={"Authorization": f"Bearer {revoked_key_value}"}
        )

        # Should return 401 (revoked keys are invalid)
        self.assertEqual(response.status_code, 401)

    def test_create_api_key_empty_name_returns_422(self):
        """POST /audit/v1/apikeys/ with empty name returns 422."""
        response = self.client.post(
            "/audit/v1/apikeys/",
            json={
                "name": "",
                "owner_id": "user123",
                "scopes": ["read"],
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 422)

    def test_create_api_key_empty_owner_id_returns_422(self):
        """POST /audit/v1/apikeys/ with empty owner_id returns 422."""
        response = self.client.post(
            "/audit/v1/apikeys/",
            json={
                "name": "Test Key",
                "owner_id": "",
                "scopes": ["read"],
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 422)

    def test_create_api_key_empty_scopes_returns_422(self):
        """POST /audit/v1/apikeys/ with empty scopes returns 422."""
        response = self.client.post(
            "/audit/v1/apikeys/",
            json={
                "name": "Test Key",
                "owner_id": "user123",
                "scopes": [],
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 422)

    def test_create_api_key_invalid_scopes_type_returns_422(self):
        """POST /audit/v1/apikeys/ with non-array scopes returns 422."""
        response = self.client.post(
            "/audit/v1/apikeys/",
            json={
                "name": "Test Key",
                "owner_id": "user123",
                "scopes": "read",  # Should be array, not string
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 422)

    def test_create_api_key_invalid_rate_limit_type_returns_422(self):
        """POST /audit/v1/apikeys/ with non-integer rate_limit returns 422."""
        response = self.client.post(
            "/audit/v1/apikeys/",
            json={
                "name": "Test Key",
                "owner_id": "user123",
                "scopes": ["read"],
                "rate_limit": "unlimited",  # Should be int, not string
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 422)

    def test_update_api_key_empty_name_returns_422(self):
        """PATCH /audit/v1/apikeys/<id> with empty name returns 422."""
        from campus.audit.resources import apikeys
        test_key, _ = apikeys.new(name="Test", owner_id="user123", scopes="read")

        response = self.client.patch(
            f"/audit/v1/apikeys/{test_key.id}/",
            json={"name": ""},
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 422)

    def test_update_api_key_empty_scopes_returns_422(self):
        """PATCH /audit/v1/apikeys/<id> with empty scopes returns 422."""
        from campus.audit.resources import apikeys
        test_key, _ = apikeys.new(name="Test", owner_id="user123", scopes="read")

        response = self.client.patch(
            f"/audit/v1/apikeys/{test_key.id}/",
            json={"scopes": []},
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 422)

    def test_update_revoked_key_fails(self):
        """PATCH /audit/v1/apikeys/<id> on revoked key should fail."""
        from campus.audit.resources import apikeys
        test_key, _ = apikeys.new(name="Test", owner_id="user123", scopes="read")

        # Revoke the key
        apikeys[test_key.id].revoke()

        # Try to update it
        response = self.client.patch(
            f"/audit/v1/apikeys/{test_key.id}/",
            json={"name": "New Name"},
            headers=self.auth_headers
        )

        # Should fail (404 or 403 depending on implementation)
        self.assertIn(response.status_code, [404, 403])

    def test_list_with_invalid_limit_returns_400(self):
        """GET /audit/v1/apikeys/?limit=invalid with non-integer limit returns 400."""
        response = self.client.get(
            "/audit/v1/apikeys/?limit=notanumber",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 400)

    def test_get_with_invalid_id_format_returns_404(self):
        """GET /audit/v1/apikeys/<id> with invalid ID format returns 404."""
        response = self.client.get(
            "/audit/v1/apikeys/invalid-id-format/",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
