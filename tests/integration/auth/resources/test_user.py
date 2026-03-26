"""campus.tests.integration.auth.resources.test_user

Integration tests for UsersResource.

These tests verify the auto-provisioning behavior for user records
during OAuth login flows, including storage interactions.

IMPORTANT: Lazy imports are required to avoid storage initialization
before test mode is configured (see AGENTS.md - Storage Initialization Order).
"""

import unittest
from campus.common import schema


class TestUsersResourceGetOrCreate(unittest.TestCase):
    """Integration tests for UsersResource.get_or_create() method."""

    @classmethod
    def setUpClass(cls):
        """Configure test storage and import resources once before all tests."""
        # MUST configure test storage BEFORE importing auth resources
        import campus.storage.testing
        campus.storage.testing.configure_test_storage()

        # Lazy import after test mode is configured
        from campus.auth.resources.user import UsersResource

        # Initialize storage schema
        UsersResource.init_storage()

        cls.UsersResource = UsersResource
        cls.resource = UsersResource()

    @classmethod
    def tearDownClass(cls):
        """Clean up test storage after all tests."""
        import campus.storage.testing
        campus.storage.testing.reset_test_storage()

    def setUp(self):
        """Clean and reinitialize storage before each test."""
        import campus.storage.testing
        campus.storage.testing.reset_test_storage()
        # Reinitialize table schema after reset
        self.UsersResource.init_storage()

    def test_get_or_create_creates_new_user_when_not_exists(self):
        """Should create a new user record when email doesn't exist in database."""
        email = schema.Email("new_user1@example.com")
        name = "New_User1"
        user_id = schema.UserID(email)

        user = self.resource.get_or_create(email, name)

        # Verify user was created
        self.assertIsNotNone(user)
        self.assertEqual(user.email, email)
        self.assertEqual(user.name, name)
        # Verify can retrieve from storage
        retrieved_user = self.resource[user_id].get()
        self.assertEqual(retrieved_user.id, user.id)

    def test_get_or_create_returns_existing_user_when_exists(self):
        """Should return existing user record without creating duplicate."""
        email = schema.Email("new_user2@example.com")
        name = "New_User2"

        # Create user first
        original_user = self.resource.new(email=email, name=name)
        self.assertIsNotNone(original_user)
        self.assertEqual(original_user.email, email)

        # get_or_create should return same user
        retrieved_user = self.resource.get_or_create(email, name)
        self.assertIsNotNone(retrieved_user)
        self.assertEqual(retrieved_user.id, original_user.id)
        self.assertEqual(retrieved_user.created_at, original_user.created_at)
        self.assertEqual(retrieved_user.email, original_user.email)
        self.assertEqual(retrieved_user.name, original_user.name)

    def test_get_or_create_idempotent_multiple_calls(self):
        """Should return same user record across multiple calls with same email."""
        email = schema.Email("new_user3@example.com")
        name = "New_User3"

        # First call creates the user
        first_user = self.resource.get_or_create(email, name)
        self.assertIsNotNone(first_user)

        # Subsequent calls should return same user
        second_user = self.resource.get_or_create(email, name)
        third_user = self.resource.get_or_create(email, name)

        self.assertEqual(first_user.id, second_user.id)
        self.assertEqual(first_user.id, third_user.id)
        self.assertEqual(first_user.created_at, second_user.created_at)
        self.assertEqual(first_user.created_at, third_user.created_at)

    def test_new_creates_user_with_activated_at(self):
        """Should create user with activated_at timestamp when provided."""
        email = schema.Email("new_user4@example.com")
        name = "New_User4"
        activated_at = schema.DateTime.utcnow()

        user = self.resource.new(email=email, name=name, activated_at=activated_at)

        self.assertIsNotNone(user)
        self.assertEqual(user.email, email)
        self.assertEqual(user.name, name)
        self.assertIsNotNone(user.activated_at)

    def test_new_creates_user_without_activated_at(self):
        """Should create user with null activated_at when not provided."""
        email = schema.Email("new_user5@example.com")
        name = "New_User5"

        user = self.resource.new(email=email, name=name)

        self.assertIsNotNone(user)
        self.assertEqual(user.email, email)
        self.assertEqual(user.name, name)
        self.assertIsNone(user.activated_at)

    def test_list_returns_all_users(self):
        """Should return list of all users in storage."""
        # Create multiple users
        self.resource.new(email=schema.Email("user1@example.com"), name="User1")
        self.resource.new(email=schema.Email("user2@example.com"), name="User2")
        self.resource.new(email=schema.Email("user3@example.com"), name="User3")

        users = self.resource.list()

        self.assertEqual(len(users), 3)
        emails = {u.email for u in users}
        self.assertEqual(emails, {"user1@example.com", "user2@example.com", "user3@example.com"})


class TestUserResource(unittest.TestCase):
    """Integration tests for UserResource methods."""

    @classmethod
    def setUpClass(cls):
        """Configure test storage and import resources once before all tests."""
        # MUST configure test storage BEFORE importing auth resources
        import campus.storage.testing
        campus.storage.testing.configure_test_storage()

        # Lazy import after test mode is configured
        from campus.auth.resources.user import UsersResource

        # Initialize storage schema
        UsersResource.init_storage()

        cls.UsersResource = UsersResource
        cls.resource = UsersResource()

    @classmethod
    def tearDownClass(cls):
        """Clean up test storage after all tests."""
        import campus.storage.testing
        campus.storage.testing.reset_test_storage()

    def setUp(self):
        """Clean and reinitialize storage before each test."""
        import campus.storage.testing
        campus.storage.testing.reset_test_storage()
        # Reinitialize table schema after reset
        self.UsersResource.init_storage()

    def test_activate_sets_activated_at(self):
        """Should set activated_at timestamp when activating a user."""
        email = schema.Email("new_user6@example.com")
        name = "New_User6"
        user = self.resource.new(email=email, name=name)

        self.assertIsNone(user.activated_at)

        # Activate the user
        user_resource = self.resource[schema.UserID(email)]
        user_resource.activate()

        # Verify activated_at is set
        activated_user = user_resource.get()
        self.assertIsNotNone(activated_user.activated_at)

    def test_delete_removes_user(self):
        """Should remove user from storage when deleted."""
        email = schema.Email("new_user7@example.com")
        name = "New_User7"
        user_id = schema.UserID(email)
        self.resource.new(email=email, name=name)

        # Verify user exists
        self.assertIsNotNone(self.resource[user_id].get())

        # Delete the user
        user_resource = self.resource[user_id]
        user_resource.delete()

        # Verify user is deleted
        from campus.common.errors import api_errors
        with self.assertRaises(api_errors.NotFoundError):
            self.resource[user_id].get()


if __name__ == '__main__':
    unittest.main()
