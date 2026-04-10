"""Unit tests for campus.audit.client.interface module.

These tests verify that the base resource classes (ResourceRoot, ResourceCollection,
Resource) properly handle path construction and client propagation.

Test Principles:
- Test path construction with trailing slashes
- Test client propagation from parent to child
- Test bracket access patterns
"""

import unittest

from campus.audit.client.interface import ResourceRoot, ResourceCollection, Resource
from unittest.mock import Mock


class MockJsonClient:
    """Mock JsonClient for testing."""
    def __init__(self, base_url: str):
        self.base_url = base_url


class TestResourceRoot(unittest.TestCase):
    """Test ResourceRoot base class."""

    def test_resource_root_base_url(self):
        """Test that base_url property returns client's base_url."""
        client = MockJsonClient("https://audit.test")
        root = ResourceRoot(json_client=client)

        self.assertEqual(root.base_url, "https://audit.test")

    def test_resource_root_client_property(self):
        """Test that client property returns the JsonClient."""
        client = MockJsonClient("https://audit.test")
        root = ResourceRoot(json_client=client)

        self.assertEqual(root.client, client)

    def test_resource_root_make_path(self):
        """Test that make_path constructs correct paths."""
        client = MockJsonClient("https://audit.test")
        root = ResourceRoot(json_client=client)
        root.url_prefix = "api/v1"

        # Base path
        self.assertEqual(root.make_path(), "/api/v1")

        # With sub-path
        self.assertEqual(root.make_path("users"), "/api/v1/users")

    def test_resource_root_make_url(self):
        """Test that make_url constructs full URLs."""
        client = MockJsonClient("https://audit.test")
        root = ResourceRoot(json_client=client)
        root.url_prefix = "api/v1"

        self.assertEqual(root.make_url(), "https://audit.test/api/v1")


class MockCollection(ResourceCollection):
    """Mock ResourceCollection for testing."""
    path = "users/"

    def __init__(self, client=None, *, root: ResourceRoot):
        self._client = client
        self.root = root


class TestResourceCollection(unittest.TestCase):
    """Test ResourceCollection base class."""

    def setUp(self):
        """Set up test fixtures."""
        self.client = MockJsonClient("https://audit.test")
        self.root = ResourceRoot(json_client=self.client)
        self.root.url_prefix = "api/v1"

    def test_resource_collection_path_must_have_trailing_slash(self):
        """Test that ResourceCollection path must have trailing slash."""
        # Valid path
        collection = MockCollection(client=self.client, root=self.root)
        self.assertTrue(collection.path.endswith("/"))

        # Invalid path should raise ValueError
        class InvalidCollection(ResourceCollection):
            path = "users"  # No trailing slash

        with self.assertRaises(ValueError):
            InvalidCollection(client=self.client, root=self.root)

    def test_resource_collection_make_path(self):
        """Test that make_path constructs correct paths."""
        collection = MockCollection(client=self.client, root=self.root)

        # Base path
        self.assertEqual(collection.make_path(), "/api/v1/users/")

        # With sub-path
        self.assertEqual(collection.make_path("123"), "/api/v1/users/123")

    def test_resource_collection_make_url(self):
        """Test that make_url constructs full URLs."""
        collection = MockCollection(client=self.client, root=self.root)

        self.assertEqual(collection.make_url(), "https://audit.test/api/v1/users/")
        self.assertEqual(collection.make_url("123"), "https://audit.test/api/v1/users/123")

    def test_resource_collection_client_propagation(self):
        """Test that client property returns parent's client."""
        collection = MockCollection(client=None, root=self.root)

        self.assertEqual(collection.client, self.client)

    def test_resource_collection_root_property(self):
        """Test that root property returns the root resource."""
        collection = MockCollection(client=self.client, root=self.root)

        self.assertEqual(collection.root, self.root)


class MockResource(Resource):
    """Mock Resource for testing."""
    def __init__(self, *parts, parent: Resource, root: ResourceRoot, client=None):
        super().__init__(*parts, parent=parent, root=root, client=client)


class TestResource(unittest.TestCase):
    """Test Resource base class."""

    def setUp(self):
        """Set up test fixtures."""
        self.client = MockJsonClient("https://audit.test")
        self.root = ResourceRoot(json_client=self.client)
        self.root.url_prefix = "api/v1"
        self.collection = MockCollection(client=self.client, root=self.root)

    def test_resource_path_construction(self):
        """Test that path is constructed from parent + parts."""
        resource = MockResource("123", parent=self.collection, root=self.root)

        self.assertEqual(resource.path, "/api/v1/users/123")

    def test_resource_with_multiple_parts(self):
        """Test path construction with multiple parts."""
        resource = MockResource("123", "profile", parent=self.collection, root=self.root)

        self.assertEqual(resource.path, "/api/v1/users/123/profile")

    def test_resource_make_path(self):
        """Test that make_path constructs sub-resource paths."""
        resource = MockResource("123", parent=self.collection, root=self.root)

        self.assertEqual(resource.make_path(), "/api/v1/users/123")
        self.assertEqual(resource.make_path("edit"), "/api/v1/users/123/edit")

    def test_resource_make_path_with_end_slash(self):
        """Test that make_path respects end_slash parameter."""
        resource = MockResource("123", parent=self.collection, root=self.root)

        self.assertTrue(resource.make_path(end_slash=True).endswith("/"))
        self.assertFalse(resource.make_path(end_slash=False).endswith("/"))

    def test_resource_make_url(self):
        """Test that make_url constructs full URLs."""
        resource = MockResource("123", parent=self.collection, root=self.root)

        self.assertEqual(resource.make_url(), "https://audit.test/api/v1/users/123")
        self.assertEqual(resource.make_url("edit"), "https://audit.test/api/v1/users/123/edit")

    def test_resource_client_propagation(self):
        """Test that client property returns parent's client."""
        resource = MockResource("123", parent=self.collection, root=self.root)

        self.assertEqual(resource.client, self.client)

    def test_resource_with_explicit_client(self):
        """Test that explicit client overrides parent's client."""
        explicit_client = MockJsonClient("https://other.test")
        resource = MockResource(
            "123",
            parent=self.collection,
            root=self.root,
            client=explicit_client
        )

        self.assertEqual(resource.client, explicit_client)

    def test_resource_root_property(self):
        """Test that root property returns the root resource."""
        resource = MockResource("123", parent=self.collection, root=self.root)

        self.assertEqual(resource.root, self.root)


if __name__ == "__main__":
    unittest.main()
