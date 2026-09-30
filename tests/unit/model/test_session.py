"""Unit tests for the AuthSession model storage flip (issue #648).

Storage keeps the RFC 6749 scope string; the scopes list is a
model-side convenience. Reads tolerate both shapes.
"""

import unittest

from campus.common import schema
from campus.model import session

CREATED_AT = schema.DateTime("2026-01-01T00:00:00+00:00")
EXPIRES_AT = schema.DateTime("2026-01-01T01:00:00+00:00")


def _make_session() -> session.AuthSession:
    return session.AuthSession(
        id="auth_session_abc123",
        created_at=CREATED_AT,
        expires_at=EXPIRES_AT,
        provider="campus",
        client_id="campus_client_test",
        user_id="user@campus.edu",
        redirect_uri="https://app.test/finalize",
        scopes=["read", "write"],
    )


class TestAuthSessionScopeStorage(unittest.TestCase):
    """Storage keeps the scope string; scopes stays a model view."""

    def test_scope_property_roundtrip(self):
        sess = _make_session()
        self.assertEqual(sess.scope, "read write")
        sess.scope = "read"
        self.assertEqual(sess.scopes, ["read"])
        sess.scope = ["a", "b"]
        self.assertEqual(sess.scopes, ["a", "b"])

    def test_to_storage_emits_scope_string(self):
        record = _make_session().to_storage()
        self.assertEqual(record["scope"], "read write")
        self.assertNotIn("scopes", record)

    def test_storage_roundtrip(self):
        sess = _make_session()
        loaded = session.AuthSession.from_storage(sess.to_storage())
        self.assertEqual(loaded.scopes, ["read", "write"])

    def test_from_storage_tolerates_legacy_scopes_list(self):
        record = _make_session().to_storage()
        record["scopes"] = ["read", "write"]
        record.pop("scope")
        loaded = session.AuthSession.from_storage(record)
        self.assertEqual(loaded.scopes, ["read", "write"])
