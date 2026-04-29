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
    """Integration tests for UsersResource.get_or_create() method.

    These tests use the tmpfile-based SQLite pattern for reliable test isolation.
    The database file persists across tests with clear_all_data() providing per-test
    cleanup without destroying the schema or causing "readonly database" errors.
    """

    @classmethod
    def setUpClass(cls):
        """Configure test storage and import resources once before all tests."""
        import campus.storage.testing
        from campus.common import env

        # Configure test mode first
        campus.storage.testing.configure_test_storage()

        # Configure tmpfile-based database (fixed path, avoids readonly errors)
        # This sets SQLITE_URI to a fixed path like /tmp/campus_test.db
        campus.storage.testing.configure_test_db()

        # Lazy import after test mode is configured
        from campus.auth.resources.user import UsersResource

        # Initialize storage schema (creates tables in the tmpfile database)
        UsersResource.init_storage()

        cls.UsersResource = UsersResource
        cls.resource = UsersResource()

    @classmethod
    def tearDownClass(cls):
        """Clean up test storage after all tests."""
        import campus.storage.testing
        # Only clear data, don't reset database (preserves connections)
        campus.storage.testing.clear_all_data()

    def setUp(self):
        """Clean storage before each test without destroying schema."""
        import campus.storage.testing
        # Use clear_all_data() instead of reset_test_storage() to avoid:
        # - "readonly database" errors from stale module-level storage refs
        # - Unnecessary database file recreation
        # - Connection closure issues
        campus.storage.testing.clear_all_data()

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
        # TODO
        pass

    def test_new_creates_user_with_activated_at(self):
        """Should create user with activated_at timestamp when provided."""
        # TODO
        pass

    def test_new_creates_user_without_activated_at(self):
        """Should create user with null activated_at when not provided."""
        # TODO
        pass

    def test_list_returns_all_users(self):
        """Should return list of all users in storage."""
        # Create multiple users
        self.resource.new(email=schema.Email("user1@example.com"), name="User1")
        self.resource.new(email=schema.Email("user2@example.com"), name="User2")
        self.resource.new(email=schema.Email("user3@example.com"), name="User3")

        users = self.resource.list()
        self.assertEqual(len(users), 3)
        emails = {u.email for u in users}
        self.assertEqual(
            emails,
            {"user1@example.com", "user2@example.com", "user3@example.com"}
        )


class TestUserResource(unittest.TestCase):
    """Integration tests for UserResource methods.

    These tests use the tmpfile-based SQLite pattern for reliable test isolation.
    The database file persists across tests with clear_all_data() providing per-test
    cleanup without destroying the schema or causing "readonly database" errors.
    """

    @classmethod
    def setUpClass(cls):
        """Configure test storage and import resources once before all tests."""
        import campus.storage.testing
        from campus.common import env

        # Configure test mode first
        campus.storage.testing.configure_test_storage()

        # Configure tmpfile-based database (fixed path, avoids readonly errors)
        # This sets SQLITE_URI to a fixed path like /tmp/campus_test.db
        campus.storage.testing.configure_test_db()

        # Lazy import after test mode is configured
        from campus.auth.resources.user import UsersResource

        # Initialize storage schema (creates tables in the tmpfile database)
        UsersResource.init_storage()

        cls.UsersResource = UsersResource
        cls.resource = UsersResource()

    @classmethod
    def tearDownClass(cls):
        """Clean up test storage after all tests."""
        import campus.storage.testing
        # Only clear data, don't reset database (preserves connections)
        campus.storage.testing.clear_all_data()

    def setUp(self):
        """Clean storage before each test without destroying schema."""
        import campus.storage.testing
        # Use clear_all_data() instead of reset_test_storage() to avoid:
        # - "readonly database" errors from stale module-level storage refs
        # - Unnecessary database file recreation
        # - Connection closure issues
        campus.storage.testing.clear_all_data()

    def test_activate_sets_activated_at(self):
        """Should set activated_at timestamp when activating a user."""
        # TODO
        pass

    def test_delete_removes_user(self):
        """Should remove user from storage when deleted."""
        # TODO
        pass


if __name__ == '__main__':
    unittest.main()
