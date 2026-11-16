"""Unit tests for keyed redaction of sensitive span fields (#805).

Covers redact_sensitive() and _is_sensitive_key() in
campus.audit.middleware.tracing: the blocklist matching rules and the
recursive masking of dict/list structures. No storage or network.
"""

import unittest

from campus.audit.middleware.tracing import redact_sensitive


class TestSensitiveKeyMatching(unittest.TestCase):
    """_is_sensitive_key matching rules."""

    def test_exact_keys_from_blocklist(self):
        from campus.audit.middleware.tracing import SENSITIVE_KEYS

        for key in SENSITIVE_KEYS:
            self.assertTrue(
                redact_sensitive({key: "x"})[key] == "[REDACTED]",
                f"key {key!r} should be redacted",
            )

    def test_case_and_dash_variants(self):
        """Header-style casing and dashes match ("Set-Cookie", "X-Api-Key")."""
        span = redact_sensitive({
            "Cookie": "session=abc",
            "set-cookie": "sid=xyz",
            "Client_Secret": "s",
        })
        self.assertEqual(span["Cookie"], "[REDACTED]")
        self.assertEqual(span["set-cookie"], "[REDACTED]")
        self.assertEqual(span["Client_Secret"], "[REDACTED]")

    def test_suffix_variants(self):
        """Prefixed variants (google_refresh_token, db_password) match."""
        span = redact_sensitive({
            "google_refresh_token": "r",
            "db_password": "p",
            "upstream_client_secret": "s",
        })
        self.assertEqual(span["google_refresh_token"], "[REDACTED]")
        self.assertEqual(span["db_password"], "[REDACTED]")
        self.assertEqual(span["upstream_client_secret"], "[REDACTED]")

    def test_non_sensitive_keys_untouched(self):
        """Identifiers and metadata stay visible: they are the point of audit."""
        span = redact_sensitive({
            "client_id": "uid-client-1",
            "user_id": "uid-user-1",
            "grant_type": "authorization_code",
            "token_type": "Bearer",
            "expires_in": 3600,
            "api_key_id": "uid-apikey-1",
            "redirect_uri": "https://app.test/cb",
        })
        self.assertEqual(
            span,
            {
                "client_id": "uid-client-1",
                "user_id": "uid-user-1",
                "grant_type": "authorization_code",
                "token_type": "Bearer",
                "expires_in": 3600,
                "api_key_id": "uid-apikey-1",
                "redirect_uri": "https://app.test/cb",
            },
        )

    def test_oauth_code_deliberately_visible(self):
        """Bare `code` stays visible (single-use; its exchange secret is
        redacted). Pins the documented gap so a change is a decision."""
        span = redact_sensitive({"code": "_1h707"})
        self.assertEqual(span["code"], "_1h707")


class TestRedactSensitiveStructures(unittest.TestCase):
    """Recursive masking across the span's stored JSON fields."""

    def test_nested_dicts_and_lists(self):
        body = {
            "client_id": "uid-client-1",
            "credentials": [
                {"token": "t1", "scopes": ["a"]},
                {"nested": {"password": "p"}},
            ],
        }
        redacted = redact_sensitive(body)

        self.assertEqual(redacted["client_id"], "uid-client-1")
        self.assertEqual(redacted["credentials"][0]["token"], "[REDACTED]")
        self.assertEqual(redacted["credentials"][0]["scopes"], ["a"])
        self.assertEqual(
            redacted["credentials"][1]["nested"]["password"], "[REDACTED]"
        )
        # Input not mutated
        self.assertEqual(body["credentials"][0]["token"], "t1")

    def test_scalars_and_text_pass_through(self):
        """Free-text bodies can't be key-redacted (gap documented in #805)."""
        self.assertEqual(redact_sensitive("secret=abc"), "secret=abc")
        self.assertEqual(redact_sensitive(42), 42)
        self.assertIsNone(redact_sensitive(None))


if __name__ == "__main__":
    unittest.main()
