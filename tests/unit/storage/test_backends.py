#!/usr/bin/env python3
"""Test the new storage backends for Flask test client strategy."""

import unittest
from campus.storage import get_table, get_collection, gt, gte, lt, lte
from campus.storage import errors as storage_errors
from campus.common import env

# Configure test storage before importing storage modules
env.set('STORAGE_MODE', "1")


class TestSQLiteBackend(unittest.TestCase):
    """Test the SQLite table backend."""

    @classmethod
    def setUpClass(cls):
        """Set up test tables once for all tests."""
        cls.users_table = get_table("test_users")
        # Initialize table schema
        from campus.model import User
        cls.users_table.init_from_model("test_users", User)

        # Create a test traces table for query operator tests
        cls.traces_table = get_table("test_traces")
        cls.traces_table.init_from_schema(
            'CREATE TABLE IF NOT EXISTS "test_traces" ('
            '"id" TEXT PRIMARY KEY, '
            '"created_at" TEXT NOT NULL, '
            '"duration_ms" INTEGER NOT NULL, '
            '"status_code" INTEGER NOT NULL);'
        )

        # Insert test data for query tests
        test_traces = [
            {"id": "trace1", "created_at": "2023-01-01T10:00:00Z", "duration_ms": 100, "status_code": 200},
            {"id": "trace2", "created_at": "2023-01-01T11:00:00Z", "duration_ms": 500, "status_code": 200},
            {"id": "trace3", "created_at": "2023-01-01T12:00:00Z", "duration_ms": 1500, "status_code": 500},
            {"id": "trace4", "created_at": "2023-01-01T13:00:00Z", "duration_ms": 2000, "status_code": 500},
        ]
        for trace in test_traces:
            try:
                cls.traces_table.insert_one(trace)
            except Exception:
                pass  # Ignore if already exists

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

    def test_get_matching_exact_match(self):
        """get_matching() with exact match query."""
        results = self.traces_table.get_matching({"status_code": 200})
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertEqual(r["status_code"], 200)

    def test_get_matching_with_gt_operator(self):
        """get_matching() with gt (greater than) operator."""
        results = self.traces_table.get_matching({"duration_ms": gt(1000)})
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertGreater(r["duration_ms"], 1000)

    def test_get_matching_with_gte_operator(self):
        """get_matching() with gte (greater than or equal) operator."""
        results = self.traces_table.get_matching({"duration_ms": gte(500)})
        self.assertEqual(len(results), 3)
        for r in results:
            self.assertGreaterEqual(r["duration_ms"], 500)

    def test_get_matching_with_lt_operator(self):
        """get_matching() with lt (less than) operator."""
        results = self.traces_table.get_matching({"duration_ms": lt(1000)})
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertLess(r["duration_ms"], 1000)

    def test_get_matching_with_lte_operator(self):
        """get_matching() with lte (less than or equal) operator."""
        results = self.traces_table.get_matching({"duration_ms": lte(500)})
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertLessEqual(r["duration_ms"], 500)

    def test_get_matching_with_multiple_operators(self):
        """get_matching() with multiple operator conditions (implicit AND)."""
        results = self.traces_table.get_matching({
            "status_code": 500,
            "duration_ms": gt(1000)
        })
        # Both trace3 (1500ms) and trace4 (2000ms) match: status=500 AND duration > 1000
        self.assertEqual(len(results), 2)
        self.assertIn(results[0]["id"], ["trace3", "trace4"])
        self.assertIn(results[1]["id"], ["trace3", "trace4"])

    def test_get_matching_with_sorting_ascending(self):
        """get_matching() with ascending sort."""
        results = self.traces_table.get_matching(
            {},
            order_by="duration_ms",
            ascending=True
        )
        self.assertEqual(len(results), 4)
        self.assertEqual(results[0]["duration_ms"], 100)
        self.assertEqual(results[-1]["duration_ms"], 2000)

    def test_get_matching_with_sorting_descending(self):
        """get_matching() with descending sort."""
        results = self.traces_table.get_matching(
            {},
            order_by="duration_ms",
            ascending=False
        )
        self.assertEqual(len(results), 4)
        self.assertEqual(results[0]["duration_ms"], 2000)
        self.assertEqual(results[-1]["duration_ms"], 100)

    def test_get_matching_with_limit(self):
        """get_matching() with limit."""
        results = self.traces_table.get_matching(
            {},
            order_by="duration_ms",
            ascending=True,
            limit=2
        )
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["duration_ms"], 100)
        self.assertEqual(results[1]["duration_ms"], 500)

    def test_get_matching_with_offset(self):
        """get_matching() with offset."""
        results = self.traces_table.get_matching(
            {},
            order_by="duration_ms",
            ascending=True,
            offset=2
        )
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["duration_ms"], 1500)
        self.assertEqual(results[1]["duration_ms"], 2000)

    def test_get_matching_with_limit_and_offset(self):
        """get_matching() with both limit and offset (pagination)."""
        results = self.traces_table.get_matching(
            {},
            order_by="duration_ms",
            ascending=True,
            limit=2,
            offset=1
        )
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["duration_ms"], 500)
        self.assertEqual(results[1]["duration_ms"], 1500)

    def test_get_matching_with_between_operator(self):
        """get_matching() with between operator for inclusive range."""
        from campus.storage import between
        # Query for traces with duration_ms between 500 and 1500 (inclusive)
        results = self.traces_table.get_matching({"duration_ms": between(500, 1500)})
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertGreaterEqual(r["duration_ms"], 500)
            self.assertLessEqual(r["duration_ms"], 1500)

    def test_get_matching_with_between_operator_string_field(self):
        """get_matching() with between operator on string/timestamp field."""
        from campus.storage import between
        # Query for traces created between 11:00 and 13:00
        results = self.traces_table.get_matching({
            "created_at": between("2023-01-01T11:00:00Z", "2023-01-01T13:00:00Z")
        })
        self.assertEqual(len(results), 2)
        # Should return trace2 (11:00) and trace3 (12:00)
        self.assertIn(results[0]["id"], ["trace2", "trace3"])
        self.assertIn(results[1]["id"], ["trace2", "trace3"])


class TestMemoryBackend(unittest.TestCase):
    """Test the memory collection backend."""

    @classmethod
    def setUpClass(cls):
        """Set up test collection once for all tests."""
        cls.posts_collection = get_collection("test_posts")

        # Create a test metrics collection for query operator tests
        cls.metrics_collection = get_collection("test_metrics")

        # Insert test data for query tests
        test_metrics = [
            {"id": "metric1", "created_at": "2023-01-01T10:00:00Z", "value": 100, "score": 200},
            {"id": "metric2", "created_at": "2023-01-01T11:00:00Z", "value": 500, "score": 200},
            {"id": "metric3", "created_at": "2023-01-01T12:00:00Z", "value": 1500, "score": 500},
            {"id": "metric4", "created_at": "2023-01-01T13:00:00Z", "value": 2000, "score": 500},
        ]
        for metric in test_metrics:
            try:
                cls.metrics_collection.insert_one(metric)
            except Exception:
                pass  # Ignore if already exists

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

    def test_get_matching_exact_match(self):
        """get_matching() with exact match query."""
        results = self.metrics_collection.get_matching({"score": 200})
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertEqual(r["score"], 200)

    def test_get_matching_with_gt_operator(self):
        """get_matching() with gt (greater than) operator."""
        results = self.metrics_collection.get_matching({"value": gt(1000)})
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertGreater(r["value"], 1000)

    def test_get_matching_with_gte_operator(self):
        """get_matching() with gte (greater than or equal) operator."""
        results = self.metrics_collection.get_matching({"value": gte(500)})
        self.assertEqual(len(results), 3)
        for r in results:
            self.assertGreaterEqual(r["value"], 500)

    def test_get_matching_with_lt_operator(self):
        """get_matching() with lt (less than) operator."""
        results = self.metrics_collection.get_matching({"value": lt(1000)})
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertLess(r["value"], 1000)

    def test_get_matching_with_lte_operator(self):
        """get_matching() with lte (less than or equal) operator."""
        results = self.metrics_collection.get_matching({"value": lte(500)})
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertLessEqual(r["value"], 500)

    def test_get_matching_with_multiple_operators(self):
        """get_matching() with multiple operator conditions (implicit AND)."""
        results = self.metrics_collection.get_matching({
            "score": 500,
            "value": gt(1000)
        })
        # Both metric3 (1500) and metric4 (2000) match: score=500 AND value > 1000
        self.assertEqual(len(results), 2)
        self.assertIn(results[0]["id"], ["metric3", "metric4"])
        self.assertIn(results[1]["id"], ["metric3", "metric4"])

    def test_get_matching_with_sorting_ascending(self):
        """get_matching() with ascending sort."""
        results = self.metrics_collection.get_matching(
            {},
            order_by="value",
            ascending=True
        )
        self.assertEqual(len(results), 4)
        self.assertEqual(results[0]["value"], 100)
        self.assertEqual(results[-1]["value"], 2000)

    def test_get_matching_with_sorting_descending(self):
        """get_matching() with descending sort."""
        results = self.metrics_collection.get_matching(
            {},
            order_by="value",
            ascending=False
        )
        self.assertEqual(len(results), 4)
        self.assertEqual(results[0]["value"], 2000)
        self.assertEqual(results[-1]["value"], 100)

    def test_get_matching_with_limit(self):
        """get_matching() with limit."""
        results = self.metrics_collection.get_matching(
            {},
            order_by="value",
            ascending=True,
            limit=2
        )
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["value"], 100)
        self.assertEqual(results[1]["value"], 500)

    def test_get_matching_with_offset(self):
        """get_matching() with offset."""
        results = self.metrics_collection.get_matching(
            {},
            order_by="value",
            ascending=True,
            offset=2
        )
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["value"], 1500)
        self.assertEqual(results[1]["value"], 2000)

    def test_get_matching_with_limit_and_offset(self):
        """get_matching() with both limit and offset (pagination)."""
        results = self.metrics_collection.get_matching(
            {},
            order_by="value",
            ascending=True,
            limit=2,
            offset=1
        )
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["value"], 500)
        self.assertEqual(results[1]["value"], 1500)


if __name__ == "__main__":
    unittest.main()

