"""Test Postgres backend JSON encoding of non-scalar values (#673).

The sqlite backend JSON-encodes non-scalar values before binding; the
postgres backend must do the same, or psycopg2 adapts Python lists as
Postgres array literals and list-typed fields (e.g. redirect_uris) are
corrupted in TEXT columns. Tests exercise the pure helpers and the
insert/get call paths via a mocked connection — no live database.
"""

import unittest
from json import dumps, loads
from unittest.mock import MagicMock, patch


class TestEncodeValue(unittest.TestCase):
    """Test the _encode_value helper directly."""

    def test_list_encoded_as_json(self):
        from campus.storage.tables.backend.postgres import _encode_value
        self.assertEqual(
            _encode_value(["http://localhost:5000/finalize_login"]),
            '["http://localhost:5000/finalize_login"]',
        )

    def test_dict_encoded_as_json(self):
        from campus.storage.tables.backend.postgres import _encode_value
        self.assertEqual(_encode_value({"a": 1}), '{"a": 1}')

    def test_scalars_passed_through(self):
        from campus.storage.tables.backend.postgres import _encode_value
        for value in ("text", "", 42, 3.14, True, False, None):
            self.assertEqual(_encode_value(value), value)


class TestBuilderMethods(unittest.TestCase):
    """Test that INSERT/UPDATE builders encode non-scalar params."""

    def test_build_columns_and_values_encodes_lists(self):
        from campus.storage.tables.backend.postgres import PostgreSQLTable
        row = {
            "id": "client1",
            "name": "Test Client",
            "is_public": True,
            "redirect_uris": ["http://localhost:5000/finalize_login"],
        }
        column_names, placeholders, values = (
            PostgreSQLTable._build_columns_and_values(row)
        )
        self.assertEqual(
            column_names, "id, name, is_public, redirect_uris")
        self.assertEqual(placeholders, "%s, %s, %s, %s")
        self.assertEqual(values[0], "client1")
        self.assertEqual(values[1], "Test Client")
        self.assertIs(values[2], True)
        self.assertEqual(
            values[3], '["http://localhost:5000/finalize_login"]')

    def test_build_set_clause_encodes_lists(self):
        from campus.storage.tables.backend.postgres import PostgreSQLTable
        update = {
            "name": "Renamed",
            "redirect_uris": ["http://localhost:5000/finalize_login"],
        }
        set_clause, params = PostgreSQLTable._build_set_clause(update)
        self.assertEqual(set_clause, "name = %s, redirect_uris = %s")
        self.assertEqual(params[0], "Renamed")
        self.assertEqual(
            params[1], '["http://localhost:5000/finalize_login"]')


class TestDeserializeRow(unittest.TestCase):
    """Test read-side decoding, mirroring sqlite's _deserialize_row."""

    def test_json_array_decoded_to_list(self):
        from campus.storage.tables.backend.postgres import PostgreSQLTable
        row = {
            "id": "client1",
            "redirect_uris": '["http://localhost:5000/finalize_login"]',
        }
        self.assertEqual(
            PostgreSQLTable._deserialize_row(row)["redirect_uris"],
            ["http://localhost:5000/finalize_login"],
        )

    def test_json_object_decoded_to_dict(self):
        from campus.storage.tables.backend.postgres import PostgreSQLTable
        row = {"meta": '{"scopes": ["read"]}'}
        self.assertEqual(
            PostgreSQLTable._deserialize_row(row)["meta"],
            {"scopes": ["read"]},
        )

    def test_plain_strings_unchanged(self):
        from campus.storage.tables.backend.postgres import PostgreSQLTable
        row = {
            "id": "client1",
            "name": "{Braces Inc}",
            "note": "[not json",
            "email": "test@example.com",
        }
        self.assertEqual(PostgreSQLTable._deserialize_row(row), row)

    def test_invalid_json_string_unchanged(self):
        from campus.storage.tables.backend.postgres import PostgreSQLTable
        # Pre-fix corrupted row: Postgres array literal in a TEXT column
        # is not valid JSON and must be returned as-is.
        row = {"redirect_uris": "{http://localhost:5000/finalize_login}"}
        self.assertEqual(
            PostgreSQLTable._deserialize_row(row)["redirect_uris"],
            "{http://localhost:5000/finalize_login}",
        )

    def test_non_string_values_unchanged(self):
        from campus.storage.tables.backend.postgres import PostgreSQLTable
        row = {"is_public": True, "user_id": 42, "owner": None}
        self.assertEqual(PostgreSQLTable._deserialize_row(row), row)


class _MockConnTestCase(unittest.TestCase):
    """Base: patches _get_connection with a MagicMock connection."""

    def setUp(self):
        from campus.storage.tables.backend.postgres import PostgreSQLTable
        self.cursor = MagicMock()
        self.cursor.__enter__.return_value = self.cursor
        self.conn = MagicMock()
        # psycopg2's connection context manager yields the connection itself
        self.conn.__enter__.return_value = self.conn
        self.conn.cursor.return_value.__enter__.return_value = self.cursor
        patcher = patch.object(
            PostgreSQLTable, "_get_connection", return_value=self.conn)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.table = PostgreSQLTable("vault_clients")


class TestInsertOneBindsJson(_MockConnTestCase):
    """End-to-end through insert_one: the bound params must be JSON."""

    def test_list_bound_as_json_string(self):
        self.table.insert_one({
            "id": "client1",
            "name": "Test Client",
            "redirect_uris": ["http://localhost:5000/finalize_login"],
        })
        (sql, params), _ = self.cursor.execute.call_args
        self.assertIn("INSERT INTO vault_clients", sql)
        self.assertEqual(params[0], "client1")
        self.assertEqual(
            params[2], '["http://localhost:5000/finalize_login"]')

    def test_update_by_id_binds_json_string(self):
        self.cursor.rowcount = 1
        self.table.update_by_id(
            "client1",
            {"redirect_uris": ["http://localhost:5000/finalize_login"]},
        )
        (sql, params), _ = self.cursor.execute.call_args
        self.assertIn("UPDATE vault_clients", sql)
        self.assertEqual(
            params[0], '["http://localhost:5000/finalize_login"]')
        self.assertEqual(params[1], "client1")


class TestGetByIdDecodesJson(_MockConnTestCase):
    """End-to-end through get_by_id: stored JSON must come back as a list."""

    def test_redirect_uris_returned_as_list(self):
        self.cursor.fetchone.return_value = {
            "id": "client1",
            "name": "Test Client",
            "redirect_uris": '["http://localhost:5000/finalize_login"]',
        }
        client = self.table.get_by_id("client1")
        self.assertEqual(
            client["redirect_uris"],
            ["http://localhost:5000/finalize_login"],
        )


class TestEncodeDecodeRoundTrip(unittest.TestCase):
    """Encoding for storage then decoding on read restores the value."""

    def test_round_trip(self):
        from campus.storage.tables.backend.postgres import (
            PostgreSQLTable,
            _encode_value,
        )
        values = [
            ["urn:ietf:wg:oauth:2.0:oob"],
            ["http://a", "http://b"],
            [],
            {"scopes": ["read", "write"]},
        ]
        for value in values:
            stored = _encode_value(value)
            row = PostgreSQLTable._deserialize_row({"col": stored})
            self.assertEqual(row["col"], value)
            self.assertEqual(loads(stored), value)
            self.assertEqual(dumps(value), stored)


if __name__ == "__main__":
    unittest.main()
