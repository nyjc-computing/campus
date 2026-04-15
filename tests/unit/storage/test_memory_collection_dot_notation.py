#!/usr/bin/env python3
"""Unit tests for MemoryCollection MongoDB dot notation support.

This test suite verifies that the MemoryCollection backend supports
MongoDB-style dot notation for nested field updates.

Dot notation examples:
- {"a.b.c": 1} sets doc["a"]["b"]["c"] = 1
- {"a.b.c": None} removes doc["a"]["b"]["c"]
- {"members.abc123": 15} sets doc["members"]["abc123"] = 15
"""

import unittest

from campus.common import devops, env
from campus.storage.documents.backend.memory import MemoryCollection


class TestMemoryCollectionDotNotation(unittest.TestCase):
    """Unit tests for MongoDB dot notation support in MemoryCollection."""

    def setUp(self):
        """Set up test environment before each test."""
        # Ensure test mode
        if env.get("ENV") != devops.TESTING:
            env.set('ENV', devops.TESTING)

        # Reset storage for clean state
        MemoryCollection.reset_storage()

        # Create test collection
        self.collection = MemoryCollection("test_dot_notation")

    def tearDown(self):
        """Clean up after each test."""
        MemoryCollection.reset_storage()

    # Single-level nested updates

    def test_set_nested_value_single_level(self):
        """Setting a single-level nested value creates intermediate dicts."""
        doc_id = "test1"
        self.collection.insert_one({"id": doc_id, "name": "Test"})

        # Update nested field
        self.collection.update_by_id(doc_id, {"metadata.count": 5})

        doc = self.collection.get_by_id(doc_id)
        self.assertEqual(doc["metadata"]["count"], 5)
        self.assertIn("metadata", doc)

    def test_set_nested_value_multiple_levels(self):
        """Setting a multi-level nested value creates all intermediate dicts."""
        doc_id = "test2"
        self.collection.insert_one({"id": doc_id, "name": "Test"})

        # Update deeply nested field
        self.collection.update_by_id(doc_id, {"a.b.c.d": 42})

        doc = self.collection.get_by_id(doc_id)
        self.assertEqual(doc["a"]["b"]["c"]["d"], 42)

    def test_unset_nested_value_single_level(self):
        """Unsetting a nested value removes it from the document."""
        doc_id = "test3"
        self.collection.insert_one({
            "id": doc_id,
            "metadata": {"count": 5, "tag": "test"}
        })

        # Remove nested field
        self.collection.update_by_id(doc_id, {"metadata.count": None})

        doc = self.collection.get_by_id(doc_id)
        self.assertNotIn("count", doc["metadata"])
        # Other nested values should remain
        self.assertEqual(doc["metadata"]["tag"], "test")

    def test_unset_nested_value_multiple_levels(self):
        """Unsetting a multi-level nested value removes only the leaf."""
        doc_id = "test4"
        self.collection.insert_one({
            "id": doc_id,
            "a": {
                "b": {
                    "c": {
                        "d": 42,
                        "e": 43
                    },
                    "f": 44
                }
            }
        })

        # Remove deeply nested field
        self.collection.update_by_id(doc_id, {"a.b.c.d": None})

        doc = self.collection.get_by_id(doc_id)
        self.assertNotIn("d", doc["a"]["b"]["c"])
        # Sibling and parent values should remain
        self.assertEqual(doc["a"]["b"]["c"]["e"], 43)
        self.assertEqual(doc["a"]["b"]["f"], 44)

    # Circle member patterns (the primary use case)

    def test_circle_member_add_pattern(self):
        """Test the circle member add pattern: members.{member_id}."""
        doc_id = "circle1"
        self.collection.insert_one({
            "id": doc_id,
            "name": "Test Circle",
            "members": {}
        })

        # Add a member
        member_id = "child1"
        access_value = 15
        self.collection.update_by_id(doc_id, {f"members.{member_id}": access_value})

        doc = self.collection.get_by_id(doc_id)
        self.assertEqual(doc["members"][member_id], access_value)

    def test_circle_member_remove_pattern(self):
        """Test the circle member remove pattern: members.{member_id} with None."""
        doc_id = "circle2"
        member_id = "child2"

        self.collection.insert_one({
            "id": doc_id,
            "name": "Test Circle",
            "members": {
                member_id: 15,
                "other": 10
            }
        })

        # Remove a member
        self.collection.update_by_id(doc_id, {f"members.{member_id}": None})

        doc = self.collection.get_by_id(doc_id)
        self.assertNotIn(member_id, doc["members"])
        # Other members should remain
        self.assertIn("other", doc["members"])

    def test_circle_member_update_pattern(self):
        """Test the circle member update pattern: changing access value."""
        doc_id = "circle3"
        member_id = "child3"

        self.collection.insert_one({
            "id": doc_id,
            "name": "Test Circle",
            "members": {
                member_id: 5
            }
        })

        # Update access value
        new_access = 10
        self.collection.update_by_id(doc_id, {f"members.{member_id}": new_access})

        doc = self.collection.get_by_id(doc_id)
        self.assertEqual(doc["members"][member_id], new_access)

    # Edge cases

    def test_unset_nonexistent_nested_path_no_error(self):
        """Unsetting a non-existent nested path should not raise an error."""
        doc_id = "test5"
        self.collection.insert_one({"id": doc_id, "name": "Test"})

        # Should not raise error even though path doesn't exist
        self.collection.update_by_id(doc_id, {"nonexistent.path.value": None})

        doc = self.collection.get_by_id(doc_id)
        # Document should be unchanged
        self.assertEqual(doc, {"id": doc_id, "name": "Test"})

    def test_mixed_dot_notation_and_regular_keys(self):
        """Mixing dot notation and regular keys in one update."""
        doc_id = "test6"
        self.collection.insert_one({
            "id": doc_id,
            "name": "Test",
            "count": 0
        })

        # Update both regular and nested fields
        self.collection.update_by_id(doc_id, {
            "name": "Updated",
            "count": 5,
            "metadata.tag": "test",
            "metadata.count": 10
        })

        doc = self.collection.get_by_id(doc_id)
        self.assertEqual(doc["name"], "Updated")
        self.assertEqual(doc["count"], 5)
        self.assertEqual(doc["metadata"]["tag"], "test")
        self.assertEqual(doc["metadata"]["count"], 10)

    def test_set_nested_replaces_non_dict_intermediate(self):
        """Setting a nested value replaces non-dict intermediate values."""
        doc_id = "test7"
        self.collection.insert_one({
            "id": doc_id,
            "metadata": "string_value"  # Not a dict
        })

        # This should replace "string_value" with a dict
        self.collection.update_by_id(doc_id, {"metadata.count": 5})

        doc = self.collection.get_by_id(doc_id)
        self.assertIsInstance(doc["metadata"], dict)
        self.assertEqual(doc["metadata"]["count"], 5)

    def test_update_nonexistent_document_no_error(self):
        """Updating a non-existent document should not raise an error."""
        # Should silently do nothing
        self.collection.update_by_id("nonexistent", {"metadata.count": 5})

        # No document should have been created
        self.assertIsNone(self.collection.get_by_id("nonexistent"))

    def test_regular_key_without_dots_still_works(self):
        """Regular keys without dots should still work as before."""
        doc_id = "test8"
        self.collection.insert_one({
            "id": doc_id,
            "name": "Test",
            "count": 0
        })

        # Update regular keys
        self.collection.update_by_id(doc_id, {
            "name": "Updated",
            "count": 10
        })

        doc = self.collection.get_by_id(doc_id)
        self.assertEqual(doc["name"], "Updated")
        self.assertEqual(doc["count"], 10)

    def test_regular_unset_with_none_still_works(self):
        """Regular key unset with None should still work as before."""
        doc_id = "test9"
        self.collection.insert_one({
            "id": doc_id,
            "name": "Test",
            "temp": "value"
        })

        # Unset a regular key
        self.collection.update_by_id(doc_id, {"temp": None})

        doc = self.collection.get_by_id(doc_id)
        self.assertNotIn("temp", doc)
        self.assertEqual(doc["name"], "Test")


if __name__ == '__main__':
    unittest.main()
