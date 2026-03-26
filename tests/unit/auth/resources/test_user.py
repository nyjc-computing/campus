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

    def test_get_or_create_creates_new_user_when_not_exists(self):
        """Should create a new user record when user_id doesn't exist in
        database.
        """
        email = "new_user1@example.com"
        name = "New_User1"
        # Campus uses email as ID
        user_id = schema.UserID(email)
        self.resource.get_or_create(user_id, email, name)
        user_resource_object = self.resource[user_id].get()
        self.assertIsNotNone(user_resource_object)
        self.assertEqual(user_resource_object.email, email)
        self.assertEqual(user_resource_object.name, name)

    
    def test_get_or_create_returns_existing_user_when_exists(self):
        """Should return existing user record without creating
        duplicate.
        """
        # TODO: Arrange: Create a user directly via user_storage.insert_one()
        #   Store the original created_at timestamp
        # Act: Call get_or_create() with the same user_id
        # Assert: Verify returned user has same created_at (no new record)
        #        Verify only one record exists in storage
        email = "new_user2@example.com"
        name = "New_User2"
        # Campus uses email as ID
        user_id = schema.UserID(email)
        user = self.resource.new(id=user_id, email=email, name=name)
        self.assertIsNotNone(user)
        self.assertEqual(user.email, email)
        self.assertEqual(user.name, name)
        user_resource_object = self.resource.get_or_create(user_id, email, name)
        self.assertIsNotNone(user_resource_object)
        self.assertEqual(user_resource_object.email, user.email)
        self.assertEqual(user_resource_object.name, user.name)
        self.assertEqual(user_resource_object.created_at, user.created_at)

    def test_get_or_create_idempotent_multiple_calls(self):
        """Should return same user record across multiple calls with
        same user_id.
        """
        # TODO: Arrange: Create initial setup
        # Act: Call get_or_create() 3 times with same parameters
        # Assert: All returned User objects have same id and created_at

    # Edge cases
    def test_get_or_create_with_empty_name(self):
        """Should handle empty string for name parameter gracefully."""
        # TODO: Decide - should this accept empty name or raise error?
        #        Current implementation accepts empty strings

    def test_get_or_create_with_unicode_in_name(self):
        """Should handle unicode characters and emojis in name
        parameter.
        """

    # Error handling
    def test_get_or_create_handles_storage_error_on_create_failure(self):
        """Should handle database errors gracefully when user creation
        fails.
        """
        # TODO: Consider using monkeypatch to temporarily break storage
        #        Verify error is propagated or handled appropriately
