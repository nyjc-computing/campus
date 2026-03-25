"""Unit tests for UsersResource.get_or_create() method.

These tests verify the auto-provisioning behavior for user records
during OAuth login flows.
"""

import unittest

from campus.auth.resources.user import UsersResource, user_storage
from campus.common import schema
import campus.storage.testing


class TestUsersResourceGetOrCreate(unittest.TestCase):
    """Test cases for UsersResource.get_or_create() method."""

    @classmethod
    def setUpClass(cls):
        """Configure test storage once before all tests."""
        campus.storage.testing.configure_test_storage()
        # Initialize storage schema
        UsersResource.init_storage()
        cls.resource = UsersResource()

    @classmethod
    def tearDownClass(cls):
        """Clean up test storage after all tests."""
        campus.storage.testing.reset_test_storage()

    def setUp(self):
        """Clean storage before each test."""
        campus.storage.testing.reset_test_storage()
        # Re-initialize storage schema after reset
        UsersResource.init_storage()

    def _create_user_directly(self, email: str, name: str) -> schema.UserID:
        """Helper to create a user directly via storage (bypasses resource layer)."""
        user_id = schema.UserID(email)
        user_storage.insert_one({
            "id": str(user_id),
            "created_at": "2024-01-01T00:00:00+00:00",
            "email": email,
            "name": name,
            "activated_at": None
        })
        return user_id

    def test_get_or_create_creates_new_user_when_not_exists(self):
        """Should create a new user record when user_id doesn't exist in database."""
        # Arrange: Set up test parameters
        user_id = schema.UserID("new.user@example.com")
        email = "new.user@example.com"
        name = "New User"

        # Act: Call get_or_create
        result = self.resource.get_or_create(user_id, email, name)

        # Assert: Verify user was created
        self.assertEqual(result.id, user_id)
        self.assertEqual(result.email, email)
        self.assertEqual(result.name, name)
        self.assertIsNone(result.activated_at)

        # Verify user exists in storage
        record = user_storage.get_by_id(user_id)
        self.assertIsNotNone(record)
        self.assertEqual(record["email"], email)

    def test_get_or_create_returns_existing_user_when_exists(self):
        """Should return existing user record without creating duplicate."""
        # Arrange: Create a user directly via storage
        original_user_id = self._create_user_directly("existing@example.com", "Existing User")
        original_user = self.resource[original_user_id].get()
        original_created_at = original_user.created_at

        # Act: Call get_or_create with the same user_id
        result = self.resource.get_or_create(
            schema.UserID("existing@example.com"),
            "existing@example.com",
            "Different Name"
        )

        # Assert: Verify returned user has same created_at (no new record)
        self.assertEqual(result.id, original_user_id)
        self.assertEqual(result.created_at, original_created_at)
        # Original name should be preserved, not updated
        self.assertEqual(result.name, "Existing User")

        # Verify only one record exists in storage
        records = user_storage.get_matching({})
        self.assertEqual(len(records), 1)

    def test_get_or_create_idempotent_multiple_calls(self):
        """Should return same user record across multiple calls with same user_id."""
        # Arrange: Create initial setup
        user_id = schema.UserID("idempotent@example.com")

        # Act: Call get_or_create() 3 times with same parameters
        result1 = self.resource.get_or_create(user_id, "idempotent@example.com", "User One")
        result2 = self.resource.get_or_create(user_id, "idempotent@example.com", "User Two")
        result3 = self.resource.get_or_create(user_id, "idempotent@example.com", "User Three")

        # Assert: All returned User objects have same id and created_at
        self.assertEqual(result1.id, result2.id)
        self.assertEqual(result2.id, result3.id)
        self.assertEqual(result1.created_at, result2.created_at)
        self.assertEqual(result2.created_at, result3.created_at)
        # Name should be from first creation
        self.assertEqual(result1.name, "User One")
        self.assertEqual(result2.name, "User One")
        self.assertEqual(result3.name, "User One")

    def test_get_or_create_with_empty_name(self):
        """Should handle empty string for name parameter."""
        user_id = schema.UserID("empty.name@example.com")

        result = self.resource.get_or_create(user_id, "empty.name@example.com", "")

        self.assertEqual(result.id, user_id)
        self.assertEqual(result.name, "")

    def test_get_or_create_with_unicode_in_name(self):
        """Should handle unicode characters and emojis in name parameter."""
        user_id = schema.UserID("unicode@example.com")

        result = self.resource.get_or_create(
            user_id,
            "unicode@example.com",
            "Tëst Üser 🎓"
        )

        self.assertEqual(result.id, user_id)
        self.assertEqual(result.name, "Tëst Üser 🎓")

    def test_get_or_create_with_special_characters_in_email(self):
        """Should handle valid email addresses with special characters."""
        user_id = schema.UserID("user+tag@example.com")

        result = self.resource.get_or_create(
            user_id,
            "user+tag@example.com",
            "Plus Tag User"
        )

        self.assertEqual(result.id, user_id)
        self.assertEqual(result.email, "user+tag@example.com")


if __name__ == '__main__':
    unittest.main()
