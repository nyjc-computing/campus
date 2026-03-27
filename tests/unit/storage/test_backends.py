#!/usr/bin/env python3
"""Test the new storage backends for Flask test client strategy."""

import unittest
from campus.storage import get_table, get_collection
from campus.storage import errors as storage_errors
from campus.common import env

# Configure test storage before importing storage modules
env.STORAGE_MODE = "1"


class TestSQLiteBackend(unittest.TestCase):
    """Test the SQLite table backend."""

    def setUp(self):
        """Set up test table before each test."""
        self.users_table = get_table("test_users")
        # Initialize table schema
        from campus.model import User
        self.users_table.init_from_model("test_users", User)

    def tearDown(self):
        """Clean up after each test."""
        try:
            self.users_table.delete_by_id("test123")
        except storage_errors.NotFoundError:
            pass

    def test_get_by_id_raises_not_found_error(self):
        """get_by_id() must raise NotFoundError when ID doesn't exist."""
        with self.assertRaises(storage_errors.NotFoundError) as cm:
            self.users_table.get_by_id("nonexistent_id")
        self.assertIn("nonexistent_id", str(cm.exception))

    def test_insert_and_retrieve(self):
        """Test inserting and retrieving a record."""
        test_user = {
            "id": "test123",
            "created_at": "2023-01-01T00:00:00Z",
            "name": "Test User",
            "email": "test@example.com"
        }
        self.users_table.insert_one(test_user)

        retrieved_user = self.users_table.get_by_id("test123")
        self.assertEqual(retrieved_user["id"], "test123")
        self.assertEqual(retrieved_user["name"], "Test User")
        self.assertEqual(retrieved_user["email"], "test@example.com")

    def test_delete_and_get_raises_not_found_error(self):
        """After deletion, get_by_id() must raise NotFoundError."""
        test_user = {
            "id": "test123",
            "created_at": "2023-01-01T00:00:00Z",
            "name": "Test User",
            "email": "test@example.com"
        }
        self.users_table.insert_one(test_user)

        # Verify record exists
        retrieved_user = self.users_table.get_by_id("test123")
        self.assertEqual(retrieved_user["id"], "test123")

        # Delete the record
        self.users_table.delete_by_id("test123")

        # Verify NotFoundError is raised
        with self.assertRaises(storage_errors.NotFoundError) as cm:
            self.users_table.get_by_id("test123")
        self.assertIn("test123", str(cm.exception))


class TestMemoryBackend(unittest.TestCase):
    """Test the memory collection backend."""

    def setUp(self):
        """Set up test collection before each test."""
        self.posts_collection = get_collection("test_posts")

    def tearDown(self):
        """Clean up after each test."""
        try:
            self.posts_collection.delete_by_id("post123")
        except storage_errors.NotFoundError:
            pass

    def test_get_by_id_returns_none_for_not_found(self):
        """Collection get_by_id() returns None when ID doesn't exist.

        Note: This is different from TableInterface which raises NotFoundError.
        Collections follow a different contract - they return None.
        """
        result = self.posts_collection.get_by_id("nonexistent_id")
        self.assertIsNone(result)

    def test_insert_and_retrieve(self):
        """Test inserting and retrieving a document."""
        test_post = {
            "id": "post123",
            "created_at": "2023-01-01T00:00:00Z",
            "title": "Test Post",
            "content": "This is a test post",
            "author": "testuser"
        }
        self.posts_collection.insert_one(test_post)

        retrieved_post = self.posts_collection.get_by_id("post123")
        self.assertEqual(retrieved_post["id"], "post123")
        self.assertEqual(retrieved_post["title"], "Test Post")


if __name__ == "__main__":
    unittest.main()

