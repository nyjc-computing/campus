"""Unit tests for the DeviceCode model storage flip (issue #648).

Storage keeps the RFC 6749 scope string; the scopes list is a
model-side convenience. Reads tolerate both shapes.
"""

import unittest

from campus.common import schema
from campus.model import device_code

CREATED_AT = schema.DateTime("2026-01-01T00:00:00+00:00")
EXPIRES_AT = schema.DateTime("2026-01-01T01:00:00+00:00")


def _make_dc() -> device_code.DeviceCode:
    return device_code.DeviceCode(
        id="device_code_abc123",
        created_at=CREATED_AT,
        expires_at=EXPIRES_AT,
        device_code="dc_123",
        user_code="uc_123",
        client_id="campus_client_test",
        scopes=["read", "write"],
    )


class TestDeviceCodeScopeStorage(unittest.TestCase):
    """Storage keeps the scope string; scopes stays a model view."""

    def test_scope_property_roundtrip(self):
        dc = _make_dc()
        self.assertEqual(dc.scope, "read write")
        dc.scope = "read"
        self.assertEqual(dc.scopes, ["read"])

    def test_to_storage_emits_scope_string(self):
        record = _make_dc().to_storage()
        self.assertEqual(record["scope"], "read write")
        self.assertNotIn("scopes", record)

    def test_storage_roundtrip(self):
        dc = _make_dc()
        loaded = device_code.DeviceCode.from_storage(dc.to_storage())
        self.assertEqual(loaded.scopes, ["read", "write"])
        self.assertEqual(loaded.state, "pending")

    def test_from_storage_tolerates_legacy_scopes_list(self):
        record = _make_dc().to_storage()
        record["scopes"] = ["read", "write"]
        record.pop("scope")
        loaded = device_code.DeviceCode.from_storage(record)
        self.assertEqual(loaded.scopes, ["read", "write"])


class TestDeviceCodeLastPolledAt(unittest.TestCase):
    """last_polled_at (#355) defaults to None and round-trips."""

    def test_unpolled_default_is_none(self):
        self.assertIsNone(_make_dc().last_polled_at)

    def test_storage_roundtrip(self):
        dc = _make_dc()
        dc.last_polled_at = schema.DateTime("2026-01-01T00:00:03+00:00")
        loaded = device_code.DeviceCode.from_storage(dc.to_storage())
        self.assertEqual(
            loaded.last_polled_at, schema.DateTime("2026-01-01T00:00:03+00:00")
        )

    def test_from_storage_tolerates_missing_field(self):
        # Legacy records written before #355 have no last_polled_at
        record = _make_dc().to_storage()
        record.pop("last_polled_at", None)
        loaded = device_code.DeviceCode.from_storage(record)
        self.assertIsNone(loaded.last_polled_at)

    def test_from_storage_tolerates_null_field(self):
        record = _make_dc().to_storage()
        record["last_polled_at"] = None
        self.assertIsNone(
            device_code.DeviceCode.from_storage(record).last_polled_at
        )
