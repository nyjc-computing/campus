"""tests/test_client_apps

Comprehensive black-box unit tests for campus.client.apps:
- **AdminClient**: System administration operations (database management, status monitoring)
- **CirclesClient**: Circle/group management with CRUD operations
- **UsersClient**: User management and profile operations  
- **User**: Resource class for individual user objects

Testing Approach:
- **Black-box methodology**: Tests only public interfaces without internal mocking
- **HTTP layer mocking**: Mocks campus.client.base.HttpClient methods for API simulation
- **Resource pattern validation**: Tests both client interfaces and resource object behavior
- **Cross-client consistency**: Validates that all apps clients follow consistent patterns

Architecture Coverage:
- **Inheritance pattern**: CirclesClient and UsersClient inherit from HttpClient
- **Composition pattern**: AdminClient uses HttpClient via composition
- **Resource objects**: User class for entity-specific operations
- **Public API contracts**: Comprehensive coverage of user-facing methods

These tests ensure the apps client library provides a reliable, consistent
interface for campus service operations across different client patterns.
"""

import unittest
from unittest.mock import Mock, patch

from campus.client.apps import AdminClient, CirclesClient, UsersClient




class TestAdminClient(unittest.TestCase):
    """Test cases for AdminClient class."""

    @patch('campus.config.get_base_url')
    def setUp(self, mock_get_base_url):
        """Set up test fixtures."""
        mock_get_base_url.return_value = "https://apps.example.com"
        self.admin_client = AdminClient()

    def test_init_default_base_url(self):
        """Test AdminClient initialization with default base URL."""
        with patch('campus.config.get_base_url') as mock_get_base_url:
            mock_get_base_url.return_value = "https://apps.default.com"
            client = AdminClient()
            mock_get_base_url.assert_called_once_with("campus.apps")
            self.assertEqual(client._client.base_url,
                             "https://apps.default.com")

    def test_init_custom_base_url(self):
        """Test AdminClient initialization with custom base URL."""
        client = AdminClient("https://custom.apps.com")
        self.assertEqual(client._client.base_url, "https://custom.apps.com")

    def test_status(self):
        """Test getting admin status."""
        with patch.object(self.admin_client, '_client') as mock_client:
            mock_client.get.return_value = {
                "status": "healthy",
                "database": "connected",
                "version": "1.0.0"
            }

            result = self.admin_client.status()

            self.assertEqual(result, {
                "status": "healthy",
                "database": "connected",
                "version": "1.0.0"
            })
            mock_client.get.assert_called_once_with("/admin/status")

    def test_init_db(self):
        """Test database initialization."""
        with patch.object(self.admin_client, '_client') as mock_client:
            mock_client.post.return_value = {
                "action": "init_db",
                "status": "success",
                "message": "Database initialized"
            }

            result = self.admin_client.init_db()

            self.assertEqual(result, {
                "action": "init_db",
                "status": "success",
                "message": "Database initialized"
            })
            mock_client.post.assert_called_once_with("/admin/init-db", data={})

    def test_purge_db(self):
        """Test database purging."""
        with patch.object(self.admin_client, '_client') as mock_client:
            mock_client.post.return_value = {
                "action": "purge_db",
                "status": "success",
                "message": "Database purged"
            }

            result = self.admin_client.purge_db()

            self.assertEqual(result, {
                "action": "purge_db",
                "status": "success",
                "message": "Database purged"
            })
            mock_client.post.assert_called_once_with(
                "/admin/purge-db", data={})


class TestCirclesClient(unittest.TestCase):
    """Test cases for CirclesClient class."""

    @patch('campus.config.get_base_url')
    def setUp(self, mock_get_base_url):
        """Set up test fixtures."""
        mock_get_base_url.return_value = "https://apps.example.com"
        self.circles_client = CirclesClient()

    def test_init_default_base_url(self):
        """Test CirclesClient initialization with default base URL."""
        with patch('campus.config.get_base_url') as mock_get_base_url:
            mock_get_base_url.return_value = "https://apps.default.com"
            client = CirclesClient()
            mock_get_base_url.assert_called_once_with("campus.apps")
            self.assertEqual(client.base_url, "https://apps.default.com")

    def test_init_custom_base_url(self):
        """Test CirclesClient initialization with custom base URL."""
        client = CirclesClient("https://custom.apps.com")
        self.assertEqual(client.base_url, "https://custom.apps.com")

    def test_getitem_returns_circle(self):
        """Test that __getitem__ returns a Circle instance."""
        from campus.client.apps.circles import Circle

        circle = self.circles_client["circle123"]

        self.assertIsInstance(circle, Circle)
        self.assertEqual(circle.id, "circle123")
        self.assertEqual(circle._client, self.circles_client)

    @patch.object(CirclesClient, 'get')
    def test_list_circles(self, mock_get):
        """Test listing circles."""
        mock_get.return_value = {
            "data": [
                {"id": "circle1", "name": "Circle 1"},
                {"id": "circle2", "name": "Circle 2"}
            ]
        }

        result = self.circles_client.list()

        expected = [
            {"id": "circle1", "name": "Circle 1"},
            {"id": "circle2", "name": "Circle 2"}
        ]
        self.assertEqual(result, expected)
        mock_get.assert_called_once_with("/circles", params={})

    @patch.object(CirclesClient, 'get')
    def test_list_circles_with_filters(self, mock_get):
        """Test listing circles with filters."""
        mock_get.return_value = {"data": []}

        self.circles_client.list(name="test", tag="important")

        mock_get.assert_called_once_with(
            "/circles", params={"name": "test", "tag": "important"})

    @patch.object(CirclesClient, 'get')
    def test_list_circles_empty_response(self, mock_get):
        """Test listing circles when response has no data key."""
        mock_get.return_value = {"status": "success"}

        result = self.circles_client.list()

        self.assertEqual(result, [])

    @patch.object(CirclesClient, 'post')
    def test_new_circle(self, mock_post):
        """Test creating a new circle."""
        mock_post.return_value = {
            "circle": {"id": "circle123", "name": "Test Circle", "description": "Test"}
        }

        result = self.circles_client.new(
            name="Test Circle", description="Test")

        self.assertEqual(
            result, {"id": "circle123", "name": "Test Circle", "description": "Test"})
        mock_post.assert_called_once_with("/circles", {
            "name": "Test Circle",
            "description": "Test"
        })

    @patch.object(CirclesClient, 'post')
    def test_new_circle_with_kwargs(self, mock_post):
        """Test creating a new circle with additional kwargs."""
        mock_post.return_value = {"circle": {"id": "circle123"}}

        self.circles_client.new(
            name="Test", description="", parent_id="parent123")

        mock_post.assert_called_once_with("/circles", {
            "name": "Test",
            "description": "",
            "parent_id": "parent123"
        })

    @patch.object(CirclesClient, 'post')
    def test_new_circle_no_circle_key(self, mock_post):
        """Test creating a new circle when response has no circle key."""
        mock_post.return_value = {"id": "circle123", "name": "Test"}

        result = self.circles_client.new(name="Test", description="")

        self.assertEqual(result, {"id": "circle123", "name": "Test"})

    @patch.object(CirclesClient, 'patch')
    def test_update_circle(self, mock_patch):
        """Test updating a circle."""
        mock_patch.return_value = {
            "circle": {"id": "circle123", "name": "Updated"}
        }

        result = self.circles_client.update(
            circle_id="circle123", name="Updated")

        self.assertEqual(result, {"id": "circle123", "name": "Updated"})
        mock_patch.assert_called_once_with(
            "/circles/circle123", {"name": "Updated"})


class TestUsersClient(unittest.TestCase):
    """Test cases for UsersClient class."""

    @patch('campus.config.get_base_url')
    def setUp(self, mock_get_base_url):
        """Set up test fixtures."""
        mock_get_base_url.return_value = "https://apps.example.com"
        self.users_client = UsersClient()

    def test_init_default_base_url(self):
        """Test UsersClient initialization with default base URL."""
        with patch('campus.config.get_base_url') as mock_get_base_url:
            mock_get_base_url.return_value = "https://apps.default.com"
            client = UsersClient()
            mock_get_base_url.assert_called_once_with("campus.apps")
            self.assertEqual(client.base_url, "https://apps.default.com")

    def test_init_custom_base_url(self):
        """Test UsersClient initialization with custom base URL."""
        client = UsersClient("https://custom.apps.com")
        self.assertEqual(client.base_url, "https://custom.apps.com")

    def test_getitem_returns_user(self):
        """Test that __getitem__ returns a User instance."""
        from campus.client.apps.users import User

        user = self.users_client["user123"]

        self.assertIsInstance(user, User)
        self.assertEqual(user.id, "user123")
        self.assertEqual(user._client, self.users_client)

    @patch.object(UsersClient, 'post')
    def test_new_user(self, mock_post):
        """Test creating a new user."""
        mock_post.return_value = {
            "user": {"id": "user123", "email": "test@example.com", "name": "Test User"}
        }

        result = self.users_client.new(
            email="test@example.com", name="Test User")

        self.assertEqual(
            result, {"id": "user123", "email": "test@example.com", "name": "Test User"})
        mock_post.assert_called_once_with("/users/", {
            "email": "test@example.com",
            "name": "Test User"
        })

    @patch.object(UsersClient, 'post')
    def test_new_user_no_user_key(self, mock_post):
        """Test creating a new user when response has no user key."""
        mock_post.return_value = {"id": "user123", "email": "test@example.com"}

        result = self.users_client.new(
            email="test@example.com", name="Test User")

        self.assertEqual(
            result, {"id": "user123", "email": "test@example.com"})

    @patch.object(UsersClient, 'get')
    def test_me(self, mock_get):
        """Test getting the authenticated user."""
        mock_get.return_value = {
            "user": {"id": "user123", "email": "me@example.com", "name": "Current User"}
        }

        result = self.users_client.me()

        self.assertEqual(
            result, {"id": "user123", "email": "me@example.com", "name": "Current User"})
        mock_get.assert_called_once_with("/me")

    @patch.object(UsersClient, 'get')
    def test_me_no_user_key(self, mock_get):
        """Test getting authenticated user when response has no user key."""
        mock_get.return_value = {"id": "user123", "email": "me@example.com"}

        result = self.users_client.me()

        self.assertEqual(result, {"id": "user123", "email": "me@example.com"})

    @patch.object(UsersClient, 'patch')
    def test_update_user(self, mock_patch):
        """Test updating a user."""
        mock_patch.return_value = {
            "user": {"id": "user123", "name": "Updated Name"}
        }

        result = self.users_client.update(
            user_id="user123", name="Updated Name")

        self.assertEqual(result, {"id": "user123", "name": "Updated Name"})
        mock_patch.assert_called_once_with(
            "/users/user123", {"name": "Updated Name"})


class TestUser(unittest.TestCase):
    """Test cases for User resource class."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_client = Mock()

    def test_init_without_data(self):
        """Test User initialization without data."""
        from campus.client.apps.users import User

        user = User(self.mock_client, "user123")

        self.assertEqual(user.id, "user123")
        self.assertEqual(user._client, self.mock_client)
        self.assertIsNone(user._data)

    def test_init_with_data(self):
        """Test User initialization with data."""
        from campus.client.apps.users import User

        user_data = {"id": "user123", "email": "test@example.com"}
        user = User(self.mock_client, "user123", user_data)

        self.assertEqual(user._data, user_data)

    def test_data_property_loads_if_needed(self):
        """Test that data property loads data if not cached."""
        from campus.client.apps.users import User

        self.mock_client.get.return_value = {
            "id": "user123", "email": "test@example.com"}
        user = User(self.mock_client, "user123")

        data = user.data

        self.assertEqual(data, {"id": "user123", "email": "test@example.com"})
        self.mock_client.get.assert_called_once_with("/users/user123")

    def test_data_property_uses_cached(self):
        """Test that data property uses cached data if available."""
        from campus.client.apps.users import User

        user_data = {"id": "user123", "email": "test@example.com"}
        user = User(self.mock_client, "user123", user_data)

        data = user.data

        self.assertEqual(data, user_data)
        self.mock_client.get.assert_not_called()

    def test_email_property(self):
        """Test email property."""
        from campus.client.apps.users import User

        user_data = {"id": "user123", "email": "test@example.com"}
        user = User(self.mock_client, "user123", user_data)

        self.assertEqual(user.email, "test@example.com")

    def test_email_property_empty(self):
        """Test email property when email not in data."""
        from campus.client.apps.users import User

        user_data = {"id": "user123"}
        user = User(self.mock_client, "user123", user_data)

        self.assertEqual(user.email, "")

    def test_name_property(self):
        """Test name property."""
        from campus.client.apps.users import User

        user_data = {"id": "user123", "name": "Test User"}
        user = User(self.mock_client, "user123", user_data)

        self.assertEqual(user.name, "Test User")

    def test_name_property_empty(self):
        """Test name property when name not in data."""
        from campus.client.apps.users import User

        user_data = {"id": "user123"}
        user = User(self.mock_client, "user123", user_data)

        self.assertEqual(user.name, "")

    def test_str_representation(self):
        """Test string representation of user."""
        from campus.client.apps.users import User

        user_data = {"id": "user123", "email": "test@example.com"}
        user = User(self.mock_client, "user123", user_data)

        result = str(user)

        self.assertEqual(result, "User(id=user123, email=test@example.com)")

    def test_update(self):
        """Test updating user."""
        from campus.client.apps.users import User

        user_data = {"id": "user123", "name": "Old Name"}
        user = User(self.mock_client, "user123", user_data)

        user.update(name="New Name")

        self.mock_client.patch.assert_called_once_with(
            "/users/user123", {"name": "New Name"})
        self.assertIsNone(user._data)  # Should clear cached data

    def test_delete(self):
        """Test deleting user."""
        from campus.client.apps.users import User

        user = User(self.mock_client, "user123")

        user.delete()

        self.mock_client.delete.assert_called_once_with("/users/user123")

    def test_get_profile(self):
        """Test getting user profile."""
        from campus.client.apps.users import User

        self.mock_client.get.return_value = {"profile": "data"}
        user = User(self.mock_client, "user123")

        result = user.get_profile()

        self.assertEqual(result, {"profile": "data"})
        self.mock_client.get.assert_called_once_with("/users/user123/profile")


class TestAppsClientInterfaces(unittest.TestCase):
    """Test cases for apps client interfaces and consistency."""

    def test_admin_client_import(self):
        """Test that AdminClient can be imported."""
        from campus.client.apps import AdminClient
        self.assertTrue(callable(AdminClient))

    def test_circles_client_import(self):
        """Test that CirclesClient can be imported."""
        from campus.client.apps import CirclesClient
        self.assertTrue(callable(CirclesClient))

    def test_users_client_import(self):
        """Test that UsersClient can be imported."""
        from campus.client.apps import UsersClient
        self.assertTrue(callable(UsersClient))

    def test_apps_module_exports(self):
        """Test that apps module exports expected classes."""
        import campus.client.apps as apps_module

        expected_exports = ['AdminClient', 'CirclesClient', 'UsersClient']
        for export in expected_exports:
            self.assertTrue(hasattr(apps_module, export),
                            f"{export} should be exported")

    @patch('campus.config.get_base_url')
    def test_client_consistency_pattern(self, mock_get_base_url):
        """Test that all apps clients follow consistent patterns."""
        mock_get_base_url.return_value = "https://apps.example.com"

        # Test AdminClient uses composition pattern
        admin = AdminClient()
        self.assertTrue(hasattr(admin, '_client'),
                        "AdminClient should have _client attribute")

        # Test CirclesClient inherits from HttpClient
        circles = CirclesClient()
        self.assertTrue(hasattr(circles, 'get'),
                        "CirclesClient should have HTTP methods")
        self.assertTrue(hasattr(circles, 'post'),
                        "CirclesClient should have HTTP methods")

        # Test UsersClient inherits from HttpClient
        users = UsersClient()
        self.assertTrue(hasattr(users, 'get'),
                        "UsersClient should have HTTP methods")
        self.assertTrue(hasattr(users, 'post'),
                        "UsersClient should have HTTP methods")


if __name__ == '__main__':
    unittest.main()
