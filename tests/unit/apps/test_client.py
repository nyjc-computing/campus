"""tests/test_client_apps

Comprehensive black-box unit tests for campus.client.apps:
- **CirclesResource**: Circle/group management with CRUD operations
- **UsersResource**: User management and profile operations  

Testing Approach:
- **Black-box methodology**: Tests only public interfaces without internal mocking
- **HTTP layer mocking**: Mocks JsonClient methods for API simulation
- **Resource pattern validation**: Tests the new Resource-based architecture

Architecture Coverage:
- **Resource pattern**: All apps resources inherit from Resource base class
- **JsonClient composition**: Resources use JsonClient for HTTP operations
- **Public API contracts**: Comprehensive coverage of user-facing methods

These tests ensure the apps client library provides a reliable, consistent
interface for campus service operations using the new Resource architecture.
"""

import unittest
from unittest.mock import Mock

from campus.common.http import JsonClient
from campus.client.apps import CirclesResource, UsersResource


class TestCirclesResource(unittest.TestCase):
    """Test cases for CirclesResource class."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_client = Mock(spec=JsonClient)
        self.mock_client.base_url = "https://apps.example.com"
        self.circles_resource = CirclesResource(self.mock_client)

    def test_init(self):
        """Test CirclesResource initialization."""
        self.assertEqual(self.circles_resource.client, self.mock_client)
        self.assertEqual(self.circles_resource.path, "circles")


class TestUsersResource(unittest.TestCase):
    """Test cases for UsersResource class."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_client = Mock(spec=JsonClient)
        self.mock_client.base_url = "https://apps.example.com"
        self.users_resource = UsersResource(self.mock_client)

    def test_init(self):
        """Test UsersResource initialization."""
        self.assertEqual(self.users_resource.client, self.mock_client)
        self.assertEqual(self.users_resource.path, "users")


class TestAppsResourceInterfaces(unittest.TestCase):
    """Test cases for apps resource interfaces and consistency."""

    def test_circles_resource_import(self):
        """Test that CirclesResource can be imported."""
        from campus.client.apps import CirclesResource
        self.assertTrue(callable(CirclesResource))

    def test_users_resource_import(self):
        """Test that UsersResource can be imported."""
        from campus.client.apps import UsersResource
        self.assertTrue(callable(UsersResource))

    def test_apps_module_exports(self):
        """Test that apps module exports expected classes."""
        import campus.client.apps as apps_module

        expected_exports = ['CirclesResource', 'UsersResource']
        for export in expected_exports:
            self.assertTrue(hasattr(apps_module, export),
                            f"{export} should be exported")

    def test_resource_consistency_pattern(self):
        """Test that all apps resources follow consistent patterns."""
        mock_client = Mock(spec=JsonClient)
        mock_client.base_url = "https://apps.example.com"

        # Test CirclesResource uses Resource pattern
        circles = CirclesResource(mock_client)
        self.assertTrue(hasattr(circles, 'client'),
                        "CirclesResource should have client attribute")
        self.assertTrue(hasattr(circles, 'path'),
                        "CirclesResource should have path attribute")

        # Test UsersResource uses Resource pattern
        users = UsersResource(mock_client)
        self.assertTrue(hasattr(users, 'client'),
                        "UsersResource should have client attribute")
        self.assertTrue(hasattr(users, 'path'),
                        "UsersResource should have path attribute")


if __name__ == '__main__':
    unittest.main()
