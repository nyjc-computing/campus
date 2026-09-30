"""Unit tests for campus.auth.resources.session record mapping.

Covers the _from_record boundary: expiry_seconds passthrough to the
model InitVar (fixes the previous behavior of silently substituting the
config default) and scope/scopes dual acceptance from storage records
(#648 storage flip).
"""

import unittest


class TestSessionFromRecord(unittest.TestCase):
    """_from_record builds AuthSession from storage records or kwargs."""

    def _from_record(self, record):
        # Lazy import: storage backends must initialize after test mode
        # is set (see tests/README.md gotchas). Import the submodule
        # directly: campus.auth.resources shadows `session` with its
        # resource singleton.
        from campus.auth.resources.session import _from_record
        return _from_record(record)

    def _base_record(self, **overrides):
        record = {
            "id": "campus_session_abc123",
            "created_at": "2026-01-01T00:00:00+00:00",
            "provider": "campus",
            "client_id": "campus_client_test",
            "redirect_uri": "https://app.test/finalize",
        }
        record.update(overrides)
        return record

    def test_expiry_seconds_passthrough(self):
        """expiry_seconds without expires_at must be honored, not
        replaced by the config default (regression: the old shim
        derived expires_at from DEFAULT_OAUTH_EXPIRY_MINUTES)."""
        sess = self._from_record(self._base_record(
            expiry_seconds=120,
            scope="read",
        ))
        delta = sess.expires_at.to_datetime() - sess.created_at.to_datetime()
        self.assertEqual(int(delta.total_seconds()), 120)
        self.assertEqual(sess.scopes, ["read"])

    def test_scope_string_accepted(self):
        """Storage records carry the scope string (#648 end state)."""
        sess = self._from_record(self._base_record(
            expires_at="2026-01-01T01:00:00+00:00",
            scope="read write",
        ))
        self.assertEqual(sess.scopes, ["read", "write"])

    def test_legacy_scopes_list_accepted(self):
        """Pre-flip storage records carry the scopes list."""
        sess = self._from_record(self._base_record(
            expires_at="2026-01-01T01:00:00+00:00",
            scopes=["read", "write"],
        ))
        self.assertEqual(sess.scopes, ["read", "write"])


if __name__ == "__main__":
    unittest.main()
