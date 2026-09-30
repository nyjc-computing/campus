#!/usr/bin/env python3
"""Test the MongoDB documents backend query-building and id-mapping.

These tests pin the contract that Campus `id`-keyed filters in
`get_matching` are translated to Mongo's `_id` field, matching how
records are stored (MongoRecord.to_mongo). Regression tests for #629:
`ne("id")` filters used to be built against a nonexistent `id` field,
so Mongo's missing-field `$ne` semantics matched every document
(including the internal `@metadata` record).

No MongoDB server is required: `_build_mongo_query` is tested directly,
and `get_matching` is tested against a stub collection.
"""

import unittest

from campus.common import env

# Configure test storage before importing storage modules
env.set('STORAGE_MODE', "1")


class TestBuildMongoQuery(unittest.TestCase):
    """Test _build_mongo_query translation of Campus queries."""

    @classmethod
    def setUpClass(cls):
        from campus.storage.documents.backend.mongodb import MongoDBCollection
        cls.backend = MongoDBCollection

    def test_exact_id_maps_to_mongo_pk(self):
        """An exact match on 'id' queries Mongo's _id, not 'id'."""
        self.assertEqual(
            self.backend._build_mongo_query({"id": "doc1"}),
            {"_id": "doc1"}
        )

    def test_id_operator_maps_to_mongo_pk(self):
        """Operator filters on 'id' (e.g. ne) query Mongo's _id."""
        from campus.storage.query import ne
        self.assertEqual(
            self.backend._build_mongo_query({"id": ne("@metadata")}),
            {"_id": {"$ne": "@metadata"}}
        )

    def test_comparison_operators_map_to_mongo_syntax(self):
        """gt/gte/lt/lte operators translate to Mongo operator syntax."""
        from campus.storage.query import gt, gte, lt, lte
        query = {
            "count": gt(1),
            "rank": gte(2),
            "score": lt(3),
            "level": lte(4),
        }
        self.assertEqual(self.backend._build_mongo_query(query), {
            "count": {"$gt": 1},
            "rank": {"$gte": 2},
            "score": {"$lt": 3},
            "level": {"$lte": 4},
        })

    def test_non_id_fields_are_unchanged(self):
        """Non-PK fields are queried under their Campus names."""
        self.assertEqual(
            self.backend._build_mongo_query(
                {"filename": "a.json", "group": "g1"}
            ),
            {"filename": "a.json", "group": "g1"}
        )


class StubMongoCollection:
    """Stand-in for pymongo.collection.Collection with Mongo find semantics.

    Applies the translated query to stored Mongo documents (keyed by
    `_id`), so a query built against the wrong field name behaves the
    way it does against real Mongo (missing fields match `$ne`,
    exact-match misses).
    """

    def __init__(self, mongo_docs: list[dict]):
        self.mongo_docs = mongo_docs
        self.last_query: dict | None = None

    @staticmethod
    def _matches(doc: dict, query: dict) -> bool:
        for key, expected in query.items():
            if isinstance(expected, dict):
                for op, value in expected.items():
                    if op == "$ne":
                        if doc.get(key) == value:
                            return False
                    elif op == "$gt":
                        if not doc.get(key, float("inf")) > value:
                            return False
                    elif op == "$gte":
                        if not doc.get(key, float("inf")) >= value:
                            return False
                    elif op == "$lt":
                        if not doc.get(key, float("-inf")) < value:
                            return False
                    elif op == "$lte":
                        if not doc.get(key, float("-inf")) <= value:
                            return False
                    else:
                        raise AssertionError(f"unsupported operator: {op}")
            elif doc.get(key) != expected:
                return False
        return True

    def find(self, query: dict) -> list[dict]:
        self.last_query = query
        return [doc for doc in self.mongo_docs if self._matches(doc, query)]


class TestGetMatchingIdQueries(unittest.TestCase):
    """Test get_matching end-to-end against a stubbed Mongo collection."""

    # Stored docs use Mongo's _id (as written by MongoRecord.to_mongo);
    # @metadata is the internal document that list() must exclude (#629).
    MONGO_DOCS = [
        {"_id": "@metadata", "filename": None},
        {"_id": "tt1", "filename": "one.json"},
        {"_id": "tt2", "filename": "two.json"},
    ]

    def setUp(self):
        from campus.storage.documents.backend.mongodb import MongoDBCollection
        self.collection = MongoDBCollection("test_timetable")
        self.stub = StubMongoCollection(self.MONGO_DOCS)
        self.collection._collection = self.stub  # bypass lazy connection

    def test_get_matching_ne_id_excludes_by_mongo_pk(self):
        """ne('@metadata') on 'id' excludes the metadata doc, not all docs."""
        from campus.storage.query import ne
        records = self.collection.get_matching({"id": ne("@metadata")})
        self.assertEqual(self.stub.last_query, {"_id": {"$ne": "@metadata"}})
        self.assertEqual(
            records,
            [
                {"id": "tt1", "filename": "one.json"},
                {"id": "tt2", "filename": "two.json"},
            ]
        )

    def test_get_matching_exact_id_returns_record(self):
        """An exact 'id' match returns the record with Campus id restored."""
        records = self.collection.get_matching({"id": "tt1"})
        self.assertEqual(self.stub.last_query, {"_id": "tt1"})
        self.assertEqual(records, [{"id": "tt1", "filename": "one.json"}])


if __name__ == '__main__':
    unittest.main()
